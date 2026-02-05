# Manipulator Bringup Launch File Documentation

## Overview

This document describes the `manipulator_bringup.launch.py` launch file, which orchestrates the startup of all infrastructure components for the manipulator ROS2 control system.

---

## Launch File: `manipulator_bringup.launch.py`

### Purpose

The main launch file that starts all infrastructure:
- Robot description (URDF/Xacro processing)
- ros2_control controller manager
- All controllers (manipulator, gripper, optional SCARA)
- Unified control interface (`move_joint_group_server`)
- Gripper service (`gripper_service`) for simple open/close control
- Optional RViz2 visualization

**Most Common Usage:** Launch with `use_scara:=true` to enable the full system including the SCARA arm. This is the recommended configuration for typical operations.

### Key Features

1. **Automatic Controller Discovery**
   - Parses controller YAML files to extract controller->joints mapping
   - No manual configuration needed
   - Single source of truth

2. **Dynamic Parameter Generation**
   - Automatically builds `controller_joints` parameter for `move_joint_group_server`
   - Based on which controllers are actually started

3. **Conditional Component Loading**
   - SCARA components only loaded when `use_scara:=true`
   - RViz only started when `rviz:=true`

---

## Launch Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `use_scara` | `bool` | `false` | Attach SCARA arm to picker_frame. When `true`, starts SCARA controller and includes SCARA in unified control. **Recommended: `true` for most common usage.** |
| `rviz` | `bool` | `true` | Launch RViz2 visualization. When `false`, no visualization window. |
| `use_sim_time` | `bool` | `false` | Use simulation clock. When `true`, all nodes use `/clock` topic. |

### Usage Examples

**Most Common Usage (Recommended):**
```bash
# Full system with SCARA arm and RViz (most common configuration)
ros2 launch manipulator_bringup manipulator_bringup.launch.py use_scara:=true
```

**Other Usage Options:**
```bash
# Basic usage (manipulator only, without SCARA, with RViz)
ros2 launch manipulator_bringup manipulator_bringup.launch.py

# Full system without visualization
ros2 launch manipulator_bringup manipulator_bringup.launch.py use_scara:=true rviz:=false

# With simulation time
ros2 launch manipulator_bringup manipulator_bringup.launch.py use_scara:=true use_sim_time:=true

# Manipulator only without visualization
ros2 launch manipulator_bringup manipulator_bringup.launch.py rviz:=false
```

**Note:** The most common usage pattern is with `use_scara:=true` to enable the full system including the SCARA arm attached to the picker frame. This provides the complete manipulator system with all three subsystems: base manipulator, gripper, and SCARA arm.

---

## Launch Process

### Step-by-Step Execution

```
1. Parse Launch Arguments
   ├─► use_scara (default: false)
   ├─► rviz (default: true)
   └─► use_sim_time (default: false)

2. Load Controller Configuration Files
   ├─► manipulator_controllers.yaml (always loaded by controller_manager)
   └─► scara_controllers.yaml (always loaded by controller_manager, but controller only spawned if use_scara)

3. Extract Controller->Joints Mapping
   ├─► Parse YAML files
   ├─► Extract joints for each controller
   ├─► Skip joint_state_broadcaster
   └─► Build controller_joints dictionary

4. Process URDF/Xacro
   ├─► Load robot.urdf.xacro
   ├─► Pass use_scara argument
   └─► Enable ros2_control

5. Start robot_state_publisher
   └─► Publishes TF tree

6. Start controller_manager
   ├─► Loads hardware interface
   └─► Manages controller lifecycle

7. Spawn Controllers (in order)
   ├─► joint_state_broadcaster (first)
   ├─► manipulator_controller (after broadcaster)
   ├─► gripper_controller (after broadcaster)
   └─► scara_controller (after broadcaster, if use_scara)

8. Start move_joint_group_server (after manipulator_controller)
   ├─► Waits for manipulator_controller to be spawned
   └─► Pass controller_joints parameter

9. Start gripper_service (after gripper_controller)
   ├─► Waits for gripper_controller to be spawned
   └─► Provides /gripper/open and /gripper/close services

10. Start RViz2 (if rviz:=true)
    └─► Loads pre-configured RViz config
```

