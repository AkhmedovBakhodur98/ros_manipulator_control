# ReturnBox Action Server

Orchestrates returning a box to a cabinet cell by coordinating platform navigation (NavigateToAddress) and SCARA arm manipulation (ScaraClient). This is the **reverse operation of ExtractBox**.

## Overview

The ReturnBox action server provides a high-level interface for returning a box to a specific cabinet cell. It takes a logical address and box ID, navigates the platform, then uses the SCARA arm to physically push the box back into the cabinet.

**Dependencies:**
- `NavigateToAddress` action — moves the platform to the target cell
- `ScaraClient` library (`scara_control`) — controls the SCARA arm for box return
- `tf2_ros` — TF2 listener (reserved for future use)

**Condition:** Only runs when SCARA is enabled (`use_scara:=true`).

## Execution Flow

```
+-------------------------------------------------------------+
|                      ReturnBox Action                       |
+-------------------------------------------------------------+
|  1. Navigate to Cell    --> /navigate_to_address action     |
|         |                   (platform moves to X, Z)        |
|                             Phase: "navigating" (0-40%)     |
|                                                             |
|  2. Return with SCARA   --> ScaraClient methods             |
|         |                   (position, push, disengage)     |
|                             Phase: "returning" (40-90%)     |
|                                                             |
|  3. Verify & Complete   --> Check sensor (mock for now)     |
|                             Generate returned_to_address    |
|                             Phase: "done" (90-100%)         |
+-------------------------------------------------------------+
```

### Step Details

**Step 1 — Navigate (0-40%)**
Send NavigateToAddress goal with the address from ReturnBox goal. Relay progress from NavigateToAddress feedback (0.0-1.0) mapped to 0-40% range. If navigation fails, abort immediately.

**Step 2 — Return with SCARA (40-90%)**
Seven-step hook-based return using `ScaraClient` (reverse of ExtractBox extraction):

```
SCARA RETURN SEQUENCE (side view)

    cabinet wall
        |
        |  +-------+ box (on platform)
        |  |       |
        |  |  +-+  |         1. ROTATE     wrist -> +/-90 (hook orientation)
        |  |  |h|  |         2. RAISE Z    ^ above box (+0.10m) -- hook clears box
        |  |  |o|  |         3. POSITION   arm to push-start (behind box)
        |  |  |o|  |         4. LOWER Z    v hook engages handle plate (-0.10m)
        |  |  |k|  |         5. PUSH       -> push box into cabinet (linear, with flip)
        |  +--+-+--+         6. RAISE Z    ^ disengage hook (+0.03m)
              -> into cabinet  7. HOME       joints home (Z stays raised), then Z home
```

| Sub-step | Progress | ScaraClient Method | Description |
|----------|----------|--------------------|-------------|
| 2a. Rotate wrist | 42% | `move_joints(wrist=+/-pi/2)` | Orient hook (left=+90, right=-90) |
| 2b. Raise Z | 48% | `move_z(current_z + z_above_box)` | Raise hook above box (+0.10m) |
| 2c. Position (push-start) | 55% | `move_to_point(x_offset, -/+overshoot)` | Move behind box (joint-space, safe) |
| 2d. Lower Z | 62% | `move_z(current_z - z_above_box)` | Hook engages handle plate (-0.10m) |
| 2e. Push linear | 72% | `move_linear(x_offset, +/-depth, allow_elbow_flip=True)` | Push box into cabinet. Flip callbacks raise/lower Z |
| 2f. Raise Z | 80% | `move_z(current_z + z_offset)` | Disengage hook above handle plate (+0.03m) |
| 2g. Home | 85% | `move_joints(0,0,0)` then `move_z(0)` | Joints home first (Z stays raised, hook clears plate), then lower Z |

