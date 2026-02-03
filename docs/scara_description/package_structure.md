# SCARA Description Package Documentation

## Overview

The `scara_description` package contains the URDF/Xacro robot description for a 3-DOF SCARA (Selective Compliance Assembly Robot Arm). This package is designed as a **reusable module** that can be attached to any parent robot.

## Package Structure

```
src/scara_description/
├── CMakeLists.txt                    # Build configuration
├── package.xml                       # Package metadata and dependencies
├── config/
│   └── scara_params.yaml             # All SCARA parameters (configurable)
├── launch/
│   └── display.launch.py             # Standalone RViz visualization
├── meshes/
│   └── scara/
│       ├── scara_base_link.STL       # Mounting bracket mesh
│       ├── scara_shoulder_link.STL   # First arm segment mesh
│       ├── scara_forearm_link.STL    # Second arm segment mesh
│       ├── scara_flange_link.STL     # Wrist/flange mesh
│       └── tool_body_link.STL        # Tool body mesh
├── rviz/
│   └── (optional RViz config)
└── urdf/
    ├── scara_arm.urdf.xacro          # Main SCARA macro (reusable)
    └── robot.urdf.xacro              # Standalone robot for testing
```

---

## File Descriptions

### Build Files

#### `CMakeLists.txt`
CMake build configuration for the ROS2 package.
- Finds required dependencies: `ament_cmake`, `urdf`, `xacro`
- Installs directories: `urdf`, `config`, `launch`, `meshes`, `rviz`

#### `package.xml`
ROS2 package manifest defining:
- Package name: `scara_description`
- Version: `0.1.0`
- Dependencies:
  - Build: `ament_cmake`
  - Runtime: `urdf`, `xacro`, `robot_state_publisher`, `joint_state_publisher_gui`, `rviz2`

---

### Configuration Files

#### `config/scara_params.yaml`
Central configuration file containing all SCARA parameters:

```yaml
# Mounting configuration
mount:
  offset:
    xyz: [0, 0, 0.15]       # Position offset from parent link
    rpy: [0, 0, 0]          # Orientation offset (roll, pitch, yaw)

# Kinematic parameters
kinematics:
  L1: 0.4125                # Shoulder to elbow length [m]
  L2: 0.2625                # Elbow to wrist length [m]

# Link properties (mesh, color, inertial)
links:
  scara_base_link: { ... }
  scara_shoulder_link: { ... }
  scara_forearm_link: { ... }
  scara_flange_link: { ... }
  tool_body_link: { ... }
  tcp_link: { ... }

# Joint properties (type, limits, dynamics)
joints:
  scara_shoulder_joint: { ... }
  scara_elbow_joint: { ... }
  scara_wrist_joint: { ... }
  tool_fix_joint: { ... }
  tool_to_tcp_joint: { ... }
```

**Key Configurable Parameters:**

| Parameter | Location | Description |
|-----------|----------|-------------|
| Mount position | `mount.offset.xyz` | XYZ offset from parent link [m] |
| Mount orientation | `mount.offset.rpy` | RPY rotation from parent link [rad] |
| Arm length L1 | `kinematics.L1` | Shoulder-to-elbow distance [m] |
| Arm length L2 | `kinematics.L2` | Elbow-to-wrist distance [m] |
| Joint limits | `joints.*.limits` | Position, effort, velocity limits |
| Joint dynamics | `joints.*.dynamics` | Damping and friction coefficients |
| TCP offset | `joints.tool_to_tcp_joint.origin.xyz` | Tool center point offset |

---

### Launch Files

#### `launch/display.launch.py`
Python launch file for standalone SCARA visualization in RViz2.

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
# Standalone SCARA visualization
ros2 launch scara_description display.launch.py

# Without GUI
ros2 launch scara_description display.launch.py gui:=false
```

---

### Mesh Files

#### `meshes/scara/`
STL mesh files for robot visualization and collision detection.

| File | Description | Associated Link |
|------|-------------|-----------------|
| `scara_base_link.STL` | Mounting bracket | `scara_base_link` |
| `scara_shoulder_link.STL` | First arm segment | `scara_shoulder_link` |
| `scara_forearm_link.STL` | Second arm segment | `scara_forearm_link` |
| `scara_flange_link.STL` | Wrist flange | `scara_flange_link` |
| `tool_body_link.STL` | Tool mounting body | `tool_body_link` |

**Notes:**
- All meshes are in STL format
- Units: meters (no scaling required)
- Origin: Aligned with link frame origin

---

### URDF/Xacro Files

#### `urdf/scara_arm.urdf.xacro`
**Main SCARA macro** - Reusable component for integration with other robots.

```xml
<xacro:macro name="scara_arm" params="parent_link config_file">
  <!-- Loads parameters from config_file -->
  <!-- Creates all links and joints -->
  <!-- Attaches to parent_link via scara_mount_joint -->
