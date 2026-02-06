# GetContainer Action Server - Architectural Design

## Overview

The `GetContainer` action server provides a high-level interface for picking up containers. It orchestrates the manipulator movement and gripper control to execute a complete pick operation.

**Action name**: `/get_container`
**Package**: `ros_control`
**Type**: `ros_control/action/GetContainer`

---

## Requirements (MVP)

1. **Simple trigger**: Client calls action without parameters
2. **Pick operation**: Move to container, grasp, lift
3. **Result**: Return success/failure to client
4. **Configurable**: Container position and lift distance via YAML

---

## Action Definition

### `action/GetContainer.action`

```yaml
# Goal (empty for MVP - just trigger)
---
# Result
bool success
string message
float64 execution_time
---
# Feedback
string current_step        # "moving_to_container", "lowering_picker", "closing_gripper", "lifting"
float32 progress_percentage
```

**Design Decision**: Empty goal for MVP simplicity. Future versions can add container ID selection.

---

## Configuration

### `config/get_container_config.yaml`

```yaml
get_container:
  # Container grasp position (joint values)
  container_position:
    base_main_frame_joint: 1.5            # X-axis rail position [m]
    main_frame_selector_frame_joint: 0.8  # Z-axis selector height at grasp [m]

  # Lift movement
  lift_height: 0.20     # Distance to lift after grasp [m]

  # Timing
  timeouts:
    move_timeout: 30.0      # Timeout for move operations [s]
    gripper_timeout: 5.0    # Timeout for gripper operations [s]

  # Tolerances
  position_tolerance: 0.01  # Position tolerance [m]
```

**Design Decision**:
- Container position and lift height are configurable here
- Gripper open/close widths are configured separately in `gripper_config.yaml`
- GetContainer just calls `/gripper/open` and `/gripper/close` Trigger services

---

## Execution Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    GetContainer Action                       │
│                                                              │
│  1. OPEN GRIPPER                                            │
│     └─► Call /gripper/open service (std_srvs/Trigger)       │
│                                                              │
│  2. MOVE TO CONTAINER (grasp position)                      │
│     └─► Call /move_joint_group action                       │
│         joints: [base_main_frame, main_frame_selector]      │
│         positions: from config                               │
│                                                              │
│  3. CLOSE GRIPPER                                           │
│     └─► Call /gripper/close service (std_srvs/Trigger)      │
│                                                              │
│  4. LIFT (raise selector)                                   │
│     └─► Call /move_joint_group action                       │
│         joint: main_frame_selector_frame_joint              │
│         position: container_z - lift_height                 │
│                                                              │
│  5. RETURN SUCCESS                                          │
└─────────────────────────────────────────────────────────────┘
```

### Step Details

| Step | Interface | Type | Description |
|------|-----------|------|-------------|
| 1. Open gripper | `/gripper/open` | Service (Trigger) | Prepare jaws for grasp |
| 2. Move to container | `/move_joint_group` | Action | Move to grasp position |
| 3. Close gripper | `/gripper/close` | Service (Trigger) | Grasp container |
| 4. Lift | `/move_joint_group` | Action | Raise selector to lift container |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Client Application                      │
│              (sends GetContainer goal)                       │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│               GetContainer Action Server                     │
│                  /get_container                              │
│                                                              │
│  - Loads config from YAML                                   │
│  - Orchestrates pick sequence                               │
│  - Publishes feedback                                       │
│  - Handles errors (fail-fast)                               │
└───────────┬─────────────────────────────────┬───────────────┘
            │                                 │
            ▼                                 ▼
┌───────────────────────┐         ┌───────────────────────────┐
│  /move_joint_group    │         │  Gripper Services         │
│  Action Client        │         │  Service Clients          │
│                       │         │                           │
│  - Move to container  │         │  - /gripper/open (Trigger)│
│  - Lift after grasp   │         │  - /gripper/close(Trigger)│
└───────────────────────┘         └───────────────────────────┘
```

---

