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
  - Runtime: `ar4_hardware_interface`, `controller_manager`, `joint_state_broadcaster`, `joint_trajectory_controller`

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

**Macro:** `ar4_ros2_control` with parameters `serial_port` and `baud_rate`.

**Defines two hardware components:**
1. **`ar4_real_hardware`** — Real hardware via `ar4_hardware_interface/Ar4System` (Teensy 4.1 serial).
   - Controls J1 (base rotation), J2 (shoulder), J3 (elbow), and J5 (wrist pitch) with motor parameters (motor_id, steps_per_rev, gear_ratio, microsteps, home_offset_rad).
2. **`ar4_mock_hardware`** — Mock via `mock_components/GenericSystem`.
   - Controls J4 and J6 (simulated).

**Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `serial_port` | `/dev/ttyACM0` | Teensy 4.1 USB serial device |
| `baud_rate` | `115200` | Serial baud rate |

**Extensibility:** To add a real joint (e.g., J4), move its `<joint>` block from the mock section to the real section and add motor parameters.

**Usage:**
```xml
<xacro:include filename="$(find ar4_description)/urdf/ar4_ros2_control.urdf.xacro"/>
<xacro:ar4_ros2_control serial_port="/dev/ttyACM0" baud_rate="115200"/>
```

#### `urdf/robot.urdf.xacro`
**Main entry point** for standalone AR4.

Creates:
- `world` link (reference frame)
- AR4 arm attached to world at origin
- Optional ros2_control hardware interface (when `use_ros2_control:=true`)

**Arguments:**

| Argument | Default | Description |
|----------|---------|-------------|
| `use_ros2_control` | `true` | Enable ros2_control hardware interfaces |
| `serial_port` | `/dev/ttyACM0` | Serial port for Teensy 4.1 (passed to ros2_control macro) |
| `baud_rate` | `115200` | Baud rate for Teensy serial (passed to ros2_control macro) |

**Usage:**
```bash
xacro robot.urdf.xacro use_ros2_control:=true serial_port:=/dev/ttyACM0 baud_rate:=115200 > ar4.urdf
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

### Hybrid Configuration: Real J1+J2+J3+J5 + Mock J4+J6

The hardware interface is split across two `ros2_control` components:

**1. `ar4_real_hardware`** — Real hardware via Teensy 4.1:
```xml
<hardware>
  <plugin>ar4_hardware_interface/Ar4System</plugin>
  <param name="serial_port">/dev/ttyACM0</param>
  <param name="baud_rate">115200</param>
</hardware>
<!-- J1+J2+J3+J5 with motor_id, steps_per_rev, gear_ratio, microsteps, home_offset_rad -->
```

**Features:**
- Controls physical motors via serial commands to Teensy 4.1
- Requires explicit homing via `/ar4_hardware/calibrate` service
- Reports real step-counted position after homing
- MKS SERVO42C closed-loop drivers ensure no lost steps

**2. `ar4_mock_hardware`** — Mock for remaining joints:
```xml
<hardware>
  <plugin>mock_components/GenericSystem</plugin>
  <param name="mock_sensor_commands">true</param>
  <param name="state_following_offset">0.0</param>
</hardware>
<!-- J4+J6 simulated -->
```

**Features:**
- Simulates joint movement for J4 and J6
- Follows commanded positions immediately
- No real hardware required

### Adding More Real Joints

To move a joint (e.g., J4 or J6) from mock to real, move its `<joint>` block from the `ar4_mock_hardware` section to `ar4_real_hardware` in `ar4_ros2_control.urdf.xacro` and add motor parameters. See `docs/ar4_hardware_interface/package_structure.md` for details.

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
# Launch AR4 standalone with controllers and RViz (default serial port)
ros2 launch manipulator_bringup ar4_bringup.launch.py

# Custom serial port
ros2 launch manipulator_bringup ar4_bringup.launch.py serial_port:=/dev/ttyUSB0

# Without RViz
ros2 launch manipulator_bringup ar4_bringup.launch.py rviz:=false
```

**Launch arguments:**

| Argument | Default | Description |
|----------|---------|-------------|
| `use_sim_time` | `false` | Use simulation clock |
| `rviz` | `true` | Launch RViz2 |
| `serial_port` | `/dev/ttyACM0` | Teensy 4.1 serial port |
| `baud_rate` | `115200` | Serial baud rate |

### Calibrate (Required Before Moving J1+J2)

```bash
# Home all real motors (J1+J2+J3+J5, moves to limit switches, establishes position references)
ros2 service call /ar4_hardware/calibrate std_srvs/srv/Trigger
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

- **AR4 Hardware Interface:** `../ar4_hardware_interface/package_structure.md`
- **Teensy 4.1 Firmware:** `../firmware/ar4_teensy.md`
- **AR4 Bringup Launch:** `../manipulator_bringup/launch_files.md`
- **AR4 Control Package:** `../ar4_control/package_structure.md`
- **Project Overview:** `../project_structure/overview.md`
