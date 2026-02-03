# Manipulator Description Package Documentation

## Overview

The `manipulator_description` package contains the URDF/Xacro robot description for a rail-mounted robotic manipulator. This package provides the robot model for visualization, simulation, and control.

## Package Structure

```
src/manipulator_description/
├── CMakeLists.txt                    # Build configuration
├── package.xml                       # Package metadata and dependencies
├── config/
│   ├── manipulator_params.yaml       # Robot parameters (mass, inertia, joints)
│   └── manipulator_controllers.yaml  # ros2_control controller configuration
├── launch/
│   ├── display.launch.py             # RViz visualization launch file
│   └── manipulator_control.launch.py # ros2_control bringup launch file
├── meshes/
│   └── manipulator/
│       ├── base_link.STL             # Railway base mesh
│       ├── main_frame.STL            # Railway carriage mesh
│       ├── selector_frame.STL        # Vertical moving frame mesh
│       ├── left_container_jaw.STL    # Left gripper jaw mesh
│       ├── right_container_jaw.STL   # Right gripper jaw mesh
│       └── picker_frame.STL          # Picker frame mesh
├── rviz/
│   └── view_robot.rviz               # RViz configuration file
└── urdf/
    ├── robot.urdf.xacro              # Main robot assembly file
    ├── materials.xacro               # Material/color definitions
    └── manipulator/
        ├── manipulator.urdf.xacro           # Manipulator top-level assembly
        ├── manipulator_base.urdf.xacro      # Base assembly (base_link + main_frame)
        ├── manipulator_selector.urdf.xacro  # Selector assembly (selector_frame + jaws)
        ├── manipulator_picker.urdf.xacro    # Picker assembly (picker_frame)
        └── manipulator_ros2_control.urdf.xacro  # ros2_control hardware interface
```

---

## File Descriptions

### Build Files

#### `CMakeLists.txt`
CMake build configuration for the ROS2 package.
- Finds required dependencies: `ament_cmake`, `urdf`, `xacro`, `ros2_control`, `controller_manager`
- Installs directories: `urdf`, `config`, `launch`, `meshes`, `rviz`

#### `package.xml`
ROS2 package manifest defining:
- Package name: `manipulator_description`
- Version: `0.1.0`
- Dependencies:
  - Build: `ament_cmake`
  - Runtime: `urdf`, `xacro`, `robot_state_publisher`, `joint_state_publisher_gui`, `rviz2`
  - ros2_control: `ros2_control`, `ros2_controllers`, `controller_manager`, `hardware_interface`

---

### Configuration Files

#### `config/manipulator_params.yaml`
Central configuration file containing all robot parameters organized by assembly:

```yaml
base_assembly:
  base_link:
    mesh: "base_link.STL"
    color: [R, G, B, A]
    inertial: {mass, origin, inertia}
  main_frame: ...
  base_main_frame_joint: {type, origin, axis, limits, dynamics}

selector_assembly:
  selector_frame: ...
  left_container_jaw: ...
  right_container_jaw: ...
  # Joint definitions...

picker_assembly:
  picker_frame: ...
  selector_frame_picker_frame_joint: ...
```

**Parameters for each link:**
| Parameter | Description |
|-----------|-------------|
| `mesh` | STL filename |
| `color` | RGBA color values [0-1] |
| `inertial.mass` | Mass in kg |
| `inertial.origin.xyz` | Center of mass position [m] |
| `inertial.origin.rpy` | Center of mass orientation [rad] |
| `inertial.inertia` | Inertia tensor (ixx, ixy, ixz, iyy, iyz, izz) |

**Parameters for each joint:**
| Parameter | Description |
|-----------|-------------|
| `type` | Joint type (prismatic, revolute, fixed) |
| `origin.xyz` | Joint position relative to parent [m] |
| `origin.rpy` | Joint orientation relative to parent [rad] |
| `axis` | Motion axis [x, y, z] |
| `limits.lower/upper` | Joint position limits [m or rad] |
| `limits.effort` | Maximum force/torque [N or Nm] |
| `limits.velocity` | Maximum velocity [m/s or rad/s] |
| `dynamics.damping` | Damping coefficient |
| `dynamics.friction` | Friction coefficient |

#### `config/manipulator_controllers.yaml`
ros2_control controller configuration file defining three controllers:

```yaml
controller_manager:
  ros__parameters:
    update_rate: 100  # Hz
    joint_state_broadcaster:
      type: joint_state_broadcaster/JointStateBroadcaster
    manipulator_controller:
      type: joint_trajectory_controller/JointTrajectoryController
    gripper_controller:
      type: forward_command_controller/ForwardCommandController
```

