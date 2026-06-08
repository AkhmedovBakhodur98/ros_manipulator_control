"""Sine trajectory driver for the full-chain EtherCAT soak test.

Streams a continuous sinusoid on every joint via the JointTrajectoryController
``FollowJointTrajectory`` action — the same path through which real
applications will command motion. Goals are sent in fixed-length segments
(``segment_period_sec``) back-to-back; the sine phase is computed from
absolute wall time inside the node, so the seam between two segments is
mathematically continuous in both position and velocity.

Per-joint amplitude and phase are independent vectors — set
``amplitudes_counts[i] = 0.0`` to leave joint i stationary (useful for
sequential per-axis probes without rewriting the joint list).

Low-amplitude defaults (±50 000 counts ≈ 0.38 motor revolutions at the
17-bit encoder, period 20 s → peak velocity ≈ 15 700 counts/s ≈ 7.2 rpm
on the motor side) match the bench-interactive feedback memo (5–10 rpm
is the comfortable range for operator-attended runs).
"""

import math
from typing import List

import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.task import Future

from builtin_interfaces.msg import Duration
from control_msgs.action import FollowJointTrajectory
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint


class SineTrajectoryDriver(Node):

    def __init__(self) -> None:
        super().__init__('sine_trajectory_driver')

        self.declare_parameter('joints', [
            'base_main_frame_joint',
            'main_frame_selector_frame_joint',
            'selector_frame_picker_frame_joint',
            'scara_shoulder_joint',
            'scara_elbow_joint',
            'scara_wrist_joint',
        ])
        # Per-joint amplitude (counts). Length must match `joints`. Zero
        # = joint is held at its centre; sequential per-axis probes can
        # be done by zeroing every entry except one without touching
        # the joints list (or the controller config).
        self.declare_parameter('amplitudes_counts', [
            50000.0, 50000.0, 50000.0, 50000.0, 50000.0, 50000.0,
        ])
        # Per-joint phase offset (rad). Defaults stagger the six joints
        # by 2*pi/6 so they don't all swing through zero at the same
        # instant — exercises the bus under varied per-cycle command
        # magnitudes rather than a single big synchronised spike.
        self.declare_parameter('phases_rad', [
            0.0,
            math.pi / 3.0,
            2.0 * math.pi / 3.0,
            math.pi,
            4.0 * math.pi / 3.0,
            5.0 * math.pi / 3.0,
        ])
        self.declare_parameter('period_sec', 20.0)
        self.declare_parameter('segment_period_sec', 30.0)
        self.declare_parameter('point_period_sec', 0.5)
        self.declare_parameter('action_name',
                               '/manipulator_trajectory_controller/follow_joint_trajectory')
        self.declare_parameter('wait_for_server_sec', 30.0)

        self._joints: List[str] = list(self.get_parameter('joints').value)
        self._amplitudes: List[float] = [
            float(x) for x in self.get_parameter('amplitudes_counts').value
        ]
        self._phases: List[float] = [
            float(x) for x in self.get_parameter('phases_rad').value
        ]
        for vec, name in ((self._amplitudes, 'amplitudes_counts'),
                          (self._phases, 'phases_rad')):
            if len(vec) != len(self._joints):
                raise ValueError(
                    f'{name} length ({len(vec)}) != joints length ({len(self._joints)})'
                )

        self._period = float(self.get_parameter('period_sec').value)
        self._segment_period = float(self.get_parameter('segment_period_sec').value)
        self._point_period = float(self.get_parameter('point_period_sec').value)
        # Pre-compute the angular velocity coefficient so we don't redo
        # it inside the inner loop (the inner loop runs O(thousands)
        # times over a 4 h soak — cheap but not free).
        self._omega = 2.0 * math.pi / self._period

        cb_group = ReentrantCallbackGroup()
        self._client = ActionClient(
            self,
            FollowJointTrajectory,
            self.get_parameter('action_name').value,
            callback_group=cb_group,
        )

        # Anchor sine time at the moment the action server first
        # accepts a goal — not at node startup — so segment boundaries
        # are aligned with what the controller actually executed.
        self._anchor_time = None
        self._segment_index = 0
        self._goal_in_flight = False
        self._goal_handle = None
        self._shutting_down = False

        # Single periodic pump. The actual goal lifecycle is callback-
        # driven; the timer just nudges the pump if a goal hasn't been
        # sent yet (cold start) or if the previous one finished while
        # the pump was sleeping.
        self._pump_timer = self.create_timer(0.1, self._pump, callback_group=cb_group)

        self.get_logger().info(
            f'SineTrajectoryDriver waiting for '
            f'{self.get_parameter("action_name").value}'
        )

    def _pump(self) -> None:
        if self._shutting_down or self._goal_in_flight:
            return
        if not self._client.wait_for_server(timeout_sec=0.0):
            return
        if self._anchor_time is None:
            self._anchor_time = self.get_clock().now()
            self.get_logger().info(
                f'Sine driver anchor time set; sending segments of '
                f'{self._segment_period:.1f} s'
            )
        self._send_segment()

    def _send_segment(self) -> None:
        seg_start_t = self._segment_index * self._segment_period
        traj = JointTrajectory()
        traj.joint_names = self._joints

        n_points = max(2, int(round(self._segment_period / self._point_period)))
        # Inclusive of the final point so positions exactly line up with
        # the next segment's t=0 sample — gives JTC a clean handoff.
        for i in range(n_points + 1):
            t_local = i * self._point_period
            t_abs = seg_start_t + t_local
            point = JointTrajectoryPoint()
            point.positions = [
                amp * math.sin(self._omega * t_abs + ph)
                for amp, ph in zip(self._amplitudes, self._phases)
            ]
            point.velocities = [
                amp * self._omega * math.cos(self._omega * t_abs + ph)
                for amp, ph in zip(self._amplitudes, self._phases)
            ]
            sec = int(t_local)
            nsec = int((t_local - sec) * 1e9)
            point.time_from_start = Duration(sec=sec, nanosec=nsec)
            traj.points.append(point)

        goal = FollowJointTrajectory.Goal()
        goal.trajectory = traj

        self._goal_in_flight = True
        future = self._client.send_goal_async(goal)
        future.add_done_callback(self._on_goal_response)

    def _on_goal_response(self, future: Future) -> None:
        try:
            self._goal_handle = future.result()
        except Exception as exc:
            self.get_logger().error(f'send_goal raised: {exc}')
            self._goal_in_flight = False
            return
        if not self._goal_handle.accepted:
            self.get_logger().error('JTC rejected the trajectory goal')
            self._goal_in_flight = False
            return
        result_future = self._goal_handle.get_result_async()
        result_future.add_done_callback(self._on_result)

    def _on_result(self, future: Future) -> None:
        try:
            result = future.result().result
        except Exception as exc:
            self.get_logger().error(f'result future raised: {exc}')
            self._goal_in_flight = False
            return

        if result.error_code != 0:
            # Don't crash the soak on a single segment failure — log
            # and keep streaming. The soak monitor counts these via
            # /diagnostics independently.
            self.get_logger().warn(
                f'JTC segment {self._segment_index} '
                f'returned error_code={result.error_code} '
                f'msg="{result.error_string}"'
            )
        self._segment_index += 1
        self._goal_in_flight = False

    def cancel_current(self) -> None:
        self._shutting_down = True
        if self._goal_handle is None:
            return
        try:
            self._goal_handle.cancel_goal_async()
        except Exception as exc:
            self.get_logger().warn(f'cancel raised: {exc}')


def main(args=None):
    rclpy.init(args=args)
    node = SineTrajectoryDriver()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        node.get_logger().info('Ctrl-C — cancelling current segment')
        node.cancel_current()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
