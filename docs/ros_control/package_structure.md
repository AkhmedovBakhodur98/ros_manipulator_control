# ros_control Package Documentation

## Overview

The `ros_control` package provides a unified ROS2 control interface for moving multiple joints simultaneously across different controllers (manipulator, SCARA, gripper, and future equipment). It implements a high-level action server that coordinates movement across multiple low-level controllers, abstracting away the complexity of managing different controller types and interfaces.

## Package Structure

```
src/ros_control/
├── CMakeLists.txt                    # Build configuration
├── package.xml                       # Package metadata and dependencies
├── README.md                         # Quick start guide
├── action/
│   ├── MoveJointGroup.action         # Joint movement action definition
│   ├── GetContainer.action           # Container pick action definition
│   ├── PlaceContainer.action         # Container place action definition
│   ├── NavigateToAddress.action      # Address-based navigation action definition
│   ├── ExtractBox.action             # Box extraction action definition
│   └── PickItemsFromWarehouse.action # Medicine picking orchestrator action definition
├── msg/
│   ├── Address.msg                   # Cabinet cell address message
│   └── Medicament.msg               # Medicine metadata message
├── config/
│   ├── move_joint_group_config.yaml  # MoveJointGroup server configuration
│   ├── gripper_config.yaml           # Gripper service configuration
│   ├── get_container_config.yaml     # GetContainer server configuration
│   ├── place_container_config.yaml   # PlaceContainer server configuration
│   ├── navigate_to_address_config.yaml  # NavigateToAddress server configuration
│   ├── extract_box_config.yaml       # ExtractBox server configuration
│   └── pick_items_from_warehouse_config.yaml # PickItemsFromWarehouse server configuration
├── launch/
│   ├── move_joint_group_server.launch.py  # Launch file for MoveJointGroup action server
│   └── extract_box_server.launch.py       # Launch file for ExtractBox action server
└── src/
    ├── move_joint_group_server.py    # Joint movement action server
    ├── gripper_service.py            # Gripper open/close services
    ├── get_container_server.py       # Container pick orchestration server
    ├── place_container_server.py     # Container place orchestration server
    ├── navigate_to_address_server.py # Address-based platform navigation server
    ├── extract_box_server.py         # Box extraction orchestration server
    └── pick_items_from_warehouse_server.py # Medicine picking orchestrator server
```

---

## File Descriptions

### Build Files

#### `CMakeLists.txt`
CMake build configuration for the ROS2 package.

**Key sections:**
- **Action/message generation**: Generates ROS2 interfaces from `MoveJointGroup.action`, `GetContainer.action`, `PlaceContainer.action`, `NavigateToAddress.action`, `ExtractBox.action`, `PickItemsFromWarehouse.action`, `Address.msg`, `Medicament.msg`
- **Python script installation**: Installs `move_joint_group_server.py`, `gripper_service.py`, `get_container_server.py`, `place_container_server.py`, `navigate_to_address_server.py`, `extract_box_server.py`, `pick_items_from_warehouse_server.py` as executables
- **Resource installation**: Installs `config/` and `launch/` directories

**Dependencies:**
- `ament_cmake` - ROS2 build system
- `rosidl_default_generators` - For generating action interfaces

#### `package.xml`
ROS2 package manifest defining package metadata and dependencies.

**Package information:**
- Name: `ros_control`
- Version: `0.1.0`
- Description: Unified ROS2 control interface for manipulator, SCARA, and other equipment
- License: Apache-2.0

**Dependencies:**

| Category | Package | Purpose |
|----------|---------|---------|
| **Build** | `ament_cmake` | ROS2 build system |
| **Action** | `rosidl_default_generators` | Generate action interfaces |
| **Action** | `rosidl_default_runtime` | Runtime support for generated interfaces |
| **ROS2 Core** | `rclpy` | ROS2 Python client library |
| **Messages** | `sensor_msgs` | JointState messages |
| **Messages** | `control_msgs` | FollowJointTrajectory action |
| **Messages** | `std_msgs` | Standard message types |
| **Messages** | `trajectory_msgs` | JointTrajectory messages |
| **Messages** | `controller_manager_msgs` | Controller discovery services |
| **Messages** | `builtin_interfaces` | Time and duration types |
| **Control** | `controller_manager` | Controller lifecycle management |
| **Control** | `ros2_control` | Hardware abstraction framework |
| **Python** | `pyyaml` | YAML configuration parsing |

---

### Action Definition

#### `action/MoveJointGroup.action`
Defines the action interface for coordinated joint movement.