---

## Controller Mapping Extraction

### How It Works

The launch file includes a Python helper function that:

1. **Loads controller YAML files**
   ```python
   # Always loads
   manipulator_controllers.yaml
   
   # Conditionally loads (if use_scara)
   scara_controllers.yaml
   ```

2. **Extracts controller definitions**
   ```python
   # For each controller in YAML:
   controller_name:
     ros__parameters:
       joints:
         - joint1
         - joint2
         ...
   ```

3. **Builds mapping dictionary**
   ```python
   controller_joints = {
     'manipulator_controller': [
       'base_main_frame_joint',
       'main_frame_selector_frame_joint',
       'selector_frame_picker_frame_joint'
     ],
     'gripper_controller': [
       'selector_left_container_jaw_joint',
       'selector_right_container_jaw_joint'
     ],
     'scara_controller': [  # Only if use_scara
       'scara_shoulder_joint',
       'scara_elbow_joint',
       'scara_wrist_joint'
     ]
   }
   ```

4. **Serializes to JSON and passes to move_joint_group_server**
   ```python
   # ROS2 doesn't support nested dict parameters, so serialize as JSON
   controller_joints_json = json.dumps(controller_joints)

   Node(
     package='ros_control',
     executable='move_joint_group_server.py',
     parameters=[
       {'controller_joints_json': controller_joints_json},
       ...
     ]
   )
   ```

### Example: Controller YAML Structure

**Input (manipulator_controllers.yaml):**
```yaml
manipulator_controller:
  ros__parameters:
    joints:
      - base_main_frame_joint
      - main_frame_selector_frame_joint
      - selector_frame_picker_frame_joint

gripper_controller:
  ros__parameters:
    joints:
      - selector_left_container_jaw_joint
      - selector_right_container_jaw_joint
```

**Extracted Mapping:**
```python
{
  'manipulator_controller': [
    'base_main_frame_joint',
    'main_frame_selector_frame_joint',
    'selector_frame_picker_frame_joint'
  ],
  'gripper_controller': [
    'selector_left_container_jaw_joint',
    'selector_right_container_jaw_joint'
  ]
}
```

### Excluded Controllers

The following controllers are **not** included in the mapping:

- `joint_state_broadcaster` - Not a control controller, only publishes state

**Rationale:** Only controllers that accept commands are included in the unified control interface.

---

## Nodes Started

### 1. robot_state_publisher

**Package:** `robot_state_publisher`  
**Executable:** `robot_state_publisher`  
**Purpose:** Publishes TF tree from URDF description

**Parameters:**
- `robot_description` - URDF XML string (from xacro)
- `use_sim_time` - Use simulation clock

**Topics:**
- `/robot_description` - URDF XML string

**TF:**
- Publishes transform tree for all links

---

### 2. controller_manager (ros2_control_node)

**Package:** `controller_manager`  
**Executable:** `ros2_control_node`  
**Purpose:** Manages controller lifecycle and hardware interface

**Parameters:**
- `robot_description` - URDF XML string (includes hardware interface)
- `manipulator_controllers.yaml` - Controller configurations (always loaded)
- `scara_controllers.yaml` - SCARA controller config (always loaded, but controller only spawned if `use_scara:=true`)

**Services:**
- `/controller_manager/list_controllers` - List active controllers
- `/controller_manager/switch_controllers` - Switch controller states
- `/controller_manager/load_controller` - Load controller
- `/controller_manager/unload_controller` - Unload controller

**Hardware Interface:**
- Loads hardware plugin from URDF (mock_components/GenericSystem by default)

---

### 3. joint_state_broadcaster

**Package:** `controller_manager`  
**Executable:** `spawner`  
**Arguments:** `['joint_state_broadcaster', '--controller-manager', '/controller_manager']`  
**Purpose:** Publishes joint states to `/joint_states` topic

