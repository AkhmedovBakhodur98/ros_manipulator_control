# ExtractBox Action Server

Orchestrates box extraction from a cabinet cell by coordinating platform navigation (NavigateToAddress) and SCARA arm manipulation (ScaraClient).

## Overview

The ExtractBox action server provides a high-level interface for extracting a box from a specific cabinet cell. It takes a logical address, navigates the platform, then uses the SCARA arm to physically extract the box.

**Dependencies:**
- `NavigateToAddress` action — moves the platform to the target cell
- `ScaraClient` library (`scara_control`) — controls the SCARA arm for box extraction
- `tf2_ros` — TF2 listener (reserved for future use)

**Condition:** Only runs when SCARA is enabled (`use_scara:=true`).

## Execution Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     ExtractBox Action                        │
├─────────────────────────────────────────────────────────────┤
│  1. Navigate to Cell    ──► /navigate_to_address action     │
│         ↓                   (platform moves to X, Z)        │
│                             Phase: "navigating" (0-40%)     │
│                                                             │
│  2. Extract with SCARA  ──► ScaraClient methods             │
│         ↓                   (reach, grab, retract)          │
│                             Phase: "extracting" (40-90%)    │
│                                                             │
│  3. Verify & Complete   ──► Check sensor (mock for now)     │
│                             Generate box_id                  │
│                             Phase: "done" (90-100%)         │
└─────────────────────────────────────────────────────────────┘
```

### Step Details

**Step 1 — Navigate (0-40%)**
Send NavigateToAddress goal with the address from ExtractBox goal. Relay progress from NavigateToAddress feedback (0.0-1.0) mapped to 0-40% range. If navigation fails, abort immediately.

**Step 2 — Extract with SCARA (40-90%)**
Six-step hook-based extraction using `ScaraClient`:

```
SCARA EXTRACTION SEQUENCE (side view)

    cabinet wall
        │
        │  ┌───────┐ box
        │  │       │
        │  │  ┌─┐  │         1. ROTATE     wrist → ±90° (hook orientation)
        │  │  │h│  │         2. RAISE Z    ↑ picker goes up by z_offset
        │  │  │a│  │         3. APPROACH   arm extends into cabinet
        │  │  │n│  │         4. LOWER Z    ↓ hook drops into gap
        │  │  │d│  │         5. RETRACT    ← pull box out (pure Y linear)
        │  │  │l│  │         6. HOME       arm returns to home (optional)
        │  │  │e│  │
        │  └──┴─┴──┘
        │
              ← SCARA arm
```

| Sub-step | Progress | ScaraClient Method | Description |
|----------|----------|--------------------|-------------|
| 2a. Rotate wrist | 42% | `move_joints(wrist=±π/2)` | Orient hook (left=+90°, right=-90°) |
| 2b. Raise Z | 48% | `move_z(current_z + z_offset)` | Raise picker above handle plate |
| 2c. Approach | 55% | `move_to_point(x, y)` | Extend arm into cabinet (joint-space motion) |
| 2d. Lower Z | 65% | `move_z(current_z - z_offset)` | Hook drops into gap under handle plate |
| 2e. Retract | 75% | `move_linear(x, y)` | Pull box out — pure Y linear motion at constant X |
| 2f. Home | 85% | `move_home()` | Return arm to home position (if `return_home: true`) |

**Approach target computation:**
The approach target is computed in SCARA base frame. After navigation aligns the platform with the cell, the SCARA only needs to reach sideways (±Y) into the cabinet:

```
approach_x = approach_x_offset_m                          # constant X offset
approach_y = ±(approach_depth_m + y_inside_m)             # + for left, - for right
```

The `approach_x_offset_m` (default 0.20m) keeps the approach angle within the shoulder joint limits (±57°) and enables a pure-Y linear retract at constant X.

**Retract (pure Y-axis linear motion):**
The retract keeps TCP X coordinate constant and only changes Y:

```
retract: (approach_x, approach_y) → (approach_x, 0.0)
```

This produces a straight-line motion perpendicular to the cabinet face. The `move_linear` method interpolates Cartesian waypoints (every `linear_step_size` meters) and computes IK for each, then sends a multi-point trajectory to the controller.

**Side-dependent behavior:**
- **Left cabinet**: wrist = +π/2, approach_y = +depth
- **Right cabinet**: wrist = -π/2, approach_y = -depth

**Design decisions:**
- `move_to_point` for approach (joint-space, safer for entry into cabinet)
- `move_linear` for retraction (straight-line ensures box clears cabinet walls)
- Rotate wrist before raise Z — hook oriented first while arm is at home (safe)
- X offset on approach — ensures the entire retract path stays within shoulder joint limits

**Step 3 — Verify & Complete (90-100%)**
- Read box extraction sensor → `box_extracted` (mock: always `True` for now)
- Generate `box_id` string: `box_{side[0]}_{cabinet}_{row}_{col}`
  - Example: `box_l_2_1_0` for side="left", cabinet=2, row=1, col=0

---

## Message Definitions

### Address.msg

Shared message type for cabinet cell addressing.

File: `ros_control/msg/Address.msg`

```
string side       # Cabinet side: "left" or "right"
uint8 cabinet_num # Cabinet number (0-based)
uint8 row         # Row within cabinet (0-based)
uint8 column      # Column within cabinet (0-based)
```

### ExtractBox.action

File: `ros_control/action/ExtractBox.action`

```yaml
# Goal
Address box                   # Target cell address
---
# Result
bool success                  # true if box successfully extracted
bool box_extracted            # true if extraction sensor triggered (mock: always true)
string box_id                 # Box ID (format: box_{side[0]}_{cabinet}_{row}_{col})
float64 execution_time        # Total execution time (seconds)
string message                # Result message
---
# Feedback
string current_phase          # "navigating", "extracting", "done"
float32 progress_percentage   # 0-100%
```

### Feedback Phases

| Phase | Progress | Description |
|-------|----------|-------------|
| navigating | 0-40% | NavigateToAddress moving platform to cell |
| extracting | 40-90% | SCARA arm reaching, grabbing, retracting |
| done | 90-100% | Sensor check, box_id generation |

### Result: box_id Format

```
box_{side_letter}_{cabinet_num}_{row}_{column}

