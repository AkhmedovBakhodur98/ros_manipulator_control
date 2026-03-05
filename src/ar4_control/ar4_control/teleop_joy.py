#!/usr/bin/env python3
"""DualShock 4 joystick teleoperation node for AR4 arm.

Subscribes to /joy (sensor_msgs/Joy) and publishes joint jog velocities
to /ar4_hardware/jog (std_msgs/Float64MultiArray).

DS4 mapping (CUH-ZCT2E):
  Left stick X/Y  -> J1 (base) / J2 (shoulder)
  Right stick Y/X  -> J3 (elbow) / J4 (forearm roll)
  L1/R1 buttons    -> J5 negative/positive
  D-pad X          -> J6 (wrist roll)
  SHARE            -> call /ar4_hardware/start
  OPTIONS          -> emergency stop (all zeros)
  Cross/Triangle   -> speed scale down/up
"""

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from control_msgs.action import FollowJointTrajectory
from sensor_msgs.msg import Joy
from std_msgs.msg import Float64MultiArray
from std_srvs.srv import Trigger
from trajectory_msgs.msg import JointTrajectoryPoint
from builtin_interfaces.msg import Duration


class TeleopJoy(Node):
    # DS4 axis indices (Bluetooth: 6 axes, no D-pad axis)
    AXIS_LEFT_X = 0
    AXIS_LEFT_Y = 1
    AXIS_RIGHT_X = 2
    AXIS_RIGHT_Y = 3

    BTN_CROSS = 0
    BTN_SQUARE = 2
    BTN_TRIANGLE = 3
    BTN_L1 = 9
    BTN_R1 = 10
    BTN_SHARE = 7
    BTN_OPTIONS = 6

    DEADZONE = 0.1
    SPEED_STEP = 0.1

    def __init__(self):
        super().__init__('teleop_joy')

        # Max speeds per joint in rad/s (configurable via ROS params)
        self.declare_parameter('max_speed_j1', 0.69)
        self.declare_parameter('max_speed_j2', 0.69)
        self.declare_parameter('max_speed_j3', 0.47)
        self.declare_parameter('max_speed_j4', 0.79)
        self.declare_parameter('max_speed_j5', 3.14)
        self.declare_parameter('max_speed_j6', 0.5)

        self.max_speeds = [
            self.get_parameter('max_speed_j1').value,
            self.get_parameter('max_speed_j2').value,
            self.get_parameter('max_speed_j3').value,
            self.get_parameter('max_speed_j4').value,
            self.get_parameter('max_speed_j5').value,
            self.get_parameter('max_speed_j6').value,
        ]

        self.speed_scale = 0.5
        self.prev_buttons = []

        self.jog_pub = self.create_publisher(Float64MultiArray, '/ar4_hardware/jog', 10)
        self.joy_sub = self.create_subscription(Joy, '/joy', self.joy_callback, 10)

        self.start_client = self.create_client(Trigger, '/ar4_hardware/start')
        self.trajectory_client = ActionClient(
            self, FollowJointTrajectory, '/arm_controller/follow_joint_trajectory')
        self.joint_names = ['J1', 'J2', 'J3', 'J4', 'J5', 'J6']

        self.get_logger().info(
            f'Teleop ready. Speed scale: {self.speed_scale:.1f}. '
            'Press SHARE to START, OPTIONS to STOP.')

    def apply_deadzone(self, value):
        if abs(value) < self.DEADZONE:
            return 0.0
        return value

    def joy_callback(self, msg: Joy):
        axes = msg.axes
        buttons = msg.buttons

        if len(axes) < 5 or len(buttons) < 10:
            return

        # Detect button press edges
        def pressed(btn_idx):
            if not self.prev_buttons:
                return False
            return buttons[btn_idx] and not self.prev_buttons[btn_idx]

        # SHARE -> START
        if pressed(self.BTN_SHARE):
            self.call_start()

        # OPTIONS -> emergency stop
        if pressed(self.BTN_OPTIONS):
            self.get_logger().warn('EMERGENCY STOP')
            stop_msg = Float64MultiArray()
            stop_msg.data = [0.0] * 6
            self.jog_pub.publish(stop_msg)
            self.prev_buttons = list(buttons)
            return

        # SQUARE -> go to all zeros
        if pressed(self.BTN_SQUARE):
            self.go_to_zero()
            self.prev_buttons = list(buttons)
            return

        # Speed scale adjustment
        if pressed(self.BTN_CROSS):
            self.speed_scale = max(0.1, self.speed_scale - self.SPEED_STEP)
            self.get_logger().info(f'Speed scale: {self.speed_scale:.1f}')
        if pressed(self.BTN_TRIANGLE):
            self.speed_scale = min(1.0, self.speed_scale + self.SPEED_STEP)
            self.get_logger().info(f'Speed scale: {self.speed_scale:.1f}')

        self.prev_buttons = list(buttons)

        # Compute joint velocities
        j1 = self.apply_deadzone(axes[self.AXIS_LEFT_X])
        j2 = self.apply_deadzone(axes[self.AXIS_LEFT_Y])
        j3 = self.apply_deadzone(axes[self.AXIS_RIGHT_Y])
        j4 = self.apply_deadzone(axes[self.AXIS_RIGHT_X])

        # J5: L1 = negative, R1 = positive
        j5 = 0.0
        if buttons[self.BTN_L1]:
            j5 = -1.0
        elif buttons[self.BTN_R1]:
            j5 = 1.0

        velocities = [j1, j2, j3, j4, j5, 0.0]

        # Apply max speeds and scale
        jog_msg = Float64MultiArray()
        jog_msg.data = [
            v * self.max_speeds[i] * self.speed_scale
            for i, v in enumerate(velocities)
        ]

        self.jog_pub.publish(jog_msg)

    def go_to_zero(self):
        # Stop any jogging first
        stop_msg = Float64MultiArray()
        stop_msg.data = [0.0] * 6
        self.jog_pub.publish(stop_msg)

        if not self.trajectory_client.wait_for_server(timeout_sec=1.0):
            self.get_logger().warn('Trajectory action server not available')
            return

        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = self.joint_names
        point = JointTrajectoryPoint()
        point.positions = [0.0] * 6
        point.time_from_start = Duration(sec=5)
        goal.trajectory.points = [point]

        self.get_logger().info('Going to all zeros...')
        future = self.trajectory_client.send_goal_async(goal)
        future.add_done_callback(self.go_to_zero_response)

    def go_to_zero_response(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().error('Go-to-zero goal rejected')
            return
        self.get_logger().info('Go-to-zero goal accepted')
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.go_to_zero_done)

    def go_to_zero_done(self, future):
        result = future.result()
        if result.status == 4:  # SUCCEEDED
            self.get_logger().info('Go-to-zero complete')
        else:
            self.get_logger().warn(f'Go-to-zero finished with status {result.status}')

    def call_start(self):
        if not self.start_client.service_is_ready():
            self.get_logger().warn('/ar4_hardware/start service not available')
            return
        future = self.start_client.call_async(Trigger.Request())
        future.add_done_callback(self.start_done)
        self.get_logger().info('Calling /ar4_hardware/start...')

    def start_done(self, future):
        try:
            resp = future.result()
            if resp.success:
                self.get_logger().info(f'START OK: {resp.message}')
            else:
                self.get_logger().error(f'START failed: {resp.message}')
        except Exception as e:
            self.get_logger().error(f'START service call failed: {e}')


def main(args=None):
    rclpy.init(args=args)
    node = TeleopJoy()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
