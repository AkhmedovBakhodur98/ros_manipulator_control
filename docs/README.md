# Documentation Overview

This directory contains comprehensive documentation for the manipulator ROS2 control system, including the main manipulator, SCARA arm, SCARA control library, unified control interface, REST API bridge, and system bringup.

---

## Documentation Structure

```
docs/
├── README.md                              # This file
├── project_structure/
│   └── overview.md                        # High-level project overview
├── manipulator_description/               # Main manipulator documentation
│   ├── frames_reference.md                # Coordinate frame reference
│   ├── package_structure.md               # Package structure and files
│   └── yaml_to_urdf.md                    # Parameter flow from YAML to URDF
├── scara_description/                     # SCARA arm documentation
│   ├── CHANGELOG.md                       # Recent changes and updates
│   ├── configuration.md                   # Configuration guide
│   ├── integration.md                     # Integration with other robots
│   ├── package_structure.md               # Package structure and files
│   └── ros2_control.md                    # ros2_control integration
├── scara_control/                         # SCARA arm control library documentation
│   ├── scara_client_architecture.md       # Architectural design document
│   ├── package_structure.md               # Package structure and files
│   └── scara_client.md                    # ScaraClient implementation details
├── ros_control/                           # Unified control interface documentation
│   ├── package_structure.md               # Package structure and files
│   ├── move_joint_group_server.md         # Joint movement action server
│   ├── gripper_service.md                 # Gripper open/close service
│   ├── get_container_action.md            # GetContainer architectural design
│   ├── get_container_server.md            # GetContainer server documentation
│   ├── place_container_action.md          # PlaceContainer architectural design
│   ├── place_container_server.md          # PlaceContainer server documentation
│   ├── return_box_server.md               # ReturnBox server documentation
│   ├── pick_items_from_warehouse_action.md # PickItemsFromWarehouse architectural design
│   └── pick_items_from_warehouse_server.md # PickItemsFromWarehouse server documentation
├── rest_api_bridge/                       # REST API bridge documentation
│   ├── package_structure.md               # Package structure and API reference
│   ├── API_REFERENCE.md                   # Complete API specification (English)
│   ├── API_CLIENT_GUIDE_RU.md             # Client API guide (Russian)
│   ├── ENDPOINT_CHANGES.md                # Endpoint renaming guide (Feb 2026)
│   ├── TESTING.md                         # Testing guide with examples
│   └── DEPENDENCIES.md                    # Python dependency installation
└── manipulator_bringup/                   # System bringup documentation
    ├── package_structure.md               # Package structure and files
    ├── launch_files.md                    # Launch file documentation
    └── implementation_review.md           # Implementation review notes
```

---

## Quick Navigation

### For New Users

**Getting Started:**
1. Start with [project_structure/overview.md](project_structure/overview.md) for a high-level project overview
2. Read [manipulator_description/package_structure.md](manipulator_description/package_structure.md) to understand the main system
3. Read [scara_description/package_structure.md](scara_description/package_structure.md) to learn about the SCARA module
4. Read [ros_control/package_structure.md](ros_control/package_structure.md) to understand the control interface
5. Read [manipulator_bringup/launch_files.md](manipulator_bringup/launch_files.md) to understand how everything starts

**Configuration:**
- [scara_description/configuration.md](scara_description/configuration.md) - Configure SCARA parameters
- [manipulator_description/yaml_to_urdf.md](manipulator_description/yaml_to_urdf.md) - Understand parameter system

**Control:**
- [scara_control/package_structure.md](scara_control/package_structure.md) - SCARA arm control library (ScaraClient)
- [scara_control/scara_client.md](scara_control/scara_client.md) - ScaraClient implementation details
- [ros_control/move_joint_group_server.md](ros_control/move_joint_group_server.md) - Unified joint movement
- [ros_control/gripper_service.md](ros_control/gripper_service.md) - Gripper open/close control
- [ros_control/get_container_server.md](ros_control/get_container_server.md) - Container pick operations
- [ros_control/place_container_server.md](ros_control/place_container_server.md) - Container place operations
- [ros_control/return_box_server.md](ros_control/return_box_server.md) - Box return to cabinet
- [ros_control/pick_items_from_warehouse_server.md](ros_control/pick_items_from_warehouse_server.md) - Medicine picking orchestrator
- [ros_control/pick_items_from_warehouse_action.md](ros_control/pick_items_from_warehouse_action.md) - PickItems architectural design
- [scara_description/ros2_control.md](scara_description/ros2_control.md) - SCARA ros2_control integration

