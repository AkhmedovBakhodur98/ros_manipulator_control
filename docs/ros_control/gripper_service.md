# Gripper Service

Provides simple binary open/close control for the symmetric container jaw gripper.

## Overview

The gripper service node provides ROS2 services for controlling the container jaws. It abstracts the low-level joint control into simple open/close commands with configurable positions.

## Jaw Movement Logic

The gripper consists of two prismatic joints with **opposite URDF axes**:
- Left jaw axis: `[0, -1, 0]` (-Y direction)
- Right jaw axis: `[0, 1, 0]` (+Y direction)

Because axes are opposite, **both jaws receive the SAME position value** to achieve symmetric movement:
- Same positive value → left moves -Y, right moves +Y → jaws move together (close)
- Same zero value → jaws at home position → jaws apart (open)

```
Position Value:    0.0 (home)              0.05 (home + offset)
                   ┌─────────────────┐     ┌─────────────────┐
Left Jaw:          │    ←            │     │         →       │
Right Jaw:         │            →    │     │       ←         │
                   └─────────────────┘     └─────────────────┘
State:             OPEN (apart)            CLOSED (together)
```

## Services

| Service | Type | Description |
|---------|------|-------------|
| `/gripper/open` | `std_srvs/srv/Trigger` | Move jaws apart (to home_position) |
| `/gripper/close` | `std_srvs/srv/Trigger` | Move jaws together (by close_offset) |

## Configuration

Configuration file: `ros_control/config/gripper_config.yaml`

```yaml
gripper_service:
  ros__parameters:
    # Joint names
    left_joint: "selector_left_container_jaw_joint"
    right_joint: "selector_right_container_jaw_joint"

    # Position configuration
    home_position: 0.0      # Open position (jaws apart) in meters
    open_offset: 0.05       # Closing distance from home (meters) = 5cm

    # Controller topic
    controller_topic: "/gripper_controller/commands"
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `left_joint` | string | `selector_left_container_jaw_joint` | Left jaw joint name |
| `right_joint` | string | `selector_right_container_jaw_joint` | Right jaw joint name |
| `home_position` | float | `0.0` | Open position (jaws fully apart) |
| `open_offset` | float | `0.05` | Distance jaws move when closing |
| `controller_topic` | string | `/gripper_controller/commands` | Topic for ForwardCommandController |

## Usage

### Call Services

```bash
# Open gripper (jaws apart)
ros2 service call /gripper/open std_srvs/srv/Trigger

# Close gripper (jaws together)
ros2 service call /gripper/close std_srvs/srv/Trigger
```

### Run Standalone

```bash
# With default parameters
ros2 run ros_control gripper_service.py

# With custom parameters
ros2 run ros_control gripper_service.py --ros-args \
  -p open_offset:=0.08 \
  -p home_position:=0.0
```

### Launch with Bringup

The gripper service is automatically started by `manipulator_bringup.launch.py`:

```bash
ros2 launch manipulator_bringup manipulator_bringup.launch.py
```

Startup sequence:
1. `joint_state_broadcaster` spawns
2. `gripper_controller` spawns
3. `gripper_service` starts (after gripper_controller)

## Published Topics

| Topic | Type | Description |
|-------|------|-------------|
| `/gripper_controller/commands` | `std_msgs/msg/Float64MultiArray` | Position commands `[left, right]` |

## Command Values

| Action | Left Jaw | Right Jaw | Published |
|--------|----------|-----------|-----------|
| Open | `home_position` | `home_position` | `[0.0, 0.0]` |
| Close | `home_position + open_offset` | `home_position + open_offset` | `[0.05, 0.05]` |

## Dependencies

- `std_srvs` - For `Trigger` service type
- `std_msgs` - For `Float64MultiArray` message type
- `gripper_controller` - Must be active (ForwardCommandController)

## Files

| File | Description |
|------|-------------|
| `src/gripper_service.py` | Main node implementation |
| `config/gripper_config.yaml` | Default configuration |

## See Also

- [move_joint_group_server.md](move_joint_group_server.md) - Action server for joint control
- [package_structure.md](package_structure.md) - Package overview
