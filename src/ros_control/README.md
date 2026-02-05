# ros_control Package

Unified ROS2 control interface for moving multiple joints simultaneously across different controllers (manipulator, SCARA, gripper, and future equipment).

## Overview

This package provides the `MoveJointGroup` action server that:
- Dynamically discovers available controllers
- Coordinates movement of multiple joints across different controllers
- Supports both action-based (JointTrajectoryController) and topic-based (ForwardCommandController) controllers
- Provides unified feedback and result reporting

## Package Structure

```
ros_control/
├── action/
│   └── MoveJointGroup.action          # Action definition
├── config/
│   └── move_joint_group_config.yaml    # Configuration file
├── launch/
│   └── move_joint_group_server.launch.py
├── src/
│   └── move_joint_group_server.py     # Action server implementation
├── CMakeLists.txt
└── package.xml
```

## Building

```bash
cd /path/to/manipulator_ros_control
colcon build --packages-select ros_control
source install/setup.bash
```

## Usage

### Launch the Action Server

```bash
ros2 launch ros_control move_joint_group_server.launch.py
```

Or integrate with your existing manipulator launch:

```bash
ros2 launch manipulator_description manipulator_control.launch.py use_scara:=true
# In another terminal:
ros2 launch ros_control move_joint_group_server.launch.py
```

### Send Action Goals

**Move manipulator axes:**
```bash
ros2 action send_goal /move_joint_group \
  ros_control/action/MoveJointGroup "{
    joint_names: [
      'base_main_frame_joint',
      'main_frame_selector_frame_joint',
      'selector_frame_picker_frame_joint'
    ],
    target_positions: [1.5, 0.5, 0.1],
    max_velocity: [0.5, 0.3, 0.2]
  }"
```

**Move SCARA arm:**
```bash
ros2 action send_goal /move_joint_group \
  ros_control/action/MoveJointGroup "{
    joint_names: [
      'scara_shoulder_joint',
      'scara_elbow_joint',
      'scara_wrist_joint'
    ],
    target_positions: [0.5, 0.3, 1.0],
    max_velocity: [1.0, 1.0, 2.0]
  }"
```

**Mixed (manipulator + SCARA):**
```bash
ros2 action send_goal /move_joint_group \
  ros_control/action/MoveJointGroup "{
    joint_names: [
      'base_main_frame_joint',
      'scara_shoulder_joint'
    ],
    target_positions: [1.0, 0.5],
    max_velocity: [0.5, 1.0]
  }"
```

**Use default velocities (set max_velocity to 0.0):**
```bash
ros2 action send_goal /move_joint_group \
  ros_control/action/MoveJointGroup "{
    joint_names: ['base_main_frame_joint'],
    target_positions: [2.0],
    max_velocity: [0.0]
  }"
```

## Configuration

Edit `config/move_joint_group_config.yaml` to adjust:
- Position tolerance
- Execution strategy (simultaneous or coordinated)
- Controller discovery refresh interval
- Feedback publish rate

## Controller Discovery

The server automatically discovers controllers by:
1. Querying controller_manager for active controllers
2. Using known mappings for joint lists (extendable)
3. Refreshing periodically (configurable)

To add support for new controllers, add them to the `known_mappings` dictionary in `move_joint_group_server.py`.

## Dependencies

- `rclpy` - ROS2 Python client
- `control_msgs` - For FollowJointTrajectory action
- `sensor_msgs` - For JointState messages
- `controller_manager_msgs` - For controller discovery
- `pyyaml` - For configuration file parsing

## Architecture

See `docs/ros_control/move_joint_group_architecture.md` for detailed architecture documentation.