**External API:**
- [rest_api_bridge/package_structure.md](rest_api_bridge/package_structure.md) - REST API for WMS integration
- [rest_api_bridge/API_REFERENCE.md](rest_api_bridge/API_REFERENCE.md) - Complete API specification (English)
- [rest_api_bridge/API_CLIENT_GUIDE_RU.md](rest_api_bridge/API_CLIENT_GUIDE_RU.md) - Client API guide (Russian)
- [rest_api_bridge/ENDPOINT_CHANGES.md](rest_api_bridge/ENDPOINT_CHANGES.md) - Endpoint renaming guide (Feb 2026)
- [rest_api_bridge/TESTING.md](rest_api_bridge/TESTING.md) - API testing guide
- [rest_api_bridge/DEPENDENCIES.md](rest_api_bridge/DEPENDENCIES.md) - Python dependencies

**Reference:**
- [manipulator_description/frames_reference.md](manipulator_description/frames_reference.md) - Frame coordinate systems

---

## Manipulator Description Documentation

### [frames_reference.md](manipulator_description/frames_reference.md)
**Purpose:** Reference guide for coordinate frames in the manipulator system.

**Contents:**
- Coordinate system conventions (ROS REP-103)
- Frame chain from `world` to `picker_frame`
- `picker_frame` coordinate system details
- SCARA mount offset explanations
- Common mount configurations
- How to visualize frames in RViz

**When to read:** When you need to understand where to mount attachments or understand frame relationships.

---

### [package_structure.md](manipulator_description/package_structure.md)
**Purpose:** Complete overview of the manipulator_description package structure and files.

**Contents:**
- Package organization
- File descriptions (CMakeLists.txt, package.xml, config files, launch files, meshes, URDF/xacro)
- Robot kinematic structure (links and joints)
- Usage examples
- Dependencies
- ros2_control architecture
- Control examples

**When to read:** First document to read for understanding the manipulator system. Essential for developers.

---

### [yaml_to_urdf.md](manipulator_description/yaml_to_urdf.md)
**Purpose:** Deep dive into how parameters flow from YAML configuration files to URDF.

**Contents:**
- How xacro works (Python-based XML preprocessor)
- YAML loading mechanism (`xacro.load_yaml()`)
- Parameter access patterns
- Complete data flow examples
- Python expressions in xacro
- Debugging tips

**When to read:** When you need to modify parameters, understand the configuration system, or debug parameter issues.

---

## SCARA Description Documentation

### [CHANGELOG.md](scara_description/CHANGELOG.md)
**Purpose:** Recent changes and updates to the SCARA arm package.

**Contents:**
- Latest ros2_control integration
- New files created
- Modified files
- Features added
- Usage examples
- Configuration changes

**When to read:** To stay updated on recent changes or understand what's new in the package.

---

### [configuration.md](scara_description/configuration.md)
**Purpose:** Complete guide to configuring SCARA arm parameters.

**Contents:**
- Configuration file structure (`scara_params.yaml`)
- Mount configuration (position and orientation offsets)
- Kinematics configuration (link lengths L1, L2)
- Links configuration (mesh, color, inertial properties)
- Joints configuration (limits, dynamics)
- Complete configuration examples
- Common modifications
- Validation methods

**When to read:** When you need to customize SCARA parameters, adjust mount position, or modify joint limits.

---

### [integration.md](scara_description/integration.md)
**Purpose:** Guide for integrating the SCARA arm with other robots.

**Contents:**
- Understanding parent frames
- Step-by-step integration process
- Configuration options
- Common integration patterns
- Mount offset configuration
- Integration with manipulator_description
- Troubleshooting
- Advanced topics (link prefixes)
- API reference

**When to read:** When you want to attach SCARA to a different robot or understand how it integrates with the manipulator.

---

### [package_structure.md](scara_description/package_structure.md)
**Purpose:** Complete overview of the scara_description package structure and files.

