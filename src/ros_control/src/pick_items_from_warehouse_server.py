#!/usr/bin/env python3
"""
PickItemsFromWarehouse Action Server

Orchestrates the full pick workflow: extracts a box from the shelf,
picks medicines from it, and places them into a shipping container.

Execution flow:
1. Validate goal          (0-5%)
2. Extract box            (5-40%)   → /extract_box action
3. Per-item pick & place  (40-90%)
4. Return home & finalize (90-100%)
"""

import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer, ActionClient, GoalResponse, CancelResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
import yaml
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple, List

from ament_index_python.packages import get_package_share_directory

from ros_control.action import PickItemsFromWarehouse, ExtractBox
from ros_control.msg import Medicament, Address
from action_msgs.msg import GoalStatus

from scara_control.scara_client import ScaraClient


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------

@dataclass
class MedicamentProfile:
    length: float    # Longest horizontal dimension (meters)
    width: float     # Shortest horizontal dimension (meters)
    height: float    # Vertical dimension (meters)


@dataclass
class GraspPose:
    x: float         # Grasp X in world frame (meters)
    y: float         # Grasp Y in world frame (meters)
    z: float         # Grasp Z in world frame (meters)
    yaw: float       # Yaw rotation (radians)


@dataclass
class BoxDetection:
    grasp_pose: GraspPose
    box_center_x: float
    box_center_y: float
    box_center_z: float
    medicament: MedicamentProfile
    confidence: float          # 0.0-1.0
    approach_height: float     # Adaptive approach height (meters)
    is_valid: bool


@dataclass
class ContainerDropPoint:
    x: float         # Drop X in world frame (meters)
    y: float         # Drop Y in world frame (meters)
    z: float         # Drop Z in world frame (meters)


# ------------------------------------------------------------------
# Vision provider interface
# ------------------------------------------------------------------

class VisionProvider(ABC):
    """Abstract interface for vision data. Matches future /FindBox and /ContSide services."""

    @abstractmethod
    def find_box(self, medicament: Medicament, box: Address) -> Tuple[bool, Optional[BoxDetection]]:
        """Locate a medicine in the extracted box.
        Returns (success, detection_result)."""
        ...

    @abstractmethod
    def container_side(self, item_index: int) -> Tuple[bool, Optional[ContainerDropPoint]]:
        """Find optimal drop coordinates in the shipping container.
        Returns (success, drop_point)."""
        ...


class MockVisionProvider(VisionProvider):
    """Mock vision that returns configurable positions.
    Calculates grasp pose from box address + row offsets.
    Calculates drop point from fixed container position + item index offset."""

    def __init__(self, config: Dict):
        self.config = config

    def find_box(self, medicament: Medicament, box: Address) -> Tuple[bool, Optional[BoxDetection]]:
        grasp_x = medicament.box_center.x + self.config['grasp_offset_x']
        grasp_y = (medicament.box_center.y
                   + self.config['grasp_offset_y']
                   + medicament.row_id * self.config['row_spacing_y'])
        grasp_z = self.config['grasp_z']

        detection = BoxDetection(
            grasp_pose=GraspPose(x=grasp_x, y=grasp_y, z=grasp_z, yaw=0.0),
            box_center_x=medicament.box_center.x,
            box_center_y=medicament.box_center.y,
            box_center_z=medicament.box_center.z,
            medicament=MedicamentProfile(
                length=self.config['default_box_length'],
                width=self.config['default_box_width'],
                height=self.config['default_box_height'],
            ),
            confidence=1.0,
            approach_height=grasp_z + 0.05,
            is_valid=True,
        )
        return True, detection

    def container_side(self, item_index: int) -> Tuple[bool, Optional[ContainerDropPoint]]:
        drop = ContainerDropPoint(
            x=self.config['place_x'] + item_index * self.config['item_spacing_x'],
            y=self.config['place_y'],
            z=self.config['place_z'],
        )
        return True, drop


# ------------------------------------------------------------------
# Action server
# ------------------------------------------------------------------

