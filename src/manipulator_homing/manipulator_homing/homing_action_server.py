"""Homing action server for the EtherCAT manipulator (Stage 6.6b).

Walks each requested joint through the CiA 402 homing sequence:

  1. Take motion controllers (JTC / FPC) off the joint by deactivating
     them through controller_manager's switch_controller service, and
     activate the helper controllers that own the ``control_word`` and
     ``mode_of_operation`` command interfaces.
  2. For each joint, in the order given by the goal:
       a. Publish a mode_of_operation vector with that slot flipped to
          6 (Homing) — every other joint stays at 8 (CSP) so it keeps
          following its last position command unchanged.
       b. Wait until the drive reports mode_of_operation_display == 6.
       c. Publish a control_word vector with that slot at 0x001F
          (Enable Operation + Homing start = bit 4). Other slots stay
          NaN so the EcCiA402Drive plugin keeps writing its own
          state-machine value.
       d. Poll status_word: bit 12 (HomingAttained) -> done, bit 13
          (HomingError) -> fail, no transition before ``timeout`` -> fail.
       e. Clear bit 4 (0x000F), flip mode back to 8, wait for
          mode_of_operation_display == 8.
  3. Switch motion controllers back on.

A subset goal (``joint_names: ['scara_wrist_joint']`` or any 1..N list)
is honoured verbatim — the loop walks exactly those joints in the order
given, leaving the rest untouched. Empty list = home every joint listed
in the ``joints`` parameter.

For Stage 6.6b bring-up the slave YAML ships method 35 (set current
position = 0, no motion); the server therefore tests the whole flip-
mode-and-poll-bit-12 pipeline without any axis actually moving. Once
each axis' hardstop direction is known, change 0x6098 in a6_slave.yaml
(or per-joint via SDO) and rerun.
"""

import math
from typing import Dict, List, Optional, Tuple

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.action.server import ServerGoalHandle
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.task import Future

from control_msgs.msg import DynamicJointState
from controller_manager_msgs.srv import SwitchController
from std_msgs.msg import Float64MultiArray

from manipulator_msgs.action import HomeJoints


# CiA 402 ControlWord bits. Manual §6.1.2.
CW_ENABLE_OPERATION = 0x000F   # bits 0..3 = 1111: drive ready + operation enabled
CW_HOMING_START_BIT = 0x0010   # bit 4: in mode 6 a rising edge starts a homing run
CW_HOMING_START = CW_ENABLE_OPERATION | CW_HOMING_START_BIT  # 0x001F

# CiA 402 StatusWord bits. Manual §6.1.3.
SW_BIT_INTERNAL_LIMIT_ACTIVE = 1 << 11  # 0x0800 - drive self-clamped on overtravel
SW_BIT_HOMING_ATTAINED       = 1 << 12  # 0x1000 - mode-6 specific success flag
SW_BIT_HOMING_ERROR          = 1 << 13  # 0x2000 - mode-6 specific failure flag

MODE_CSP    = 8
MODE_HOMING = 6