**Contents:**
- Package organization
- File descriptions (build files, config files, launch files, meshes, URDF/xacro)
- Robot kinematic structure
- SCARA kinematics (workspace, joint specifications, forward kinematics)
- Usage examples
- Integration examples
- Dependencies
- ROS2 topics

**When to read:** First document to read for understanding the SCARA system. Essential for developers.

---

### [ros2_control.md](scara_description/ros2_control.md)
**Purpose:** Complete documentation for ros2_control integration with SCARA.

**Contents:**
- Architecture overview
- Files created for ros2_control
- Standalone usage
- Integration with manipulator_description
- Hardware interface (mock and real hardware)
- Joint limits
- Topics and actions
- Troubleshooting
- Configuration changes

**When to read:** When you need to control SCARA programmatically, understand the control architecture, or integrate with real hardware.

---

## SCARA Control Library Documentation

### [package_structure.md](scara_control/package_structure.md)
**Purpose:** Complete overview of the scara_control package — reusable SCARA arm control library.

**Contents:**
- Package organization and file descriptions
- Two-controller architecture (SCARA + optional Z-axis)
- Configuration reference (scara_client section in scara_params.yaml)
- ROS2 interfaces (topics, actions, services)
- Usage examples (move joints, IK, pick/place, linear motion)
- Build and verify instructions

**When to read:** First document to read for using the ScaraClient library. Essential for integrators.

---

### [scara_client.md](scara_control/scara_client.md)
**Purpose:** Detailed implementation documentation for the ScaraClient class.

**Contents:**
- Data types (ScaraResult, ElbowConfig, CartesianPose, IKSolution, IKDiagnostic)
- Exceptions and error handling strategy
- Constructor and config auto-discovery
- State queries (joint positions, TCP position, elbow config)
- Kinematics (FK, IK, reachability, IK diagnostics)
- Motion methods (move_joints, move_z, move_to_point, move_linear, move_linear_with_flip, move_home)
- Tool control (trigger_tool, pick_at, place_at)
- Implementation patterns (thread safety, async action client, trajectory points)
- SCARA arm specification and velocity reference

**When to read:** When you need to understand ScaraClient internals, extend behavior, or debug motion issues.

---

### [scara_client_architecture.md](scara_control/scara_client_architecture.md)
**Purpose:** Architectural design document for the ScaraClient class.

**When to read:** When you need to understand design decisions, IK equations, or the elbow flip algorithm.

---

## ROS Control Documentation

### [package_structure.md](ros_control/package_structure.md)
**Purpose:** Complete overview of the ros_control package — unified control interface.

**Contents:**
- Package organization and file descriptions
- Action definitions (MoveJointGroup, GetContainer, PlaceContainer)
- Configuration files for all servers
- Source code descriptions
- Architecture and data flow diagrams
- ROS2 topics, services, and actions reference
- Usage examples (CLI, Python, C++)
- Troubleshooting

**When to read:** First document to read for understanding the control interface. Essential for developers.

---

### [move_joint_group_server.md](ros_control/move_joint_group_server.md)
**Purpose:** Documentation for the MoveJointGroup action server — coordinated multi-joint movement.

**When to read:** When you need to move manipulator joints programmatically.

---

### [gripper_service.md](ros_control/gripper_service.md)
**Purpose:** Documentation for the gripper open/close service node.

**When to read:** When you need to control the gripper or understand jaw movement.

---

### [get_container_server.md](ros_control/get_container_server.md)
**Purpose:** Documentation for the GetContainer action server — container pick operations.

**Contents:**
- Execution flow (open gripper -> move -> close gripper -> lift)
- Action definition and feedback steps
- Configuration parameters
- Usage examples (CLI, Python, C++)
- Implementation details

**When to read:** When you need to perform container pick operations.

---

### [place_container_server.md](ros_control/place_container_server.md)
**Purpose:** Documentation for the PlaceContainer action server — container place operations (reverse of GetContainer).

**Contents:**
- Execution flow (move to place -> open gripper -> retract)
- Action definition and feedback steps
- Configuration parameters
- Usage examples (CLI, Python, C++)
- Implementation details

**When to read:** When you need to perform container place operations.

---