Examples:
  side="left",  cabinet=2, row=1, col=0  →  box_l_2_1_0
  side="right", cabinet=0, row=3, col=1  →  box_r_0_3_1
```

---

## Architecture

### Node Dependencies

```
                    ┌──────────────────────┐
                    │  ExtractBox Server   │
                    │  (ROS2 Node)         │
                    └──────┬───────────────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
  ┌─────────────────┐ ┌────────────┐ ┌─────────────────┐
  │ NavigateToAddress│ │ ScaraClient│ │ Sensor Interface │
  │ (Action Client)  │ │ (Library)  │ │ (Mock for now)   │
  └────────┬────────┘ └─────┬──────┘ └─────────────────┘
           │                │
           ▼                ▼
  ┌─────────────────┐ ┌─────────────────────────────┐
  │ MoveJointGroup  │ │ scara_controller            │
  │ (platform X, Z) │ │ + picker_z_controller       │
  └─────────────────┘ │ (SCARA joints + Z axis)     │
                      └─────────────────────────────┘
```

### ROS2 Interfaces Used

| Interface | Type | Direction | Purpose |
|-----------|------|-----------|---------|
| `/extract_box` | Action Server | Incoming | This node's action interface |
| `/navigate_to_address` | Action Client | Outgoing | Move platform to cell |
| `/scara_controller/follow_joint_trajectory` | Action Client | Outgoing | Via ScaraClient (arm motion) |
| `/picker_z_controller/follow_joint_trajectory` | Action Client | Outgoing | Via ScaraClient (Z axis) |
| `/joint_states` | Subscription | Incoming | Via ScaraClient (arm state) |

### Threading Model

- `ReentrantCallbackGroup` for async action/service calls
- `MultiThreadedExecutor` for concurrent callback handling

---

## Configuration

Configuration file: `ros_control/config/extract_box_config.yaml`

```yaml
extract_box_server:
  ros__parameters:
    hook_grasp:
      wrist_angle_rad: 1.5708       # ±π/2 — hook orientation (sign auto from side)
      z_offset_m: 0.03              # Raise/lower distance to clear handle plate
      approach_depth_m: 0.20        # How far arm reaches into cabinet (Y axis)
      approach_x_offset_m: 0.20     # X offset for approach — keeps arm within shoulder limits
      y_inside_m: 0.02              # Extra depth inside box edge
      z_lower_velocity: 0.05        # Z lowering velocity (m/s)

    motion:
      approach_velocity: 0.5        # Velocity scaling for approach
      retract_velocity: 0.05        # Velocity scaling for retraction (with box)
      linear_step_size: 0.005       # Step size for linear retraction (m)
      return_home: true             # If true, arm returns to home after retract

    timeouts:
      navigate_timeout: 60.0        # NavigateToAddress timeout (seconds)
      extract_timeout: 30.0         # SCARA extraction timeout (seconds)

    sensor:
      mock: true                    # Use mock sensor (always returns true)
      # topic: "/box_sensor"        # Real sensor topic (for future)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hook_grasp.wrist_angle_rad` | float | `1.5708` | Hook orientation angle (sign auto from side) |