</xacro:macro>
```

**Parameters:**
| Parameter | Required | Description |
|-----------|----------|-------------|
| `parent_link` | Yes | Name of the link to attach SCARA to |
| `config_file` | Yes | Path to scara_params.yaml |

#### `urdf/robot.urdf.xacro`
**Standalone robot file** for testing SCARA independently.

Creates:
- `world` link (reference frame)
- `base_mount` link (simple pedestal)
- SCARA arm attached to pedestal

---

## Robot Kinematic Structure

### Links (7 total)

| # | Link Name | Description | Mesh |
|---|-----------|-------------|------|
| 1 | `scara_base_link` | Mounting bracket | scara_base_link.STL |
| 2 | `scara_shoulder_link` | First arm (L1) | scara_shoulder_link.STL |
| 3 | `scara_forearm_link` | Second arm (L2) | scara_forearm_link.STL |
| 4 | `scara_flange_link` | Wrist flange | scara_flange_link.STL |
| 5 | `tool_body_link` | Tool body | tool_body_link.STL |
| 6 | `tcp_link` | Tool center point | (sphere marker) |

### Joints (5 total)

| # | Joint Name | Type | Parent | Child | Axis | Limits |
|---|------------|------|--------|-------|------|--------|
| 1 | `scara_mount_joint` | fixed | (parent) | scara_base_link | - | - |
| 2 | `scara_shoulder_joint` | revolute | scara_base_link | scara_shoulder_link | Z | ±57° |
| 3 | `scara_elbow_joint` | revolute | scara_shoulder_link | scara_forearm_link | Z | ±185° |
| 4 | `scara_wrist_joint` | revolute | scara_forearm_link | scara_flange_link | Z | ±360° |
| 5 | `tool_fix_joint` | fixed | scara_flange_link | tool_body_link | - | - |
| 6 | `tool_to_tcp_joint` | fixed | tool_body_link | tcp_link | - | - |

### Kinematic Tree

```
parent_link (from host robot)
 └── [scara_mount_joint: fixed]
     └── scara_base_link
         └── [scara_shoulder_joint: revolute Z, θ1]
             └── scara_shoulder_link
                 └── [scara_elbow_joint: revolute Z, θ2]
                     └── scara_forearm_link
                         └── [scara_wrist_joint: revolute Z, θ3]
                             └── scara_flange_link
                                 └── [tool_fix_joint: fixed]
                                     └── tool_body_link
                                         └── [tool_to_tcp_joint: fixed]
                                             └── tcp_link
```

---

## SCARA Kinematics

### Workspace

```
        ← L1 = 0.4125m →← L2 = 0.2625m →

             Elbow          Wrist/TCP
    Base ──────●──────────────●
      ↑        θ2             θ3
      θ1

Reach (min): L1 - L2 = 0.15m
Reach (max): L1 + L2 = 0.675m
```

### Joint Specifications

| Joint | Symbol | Range | Max Velocity | Max Effort |
|-------|--------|-------|--------------|------------|
| Shoulder | θ1 | ±57° (±0.995 rad) | 1.6 rad/s | 20 Nm |
| Elbow | θ2 | ±185° (±3.228 rad) | 1.5 rad/s | 3.3 Nm |
| Wrist | θ3 | ±360° (±6.28 rad) | 3.3 rad/s | 5 Nm |

### Forward Kinematics

```
x = L1·cos(θ1) + L2·cos(θ1 + θ2)
y = L1·sin(θ1) + L2·sin(θ1 + θ2)
φ = θ1 + θ2 + θ3  (end-effector orientation)
```

---

## Usage

### Build the Package

```bash
cd /home/akhmedov/manipulator_ros_control
colcon build --symlink-install --packages-select scara_description
source install/setup.bash
```

### Standalone Visualization

```bash
ros2 launch scara_description display.launch.py
```

### Generate URDF from Xacro

```bash
ros2 run xacro xacro src/scara_description/urdf/robot.urdf.xacro > scara.urdf
```

### Check URDF for Errors

```bash
check_urdf scara.urdf
```

---

## Integration with Other Robots

See [integration.md](integration.md) for detailed instructions on how to attach the SCARA arm to other robots.

**Quick example:**
```xml
<!-- In your robot's xacro file -->
<xacro:include filename="$(find scara_description)/urdf/scara_arm.urdf.xacro"/>

<xacro:scara_arm
  parent_link="your_attachment_link"
  config_file="$(find scara_description)/config/scara_params.yaml"/>
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

---

## ROS2 Topics

When running `display.launch.py`:

| Topic | Type | Description |
|-------|------|-------------|
| `/robot_description` | `std_msgs/String` | URDF XML string |
| `/joint_states` | `sensor_msgs/JointState` | Current joint positions |
| `/tf` | `tf2_msgs/TFMessage` | Transform tree |
| `/tf_static` | `tf2_msgs/TFMessage` | Static transforms |