**Controllers:**

| Controller | Type | Purpose |
|------------|------|---------|
| `joint_state_broadcaster` | JointStateBroadcaster | Publishes joint states to `/joint_states` |
| `manipulator_controller` | JointTrajectoryController | Trajectory control for main axes |
| `gripper_controller` | ForwardCommandController | Direct position control for gripper jaws |

**Manipulator Controller Joints (3):**
- `base_main_frame_joint` - X-axis rail movement
- `main_frame_selector_frame_joint` - Z-axis vertical lift
- `selector_frame_picker_frame_joint` - Z-axis picker movement

**Gripper Controller Joints (2):**
- `selector_left_container_jaw_joint` - Left jaw (-Y axis)
- `selector_right_container_jaw_joint` - Right jaw (+Y axis, mirrored)

---

### Launch Files

#### `launch/display.launch.py`
Python launch file for visualizing the robot in RViz2.

**Nodes launched:**
1. `robot_state_publisher` - Publishes robot transforms
2. `joint_state_publisher_gui` - GUI for manual joint control
3. `rviz2` - 3D visualization

**Launch arguments:**
| Argument | Default | Description |
|----------|---------|-------------|
| `use_sim_time` | `false` | Use simulation clock |
| `gui` | `true` | Launch joint_state_publisher_gui |

**Usage:**
```bash
ros2 launch manipulator_description display.launch.py
ros2 launch manipulator_description display.launch.py gui:=false
```

#### `launch/manipulator_control.launch.py`
Python launch file for ros2_control with hardware interface.

**Nodes launched:**
1. `robot_state_publisher` - Publishes robot transforms
2. `ros2_control_node` - Controller manager with hardware interface
3. `spawner` (x3) - Spawns controllers (joint_state_broadcaster, manipulator_controller, gripper_controller)
4. `rviz2` - 3D visualization (optional)

**Launch arguments:**
| Argument | Default | Description |
|----------|---------|-------------|
| `use_sim_time` | `false` | Use simulation clock |
| `rviz` | `true` | Launch RViz2 |
| `use_scara` | `false` | Attach SCARA arm to picker_frame |

**Usage:**
```bash
# Launch with RViz
ros2 launch manipulator_description manipulator_control.launch.py

# Launch without RViz
ros2 launch manipulator_description manipulator_control.launch.py rviz:=false

# Launch with SCARA arm
ros2 launch manipulator_description manipulator_control.launch.py use_scara:=true
```

---

### Mesh Files

#### `meshes/manipulator/`
STL mesh files for robot visualization and collision detection.

| File | Description | Associated Link |
|------|-------------|-----------------|
| `base_link.STL` | Railway base/track | `base_link` |
| `main_frame.STL` | Railway carriage | `main_frame` |
| `selector_frame.STL` | Vertical moving frame | `selector_frame` |
| `left_container_jaw.STL` | Left gripper jaw | `left_container_jaw` |
| `right_container_jaw.STL` | Right gripper jaw | `right_container_jaw` |
| `picker_frame.STL` | Picker vertical frame | `picker_frame` |

**Notes:**
- All meshes are in STL format
- Units: meters (no scaling required)
- Origin: Aligned with link frame origin

---

### RViz Configuration

#### `rviz/view_robot.rviz`
Pre-configured RViz2 layout with:
- Grid display (XY plane)
- RobotModel display (from `/robot_description` topic)
- TF display (coordinate frames)
- Orbit camera view centered on robot

---

### URDF/Xacro Files

#### `urdf/robot.urdf.xacro`
**Main robot assembly file** - Entry point for the robot description.

```xml
<robot name="manipulator_system">
  <!-- Includes -->
  <xacro:include filename=".../materials.xacro"/>
  <xacro:include filename=".../manipulator/manipulator.urdf.xacro"/>

  <!-- World frame -->
  <link name="world"/>

  <!-- Instantiate manipulator -->
  <xacro:manipulator config_file=".../manipulator_params.yaml"/>

  <!-- Attach to world -->
  <joint name="world_to_base" type="fixed">
    <parent link="world"/>
    <child link="base_link"/>
  </joint>
</robot>
```

#### `urdf/materials.xacro`
Material definitions for visualization colors:
- `manipulator_dark_grey`
- `rail_silver`
- `selector_orange`
- `gripper_black`

#### `urdf/manipulator/manipulator.urdf.xacro`
Top-level manipulator macro that combines all sub-assemblies:

