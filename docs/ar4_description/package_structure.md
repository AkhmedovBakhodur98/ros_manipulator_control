# AR4 Description Package Documentation

## Overview

The `ar4_description` package contains the URDF/Xacro robot description for a 6-DOF AR4 robotic arm (AR4 MK3). This package runs **standalone** — it is not integrated with the manipulator system. No Gazebo — only RViz visualization with `mock_components/GenericSystem` for hardware simulation.

## Package Structure

```
src/ar4_description/
├── CMakeLists.txt                    # Build configuration
├── package.xml                       # Package metadata and dependencies
├── config/
│   └── ar4_controllers.yaml          # ros2_control controller configuration
├── meshes/
│   ├── visual/                       # Visual meshes (7 STL files)
│   │   ├── base_link.STL
│   │   ├── link_1.STL
│   │   ├── link_2.STL
│   │   ├── link_3.STL
│   │   ├── link_4.STL
│   │   ├── link_5.STL
│   │   └── link_6.STL
│   └── collision/                    # Collision meshes (7 STL files)
│       ├── base_link.STL
│       ├── link_1.STL
│       ├── link_2.STL
│       ├── link_3.STL
│       ├── link_4.STL
│       ├── link_5.STL
│       └── link_6.STL
├── rviz/
│   └── ar4.rviz                      # RViz config (fixed frame: world)
└── urdf/
    ├── ar4_macro.xacro               # Main AR4 macro (reusable)
    ├── ar4_ros2_control.urdf.xacro   # ros2_control hardware interface
    └── robot.urdf.xacro              # Standalone robot entry point
```

---

## File Descriptions

### Build Files

#### `CMakeLists.txt`
CMake build configuration for the ROS2 package.
- Finds required dependencies: `ament_cmake`, `urdf`, `xacro`
- Installs directories: `urdf`, `config`, `meshes`, `rviz`

#### `package.xml`
ROS2 package manifest defining:
- Package name: `ar4_description`
- Version: `0.1.0`
- Dependencies:
  - Build: `ament_cmake`
  - Runtime: `urdf`, `xacro`, `robot_state_publisher`, `joint_state_publisher_gui`, `rviz2`
  - Runtime: `controller_manager`, `joint_state_broadcaster`, `joint_trajectory_controller`

---

### Configuration Files

#### `config/ar4_controllers.yaml`
Controller configuration for ros2_control.

**Controllers:**
- `joint_state_broadcaster` - Publishes joint states to `/joint_states`
- `arm_controller` - JointTrajectoryController for all 6 arm joints (J1-J6)

**Configuration:**
- Update rate: 100 Hz
- Command interface: position
- State interfaces: position, velocity
- State publish rate: 50 Hz
- Per-joint goal tolerances: 0.05 rad (~3°)

**Note:** No gripper controller — arm only.

---

### Mesh Files

#### `meshes/visual/` and `meshes/collision/`
STL mesh files for robot visualization and collision detection.

| File | Description | Associated Link |
|------|-------------|-----------------|
| `base_link.STL` | Base housing | `base_link` |
| `link_1.STL` | Shoulder | `link1` |
| `link_2.STL` | Upper arm | `link2` |
| `link_3.STL` | Elbow | `link3` |
| `link_4.STL` | Forearm | `link4` |
| `link_5.STL` | Wrist | `link5` |
| `link_6.STL` | Flange | `link6` |

**Notes:**
- All meshes are in STL format
- Units: meters (no scaling required)
- Origin: Aligned with link frame origin
- Visual and collision meshes are separate (identical geometry)

---

### URDF/Xacro Files

#### `urdf/ar4_macro.xacro`
**Main AR4 macro** — defines the 6-DOF arm with all links and joints.

```xml
<xacro:macro name="ar4_robot" params="tf_prefix parent *origin">
  <!-- Creates base_link, link1-6, ee_link -->
  <!-- Creates J1-J6 revolute joints + ee_joint fixed -->
</xacro:macro>
```

