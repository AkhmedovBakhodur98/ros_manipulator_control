# Project Structure Overview

ROS2 control system for manipulator robot with optional SCARA arm module.

## Main Packages

```
src/
├── manipulator_bringup/      # Launch infrastructure
├── manipulator_description/  # Main manipulator robot
├── ros_control/              # Unified control interface
└── scara_description/        # SCARA arm module (optional)
```

## Package Descriptions

### manipulator_bringup
Central launch package that starts the entire system.
- `launch/manipulator_bringup.launch.py` - Main entry point

### manipulator_description
Main manipulator robot definition.
- `config/` - Parameters and controllers configuration
- `launch/` - Display and control launch files
- `meshes/` - 3D models
- `urdf/` - Robot description (xacro)

### ros_control
Unified control interface with action servers.
- `src/move_joint_group_server.py` - Joint group action server
- `src/gripper_service.py` - Gripper control service
- `config/` - Controller configurations

### scara_description
Modular 3-DOF SCARA arm (can be used standalone or attached to manipulator).
- `config/` - SCARA parameters and controllers
- `launch/` - Standalone launch files
- `meshes/` - SCARA 3D models
- `urdf/` - SCARA robot description

## Key Configuration Files

| File | Purpose |
|------|---------|
| `manipulator_params.yaml` | Manipulator geometry/limits |
| `manipulator_controllers.yaml` | Manipulator ros2_control |
| `scara_params.yaml` | SCARA geometry/limits |
| `scara_controllers.yaml` | SCARA ros2_control |

## Quick Start

```bash
# Full system (manipulator + SCARA)
ros2 launch manipulator_bringup manipulator_bringup.launch.py use_scara:=true

# Manipulator only
ros2 launch manipulator_bringup manipulator_bringup.launch.py

# SCARA standalone
ros2 launch scara_description scara_control.launch.py
```

## Architecture

```
manipulator_description
    ├── Base assembly (rail + carriage)
    ├── Selector assembly (vertical lift + gripper)
    ├── Picker assembly (fine adjustment)
    └── scara_description (optional)
        └── SCARA arm (3-DOF) → attaches to picker_frame
```
