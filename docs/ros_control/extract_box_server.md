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
Seven-step hook-based extraction using `ScaraClient`:

```
SCARA EXTRACTION SEQUENCE (side view)

    cabinet wall
        │
        │  ┌───────┐ box
        │  │       │
        │  │  ┌─┐  │         1. ROTATE     wrist → ±90° (hook orientation)
        │  │  │h│  │         2. RAISE Z    ↑ above handle plate (+0.03m)
        │  │  │a│  │         3. APPROACH   arm extends into cabinet
        │  │  │n│  │         4. LOWER Z    ↓ hook drops into gap (-0.03m)
        │  │  │d│  │         5. RETRACT    ← pull box out (pure Y linear)
        │  │  │l│  │         6. RAISE Z    ↑ disengage hook above box (+0.10m)
        │  │  │e│  │         7. HOME       arm returns to home (optional)
        │  └──┴─┴──┘
        │
              ← SCARA arm
```

| Sub-step | Progress | ScaraClient Method | Description |
|----------|----------|--------------------|-------------|
| 2a. Rotate wrist | 42% | `move_joints(wrist=±π/2)` | Orient hook (left=+90°, right=-90°) |
| 2b. Raise Z | 48% | `move_z(current_z + z_offset)` | Raise picker above handle plate (+0.03m) |
| 2c. Approach | 55% | `move_to_point(x, y)` | Extend arm into cabinet (joint-space motion) |
| 2d. Lower Z | 65% | `move_z(current_z - z_offset)` | Hook drops into gap under handle plate (-0.03m) |
| 2e. Retract | 75% | `move_linear(x, y, allow_elbow_flip=True, on_before_flip, on_after_flip)` | Pull box out — raises Z before elbow flip, lowers after |
| 2f. Raise Z | 80% | `move_z(current_z + z_above_box)` | Disengage hook — raise above box before going home |
| 2g. Home | 85% | `move_joints(0,0,0)` then `move_z(0)` | Arm joints home first (Z stays raised), then lower Z |

**Approach target computation:**
The approach target is computed in SCARA base frame. After navigation aligns the platform with the cell, the SCARA only needs to reach sideways (±Y) into the cabinet:

```
approach_x = approach_x_offset_m                          # constant X offset
approach_y = ±(approach_depth_m + y_inside_m)             # + for left, - for right
```

The `approach_x_offset_m` (default 0.20m) keeps the approach angle within the shoulder joint limits (±57°) and enables a pure-Y linear retract at constant X.

**Retract (Y-axis linear motion with overshoot and elbow flip):**
The retract keeps TCP X coordinate constant and pulls past Y=0 by `retract_overshoot_m` to fully extract the box:

```
retract: (approach_x, approach_y) → (approach_x, ∓retract_overshoot_m)
         left side: Y goes from +depth to -overshoot
         right side: Y goes from -depth to +overshoot
```

Total retract distance = `approach_depth_m + y_inside_m + retract_overshoot_m` (default: 0.22 + 0.38 = 0.60m, matching standard box length).

The retract uses `move_linear(allow_elbow_flip=True)` because the long retract path crosses the shoulder joint limit (±57°). At the limit boundary, the arm automatically flips elbow configuration (elbow_up → elbow_down) and continues. Before the flip, Z is raised by `z_above_box_m` (0.10m) to clear the box, and lowered back after the flip. This prevents the hook from colliding with the box during the elbow reconfiguration.

The `move_linear` method interpolates Cartesian waypoints (every `linear_step_size` meters) and computes IK for each, then sends a multi-point trajectory to the controller.

**Side-dependent behavior:**
- **Left cabinet**: wrist = +π/2, approach_y = +depth, retract_y = -overshoot
- **Right cabinet**: wrist = -π/2, approach_y = -depth, retract_y = +overshoot

**Design decisions:**
- `move_to_point` for approach (joint-space, safer for entry into cabinet)
- `move_linear` with `allow_elbow_flip=True` for retraction (straight-line ensures box clears cabinet walls; elbow flip handles shoulder limit crossing)
- Flip callbacks raise/lower Z around elbow flip — prevents hook collision with box during reconfiguration
- Rotate wrist before raise Z — hook oriented first while arm is at home (safe)
- X offset on approach — keeps approach angle within shoulder joint limits
- Home uses `move_joints` + `move_z` instead of `move_home()` — `move_home()` lowers Z first, which would drag the hook through the extracted box

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

