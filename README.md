# Manipulator ROS2 Control System

ROS2 control system for an industrial manipulator with optional SCARA arm. Provides unified joint control, gripper management, and high-level container pick/place operations.

## Packages

| Package | Description |
|---------|-------------|
| `manipulator_description` | Robot model (URDF/xacro), meshes, controllers config |
| `scara_description` | Optional SCARA arm module (3-DOF, attaches to picker_frame) |
| `ros_control` | Unified control interface: joint movement, gripper, container operations, box extraction/return, medicine picking |
| `scara_control` | SCARA arm control library (ScaraClient: IK/FK, linear motion, pick/place) |
| `rest_api_bridge` | REST API layer for external WMS integration (FastAPI + JWT auth) |
| `ar4_description` | AR4 6-DOF arm (standalone): URDF, meshes, controllers |
| `ar4_hardware_interface` | ros2_control plugin for AR4 real hardware (Teensy 4.1 serial) |
| `ar4_control` | AR4 arm control (placeholder) |
| `manipulator_bringup` | Launch files for full system startup |
| `firmware/ar4_teensy` | Teensy 4.1 firmware: stepper motor control, homing, serial protocol |

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

# Navigate to cabinet address
ros2 action send_goal /navigate_to_address ros_control/action/NavigateToAddress \
  "{side: 'left', cabinet_num: 2, row: 1, column: 0}" --feedback

# Extract box from shelf
ros2 action send_goal /extract_box ros_control/action/ExtractBox \
  "{box: {side: 'left', cabinet_num: 2, row: 1, column: 0}}" --feedback

# Return box to shelf
ros2 action send_goal /return_box ros_control/action/ReturnBox \
  "{box: {side: 'left', cabinet_num: 2, row: 1, column: 0}, box_id: 'box_l_2_1_0'}" --feedback

# Pick medicines from box (orchestrator: extract box + pick + place into container)
ros2 action send_goal /PickItems ros_control/action/PickItemsFromWarehouse \
  "{detection: [{image_id: 'med-001', row_id: 0, box_center: {x: 0.0, y: 0.0, z: 0.0}}], box: {side: 'left', cabinet_num: 2, row: 1, column: 0}}" --feedback

# Gripper
ros2 service call /gripper/open std_srvs/srv/Trigger
ros2 service call /gripper/close std_srvs/srv/Trigger
```

### REST API Integration

External systems can control the robot via HTTP/JSON REST API:

```bash
# Start REST API server
ros2 launch rest_api_bridge rest_api_server.launch.py

# API available at: http://localhost:8080/api/v1
# Interactive docs: http://localhost:8080/api/v1/docs

# Get authentication token
curl -X POST http://localhost:8080/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "wms_system", "client_secret": "demo_secret_2024"}'

# Get container
curl -X POST http://localhost:8080/api/v1/getcontainer \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"unload": false}'

# Extract medicines
curl -X POST http://localhost:8080/api/v1/get_items \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "medicine_list": [{"image_id": "med-001", "raw_id": 0}],
    "box_id": "BOX-12345",
    "task_id": "task-001"
  }'

# Check task status
curl http://localhost:8080/api/v1/task/status \
  -H "Authorization: Bearer <token>"
```

See [docs/rest_api_bridge/](docs/rest_api_bridge/) for complete API documentation.

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
│   ├── action/                    # MoveJointGroup, GetContainer, PlaceContainer, NavigateToAddress, ExtractBox, ReturnBox, PickItemsFromWarehouse
│   ├── msg/                       # Address, Medicament
│   ├── config/                    # Server configurations
│   └── src/                       # Server implementations
│       ├── move_joint_group_server.py
│       ├── gripper_service.py
│       ├── get_container_server.py
│       ├── place_container_server.py
│       ├── navigate_to_address_server.py
│       ├── extract_box_server.py
│       ├── return_box_server.py
│       └── pick_items_from_warehouse_server.py
│
├── rest_api_bridge/               # REST API for external WMS
│   ├── rest_api_bridge/           # Python package
│   │   ├── api_server.py          # FastAPI + ROS2 node
│   │   ├── routers/               # API endpoints (auth, container, medicine, task)
│   │   ├── models/                # Pydantic request/response models
│   │   ├── middleware/            # JWT authentication
│   │   └── services/              # Mock/ROS service implementations
│   ├── config/                    # rest_api_config.yaml (JWT, server settings)
│   └── launch/                    # rest_api_server.launch.py
│
├── ar4_description/               # AR4 6-DOF arm (standalone)
│   ├── urdf/                      # AR4 URDF/xacro (macro + ros2_control)
│   ├── config/                    # ar4_controllers.yaml
│   ├── meshes/                    # Visual and collision STL models
│   └── rviz/                      # AR4 RViz config
│
├── ar4_hardware_interface/        # AR4 real hardware plugin
│   ├── include/                   # Ar4System, SerialPort, TeensyProtocol
│   └── src/                       # Plugin lifecycle, serial comms
│
├── ar4_control/                   # AR4 control (placeholder)
│
└── manipulator_bringup/           # System startup
    └── launch/
        ├── manipulator_bringup.launch.py
        ├── ar4_bringup.launch.py
        └── ar4_display.launch.py

firmware/
└── ar4_teensy/                    # Teensy 4.1 firmware (PlatformIO)
    ├── include/                   # config.h, joints_config.h, motor.h, homing.h, protocol.h
    └── src/                       # main.cpp, motor.cpp, homing.cpp, protocol.cpp
```