**Goal (Request):**
```yaml
string[] joint_names          # Individual joint names (not groups)
float64[] target_positions    # Target positions (meters for prismatic, radians for revolute)
float64[] max_velocity        # Max velocity per joint (0.0 = use default)
```

**Result (Response):**
```yaml
bool success                  # True if joints reached target within tolerance
float64[] final_position     # Actually achieved positions
float64 position_error       # Maximum position error across all joints
float64 execution_time        # Total execution time (seconds)
string message               # Result message (success/error description)
```

**Feedback (Progress Updates):**
```yaml
string[] joint_names         # Joint names being moved
float64[] current_positions  # Current joint positions
float64[] target_positions   # Target joint positions
float32 progress_percentage  # Progress (0-100%)
```

**Usage Example:**
```bash
ros2 action send_goal /move_joint_group \
  ros_control/action/MoveJointGroup "{
    joint_names: ['base_main_frame_joint', 'scara_shoulder_joint'],
    target_positions: [1.5, 0.5],
    max_velocity: [0.5, 1.0]
  }"
```

#### `action/GetContainer.action`
Defines the action interface for container pick operations.

**Goal (Request):**
```yaml
# Empty - trigger only
```

**Result (Response):**
```yaml
bool success           # True if container picked successfully
string message         # Result message
float64 execution_time # Total execution time (seconds)
```

**Feedback (Progress Updates):**
```yaml
string current_step        # Current operation step
float32 progress_percentage # Progress (0-100%)
```

**Feedback Steps:**
| Step | Progress | Description |
|------|----------|-------------|
| Opening gripper | 0% | Sending open command |
| Moving to container | 25% | Moving to pickup position |
| Closing gripper | 50% | Closing gripper + settle time |
| Lifting container | 75% | Lifting selector frame |
| Complete | 100% | Operation finished |

**Usage Example:**
```bash
ros2 action send_goal /get_container ros_control/action/GetContainer "{}" --feedback
```

#### `action/PlaceContainer.action`
Defines the action interface for container place operations (reverse of GetContainer).

**Goal (Request):**
```yaml
# Empty - trigger only
```

**Result (Response):**
```yaml
bool success           # True if container placed successfully
string message         # Result message
float64 execution_time # Total execution time (seconds)
```

**Feedback (Progress Updates):**
```yaml
string current_step        # Current operation step
float32 progress_percentage # Progress (0-100%)
```

**Feedback Steps:**
| Step | Progress | Description |
|------|----------|-------------|
| Moving to place position | 0% | Moving to placement position |
| Opening gripper | 33% | Opening gripper + settle time |
| Retracting | 66% | Lowering selector to clear container |
| Complete | 100% | Operation finished |

**Usage Example:**
```bash
ros2 action send_goal /place_container ros_control/action/PlaceContainer "{}" --feedback
```

#### `action/NavigateToAddress.action`
Defines the action interface for address-based platform navigation.

**Goal (Request):**
```yaml
string side           # Cabinet side: "left" or "right"
uint8 cabinet_num     # Cabinet number (0-based)
uint8 row             # Row within cabinet (0-based)
uint8 column          # Column within cabinet (0-based)
```

**Result (Response):**
```yaml
bool success                          # True if platform reached position
geometry_msgs/Point final_position    # End-effector position [x, y, z] in world frame
float64 position_error                # Maximum position error across all joints
string message                        # Result message
```

**Feedback (Progress Updates):**
```yaml
float64 progress      # Progress (0.0 - 1.0)
string current_phase  # "validating", "computing", "moving", "done"
```

#### `action/ExtractBox.action`
Defines the action interface for box extraction from a cabinet cell.

**Goal (Request):**
```yaml
ros_control/Address box   # Target cell address
```

**Result (Response):**
```yaml
bool success              # True if box successfully extracted
bool box_extracted        # True if extraction sensor triggered (mock: always true)
string box_id             # Box ID (format: box_{side[0]}_{cabinet}_{row}_{col})
float64 execution_time    # Total execution time (seconds)
string message            # Result message
```

**Feedback (Progress Updates):**
```yaml
string current_phase         # "navigating", "extracting", "done"
float32 progress_percentage  # 0-100%
```

#### `action/PickItemsFromWarehouse.action`
Defines the action interface for the medicine picking orchestrator.

**Goal (Request):**
```yaml
ros_control/Medicament[] detection   # List of medicines to pick
ros_control/Address box              # Source box address on the shelf
```

**Result (Response):**
```yaml
bool success                         # True if all items picked and placed
string[] medicine_qr                 # DataMatrix codes of identified medicines
uint8 items_picked                   # Count of successfully picked items
uint8 items_total                    # Total items requested
float64 execution_time               # Total execution time (seconds)
string message                       # Result status message
```

