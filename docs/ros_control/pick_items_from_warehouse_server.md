# PickItemsFromWarehouse Action Server

Orchestrates the full medicine picking workflow: extracts a box from the shelf via `/extract_box`, picks medicines from it, and places them into a shipping container using the SCARA arm and a pluggable vision provider.

## Overview

The PickItemsFromWarehouse action server is the top-level orchestrator for picking. It receives a list of medicine detections (with approximate positions) and a box address, then:
1. Calls `/extract_box` to navigate the platform and extract the box
2. Uses a vision provider to compute grasp and drop coordinates
3. Drives the SCARA arm through the pick-and-place cycle for each item

**Dependencies:**
- `/extract_box` action server — navigates platform and extracts box from shelf
- `ScaraClient` library (`scara_control`) — controls the SCARA arm (IK, Z-axis, tool)
- `VisionProvider` — pluggable ABC for grasp/drop position computation (currently `MockVisionProvider`)

**Condition:** Only runs when SCARA is enabled (`use_scara:=true`).

## Execution Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                  PickItemsFromWarehouse Action                    │
├──────────────────────────────────────────────────────────────────┤
│  Phase 1: Initialize              (0-5%)                         │
│         Validate goal, check detection list non-empty            │
│                                                                  │
│  Phase 2: Extract box             (5-40%)                        │
│         Call /extract_box action (navigate + SCARA extraction)   │
│                                                                  │
│  Phase 3: Per-item loop           (40-90%)                       │
│         For each medicine in detection[]:                        │
│         ┌─ 3a. Detect   ─► VisionProvider.find_box() + retries  │
│         ├─ 3b. Approach ─► move_z(safe) + move_to_point(grasp)  │
│         │                  + move_z(approach_z)                  │
│         ├─ 3c. Pick     ─► move_z(pick_z) + trigger_tool(True)  │
│         ├─ 3d. Find drop─► VisionProvider.container_side()       │
│         └─ 3e. Place    ─► move_to_point(drop) + trigger_tool(F)│
│                                                                  │
│  Phase 4: Finalize                (90-100%)                      │
│         Return SCARA home, compile results                       │
└──────────────────────────────────────────────────────────────────┘
```

### Step Details

**Phase 1 — Initialize (0-5%)**
Validate the goal. If the detection list is empty, abort with an error message.

**Phase 2 — Extract box (5-40%)**
Call `/extract_box` action with the target box address. ExtractBox handles platform navigation and SCARA extraction internally. Feedback from ExtractBox is relayed and mapped to the 5-40% progress range. Cancellation is forwarded to the active ExtractBox goal. If extraction fails, the entire goal aborts.

**Phase 3 — Per-item pick & place (40-90%)**
For each medicine in the detection list, execute the full pick-and-place cycle:

| Sub-step | Relative % | ScaraClient / Vision Method | Description |
|----------|-----------|----------------------------|-------------|
| 3a. Detect | 0-15% | `vision.find_box(medicament, box)` with up to `max_detection_retries` | Get grasp pose from vision provider |
| 3b. Approach | 15-30% | `scara.move_z(safe_z)` + `scara.move_to_point(grasp_x, grasp_y)` + `scara.move_z(approach_z)` | Raise Z, move XY, descend to approach height |
| 3c. Pick | 30-55% | `scara.move_z(pick_z)` + `scara.trigger_tool(True)` + settle + `scara.move_z(safe_z)` | Descend to grasp, activate tool, wait, raise |
| 3d. Find drop | 55-65% | `vision.container_side(item_index)` | Get drop position in container |
| 3e. Place | 65-100% | `scara.move_to_point(drop_x, drop_y)` + `scara.move_z(drop_z)` + `scara.trigger_tool(False)` + settle + `scara.move_z(safe_z)` | Transit to container, lower, release, raise |

Cancellation and per-item timeout are checked between each sub-step. If an item fails and `continue_on_item_failure` is `true` (default), the server skips to the next item. Total timeout is checked before starting each item.

**Phase 4 — Finalize (90-100%)**
Return SCARA to home position (if `return_home_after_all` is `true`). Compile result with `items_picked`, `items_total`, and list of `medicine_qr` codes.

### Progress Mapping

Per-item progress is evenly distributed across the 40-90% band:

```
item_progress_start = 40.0 + (item_index / total_items) * 50.0
item_progress_end   = 40.0 + ((item_index + 1) / total_items) * 50.0
```

Example with 2 items:
- Item 0: 40.0% — 65.0%
- Item 1: 65.0% — 90.0%

---

## Message Definitions

### Medicament.msg

File: `ros_control/msg/Medicament.msg`

```
string image_id                       # Unique image identifier for the medicine
uint8 row_id                          # Row number within the box (0-based)
geometry_msgs/Point box_center        # Approximate center in world coordinates (meters)
```

### PickItemsFromWarehouse.action

File: `ros_control/action/PickItemsFromWarehouse.action`

```yaml
# Goal
ros_control/Medicament[] detection    # List of medicines to pick
ros_control/Address box               # Source box address on the shelf
---
# Result
bool success                          # true if ALL items picked and placed
string[] medicine_qr                  # image_id codes of successfully picked medicines
uint8 items_picked                    # Count of successfully picked items
uint8 items_total                     # Total items requested
float64 execution_time                # Total execution time (seconds)
string message                        # Result status message
---
# Feedback
string current_phase                  # "initializing", "extracting_box", "picking", "finalizing"
uint8 current_item_index              # Current item (0-based)
uint8 total_items                     # Total items count
float32 progress_percentage           # Overall progress 0-100%
string message                        # Human-readable status
```

### Feedback Phases

| Phase | Progress | Description |
|-------|----------|-------------|
| initializing | 0-5% | Goal validation |
| extracting_box | 5-40% | ExtractBox sub-action (navigate + extract) |
| picking | 40-90% | Per-item detect → approach → pick → find drop → place cycle |
| finalizing | 90-100% | SCARA home return, result compilation |

### Result: Partial Success

The result `success` is `true` only when `items_picked == items_total`. Partial results are reported when some items fail:

```
success: false
items_picked: 2
items_total: 3
medicine_qr: ['med-001', 'med-003']   # Only successfully picked items
message: "Partial success: 2/3 items picked"
```

---

## Architecture

### Node Dependencies

```
                    ┌──────────────────────────────┐
                    │ PickItemsFromWarehouse Server │
                    │ (ROS2 Node — Orchestrator)    │
                    └──────┬───────────────────────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
  ┌──────────────────┐ ┌────────────┐ ┌──────────────────────┐
  │  ExtractBox      │ │ ScaraClient│ │   VisionProvider     │
  │  (Action Client) │ │ (Library)  │ │   (Internal ABC)     │
  └────────┬─────────┘ └─────┬──────┘ └──────────┬───────────┘
           │                 │                    │
           ▼                 ▼                    ▼
  ┌──────────────────┐ ┌──────────────────────┐ ┌─────────────────────┐
  │ extract_box_server│ │ scara_controller     │ │ MockVisionProvider   │
  │ (navigate+extract)│ │ + picker_z_controller│ │ (config-based poses) │
  └──────────────────┘ │ (SCARA joints + Z)  │ └─────────────────────┘
                       └──────────────────────┘
