#!/usr/bin/env python3
"""
ReturnBox Action Server

Orchestrates returning a box to a cabinet cell by coordinating
platform navigation (NavigateToAddress) and SCARA arm manipulation (ScaraClient).

This is the reverse operation of ExtractBox — it pushes a box back into
the cabinet instead of pulling it out.

Execution flow:
1. Navigate to cell     → /navigate_to_address action  (0-40%)
2. Return with SCARA    → ScaraClient methods           (40-90%)
3. Verify & complete    → Sensor check + address         (90-100%)
"""

import math
import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer, ActionClient, GoalResponse, CancelResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
import yaml
import time
from pathlib import Path
from typing import Dict
import threading

from ament_index_python.packages import get_package_share_directory

import tf2_ros

from ros_control.action import ReturnBox, NavigateToAddress
from action_msgs.msg import GoalStatus

from scara_control.scara_client import ScaraClient


class ReturnBoxServer(Node):
    """Action server that orchestrates returning a box to a cabinet cell."""

    def __init__(self):
        super().__init__('return_box_server')

        self.callback_group = ReentrantCallbackGroup()

        # Load configuration
        self.config = self._load_config()
        self.get_logger().info('Configuration loaded')

        # TF2 listener for picker_frame transform lookup
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        # NavigateToAddress action client
        self.navigate_client = ActionClient(
            self,
            NavigateToAddress,
            '/navigate_to_address',
            callback_group=self.callback_group
        )

        # ScaraClient instance (attaches to this node, auto-loads config)
        self.scara = ScaraClient(self)

        # Track active navigation goal for cancellation
        self._active_nav_goal_handle = None
        self._current_phase = ''
        self._executing = False

        # Action server
        self.action_server = ActionServer(
            self,
            ReturnBox,
            'return_box',
            self.execute_callback,
            goal_callback=self._goal_callback,
            cancel_callback=self._cancel_callback,
            callback_group=self.callback_group
        )

        self.get_logger().info('ReturnBox action server started')

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def _load_config(self) -> Dict:
        """Load configuration from YAML file."""
        try:
            pkg_share = get_package_share_directory('ros_control')
            config_path = Path(pkg_share) / 'config' / 'return_box_config.yaml'
        except Exception:
            config_path = Path(__file__).parent.parent / 'config' / 'return_box_config.yaml'

        if not config_path.exists():
            self.get_logger().warn(f'Config file not found at {config_path}, using defaults')
            return self._default_config()

        with open(config_path, 'r') as f:
            yaml_data = yaml.safe_load(f)

        if not yaml_data:
            return self._default_config()

        config = None
        if 'return_box_server' in yaml_data:
            node_config = yaml_data['return_box_server']
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
            'hook_grasp': {
                'wrist_angle_rad': math.pi / 2,
                'z_offset_m': 0.03,
                'z_above_box_m': 0.10,
                'approach_depth_m': 0.20,
                'approach_x_offset_m': 0.20,
                'y_inside_m': 0.02,
                'retract_overshoot_m': 0.38,
                'z_lower_velocity': 0.05,
            },
            'motion': {
                'push_velocity': 0.05,
                'position_velocity': 0.5,
                'linear_step_size': 0.005,
                'return_home': True,
            },
            'timeouts': {
                'navigate_timeout': 60.0,
                'return_timeout': 30.0,
            },
            'sensor': {
                'mock': True,
            },
        }

    # ------------------------------------------------------------------
    # Goal / Cancel callbacks
    # ------------------------------------------------------------------

    def _goal_callback(self, goal_request):
        """Accept goal only if not already executing (single-goal policy)."""
        if self._executing:
            self.get_logger().warn('ReturnBox goal rejected — already executing')
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _cancel_callback(self, goal_handle):
        """Accept cancellation requests and forward to active sub-goals."""
        self.get_logger().info('Cancel requested for ReturnBox')
        if self._active_nav_goal_handle is not None:
            self.get_logger().info('Forwarding cancel to NavigateToAddress')
            self._active_nav_goal_handle.cancel_goal_async()
        return CancelResponse.ACCEPT

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    async def execute_callback(self, goal_handle):
        """Execute the ReturnBox action."""
        goal = goal_handle.request
        box = goal.box
        box_id = goal.box_id
        self.get_logger().info(
            f'ReturnBox: side={box.side}, cabinet={box.cabinet_num}, '
            f'row={box.row}, column={box.column}, box_id={box_id}'
        )

        start_time = time.time()
        feedback = ReturnBox.Feedback()
        self._executing = True

        try:
            # --- Phase 1: Navigate (0-40%) ---
            self._current_phase = 'navigating'
            feedback.current_phase = 'navigating'
            feedback.progress_percentage = 0.0
            goal_handle.publish_feedback(feedback)

            nav_success, nav_result = await self._navigate_to_cell(
                box, goal_handle, feedback
            )

            # Check for cancellation (may have been forwarded during navigation)
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                return self._create_canceled_result(start_time)

            if not nav_success:
                error_msg = nav_result if isinstance(nav_result, str) else nav_result.message
                return self._create_result(
                    goal_handle, False, False, '', start_time,
                    f'Navigation failed: {error_msg}'
                )

            # --- Phase 2: Return with SCARA (40-90%) ---
            acquired = await self.scara.acquire()
            if not acquired:
                return self._create_result(
                    goal_handle, False, False, '', start_time,
                    'SCARA arm is busy'
                )

            try:
                self._current_phase = 'returning'
                feedback.current_phase = 'returning'
                feedback.progress_percentage = 40.0
                goal_handle.publish_feedback(feedback)

                return_success, return_msg = await self._return_box(
                    box, nav_result, goal_handle, feedback
                )

                # Check for cancellation (may have been triggered during return)
                if goal_handle.is_cancel_requested:
                    goal_handle.canceled()
                    return self._create_canceled_result(start_time)

                if not return_success:
                    return self._create_result(
                        goal_handle, False, False, '', start_time,
                        f'Return failed: {return_msg}'
                    )
            finally:
                await self.scara.release()

            # --- Phase 3: Verify & Complete (90-100%) ---
            self._current_phase = 'done'
            feedback.current_phase = 'done'
            feedback.progress_percentage = 90.0
            goal_handle.publish_feedback(feedback)

            box_extracted = self._check_box_sensor()
            returned_to_address = (
                f'{box.side[0]}_{box.cabinet_num}_{box.row}_{box.column}'
            )

            feedback.progress_percentage = 100.0
            goal_handle.publish_feedback(feedback)

            if box_extracted:
                return self._create_result(
                    goal_handle, True, True, returned_to_address, start_time,
                    f'Box {box_id} returned to {returned_to_address} successfully'
                )
            else:
                return self._create_result(
                    goal_handle, True, False, returned_to_address, start_time,
                    'Box not detected by sensor in storage'
                )

        except Exception as e:
            self.get_logger().error(f'Error during execution: {e}')
            return self._create_result(
                goal_handle, False, False, '', start_time,
                f'Execution error: {e}'
            )
        finally:
            self._active_nav_goal_handle = None
            self._current_phase = ''
            self._executing = False

    # ------------------------------------------------------------------
    # Phase 1: Navigation
    # ------------------------------------------------------------------

    async def _navigate_to_cell(self, box, goal_handle, feedback):
        """Send NavigateToAddress goal and relay feedback.

        Returns:
            (True, NavigateToAddress.Result) on success
            (False, error_string_or_result) on failure
        """
        timeout = self.config['timeouts']['navigate_timeout']

        if not self.navigate_client.wait_for_server(timeout_sec=10.0):
            return False, 'NavigateToAddress action server not available'

        nav_goal = NavigateToAddress.Goal()
        nav_goal.side = box.side
        nav_goal.cabinet_num = box.cabinet_num
        nav_goal.row = box.row
        nav_goal.column = box.column

        self.get_logger().info(
            f'Sending NavigateToAddress goal: side={box.side}, '
            f'cabinet={box.cabinet_num}, row={box.row}, col={box.column}'
        )

        try:
            send_goal_future = await self.navigate_client.send_goal_async(
                nav_goal,
                feedback_callback=lambda fb: self._relay_nav_feedback(
                    fb, goal_handle, feedback
                )
            )

            if not send_goal_future.accepted:
                return False, 'Goal rejected by NavigateToAddress server'

            # Store for cancellation forwarding
            self._active_nav_goal_handle = send_goal_future

            # Set up timeout timer — cancels the nav goal if it exceeds deadline
            nav_timed_out = threading.Event()

            def _on_nav_timeout():
                nav_timed_out.set()
                self.get_logger().warn(
                    f'Navigation timed out after {timeout}s, canceling'
                )
                if self._active_nav_goal_handle is not None:
                    self._active_nav_goal_handle.cancel_goal_async()

            timeout_timer = threading.Timer(timeout, _on_nav_timeout)
            timeout_timer.daemon = True
            timeout_timer.start()

            try:
                result_future = await send_goal_future.get_result_async()
            finally:
                timeout_timer.cancel()

            self._active_nav_goal_handle = None

            if result_future.status == GoalStatus.STATUS_CANCELED:
                if nav_timed_out.is_set():
                    return False, f'Navigation timed out after {timeout}s'
                return False, 'Navigation was canceled'

            nav_result = result_future.result
            if nav_result.success:
                return True, nav_result
            else:
                return False, nav_result

        except Exception as e:
            self._active_nav_goal_handle = None
            return False, str(e)

    def _relay_nav_feedback(self, nav_feedback_msg, goal_handle, feedback):
        """Relay NavigateToAddress feedback mapped to 0-40% range."""
        nav_fb = nav_feedback_msg.feedback
        # NavigateToAddress progress is 0.0-1.0, map to 0-40%
        mapped_progress = nav_fb.progress * 40.0
        feedback.current_phase = 'navigating'
        feedback.progress_percentage = float(mapped_progress)
        goal_handle.publish_feedback(feedback)

    # ------------------------------------------------------------------
    # Phase 2: SCARA return (reverse of extraction)
    # ------------------------------------------------------------------

    async def _return_box(self, box, nav_result, goal_handle, feedback):
        """Execute 7-step SCARA return sequence (reverse of extraction).

        Returns:
            (True, message) on success
            (False, message) on failure
        """
        cfg_grasp = self.config['hook_grasp']
        cfg_motion = self.config['motion']
        return_timeout = self.config['timeouts']['return_timeout']
        return_start = time.time()

        def _check_abort():
            """Check if return should be aborted (cancellation or timeout)."""
            if goal_handle.is_cancel_requested:
                return True, 'Return canceled'
            if time.time() - return_start > return_timeout:
                return True, f'Return timed out after {return_timeout}s'
            return False, ''

        # Determine wrist angle based on side
        wrist_angle = cfg_grasp['wrist_angle_rad']
        if box.side == 'right':
            wrist_angle = -wrist_angle

        z_offset = cfg_grasp['z_offset_m']
        z_above_box = cfg_grasp['z_above_box_m']

        # --- 2a. Rotate wrist ---
        self.get_logger().info(f'Step 2a: Rotating wrist to {wrist_angle:.4f} rad')
        feedback.progress_percentage = 42.0
        goal_handle.publish_feedback(feedback)

        result = await self.scara.move_joints(wrist=wrist_angle)
        if not result.success:
            return False, f'Wrist rotation failed: {result.message}'

        abort, msg = _check_abort()
        if abort:
            return False, msg

        # --- 2b. Raise Z (above box — must clear entire box height) ---
        current_z = self.scara.get_z_position()
        target_z_up = current_z + z_above_box

        self.get_logger().info(f'Step 2b: Raising Z from {current_z:.4f} to {target_z_up:.4f}')
        feedback.progress_percentage = 48.0
        goal_handle.publish_feedback(feedback)

        result = await self.scara.move_z(target_z_up, velocity=cfg_grasp['z_lower_velocity'])
        if not result.success:
            return False, f'Z raise failed: {result.message}'

        abort, msg = _check_abort()
        if abort:
            return False, msg

        # --- 2c. Position (push-start — behind box, robot side) ---
        push_start_x, push_start_y = self._compute_push_start(box)

        self.get_logger().info(
            f'Step 2c: Positioning to push-start ({push_start_x:.4f}, {push_start_y:.4f})'
        )
        feedback.progress_percentage = 55.0
        goal_handle.publish_feedback(feedback)

        result = await self.scara.move_to_point(
            x=push_start_x, y=push_start_y,
            velocity=cfg_motion['position_velocity']
        )
        if not result.success:
            return False, f'Position failed: {result.message}'

        abort, msg = _check_abort()
        if abort:
            return False, msg

        # --- 2d. Lower Z (hook engages handle plate) ---
        current_z = self.scara.get_z_position()
        target_z_down = current_z - z_above_box

        self.get_logger().info(f'Step 2d: Lowering Z from {current_z:.4f} to {target_z_down:.4f}')
        feedback.progress_percentage = 62.0
        goal_handle.publish_feedback(feedback)

        result = await self.scara.move_z(target_z_down, velocity=cfg_grasp['z_lower_velocity'])
        if not result.success:
            return False, f'Z lower failed: {result.message}'

        abort, msg = _check_abort()
        if abort:
            return False, msg

        # --- 2e. Push linear (push box into cabinet, with elbow flip) ---
        push_target_x, push_target_y = self._compute_push_target(box)

        self.get_logger().info(
            f'Step 2e: Pushing linearly from ({push_start_x:.4f}, {push_start_y:.4f}) '
            f'to ({push_target_x:.4f}, {push_target_y:.4f})'
        )
        feedback.progress_percentage = 72.0
        goal_handle.publish_feedback(feedback)

        async def _raise_z_before_flip():
            self.get_logger().info(
                f'Step 2e: Raising Z +{z_above_box}m before elbow flip'
            )
            await self.scara.move_z(
                self.scara.get_z_position() + z_above_box,
                velocity=cfg_grasp['z_lower_velocity'],
            )

        async def _lower_z_after_flip():
            self.get_logger().info(
                f'Step 2e: Lowering Z -{z_above_box}m after elbow flip'
            )
            await self.scara.move_z(
                self.scara.get_z_position() - z_above_box,
                velocity=cfg_grasp['z_lower_velocity'],
            )

        result = await self.scara.move_linear(
            x=push_target_x, y=push_target_y,
            velocity=cfg_motion['push_velocity'],
            step_size=cfg_motion['linear_step_size'],
            allow_elbow_flip=True,
            on_before_flip=_raise_z_before_flip,
            on_after_flip=_lower_z_after_flip,
        )
        if not result.success:
            return False, f'Push failed: {result.message}'

        abort, msg = _check_abort()
        if abort:
            return False, msg

        # --- 2f. Raise Z (disengage hook above handle plate) ---
        current_z = self.scara.get_z_position()
        target_z_disengage = current_z + z_offset

        self.get_logger().info(
            f'Step 2f: Raising Z from {current_z:.4f} to {target_z_disengage:.4f} '
            f'(disengage hook)'
        )
        feedback.progress_percentage = 80.0
        goal_handle.publish_feedback(feedback)

        result = await self.scara.move_z(
            target_z_disengage, velocity=cfg_grasp['z_lower_velocity']
        )
        if not result.success:
            return False, f'Z raise (disengage) failed: {result.message}'

        abort, msg = _check_abort()
        if abort:
            return False, msg

        # --- 2g. Home (optional) ---
        # Move arm joints home first (Z stays raised so hook clears plate
        # during joint motion), then lower Z.
        if cfg_motion['return_home']:
            self.get_logger().info('Step 2g: Moving arm to home (Z stays raised)')
            feedback.progress_percentage = 85.0
            goal_handle.publish_feedback(feedback)

            result = await self.scara.move_joints(
                shoulder=0.0, elbow=0.0, wrist=0.0,
            )
            if not result.success:
                return False, f'Arm home failed: {result.message}'

            self.get_logger().info('Step 2g: Lowering Z to home')
            result = await self.scara.move_z(0.0, velocity=0.1)
            if not result.success:
                return False, f'Z home failed: {result.message}'

        feedback.progress_percentage = 90.0
        goal_handle.publish_feedback(feedback)

        return True, 'Return sequence completed'

    def _compute_push_start(self, box):
        """Compute push start position (behind box, robot side).

        This is where the extract ended — the overshoot position.
        """
        cfg_grasp = self.config['hook_grasp']
        x_offset = cfg_grasp['approach_x_offset_m']
        overshoot = cfg_grasp['retract_overshoot_m']

        push_start_x = x_offset
        if box.side == 'left':
            push_start_y = -overshoot
        else:
            push_start_y = overshoot

        self.get_logger().info(
            f'Push start in SCARA frame: ({push_start_x:.4f}, {push_start_y:.4f}), '
            f'overshoot={overshoot:.4f}, x_offset={x_offset:.4f}, side={box.side}'
        )

        return push_start_x, push_start_y

    def _compute_push_target(self, box):
        """Compute push target position (inside cabinet).

        Push goes from overshoot (robot side) to depth + y_inside (cabinet side).
        """
        cfg_grasp = self.config['hook_grasp']
        x_offset = cfg_grasp['approach_x_offset_m']
        depth = cfg_grasp['approach_depth_m'] + cfg_grasp['y_inside_m']

        push_target_x = x_offset
        if box.side == 'left':
            push_target_y = depth
        else:
            push_target_y = -depth

        self.get_logger().info(
            f'Push target in SCARA frame: ({push_target_x:.4f}, {push_target_y:.4f}), '
            f'depth={depth:.4f}, x_offset={x_offset:.4f}, side={box.side}'
        )

        return push_target_x, push_target_y

    # ------------------------------------------------------------------
    # Phase 3: Sensor check
    # ------------------------------------------------------------------

    def _check_box_sensor(self) -> bool:
        """Check box return sensor."""
        if self.config['sensor']['mock']:
            return True
        # Future: read from sensor topic/service
        return False

    # ------------------------------------------------------------------
    # Result / cancellation helpers
    # ------------------------------------------------------------------

    def _create_result(self, goal_handle, success, box_extracted,
                       returned_to_address, start_time, message):
        """Create and return action result."""
        result = ReturnBox.Result()
        result.success = success
        result.box_extracted = box_extracted
        result.returned_to_address = returned_to_address
        result.execution_time = time.time() - start_time
        result.message = message

        if success:
            goal_handle.succeed()
            self.get_logger().info(f'ReturnBox succeeded: {message}')
        else:
            goal_handle.abort()
            self.get_logger().error(f'ReturnBox failed: {message}')

        return result

    def _create_canceled_result(self, start_time):
        """Create result for canceled goal."""
        result = ReturnBox.Result()
        result.success = False
        result.box_extracted = False
        result.returned_to_address = ''
        result.execution_time = time.time() - start_time
        result.message = 'Goal canceled'
        return result


def main(args=None):
    rclpy.init(args=args)

    node = ReturnBoxServer()

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