**Feedback (Progress Updates):**
```yaml
string current_phase                 # Phase name (initializing, extracting_box, picking_items, finalizing)
uint8 current_item_index             # Current item (0-based)
uint8 total_items                    # Total items count
float32 progress_percentage          # Overall progress 0-100%
string message                       # Human-readable status
```

#### `msg/Address.msg`
Message type representing a cabinet cell address.

```yaml
string side       # Cabinet side: "left" or "right"
uint8 cabinet_num # Cabinet number (0-based)
uint8 row         # Row within cabinet (0-based)
uint8 column      # Column within cabinet (0-based)
```

#### `msg/Medicament.msg`
Medicine metadata for picking.

```yaml
string image_id                      # Unique image identifier for the medicine
uint8 row_id                         # Row number within the box (0-based)
geometry_msgs/Point box_center       # Approximate center in SCARA base frame (meters)
```

---

### Configuration Files

#### `config/move_joint_group_config.yaml`
Configuration file for the MoveJointGroup action server.

**Configuration Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `position_tolerance` | float | 0.01 | Position tolerance for success (meters/radians) |
| `execution.strategy` | string | "simultaneous" | Execution strategy: "simultaneous" or "coordinated" |
| `execution.max_coordination_time` | float | 10.0 | Max time for coordinated execution (seconds) |
| `execution.timeout` | float | 30.0 | Maximum time to wait for completion (seconds) |
| `discovery.refresh_interval` | float | 5.0 | Controller discovery refresh interval (seconds) |
| `discovery.query_timeout` | float | 2.0 | Timeout for controller queries (seconds) |
| `feedback.publish_rate` | float | 10.0 | Feedback publishing rate (Hz) |

**Execution Strategies:**

1. **`simultaneous`** (default):
   - All joints start moving at once
   - Each joint finishes independently when it reaches its target
   - Faster overall execution
   - Joints may arrive at different times

2. **`coordinated`**:
   - All joints start moving at once
   - All joints arrive at their targets at the same time
   - Calculates timing to synchronize arrival
   - Useful for coordinated motions (e.g., maintaining orientation)

**Example Configuration:**
```yaml
position_tolerance: 0.01

execution:
  strategy: "simultaneous"
  max_coordination_time: 10.0
  timeout: 30.0

discovery:
  refresh_interval: 5.0
  query_timeout: 2.0

feedback:
  publish_rate: 10.0
```

#### `config/gripper_config.yaml`
Configuration file for the gripper service.

**Configuration Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `left_joint` | string | `selector_left_container_jaw_joint` | Left jaw joint name |
| `right_joint` | string | `selector_right_container_jaw_joint` | Right jaw joint name |
| `home_position` | float | `0.0` | Open position (jaws apart) |
| `open_offset` | float | `0.05` | Distance jaws move when closing |
| `controller_topic` | string | `/gripper_controller/commands` | Controller command topic |

#### `config/get_container_config.yaml`
Configuration file for the GetContainer action server.

**Configuration Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `container_position` | dict | - | Target joint positions for pickup |
| `lift_joint` | string | `main_frame_selector_frame_joint` | Joint for Z-axis lift |
| `lift_height` | float | `0.20` | Lift distance (meters) |
| `gripper_settle_time` | float | `1.0` | Wait time after gripper close |
| `timeouts.move_timeout` | float | `30.0` | Movement timeout |
| `timeouts.gripper_timeout` | float | `5.0` | Gripper service timeout |

**Example Configuration:**
```yaml
get_container_server:
  ros__parameters:
    container_position:
      base_main_frame_joint: 1.5
      main_frame_selector_frame_joint: 0.2
    lift_joint: main_frame_selector_frame_joint
    lift_height: 0.20
    gripper_settle_time: 1.0
    timeouts:
      move_timeout: 30.0
      gripper_timeout: 5.0
```

#### `config/place_container_config.yaml`
Configuration file for the PlaceContainer action server.

**Configuration Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `place_position` | dict | - | Target joint positions for placement |
| `retract_joint` | string | `main_frame_selector_frame_joint` | Joint for retraction |
| `retract_distance` | float | `0.10` | Distance to lower after release (meters) |
| `gripper_settle_time` | float | `1.0` | Wait time after gripper open |
| `timeouts.move_timeout` | float | `30.0` | Movement timeout |
| `timeouts.gripper_timeout` | float | `5.0` | Gripper service timeout |

**Example Configuration:**
```yaml
place_container_server:
  ros__parameters:
    place_position:
      base_main_frame_joint: 1.5
      main_frame_selector_frame_joint: 0.2
    retract_joint: main_frame_selector_frame_joint
    retract_distance: 0.10
    gripper_settle_time: 1.0
    timeouts:
      move_timeout: 30.0
      gripper_timeout: 5.0
```