```

### ROS2 Interfaces Used

| Interface | Type | Direction | Purpose |
|-----------|------|-----------|---------|
| `/PickItems` | Action Server | Incoming | This node's action interface |
| `/extract_box` | Action Client | Outgoing | Box extraction (navigate + SCARA hook) |
| `/scara_controller/follow_joint_trajectory` | Action Client | Outgoing | Via ScaraClient (arm motion) |
| `/picker_z_controller/follow_joint_trajectory` | Action Client | Outgoing | Via ScaraClient (Z axis) |
| `/scara_tool/activate` | Service Client | Outgoing | Via ScaraClient (tool on) — non-fatal if unavailable |
| `/scara_tool/deactivate` | Service Client | Outgoing | Via ScaraClient (tool off) — non-fatal if unavailable |
| `/joint_states` | Subscription | Incoming | Via ScaraClient (arm state) |

### Threading Model

- `ReentrantCallbackGroup` for async action callbacks
- `MultiThreadedExecutor` for concurrent callback handling
- Blocking `time.sleep()` for settle times (safe in multi-threaded executor)

---

## Configuration

Configuration file: `ros_control/config/pick_items_from_warehouse_config.yaml`

```yaml
pick_items_from_warehouse_server:
  ros__parameters:
    pick_heights:
      safe_z: 0.25                    # Safe transit height (meters)
      approach_offset_z: 0.05         # Height above grasp point for approach
      grasp_offset_z: 0.005           # Extra depth below grasp point
      place_offset_z: 0.02            # Height above drop point for release

    motion:
      approach_velocity: 0.3          # Velocity for approach moves (fraction 0-1)
      pick_velocity: 0.1              # Velocity for pick (slow, precise)
      transit_velocity: 0.5           # Velocity for transit between box and container
      place_velocity: 0.2             # Velocity for place
      z_velocity: 0.1                 # Z-axis velocity

    tool:
      settle_time_after_grasp: 0.5    # Wait time after activating tool (seconds)
      settle_time_after_release: 0.3  # Wait time after deactivating tool (seconds)

    timeouts:
      per_item_timeout: 60.0          # Max time per single item pick-place
      total_timeout: 300.0            # Max total execution time

    behavior:
      continue_on_item_failure: true  # Continue to next item if one fails
      return_home_after_all: true     # Return SCARA home after all items
      max_detection_retries: 2        # Retry find_box on failure

    mock:
      enabled: true                   # Use MockVisionProvider
      grasp_offset_x: 0.15           # Grasp X offset from box_center (meters)
      grasp_offset_y: 0.0            # Grasp Y offset from box_center (meters)
      grasp_z: 0.10                  # Grasp Z height (meters)
      row_spacing_y: 0.05            # Y spacing between rows in box (meters)
      place_x: 0.20                  # Container drop X (meters)
      place_y: -0.15                 # Container drop Y (meters)
      place_z: 0.10                  # Container drop Z (meters)
      item_spacing_x: 0.06           # X spacing between placed items (meters)
      default_box_length: 0.10       # Default medicine box length (meters)
      default_box_width: 0.04        # Default medicine box width (meters)
      default_box_height: 0.03       # Default medicine box height (meters)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pick_heights.safe_z` | float | `0.25` | Safe transit height [m] |