class HomingActionServer(Node):

    def __init__(self) -> None:
        super().__init__('homing_action_server')

        # Canonical joint order as published by the helper controllers.
        # MUST match the `joints:` list in their YAML — the index in
        # Float64MultiArray.data corresponds to the joint at the same
        # index here.
        self.declare_parameter('joints', [
            'base_main_frame_joint',
            'main_frame_selector_frame_joint',
            'selector_frame_picker_frame_joint',
            'scara_shoulder_joint',
            'scara_elbow_joint',
            'scara_wrist_joint',
        ])
        self.declare_parameter('mode_command_topic',
                               '/mode_of_operation_controller/commands')
        self.declare_parameter('control_word_command_topic',
                               '/control_word_controller/commands')
        self.declare_parameter('dynamic_joint_states_topic',
                               '/dynamic_joint_states')
        self.declare_parameter('controller_manager_service',
                               '/controller_manager/switch_controller')
        # Controllers that hand command_interface ownership of
        # control_word / mode_of_operation to this action server.
        self.declare_parameter('homing_controllers', [
            'mode_of_operation_controller',
            'control_word_controller',
        ])
        # Controllers gripping position command_interface during normal
        # operation. Deactivated while a homing run is in flight so
        # they do not fight the action server for command ownership
        # (ros2_control rejects two controllers claiming the same
        # command_interface).
        self.declare_parameter('motion_controllers', [
            'manipulator_trajectory_controller',
        ])
        self.declare_parameter('default_timeout_sec', 30.0)
        # 50 ms is comfortable for an operator and keeps the executor
        # responsive without spamming.
        self.declare_parameter('poll_period_sec', 0.05)
        # Latency budget for one PDO cycle (1 ms master) plus state
        # publisher round-trip.
        self.declare_parameter('settle_after_command_sec', 0.05)

        self._joints: List[str] = list(self.get_parameter('joints').value)
        self._joint_index: Dict[str, int] = {j: i for i, j in enumerate(self._joints)}

        self._mode_pub = self.create_publisher(
            Float64MultiArray,
            self.get_parameter('mode_command_topic').value,
            10,
        )
        self._cw_pub = self.create_publisher(
            Float64MultiArray,
            self.get_parameter('control_word_command_topic').value,
            10,
        )

        cb_group = ReentrantCallbackGroup()
        self.create_subscription(
            DynamicJointState,
            self.get_parameter('dynamic_joint_states_topic').value,
            self._state_cb,
            10,
            callback_group=cb_group,
        )
        self._switch_cli = self.create_client(
            SwitchController,
            self.get_parameter('controller_manager_service').value,
            callback_group=cb_group,
        )

        # Latest per-joint state, keyed by (joint, interface).
        self._state: Dict[str, Dict[str, float]] = {j: {} for j in self._joints}

        self._action_server = ActionServer(
            self,
            HomeJoints,
            'home_joints',
            execute_callback=self._execute_callback,
            goal_callback=self._goal_callback,
            cancel_callback=self._cancel_callback,
            callback_group=cb_group,
        )

        self.get_logger().info(
            f'HomingActionServer ready: joints={self._joints}, '
            f'mode topic={self._mode_pub.topic_name}, '
            f'cw topic={self._cw_pub.topic_name}'
        )

    # ----- callbacks -----

    def _state_cb(self, msg: DynamicJointState) -> None:
        for name, iv in zip(msg.joint_names, msg.interface_values):
            if name not in self._state:
                continue
            for iface, value in zip(iv.interface_names, iv.values):
                self._state[name][iface] = value

    def _goal_callback(self, goal_request) -> GoalResponse:
        unknown = [j for j in goal_request.joint_names
                   if j and j not in self._joint_index]
        if unknown:
            self.get_logger().warn(
                f'Rejecting homing goal — unknown joints: {unknown}. '
                f'Known: {self._joints}'
            )
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _cancel_callback(self, goal_handle: ServerGoalHandle) -> CancelResponse:
        self.get_logger().warn('Homing cancel requested; will stop after current joint.')
        return CancelResponse.ACCEPT

    # ----- execute -----

    async def _execute_callback(self, goal_handle: ServerGoalHandle):
        goal = goal_handle.request
        joints = list(goal.joint_names) if goal.joint_names else list(self._joints)
        per_joint_timeout = (
            goal.timeout if goal.timeout > 0.0
            else float(self.get_parameter('default_timeout_sec').value)
        )

        result = HomeJoints.Result()
        result.homed_joints = []
        result.failed_joints = []

        if not await self._switch_controllers(
            activate=list(self.get_parameter('homing_controllers').value),
            deactivate=list(self.get_parameter('motion_controllers').value),
        ):
            goal_handle.abort()
            result.success = False
            result.message = 'Failed to activate homing controllers — see controller_manager log.'
            return result

        # Seed both vectors at idle defaults so the first publish to a
        # single slot doesn't accidentally drive the others.
        self._publish_mode_vector({j: MODE_CSP for j in self._joints})
        self._publish_cw_vector({j: math.nan for j in self._joints})

        try:
            for joint in joints:
                if goal_handle.is_cancel_requested:
                    goal_handle.canceled()
                    result.success = False
                    result.message = f'Cancelled before completing {joint}.'
                    return result

                ok, why = await self._home_one(joint, per_joint_timeout, goal_handle)
                if ok:
                    result.homed_joints.append(joint)
                else:
                    # Stop the whole sequence on first failure: a
                    # half-homed manipulator is more dangerous than
                    # a not-homed one — operator must inspect.
                    result.failed_joints.append(joint)
                    result.success = False
                    result.message = f'{joint}: {why}'
                    goal_handle.abort()
                    return result
        finally:
            await self._switch_controllers(
                activate=list(self.get_parameter('motion_controllers').value),
                deactivate=list(self.get_parameter('homing_controllers').value),
            )

        result.success = True
        result.message = f'Homed {len(result.homed_joints)} joints.'
        goal_handle.succeed()
        return result

    # ----- per-joint sequence -----

    async def _home_one(self, joint: str, timeout: float,
                        goal_handle: ServerGoalHandle) -> Tuple[bool, str]:
        self._publish_feedback(goal_handle, joint, 'entering_homing_mode')
        self._publish_mode_vector({joint: MODE_HOMING})
        ok = await self._wait_for(
            joint, 'mode_of_operation',
            lambda v: int(v) == MODE_HOMING,
            timeout=5.0, goal_handle=goal_handle,
        )
        if not ok:
            return False, 'drive did not report mode_of_operation_display = 6'

        self._publish_cw_vector({joint: CW_HOMING_START})
        await self._sleep(float(self.get_parameter('settle_after_command_sec').value))

        self._publish_feedback(goal_handle, joint, 'homing_in_progress')
        ok = await self._wait_for_homing(joint, timeout, goal_handle)
        # Drop bit 4 regardless of outcome. Leaving it asserted while
        # the drive is in HomingAttained is harmless but on Error we
        # want it cleared so a fault reset can recover.
        self._publish_cw_vector({joint: math.nan})

        if not ok:
            self._publish_feedback(goal_handle, joint, 'error')
            return False, 'homing timed out or reported error (StatusWord bit 13)'

        self._publish_feedback(goal_handle, joint, 'leaving_homing_mode')
        self._publish_mode_vector({joint: MODE_CSP})
        ok = await self._wait_for(
            joint, 'mode_of_operation',
            lambda v: int(v) == MODE_CSP,
            timeout=5.0, goal_handle=goal_handle,
        )
        if not ok:
            return False, 'drive did not return to mode_of_operation_display = 8 (CSP)'

        self._publish_feedback(goal_handle, joint, 'done')
        return True, 'ok'

    async def _wait_for_homing(self, joint: str, timeout: float,
                               goal_handle: ServerGoalHandle) -> bool:
        deadline = self.get_clock().now().nanoseconds + int(timeout * 1e9)
        poll = float(self.get_parameter('poll_period_sec').value)
        while self.get_clock().now().nanoseconds < deadline:
            if goal_handle.is_cancel_requested:
                return False
            sw = int(self._state.get(joint, {}).get('status_word', 0))
            if sw & SW_BIT_HOMING_ERROR:
                self._publish_feedback(goal_handle, joint, 'error', sw)
                return False
            if sw & SW_BIT_HOMING_ATTAINED:
                self._publish_feedback(goal_handle, joint, 'homing_in_progress', sw)
                return True
            await self._sleep(poll)
        return False

    async def _wait_for(self, joint: str, interface: str, predicate,
                        timeout: float, goal_handle: ServerGoalHandle) -> bool:
        deadline = self.get_clock().now().nanoseconds + int(timeout * 1e9)
        poll = float(self.get_parameter('poll_period_sec').value)
        while self.get_clock().now().nanoseconds < deadline:
            if goal_handle.is_cancel_requested:
                return False
            value = self._state.get(joint, {}).get(interface)
            if value is not None and predicate(value):
                return True
            await self._sleep(poll)
        return False

    # ----- command publishing -----

    def _publish_mode_vector(self, overrides: Dict[str, float]) -> None:
        # Slots not in `overrides` default to CSP — we never want a
        # sibling joint to drift into an unintended mode while we
        # operate on a different one.
        msg = Float64MultiArray()
        msg.data = [float(overrides.get(j, MODE_CSP)) for j in self._joints]
        self._mode_pub.publish(msg)

    def _publish_cw_vector(self, overrides: Dict[str, float]) -> None:
        # NaN tells the EcCiA402Drive channel manager to fall back to
        # the plugin's transition()-managed default_value, i.e. keep
        # the CiA 402 state machine in charge. Only the joint currently
        # being homed gets a numeric override.
        msg = Float64MultiArray()
        msg.data = [float(overrides.get(j, math.nan)) for j in self._joints]
        self._cw_pub.publish(msg)

    def _publish_feedback(self, goal_handle: ServerGoalHandle, joint: str,
                          phase: str, status_word: Optional[int] = None) -> None:
        fb = HomeJoints.Feedback()
        fb.current_joint = joint
        fb.phase = phase
        fb.status_word = (
            status_word if status_word is not None
            else int(self._state.get(joint, {}).get('status_word', 0))
        )
        goal_handle.publish_feedback(fb)

    # ----- helpers -----

    async def _switch_controllers(self, activate: List[str],
                                  deactivate: List[str]) -> bool:
        # Empty lists are common (no JTC yet on first bring-up) — skip
        # the call rather than hit the service with a no-op request.
        if not activate and not deactivate:
            return True
        if not self._switch_cli.wait_for_service(timeout_sec=5.0):
            self.get_logger().error(
                f'switch_controller service '
                f'{self._switch_cli.srv_name} not available.'
            )
            return False
        req = SwitchController.Request()
        req.activate_controllers = activate
        req.deactivate_controllers = deactivate
        # BEST_EFFORT so a controller already in the desired state is
        # treated as success; STRICT would abort and surface as a
        # failed homing goal for no useful reason.
        req.strictness = SwitchController.Request.BEST_EFFORT
        req.activate_asap = True
        future = self._switch_cli.call_async(req)
        await future
        resp = future.result()
        if not resp.ok:
            self.get_logger().error(
                f'switch_controller failed: activate={activate} deactivate={deactivate}'
            )
            return False
        return True

    async def _sleep(self, seconds: float) -> None:
        # rclpy has no first-class async sleep; one-shot timer + future
        # is the standard pattern. time.sleep would block the executor
        # and starve the state subscription.
        future = Future()
        timer = self.create_timer(seconds, lambda: future.set_result(True))
        try:
            await future
        finally:
            self.destroy_timer(timer)


def main(args=None):
    rclpy.init(args=args)
    node = HomingActionServer()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