#### `config/navigate_to_address_config.yaml`
Configuration file for the NavigateToAddress action server. Contains cabinet layout parameters and motion settings for platform navigation.

#### `config/extract_box_config.yaml`
Configuration file for the ExtractBox action server.

**Configuration Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hook_grasp.wrist_angle_rad` | float | 1.5708 | Hook orientation angle (sign auto from side) |
| `hook_grasp.z_offset_m` | float | 0.03 | Raise/lower distance to clear handle plate |
| `hook_grasp.z_above_box_m` | float | 0.10 | Raise distance to clear entire box (overhook disengage) |
| `hook_grasp.approach_depth_m` | float | 0.20 | How far arm reaches into cabinet (Y axis) |
| `hook_grasp.approach_x_offset_m` | float | 0.20 | X offset — keeps approach within shoulder limits |
| `hook_grasp.y_inside_m` | float | 0.02 | Extra depth inside box edge |
| `hook_grasp.retract_overshoot_m` | float | 0.38 | How far past Y=0 to retract for full box extraction |
| `hook_grasp.z_lower_velocity` | float | 0.05 | Z lowering velocity (m/s) |
| `motion.approach_velocity` | float | 0.5 | Velocity scaling for approach |
| `motion.retract_velocity` | float | 0.05 | Velocity for linear retraction (m/s) |
| `motion.linear_step_size` | float | 0.005 | Step size for linear retraction (m) |
| `motion.return_home` | bool | true | If true, arm returns to home after retract |
| `timeouts.navigate_timeout` | float | 60.0 | NavigateToAddress timeout (seconds) |
| `timeouts.extract_timeout` | float | 30.0 | SCARA extraction timeout (seconds) |
| `sensor.mock` | bool | true | Use mock sensor (always returns true) |

#### `config/pick_items_from_warehouse_config.yaml`
Configuration file for the PickItemsFromWarehouse action server.

**Key Configuration Sections:**

| Section | Description |
|---------|-------------|
| `safe_heights` | Z heights for safe transit, approach, and pick operations |
| `pick_heights` | Grasp Z, offset, approach offset for two-stage descent |
| `place_positions` | Container drop position (x, y, z) and item spacing |
| `velocities` | Approach, pick, place, and transit velocity settings |
| `timeouts` | Per-item and total timeout enforcement |
| `behavior` | Continue-on-failure, detection retries, settle times |
| `mock` | Mock vision provider enable/disable and grasp offsets |

---

### Source Code

#### `src/move_joint_group_server.py`
Main implementation of the MoveJointGroup action server.

**Class: `MoveJointGroupServer`**

**Key Responsibilities:**
1. **Controller Discovery**: Automatically discovers available controllers and their joints
2. **Joint Mapping**: Maps joints to their controllers and interface types
3. **Goal Execution**: Coordinates movement across multiple controllers
4. **Progress Monitoring**: Monitors joint states and publishes feedback
5. **Error Handling**: Implements fail-all strategy (cancels all goals on failure)

**Main Components:**

| Component | Type | Purpose |
|-----------|------|---------|
| `action_server` | `ActionServer` | Receives MoveJointGroup action goals |
| `joint_state_sub` | `Subscription` | Subscribes to `/joint_states` for current positions |
| `list_controllers_client` | `ServiceClient` | Queries controller manager for active controllers |
| `trajectory_action_clients` | `Dict[ActionClient]` | Action clients for trajectory controllers (created on demand) |
| `topic_publishers` | `Dict[Publisher]` | Publishers for topic-based controllers (created on demand) |

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `discover_controllers()` | Discovers active controllers and maps joints |
| `_get_controller_joints()` | Retrieves joint list for a controller from ROS2 parameters |
| `validate_goal()` | Validates goal request (array lengths, joint existence) |
| `group_joints_by_controller()` | Groups joints by their controllers |
| `execute_goal_callback()` | Main execution handler for action goals |
| `_execute_trajectory_action()` | Sends trajectory goals to action-based controllers |
| `_publish_topic_command()` | Publishes commands to topic-based controllers |
| `_check_joints_reached()` | Checks if joints are within tolerance |
| `_publish_feedback()` | Publishes progress feedback |
| `_cancel_all_active_goals()` | Cancels all active goals (fail-all strategy) |

**Controller Interface Types:**

1. **Action-based** (`JointTrajectoryController`):
   - Uses `FollowJointTrajectory` action
   - Interface: `/{controller_name}/follow_joint_trajectory`
   - Supports velocity constraints and timing

2. **Topic-based** (`ForwardCommandController`):
   - Uses `Float64MultiArray` topic
   - Interface: `/{controller_name}/commands`
   - Direct position commands

**Controller Discovery Process:**

1. Query `controller_manager/list_controllers` service
2. Filter active controllers (skip `joint_state_broadcaster`)
3. For each controller:
   - Get controller type
   - Get joint list from ROS2 `controller_joints` parameter (passed by launch file)
   - Determine interface type (action or topic) based on controller type
   - Map joints to controller
4. Store mapping: `joint_name -> (controller_name, controller_type, interface_name)`

**Note:** The `controller_joints` parameter is a dictionary passed by the launch file with structure:
```python
{
    'controller_name': ['joint1', 'joint2', ...],
    ...
}
```

**Execution Flow:**

1. **Goal Received**: Validate goal request
2. **Discovery Refresh**: Refresh controller discovery if needed
3. **Group Joints**: Group joints by their controllers
4. **Send Commands**:
   - Action controllers: Send trajectory goals asynchronously
   - Topic controllers: Publish position commands
5. **Monitor Progress**:
   - Subscribe to `/joint_states`
   - Check if all joints are within tolerance
   - Publish feedback periodically
6. **Completion**:
   - Success: All joints within tolerance
   - Timeout: Maximum time exceeded
   - Cancellation: User requested cancellation
7. **Fail-All Strategy**: On any failure, cancel all active goals

**Error Handling:**

- **Validation Errors**: Invalid goal (array length mismatch, unknown joints)
- **Controller Errors**: Controller not available, goal rejected
- **Timeout**: Joints don't reach target within timeout
- **Cancellation**: User cancels goal (cancels all active goals)

#### `src/gripper_service.py`
Simple service node for gripper open/close control.

**Class: `GripperService`**

**Services Provided:**

| Service | Type | Description |
|---------|------|-------------|
| `/gripper/open` | `std_srvs/srv/Trigger` | Opens gripper (jaws apart) |
| `/gripper/close` | `std_srvs/srv/Trigger` | Closes gripper (jaws together) |

**Published Topics:**

| Topic | Type | Description |
|-------|------|-------------|
| `/gripper_controller/commands` | `std_msgs/msg/Float64MultiArray` | Position commands `[left, right]` |

**See detailed documentation:** [gripper_service.md](gripper_service.md)

#### `src/get_container_server.py`
High-level action server for container pick operations.

**Class: `GetContainerServer`**

**Key Features:**
- Uses `MultiThreadedExecutor` for async operations
- Coordinates gripper services and MoveJointGroup action
- Implements sequential execution with settle time

**Dependencies:**

| Interface | Type | Purpose |
|-----------|------|---------|
| `/gripper/open` | Service | Open gripper before pickup |
| `/gripper/close` | Service | Close gripper to grab container |
| `/move_joint_group` | Action | Move manipulator joints |

**Execution Flow:**
1. Open gripper
2. Move to container position
3. Close gripper + wait settle time
4. Lift container (Z axis)

**See detailed documentation:** [get_container_server.md](get_container_server.md)

#### `src/place_container_server.py`
High-level action server for container place operations (reverse of GetContainer).

**Class: `PlaceContainerServer`**

**Key Features:**
- Uses `MultiThreadedExecutor` for async operations
- Coordinates MoveJointGroup action and gripper services
- Implements sequential execution with settle time
- Retracts selector after release to clear container

**Dependencies:**

| Interface | Type | Purpose |
|-----------|------|---------|
| `/gripper/open` | Service | Open gripper to release container |
| `/move_joint_group` | Action | Move manipulator joints |

**Execution Flow:**
1. Move to place position
2. Open gripper + wait settle time
3. Retract (lower selector by `retract_distance`)

**See detailed documentation:** [place_container_server.md](place_container_server.md)

#### `src/navigate_to_address_server.py`
Action server for address-based platform navigation.

**Class: `NavigateToAddressServer`**

**Key Features:**
- Translates cabinet cell address (side, cabinet, row, column) into joint positions
- Coordinates platform movement via MoveJointGroup action
- Computes end-effector position using forward kinematics

**Dependencies:**

| Interface | Type | Purpose |
|-----------|------|---------|
| `/move_joint_group` | Action | Move platform joints to target |

#### `src/extract_box_server.py`
High-level action server orchestrating box extraction from a cabinet cell.

**Class: `ExtractBoxServer`**

**Key Features:**
- Coordinates NavigateToAddress and ScaraClient for full extraction sequence
- 3-phase execution: navigate (0-40%), extract with SCARA (40-90%), verify (90-100%)
- Uses TF2 for picker_frame transform lookup
- Supports cancellation at phase boundaries

**Dependencies:**

| Interface | Type | Purpose |
|-----------|------|---------|
| `/navigate_to_address` | Action | Navigate platform to target cell |
| `ScaraClient` | Library | SCARA arm movement (wrist, Z, approach, retract, home) |
| `picker_frame` TF | Transform | SCARA base position in world frame |

**Execution Flow:**
1. Navigate to cell (NavigateToAddress action)
2. Rotate wrist for hook orientation
3. Raise Z to clear handle plate
4. Approach — extend arm into cabinet
5. Lower Z — hook drops into gap
6. Retract — pull box out linearly
7. Return home (optional)
8. Verify with box sensor

#### `src/pick_items_from_warehouse_server.py`
High-level orchestrator action server for the medicine picking workflow.

**Class: `PickItemsFromWarehouseServer`**

**Key Features:**
- Orchestrates full picking workflow: extract box → pick medicines → place into container
- Calls ExtractBox as sub-action with feedback relay (progress 5-40%)
- Uses ScaraClient directly for pick-and-place loop (progress 40-90%)
- VisionProvider abstraction (MockVisionProvider / future RealVisionProvider)
- Per-item and total timeout enforcement
- Detection retries with configurable max attempts
- Two-stage approach descent (safe_z → approach_z → pick_z)
- Cancellation forwarding to ExtractBox sub-goal

**Dependencies:**

| Interface | Type | Purpose |
|-----------|------|---------|
| `/extract_box` | Action | Extract box from shelf (navigate + SCARA hook) |
| `ScaraClient` | Library | SCARA arm pick-and-place movements |
| `/scara_tool/activate` | Service | Activate suction tool (non-fatal if unavailable) |
| `/scara_tool/deactivate` | Service | Deactivate suction tool (non-fatal if unavailable) |

**Execution Flow (4 phases):**
1. **Initialize** (0-5%): Validate goal, create VisionProvider
2. **Extract box** (5-40%): Call ExtractBox action, relay feedback
3. **Pick items** (40-90%): For each medicine: detect → approach → pick → transit → place
4. **Finalize** (90-100%): Return SCARA home, build result

**See detailed documentation:** [pick_items_from_warehouse_action.md](pick_items_from_warehouse_action.md), [pick_items_from_warehouse_server.md](pick_items_from_warehouse_server.md)

---

### Launch Files

#### `launch/move_joint_group_server.launch.py`
Launch file for starting the MoveJointGroup action server.

**See detailed documentation in:** `docs/ros_control/move_joint_group_server_launch.md`

**Quick Summary:**
- Launches `move_joint_group_server.py` node
- Loads configuration from `config/move_joint_group_config.yaml`
- Supports `use_sim_time` parameter for simulation

#### `launch/extract_box_server.launch.py`
Launch file for starting the ExtractBox action server standalone.

**Quick Summary:**
- Launches `extract_box_server.py` node
- Loads configuration from `config/extract_box_config.yaml`
- Supports `use_sim_time` parameter for simulation

---

## Architecture

### System Integration

```
┌─────────────────────────────────────────────────────────────┐
│                    Your Application                          │
│  (sends MoveJointGroup goals, receives feedback/results)    │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│          MoveJointGroup Action Server                        │
│  (ros_control package)                                      │
│  - Discovers controllers                                     │
│  - Coordinates movement across controllers                  │
│  - Monitors progress                                         │
└───────┬───────────────────────┬─────────────────────────────┘
        │                       │
        ▼                       ▼
