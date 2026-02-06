#!/usr/bin/env python3
"""
GetContainer Action Server

Orchestrates container pick operations by coordinating gripper control
and manipulator movement.

Execution flow:
1. Open gripper
2. Move to container position
3. Close gripper
4. Lift container
"""

import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer, ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
import yaml
import time
from pathlib import Path
from typing import Dict, Optional
from ament_index_python.packages import get_package_share_directory

# Action messages
from ros_control.action import GetContainer, MoveJointGroup

# Service messages
from std_srvs.srv import Trigger


class GetContainerServer(Node):
    """Action server for container pick operations"""

    def __init__(self):
        super().__init__('get_container_server')

        # Use reentrant callback group for async operations
        self.callback_group = ReentrantCallbackGroup()

        # Load configuration
        self.config = self._load_config()
        self.get_logger().info('Configuration loaded')

        # Service clients for gripper
        self.gripper_open_client = self.create_client(
            Trigger,
            '/gripper/open',
            callback_group=self.callback_group
        )
        self.gripper_close_client = self.create_client(
            Trigger,
            '/gripper/close',
            callback_group=self.callback_group
        )

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
            GetContainer,
            'get_container',
            self.execute_callback,
            callback_group=self.callback_group
        )

        self.get_logger().info('GetContainer action server started')

    def _load_config(self) -> Dict:
        """Load configuration from YAML file"""
        try:
            pkg_share = get_package_share_directory('ros_control')
            config_path = Path(pkg_share) / 'config' / 'get_container_config.yaml'
        except Exception:
            # Fallback for development
            config_path = Path(__file__).parent.parent / 'config' / 'get_container_config.yaml'

        if not config_path.exists():
            self.get_logger().warn(f'Config file not found at {config_path}, using defaults')
            return self._default_config()

        with open(config_path, 'r') as f:
            yaml_data = yaml.safe_load(f)

        if not yaml_data:
            return self._default_config()

        # Extract config from various YAML structures
        config = None
        if 'get_container_server' in yaml_data:
            node_config = yaml_data['get_container_server']
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

        # Deep merge with defaults
        default = self._default_config()
        merged = self._deep_merge(default, config)
        return merged

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _default_config(self) -> Dict:
        """Return default configuration"""
        return {
            'container_position': {
                'base_main_frame_joint': 1.5,
                'main_frame_selector_frame_joint': 0.8
            },
            'lift_joint': 'selector_frame_picker_frame_joint',
            'lift_height': 0.20,
            'gripper_settle_time': 1.0,
            'timeouts': {
                'move_timeout': 30.0,
                'gripper_timeout': 5.0
            },
            'position_tolerance': 0.01
        }

    async def execute_callback(self, goal_handle):
        """Execute the GetContainer action"""
        self.get_logger().info('GetContainer action started')
        start_time = time.time()

        feedback = GetContainer.Feedback()

        try:
            # Step 1: Open gripper
            feedback.current_step = 'Opening gripper'
            feedback.progress_percentage = 0.0
            goal_handle.publish_feedback(feedback)

            success, message = await self._open_gripper()
            if not success:
                return self._create_result(goal_handle, False, f'Failed to open gripper: {message}', start_time)

            # Step 2: Move to container position
            feedback.current_step = 'Moving to container'
            feedback.progress_percentage = 25.0
            goal_handle.publish_feedback(feedback)

            success, message = await self._move_to_container()
            if not success:
                return self._create_result(goal_handle, False, f'Failed to move to container: {message}', start_time)

            # Step 3: Close gripper
            feedback.current_step = 'Closing gripper'
            feedback.progress_percentage = 50.0
            goal_handle.publish_feedback(feedback)

            success, message = await self._close_gripper()
            if not success:
                return self._create_result(goal_handle, False, f'Failed to close gripper: {message}', start_time)

            # Step 4: Lift container
            feedback.current_step = 'Lifting container'
            feedback.progress_percentage = 75.0
            goal_handle.publish_feedback(feedback)

            success, message = await self._lift_container()
            if not success:
                return self._create_result(goal_handle, False, f'Failed to lift container: {message}', start_time)

            # Success
            feedback.current_step = 'Complete'
            feedback.progress_percentage = 100.0
            goal_handle.publish_feedback(feedback)

            return self._create_result(goal_handle, True, 'Container picked successfully', start_time)

        except Exception as e:
            self.get_logger().error(f'Error during execution: {e}')
            return self._create_result(goal_handle, False, f'Execution error: {e}', start_time)

    async def _open_gripper(self) -> tuple[bool, str]:
        """Open the gripper"""
        timeout = self.config['timeouts']['gripper_timeout']

        if not self.gripper_open_client.wait_for_service(timeout_sec=timeout):
            return False, 'Gripper open service not available'

        request = Trigger.Request()
        future = self.gripper_open_client.call_async(request)

        try:
            response = await future
            if response.success:
                self.get_logger().info('Gripper opened successfully')
                return True, response.message
            else:
                return False, response.message
        except Exception as e:
            return False, str(e)

    async def _close_gripper(self) -> tuple[bool, str]:
        """Close the gripper and wait for it to settle"""
        timeout = self.config['timeouts']['gripper_timeout']

        if not self.gripper_close_client.wait_for_service(timeout_sec=timeout):
            return False, 'Gripper close service not available'

        request = Trigger.Request()
        future = self.gripper_close_client.call_async(request)

        try:
            response = await future
            if response.success:
                # Wait for gripper to physically close before returning
                settle_time = self.config.get('gripper_settle_time', 1.0)
                self.get_logger().info(f'Gripper command sent, waiting {settle_time}s for gripper to close...')
                time.sleep(settle_time)
                self.get_logger().info('Gripper closed successfully')
                return True, response.message
            else:
                return False, response.message
        except Exception as e:
            return False, str(e)

    async def _move_to_container(self) -> tuple[bool, str]:
        """Move manipulator to container position"""
        timeout = self.config['timeouts']['move_timeout']

        if not self.move_joint_group_client.wait_for_server(timeout_sec=timeout):
            return False, 'MoveJointGroup action server not available'

        # Build goal from config
        container_pos = self.config['container_position']
        joint_names = list(container_pos.keys())
        target_positions = [container_pos[j] for j in joint_names]

        goal = MoveJointGroup.Goal()
        goal.joint_names = joint_names
        goal.target_positions = target_positions
        goal.max_velocity = [0.5] * len(joint_names)  # Default velocity

        self.get_logger().info(f'Moving to container: {dict(zip(joint_names, target_positions))}')

        try:
            goal_handle = await self.move_joint_group_client.send_goal_async(goal)
            if not goal_handle.accepted:
                return False, 'Goal rejected by MoveJointGroup server'

            result = await goal_handle.get_result_async()
            if result.result.success:
                self.get_logger().info('Moved to container position')
                return True, result.result.message
            else:
                return False, result.result.message
        except Exception as e:
            return False, str(e)

    async def _lift_container(self) -> tuple[bool, str]:
        """Lift the container by moving the vertical joint (Z axis)"""
        timeout = self.config['timeouts']['move_timeout']

        if not self.move_joint_group_client.wait_for_server(timeout_sec=timeout):
            return False, 'MoveJointGroup action server not available'

        lift_height = self.config['lift_height']
        container_pos = self.config['container_position']

        # Use configurable lift joint
        joint_name = self.config.get('lift_joint', 'main_frame_selector_frame_joint')

        # Get current position from container_position and add lift_height
        current_pos = container_pos.get(joint_name, 0.0)
        lift_pos = current_pos + lift_height

        goal = MoveJointGroup.Goal()
        goal.joint_names = [joint_name]
        goal.target_positions = [lift_pos]
        goal.max_velocity = [0.3]  # Slower for lifting

        self.get_logger().info(f'Lifting container: {joint_name} -> {lift_pos}')

        try:
            goal_handle = await self.move_joint_group_client.send_goal_async(goal)
            if not goal_handle.accepted:
                return False, 'Lift goal rejected by MoveJointGroup server'

            result = await goal_handle.get_result_async()
            if result.result.success:
                self.get_logger().info('Container lifted successfully')
                return True, result.result.message
            else:
                return False, result.result.message
        except Exception as e:
            return False, str(e)

    def _create_result(self, goal_handle, success: bool, message: str, start_time: float):
        """Create and return result"""
        result = GetContainer.Result()
        result.success = success
        result.message = message
        result.execution_time = time.time() - start_time

        if success:
            goal_handle.succeed()
            self.get_logger().info(f'GetContainer succeeded: {message}')
        else:
            goal_handle.abort()
            self.get_logger().error(f'GetContainer failed: {message}')

        return result


def main(args=None):
    rclpy.init(args=args)

    node = GetContainerServer()

    # Use MultiThreadedExecutor for async callback support
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