## Concurrency Control

### Single-Goal Policy

The server rejects concurrent goals using an `_executing` flag:

```python
def _goal_callback(self, goal_request):
    if self._executing:
        return GoalResponse.REJECT   # "ExtractBox goal rejected — already executing"
    return GoalResponse.ACCEPT
```

The flag is set to `True` at the start of `execute_callback` and reset in a `finally` block.

### Distributed Lock (SCARA Mutual Exclusion)

Before using the SCARA arm (Phase 2), the server acquires the distributed lock via `ScaraClient.acquire()`. This prevents conflicts when another server (e.g. `PickItemsFromWarehouseServer`) is using the SCARA arm concurrently:

```
execute_callback:
    self._executing = True
    try:
        Phase 1: Navigate (no SCARA, no lock needed)

        acquired = await self.scara.acquire()
        if not acquired:
            return error("SCARA arm is busy")
        try:
            Phase 2: Extract with SCARA
        finally:
            await self.scara.release()

        Phase 3: Verify
    finally:
        self._executing = False
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
  └─────────────────┘ │ + scara_lock_server (lock)  │
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
| `/scara_lock/acquire` | Service Client | Outgoing | Via ScaraClient (distributed lock) |
| `/scara_lock/release` | Service Client | Outgoing | Via ScaraClient (distributed lock) |

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
      z_above_box_m: 0.10            # Raise distance to clear entire box (overhook disengage)
      approach_depth_m: 0.20        # How far arm reaches into cabinet (Y axis)
      approach_x_offset_m: 0.20     # X offset for approach — keeps arm within shoulder limits
      y_inside_m: 0.02              # Extra depth inside box edge
      retract_overshoot_m: 0.38    # How far past Y=0 to retract (full box extraction)
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
| `hook_grasp.z_above_box_m` | float | `0.10` | Raise distance to clear entire box for overhook disengage [m] |
| `hook_grasp.approach_depth_m` | float | `0.20` | How far arm reaches into cabinet [m] |
| `hook_grasp.approach_x_offset_m` | float | `0.20` | X offset to keep approach within shoulder limits [m] |
| `hook_grasp.y_inside_m` | float | `0.02` | Extra depth inside box edge [m] |
| `hook_grasp.retract_overshoot_m` | float | `0.38` | How far past Y=0 to retract for full extraction [m] |
| `hook_grasp.z_lower_velocity` | float | `0.05` | Z axis velocity [m/s] |
| `motion.approach_velocity` | float | `0.5` | Velocity scaling for approach |
| `motion.retract_velocity` | float | `0.05` | Velocity for linear retraction [m/s] |
| `motion.linear_step_size` | float | `0.005` | Cartesian step size for linear retraction [m] |
| `motion.return_home` | bool | `true` | Return arm to home after retraction |
| `timeouts.navigate_timeout` | float | `60.0` | NavigateToAddress action timeout [s] |
| `timeouts.extract_timeout` | float | `30.0` | SCARA extraction timeout [s] |
| `sensor.mock` | bool | `true` | Use mock sensor (always returns true) |

### SCARA Workspace Constraints

The approach X offset exists because the SCARA arm has narrow shoulder joint limits (±57° / ±0.995 rad). Without the offset, the approach at pure Y direction (90° from +X) sits at the shoulder limit and retraction becomes impossible.

With `approach_x_offset_m = 0.20` and `retract_overshoot_m = 0.38`:
- Approach point `(0.20, 0.22)`: shoulder angle 47.7° — comfortably within limits
- Retract path crosses shoulder limit at `Y ≈ -0.10` (shoulder = -57°)
- Elbow flip at the limit boundary switches from elbow_up to elbow_down
- After flip: shoulder angle becomes ~+22° — well within limits
- Retract endpoint `(0.20, -0.38)`: reachable in elbow_down configuration
- Total retract travel: 0.22 + 0.38 = **0.60m** (matches standard box length)

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
| Concurrent goal while executing | goal callback | Goal rejected (GoalResponse.REJECT) |
| SCARA lock not available (arm busy) | extracting | success=False, message="SCARA arm is busy" |
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

- [return_box_server.md](return_box_server.md) — Box return (reverse of ExtractBox)
- [navigate_to_address_server.md](navigate_to_address_server.md) — Platform navigation (used by ExtractBox)
- [move_joint_group_server.md](move_joint_group_server.md) — Joint movement action server
- [package_structure.md](package_structure.md) — Full package documentation
