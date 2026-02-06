#!/usr/bin/env python3
"""
PlaceContainer Action Server

Orchestrates container place operations by coordinating manipulator
movement and gripper control — the reverse of GetContainer.

Execution flow:
1. Move to place position
2. Open gripper (release container)
3. Retract (lower selector to clear container)
"""

import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer, ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
import yaml
import time
from pathlib import Path
from typing import Dict
from ament_index_python.packages import get_package_share_directory

# Action messages
from ros_control.action import PlaceContainer, MoveJointGroup

# Service messages
from std_srvs.srv import Trigger


class PlaceContainerServer(Node):
    """Action server for container place operations"""

    def __init__(self):
        super().__init__('place_container_server')

        # Use reentrant callback group for async operations
        self.callback_group = ReentrantCallbackGroup()

        # Load configuration
        self.config = self._load_config()
        self.get_logger().info('Configuration loaded')

        # Service client for gripper
        self.gripper_open_client = self.create_client(
            Trigger,
            '/gripper/open',
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
            PlaceContainer,
            'place_container',
            self.execute_callback,
            callback_group=self.callback_group
        )

        self.get_logger().info('PlaceContainer action server started')

    def _load_config(self) -> Dict:
        """Load configuration from YAML file"""
        try:
            pkg_share = get_package_share_directory('ros_control')
            config_path = Path(pkg_share) / 'config' / 'place_container_config.yaml'
        except Exception:
            # Fallback for development
            config_path = Path(__file__).parent.parent / 'config' / 'place_container_config.yaml'

        if not config_path.exists():
            self.get_logger().warn(f'Config file not found at {config_path}, using defaults')
            return self._default_config()

        with open(config_path, 'r') as f:
            yaml_data = yaml.safe_load(f)

        if not yaml_data:
            return self._default_config()

        # Extract config from various YAML structures
        config = None
        if 'place_container_server' in yaml_data:
            node_config = yaml_data['place_container_server']
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
            'place_position': {
                'base_main_frame_joint': 1.5,
                'main_frame_selector_frame_joint': 0.2
            },
            'retract_joint': 'main_frame_selector_frame_joint',
            'retract_distance': 0.10,
            'gripper_settle_time': 1.0,
            'timeouts': {
                'move_timeout': 30.0,
                'gripper_timeout': 5.0
            },
            'position_tolerance': 0.01
        }

    async def execute_callback(self, goal_handle):
        """Execute the PlaceContainer action"""
        self.get_logger().info('PlaceContainer action started')
        start_time = time.time()

        feedback = PlaceContainer.Feedback()

        try:
            # Step 1: Move to place position
            feedback.current_step = 'Moving to place position'
            feedback.progress_percentage = 0.0
            goal_handle.publish_feedback(feedback)

            success, message = await self._move_to_place()
            if not success:
                return self._create_result(goal_handle, False, f'Failed to move to place position: {message}', start_time)

            # Step 2: Open gripper (release container)
            feedback.current_step = 'Opening gripper'
            feedback.progress_percentage = 33.0
            goal_handle.publish_feedback(feedback)

            success, message = await self._open_gripper()
            if not success:
                return self._create_result(goal_handle, False, f'Failed to open gripper: {message}', start_time)

            # Step 3: Retract (lower selector to clear container)
            feedback.current_step = 'Retracting'
            feedback.progress_percentage = 66.0
            goal_handle.publish_feedback(feedback)

            success, message = await self._retract()
            if not success:
                return self._create_result(goal_handle, False, f'Failed to retract: {message}', start_time)

            # Success
            feedback.current_step = 'Complete'
            feedback.progress_percentage = 100.0
            goal_handle.publish_feedback(feedback)

            return self._create_result(goal_handle, True, 'Container placed successfully', start_time)

        except Exception as e:
            self.get_logger().error(f'Error during execution: {e}')
            return self._create_result(goal_handle, False, f'Execution error: {e}', start_time)

    async def _move_to_place(self) -> tuple[bool, str]:
        """Move manipulator to place position"""
        timeout = self.config['timeouts']['move_timeout']

        if not self.move_joint_group_client.wait_for_server(timeout_sec=timeout):
            return False, 'MoveJointGroup action server not available'

        # Build goal from config
        place_pos = self.config['place_position']
        joint_names = list(place_pos.keys())
        target_positions = [place_pos[j] for j in joint_names]

        goal = MoveJointGroup.Goal()
        goal.joint_names = joint_names
        goal.target_positions = target_positions
        goal.max_velocity = [0.5] * len(joint_names)

        self.get_logger().info(f'Moving to place position: {dict(zip(joint_names, target_positions))}')

        try:
            goal_handle = await self.move_joint_group_client.send_goal_async(goal)
            if not goal_handle.accepted:
                return False, 'Goal rejected by MoveJointGroup server'

            result = await goal_handle.get_result_async()
            if result.result.success:
                self.get_logger().info('Moved to place position')
                return True, result.result.message
            else:
                return False, result.result.message
        except Exception as e:
            return False, str(e)

    async def _open_gripper(self) -> tuple[bool, str]:
        """Open the gripper to release the container"""
        timeout = self.config['timeouts']['gripper_timeout']

        if not self.gripper_open_client.wait_for_service(timeout_sec=timeout):
            return False, 'Gripper open service not available'

        request = Trigger.Request()
        future = self.gripper_open_client.call_async(request)

        try:
            response = await future
            if response.success:
                # Wait for gripper to physically open before returning
                settle_time = self.config.get('gripper_settle_time', 1.0)
                self.get_logger().info(f'Gripper command sent, waiting {settle_time}s for gripper to open...')
                time.sleep(settle_time)
                self.get_logger().info('Gripper opened successfully')
                return True, response.message
            else:
                return False, response.message
        except Exception as e:
            return False, str(e)

    async def _retract(self) -> tuple[bool, str]:
        """Lower the selector to clear the container after release"""
        timeout = self.config['timeouts']['move_timeout']

        if not self.move_joint_group_client.wait_for_server(timeout_sec=timeout):
            return False, 'MoveJointGroup action server not available'

        retract_distance = self.config['retract_distance']
        place_pos = self.config['place_position']

        joint_name = self.config.get('retract_joint', 'main_frame_selector_frame_joint')

        # Get place position and subtract retract_distance (lower the selector)
        current_pos = place_pos.get(joint_name, 0.0)
        retract_pos = current_pos - retract_distance

        goal = MoveJointGroup.Goal()
        goal.joint_names = [joint_name]
        goal.target_positions = [retract_pos]
        goal.max_velocity = [0.3]  # Slower for retraction

        self.get_logger().info(f'Retracting: {joint_name} -> {retract_pos}')

        try:
            goal_handle = await self.move_joint_group_client.send_goal_async(goal)
            if not goal_handle.accepted:
                return False, 'Retract goal rejected by MoveJointGroup server'

            result = await goal_handle.get_result_async()
            if result.result.success:
                self.get_logger().info('Retracted successfully')
                return True, result.result.message
            else:
                return False, result.result.message
        except Exception as e:
            return False, str(e)

    def _create_result(self, goal_handle, success: bool, message: str, start_time: float):
        """Create and return result"""
        result = PlaceContainer.Result()
        result.success = success
        result.message = message
        result.execution_time = time.time() - start_time

        if success:
            goal_handle.succeed()
            self.get_logger().info(f'PlaceContainer succeeded: {message}')
        else:
            goal_handle.abort()
            self.get_logger().error(f'PlaceContainer failed: {message}')

        return result


def main(args=None):
    rclpy.init(args=args)

    node = PlaceContainerServer()

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
