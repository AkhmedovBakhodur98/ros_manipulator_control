# SCARA Arm Integration Guide

This document explains how to integrate the `scara_description` package with other robots.

---

## Understanding Parent Frame

**Before mounting SCARA, you must understand the parent link's coordinate frame.**

For `manipulator_description`, see: [frames_reference.md](../manipulator_description/frames_reference.md)

Key points:
- **X-axis** = Forward direction
- **Y-axis** = Left direction
- **Z-axis** = Up direction
- Mount offset is relative to parent link origin

To visualize frames in RViz:
1. Add "TF" display
2. Enable "Show Axes" and "Show Names"
3. Red=X, Green=Y, Blue=Z

---

## Overview

The SCARA arm is designed as a **modular, reusable component**. It can be attached to any robot by:

1. Adding `scara_description` as a dependency
2. Including the SCARA xacro macro
3. Calling the macro with your parent link
4. (Optional) Customizing the configuration

```
┌─────────────────────────────────────────────────────────────────┐
│                        YOUR ROBOT                                │
│                                                                  │
│   ┌──────────────┐                                               │
│   │  your_link   │ ◄── parent_link parameter                     │
│   └──────┬───────┘                                               │
│          │                                                       │
│          │  scara_mount_joint (fixed, configurable offset)       │
│          ▼                                                       │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │                    SCARA ARM MODULE                       │  │
│   │                                                           │  │
│   │   scara_base_link → shoulder → forearm → flange → tcp    │  │
│   │                                                           │  │
│   └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Step-by-Step Integration

### Step 1: Add Package Dependency

Edit your robot's `package.xml`:

```xml
<package format="3">
  <name>my_robot_description</name>
  <!-- ... -->

  <depend>scara_description</depend>  <!-- Add this line -->

  <!-- ... -->
</package>
```

### Step 2: Include SCARA Macro in Your Xacro

In your robot's URDF xacro file:

```xml
<?xml version="1.0"?>
<robot name="my_robot" xmlns:xacro="http://www.ros.org/wiki/xacro">

  <!-- Include SCARA arm macro -->
  <xacro:include filename="$(find scara_description)/urdf/scara_arm.urdf.xacro"/>

  <!-- Your robot definition... -->
  <link name="base_link">...</link>
  <link name="arm_mount">...</link>

  <!-- Attach SCARA arm to your robot -->
  <xacro:scara_arm
    parent_link="arm_mount"
    config_file="$(find scara_description)/config/scara_params.yaml"/>

</robot>
```

### Step 3: Build and Test

```bash
# Rebuild your workspace
colcon build --symlink-install

# Source the workspace
source install/setup.bash

# Launch your robot
ros2 launch my_robot_description display.launch.py
```

---

## Configuration Options

### Option A: Use Default Configuration

Use the default `scara_params.yaml` from the package:

```xml
<xacro:scara_arm
  parent_link="your_link"
  config_file="$(find scara_description)/config/scara_params.yaml"/>
```

### Option B: Custom Configuration File

Create your own config file with modified parameters:

1. Copy the default config:
```bash
cp src/scara_description/config/scara_params.yaml \
   src/my_robot_description/config/my_scara_params.yaml
```

2. Edit the parameters (e.g., mount offset):
```yaml
# my_scara_params.yaml
mount:
  offset:
    xyz: [0.1, 0, 0.2]    # Custom position
    rpy: [0, 0, 1.57]     # Rotated 90° around Z
```

3. Reference your config file:
```xml
<xacro:scara_arm
  parent_link="your_link"
  config_file="$(find my_robot_description)/config/my_scara_params.yaml"/>
```

---

## Common Integration Patterns

### Pattern 1: End-Effector Mount

Attach SCARA as an end-effector to an existing arm:

```xml
<!-- Existing 6-DOF arm -->
<link name="arm_flange"/>

<!-- SCARA as secondary manipulator -->
<xacro:scara_arm
  parent_link="arm_flange"
  config_file="$(find scara_description)/config/scara_params.yaml"/>
```

### Pattern 2: Gantry/Linear Rail Mount

Attach SCARA to a linear motion system (like manipulator_description):

```xml
<!-- Gantry system -->
<link name="picker_frame"/>  <!-- Moves on Z-axis -->

<!-- SCARA mounted to gantry -->
<xacro:scara_arm
  parent_link="picker_frame"
  config_file="$(find scara_description)/config/scara_params.yaml"/>
```

### Pattern 3: Conditional Inclusion

Use xacro arguments to optionally include SCARA:

```xml
<!-- In your main robot xacro -->
<xacro:arg name="use_scara" default="false"/>

<xacro:if value="$(arg use_scara)">
  <xacro:include filename="$(find scara_description)/urdf/scara_arm.urdf.xacro"/>
  <xacro:scara_arm
    parent_link="mount_link"
    config_file="$(find scara_description)/config/scara_params.yaml"/>
</xacro:if>
```

Launch with or without SCARA:
```bash
ros2 launch my_robot display.launch.py use_scara:=true
ros2 launch my_robot display.launch.py use_scara:=false
```

### Pattern 4: Multiple SCARA Arms

Attach multiple SCARA arms with different configurations:

```xml
<!-- Left SCARA -->
<xacro:scara_arm
  parent_link="left_mount"
  config_file="$(find my_robot)/config/scara_left.yaml"/>

<!-- Right SCARA -->
<xacro:scara_arm
  parent_link="right_mount"
  config_file="$(find my_robot)/config/scara_right.yaml"/>