**Parameters:**
| Parameter | Required | Description |
|-----------|----------|-------------|
| `tf_prefix` | Yes | Namespace prefix for link/joint names (use `""` for default) |
| `parent` | Yes | Name of the parent link to attach AR4 to |
| `*origin` | Yes | Origin block (xyz, rpy) for base_joint |

**Joint limits are hardcoded as xacro properties** (from AR4 MK3 reference):
- All joints: `effort=1000`, `velocity=1.0472 rad/s` (~60°/s)
- `damping=100.0`, `friction=10.0`

#### `urdf/ar4_ros2_control.urdf.xacro`
**ros2_control hardware interface** for AR4 joints.

**Macro:** `ar4_ros2_control` (no parameters)

**Defines:**
- Hardware plugin: `mock_components/GenericSystem`
- 6 joint interfaces (J1-J6): position command + position/velocity state
- Joint limits hardcoded (matching ar4_macro.xacro values)

**Usage:**
```xml
<xacro:include filename="$(find ar4_description)/urdf/ar4_ros2_control.urdf.xacro"/>
<xacro:ar4_ros2_control/>
```

#### `urdf/robot.urdf.xacro`
**Main entry point** for standalone AR4.

Creates:
- `world` link (reference frame)
- AR4 arm attached to world at origin
- Optional ros2_control hardware interface (when `use_ros2_control:=true`)

**Arguments:**
- `use_ros2_control` (default: `true`) - Enable ros2_control

**Usage:**
```bash
xacro robot.urdf.xacro use_ros2_control:=true > ar4.urdf
```

---

## Robot Kinematic Structure

### Links (8 total)

| # | Link Name | Description | Mesh |
|---|-----------|-------------|------|
| 1 | `base_link` | Base housing | base_link.STL |
| 2 | `link1` | Shoulder | link_1.STL |
| 3 | `link2` | Upper arm | link_2.STL |
| 4 | `link3` | Elbow | link_3.STL |
| 5 | `link4` | Forearm | link_4.STL |
| 6 | `link5` | Wrist | link_5.STL |
| 7 | `link6` | Flange | link_6.STL |
| 8 | `ee_link` | End effector | (no mesh) |

### Joints (8 total)

| # | Joint Name | Type | Parent | Child | Axis | Limits |
|---|------------|------|--------|-------|------|--------|
| 1 | `base_joint` | fixed | world | base_link | - | - |
| 2 | `J1` | revolute | base_link | link1 | Z | ±170° |
| 3 | `J2` | revolute | link1 | link2 | Z | -42° to 90° |
| 4 | `J3` | revolute | link2 | link3 | Z | -89° to 52° |
| 5 | `J4` | revolute | link3 | link4 | Z | ±165° |
| 6 | `J5` | revolute | link4 | link5 | X | ±105° |
| 7 | `J6` | revolute | link5 | link6 | Z | ±155° |
| 8 | `ee_joint` | fixed | link6 | ee_link | - | - |

### Kinematic Tree

```
world
 └── [base_joint: fixed]
     └── base_link
         └── [J1: revolute Z]
             └── link1
                 └── [J2: revolute Z]
                     └── link2
                         └── [J3: revolute Z]
                             └── link3
                                 └── [J4: revolute Z]
                                     └── link4
                                         └── [J5: revolute X]
                                             └── link5
                                                 └── [J6: revolute Z]
                                                     └── link6
                                                         └── [ee_joint: fixed]
                                                             └── ee_link
```

---

## Joint Specifications

| Joint | Range (deg) | Range (rad) | Max Velocity | Max Effort |
|-------|-------------|-------------|--------------|------------|
| J1 | ±170° | ±2.967 | 1.047 rad/s | 1000 |
| J2 | -42° to 90° | -0.733 to 1.571 | 1.047 rad/s | 1000 |
| J3 | -89° to 52° | -1.553 to 0.907 | 1.047 rad/s | 1000 |
| J4 | ±165° | ±2.880 | 1.047 rad/s | 1000 |
| J5 | ±105° | ±1.833 | 1.047 rad/s | 1000 |
| J6 | ±155° | ±2.705 | 1.047 rad/s | 1000 |

