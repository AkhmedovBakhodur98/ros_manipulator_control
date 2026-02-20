# ros_control Package

Unified ROS2 control interface for the manipulator system. Provides action servers for joint movement, gripper control, container operations, platform navigation, box extraction, and medicine picking.

## Overview

This package provides:
- **MoveJointGroup** — Coordinated multi-joint movement across controllers
- **GripperService** — Gripper open/close services
- **GetContainer / PlaceContainer** — Container pick and place orchestration
- **NavigateToAddress** — Address-based platform navigation
- **ExtractBox** — Box extraction from shelf (navigate + SCARA hook retract)
- **PickItemsFromWarehouse** — Orchestrator: extract box + pick medicines + place into container

## Package Structure

```
ros_control/
├── action/
│   ├── MoveJointGroup.action              # Joint movement action
│   ├── GetContainer.action                # Container pick action
│   ├── PlaceContainer.action              # Container place action
│   ├── NavigateToAddress.action           # Platform navigation action
│   ├── ExtractBox.action                  # Box extraction action
│   └── PickItemsFromWarehouse.action      # Medicine picking orchestrator action
├── msg/
│   ├── Address.msg                        # Cabinet cell address
│   └── Medicament.msg                     # Medicine metadata (image_id, row_id, box_center)
├── config/
│   ├── move_joint_group_config.yaml
│   ├── gripper_config.yaml
│   ├── get_container_config.yaml
│   ├── place_container_config.yaml
│   ├── navigate_to_address_config.yaml
│   ├── extract_box_config.yaml
│   └── pick_items_from_warehouse_config.yaml
├── launch/
│   ├── move_joint_group_server.launch.py
│   └── extract_box_server.launch.py
├── src/
│   ├── move_joint_group_server.py
│   ├── gripper_service.py
│   ├── get_container_server.py
│   ├── place_container_server.py
│   ├── navigate_to_address_server.py
│   ├── extract_box_server.py
│   └── pick_items_from_warehouse_server.py
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

## Documentation

Full documentation: [docs/ros_control/](../../docs/ros_control/)

- [package_structure.md](../../docs/ros_control/package_structure.md) — Package overview and ROS2 interfaces
- [move_joint_group_server.md](../../docs/ros_control/move_joint_group_server.md) — Joint movement server
- [gripper_service.md](../../docs/ros_control/gripper_service.md) — Gripper service
- [get_container_server.md](../../docs/ros_control/get_container_server.md) — Container pick operations
- [place_container_server.md](../../docs/ros_control/place_container_server.md) — Container place operations
- [pick_items_from_warehouse_action.md](../../docs/ros_control/pick_items_from_warehouse_action.md) — Medicine picking design
- [pick_items_from_warehouse_server.md](../../docs/ros_control/pick_items_from_warehouse_server.md) — Medicine picking server