### [get_container_action.md](ros_control/get_container_action.md)
**Purpose:** Architectural design document for the GetContainer action.

**When to read:** When you need to understand design decisions behind the GetContainer implementation.

---

### [place_container_action.md](ros_control/place_container_action.md)
**Purpose:** Architectural design document for the PlaceContainer action.

**When to read:** When you need to understand design decisions behind the PlaceContainer implementation.

---

### [return_box_server.md](ros_control/return_box_server.md)
**Purpose:** Documentation for the ReturnBox action server — returning a box to a cabinet cell (reverse of ExtractBox).

**Contents:**
- Execution flow (navigate -> position -> push -> disengage -> home)
- 7-step SCARA return sequence (reverse of extraction)
- Comparison table: ExtractBox vs ReturnBox differences
- Action definition and feedback phases
- Configuration parameters
- Usage examples (CLI, Python)
- Implementation details

**When to read:** When you need to return boxes to cabinet cells after extraction.

---

### [pick_items_from_warehouse_action.md](ros_control/pick_items_from_warehouse_action.md)
**Purpose:** Architectural design document for the PickItemsFromWarehouse action — medicine picking orchestrator.

**Contents:**
- System data flow (PickItems as orchestrator calling ExtractBox → pick → place)
- Action definition (Goal, Result, Feedback)
- VisionProvider abstraction (mock/real)
- 10 key design decisions (orchestrator pattern, timeouts, detection retries, two-stage descent)
- File manifest

**When to read:** When you need to understand the design decisions behind the medicine picking workflow.

---

### [pick_items_from_warehouse_server.md](ros_control/pick_items_from_warehouse_server.md)
**Purpose:** Implementation documentation for the PickItemsFromWarehouse action server.

**Contents:**
- 4-phase execution flow (init → extract box → pick items → finalize)
- ExtractBox sub-action integration with feedback relay
- ScaraClient pick-and-place sequence (approach → pick → transit → place)
- VisionProvider mock architecture
- Error handling, cancellation forwarding, timeout enforcement
- Configuration reference

**When to read:** When you need to understand PickItemsFromWarehouse server internals or debug the picking workflow.

---

## REST API Bridge Documentation

### [package_structure.md](rest_api_bridge/package_structure.md)
**Purpose:** Complete documentation for the REST API Bridge package that provides HTTP/JSON endpoints for external WMS (Warehouse Management Systems) to control the robot.

**Contents:**
- Package structure and file descriptions
- FastAPI application architecture
- JWT authentication and security
- API endpoint reference (health, auth, container, medicine, task)
- Pydantic request/response models
- Mock service implementation
- Configuration parameters
- ROS2 integration design
- HTTP/Python/JavaScript client examples
- Production deployment guide
- Security best practices
- Troubleshooting

**When to read:** When you need to:
- Integrate external systems with the robot via REST API
- Understand API authentication and security
- Test API endpoints
- Deploy the API in production
- Add new API endpoints
- Implement real ROS2 integration (replacing mock mode)

---

### [TESTING.md](rest_api_bridge/TESTING.md)
**Purpose:** Complete guide for testing REST API endpoints with examples.

**Contents:**
- Starting the REST API server
- Health check testing
- JWT authentication flow
- Testing all API endpoints with curl
- Python test script
- Expected responses
- Troubleshooting common issues

**When to read:** When you need to:
- Verify API server is working correctly
- Test new endpoints after changes
- Debug API issues
- Learn how to interact with the API

---

### [API_REFERENCE.md](rest_api_bridge/API_REFERENCE.md)
**Purpose:** Complete REST API specification with detailed endpoint documentation (English).

**Contents:**
- All endpoint specifications with request/response examples
- Authentication flow (JWT tokens)
- Error response format
- Complete workflow examples
- Python and curl client examples
- Interactive documentation (Swagger UI)

**When to read:** When you need to:
- Integrate with the REST API
- Understand endpoint request/response structures
- Implement API clients
- Debug API integration issues

---

### [API_CLIENT_GUIDE_RU.md](rest_api_bridge/API_CLIENT_GUIDE_RU.md)
**Purpose:** Comprehensive client integration guide in Russian (Полное руководство по интеграции на русском языке).

