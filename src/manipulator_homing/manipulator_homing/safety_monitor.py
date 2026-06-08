"""Safety / limit monitor for the EtherCAT manipulator (Stage 6.6b).

Subscribes to ``/dynamic_joint_states`` and watches each joint's
``status_word`` (bit 11 = Internal limit active) and ``digital_inputs``
(bit 0 = N-OT, bit 1 = P-OT). When a drive raises one of these the
node publishes a latched ``OvertravelEvent`` on ``/overtravel_events``
so application/UI layers can react to a self-clamping drive instead
of trusting JTC's ``SUCCEEDED`` result (the hole exposed in Stage 6.6a:
JTC keeps streaming targets and reports success while the drive is
silently halting on its overtravel input).

Events are emitted on the rising edge of each condition (per joint).
A falling edge emits a clear event with all booleans cleared so a UI
can flip a banner back off without polling. Latched edge tracking is
in-process; if the node restarts, the next sample triggers an event
again.

Optional: with ``trip_action: hold`` (default: ``log_only``) the node
calls ``switch_controller`` to swap the motion controllers for a
do-nothing ``forward_command_controller`` that just freezes the last
position command. This is the brutal-but-safe response and stays off
by default because the operator may not want every transient bounce
to abort the run.
"""

from typing import Dict, List

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from control_msgs.msg import DynamicJointState
from controller_manager_msgs.srv import SwitchController

from manipulator_msgs.msg import OvertravelEvent


SW_BIT_INTERNAL_LIMIT_ACTIVE = 1 << 11
DI_BIT_N_OT = 1 << 0
DI_BIT_P_OT = 1 << 1


class _JointState:
    """Per-joint latched flags so we publish on edges, not every cycle."""

    __slots__ = ('p_ot', 'n_ot', 'internal_limit')

    def __init__(self) -> None:
        self.p_ot = False
        self.n_ot = False
        self.internal_limit = False


class SafetyMonitor(Node):

    def __init__(self) -> None:
        super().__init__('safety_monitor')

        self.declare_parameter('joints', [
            'base_main_frame_joint',
            'main_frame_selector_frame_joint',
            'selector_frame_picker_frame_joint',
            'scara_shoulder_joint',
            'scara_elbow_joint',
            'scara_wrist_joint',
        ])
        self.declare_parameter('event_topic', '/overtravel_events')
        self.declare_parameter('dynamic_joint_states_topic',
                               '/dynamic_joint_states')
        # log_only — just publish events. hold — additionally swap motion
        # controllers off via controller_manager. Anything else is
        # treated as log_only.
        self.declare_parameter('trip_action', 'log_only')
        self.declare_parameter('controller_manager_service',
                               '/controller_manager/switch_controller')
        self.declare_parameter('motion_controllers', [
            'manipulator_trajectory_controller',
        ])

        self._joints: List[str] = list(self.get_parameter('joints').value)
        self._latched: Dict[str, _JointState] = {
            j: _JointState() for j in self._joints
        }

        self._event_pub = self.create_publisher(
            OvertravelEvent,
            self.get_parameter('event_topic').value,
            # KEEP_LAST 50 — overtravel is rare; we want the last few
            # events available to late subscribers (e.g. a UI that
            # connects after the trip).
            50,
        )

        cb_group = ReentrantCallbackGroup()
        self.create_subscription(
            DynamicJointState,
            self.get_parameter('dynamic_joint_states_topic').value,
            self._state_cb,
            10,
            callback_group=cb_group,
        )

        if self.get_parameter('trip_action').value == 'hold':
            self._switch_cli = self.create_client(
                SwitchController,
                self.get_parameter('controller_manager_service').value,
                callback_group=cb_group,
            )
        else:
            self._switch_cli = None

        self.get_logger().info(
            f'SafetyMonitor watching {len(self._joints)} joints, '
            f'trip_action={self.get_parameter("trip_action").value}'
        )

    def _state_cb(self, msg: DynamicJointState) -> None:
        for name, iv in zip(msg.joint_names, msg.interface_values):
            if name not in self._latched:
                continue
            sw = di = 0
            sw_seen = di_seen = False
            for iface, value in zip(iv.interface_names, iv.values):
                if iface == 'status_word':
                    sw = int(value)
                    sw_seen = True
                elif iface == 'digital_inputs':
                    di = int(value)
                    di_seen = True

            # Both interfaces must be present before we evaluate —
            # otherwise we'd publish phantom "all clear" events when
            # only one half of the picture arrives in a frame.
            if not (sw_seen and di_seen):
                continue

            internal = bool(sw & SW_BIT_INTERNAL_LIMIT_ACTIVE)
            n_ot = bool(di & DI_BIT_N_OT)
            p_ot = bool(di & DI_BIT_P_OT)

            latch = self._latched[name]
            if (internal == latch.internal_limit
                    and p_ot == latch.p_ot
                    and n_ot == latch.n_ot):
                continue

            latch.internal_limit = internal
            latch.p_ot = p_ot
            latch.n_ot = n_ot

            ev = OvertravelEvent()
            ev.stamp = self.get_clock().now().to_msg()
            ev.joint_name = name
            ev.status_word = sw
            ev.digital_inputs = di
            ev.p_ot_active = p_ot
            ev.n_ot_active = n_ot
            ev.internal_limit_active = internal
            self._event_pub.publish(ev)

            if internal or p_ot or n_ot:
                self.get_logger().warn(
                    f'OVERTRAVEL {name}: '
                    f'internal={internal} p_ot={p_ot} n_ot={n_ot} '
                    f'sw=0x{sw:04x} di=0x{di:08x}'
                )
                if self._switch_cli is not None:
                    self._trip()
            else:
                self.get_logger().info(f'overtravel cleared on {name}')

    def _trip(self) -> None:
        # Async fire-and-forget — we cannot await here, _state_cb is
        # called from the executor on a regular (non-async) thread.
        if not self._switch_cli.service_is_ready():
            self.get_logger().error(
                f'trip requested but {self._switch_cli.srv_name} not available'
            )
            return
        req = SwitchController.Request()
        req.deactivate_controllers = list(
            self.get_parameter('motion_controllers').value
        )
        req.strictness = SwitchController.Request.BEST_EFFORT
        future = self._switch_cli.call_async(req)
        future.add_done_callback(self._trip_done)

    def _trip_done(self, future) -> None:
        try:
            resp = future.result()
        except Exception as exc:
            self.get_logger().error(f'trip switch_controller raised: {exc}')
            return
        if resp.ok:
            self.get_logger().warn('trip: motion controllers deactivated')
        else:
            self.get_logger().error('trip: switch_controller refused the request')


def main(args=None):
    rclpy.init(args=args)
    node = SafetyMonitor()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