┌──────────────────┐   ┌──────────────────┐
│  Controller 1    │   │  Controller 2    │
│  (Manipulator)   │   │  (SCARA)         │
│                  │   │                  │
│  Joints:         │   │  Joints:         │
│  - base_main_... │   │  - scara_shoulder│
│  - main_frame_...│   │  - scara_elbow   │
│  - selector_...  │   │  - scara_wrist   │
└────────┬─────────┘   └────────┬─────────┘
         │                      │
         ▼                      ▼
┌─────────────────────────────────────────────┐
│         Controller Manager                   │
│  (ros2_control framework)                   │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│         Hardware Interface                  │
│  (robot hardware abstraction)               │
└─────────────────────────────────────────────┘
```

### Data Flow

1. **Goal Request**:
   ```
   Application → MoveJointGroup Action Server
   ```

2. **Controller Discovery**:
   ```
   Action Server → Controller Manager (list_controllers service)
   Controller Manager → Action Server (controller list)
   ```

3. **Command Execution**:
   ```
   Action Server → Controllers (trajectory actions or topic commands)
   ```

4. **State Monitoring**:
   ```
   Hardware → Joint State Broadcaster → /joint_states topic
   /joint_states → Action Server (monitoring)
   ```

5. **Feedback/Result**:
   ```
   Action Server → Application (feedback during execution, result on completion)
   ```

---

## Dependencies

### ROS2 Packages

| Package | Purpose |
|---------|---------|
| `rclpy` | ROS2 Python client library |
| `sensor_msgs` | JointState messages |
| `control_msgs` | FollowJointTrajectory action interface |
| `std_msgs` | Standard message types |
| `trajectory_msgs` | JointTrajectory message types |
| `controller_manager_msgs` | Controller discovery services |
| `builtin_interfaces` | Time and duration types |
| `controller_manager` | Controller lifecycle management |
| `ros2_control` | Hardware abstraction framework |

### Python Packages

| Package | Purpose |
|---------|---------|
| `pyyaml` | YAML configuration file parsing |

---

## ROS2 Topics

### Subscribed Topics

| Topic | Type | Description |
|-------|------|-------------|
| `/joint_states` | `sensor_msgs/JointState` | Current joint positions, velocities, efforts |

### Published Topics

| Topic | Type | Publisher | Description |
|-------|------|-----------|-------------|
| `/gripper_controller/commands` | `std_msgs/msg/Float64MultiArray` | `gripper_service` | Gripper position commands |

---

## ROS2 Services

### Service Servers

| Service | Type | Provider | Description |
|---------|------|----------|-------------|
| `/gripper/open` | `std_srvs/srv/Trigger` | `gripper_service` | Open gripper |
| `/gripper/close` | `std_srvs/srv/Trigger` | `gripper_service` | Close gripper |

### Service Clients

| Service | Type | Consumer | Description |
|---------|------|----------|-------------|
| `/controller_manager/list_controllers` | `controller_manager_msgs/ListControllers` | `move_joint_group_server` | Query active controllers |
| `/gripper/open` | `std_srvs/srv/Trigger` | `get_container_server` | Open gripper |
| `/gripper/close` | `std_srvs/srv/Trigger` | `get_container_server` | Close gripper |
| `/gripper/open` | `std_srvs/srv/Trigger` | `place_container_server` | Open gripper to release |

---

## ROS2 Actions

### Action Servers

| Action | Type | Provider | Description |
|--------|------|----------|-------------|
| `/move_joint_group` | `ros_control/action/MoveJointGroup` | `move_joint_group_server` | Coordinated joint movement |
| `/get_container` | `ros_control/action/GetContainer` | `get_container_server` | Container pick orchestration |
| `/place_container` | `ros_control/action/PlaceContainer` | `place_container_server` | Container place orchestration |
| `/navigate_to_address` | `ros_control/action/NavigateToAddress` | `navigate_to_address_server` | Address-based platform navigation |
| `/extract_box` | `ros_control/action/ExtractBox` | `extract_box_server` | Box extraction orchestration |
| `/PickItems` | `ros_control/action/PickItemsFromWarehouse` | `pick_items_from_warehouse_server` | Medicine picking orchestrator |

### Action Clients

| Action | Type | Consumer | Description |
|--------|------|----------|-------------|
| `/{controller_name}/follow_joint_trajectory` | `control_msgs/action/FollowJointTrajectory` | `move_joint_group_server` | Trajectory controllers |
| `/move_joint_group` | `ros_control/action/MoveJointGroup` | `get_container_server` | Joint movement |
| `/move_joint_group` | `ros_control/action/MoveJointGroup` | `place_container_server` | Joint movement |
| `/move_joint_group` | `ros_control/action/MoveJointGroup` | `navigate_to_address_server` | Platform movement |
| `/navigate_to_address` | `ros_control/action/NavigateToAddress` | `extract_box_server` | Cell navigation |
| `/extract_box` | `ros_control/action/ExtractBox` | `pick_items_from_warehouse_server` | Box extraction sub-action |

---

## ROS2 Parameters

### Node Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `use_sim_time` | bool | Use simulation clock if true |
| `controller_joints` | dict | Controller-to-joints mapping (passed by launch file) |

**`controller_joints` Parameter Structure:**
```yaml
controller_joints:
  manipulator_controller:
    - base_main_frame_joint
    - main_frame_selector_frame_joint
  picker_z_controller:
    - selector_frame_picker_frame_joint
  scara_controller:
    - scara_shoulder_joint
    - scara_elbow_joint
    - scara_wrist_joint
