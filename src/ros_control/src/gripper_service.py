#!/usr/bin/env python3
"""
Gripper Service Node

Provides simple open/close services for symmetric jaw gripper.
Configuration is loaded from ROS2 parameters.
"""

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger
from std_msgs.msg import Float64MultiArray


class GripperService(Node):
    """Service node for symmetric gripper open/close control"""

    def __init__(self):
        super().__init__('gripper_service')

        # Declare parameters with defaults
        self.declare_parameter('left_joint', 'selector_left_container_jaw_joint')
        self.declare_parameter('right_joint', 'selector_right_container_jaw_joint')
        self.declare_parameter('home_position', 0.0)
        self.declare_parameter('open_offset', 0.05)
        self.declare_parameter('controller_topic', '/gripper_controller/commands')

        # Get parameters
        self.left_joint = self.get_parameter('left_joint').value
        self.right_joint = self.get_parameter('right_joint').value
        self.home_position = self.get_parameter('home_position').value
        self.open_offset = self.get_parameter('open_offset').value
        controller_topic = self.get_parameter('controller_topic').value

        # Publisher to gripper controller
        self.cmd_publisher = self.create_publisher(
            Float64MultiArray,
            controller_topic,
            10
        )

        # Services
        self.open_service = self.create_service(
            Trigger,
            'gripper/open',
            self.open_callback
        )
        self.close_service = self.create_service(
            Trigger,
            'gripper/close',
            self.close_callback
        )

        # State tracking
        self.is_open = False

        self.get_logger().info(
            f'Gripper service started:\n'
            f'  - Joints: [{self.left_joint}, {self.right_joint}]\n'
            f'  - Home: {self.home_position}m, Open offset: {self.open_offset}m\n'
            f'  - Controller topic: {controller_topic}\n'
            f'  - Services: /gripper/open, /gripper/close'
        )

    def _publish_command(self, left_pos: float, right_pos: float) -> bool:
        """Publish position command to gripper controller.

        Args:
            left_pos: Position for left jaw
            right_pos: Position for right jaw (typically negative of left for symmetric)

        Returns:
            True if published successfully
        """
        try:
            msg = Float64MultiArray()
            msg.data = [left_pos, right_pos]
            self.cmd_publisher.publish(msg)
            return True
        except Exception as e:
            self.get_logger().error(f'Failed to publish command: {e}')
            return False

    def open_callback(self, request, response):
        """Handle gripper open request"""
        # Both jaws get SAME value - URDF axes are opposite so same value = opposite movement
        # Zero/negative = jaws apart (open), positive = jaws together (close)
        position = self.home_position

        if self._publish_command(position, position):
            self.is_open = True
            response.success = True
            response.message = f'Gripper opened'
            self.get_logger().info(f'Gripper opened: [{position}, {position}]')
        else:
            response.success = False
            response.message = 'Failed to publish open command'

        return response

    def close_callback(self, request, response):
        """Handle gripper close request"""
        # Positive values = jaws move together (close)
        position = self.home_position + self.open_offset

        if self._publish_command(position, position):
            self.is_open = False
            response.success = True
            response.message = f'Gripper closed by {self.open_offset}m'
            self.get_logger().info(f'Gripper closed: [{position}, {position}]')
        else:
            response.success = False
            response.message = 'Failed to publish close command'

        return response


def main(args=None):
    rclpy.init(args=args)

    node = GripperService()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