```xml
<xacro:macro name="manipulator" params="config_file">
  <xacro:base_assembly .../>
  <xacro:selector_assembly .../>
  <xacro:picker_assembly .../>
</xacro:macro>
```

#### `urdf/manipulator/manipulator_base.urdf.xacro`
Base assembly containing:
- `base_link` - Railway base (static)
- `main_frame` - Railway carriage (moves on X-axis)
- `base_main_frame_joint` - Prismatic joint (X-axis)

#### `urdf/manipulator/manipulator_selector.urdf.xacro`
Selector assembly containing:
- `selector_frame` - Vertical moving frame
- `left_container_jaw` - Left gripper jaw
- `right_container_jaw` - Right gripper jaw
- Associated joints for Z-axis and Y-axis motion

#### `urdf/manipulator/manipulator_picker.urdf.xacro`
Picker assembly containing:
- `picker_frame` - Picker vertical frame
- `selector_frame_picker_frame_joint` - Prismatic joint (Z-axis)

#### `urdf/manipulator/manipulator_ros2_control.urdf.xacro`
ros2_control hardware interface definition macro.

**Hardware Plugin:** `mock_components/GenericSystem` (for testing without real hardware)

**Controlled Joints (5):**

| Joint | Interface | Limits |
|-------|-----------|--------|
| `base_main_frame_joint` | position | 0.0 to 4.0m |
| `main_frame_selector_frame_joint` | position | -0.01 to 1.5m |
| `selector_left_container_jaw_joint` | position | -0.2 to 0.2m |
| `selector_right_container_jaw_joint` | position | -0.2 to 0.2m |
| `selector_frame_picker_frame_joint` | position | -0.01 to 0.3m |

**Each joint provides:**
- `command_interface`: position
- `state_interface`: position, velocity

**Switching to Real Hardware:**
Replace the mock plugin with your custom hardware interface:
```xml
<!-- Change from -->
<plugin>mock_components/GenericSystem</plugin>

<!-- To your hardware interface -->
<plugin>your_package/YourHardwareInterface</plugin>
```

---

## Robot Kinematic Structure

### Links (7 total)

| # | Link Name | Description | Mesh |
|---|-----------|-------------|------|
| 1 | `world` | Reference frame | None |
| 2 | `base_link` | Railway base | base_link.STL |
| 3 | `main_frame` | Railway carriage | main_frame.STL |
| 4 | `selector_frame` | Vertical moving frame | selector_frame.STL |
| 5 | `left_container_jaw` | Left gripper jaw | left_container_jaw.STL |
| 6 | `right_container_jaw` | Right gripper jaw | right_container_jaw.STL |
| 7 | `picker_frame` | Picker frame | picker_frame.STL |

### Joints (6 total)

| # | Joint Name | Type | Parent | Child | Axis | Limits |
|---|------------|------|--------|-------|------|--------|
| 1 | `world_to_base` | fixed | world | base_link | - | - |
| 2 | `base_main_frame_joint` | prismatic | base_link | main_frame | X | 0 to 4m |
| 3 | `main_frame_selector_frame_joint` | prismatic | main_frame | selector_frame | Z | -0.01 to 1.5m |
| 4 | `selector_left_container_jaw_joint` | prismatic | selector_frame | left_container_jaw | -Y | -0.2 to 0.2m |
| 5 | `selector_right_container_jaw_joint` | prismatic | selector_frame | right_container_jaw | +Y | -0.2 to 0.2m |
| 6 | `selector_frame_picker_frame_joint` | prismatic | selector_frame | picker_frame | Z | -0.01 to 0.3m |

### Kinematic Tree

```
world
 └── [world_to_base: fixed]
     └── base_link
         └── [base_main_frame_joint: prismatic X]
             └── main_frame
                 └── [main_frame_selector_frame_joint: prismatic Z]
                     └── selector_frame
                         ├── [selector_left_container_jaw_joint: prismatic -Y]
                         │   └── left_container_jaw
                         ├── [selector_right_container_jaw_joint: prismatic +Y]
                         │   └── right_container_jaw
                         └── [selector_frame_picker_frame_joint: prismatic Z]
                             └── picker_frame
```

---

## Usage

### Build the Package

```bash
cd /home/akhmedov/manipulator_ros_control
colcon build --symlink-install
source install/setup.bash
```

### Visualize in RViz

```bash
ros2 launch manipulator_description display.launch.py
```

### Generate URDF from Xacro

```bash
ros2 run xacro xacro src/manipulator_description/urdf/robot.urdf.xacro > robot.urdf
```

### Check URDF for Errors