## ROS2 Interfaces

### Actions

| Action | Type | Description |
|--------|------|-------------|
| `/move_joint_group` | `ros_control/action/MoveJointGroup` | Coordinated multi-joint movement |
| `/get_container` | `ros_control/action/GetContainer` | Container pick (open -> move -> grab -> lift) |
| `/place_container` | `ros_control/action/PlaceContainer` | Container place (move -> release -> retract) |
| `/navigate_to_address` | `ros_control/action/NavigateToAddress` | Navigate platform to cabinet address (side, cabinet, row, column) |
| `/extract_box` | `ros_control/action/ExtractBox` | Extract box from shelf (navigate + SCARA hook retract) |
| `/return_box` | `ros_control/action/ReturnBox` | Return box to shelf (navigate + SCARA hook push) |
| `/PickItems` | `ros_control/action/PickItemsFromWarehouse` | Orchestrator: extract box + pick medicines + place into container |

### Services

| Service | Type | Description |
|---------|------|-------------|
| `/gripper/open` | `std_srvs/srv/Trigger` | Open gripper |
| `/gripper/close` | `std_srvs/srv/Trigger` | Close gripper |

### REST API Endpoints

External systems can access robot functionality via REST API:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/token` | POST | Get JWT authentication token |
| `/api/v1/health` | GET | Check service health |
| `/api/v1/is_ready` | GET | Check system readiness |
| `/api/v1/getcontainer` | POST | Retrieve container from storage |
| `/api/v1/retcontainer` | GET | Return container to storage |
| `/api/v1/get_items` | POST | Extract medicines from box |
| `/api/v1/put_items` | POST | Place medicines into box |
| `/api/v1/task/status` | GET | Get current task status |
| `/api/v1/task/cancel` | GET | Cancel running task |

## Documentation

Full documentation is in the [docs/](docs/) directory:

**Manipulator system:**
- [docs/project_structure/overview.md](docs/project_structure/overview.md) - High-level project overview
- [docs/manipulator_description/package_structure.md](docs/manipulator_description/package_structure.md) - Robot model details
- [docs/manipulator_bringup/launch_files.md](docs/manipulator_bringup/launch_files.md) - Launch file reference
- [docs/ros_control/package_structure.md](docs/ros_control/package_structure.md) - Control interface details

**AR4 arm:**
- [docs/firmware/ar4_teensy.md](docs/firmware/ar4_teensy.md) - Teensy firmware, serial protocol, pin assignments
- [docs/ar4_hardware_interface/package_structure.md](docs/ar4_hardware_interface/package_structure.md) - ROS2 hardware interface, calibration
- [docs/ar4_description/package_structure.md](docs/ar4_description/package_structure.md) - AR4 URDF, joint specs, usage

**Action servers:**
- [docs/ros_control/get_container_server.md](docs/ros_control/get_container_server.md) - Container pick operations
- [docs/ros_control/place_container_server.md](docs/ros_control/place_container_server.md) - Container place operations
- [docs/ros_control/navigate_to_address_server.md](docs/ros_control/navigate_to_address_server.md) - Address-based platform navigation
- [docs/ros_control/extract_box_server.md](docs/ros_control/extract_box_server.md) - Box extraction from shelf
- [docs/ros_control/return_box_server.md](docs/ros_control/return_box_server.md) - Box return to shelf
- [docs/ros_control/pick_items_from_warehouse_server.md](docs/ros_control/pick_items_from_warehouse_server.md) - Medicine picking orchestrator

**REST API:**
- [docs/rest_api_bridge/package_structure.md](docs/rest_api_bridge/package_structure.md) - REST API complete reference
- [docs/rest_api_bridge/API_CLIENT_GUIDE_RU.md](docs/rest_api_bridge/API_CLIENT_GUIDE_RU.md) - API client integration guide (Russian)