**Spawned:** First (before other controllers)

**Topics:**
- `/joint_states` - Joint positions, velocities, efforts

---

### 4. manipulator_controller

**Package:** `controller_manager`  
**Executable:** `spawner`  
**Arguments:** `['manipulator_controller', '--controller-manager', '/controller_manager']`  
**Purpose:** Trajectory control for main manipulator axes

**Spawned:** After `joint_state_broadcaster` (via event handler)

**Type:** `joint_trajectory_controller/JointTrajectoryController`

**Joints:**
- `base_main_frame_joint` - X-axis rail movement
- `main_frame_selector_frame_joint` - Z-axis vertical lift
- `selector_frame_picker_frame_joint` - Z-axis picker movement

**Actions:**
- `/manipulator_controller/follow_joint_trajectory` - Execute trajectory

---

### 5. gripper_controller

**Package:** `controller_manager`  
**Executable:** `spawner`  
**Arguments:** `['gripper_controller', '--controller-manager', '/controller_manager']`  
**Purpose:** Position control for gripper jaws

**Spawned:** After `joint_state_broadcaster` (via event handler)

**Type:** `forward_command_controller/ForwardCommandController`

**Joints:**
- `selector_left_container_jaw_joint` - Left jaw
- `selector_right_container_jaw_joint` - Right jaw

**Topics:**
- `/gripper_controller/commands` - Position commands (Float64MultiArray)

---

### 6. scara_controller (Conditional)

**Package:** `controller_manager`  
**Executable:** `spawner`  
**Arguments:** `['scara_controller', '--controller-manager', '/controller_manager']`  
**Condition:** `use_scara:=true`  
**Purpose:** Trajectory control for SCARA arm

**Spawned:** After `joint_state_broadcaster` (via event handler, only if use_scara)

**Type:** `joint_trajectory_controller/JointTrajectoryController`

**Joints:**
- `scara_shoulder_joint` - Base rotation
- `scara_elbow_joint` - Arm reach
- `scara_wrist_joint` - End-effector rotation

**Actions:**
- `/scara_controller/follow_joint_trajectory` - Execute trajectory

---

### 7. move_joint_group_server

**Package:** `ros_control`
**Executable:** `move_joint_group_server.py`
**Purpose:** Unified control interface for coordinating multiple controllers

**Spawned:** After `manipulator_controller` (via event handler)

**Why Delayed Startup:**
- Controller discovery runs on node initialization
- If started before controllers are active, discovery fails
- Delaying until after `manipulator_controller` ensures controllers are available