```

---

## Usage Examples

### Basic Usage

**Launch the server:**
```bash
ros2 launch ros_control move_joint_group_server.launch.py
```

**Move platform + picker joints:**
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

> Note: `move_joint_group_server` automatically discovers that `base_main_frame_joint` and `main_frame_selector_frame_joint` belong to `manipulator_controller`, while `selector_frame_picker_frame_joint` belongs to `picker_z_controller`, and sends goals to both controllers.

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

**Mixed movement (manipulator + SCARA):**
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

**Use default velocities:**
```bash
ros2 action send_goal /move_joint_group \
  ros_control/action/MoveJointGroup "{
    joint_names: ['base_main_frame_joint'],
    target_positions: [2.0],
    max_velocity: [0.0]  # 0.0 = use default velocity
  }"
```

### Python Client Example

```python
import rclpy
from rclpy.action import ActionClient
from ros_control.action import MoveJointGroup

def main():
    rclpy.init()
    node = rclpy.create_node('move_joint_group_client')
    
    action_client = ActionClient(node, MoveJointGroup, '/move_joint_group')
    
    # Wait for server
    action_client.wait_for_server()
    
    # Create goal
    goal = MoveJointGroup.Goal()
    goal.joint_names = ['base_main_frame_joint', 'scara_shoulder_joint']
    goal.target_positions = [1.5, 0.5]
    goal.max_velocity = [0.5, 1.0]
    
    # Send goal
    send_goal_future = action_client.send_goal_async(goal)
    rclpy.spin_until_future_complete(node, send_goal_future)
    goal_handle = send_goal_future.result()
    
    # Wait for result
    result_future = goal_handle.get_result_async()
    rclpy.spin_until_future_complete(node, result_future)
    result = result_future.result().result
    
    print(f"Success: {result.success}")
    print(f"Message: {result.message}")
    print(f"Execution time: {result.execution_time:.2f}s")
    
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
```

---

## Building

```bash
cd /path/to/manipulator_ros_control
colcon build --packages-select ros_control
source install/setup.bash
```

---

## Configuration

### Adjusting Position Tolerance

Edit `config/move_joint_group_config.yaml`:
```yaml
position_tolerance: 0.005  # 5mm or ~0.29 degrees
```

### Changing Execution Strategy

```yaml
execution:
  strategy: "coordinated"  # or "simultaneous"