**Key differences from ExtractBox:**
- Step 2b raises by `z_above_box` (0.10m) instead of `z_offset` (0.03m) — must clear entire box
- Step 2c goes to overshoot position (robot-side of box) instead of depth position
- Step 2d lowers by `z_above_box` (0.10m) instead of `z_offset` (0.03m)
- Step 2e PUSHES (towards cabinet) instead of retracting (away from cabinet) — direction reversed
- Step 2f raises by `z_offset` (0.03m) to clear handle plate only (hook exits plate gap)
- Step 2g goes directly home from inside cabinet (Z stays raised so hook doesn't catch plate during joint motion)

**Push direction (opposite of retract):**
```
Push: (x_offset, -/+overshoot) -> (x_offset, +/-(depth + y_inside))
  left side:  Y goes from -overshoot to +depth
  right side: Y goes from +overshoot to -depth
```

**Push-start computation:**
The push-start position is where ExtractBox's retract ended — the overshoot position on the robot side of the box:
```
push_start_x = approach_x_offset_m                    # constant X offset
push_start_y = -/+retract_overshoot_m                 # - for left, + for right
```

**Push-target computation:**
The push-target is the depth position inside the cabinet:
```
push_target_x = approach_x_offset_m                   # constant X offset
push_target_y = +/-(approach_depth_m + y_inside_m)    # + for left, - for right
```

**Elbow flip during push:** Same `move_linear(allow_elbow_flip=True)` with Z raise/lower callbacks, but arm crosses shoulder limit in the opposite direction (elbow_down -> elbow_up).

**Side-dependent behavior:**
- **Left cabinet**: wrist = +pi/2, push from Y=-overshoot to Y=+depth
- **Right cabinet**: wrist = -pi/2, push from Y=+overshoot to Y=-depth

**Design decisions:**
- `move_to_point` for positioning to push-start (joint-space, safer)
- `move_linear` with `allow_elbow_flip=True` for push (straight-line ensures box enters cabinet walls cleanly; elbow flip handles shoulder limit crossing)
- Flip callbacks raise/lower Z around elbow flip — prevents hook collision with box during reconfiguration
- Rotate wrist before raise Z — hook oriented first while arm is at home (safe)
- X offset on push — keeps approach angle within shoulder joint limits
- Home uses `move_joints` + `move_z` instead of `move_home()` — `move_home()` lowers Z first, which would drag the hook through the handle plate

**Step 3 — Verify & Complete (90-100%)**
- Read box return sensor -> `box_extracted` (mock: always `True` for now)
- Generate `returned_to_address` string: `{side[0]}_{cabinet}_{row}_{col}`
  - Example: `l_2_1_0` for side="left", cabinet=2, row=1, col=0

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

### ReturnBox.action

File: `ros_control/action/ReturnBox.action`

```yaml
# Goal
ros_control/Address box       # Target cell address to return box to
string box_id                 # ID of box being returned (e.g. "box_l_2_1_0")
---
# Result
bool success                  # true if box successfully returned
bool box_extracted            # true if box released in storage (sensor)
string returned_to_address    # Address format: "{side[0]}_{cabinet}_{row}_{col}"
float64 execution_time        # Total execution time (seconds)
string message                # Result message
---
# Feedback
string current_phase          # "navigating", "returning", "done"
float32 progress_percentage   # 0-100%
```

### Feedback Phases

| Phase | Progress | Description |
|-------|----------|-------------|
| navigating | 0-40% | NavigateToAddress moving platform to cell |
| returning | 40-90% | SCARA arm positioning, pushing, disengaging |
| done | 90-100% | Sensor check, returned_to_address generation |

### Result: returned_to_address Format

```
{side_letter}_{cabinet_num}_{row}_{column}

Examples:
  side="left",  cabinet=2, row=1, col=0  ->  l_2_1_0
  side="right", cabinet=0, row=3, col=1  ->  r_0_3_1
```

---

## Concurrency Control

### Single-Goal Policy

The server rejects concurrent goals using an `_executing` flag:

```python
def _goal_callback(self, goal_request):
    if self._executing:
        return GoalResponse.REJECT   # "ReturnBox goal rejected -- already executing"
    return GoalResponse.ACCEPT
```

The flag is set to `True` at the start of `execute_callback` and reset in a `finally` block.

### Distributed Lock (SCARA Mutual Exclusion)

Before using the SCARA arm (Phase 2), the server acquires the distributed lock via `ScaraClient.acquire()`. This prevents conflicts when another server (e.g. `ExtractBoxServer`, `PickItemsFromWarehouseServer`) is using the SCARA arm concurrently:

```
execute_callback:
    self._executing = True
    try:
        Phase 1: Navigate (no SCARA, no lock needed)

        acquired = await self.scara.acquire()
        if not acquired:
            return error("SCARA arm is busy")
        try:
            Phase 2: Return with SCARA
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
                    +----------------------+
                    |  ReturnBox Server    |
                    |  (ROS2 Node)        |
                    +------+---------------+
                           |
            +--------------+--------------+
            |              |              |
            v              v              v
  +-----------------+ +------------+ +-----------------+
  | NavigateToAddress| | ScaraClient| | Sensor Interface |
  | (Action Client)  | | (Library)  | | (Mock for now)   |
  +--------+--------+ +-----+------+ +-----------------+
           |                |
           v                v
  +-----------------+ +-----------------------------+
  | MoveJointGroup  | | scara_controller            |
  | (platform X, Z) | | + picker_z_controller       |
  +-----------------+ | + scara_lock_server (lock)  |
                      +-----------------------------+
```

### ROS2 Interfaces Used

| Interface | Type | Direction | Purpose |
|-----------|------|-----------|---------|
| `/return_box` | Action Server | Incoming | This node's action interface |
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

Configuration file: `ros_control/config/return_box_config.yaml`

```yaml
return_box_server:
  ros__parameters:
    hook_grasp:
      wrist_angle_rad: 1.5708       # +/-pi/2 -- hook orientation (sign auto from side)
      z_offset_m: 0.03              # Raise to disengage hook above handle plate
      z_above_box_m: 0.10           # Raise to clear entire box
      approach_depth_m: 0.20        # Depth into cabinet (Y axis)
      approach_x_offset_m: 0.20     # X offset (same as extract)
      y_inside_m: 0.02              # Extra depth inside box edge
      retract_overshoot_m: 0.38     # Push start position (where extract ended)
      z_lower_velocity: 0.05        # Z velocity (m/s)

    motion:
      push_velocity: 0.05           # Linear push velocity (m/s) -- slow for safety
      position_velocity: 0.5        # Joint-space positioning velocity
      linear_step_size: 0.005       # Cartesian step size (m)
      return_home: true             # Arm returns to home after return

    timeouts:
      navigate_timeout: 60.0        # NavigateToAddress timeout (seconds)
      return_timeout: 30.0          # SCARA return timeout (seconds)

    sensor:
      mock: true                    # Use mock sensor (always returns true)
      # topic: "/box_sensor"        # Real sensor topic (for future)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hook_grasp.wrist_angle_rad` | float | `1.5708` | Hook orientation angle (sign auto from side) |
| `hook_grasp.z_offset_m` | float | `0.03` | Raise distance to disengage hook above handle plate [m] |
| `hook_grasp.z_above_box_m` | float | `0.10` | Raise distance to clear entire box [m] |
| `hook_grasp.approach_depth_m` | float | `0.20` | Depth into cabinet [m] |
| `hook_grasp.approach_x_offset_m` | float | `0.20` | X offset to keep approach within shoulder limits [m] |
| `hook_grasp.y_inside_m` | float | `0.02` | Extra depth inside box edge [m] |
| `hook_grasp.retract_overshoot_m` | float | `0.38` | Push start position (where extract ended) [m] |
| `hook_grasp.z_lower_velocity` | float | `0.05` | Z axis velocity [m/s] |
| `motion.push_velocity` | float | `0.05` | Linear push velocity [m/s] |
| `motion.position_velocity` | float | `0.5` | Joint-space positioning velocity |
| `motion.linear_step_size` | float | `0.005` | Cartesian step size for linear push [m] |
| `motion.return_home` | bool | `true` | Return arm to home after push |
| `timeouts.navigate_timeout` | float | `60.0` | NavigateToAddress action timeout [s] |
| `timeouts.return_timeout` | float | `30.0` | SCARA return timeout [s] |
| `sensor.mock` | bool | `true` | Use mock sensor (always returns true) |

---

## Usage

### Command Line

```bash
# Return box to left side, cabinet 2, row 1, column 0
ros2 action send_goal /return_box ros_control/action/ReturnBox \
  "{box: {side: 'left', cabinet_num: 2, row: 1, column: 0}, box_id: 'box_l_2_1_0'}" --feedback

# Return box to right side, cabinet 0, row 1, column 0
ros2 action send_goal /return_box ros_control/action/ReturnBox \
  "{box: {side: 'right', cabinet_num: 0, row: 1, column: 0}, box_id: 'box_r_0_1_0'}" --feedback
```

### Python Client

```python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from ros_control.action import ReturnBox
from ros_control.msg import Address


class ReturnBoxClient(Node):
    def __init__(self):
        super().__init__('return_box_client')
        self.client = ActionClient(self, ReturnBox, '/return_box')

    def send_goal(self, side, cabinet_num, row, column, box_id):
        self.client.wait_for_server()

        goal = ReturnBox.Goal()
        goal.box.side = side
        goal.box.cabinet_num = cabinet_num
        goal.box.row = row
        goal.box.column = column
        goal.box_id = box_id

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
                f'Box returned to {result.returned_to_address} '
                f'in {result.execution_time:.1f}s'
            )
        else:
            self.get_logger().error(f'Failed: {result.message}')


def main():
    rclpy.init()
    client = ReturnBoxClient()
    client.send_goal('left', 2, 1, 0, 'box_l_2_1_0')
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
3. `return_box_server` starts (triggered by `scara_controller` exit)

The server is wrapped with `IfCondition(use_scara)` — it only launches when SCARA is enabled.

### Run Standalone

```bash
ros2 run ros_control return_box_server.py
```

Requires `navigate_to_address_server` and `scara_controller` to be running.

---

## Error Handling

| Error | Phase | Result |
|-------|-------|--------|
| Concurrent goal while executing | goal callback | Goal rejected (GoalResponse.REJECT) |
| SCARA lock not available (arm busy) | returning | success=False, message="SCARA arm is busy" |
| NavigateToAddress server not available | navigating | success=False, message="Navigation failed: ..." |
| Navigation failed | navigating | success=False, message="Navigation failed: ..." |
| SCARA motion failed (IK, joint limits) | returning | success=False, message="Return failed: ..." |
| Sensor not triggered | done | success=True, box_extracted=False, message="Box not detected by sensor in storage" |
| Cancellation | any | Cancel forwarded to active sub-goals |

### Cancellation

If ReturnBox is cancelled:
1. If in "navigating" phase — cancel NavigateToAddress goal
2. If in "returning" phase — ScaraClient motion completes current step (safe stop), then return
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

The server loads configuration from `return_box_config.yaml` with deep-merge against built-in defaults. This means any subset of parameters can be overridden in the YAML file; unspecified parameters use defaults.

### Relationship to ExtractBox

ReturnBox is the exact inverse of ExtractBox. The two operations are symmetric:

| Aspect | ExtractBox | ReturnBox |
|--------|-----------|-----------|
| Phase 2 name | "extracting" | "returning" |
| Step 2b Z raise | +z_offset (0.03m) | +z_above_box (0.10m) |
| Step 2c target | depth position (inside cabinet) | overshoot position (robot side) |
| Step 2d Z lower | -z_offset (0.03m) | -z_above_box (0.10m) |
| Step 2e direction | retract (away from cabinet) | push (towards cabinet) |
| Step 2f Z raise | +z_above_box (0.10m) | +z_offset (0.03m) |
| Elbow flip | elbow_up -> elbow_down | elbow_down -> elbow_up |

---

## Files

| File | Description |
|------|-------------|
| `action/ReturnBox.action` | Action definition |
| `msg/Address.msg` | Cabinet cell address message |
| `src/return_box_server.py` | Main node implementation |
| `config/return_box_config.yaml` | Default configuration |

## See Also

- [extract_box_server.md](extract_box_server.md) — Box extraction (reverse of ReturnBox)
- [navigate_to_address_server.md](navigate_to_address_server.md) — Platform navigation (used by ReturnBox)
- [move_joint_group_server.md](move_joint_group_server.md) — Joint movement action server
- [package_structure.md](package_structure.md) — Full package documentation
