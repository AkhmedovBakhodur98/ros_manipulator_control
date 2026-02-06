# Manipulator ROS2 Control System

ROS2 control system for an industrial manipulator with optional SCARA arm. Provides unified joint control, gripper management, and high-level container pick/place operations.

## Packages

| Package | Description |
|---------|-------------|
| `manipulator_description` | Robot model (URDF/xacro), meshes, controllers config |
| `scara_description` | Optional SCARA arm module (3-DOF, attaches to picker_frame) |
| `ros_control` | Unified control interface: joint movement, gripper, container operations |
| `manipulator_bringup` | Launch files for full system startup |

## Quick Start

### Build

```bash
cd ~/manipulator_ros_control
colcon build
source install/setup.bash
```

### Launch Full System

```bash
# Manipulator with RViz
ros2 launch manipulator_bringup manipulator_bringup.launch.py

# With SCARA arm (recommended for full system)
ros2 launch manipulator_bringup manipulator_bringup.launch.py use_scara:=true

# Without visualization
ros2 launch manipulator_bringup manipulator_bringup.launch.py rviz:=false
```

### Control Commands

```bash
# Move joints
ros2 action send_goal /move_joint_group ros_control/action/MoveJointGroup \
  "{joint_names: ['base_main_frame_joint'], target_positions: [1.5], max_velocity: [0.5]}"

# Pick container
ros2 action send_goal /get_container ros_control/action/GetContainer "{}" --feedback

# Place container
ros2 action send_goal /place_container ros_control/action/PlaceContainer "{}" --feedback

# Gripper
ros2 service call /gripper/open std_srvs/srv/Trigger
ros2 service call /gripper/close std_srvs/srv/Trigger
```

## Project Structure

```
src/
├── manipulator_description/       # Robot model
│   ├── urdf/                      # URDF/xacro files
│   ├── config/                    # manipulator_params.yaml, manipulator_controllers.yaml
│   ├── meshes/                    # 3D models
│   ├── launch/                    # display.launch.py, manipulator_control.launch.py
│   └── rviz/                      # RViz config
│
├── scara_description/             # SCARA arm (optional)
│   ├── urdf/                      # SCARA xacro files
│   ├── config/                    # scara_params.yaml, scara_controllers.yaml
│   └── launch/                    # display.launch.py, scara_control.launch.py
│
├── ros_control/                   # Unified control interface
│   ├── action/                    # MoveJointGroup, GetContainer, PlaceContainer
│   ├── config/                    # Server configurations
│   └── src/                       # Server implementations
│       ├── move_joint_group_server.py
│       ├── gripper_service.py
│       ├── get_container_server.py
│       └── place_container_server.py
│
└── manipulator_bringup/           # System startup
    └── launch/
        └── manipulator_bringup.launch.py
```

## ROS2 Interfaces

### Actions

| Action | Type | Description |
|--------|------|-------------|
| `/move_joint_group` | `ros_control/action/MoveJointGroup` | Coordinated multi-joint movement |
| `/get_container` | `ros_control/action/GetContainer` | Container pick (open -> move -> grab -> lift) |
| `/place_container` | `ros_control/action/PlaceContainer` | Container place (move -> release -> retract) |

### Services

| Service | Type | Description |
|---------|------|-------------|
| `/gripper/open` | `std_srvs/srv/Trigger` | Open gripper |
| `/gripper/close` | `std_srvs/srv/Trigger` | Close gripper |

## Documentation

Full documentation is in the [docs/](docs/) directory:

- [docs/README.md](docs/README.md) - Documentation index
- [docs/ros_control/package_structure.md](docs/ros_control/package_structure.md) - Control interface details
- [docs/ros_control/get_container_server.md](docs/ros_control/get_container_server.md) - Container pick operations
- [docs/ros_control/place_container_server.md](docs/ros_control/place_container_server.md) - Container place operations
- [docs/manipulator_bringup/launch_files.md](docs/manipulator_bringup/launch_files.md) - Launch file reference
- [docs/manipulator_description/package_structure.md](docs/manipulator_description/package_structure.md) - Robot model details