## Dependencies

### Existing Components Used

| Component | Interface | Purpose |
|-----------|-----------|---------|
| `move_joint_group_server` | Action `/move_joint_group` | Move manipulator joints |
| `gripper_service` | Service `/gripper/open` | Open gripper jaws |
| `gripper_service` | Service `/gripper/close` | Close gripper jaws |

### New Files to Create

| File | Purpose |
|------|---------|
| `action/GetContainer.action` | Action definition |
| `config/get_container_config.yaml` | Configuration |
| `src/get_container_server.py` | Action server implementation |

### Package Dependencies

- `rclpy` - ROS2 Python client
- `ros_control` - MoveJointGroup action (same package)
- `sensor_msgs` - JointState for monitoring

---

## Error Handling

### Fail-Fast Strategy

If any step fails, the action:
1. Cancels any active sub-goals
2. Returns failure result with error message
3. Does NOT attempt recovery (MVP simplicity)

### Error Cases

| Error | Handling |
|-------|----------|
| Move timeout | Abort, return failure |
| Gripper timeout | Abort, return failure |
| Action preempted | Cancel sub-goals, return canceled |
| Invalid config | Fail on startup with clear error |

---

## Feedback Messages

| Step | `current_step` | `progress_percentage` |
|------|----------------|----------------------|
| Opening gripper | `"opening_gripper"` | 0-15% |
| Moving to container | `"moving_to_container"` | 15-50% |
| Closing gripper | `"closing_gripper"` | 50-70% |
| Lifting | `"lifting"` | 70-100% |

---

## Implementation Notes

### Gripper Interface

**Decision**: Use existing `gripper_service.py` services:
- `/gripper/open` - `std_srvs/srv/Trigger`
- `/gripper/close` - `std_srvs/srv/Trigger`

Gripper positions are configured in `gripper_config.yaml` (separate from GetContainer config).

### State Machine

```
IDLE ─► OPENING_GRIPPER ─► MOVING_TO_CONTAINER ─► CLOSING_GRIPPER ─► LIFTING ─► SUCCESS
```

---

## Future Extensions (Post-MVP)

1. **Multiple containers**: Add container ID to goal
   ```yaml
   # Goal
   string container_id  # e.g., "container_1", "container_2"
   ```

2. **Container positions list**:
   ```yaml
   containers:
     container_1:
       position: [1.5, 0.8, 0.0]
       gripper_width: 0.15
     container_2:
       position: [2.5, 0.8, 0.0]
       gripper_width: 0.12
   ```

3. **Place container action**: `/place_container`

4. **Approach position**: Add safe approach before lowering

5. **Grasp verification**: Check gripper force/position to verify grasp

---

## Usage (After Implementation)

### Launch

```bash
# Start full system with get_container server
ros2 launch manipulator_bringup manipulator_bringup.launch.py
```

### Call Action

```bash
# Trigger pick operation
ros2 action send_goal /get_container ros_control/action/GetContainer "{}"
```

### Monitor Feedback

```bash
ros2 action send_goal /get_container ros_control/action/GetContainer "{}" --feedback
```

---

## File Structure (After Implementation)

```
src/ros_control/
├── action/
│   ├── MoveJointGroup.action
│   └── GetContainer.action        # NEW
├── config/
│   ├── move_joint_group_config.yaml
│   └── get_container_config.yaml  # NEW
├── src/
│   ├── move_joint_group_server.py
│   ├── gripper_service.py
│   └── get_container_server.py    # NEW
└── launch/
    ├── move_joint_group_server.launch.py
    └── get_container_server.launch.py  # NEW (or add to existing)
```

---

## Open Questions

1. ~~**Gripper interface**: Confirm using existing `gripper_service.py`~~ ✓ Resolved - use `/gripper/open` and `/gripper/close` Trigger services
2. **Launch integration**: Add to `manipulator_bringup.launch.py` or separate launch?
3. **Joint names**: Confirm exact joint names from `manipulator_params.yaml`
