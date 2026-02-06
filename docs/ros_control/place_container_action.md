# PlaceContainer Action Server - Architectural Design

## Overview

The `PlaceContainer` action server provides a high-level interface for placing containers. It orchestrates the manipulator movement and gripper control to execute a complete place operation — the reverse of `GetContainer`.

**Action name**: `/place_container`
**Package**: `ros_control`
**Type**: `ros_control/action/PlaceContainer`

---

## Requirements (MVP)

1. **Simple trigger**: Client calls action without parameters
2. **Place operation**: Move to place position, release, retract
3. **Result**: Return success/failure to client
4. **Configurable**: Place position, retract distance via YAML

---

## Action Definition

### `action/PlaceContainer.action`

```yaml
# Goal (empty for MVP - just trigger)
---
# Result
bool success
string message
float64 execution_time
---
# Feedback
string current_step
float32 progress_percentage
```

**Design Decision**: Same interface as `GetContainer` — empty goal for MVP simplicity. Reuses the same Result/Feedback structure for consistency.

---

## Configuration

### `config/place_container_config.yaml`

```yaml
place_container_server:
  ros__parameters:
    # Target position to place container
    place_position:
      base_main_frame_joint: 1.5              # X-axis rail position [m]
      main_frame_selector_frame_joint: 0.2    # Z-axis selector height at place [m]

    # Retract movement (lower selector to clear container after release)
    retract_joint: main_frame_selector_frame_joint
    retract_distance: 0.10                     # Distance to lower after release [m]

    # Timing
    gripper_settle_time: 1.0    # Wait time after gripper open (seconds)

    # Timeouts
    timeouts:
      move_timeout: 30.0        # MoveJointGroup timeout (seconds)
      gripper_timeout: 5.0      # Gripper service timeout (seconds)

    position_tolerance: 0.01    # Position tolerance (meters)
```

---

## Execution Flow

```
┌─────────────────────────────────────────────────────────────┐
│                   PlaceContainer Action                       │
│                                                              │
│  1. MOVE TO PLACE POSITION                                  │
│     └─► Call /move_joint_group action                       │
│         joints: [base_main_frame, main_frame_selector]      │
│         positions: from config                               │
│                                                              │
│  2. OPEN GRIPPER (release container)                        │
│     └─► Call /gripper/open service (std_srvs/Trigger)       │
│         + wait gripper_settle_time                           │
│                                                              │
│  3. RETRACT (lower selector to clear container)             │
│     └─► Call /move_joint_group action                       │
│         joint: main_frame_selector_frame_joint              │
│         position: place_z - retract_distance                │
│                                                              │
│  4. RETURN SUCCESS                                          │
└─────────────────────────────────────────────────────────────┘
```

### Step Details

| Step | Interface | Type | Description |
|------|-----------|------|-------------|
| 1. Move to place position | `/move_joint_group` | Action | Lower container to place position |
| 2. Open gripper | `/gripper/open` | Service (Trigger) | Release container |
| 3. Retract | `/move_joint_group` | Action | Lower selector to clear container |

### Comparison with GetContainer

| | GetContainer | PlaceContainer |
|---|---|---|
| Step 1 | Open gripper | Move to place position |
| Step 2 | Move to container | Open gripper + settle |
| Step 3 | Close gripper + settle | Retract (lower selector) |
| Step 4 | Lift (raise selector) | — |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Client Application                      │
│              (sends PlaceContainer goal)                     │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              PlaceContainer Action Server                     │
│                 /place_container                              │
│                                                              │
│  - Loads config from YAML                                   │
│  - Orchestrates place sequence                              │
│  - Publishes feedback                                       │
│  - Handles errors (fail-fast)                               │
└───────────┬─────────────────────────────────────┬───────────┘
            │                                     │
            ▼                                     ▼
┌───────────────────────┐             ┌───────────────────────┐
│  /move_joint_group    │             │  Gripper Services     │
│  Action Client        │             │  Service Client       │
│                       │             │                       │
│  - Move to place pos  │             │  - /gripper/open      │
│  - Retract after      │             │    (Trigger)          │
└───────────────────────┘             └───────────────────────┘
```

---

## Dependencies

### Existing Components Used

| Component | Interface | Purpose |
|-----------|-----------|---------|
| `move_joint_group_server` | Action `/move_joint_group` | Move manipulator joints |
| `gripper_service` | Service `/gripper/open` | Open gripper jaws |

### New Files to Create

| File | Purpose |
|------|---------|
| `action/PlaceContainer.action` | Action definition |
| `config/place_container_config.yaml` | Configuration |
| `src/place_container_server.py` | Action server implementation |

### Files to Modify

| File | Change |
|------|--------|
| `CMakeLists.txt` | Add `PlaceContainer.action` to rosidl_generate_interfaces, add `place_container_server.py` to install |
| `manipulator_bringup.launch.py` | Add `place_container_server` node to launch |

### Package Dependencies

- `rclpy` - ROS2 Python client
- `ros_control` - MoveJointGroup and PlaceContainer action types
- `std_srvs` - For Trigger service type

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
| Moving to place position | `"Moving to place position"` | 0% |
| Opening gripper | `"Opening gripper"` | 33% |
| Retracting | `"Retracting"` | 66% |
| Complete | `"Complete"` | 100% |

---

## State Machine

```
IDLE ─► MOVING_TO_PLACE ─► OPENING_GRIPPER ─► RETRACTING ─► SUCCESS
```

---

## Usage (After Implementation)

### Call Action

```bash
# Trigger place operation
ros2 action send_goal /place_container ros_control/action/PlaceContainer "{}"

# With feedback
ros2 action send_goal /place_container ros_control/action/PlaceContainer "{}" --feedback
```

---

## File Structure (After Implementation)

```
src/ros_control/
├── action/
│   ├── MoveJointGroup.action
│   ├── GetContainer.action
│   └── PlaceContainer.action        # NEW
├── config/
│   ├── move_joint_group_config.yaml
│   ├── get_container_config.yaml
│   └── place_container_config.yaml   # NEW
├── src/
│   ├── move_joint_group_server.py
│   ├── gripper_service.py
│   ├── get_container_server.py
│   └── place_container_server.py     # NEW
└── CMakeLists.txt                    # MODIFIED
```

---

## Implementation Steps

1. Create `docs/ros_control/place_container_action.md` — this architecture doc
2. Create `action/PlaceContainer.action` — action definition
3. Create `config/place_container_config.yaml` — configuration
4. Create `src/place_container_server.py` — server implementation (modeled after `get_container_server.py`)
5. Update `CMakeLists.txt` — register action and install script
6. Update `manipulator_bringup.launch.py` — add node to launch
7. Build and test