| `pick_heights.approach_offset_z` | float | `0.05` | Height above grasp point for intermediate descent [m] |
| `pick_heights.grasp_offset_z` | float | `0.005` | Extra depth below grasp point [m] |
| `pick_heights.place_offset_z` | float | `0.02` | Height above drop point for release [m] |
| `motion.approach_velocity` | float | `0.3` | Velocity for approach moves and intermediate descent (0-1) |
| `motion.pick_velocity` | float | `0.1` | Velocity for final descent to grasp (slow, precise) |
| `motion.transit_velocity` | float | `0.5` | Velocity for transit between box and container |
| `motion.place_velocity` | float | `0.2` | Velocity for place |
| `motion.z_velocity` | float | `0.1` | Z-axis velocity for safe height moves |
| `tool.settle_time_after_grasp` | float | `0.5` | Wait after activating tool [s] |
| `tool.settle_time_after_release` | float | `0.3` | Wait after deactivating tool [s] |
| `timeouts.per_item_timeout` | float | `60.0` | Max time per single item pick-place [s] |
| `timeouts.total_timeout` | float | `300.0` | Max total execution time [s] |
| `behavior.continue_on_item_failure` | bool | `true` | Continue to next item if one fails |
| `behavior.return_home_after_all` | bool | `true` | Return SCARA home after all items |
| `behavior.max_detection_retries` | int | `2` | Number of retries for find_box on failure |
| `mock.enabled` | bool | `true` | Use MockVisionProvider (false raises RuntimeError until RealVisionProvider exists) |
| `mock.grasp_offset_x` | float | `0.15` | Grasp X offset from box_center [m] |
| `mock.grasp_offset_y` | float | `0.0` | Grasp Y offset from box_center [m] |
| `mock.grasp_z` | float | `0.10` | Grasp Z height [m] |
| `mock.row_spacing_y` | float | `0.05` | Y spacing between rows in box [m] |
| `mock.place_x` | float | `0.20` | Container drop X [m] |
| `mock.place_y` | float | `-0.15` | Container drop Y [m] |
| `mock.place_z` | float | `0.10` | Container drop Z [m] |
| `mock.item_spacing_x` | float | `0.06` | X spacing between placed items [m] |

