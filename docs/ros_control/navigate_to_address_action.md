# NavigateToAddress Action Server - Architectural Design

## Overview

The `NavigateToAddress` action server translates a logical cabinet address (side, cabinet, row, column) into physical joint positions and moves the manipulator platform to that position. It controls only the platform joints (rail + vertical lift), not the arm or gripper.

**Action name**: `/navigate_to_address`
**Package**: `ros_control`
**Type**: `ros_control/action/NavigateToAddress`

---

## Requirements

1. **Address input**: Accept logical address (side, cabinet_num, row, column)
2. **Position resolution**: Convert address to physical (X, Z) coordinates using configurable cabinet geometry
3. **Platform movement**: Move `base_main_frame_joint` (X) and `main_frame_selector_frame_joint` (Z) to computed positions
4. **Configurable geometry**: Cabinet layout defined in YAML config with per-cell offsets
5. **Input validation**: Reject out-of-range addresses before moving
6. **Result**: Return actual position, error, and success/failure status

---

## Action Definition

### `action/NavigateToAddress.action`

```yaml
# Goal
# Сторона установки шкафа: "left" или "right"
string side
# Номер шкафа (0-4)
uint8 cabinet_num
# Ряд внутри шкафа (0-N)
uint8 row
# Колонка внутри шкафа (0-1)
uint8 column
---
# Result
# true если платформа достигла позиции в пределах допуска
bool success
# Позиция концевого эффектора [x, y, z] в мировой системе координат
geometry_msgs/Point final_position
# Максимальная ошибка позиции среди всех суставов
float64 position_error
# Сообщение о результате
string message
---
# Feedback
# Процент выполнения (0.0 - 1.0)
float64 progress
# Текущая фаза: "validating", "computing", "moving_rail", "moving_lift", "done"
string current_phase
```

**Design Decisions**:
- `geometry_msgs/Point` for `final_position` provides standard ROS2 type compatibility
- `side` is stored in the goal for full address context; it does **not** affect platform position for now. Reserved for future use (e.g., arm reaching direction, per-side geometry)
- Feedback includes `current_phase` for observability during movement

---

## Configuration

### `config/navigate_to_address_config.yaml`

```yaml
navigate_to_address:
  # ============================================================
  # Cabinet geometry
  # ============================================================
  cabinets:
    num_cabinets: 5           # Number of cabinets per side (0-4)
    rows_per_cabinet: 4       # Number of rows per cabinet (0-3)
    columns_per_row: 2        # Number of columns per row (0-1)

  # ============================================================
  # X axis (rail) - base_main_frame_joint
  # ============================================================
  rail:
    first_cabinet_x: 0.2     # [TEST] X position of cabinet_0, column_0 center [m]
    cabinet_spacing: 0.75     # [TEST] X distance between adjacent cabinet centers [m]
    column_width: 0.35        # [TEST] X distance between column_0 and column_1 [m]

  # ============================================================
  # Z axis (vertical lift) - main_frame_selector_frame_joint
  # ============================================================
  lift:
    first_row_z: 0.1           # [TEST] Z position of row_0 center [m]
    row_height: 0.30           # [TEST] Z distance between adjacent rows [m]

  # ============================================================
  # Fine-tuning offsets (applied after formula computation)
  # ============================================================
  offsets:
    x: 0.0                    # Global X correction [m]
    z: 0.0                    # Global Z correction [m]

  # ============================================================
  # Movement parameters
  # ============================================================
  movement:
    max_velocity_x: 1.0       # Max rail velocity [m/s]
    max_velocity_z: 0.8       # Max lift velocity [m/s]

  # ============================================================
  # Tolerances and timeouts
  # ============================================================
  position_tolerance: 0.005   # Acceptable position error [m]
```

**Position formulas**:
```
X = first_cabinet_x + cabinet_num * cabinet_spacing + column * column_width + offsets.x
Z = first_row_z + row * row_height + offsets.z
```

---

## Execution Flow

