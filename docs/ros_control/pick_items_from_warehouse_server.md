# PickItemsFromWarehouse Action Server

Orchestrates picking medicines from an extracted box and placing them into a shipping container using the SCARA arm and a pluggable vision provider.

## Overview

The PickItemsFromWarehouse action server performs pick-and-place operations for one or more medicines. It receives a list of medicine detections (with approximate positions), uses a vision provider to compute grasp and drop coordinates, and drives the SCARA arm through the pick-and-place cycle for each item.

**Dependencies:**
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
│  Phase 2: Per-item loop           (5-90%)                        │
│         For each medicine in detection[]:                        │
│         ┌─ 2a. Detect   ─► VisionProvider.find_box()            │
│         ├─ 2b. Approach ─► move_z(safe) + move_to_point(grasp)  │
│         ├─ 2c. Pick     ─► move_z(grasp) + trigger_tool(True)   │
│         ├─ 2d. Find drop─► VisionProvider.container_side()       │
│         └─ 2e. Place    ─► move_to_point(drop) + trigger_tool(F)│
│                                                                  │
│  Phase 3: Finalize                (90-100%)                      │
│         Return SCARA home, compile results                       │
└──────────────────────────────────────────────────────────────────┘
```

### Step Details

**Phase 1 — Initialize (0-5%)**
Validate the goal. If the detection list is empty, abort with an error message.

**Phase 2 — Per-item pick & place (5-90%)**
For each medicine in the detection list, execute the full pick-and-place cycle:

| Sub-step | Relative % | ScaraClient / Vision Method | Description |
|----------|-----------|----------------------------|-------------|
| 2a. Detect | 0-15% | `vision.find_box(medicament, box)` | Get grasp pose from vision provider |
| 2b. Approach | 15-30% | `scara.move_z(safe_z)` + `scara.move_to_point(grasp_x, grasp_y)` | Raise Z for safe transit, move above grasp point |
| 2c. Pick | 30-55% | `scara.move_z(grasp_z)` + `scara.trigger_tool(True)` + settle + `scara.move_z(safe_z)` | Lower to grasp, activate tool, wait, raise |
| 2d. Find drop | 55-65% | `vision.container_side(item_index)` | Get drop position in container |
| 2e. Place | 65-100% | `scara.move_to_point(drop_x, drop_y)` + `scara.move_z(drop_z)` + `scara.trigger_tool(False)` + settle + `scara.move_z(safe_z)` | Transit to container, lower, release, raise |

Cancellation is checked between each sub-step. If an item fails and `continue_on_item_failure` is `true` (default), the server skips to the next item.

**Phase 3 — Finalize (90-100%)**
Return SCARA to home position (if `return_home_after_all` is `true`). Compile result with `items_picked`, `items_total`, and list of `medicine_qr` codes.

### Progress Mapping

Per-item progress is evenly distributed across the 5-90% band:

```
item_progress_start = 5.0 + (item_index / total_items) * 85.0
item_progress_end   = 5.0 + ((item_index + 1) / total_items) * 85.0
```

Example with 2 items:
- Item 0: 5.0% — 47.5%
- Item 1: 47.5% — 90.0%

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
string current_phase                  # "initializing", "picking", "finalizing"
uint8 current_item_index              # Current item (0-based)
uint8 total_items                     # Total items count
float32 progress_percentage           # Overall progress 0-100%
string message                        # Human-readable status
```

### Feedback Phases

| Phase | Progress | Description |
|-------|----------|-------------|
| initializing | 0-5% | Goal validation |
| picking | 5-90% | Per-item detect → approach → pick → find drop → place cycle |
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
                    │ (ROS2 Node)                   │
                    └──────┬───────────────────────┘
                           │
               ┌───────────┼───────────┐
               │                       │
               ▼                       ▼
     ┌──────────────────┐   ┌──────────────────────┐
     │   ScaraClient    │   │   VisionProvider     │
     │   (Library)      │   │   (Internal ABC)     │
     └────────┬─────────┘   └──────────┬───────────┘
              │                        │
              ▼                        ▼
     ┌──────────────────────┐   ┌─────────────────────┐
     │ scara_controller     │   │ MockVisionProvider   │
     │ + picker_z_controller│   │ (config-based poses) │
     │ (SCARA joints + Z)  │   └─────────────────────┘
     └──────────────────────┘
```

### ROS2 Interfaces Used

| Interface | Type | Direction | Purpose |
|-----------|------|-----------|---------|
| `/PickItems` | Action Server | Incoming | This node's action interface |
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
| `pick_heights.approach_offset_z` | float | `0.05` | Height above grasp point for approach [m] |
| `pick_heights.grasp_offset_z` | float | `0.005` | Extra depth below grasp point [m] |
| `pick_heights.place_offset_z` | float | `0.02` | Height above drop point for release [m] |
| `motion.approach_velocity` | float | `0.3` | Velocity for approach moves (0-1) |
| `motion.pick_velocity` | float | `0.1` | Velocity for pick (slow, precise) |
| `motion.transit_velocity` | float | `0.5` | Velocity for transit between box and container |
| `motion.place_velocity` | float | `0.2` | Velocity for place |
| `motion.z_velocity` | float | `0.1` | Z-axis velocity |
| `tool.settle_time_after_grasp` | float | `0.5` | Wait after activating tool [s] |
| `tool.settle_time_after_release` | float | `0.3` | Wait after deactivating tool [s] |
| `timeouts.per_item_timeout` | float | `60.0` | Max time per single item [s] |
| `timeouts.total_timeout` | float | `300.0` | Max total execution time [s] |
| `behavior.continue_on_item_failure` | bool | `true` | Continue to next item if one fails |
| `behavior.return_home_after_all` | bool | `true` | Return SCARA home after all items |
| `behavior.max_detection_retries` | int | `2` | Retry find_box on failure |
| `mock.enabled` | bool | `true` | Use MockVisionProvider |
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
# Pick 1 medicine
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
3. `pick_items_from_warehouse_server` starts (triggered by `scara_controller` exit)

The server is wrapped with `IfCondition(use_scara)` — it only launches when SCARA is enabled.

### Run Standalone

```bash
ros2 run ros_control pick_items_from_warehouse_server.py
```

Requires `scara_controller` and `picker_z_controller` to be running.

---

## Error Handling

| Error | Phase | Result |
|-------|-------|--------|
| Empty detection list | initializing | success=False, message="No items in detection list" |
| Vision detection failed | picking (2a) | Item skipped (if continue_on_item_failure), else abort |
| SCARA motion failed (IK, limits) | picking (2b-2e) | Item fails with specific message |
| Tool activate/deactivate failed | picking (2c/2e) | Logged as warning, continues (non-fatal) |
| Container detection failed | picking (2d) | Item fails, "Container detection failed" |
| All items picked | finalizing | success=True |
| Some items failed | finalizing | success=False, items_picked < items_total |

### Cancellation

Cancellation is checked between each sub-step within an item and between items:
1. `goal_handle.is_cancel_requested` polled at 7 points per item cycle
2. On cancel: current SCARA motion completes (safe stop), partial results returned
3. Result includes `medicine_qr` and `items_picked` for successfully completed items

---

## Implementation Notes

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
- [extract_box_server.md](extract_box_server.md) — ExtractBox action server (upstream in pipeline)
- [package_structure.md](package_structure.md) — Full package documentation