### Configuration Loading

The server loads config from `pick_items_from_warehouse_config.yaml` with deep-merge against built-in defaults. Any subset of parameters can be overridden in the YAML file; unspecified parameters use defaults.

---

## Usage

### Command Line

```bash
# Pick 1 medicine (extracts box automatically)
ros2 action send_goal /PickItems ros_control/action/PickItemsFromWarehouse "{
  detection: [{image_id: 'med-001', row_id: 0, box_center: {x: 0.1, y: 0.0, z: 0.1}}],
  box: {side: 'left', cabinet_num: 2, row: 1, column: 0}
}" --feedback

# Pick 2 medicines from same box
ros2 action send_goal /PickItems ros_control/action/PickItemsFromWarehouse "{
  detection: [
    {image_id: 'med-001', row_id: 0, box_center: {x: 0.1, y: 0.0, z: 0.1}},
    {image_id: 'med-002', row_id: 1, box_center: {x: 0.1, y: 0.05, z: 0.1}}
  ],
  box: {side: 'left', cabinet_num: 2, row: 1, column: 0}
}" --feedback
```

### Python Client

```python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from ros_control.action import PickItemsFromWarehouse
from ros_control.msg import Medicament, Address


class PickItemsClient(Node):
    def __init__(self):
        super().__init__('pick_items_client')
        self.client = ActionClient(self, PickItemsFromWarehouse, '/PickItems')

    def send_goal(self, medicines, side, cabinet_num, row, column):
        self.client.wait_for_server()

        goal = PickItemsFromWarehouse.Goal()
        goal.box.side = side
        goal.box.cabinet_num = cabinet_num
        goal.box.row = row
        goal.box.column = column

        for image_id, row_id, cx, cy, cz in medicines:
            med = Medicament()
            med.image_id = image_id
            med.row_id = row_id
            med.box_center.x = cx
            med.box_center.y = cy
            med.box_center.z = cz
            goal.detection.append(med)

        future = self.client.send_goal_async(
            goal, feedback_callback=self.feedback_callback
        )
        future.add_done_callback(self.goal_response_callback)

    def feedback_callback(self, feedback_msg):
        fb = feedback_msg.feedback
        self.get_logger().info(
            f'[{fb.current_phase}] Item {fb.current_item_index + 1}/{fb.total_items} '
            f'Progress: {fb.progress_percentage:.1f}% — {fb.message}'
        )

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().error('Goal rejected')
            return
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.result_callback)

    def result_callback(self, future):
        result = future.result().result
        if result.success:
            self.get_logger().info(
                f'Picked {result.items_picked}/{result.items_total} items '
                f'in {result.execution_time:.1f}s: {result.medicine_qr}'
            )
        else:
            self.get_logger().error(f'Failed: {result.message}')


def main():
    rclpy.init()
    client = PickItemsClient()
    client.send_goal(
        medicines=[
            ('med-001', 0, 0.1, 0.0, 0.1),
            ('med-002', 1, 0.1, 0.05, 0.1),
        ],
        side='left', cabinet_num=2, row=1, column=0,
    )
    rclpy.spin(client)


if __name__ == '__main__':
    main()
```

### Launch with Bringup

The server is automatically started by `manipulator_bringup.launch.py` when SCARA is enabled:

```bash
ros2 launch manipulator_bringup manipulator_bringup.launch.py use_scara:=true
```

Startup sequence:
1. `joint_state_broadcaster` spawns
2. `scara_controller` spawns
3. `extract_box_server` and `pick_items_from_warehouse_server` start (triggered by `scara_controller` exit)

The server is wrapped with `IfCondition(use_scara)` — it only launches when SCARA is enabled.

### Run Standalone