```
┌─────────────────────────────────────────────────────────────┐
│                 NavigateToAddress Action                      │
│                                                              │
│  1. VALIDATE INPUT                                          │
│     ├─ side in ["left", "right"]                            │
│     ├─ cabinet_num < num_cabinets                           │
│     ├─ row < rows_per_cabinet                               │
│     └─ column < columns_per_row                             │
│                                                              │
│  2. COMPUTE TARGET POSITION                                 │
│     ├─ X = first_cabinet_x                                  │
│     │     + cabinet_num * cabinet_spacing                    │
│     │     + column * column_width                            │
│     │     + offsets.x                                        │
│     └─ Z = first_row_z + row * row_height + offsets.z       │
│                                                              │
│  3. VALIDATE JOINT LIMITS                                   │
│     ├─ X in [0.0, 4.0] (base_main_frame_joint)             │
│     └─ Z in [-0.01, 1.5] (main_frame_selector_frame_joint) │
│                                                              │
│  4. MOVE PLATFORM                                           │
│     └─► Call /move_joint_group action                       │
│         joints: [base_main_frame_joint,                     │
│                  main_frame_selector_frame_joint]            │
│         positions: [X, Z]                                   │
│         max_velocity: [max_velocity_x, max_velocity_z]      │
│                                                              │
│     MoveJointGroup handles:                                 │
│       - Execution strategy (simultaneous/coordinated)       │
│       - Timeout monitoring                                  │
│       - Position tolerance checking                         │
│       - Feedback (progress_percentage, current_positions)   │
│                                                              │
│  5. RELAY RESULT from MoveJointGroup                        │
│     ├─ final_position: Point(x, y=0, z) from final_position│
│     ├─ position_error: from move result position_error      │
│     ├─ success: from move result success                    │
│     └─ message: from move result message                    │
└─────────────────────────────────────────────────────────────┘
```

### Step Details

| Step | Action | Description |
|------|--------|-------------|
| 1. Validate address | Internal | Check address bounds against config |
| 2. Compute position | Internal | Apply formula to get (X, Z) |
| 3. Validate limits | Internal | Check (X, Z) within URDF joint limits |
| 4. Move | `/move_joint_group` Action | Move platform joints to target |
| 5. Relay result | Internal | Map MoveJointGroup result to NavigateToAddress result |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Client Application                      │
│         (sends NavigateToAddress goal with address)          │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│            NavigateToAddress Action Server                    │
│                /navigate_to_address                          │
│                                                              │
│  - Loads cabinet geometry from YAML                         │
│  - Validates address                                        │
│  - Computes (X, Z) from address                             │
│  - Delegates movement to move_joint_group                   │
│  - Relays feedback                                          │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│               /move_joint_group Action Client                │
│                                                              │
│  joints: [base_main_frame_joint,                            │
│           main_frame_selector_frame_joint]                   │
│  positions: [X, Z]                                          │
│  max_velocity: [vel_x, vel_z]                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Controlled Joints

| Joint | Axis | Range | Determined by |
|-------|------|-------|---------------|
| `base_main_frame_joint` | X (prismatic) | 0.0 - 4.0 m | `cabinet_num` + `column` |
| `main_frame_selector_frame_joint` | Z (prismatic) | -0.01 - 1.5 m | `row` |

**Not controlled by this node**: gripper joints, picker joints, SCARA joints.

---

## Dependencies

### Existing Components Used

| Component | Interface | Purpose |
|-----------|-----------|---------|
| `move_joint_group_server` | Action `/move_joint_group` | Move platform joints |

### New Files to Create

| File | Purpose |
|------|---------|
| `action/NavigateToAddress.action` | Action definition |
| `config/navigate_to_address_config.yaml` | Cabinet geometry configuration |
| `src/navigate_to_address_server.py` | Action server implementation |

**Note**: No separate launch file. This node will be added to `manipulator_bringup.launch.py` later.

### Package Dependencies

- `rclpy` - ROS2 Python client
- `ros_control` - MoveJointGroup action (same package)
- `geometry_msgs` - Point message for final_position

---

## Error Handling

### Fail-Fast Strategy

If any step fails, the action:
1. Cancels any active move_joint_group goal
2. Returns failure result with error message
3. Does NOT attempt recovery

### Error Cases

| Error | Handling | Message |
|-------|----------|---------|
| Invalid side | Abort, return failure | `"Invalid side: '{side}'. Expected 'left' or 'right'"` |
| cabinet_num out of range | Abort, return failure | `"cabinet_num {n} out of range [0, {max})"` |
| row out of range | Abort, return failure | `"row {n} out of range [0, {max})"` |
| column out of range | Abort, return failure | `"column {n} out of range [0, {max})"` |
| Computed X outside joint limits | Abort, return failure | `"Computed X={x} outside joint limits [0.0, 4.0]"` |
| Computed Z outside joint limits | Abort, return failure | `"Computed Z={z} outside joint limits [-0.01, 1.5]"` |
| Move failed | Abort, return failure | Relay message from move_joint_group result |
| Action preempted | Cancel sub-goal, return canceled | `"Navigation canceled"` |
| Config file missing | Fail on startup | `"Config file not found"` |

---

## Feedback Messages