```

**Note:** You'll need to modify the xacro to support prefixes for link/joint names to avoid conflicts. See [Advanced: Link Prefixes](#advanced-link-prefixes).

---

## Mount Offset Configuration

The mount offset defines where the SCARA base attaches relative to the parent link.

### Position Offset (xyz)

```yaml
mount:
  offset:
    xyz: [x, y, z]  # meters
```

| Value | Effect |
|-------|--------|
| `[0, 0, 0]` | SCARA base at parent origin |
| `[0, 0, 0.15]` | SCARA 150mm above parent |
| `[0.1, 0, 0]` | SCARA 100mm in front (X+) |
| `[0, 0.1, 0]` | SCARA 100mm to the side (Y+) |

### Orientation Offset (rpy)

```yaml
mount:
  offset:
    rpy: [roll, pitch, yaw]  # radians
```

| Value | Effect |
|-------|--------|
| `[0, 0, 0]` | No rotation |
| `[0, 0, 1.5708]` | Rotated 90° around Z |
| `[0, 0, 3.1416]` | Rotated 180° around Z |
| `[3.1416, 0, 0]` | Flipped upside down |

### Visual Guide

```
Parent Link Frame
       Z
       │
       │    xyz=[0, 0, 0.15]
       │         ↓
       ├────────[SCARA]
       │
       │
  Y────┼────X
       │
```

---

## Integration with manipulator_description

The `manipulator_description` package already has SCARA integration built-in, including ros2_control support.

### Enable SCARA (Visualization Only)

```bash
ros2 launch manipulator_description display.launch.py use_scara:=true
```

### Enable SCARA with ros2_control

```bash
ros2 launch manipulator_description manipulator_control.launch.py use_scara:=true rviz:=true
```

This launches:
- Manipulator with SCARA arm attached
- All controllers (manipulator, gripper, SCARA)
- RViz visualization

**See:** [ros2_control.md](ros2_control.md) for detailed control instructions.

### How It Works

In `manipulator_picker.urdf.xacro`:

```xml
<!-- Include SCARA from separate package -->
<xacro:include filename="$(find scara_description)/urdf/scara_arm.urdf.xacro"/>

<xacro:macro name="picker_assembly" params="parent_link config_file use_scara:=false">

  <!-- Picker frame definition... -->
  <link name="picker_frame">...</link>

  <!-- Conditional SCARA inclusion -->
  <xacro:if value="${use_scara}">
    <xacro:scara_arm
      parent_link="picker_frame"
      config_file="$(find scara_description)/config/scara_params.yaml"/>
  </xacro:if>

</xacro:macro>
```

---

## Troubleshooting

### Error: Package not found

```
Package 'scara_description' not found
```

**Solution:** Build and source the workspace:
```bash
colcon build --packages-select scara_description
source install/setup.bash
```

### Error: File not found

```
Resource not found: scara_description
```

**Solution:** Check that the package is in your workspace and built:
```bash
ros2 pkg list | grep scara
```

### Error: Link name conflict

```
Link 'scara_base_link' already exists
```

**Solution:** You're trying to include SCARA twice. Use prefixes for multiple instances (see Advanced section).

### SCARA appears in wrong position

**Solution:** Check mount offset in config file:
```yaml
mount:
  offset:
    xyz: [0, 0, 0.15]  # Adjust these values
    rpy: [0, 0, 0]
```

### Joints not moving

**Solution:** Ensure joint_state_publisher_gui is running and SCARA joints are listed:
```bash
ros2 topic echo /joint_states
```

---

## Advanced: Link Prefixes

To support multiple SCARA instances, you can modify the macro to accept a prefix:

```xml
<xacro:macro name="scara_arm" params="parent_link config_file prefix:=''">

  <link name="${prefix}scara_base_link">...</link>

  <joint name="${prefix}scara_mount_joint" type="fixed">
    <parent link="${parent_link}"/>
    <child link="${prefix}scara_base_link"/>
  </joint>

  <!-- Continue with prefix for all links/joints -->

</xacro:macro>
```

Usage:
```xml
<xacro:scara_arm parent_link="left_mount" config_file="..." prefix="left_"/>
<xacro:scara_arm parent_link="right_mount" config_file="..." prefix="right_"/>
```

---

## API Reference

### Macro: `scara_arm`

```xml
<xacro:scara_arm
  parent_link="string"
  config_file="string"/>
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `parent_link` | string | Yes | Name of link to attach SCARA to |
| `config_file` | string | Yes | Full path to YAML config file |

### Created Links

| Link Name | Description |
|-----------|-------------|
| `scara_base_link` | Mounting bracket |
| `scara_shoulder_link` | First arm segment |
| `scara_forearm_link` | Second arm segment |
| `scara_flange_link` | Wrist flange |
| `tool_body_link` | Tool mounting body |
| `tcp_link` | Tool center point |

### Created Joints

| Joint Name | Type | Description |
|------------|------|-------------|
| `scara_mount_joint` | fixed | Parent to SCARA base |
| `scara_shoulder_joint` | revolute | Base rotation (θ1) |
| `scara_elbow_joint` | revolute | Arm reach (θ2) |
| `scara_wrist_joint` | revolute | End-effector rotation (θ3) |
| `tool_fix_joint` | fixed | Flange to tool body |
| `tool_to_tcp_joint` | fixed | Tool body to TCP |