```bash
ros2 run ros_control pick_items_from_warehouse_server.py
```

Requires `scara_controller`, `picker_z_controller`, and `extract_box_server` to be running.

---

## Error Handling

| Error | Phase | Result |
|-------|-------|--------|
| Empty detection list | initializing | success=False, message="No items in detection list" |
| ExtractBox server not available | extracting_box | success=False, message="ExtractBox action server not available" |
| ExtractBox goal rejected | extracting_box | success=False, message="ExtractBox goal rejected" |
| ExtractBox failed | extracting_box | success=False, message="Box extraction failed: ..." |
| ExtractBox canceled | extracting_box | Goal canceled, partial results returned |
| Total timeout exceeded | picking (before item) | success=False, message="Total timeout (300s) exceeded after N/M items" |
| Per-item timeout exceeded | picking (3a-3e) | Item fails, "Per-item timeout (60s) exceeded" |
| Vision detection failed | picking (3a) | Item fails after `max_detection_retries + 1` attempts |
| SCARA motion failed (IK, limits) | picking (3b-3e) | Item fails with specific message |
| Tool activate/deactivate failed | picking (3c/3e) | Logged as warning, continues (non-fatal) |
| Container detection failed | picking (3d) | Item fails, "Container detection failed" |
| All items picked | finalizing | success=True |
| Some items failed | finalizing | success=False, items_picked < items_total |

### Cancellation

Cancellation is checked at multiple points:
1. After ExtractBox completes — forwarded via `_active_extract_goal_handle.cancel_goal_async()`
2. Before each item in the main loop
3. Between each sub-step within an item (7 checkpoints per item)
4. Per-item timeout is also checked at each of these 7 checkpoints

On cancel: current motion completes (safe stop), partial results returned with `medicine_qr` and `items_picked` for successfully completed items.

---

## Implementation Notes

### Two-Stage Approach Descent

The approach phase uses a two-stage Z descent:
1. `safe_z` (0.25m) → `approach_z` (grasp.z + approach_offset_z = 0.15m) at `approach_velocity`
2. `approach_z` (0.15m) → `pick_z` (grasp.z - grasp_offset_z = 0.095m) at `pick_velocity`

This gives controlled deceleration before contact with the medicine.

### Detection Retries

`find_box()` is called up to `1 + max_detection_retries` times (default: 3 attempts). Each failed attempt is logged as a warning. If all attempts fail, the item is skipped (with `continue_on_item_failure`) or the goal aborts.

### Tool Service in Mock Hardware

When running with mock hardware (`mock_components/GenericSystem`), the tool services (`/scara_tool/activate`, `/scara_tool/deactivate`) are not available. The server treats `trigger_tool()` failures as non-fatal — it logs a warning and continues the pick-and-place sequence. This allows full end-to-end testing of the motion pipeline without a real tool.

### Settle Times

After activating the tool (grasp) and deactivating it (release), the server waits for a configurable settle time to allow the vacuum/gripper to stabilize. These use `time.sleep()` (blocking) because ROS2's `MultiThreadedExecutor` does not expose a standard asyncio event loop.

### MockVisionProvider Position Computation

**Grasp position:**
```
grasp_x = box_center.x + grasp_offset_x
grasp_y = box_center.y + grasp_offset_y + row_id * row_spacing_y
grasp_z = grasp_z (from config)
```

**Drop position:**
```
drop_x = place_x + item_index * item_spacing_x
drop_y = place_y (from config)
drop_z = place_z (from config)
```

This spreads picked items along the X axis in the container.

---

## Files

| File | Description |
|------|-------------|
| `action/PickItemsFromWarehouse.action` | Action definition |
| `msg/Medicament.msg` | Medicine metadata message |
| `src/pick_items_from_warehouse_server.py` | Main node implementation |
| `config/pick_items_from_warehouse_config.yaml` | Default configuration |

## See Also

- [pick_items_from_warehouse_action.md](pick_items_from_warehouse_action.md) — Architectural design and design decisions
- [extract_box_server.md](extract_box_server.md) — ExtractBox action server (called as sub-action)
- [package_structure.md](package_structure.md) — Full package documentation