```

### Adjusting Timeouts

```yaml
execution:
  timeout: 60.0  # Increase timeout for slow movements
```

### Changing Discovery Refresh Rate

```yaml
discovery:
  refresh_interval: 10.0  # Refresh every 10 seconds
```

---

## Troubleshooting

### Controller Not Found

**Problem**: Error "Joints not found: ['joint_name']"

**Solutions**:
1. Ensure controller is active: `ros2 control list_controllers`
2. Check controller_joints parameter is passed correctly by launch file
3. Verify joint names match exactly (case-sensitive)

### Goal Timeout

**Problem**: Goal times out before joints reach target

**Solutions**:
1. Increase `execution.timeout` in config
2. Check joint limits and velocities
3. Verify hardware is responding
4. Check for obstacles or mechanical issues

### Controller Discovery Fails

**Problem**: No controllers discovered

**Solutions**:
1. Ensure controller_manager is running
2. Check controller_manager service: `ros2 service list | grep controller_manager`
3. Verify controllers are active: `ros2 control list_controllers`
4. Check launch file passes controller_joints parameter correctly

---

## Extending the Package

### Adding Support for New Controllers

1. **Add controller to launch file**: Update launch file to pass controller_joints parameter
2. **Verify interface type**: Ensure controller uses either:
   - `JointTrajectoryController` (action-based)
   - `ForwardCommandController` (topic-based)
3. **Test discovery**: Launch server and verify controller is discovered

### Adding New Execution Strategies

1. Edit `src/move_joint_group_server.py`
2. Add new strategy to `_default_config()` in `execution.strategy`
3. Implement strategy logic in `execute_goal_callback()`
4. Update config file documentation

---

## Related Documentation

- **MoveJointGroup Server**: [move_joint_group_server.md](move_joint_group_server.md)
- **Gripper Service**: [gripper_service.md](gripper_service.md)
- **GetContainer Server**: [get_container_server.md](get_container_server.md)
- **PlaceContainer Server**: [place_container_server.md](place_container_server.md)
- **PickItemsFromWarehouse Design**: [pick_items_from_warehouse_action.md](pick_items_from_warehouse_action.md)
- **PickItemsFromWarehouse Server**: [pick_items_from_warehouse_server.md](pick_items_from_warehouse_server.md)
- **Package README**: `src/ros_control/README.md`
- **Manipulator Description**: `docs/manipulator_description/package_structure.md`
- **SCARA Description**: `docs/scara_description/package_structure.md`