```bash
check_urdf robot.urdf
```

### View TF Tree

```bash
ros2 run tf2_tools view_frames
```

---

## Modifying the Robot

### Adding a New Link

1. Add mesh file to `meshes/manipulator/`
2. Add link parameters to `config/manipulator_params.yaml`
3. Add link and joint definitions to appropriate xacro file
4. Rebuild: `colcon build --symlink-install`

### Updating Mesh Files

1. Replace STL file in `meshes/manipulator/`
2. Update inertial parameters in `config/manipulator_params.yaml`:
   - `mass` - From CAD mass properties
   - `inertial.origin.xyz` - Center of mass from CAD
   - `inertial.inertia` - Inertia tensor from CAD
3. Update joint origins if attachment points changed

### Changing Joint Limits

Edit `config/manipulator_params.yaml`:
```yaml
base_main_frame_joint:
  limits: {lower: 0.0, upper: 4.0, effort: 2000.0, velocity: 2.0}
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `urdf` | URDF parsing |
| `xacro` | XML macro processing |
| `robot_state_publisher` | Publish TF transforms |
| `joint_state_publisher_gui` | Manual joint control GUI |
| `rviz2` | 3D visualization |
| `ros2_control` | Hardware abstraction layer |
| `ros2_controllers` | Standard controller implementations |
| `controller_manager` | Controller lifecycle management |
| `hardware_interface` | Hardware interface base classes |

---

## ROS2 Topics

When running `display.launch.py`:

| Topic | Type | Description |
|-------|------|-------------|
| `/robot_description` | `std_msgs/String` | URDF XML string |
| `/joint_states` | `sensor_msgs/JointState` | Current joint positions |
| `/tf` | `tf2_msgs/TFMessage` | Transform tree |
| `/tf_static` | `tf2_msgs/TFMessage` | Static transforms |

---

## ros2_control

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Your ROS2 Application                        │
│  (sends trajectory goals, gripper commands, reads joint states) │
└─────────────────────────────┬───────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ manipulator_    │  │ gripper_        │  │ joint_state_    │
│ controller      │  │ controller      │  │ broadcaster     │
│ (Trajectory)    │  │ (Forward Cmd)   │  │                 │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │
         └────────────────────┼────────────────────┘
                              ▼
                  ┌───────────────────────┐
                  │   Controller Manager   │
                  │   (100 Hz loop)        │
                  └───────────┬───────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │   Hardware Interface   │
                  │   (mock_components/    │
                  │    GenericSystem)      │
                  └───────────────────────┘
```

### Topics and Actions

When running `manipulator_control.launch.py`:

| Interface | Type | Description |
|-----------|------|-------------|
| `/joint_states` | Topic | Current joint positions/velocities |
| `/manipulator_controller/follow_joint_trajectory` | Action | Send trajectory goals |
| `/gripper_controller/commands` | Topic | Send gripper position commands |
| `/controller_manager/*` | Services | Controller lifecycle management |

### Usage Examples

**Move main axes (trajectory):**
```bash
ros2 action send_goal /manipulator_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory "{
    trajectory: {
      joint_names: [base_main_frame_joint, main_frame_selector_frame_joint, selector_frame_picker_frame_joint],
      points: [
        {positions: [1.5, 0.5, 0.1], time_from_start: {sec: 2, nanosec: 0}}
      ]
    }
  }"
```

**Open gripper (jaws move apart):**
```bash
ros2 topic pub --once /gripper_controller/commands \
  std_msgs/msg/Float64MultiArray "{data: [0.1, -0.1]}"
```

**Close gripper (jaws move together):**
```bash
ros2 topic pub --once /gripper_controller/commands \
  std_msgs/msg/Float64MultiArray "{data: [0.0, 0.0]}"
```

**Set specific gripper width (e.g., 0.2m between jaws):**
```bash
ros2 topic pub --once /gripper_controller/commands \
  std_msgs/msg/Float64MultiArray "{data: [0.1, -0.1]}"
```

**Check controller status:**
```bash
ros2 control list_controllers
```

**List hardware interfaces:**
```bash
ros2 control list_hardware_interfaces
```

### Gripper Control Notes

The gripper has two jaws that move in opposite Y directions:
- `selector_left_container_jaw_joint` moves on **-Y axis**
- `selector_right_container_jaw_joint` moves on **+Y axis**

For symmetric (mirrored) gripper behavior, send **opposite values**:
- Open: `[+value, -value]` (e.g., `[0.1, -0.1]`)
- Close: `[0.0, 0.0]`

The total gripper width = `|left_position| + |right_position|`
