# Project Structure Overview

ROS2 control system for manipulator robot with optional SCARA arm module.

## Main Packages

```
src/
├── manipulator_bringup/           # Launch infrastructure
├── manipulator_description/       # Main manipulator robot
├── manipulator_hardware_interface/# EtherCAT hardware interface (host stack ready; ROS package pending Stage 6)
├── ros_control/                   # Unified control interface
├── scara_description/             # SCARA arm module (optional)
├── scara_control/                 # SCARA arm control library
├── ar4_description/               # AR4 6-DOF arm (standalone)
├── ar4_hardware_interface/        # AR4 Teensy-serial hardware interface
└── ar4_control/                   # AR4 arm control (placeholder)
```

## Package Descriptions

### manipulator_bringup
Central launch package that starts the entire system.
- `launch/manipulator_bringup.launch.py` - Main entry point (manipulator system)
- `launch/ar4_bringup.launch.py` - AR4 standalone bringup

### manipulator_description
Main manipulator robot definition.
- `config/` - Parameters and controllers configuration
- `launch/` - Display and control launch files
- `meshes/` - 3D models
- `urdf/` - Robot description (xacro)

### ros_control
Unified control interface with action servers and services.
- `src/move_joint_group_server.py` - Joint group action server
- `src/gripper_service.py` - Gripper open/close services
- `src/get_container_server.py` - Container pick orchestration action server
- `src/place_container_server.py` - Container place orchestration action server
- `src/navigate_to_address_server.py` - Address-based platform navigation action server
- `src/extract_box_server.py` - Box extraction orchestration action server
- `src/return_box_server.py` - Box return orchestration action server
- `src/pick_items_from_warehouse_server.py` - Medicine picking orchestrator action server
- `action/MoveJointGroup.action` - Joint movement action definition
- `action/GetContainer.action` - Container pick action definition
- `action/PlaceContainer.action` - Container place action definition
- `action/NavigateToAddress.action` - Address-based navigation action definition
- `action/ExtractBox.action` - Box extraction action definition
- `action/ReturnBox.action` - Box return action definition
- `action/PickItemsFromWarehouse.action` - Medicine picking orchestrator action definition
- `msg/Address.msg` - Cabinet cell address message
- `msg/Medicament.msg` - Medicine metadata message (image_id, row_id, box_center)
- `config/` - Server configurations

### scara_description
Modular 3-DOF SCARA arm (can be used standalone or attached to manipulator).
- `config/` - SCARA parameters and controllers
- `launch/` - Standalone launch files
- `meshes/` - SCARA 3D models
- `urdf/` - SCARA robot description

### ar4_description
Standalone 6-DOF AR4 arm (AR4 MK3). Not integrated with the manipulator system.
- `config/` - Controller configuration (arm_controller for J1-J6)
- `meshes/` - Visual and collision STL models (7 links)
- `rviz/` - Pre-configured RViz visualization
- `urdf/` - Robot description (macro + ros2_control + entry point)

### ar4_control
Minimal placeholder package for future AR4 arm control development. Follows `scara_control` pattern (`ament_python`), currently empty.

### manipulator_hardware_interface (host stack ready; ROS package pending Stage 6)
EtherCAT hardware interface for the main manipulator (Z/X/A axes) and SCARA arm, driving StepperOnline A6-EC servos. Uses [ICube-Robotics/ethercat_driver_ros2](https://github.com/ICube-Robotics/ethercat_driver_ros2) `EcCiA402Drive` plugin via per-slave YAML configs — no custom C++ plugin. Replaces the Teensy-based path for production manipulator; AR4 keeps its own Teensy interface (`ar4_hardware_interface`).

Status on `grenka` 2026-05-14: Stages 1-5 of [bringup.md](../manipulator_hardware_interface/bringup.md) are closed (RT kernel, IgH master, slave discovery, single-slave CSP smoke via [`tools/csp_smoke/`](../../tools/csp_smoke/), ICube driver built with local patches). Stage 6 (per-slave YAML + ros2_control launch) is the next step. See `docs/manipulator_hardware_interface/` for the full plan and history.

## Key Configuration Files

| File | Purpose |
|------|---------|
| `manipulator_params.yaml` | Manipulator geometry/limits |
| `manipulator_controllers.yaml` | Manipulator ros2_control |
| `scara_params.yaml` | SCARA geometry/limits |
| `scara_controllers.yaml` | SCARA ros2_control |
| `ar4_controllers.yaml` | AR4 ros2_control |

## Quick Start

```bash
# Full system (manipulator + SCARA)
ros2 launch manipulator_bringup manipulator_bringup.launch.py use_scara:=true

# Manipulator only
ros2 launch manipulator_bringup manipulator_bringup.launch.py

# SCARA standalone
ros2 launch scara_description scara_control.launch.py

# AR4 standalone
ros2 launch manipulator_bringup ar4_bringup.launch.py
```

## Architecture

```
manipulator_description
    ├── Base assembly (rail + carriage)
    ├── Selector assembly (vertical lift + gripper)
    ├── Picker assembly (fine adjustment)
    └── scara_description (optional)
        └── SCARA arm (3-DOF) → attaches to picker_frame

ar4_description (standalone robot)
    └── AR4 arm (6-DOF) → standalone, not attached to manipulator
```