---

## Hardware Interface

### Current: Mock Hardware

The default hardware interface uses `mock_components/GenericSystem` for testing:

```xml
<hardware>
  <plugin>mock_components/GenericSystem</plugin>
  <param name="mock_sensor_commands">true</param>
  <param name="state_following_offset">0.0</param>
</hardware>
```

**Features:**
- Simulates joint movement
- Follows commanded positions
- Publishes joint states
- No real hardware required

### Replacing with Real Hardware

To use real hardware, replace the hardware plugin in `ar4_ros2_control.urdf.xacro`:

```xml
<hardware>
  <plugin>your_hardware_package/YourHardwareInterface</plugin>
  <!-- Add your hardware-specific parameters -->
</hardware>
```

---

## Usage

### Build the Package

```bash
cd /home/akhmedov/manipulator_ros_control
colcon build --packages-select ar4_description
source install/setup.bash
```

### Launch with ros2_control (via manipulator_bringup)

```bash
# Launch AR4 standalone with controllers and RViz
ros2 launch manipulator_bringup ar4_bringup.launch.py

# Without RViz
ros2 launch manipulator_bringup ar4_bringup.launch.py rviz:=false
```

### Control the Arm

**Send trajectory goal:**
```bash
ros2 action send_goal /arm_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory "{
    trajectory: {
      joint_names: [J1, J2, J3, J4, J5, J6],
      points: [
        {positions: [0.5, 0.3, -0.3, 0.8, -0.5, 1.0], time_from_start: {sec: 3}},
        {positions: [-0.5, 0.7, 0.4, -0.8, 0.5, -1.0], time_from_start: {sec: 6}}
      ]
    }
  }"
```

**Return to home position:**
```bash
ros2 action send_goal /arm_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory "{
    trajectory: {
      joint_names: [J1, J2, J3, J4, J5, J6],
      points: [{positions: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], time_from_start: {sec: 2}}]
    }
  }"
```

**Monitor joint states:**
```bash
ros2 topic echo /joint_states
```

**Check controller status:**
```bash
ros2 control list_controllers
ros2 control list_hardware_interfaces
```

---

## Topics and Actions

### Topics

| Topic | Type | Description |
|-------|------|-------------|
| `/joint_states` | `sensor_msgs/JointState` | All joint positions/velocities |
| `/arm_controller/controller_state` | `control_msgs/msg/JointTrajectoryControllerState` | Controller state |
| `/arm_controller/joint_trajectory` | `trajectory_msgs/JointTrajectory` | Current trajectory |
| `/robot_description` | `std_msgs/String` | URDF XML string |
| `/tf` | `tf2_msgs/TFMessage` | Transform tree |
| `/tf_static` | `tf2_msgs/TFMessage` | Static transforms |

### Actions

| Action | Type | Description |
|--------|------|-------------|
| `/arm_controller/follow_joint_trajectory` | `control_msgs/action/FollowJointTrajectory` | Execute trajectory |

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `urdf` | URDF parsing |
| `xacro` | XML macro processing |
| `robot_state_publisher` | Publish TF transforms |
| `joint_state_publisher_gui` | Manual joint control GUI |
| `rviz2` | 3D visualization |
| `controller_manager` | Controller lifecycle management |
| `joint_state_broadcaster` | Joint state publishing |
| `joint_trajectory_controller` | Trajectory control |

---

## Related Documentation

- **AR4 Bringup Launch:** `../manipulator_bringup/launch_files.md`
- **AR4 Control Package:** `../ar4_control/package_structure.md`
- **Project Overview:** `../project_structure/overview.md`