**Parameters:**
- `use_sim_time` - Use simulation clock
- `controller_joints_json` - **Auto-generated** controller->joints mapping as JSON string (ROS2 doesn't support nested dict params)
- `move_joint_group_config.yaml` - Server configuration

**Node Creation:**
Uses `OpaqueFunction` to create the node at launch time, which allows:
- Resolving file paths at runtime
- Extracting controller joints from YAML files
- Serializing to JSON string

**Actions:**
- `/move_joint_group` - Coordinated joint movement

**How controller_joints_json is Generated:**

```python
import yaml
import json

def get_controller_joints(manip_controllers_file, scara_controllers_file, use_scara):
    """Extract controller->joints mapping from YAML files"""
    controller_joints = {}

    # Parse manipulator controllers
    with open(manip_controllers_file) as f:
        manip_config = yaml.safe_load(f)

    # Extract manipulator_controller
    if 'manipulator_controller' in manip_config:
        if 'ros__parameters' in manip_config['manipulator_controller']:
            joints = manip_config['manipulator_controller']['ros__parameters'].get('joints', [])
            if joints:
                controller_joints['manipulator_controller'] = joints

    # Extract gripper_controller
    if 'gripper_controller' in manip_config:
        if 'ros__parameters' in manip_config['gripper_controller']:
            joints = manip_config['gripper_controller']['ros__parameters'].get('joints', [])
            if joints:
                controller_joints['gripper_controller'] = joints

    # Parse SCARA controllers if enabled
    if use_scara:
        with open(scara_controllers_file) as f:
            scara_config = yaml.safe_load(f)
        if 'scara_controller' in scara_config:
            if 'ros__parameters' in scara_config['scara_controller']:
                joints = scara_config['scara_controller']['ros__parameters'].get('joints', [])
                if joints:
                    controller_joints['scara_controller'] = joints

    return controller_joints

# In create_move_joint_group_server():
controller_joints = get_controller_joints(manip_file, scara_file, use_scara_val)

# Serialize to JSON (ROS2 doesn't support nested dict params)
controller_joints_json = json.dumps(controller_joints)
```

**Example Generated Parameter (JSON string):**
```json
{"manipulator_controller": ["base_main_frame_joint", "main_frame_selector_frame_joint", "selector_frame_picker_frame_joint"], "gripper_controller": ["selector_left_container_jaw_joint", "selector_right_container_jaw_joint"], "scara_controller": ["scara_shoulder_joint", "scara_elbow_joint", "scara_wrist_joint"]}
```

**Parsed structure (what move_joint_group_server receives after JSON parsing):**
```python
{
  'manipulator_controller': [
    'base_main_frame_joint',
    'main_frame_selector_frame_joint',
    'selector_frame_picker_frame_joint'
  ],
  'gripper_controller': [
    'selector_left_container_jaw_joint',
    'selector_right_container_jaw_joint'
  ],
  'scara_controller': [  # Only if use_scara
    'scara_shoulder_joint',
    'scara_elbow_joint',
    'scara_wrist_joint'
  ]
}
```

---

### 8. gripper_service

**Package:** `ros_control`
**Executable:** `gripper_service.py`
**Purpose:** Simple binary open/close control for gripper jaws

**Spawned:** After `gripper_controller` (via event handler)

**Why Delayed Startup:**
- Requires `gripper_controller` to be active
- Publishes to `/gripper_controller/commands` topic

**Parameters:**
- `use_sim_time` - Use simulation clock
- `gripper_config.yaml` - Gripper configuration (home_position, open_offset)

**Node Creation:**
Uses `OpaqueFunction` similar to `move_joint_group_server`:

```python
def create_gripper_service(context):
    config_file = str(gripper_config_file.perform(context))
    node = Node(
        package='ros_control',
        executable='gripper_service.py',
        name='gripper_service',
        parameters=[
            {'use_sim_time': use_sim_time_val},
            config_file
        ]
    )
    return [node]
```

**Services:**
- `/gripper/open` - Open gripper (jaws apart)
- `/gripper/close` - Close gripper (jaws together)

**Topics Published:**
- `/gripper_controller/commands` - Position commands `[left, right]`

**Configuration:**
```yaml
gripper_service:
  ros__parameters:
    home_position: 0.0      # Open position (jaws apart)
    open_offset: 0.05       # Closing distance (5cm)
```

**See Also:** [gripper_service.md](../ros_control/gripper_service.md)

---

### 9. rviz2 (Conditional)

**Package:** `rviz2`  
**Executable:** `rviz2`  
**Condition:** `rviz:=true`  
**Purpose:** 3D visualization

**Parameters:**
- `use_sim_time` - Use simulation clock

**Config File:**
- Uses pre-configured RViz config from `manipulator_description` package

---

## Execution Order

### Critical Dependencies

Controllers and services must be started in a specific order:

1. **joint_state_broadcaster** (first)
   - Required by all other controllers
   - Publishes joint states

2. **Control controllers** (after broadcaster)
   - `manipulator_controller`
   - `gripper_controller`
   - `scara_controller` (if enabled)
   - These can be spawned in parallel (no dependencies between them)

3. **move_joint_group_server** (after manipulator_controller)
   - Needs controllers to be active for discovery
   - **Delayed startup:** Waits for `manipulator_controller` to be spawned
   - This ensures controllers are active when initial discovery runs

4. **gripper_service** (after gripper_controller)
   - Needs `gripper_controller` to be active
   - **Delayed startup:** Waits for `gripper_controller` to be spawned
   - Provides simple open/close services

### Event Handlers

The launch file uses ROS2 launch event handlers to ensure proper ordering:

```python
# Spawn manipulator_controller after joint_state_broadcaster
RegisterEventHandler(
    event_handler=OnProcessExit(
        target_action=spawn_joint_state_broadcaster,
        on_exit=[spawn_manipulator_controller]
    )
)

# Start move_joint_group_server after manipulator_controller is spawned
RegisterEventHandler(
    event_handler=OnProcessExit(
        target_action=spawn_manipulator_controller,
        on_exit=[move_joint_group_server_action]
    )
)

# Start gripper_service after gripper_controller is spawned
RegisterEventHandler(
    event_handler=OnProcessExit(
        target_action=spawn_gripper_controller,
        on_exit=[gripper_service_action]
    )
)
```

This ensures:
- Controllers are spawned only after `joint_state_broadcaster` is active
- `move_joint_group_server` starts only after `manipulator_controller` is spawned, guaranteeing controllers are available for discovery
- `gripper_service` starts only after `gripper_controller` is spawned, guaranteeing the controller topic is available

---

## Configuration Files Used

### Controller Configuration Files

1. **`manipulator_controllers.yaml`**
   - Location: `manipulator_description/config/`
   - Always loaded
   - Defines: `manipulator_controller`, `gripper_controller`

2. **`scara_controllers.yaml`**
   - Location: `scara_description/config/`
   - Loaded only if `use_scara:=true`
   - Defines: `scara_controller`

### Unified Control Configuration

3. **`move_joint_group_config.yaml`**
   - Location: `ros_control/config/`
   - Loaded by `move_joint_group_server`
   - Defines: tolerances, timeouts, execution strategies

4. **`gripper_config.yaml`**
   - Location: `ros_control/config/`
   - Loaded by `gripper_service`
   - Defines: home_position, open_offset, controller_topic

### RViz Configuration

4. **`view_robot.rviz`**
   - Location: `manipulator_description/rviz/`
   - Loaded by RViz2 if `rviz:=true`
   - Pre-configured visualization settings

---

## Troubleshooting

### Controllers Not Starting

**Problem:** Controllers fail to spawn

**Check:**
1. Controller manager is running: `ros2 node list | grep controller_manager`
2. Controllers are declared in YAML files
3. Hardware interface is loaded: `ros2 control list_hardware_interfaces`

**Solution:**
- Check controller YAML syntax
- Verify hardware interface plugin is correct
- Check launch file logs for errors

### move_joint_group_server Not Discovering Controllers

**Problem:** Server reports "Joints not found"

**Check:**
1. `controller_joints_json` parameter is passed correctly (check launch output for debug messages)
2. Controller names match exactly (case-sensitive)
3. Joint names match exactly

**Solution:**
- Check launch output for "[manipulator_bringup] Extracted controller joints:" messages
- Verify controller_joints_json parameter is being serialized correctly
- Check that controllers are actually started
- Verify joint names in controller YAML files

### SCARA Controller Not Starting

**Problem:** SCARA controller doesn't spawn even with `use_scara:=true`

**Check:**
1. `use_scara` argument is passed correctly
2. SCARA controllers YAML is loaded
3. SCARA hardware interface is in URDF

**Solution:**
- Verify `use_scara:=true` in launch command
- Check `scara_controllers.yaml` exists and is valid
- Verify URDF includes SCARA ros2_control when `use_scara:=true`

---

## Related Documentation

- **Package Structure**: [package_structure.md](package_structure.md) - Overall package architecture
- **Manipulator Controllers**: `../manipulator_description/package_structure.md`
- **SCARA Controllers**: `../scara_description/ros2_control.md`
- **Unified Control**: `../ros_control/package_structure.md`