| `hook_grasp.z_offset_m` | float | `0.03` | Raise/lower distance to clear handle plate [m] |
| `hook_grasp.approach_depth_m` | float | `0.20` | How far arm reaches into cabinet [m] |
| `hook_grasp.approach_x_offset_m` | float | `0.20` | X offset to keep approach within shoulder limits [m] |
| `hook_grasp.y_inside_m` | float | `0.02` | Extra depth inside box edge [m] |
| `hook_grasp.z_lower_velocity` | float | `0.05` | Z axis velocity [m/s] |
| `motion.approach_velocity` | float | `0.5` | Velocity scaling for approach |
| `motion.retract_velocity` | float | `0.05` | Velocity for linear retraction [m/s] |
| `motion.linear_step_size` | float | `0.005` | Cartesian step size for linear retraction [m] |
| `motion.return_home` | bool | `true` | Return arm to home after retraction |
| `timeouts.navigate_timeout` | float | `60.0` | NavigateToAddress action timeout [s] |
| `timeouts.extract_timeout` | float | `30.0` | SCARA extraction timeout [s] |
| `sensor.mock` | bool | `true` | Use mock sensor (always returns true) |

### SCARA Workspace Constraints

The approach X offset exists because the SCARA arm has narrow shoulder joint limits (±57° / ±0.995 rad). Without the offset, the approach at pure Y direction (90° from +X) sits at the shoulder limit and a pure-Y retract becomes impossible.

With `approach_x_offset_m = 0.20`:
- Approach point `(0.20, 0.22)`: angle 47.7° — comfortably within limits
- Retract endpoint `(0.20, 0.00)`: angle 0° — well within limits
- All intermediate retract waypoints stay within joint limits

---

## Usage

### Command Line

```bash
# Extract box from left side, cabinet 2, row 2, column 0
ros2 action send_goal /extract_box ros_control/action/ExtractBox \
  "{box: {side: 'left', cabinet_num: 2, row: 2, column: 0}}" --feedback

# Extract box from right side, cabinet 0, row 1, column 0
ros2 action send_goal /extract_box ros_control/action/ExtractBox \
  "{box: {side: 'right', cabinet_num: 0, row: 1, column: 0}}" --feedback
```

### Python Client

```python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from ros_control.action import ExtractBox
from ros_control.msg import Address


class ExtractBoxClient(Node):
    def __init__(self):
        super().__init__('extract_box_client')
        self.client = ActionClient(self, ExtractBox, '/extract_box')

    def send_goal(self, side, cabinet_num, row, column):
        self.client.wait_for_server()

        goal = ExtractBox.Goal()
        goal.box.side = side
        goal.box.cabinet_num = cabinet_num
        goal.box.row = row
        goal.box.column = column

        future = self.client.send_goal_async(
            goal,
            feedback_callback=self.feedback_callback
        )
        future.add_done_callback(self.goal_response_callback)

    def feedback_callback(self, feedback_msg):
        fb = feedback_msg.feedback
        self.get_logger().info(
            f'Phase: {fb.current_phase}, Progress: {fb.progress_percentage:.1f}%'
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
                f'Box {result.box_id} extracted in {result.execution_time:.1f}s'
            )
        else:
            self.get_logger().error(f'Failed: {result.message}')


def main():
    rclpy.init()
    client = ExtractBoxClient()
    client.send_goal('left', 2, 1, 0)
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
3. `extract_box_server` starts (triggered by `scara_controller` exit)

The server is wrapped with `IfCondition(use_scara)` — it only launches when SCARA is enabled.

### Run Standalone

```bash
ros2 run ros_control extract_box_server.py
```

Requires `navigate_to_address_server` and `scara_controller` to be running.

---

## Error Handling

| Error | Phase | Result |
|-------|-------|--------|
| NavigateToAddress server not available | navigating | success=False, message="Navigation failed: ..." |
| Navigation failed | navigating | success=False, message="Navigation failed: ..." |
| SCARA motion failed (IK, joint limits) | extracting | success=False, message="Extraction failed: ..." |
| Sensor not triggered | done | success=True, box_extracted=False, message="Box not detected by sensor" |
| Cancellation | any | Cancel forwarded to active sub-goals |

### Cancellation

If ExtractBox is cancelled:
1. If in "navigating" phase — cancel NavigateToAddress goal
2. If in "extracting" phase — ScaraClient motion completes current step (safe stop), then return
3. Set result.success = False

---

## Implementation Notes

### box_extracted Sensor (Mock)

For now, `box_extracted` is always `True` when the SCARA sequence completes successfully:

```python
def _check_box_sensor(self) -> bool:
    if self.config['sensor']['mock']:
        return True
    # Future: read from sensor topic/service
    return False
```

### Configuration Loading

The server loads configuration from `extract_box_config.yaml` with deep-merge against built-in defaults. This means any subset of parameters can be overridden in the YAML file; unspecified parameters use defaults.

---

## Files

| File | Description |
|------|-------------|
| `action/ExtractBox.action` | Action definition |
| `msg/Address.msg` | Cabinet cell address message |
| `src/extract_box_server.py` | Main node implementation |
| `config/extract_box_config.yaml` | Default configuration |
| `launch/extract_box_server.launch.py` | Standalone launch file |

## See Also

- [navigate_to_address_server.md](navigate_to_address_server.md) — Platform navigation (used by ExtractBox)
- [move_joint_group_server.md](move_joint_group_server.md) — Joint movement action server
- [package_structure.md](package_structure.md) — Full package documentation