class PickItemsFromWarehouseServer(Node):
    """Action server that orchestrates picking medicines from a box
    and placing them into a shipping container."""

    def __init__(self):
        super().__init__('pick_items_from_warehouse_server')

        self.callback_group = ReentrantCallbackGroup()

        # Load configuration
        self.config = self._load_config()
        self.get_logger().info('Configuration loaded')

        # ExtractBox action client
        self.extract_box_client = ActionClient(
            self,
            ExtractBox,
            'extract_box',
            callback_group=self.callback_group,
        )
        self._active_extract_goal_handle = None
        self._executing = False

        # ScaraClient instance (attaches to this node, auto-loads config)
        self.scara = ScaraClient(self)

        # Vision provider
        if self.config['mock'].get('enabled', True):
            self.vision = MockVisionProvider(self.config['mock'])
            self.get_logger().info('Using MockVisionProvider')
        else:
            raise RuntimeError(
                'RealVisionProvider is not yet implemented. '
                'Set mock.enabled: true in config.'
            )

        # Action server
        self.action_server = ActionServer(
            self,
            PickItemsFromWarehouse,
            'PickItems',
            self.execute_callback,
            goal_callback=self._goal_callback,
            cancel_callback=self._cancel_callback,
            callback_group=self.callback_group,
        )

        self.get_logger().info('PickItemsFromWarehouse action server started')

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def _load_config(self) -> Dict:
        """Load configuration from YAML file."""
        try:
            pkg_share = get_package_share_directory('ros_control')
            config_path = Path(pkg_share) / 'config' / 'pick_items_from_warehouse_config.yaml'
        except Exception:
            config_path = Path(__file__).parent.parent / 'config' / 'pick_items_from_warehouse_config.yaml'

        if not config_path.exists():
            self.get_logger().warn(f'Config file not found at {config_path}, using defaults')
            return self._default_config()

        with open(config_path, 'r') as f:
            yaml_data = yaml.safe_load(f)

        if not yaml_data:
            return self._default_config()

        config = None
        if 'pick_items_from_warehouse_server' in yaml_data:
            node_config = yaml_data['pick_items_from_warehouse_server']
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
            'pick_heights': {
                'safe_z': 0.25,
                'approach_offset_z': 0.05,
                'grasp_offset_z': 0.005,
                'place_offset_z': 0.02,
            },
            'motion': {
                'approach_velocity': 0.3,
                'pick_velocity': 0.1,
                'transit_velocity': 0.5,
                'place_velocity': 0.2,
                'z_velocity': 0.1,
            },
            'tool': {
                'settle_time_after_grasp': 0.5,
                'settle_time_after_release': 0.3,
            },
            'timeouts': {
                'per_item_timeout': 60.0,
                'total_timeout': 300.0,
            },
            'behavior': {
                'continue_on_item_failure': True,
                'return_home_after_all': True,
                'max_detection_retries': 2,
            },
            'mock': {
                'enabled': True,
                'grasp_offset_x': 0.15,
                'grasp_offset_y': 0.0,
                'grasp_z': 0.10,
                'row_spacing_y': 0.05,
                'place_x': 0.20,
                'place_y': -0.15,
                'place_z': 0.10,
                'item_spacing_x': 0.06,
                'default_box_length': 0.10,
                'default_box_width': 0.04,
                'default_box_height': 0.03,
            },
        }

    # ------------------------------------------------------------------
    # Goal / Cancel callbacks
    # ------------------------------------------------------------------

    def _goal_callback(self, goal_request):
        """Accept goal only if not already executing (single-goal policy)."""
        if self._executing:
            self.get_logger().warn('PickItems goal rejected — already executing')
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _cancel_callback(self, goal_handle):
        """Accept cancellation requests and forward to active sub-goals."""
        self.get_logger().info('Cancel requested for PickItemsFromWarehouse')
        if self._active_extract_goal_handle is not None:
            self.get_logger().info('Forwarding cancel to ExtractBox')
            self._active_extract_goal_handle.cancel_goal_async()
        return CancelResponse.ACCEPT

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    async def execute_callback(self, goal_handle):
        """Execute the PickItemsFromWarehouse action."""
        goal = goal_handle.request
        detection = goal.detection
        box = goal.box
        total_items = len(detection)

        self.get_logger().info(
            f'PickItems: {total_items} items from box '
            f'side={box.side}, cabinet={box.cabinet_num}, '
            f'row={box.row}, column={box.column}'
        )

        start_time = time.time()
        feedback = PickItemsFromWarehouse.Feedback()
        medicine_qr: List[str] = []
        items_picked = 0
        self._executing = True

        try:
            # --- Phase 1: Validate (0-5%) ---
            feedback.current_phase = 'initializing'
            feedback.current_item_index = 0
            feedback.total_items = total_items
            feedback.progress_percentage = 0.0
            feedback.message = 'Validating goal'
            goal_handle.publish_feedback(feedback)

            if total_items == 0:
                return self._create_result(
                    goal_handle, False, medicine_qr, 0, 0, start_time,
                    'No items in detection list'
                )

            feedback.progress_percentage = 5.0
            feedback.message = 'Goal validated'
            goal_handle.publish_feedback(feedback)

            # --- Phase 2: Extract box (5-40%) ---
            # ExtractBox acquires/releases its own lock internally.
            feedback.current_phase = 'extracting_box'
            feedback.progress_percentage = 5.0
            feedback.message = 'Extracting box from shelf'
            goal_handle.publish_feedback(feedback)

            extract_success, extract_msg = await self._extract_box(
                box, goal_handle, feedback
            )

            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                return self._create_canceled_result(
                    medicine_qr, items_picked, total_items, start_time
                )

            if not extract_success:
                return self._create_result(
                    goal_handle, False, medicine_qr,
                    items_picked, total_items, start_time,
                    f'Box extraction failed: {extract_msg}'
                )

            self.get_logger().info(f'Box extracted successfully: {extract_msg}')

            # --- Phase 3: Per-item pick & place (40-90%) ---
            acquired = await self.scara.acquire()
            if not acquired:
                return self._create_result(
                    goal_handle, False, medicine_qr,
                    items_picked, total_items, start_time,
                    'SCARA arm is busy'
                )

            try:
                cfg_timeouts = self.config['timeouts']

                for idx, med in enumerate(detection):
                    # Check total timeout
                    if (time.time() - start_time) > cfg_timeouts['total_timeout']:
                        return self._create_result(
                            goal_handle, False, medicine_qr,
                            items_picked, total_items, start_time,
                            f'Total timeout ({cfg_timeouts["total_timeout"]:.0f}s) exceeded '
                            f'after {items_picked}/{total_items} items'
                        )

                    # Check cancellation
                    if goal_handle.is_cancel_requested:
                        goal_handle.canceled()
                        return self._create_canceled_result(
                            medicine_qr, items_picked, total_items, start_time
                        )

                    feedback.current_phase = 'picking'
                    feedback.current_item_index = idx
                    item_progress_start = 40.0 + (idx / total_items) * 50.0
                    feedback.progress_percentage = item_progress_start
                    feedback.message = f'Processing item {idx + 1}/{total_items}: {med.image_id}'
                    goal_handle.publish_feedback(feedback)

                    self.get_logger().info(
                        f'Item {idx + 1}/{total_items}: image_id={med.image_id}, '
                        f'row_id={med.row_id}, center=({med.box_center.x:.3f}, '
                        f'{med.box_center.y:.3f}, {med.box_center.z:.3f})'
                    )

                    success, msg = await self._pick_and_place_item(
                        idx, med, box, goal_handle, feedback, total_items
                    )

                    if success:
                        items_picked += 1
                        medicine_qr.append(med.image_id)
                        self.get_logger().info(f'Item {idx + 1} picked successfully')
                    else:
                        self.get_logger().warn(f'Item {idx + 1} failed: {msg}')
                        if not self.config['behavior']['continue_on_item_failure']:
                            return self._create_result(
                                goal_handle, False, medicine_qr,
                                items_picked, total_items, start_time,
                                f'Item {idx + 1} failed: {msg}'
                            )

                # --- Phase 4: Finalize (90-100%) ---
                feedback.current_phase = 'finalizing'
                feedback.progress_percentage = 90.0
                feedback.message = 'Returning home'
                goal_handle.publish_feedback(feedback)

                if self.config['behavior']['return_home_after_all']:
                    result = await self.scara.move_home()
                    if not result.success:
                        self.get_logger().warn(f'Home return failed: {result.message}')
            finally:
                await self.scara.release()

            feedback.progress_percentage = 100.0
            feedback.message = 'Complete'
            goal_handle.publish_feedback(feedback)

            all_picked = (items_picked == total_items)
            message = (
                f'Picked {items_picked}/{total_items} items successfully'
                if all_picked
                else f'Partial success: {items_picked}/{total_items} items picked'
            )

            return self._create_result(
                goal_handle, all_picked, medicine_qr,
                items_picked, total_items, start_time, message
            )

        except Exception as e:
            self.get_logger().error(f'Error during execution: {e}')
            return self._create_result(
                goal_handle, False, medicine_qr,
                items_picked, total_items, start_time,
                f'Execution error: {e}'
            )
        finally:
            self._executing = False

    # ------------------------------------------------------------------
    # Phase 2: Box extraction
    # ------------------------------------------------------------------

    async def _extract_box(self, box, goal_handle, feedback):
        """Call ExtractBox action to extract the target box from the shelf.

        Returns:
            (True, message) on success
            (False, message) on failure
        """
        if not self.extract_box_client.wait_for_server(timeout_sec=10.0):
            return False, 'ExtractBox action server not available'

        extract_goal = ExtractBox.Goal()
        extract_goal.box = box

        self.get_logger().info(
            f'Sending ExtractBox goal: side={box.side}, '
            f'cabinet={box.cabinet_num}, row={box.row}, column={box.column}'
        )

        def _relay_extract_feedback(fb_msg):
            """Relay ExtractBox feedback mapped to 5-40% range."""
            extract_fb = fb_msg.feedback
            mapped = 5.0 + extract_fb.progress_percentage * 0.35
            feedback.current_phase = 'extracting_box'
            feedback.progress_percentage = float(mapped)
            feedback.message = f'Extracting box: {extract_fb.current_phase}'
            goal_handle.publish_feedback(feedback)

        try:
            send_goal_future = await self.extract_box_client.send_goal_async(
                extract_goal,
                feedback_callback=_relay_extract_feedback,
            )

            if not send_goal_future.accepted:
                return False, 'ExtractBox goal rejected'

            self._active_extract_goal_handle = send_goal_future

            result_future = await send_goal_future.get_result_async()

            self._active_extract_goal_handle = None

            if result_future.status == GoalStatus.STATUS_CANCELED:
                return False, 'ExtractBox was canceled'

            extract_result = result_future.result
            if extract_result.success:
                self.get_logger().info(f'Box extracted: {extract_result.box_id}')
                return True, extract_result.message
            else:
                return False, extract_result.message

        except Exception as e:
            self._active_extract_goal_handle = None
            return False, f'ExtractBox error: {e}'

    # ------------------------------------------------------------------
    # Phase 3: Per-item pick & place
    # ------------------------------------------------------------------

    async def _pick_and_place_item(
        self, index: int, medicament: Medicament, box: Address,
        goal_handle, feedback: PickItemsFromWarehouse.Feedback,
        total_items: int,
    ) -> Tuple[bool, str]:
        """Execute pick-and-place for a single item.

        Returns:
            (True, message) on success
            (False, message) on failure
        """
        cfg_heights = self.config['pick_heights']
        cfg_motion = self.config['motion']
        cfg_tool = self.config['tool']
        safe_z = cfg_heights['safe_z']
        per_item_timeout = self.config['timeouts']['per_item_timeout']
        item_start_time = time.time()

        # Progress range for this item within the 40-90% band
        item_start = 40.0 + (index / total_items) * 50.0
        item_end = 40.0 + ((index + 1) / total_items) * 50.0
        item_range = item_end - item_start

        def _item_progress(relative_pct: float) -> float:
            return item_start + relative_pct * item_range / 100.0

        def _publish(phase_msg: str, relative_pct: float):
            feedback.progress_percentage = _item_progress(relative_pct)
            feedback.message = phase_msg
            goal_handle.publish_feedback(feedback)

        def _is_canceled() -> bool:
            return goal_handle.is_cancel_requested

        def _is_timed_out() -> bool:
            return (time.time() - item_start_time) > per_item_timeout

        # --- 3a. Detect item ---
        _publish(f'Detecting item {index + 1}', 0.0)

        max_retries = self.config['behavior']['max_detection_retries']
        detection = None
        for attempt in range(1 + max_retries):
            success, detection = self.vision.find_box(medicament, box)
            if success and detection is not None and detection.is_valid:
                break
            if attempt < max_retries:
                self.get_logger().warn(
                    f'Detection attempt {attempt + 1} failed for item {index + 1}, '
                    f'retrying ({attempt + 1}/{max_retries})...'
                )
        if not success or detection is None or not detection.is_valid:
            return False, f'Vision detection failed after {1 + max_retries} attempts'

        grasp = detection.grasp_pose
        self.get_logger().info(
            f'  Grasp pose: ({grasp.x:.4f}, {grasp.y:.4f}, {grasp.z:.4f})'
        )

        if _is_canceled():
            return False, 'Canceled'
        if _is_timed_out():
            return False, f'Per-item timeout ({per_item_timeout:.0f}s) exceeded'

        # --- 3b. Approach ---
        _publish(f'Approaching item {index + 1}', 15.0)

        result = await self.scara.move_z(safe_z, velocity=cfg_motion['z_velocity'])
        if not result.success:
            return False, f'Z safe move failed: {result.message}'

        if _is_canceled():
            return False, 'Canceled'
        if _is_timed_out():
            return False, f'Per-item timeout ({per_item_timeout:.0f}s) exceeded'

        result = await self.scara.move_to_point(
            x=grasp.x, y=grasp.y,
            velocity=cfg_motion['approach_velocity'],
        )
        if not result.success:
            return False, f'Approach move failed: {result.message}'

        if _is_canceled():
            return False, 'Canceled'
        if _is_timed_out():
            return False, f'Per-item timeout ({per_item_timeout:.0f}s) exceeded'

        # Descend to approach height above grasp point
        approach_z = grasp.z + cfg_heights['approach_offset_z']
        result = await self.scara.move_z(approach_z, velocity=cfg_motion['approach_velocity'])
        if not result.success:
            return False, f'Z approach descent failed: {result.message}'

        if _is_canceled():
            return False, 'Canceled'
        if _is_timed_out():
            return False, f'Per-item timeout ({per_item_timeout:.0f}s) exceeded'

        # --- 3c. Pick ---
        _publish(f'Picking item {index + 1}', 30.0)

        pick_z = grasp.z - cfg_heights['grasp_offset_z']
        result = await self.scara.move_z(pick_z, velocity=cfg_motion['pick_velocity'])
        if not result.success:
            return False, f'Z pick move failed: {result.message}'

        result = await self.scara.trigger_tool(True)
        if not result.success:
            self.get_logger().warn(f'Tool activate failed (non-fatal): {result.message}')

        time.sleep(cfg_tool['settle_time_after_grasp'])

        result = await self.scara.move_z(safe_z, velocity=cfg_motion['z_velocity'])
        if not result.success:
            return False, f'Z raise after pick failed: {result.message}'

        if _is_canceled():
            return False, 'Canceled'
        if _is_timed_out():
            return False, f'Per-item timeout ({per_item_timeout:.0f}s) exceeded'

        # --- 3d. Detect drop point ---
        _publish(f'Finding drop point for item {index + 1}', 55.0)

        success, drop_point = self.vision.container_side(index)
        if not success or drop_point is None:
            return False, 'Container detection failed'

        self.get_logger().info(
            f'  Drop point: ({drop_point.x:.4f}, {drop_point.y:.4f}, {drop_point.z:.4f})'
        )

        if _is_canceled():
            return False, 'Canceled'
        if _is_timed_out():
            return False, f'Per-item timeout ({per_item_timeout:.0f}s) exceeded'

        # --- 3e. Place ---
        _publish(f'Placing item {index + 1}', 65.0)

        result = await self.scara.move_to_point(
            x=drop_point.x, y=drop_point.y,
            velocity=cfg_motion['transit_velocity'],
        )
        if not result.success:
            return False, f'Transit move failed: {result.message}'

        if _is_canceled():
            return False, 'Canceled'
        if _is_timed_out():
            return False, f'Per-item timeout ({per_item_timeout:.0f}s) exceeded'

        place_z = drop_point.z + cfg_heights['place_offset_z']
        result = await self.scara.move_z(place_z, velocity=cfg_motion['place_velocity'])
        if not result.success:
            return False, f'Z place move failed: {result.message}'

        result = await self.scara.trigger_tool(False)
        if not result.success:
            self.get_logger().warn(f'Tool deactivate failed (non-fatal): {result.message}')

        time.sleep(cfg_tool['settle_time_after_release'])

        result = await self.scara.move_z(safe_z, velocity=cfg_motion['z_velocity'])
        if not result.success:
            return False, f'Z raise after place failed: {result.message}'

        _publish(f'Item {index + 1} complete', 100.0)

        return True, f'Item {index + 1} picked and placed'

    # ------------------------------------------------------------------
    # Result / cancellation helpers
    # ------------------------------------------------------------------

    def _create_result(self, goal_handle, success: bool, medicine_qr: List[str],
                       items_picked: int, items_total: int,
                       start_time: float, message: str):
        """Create and return action result."""
        result = PickItemsFromWarehouse.Result()
        result.success = success
        result.medicine_qr = medicine_qr
        result.items_picked = items_picked
        result.items_total = items_total
        result.execution_time = time.time() - start_time
        result.message = message

        if success:
            goal_handle.succeed()
            self.get_logger().info(f'PickItems succeeded: {message}')
        else:
            goal_handle.abort()
            self.get_logger().error(f'PickItems failed: {message}')

        return result

    def _create_canceled_result(self, medicine_qr: List[str],
                                items_picked: int, items_total: int,
                                start_time: float):
        """Create result for canceled goal."""
        result = PickItemsFromWarehouse.Result()
        result.success = False
        result.medicine_qr = medicine_qr
        result.items_picked = items_picked
        result.items_total = items_total
        result.execution_time = time.time() - start_time
        result.message = 'Goal canceled'
        return result


def main(args=None):
    rclpy.init(args=args)

    node = PickItemsFromWarehouseServer()

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