**Contents (на русском языке):**
- Быстрый старт с примерами
- Аутентификация JWT
- Проверка состояния системы
- Работа с контейнерами (получение, возврат)
- Работа с медикаментами (извлечение, размещение)
- Управление задачами (статус, отмена)
- Типичные сценарии использования
- Обработка ошибок и коды ответов
- Примеры интеграции (Python, C#)
- Рекомендации по интеграции
- FAQ на русском языке

**When to read (Когда читать):** When you need to:
- Integrate external WMS systems with the robot API
- Learn the complete API workflow with real examples
- Understand error handling and best practices
- Implement API clients in Python or C#
- Russian-speaking developers and integrators

---

### [ENDPOINT_CHANGES.md](rest_api_bridge/ENDPOINT_CHANGES.md)
**Purpose:** Migration guide for endpoint renaming (February 2026).

**Contents:**
- Summary of renamed endpoints (startloading→is_ready, getmedicine→get_items, putmedicine→put_items)
- Migration guide with before/after examples
- Python client update examples
- Testing commands for new endpoints
- Code and model changes

**When to read:** When you need to:
- Migrate existing API clients to new endpoint names
- Understand what changed in February 2026 update
- Update integration code

---

### [DEPENDENCIES.md](rest_api_bridge/DEPENDENCIES.md)
**Purpose:** Python dependency installation guide for REST API Bridge.

**Contents:**
- Required Python packages (python-jose, passlib, bcrypt)
- Installation instructions
- Version compatibility notes
- Troubleshooting dependency issues

**When to read:** When you need to:
- Install REST API Bridge dependencies
- Fix dependency-related errors
- Understand version compatibility requirements

---

## Manipulator Bringup Documentation

### [package_structure.md](manipulator_bringup/package_structure.md)
**Purpose:** Overview of the manipulator_bringup package.

**When to read:** To understand the bringup package organization.

---

### [launch_files.md](manipulator_bringup/launch_files.md)
**Purpose:** Detailed documentation of `manipulator_bringup.launch.py` — the main launch file.

**Contents:**
- Launch arguments (use_scara, rviz, use_sim_time)
- Step-by-step execution order
- Controller mapping extraction
- All nodes started (robot_state_publisher, controller_manager, controllers, move_joint_group_server, gripper_service, get_container_server, place_container_server, rviz2)
- Event handler sequencing
- Configuration files used
- Troubleshooting

**When to read:** When you need to understand system startup or debug launch issues.

---

## Documentation by Use Case

### I want to...

**...understand the overall system:**
- Start with [project_structure/overview.md](project_structure/overview.md)
- Then read [manipulator_description/package_structure.md](manipulator_description/package_structure.md)
- Then read [ros_control/package_structure.md](ros_control/package_structure.md)

**...launch the full system:**
- Read [manipulator_bringup/launch_files.md](manipulator_bringup/launch_files.md)

**...move manipulator joints:**
- Read [ros_control/move_joint_group_server.md](ros_control/move_joint_group_server.md)

**...pick or place containers:**
- Read [ros_control/get_container_server.md](ros_control/get_container_server.md)
- Read [ros_control/place_container_server.md](ros_control/place_container_server.md)

**...return a box to the shelf:**
- Read [ros_control/return_box_server.md](ros_control/return_box_server.md)

**...pick medicines from a shelf box:**
- Read [ros_control/pick_items_from_warehouse_action.md](ros_control/pick_items_from_warehouse_action.md) for architectural design
- Read [ros_control/pick_items_from_warehouse_server.md](ros_control/pick_items_from_warehouse_server.md) for implementation details

**...control the gripper:**
- Read [ros_control/gripper_service.md](ros_control/gripper_service.md)

**...integrate SCARA with my robot:**
- Read [scara_description/integration.md](scara_description/integration.md)
- Reference [manipulator_description/frames_reference.md](manipulator_description/frames_reference.md) for frame understanding

**...configure SCARA parameters:**
- Read [scara_description/configuration.md](scara_description/configuration.md)
- Reference [manipulator_description/yaml_to_urdf.md](manipulator_description/yaml_to_urdf.md) for parameter system details

**...control SCARA programmatically (high-level library):**
- Read [scara_control/package_structure.md](scara_control/package_structure.md) for quick start
- Read [scara_control/scara_client.md](scara_control/scara_client.md) for full API details

**...control SCARA via low-level ros2_control:**
- Read [scara_description/ros2_control.md](scara_description/ros2_control.md)

**...understand coordinate frames:**
- Read [manipulator_description/frames_reference.md](manipulator_description/frames_reference.md)

**...modify or extend the system:**
- Read [manipulator_description/yaml_to_urdf.md](manipulator_description/yaml_to_urdf.md) for parameter system
- Read package structure documents for file organization

**...see what's new:**
- Read [scara_description/CHANGELOG.md](scara_description/CHANGELOG.md)

**...integrate external systems via REST API:**
- Read [rest_api_bridge/API_REFERENCE.md](rest_api_bridge/API_REFERENCE.md) for complete API specification
- Read [rest_api_bridge/API_CLIENT_GUIDE_RU.md](rest_api_bridge/API_CLIENT_GUIDE_RU.md) for Russian client guide
- Read [rest_api_bridge/ENDPOINT_CHANGES.md](rest_api_bridge/ENDPOINT_CHANGES.md) for endpoint migration guide
- Read [rest_api_bridge/TESTING.md](rest_api_bridge/TESTING.md) for testing examples

---

## Key Concepts

### Coordinate Frames
All frames follow **ROS REP-103** convention:
- **X** = Forward (red axis in RViz)
- **Y** = Left (green axis in RViz)
- **Z** = Up (blue axis in RViz)

See [manipulator_description/frames_reference.md](manipulator_description/frames_reference.md) for details.

### Parameter System
Parameters are defined in YAML files and loaded into URDF via xacro:
- `manipulator_params.yaml` - Main manipulator parameters
- `scara_params.yaml` - SCARA arm parameters

See [manipulator_description/yaml_to_urdf.md](manipulator_description/yaml_to_urdf.md) for how this works.

### ros2_control Integration
Both manipulator and SCARA support ros2_control:
- Independent controllers for each subsystem
- Action-based trajectory control
- Mock hardware interfaces for testing

See [scara_description/ros2_control.md](scara_description/ros2_control.md) for SCARA control details.

---

## Package Relationships

```
manipulator_description (robot model)
    │
    ├── Base assembly (rail + carriage)
    ├── Selector assembly (vertical lift + gripper)
    ├── Picker assembly (fine adjustment)
    │
    └── scara_description (optional module)
        └── SCARA arm (3-DOF arm)
            └── Attaches to picker_frame

scara_control (SCARA arm control library)
    │
    └── ScaraClient              ── High-level SCARA API
        ├── IK/FK, linear motion, elbow flip
        ├── Optional Z-axis control
        └── Tool trigger (pick/place)

ros_control (unified control interface)
    │
    ├── move_joint_group_server              ── Coordinated joint movement
    ├── gripper_service                      ── Gripper open/close
    ├── get_container_server                 ── Container pick orchestration
    ├── place_container_server               ── Container place orchestration
    ├── navigate_to_address_server           ── Address-based platform navigation
    ├── extract_box_server                   ── Box extraction (navigate + SCARA hook)
    ├── return_box_server                    ── Box return (navigate + SCARA hook push)
    └── pick_items_from_warehouse_server     ── Orchestrator: extract box + pick + place

manipulator_bringup (system startup)
    │
    └── manipulator_bringup.launch.py
        ├── Starts robot_state_publisher
        ├── Starts controller_manager + controllers
        ├── Starts all ros_control nodes
        └── Optionally starts RViz2
```

The SCARA arm is a **modular, reusable component** that can be:
- Used standalone
- Attached to manipulator_description
- Integrated with other robots

---

## Quick Reference

### Launch Commands

**Full system (recommended):**
```bash
ros2 launch manipulator_bringup manipulator_bringup.launch.py use_scara:=true
```

**Manipulator only:**
```bash
ros2 launch manipulator_bringup manipulator_bringup.launch.py
```

**Without visualization:**
```bash
ros2 launch manipulator_bringup manipulator_bringup.launch.py use_scara:=true rviz:=false
```

**Visualization only (no control):**
```bash
ros2 launch manipulator_description display.launch.py use_scara:=true
```

**SCARA standalone:**
```bash
ros2 launch scara_description display.launch.py
```

### Action Commands

```bash
# Move joints
ros2 action send_goal /move_joint_group ros_control/action/MoveJointGroup \
  "{joint_names: ['base_main_frame_joint'], target_positions: [1.5], max_velocity: [0.5]}"

# Pick container
ros2 action send_goal /get_container ros_control/action/GetContainer "{}" --feedback

# Place container
ros2 action send_goal /place_container ros_control/action/PlaceContainer "{}" --feedback

# Return box to shelf
ros2 action send_goal /return_box ros_control/action/ReturnBox \
  "{box: {side: 'left', cabinet_num: 2, row: 1, column: 0}, box_id: 'box_l_2_1_0'}" --feedback

# Pick medicines from shelf (orchestrator)
ros2 action send_goal /PickItems ros_control/action/PickItemsFromWarehouse \
  "{detection: [{image_id: 'med-001', row_id: 0, box_center: {x: 0.0, y: 0.0, z: 0.0}}], box: {side: 'left', cabinet_num: 2, row: 1, column: 0}}" --feedback
```

### Service Commands

```bash
# Open gripper
ros2 service call /gripper/open std_srvs/srv/Trigger

# Close gripper
ros2 service call /gripper/close std_srvs/srv/Trigger
```

### REST API Commands

```bash
# Start REST API server
ros2 run rest_api_bridge rest_api_server

# Health check
curl http://localhost:8080/api/v1/health

# Get JWT token
curl -X POST http://localhost:8080/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "wms_system", "client_secret": "demo_secret_2024"}'

# Get medicine (with authentication)
curl -X POST http://localhost:8080/api/v1/get_items \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"side": "left", "cabinet_num": 2, "row": 1, "column": 0, "item_count": 1}'

# Interactive API docs
# Open browser: http://localhost:8080/api/v1/docs
```

### Configuration Files

- `src/manipulator_description/config/manipulator_params.yaml` - Main manipulator parameters
- `src/manipulator_description/config/manipulator_controllers.yaml` - Manipulator controllers
- `src/scara_description/config/scara_params.yaml` - SCARA parameters + ScaraClient config
- `src/scara_description/config/scara_controllers.yaml` - SCARA controllers
- `src/ros_control/config/move_joint_group_config.yaml` - Joint movement server config
- `src/ros_control/config/gripper_config.yaml` - Gripper service config
- `src/ros_control/config/get_container_config.yaml` - GetContainer server config
- `src/ros_control/config/place_container_config.yaml` - PlaceContainer server config
- `src/ros_control/config/extract_box_config.yaml` - ExtractBox server config
- `src/ros_control/config/return_box_config.yaml` - ReturnBox server config
- `src/ros_control/config/pick_items_from_warehouse_config.yaml` - PickItemsFromWarehouse server config
- `src/rest_api_bridge/config/rest_api_config.yaml` - REST API server and authentication config

### Key Links

- `picker_frame` - Default parent for SCARA mounting
- `scara_base_link` - SCARA mounting point
- `tcp_link` - SCARA tool center point

---

## Contributing

When adding or modifying documentation:

1. **Keep it organized:** Place documentation in the appropriate package subdirectory
2. **Be consistent:** Follow the existing documentation style and structure
3. **Include examples:** Provide practical usage examples
4. **Cross-reference:** Link to related documents
5. **Update this README:** Add new documents to the appropriate sections

---

## Questions?

If you have questions about:
- **System architecture:** See package structure documents
- **System startup:** See [manipulator_bringup/launch_files.md](manipulator_bringup/launch_files.md)
- **Configuration:** See configuration guides
- **Integration:** See integration guides
- **Control:** See ros_control documentation
- **Frames:** See frames reference
- **REST API:** See [rest_api_bridge/API_REFERENCE.md](rest_api_bridge/API_REFERENCE.md) or [API_CLIENT_GUIDE_RU.md](rest_api_bridge/API_CLIENT_GUIDE_RU.md) (Russian)
- **API Testing:** See [rest_api_bridge/TESTING.md](rest_api_bridge/TESTING.md)

For code-related questions, refer to the source code in `src/`.