| Phase | `current_phase` | `progress` |
|-------|-----------------|------------|
| Validating input | `"validating"` | 0.0 |
| Computing position | `"computing"` | 0.05 |
| Moving platform | `"moving"` | 0.05 - 0.95 (relayed from move_joint_group) |
| Done | `"done"` | 1.0 |

---

## Implementation Notes

### Position Computation

```python
def compute_position(self, goal):
    cfg = self.config
    x = (cfg['rail']['first_cabinet_x']
         + goal.cabinet_num * cfg['rail']['cabinet_spacing']
         + goal.column * cfg['rail']['column_width']
         + cfg['offsets']['x'])
    z = (cfg['lift']['first_row_z']
         + goal.row * cfg['lift']['row_height']
         + cfg['offsets']['z'])
    return x, z
```

### Movement via MoveJointGroup

NavigateToAddress delegates all movement to `/move_joint_group`. MoveJointGroup handles execution strategy, timeout, position tolerance, and progress monitoring internally.

```python
move_goal = MoveJointGroup.Goal()
move_goal.joint_names = [
    'base_main_frame_joint',
    'main_frame_selector_frame_joint'
]
move_goal.target_positions = [x, z]
move_goal.max_velocity = [
    cfg['movement']['max_velocity_x'],
    cfg['movement']['max_velocity_z']
]
```

### Result Relay from MoveJointGroup

MoveJointGroup result provides: `success`, `final_position[]`, `position_error`, `execution_time`, `message`. NavigateToAddress maps these to its own result:

```python
from geometry_msgs.msg import Point

# MoveJointGroup result -> NavigateToAddress result
move_result = goal_handle.get_result()

result = NavigateToAddress.Result()
result.success = move_result.success
result.position_error = move_result.position_error
result.message = move_result.message
result.final_position = Point()
result.final_position.x = move_result.final_position[0]  # base_main_frame_joint
result.final_position.y = 0.0  # Platform does not move in Y
result.final_position.z = move_result.final_position[1]  # main_frame_selector_frame_joint
```

**Note**: `final_position.y` is always 0.0 because this node only moves the platform in X and Z. The Y component is reserved for future use (e.g., when arm movement is added).

---

## Usage (After Implementation)

### Launch

```bash
# Full system (navigate_to_address will be added to this launch later)
ros2 launch manipulator_bringup manipulator_bringup.launch.py
```

### Call Action

```bash
# Navigate to left side, cabinet 2, row 1, column 0
ros2 action send_goal /navigate_to_address ros_control/action/NavigateToAddress \
  "{side: 'left', cabinet_num: 2, row: 1, column: 0}"
```

### Monitor Feedback

```bash
ros2 action send_goal /navigate_to_address ros_control/action/NavigateToAddress \
  "{side: 'left', cabinet_num: 2, row: 1, column: 0}" --feedback
```

---

## File Structure (After Implementation)

```
src/ros_control/
├── action/
│   ├── MoveJointGroup.action
│   ├── GetContainer.action
│   ├── PlaceContainer.action
│   └── NavigateToAddress.action      # NEW
├── config/
│   ├── move_joint_group_config.yaml
│   ├── get_container_config.yaml
│   └── navigate_to_address_config.yaml  # NEW
├── src/
│   ├── move_joint_group_server.py
│   ├── gripper_service.py
│   ├── get_container_server.py
│   ├── place_container_server.py
│   └── navigate_to_address_server.py   # NEW
└── launch/
    └── move_joint_group_server.launch.py
```

---

## Resolved Questions

1. ~~**Side handling**~~ -- `side` does **not** affect platform position for now. Reserved for future use.
2. ~~**Movement strategy**~~ -- Delegated to `MoveJointGroup` which handles execution strategy (simultaneous/coordinated), timeout, and position monitoring.
3. ~~**Cabinet geometry values**~~ -- Using **test dimensions** for now. Marked with `[TEST]` in config. Will be replaced with real measurements later.
4. ~~**Launch integration**~~ -- No separate launch file. Node will be added to `manipulator_bringup.launch.py` later.
5. ~~**Joint limits validation**~~ -- NavigateToAddress **validates** computed positions against URDF joint limits before sending to MoveJointGroup (MoveJointGroup does not check limits itself).

## Open Questions

All questions resolved.

---

## Related Documentation

- **MoveJointGroup Server**: `docs/ros_control/move_joint_group_server.md`
- **GetContainer Action**: `docs/ros_control/get_container_action.md`
- **Manipulator Parameters**: `src/manipulator_description/config/manipulator_params.yaml`
- **Controllers**: `src/manipulator_description/config/manipulator_controllers.yaml`
