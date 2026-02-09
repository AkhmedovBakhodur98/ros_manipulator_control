#!/usr/bin/env python3
"""
NavigateToAddress Action Server

Translates a logical cabinet address (side, cabinet, row, column) into
physical joint positions and moves the manipulator platform.

Controls only platform joints:
  - base_main_frame_joint (X axis, rail)
  - main_frame_selector_frame_joint (Z axis, vertical lift)

Position formulas:
  X = first_cabinet_x + cabinet_num * cabinet_spacing + column * column_width + offsets.x
  Z = first_row_z + row * row_height + offsets.z
"""

import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer, ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
import yaml
import time
from pathlib import Path
from typing import Dict, Tuple
from ament_index_python.packages import get_package_share_directory

from ros_control.action import NavigateToAddress, MoveJointGroup
from geometry_msgs.msg import Point


class NavigateToAddressServer(Node):
    """Action server that navigates manipulator platform to a cabinet address."""

    def __init__(self):
        super().__init__('navigate_to_address_server')

        self.callback_group = ReentrantCallbackGroup()

        # Load configuration
        self.config = self._load_config()
        self.get_logger().info('Configuration loaded')

        # Action client for move_joint_group
        self.move_joint_group_client = ActionClient(
            self,
            MoveJointGroup,
            '/move_joint_group',
            callback_group=self.callback_group
        )

        # Action server
        self.action_server = ActionServer(
            self,
            NavigateToAddress,
            'navigate_to_address',
            self.execute_callback,
            callback_group=self.callback_group
        )

        self.get_logger().info('NavigateToAddress action server started')

    def _load_config(self) -> Dict:
        """Load configuration from YAML file."""
        try:
            pkg_share = get_package_share_directory('ros_control')
            config_path = Path(pkg_share) / 'config' / 'navigate_to_address_config.yaml'
        except Exception:
            config_path = Path(__file__).parent.parent / 'config' / 'navigate_to_address_config.yaml'

        if not config_path.exists():
            self.get_logger().warn(f'Config file not found at {config_path}, using defaults')
            return self._default_config()

        with open(config_path, 'r') as f:
            yaml_data = yaml.safe_load(f)

        if not yaml_data:
            return self._default_config()

        config = None
        if 'navigate_to_address_server' in yaml_data:
            node_config = yaml_data['navigate_to_address_server']
            if isinstance(node_config, dict) and 'ros__parameters' in node_config:
                config = node_config['ros__parameters']
            elif isinstance(node_config, dict):
                config = node_config
        elif 'ros__parameters' in yaml_data:
            config = yaml_data['ros__parameters']
        else:
            config = yaml_data

        if not config:
            config = {}

        default = self._default_config()
        merged = self._deep_merge(default, config)
        return merged

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _default_config(self) -> Dict:
        """Return default configuration."""
        return {
            'cabinets': {
                'num_cabinets': 5,
                'rows_per_cabinet': 4,
                'columns_per_row': 2,
            },
            'rail': {
                'first_cabinet_x': 0.2,
                'cabinet_spacing': 0.75,
                'column_width': 0.35,
            },
            'lift': {
                'first_row_z': 0.1,
                'row_height': 0.30,
            },
            'offsets': {
                'x': 0.0,
                'z': 0.0,
            },
            'movement': {
                'max_velocity_x': 1.0,
                'max_velocity_z': 0.8,
            },
            'joint_limits': {
                'x_min': 0.0,
                'x_max': 4.0,
                'z_min': -0.01,
                'z_max': 1.5,
            },
            'position_tolerance': 0.005,
            'timeouts': {
                'move_timeout': 30.0,
            },
        }

    def _validate_address(self, goal) -> Tuple[bool, str]:
        """Validate the input address against configured bounds."""
        cfg = self.config['cabinets']

        if goal.side not in ('left', 'right'):
            return False, f"Invalid side: '{goal.side}'. Expected 'left' or 'right'"

        if goal.cabinet_num >= cfg['num_cabinets']:
            return False, f"cabinet_num {goal.cabinet_num} out of range [0, {cfg['num_cabinets']})"

        if goal.row >= cfg['rows_per_cabinet']:
            return False, f"row {goal.row} out of range [0, {cfg['rows_per_cabinet']})"

        if goal.column >= cfg['columns_per_row']:
            return False, f"column {goal.column} out of range [0, {cfg['columns_per_row']})"

        return True, ''

    def _compute_position(self, goal) -> Tuple[float, float]:
        """Compute target (X, Z) from address using cabinet geometry."""
        cfg = self.config
        x = (cfg['rail']['first_cabinet_x']
             + goal.cabinet_num * cfg['rail']['cabinet_spacing']
             + goal.column * cfg['rail']['column_width']
             + cfg['offsets']['x'])
        z = (cfg['lift']['first_row_z']
             + goal.row * cfg['lift']['row_height']
             + cfg['offsets']['z'])
        return x, z

    def _validate_joint_limits(self, x: float, z: float) -> Tuple[bool, str]:
        """Validate computed positions against URDF joint limits."""
        limits = self.config['joint_limits']

        if not (limits['x_min'] <= x <= limits['x_max']):
            return False, (f"Computed X={x:.4f} outside joint limits "
                           f"[{limits['x_min']}, {limits['x_max']}]")

        if not (limits['z_min'] <= z <= limits['z_max']):
            return False, (f"Computed Z={z:.4f} outside joint limits "
                           f"[{limits['z_min']}, {limits['z_max']}]")

        return True, ''

    async def execute_callback(self, goal_handle):
        """Execute the NavigateToAddress action."""
        goal = goal_handle.request
        self.get_logger().info(
            f'NavigateToAddress: side={goal.side}, cabinet={goal.cabinet_num}, '
            f'row={goal.row}, column={goal.column}'
        )

        feedback = NavigateToAddress.Feedback()

        try:
            # Step 1: Validate input
            feedback.current_phase = 'validating'
            feedback.progress = 0.0
            goal_handle.publish_feedback(feedback)

            valid, msg = self._validate_address(goal)
            if not valid:
                self.get_logger().error(f'Validation failed: {msg}')
                return self._create_result(goal_handle, False, msg)

            # Step 2: Compute target position
            feedback.current_phase = 'computing'
            feedback.progress = 0.05
            goal_handle.publish_feedback(feedback)

            x, z = self._compute_position(goal)
            self.get_logger().info(f'Computed position: X={x:.4f}, Z={z:.4f}')

            # Step 3: Validate joint limits
            valid, msg = self._validate_joint_limits(x, z)
            if not valid:
                self.get_logger().error(f'Joint limits check failed: {msg}')
                return self._create_result(goal_handle, False, msg)

            # Step 4: Move platform via MoveJointGroup
            feedback.current_phase = 'moving'
            feedback.progress = 0.1
            goal_handle.publish_feedback(feedback)

            move_success, move_result = await self._move_platform(x, z, goal_handle, feedback)

            if not move_success:
                error_msg = move_result if isinstance(move_result, str) else move_result.message
                return self._create_result(goal_handle, False, error_msg)

            # Step 5: Relay result
            feedback.current_phase = 'done'
            feedback.progress = 1.0
            goal_handle.publish_feedback(feedback)

            result = NavigateToAddress.Result()
            result.success = move_result.success
            result.position_error = move_result.position_error
            result.message = move_result.message
            result.final_position = Point()
            result.final_position.x = move_result.final_position[0]
            result.final_position.y = 0.0
            result.final_position.z = move_result.final_position[1]

            goal_handle.succeed()
            self.get_logger().info(
                f'NavigateToAddress succeeded: X={result.final_position.x:.4f}, '
                f'Z={result.final_position.z:.4f}, error={result.position_error:.4f}'
            )
            return result

        except Exception as e:
            self.get_logger().error(f'Error during execution: {e}')
            return self._create_result(goal_handle, False, f'Execution error: {e}')

    async def _move_platform(self, x: float, z: float, goal_handle, feedback):
        """Move platform joints via /move_joint_group action.

        Returns:
            (True, MoveJointGroup.Result) on success
            (False, error_string_or_result) on failure
        """
        timeout = self.config['timeouts']['move_timeout']
        cfg = self.config['movement']

        if not self.move_joint_group_client.wait_for_server(timeout_sec=timeout):
            return False, 'MoveJointGroup action server not available'

        move_goal = MoveJointGroup.Goal()
        move_goal.joint_names = [
            'base_main_frame_joint',
            'main_frame_selector_frame_joint'
        ]
        move_goal.target_positions = [x, z]
        move_goal.max_velocity = [
            cfg['max_velocity_x'],
            cfg['max_velocity_z']
        ]

        self.get_logger().info(
            f'Sending MoveJointGroup goal: joints={move_goal.joint_names}, '
            f'positions=[{x:.4f}, {z:.4f}]'
        )

        try:
            send_goal_future = await self.move_joint_group_client.send_goal_async(
                move_goal,
                feedback_callback=lambda fb: self._relay_move_feedback(fb, goal_handle, feedback)
            )

            if not send_goal_future.accepted:
                return False, 'Goal rejected by MoveJointGroup server'

            result_future = await send_goal_future.get_result_async()
            move_result = result_future.result

            if move_result.success:
                return True, move_result
            else:
                return False, move_result

        except Exception as e:
            return False, str(e)

    def _relay_move_feedback(self, move_feedback_msg, goal_handle, feedback):
        """Relay MoveJointGroup feedback as NavigateToAddress feedback."""
        move_fb = move_feedback_msg.feedback
        # Map MoveJointGroup progress (0-100) to NavigateToAddress progress (0.1-0.95)
        normalized = move_fb.progress_percentage / 100.0
        feedback.progress = 0.1 + normalized * 0.85
        feedback.current_phase = 'moving'
        goal_handle.publish_feedback(feedback)

    def _create_result(self, goal_handle, success: bool, message: str):
        """Create and return a failure result."""
        result = NavigateToAddress.Result()
        result.success = success
        result.message = message
        result.position_error = 0.0
        result.final_position = Point()

        goal_handle.abort()
        self.get_logger().error(f'NavigateToAddress failed: {message}')

        return result


def main(args=None):
    rclpy.init(args=args)

    node = NavigateToAddressServer()

    executor = MultiThreadedExecutor()
    executor.add_node(node)

    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
