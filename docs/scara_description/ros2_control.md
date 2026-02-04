# SCARA Arm ros2_control Integration

This document describes the ros2_control integration for the SCARA arm, allowing trajectory-based control of all SCARA joints.

---

## Overview

The SCARA arm has its own **independent ros2_control setup** with:
- Separate hardware interface (`scara_hardware`)
- Dedicated controller (`scara_controller`)
- Standalone launch file for testing
- Full integration with manipulator_description

**Key Features:**
- Position control via JointTrajectoryController
- Independent operation from manipulator controllers
- Mock hardware interface for testing (easily replaceable with real hardware)
- Action-based trajectory following

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              ros2_control Controller Manager              │
│                                                          │
│  ┌──────────────────┐    ┌──────────────────┐        │
│  │ scara_hardware   │    │ manipulator_      │        │
│  │ (GenericSystem)  │    │ hardware          │        │
│  └────────┬─────────┘    └────────┬──────────┘        │
│           │                       │                     │
│           ▼                       ▼                     │
│  ┌──────────────────┐    ┌──────────────────┐        │
│  │ scara_controller │    │ manipulator_     │        │
│  │ (JointTrajectory)│    │ controller       │        │
│  └──────────────────┘    └──────────────────┘        │
└─────────────────────────────────────────────────────────┘
```

---

## Files Created

### 1. `urdf/scara_ros2_control.urdf.xacro`

Hardware interface definition for SCARA joints.

**Macro:** `scara_ros2_control`

**Parameters:**
- `config_file` - Path to `scara_params.yaml` (loads joint limits)

**Defines:**
- Hardware plugin: `mock_components/GenericSystem` (for testing)
- 3 joint interfaces:
  - `scara_shoulder_joint` (position command/state)
  - `scara_elbow_joint` (position command/state)
  - `scara_wrist_joint` (position command/state)

**Usage:**
```xml
<xacro:include filename="$(find scara_description)/urdf/scara_ros2_control.urdf.xacro"/>

<xacro:scara_ros2_control
  config_file="$(find scara_description)/config/scara_params.yaml"/>
```

### 2. `config/scara_controllers.yaml`

Controller configuration file.

**Controllers:**
- `joint_state_broadcaster` - Publishes joint states to `/joint_states`
- `scara_controller` - JointTrajectoryController for all 3 SCARA joints

**Configuration:**
- Update rate: 100 Hz
- Command interface: position
- State interfaces: position, velocity
- Interpolation: splines
- State publish rate: 50 Hz

### 3. `launch/scara_control.launch.py`

Launch file for standalone SCARA with ros2_control.

**Nodes:**
- `robot_state_publisher` - Publishes robot transforms
- `controller_manager` - Manages controllers
- `joint_state_broadcaster` - Publishes joint states
- `scara_controller` - Trajectory controller
- `rviz2` - Visualization (optional)

**Launch Arguments:**
| Argument | Default | Description |
|----------|---------|-------------|
| `use_sim_time` | `false` | Use simulation clock |
| `rviz` | `true` | Launch RViz2 |

**Usage:**
```bash
# Launch with RViz
ros2 launch scara_description scara_control.launch.py

# Without RViz
ros2 launch scara_description scara_control.launch.py rviz:=false
```

### 4. `rviz/scara_control.rviz`

RViz configuration file with:
- Fixed frame set to `world`
- RobotModel display configured
- TF tree visualization
- Grid display

---

## Updated Files

### 1. `urdf/robot.urdf.xacro`

**Added:**
- `use_ros2_control` argument (default: `false`)
- Conditional inclusion of `scara_ros2_control.urdf.xacro`
- Conditional instantiation of `scara_ros2_control` macro

**Usage:**
```bash
# Generate URDF with ros2_control
xacro robot.urdf.xacro use_ros2_control:=true > robot.urdf
```

### 2. `package.xml`

**Added Dependencies:**
- `controller_manager` - Controller management
- `joint_state_broadcaster` - Joint state publishing
- `joint_trajectory_controller` - Trajectory control

---

## Standalone Usage

### Launch SCARA with ros2_control

```bash
# Build the package
colcon build --packages-select scara_description
source install/setup.bash

# Launch
ros2 launch scara_description scara_control.launch.py
```

### Control the Arm

**Send trajectory goal:**
```bash
ros2 action send_goal /scara_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory "{
    trajectory: {
      joint_names: [scara_shoulder_joint, scara_elbow_joint, scara_wrist_joint],
      points: [
        {positions: [0.5, 0.3, 1.0], time_from_start: {sec: 2}},
        {positions: [-0.3, 0.5, 2.0], time_from_start: {sec: 4}}
      ]
    }
  }"
```

**Return to home position:**
```bash
ros2 action send_goal /scara_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory "{
    trajectory: {
      joint_names: [scara_shoulder_joint, scara_elbow_joint, scara_wrist_joint],
      points: [{positions: [0.0, 0.0, 0.0], time_from_start: {sec: 2}}]
    }
  }"
```

**Monitor joint states:**
```bash
ros2 topic echo /joint_states
```

**Check controller status:**
```bash
ros2 topic echo /scara_controller/controller_state
```

---

## Integration with manipulator_description

The SCARA arm's ros2_control is fully integrated with the manipulator system.

### How It Works

When `use_scara:=true` is set:

1. **URDF Integration** (`manipulator_description/urdf/robot.urdf.xacro`):
   - Includes SCARA ros2_control hardware interface
   - Conditionally instantiates `scara_ros2_control` macro

2. **Launch Integration** (`manipulator_description/launch/manipulator_control.launch.py`):
   - Loads SCARA controllers configuration
   - Spawns `scara_controller` when SCARA is enabled

### Launch Combined System

```bash
# Launch manipulator with SCARA and ros2_control
ros2 launch manipulator_description manipulator_control.launch.py use_scara:=true rviz:=true
```

### Controllers Available

When launched with SCARA:

| Controller | Joints | Purpose |
|------------|--------|---------|
| `manipulator_controller` | base_main_frame_joint, main_frame_selector_frame_joint, selector_frame_picker_frame_joint | Main manipulator axes |
| `gripper_controller` | selector_left_container_jaw_joint, selector_right_container_jaw_joint | Container gripper |
| `scara_controller` | scara_shoulder_joint, scara_elbow_joint, scara_wrist_joint | SCARA arm |

**All controllers operate independently!**

### Control Both Systems

**Control manipulator:**
```bash
ros2 action send_goal /manipulator_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory "{
    trajectory: {
      joint_names: [base_main_frame_joint, main_frame_selector_frame_joint, selector_frame_picker_frame_joint],
      points: [{positions: [1.0, 0.5, 0.2], time_from_start: {sec: 2}}]
    }
  }"
```

**Control SCARA (simultaneously):**
```bash
ros2 action send_goal /scara_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory "{
    trajectory: {
      joint_names: [scara_shoulder_joint, scara_elbow_joint, scara_wrist_joint],
      points: [{positions: [0.5, 0.3, 1.0], time_from_start: {sec: 2}}]
    }
  }"
```

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

To use real hardware, replace the hardware plugin in `scara_ros2_control.urdf.xacro`:

```xml
<hardware>
  <plugin>your_hardware_package/YourHardwareInterface</plugin>
  <param name="device_name">/dev/ttyUSB0</param>
  <param name="baud_rate">115200</param>
  <!-- Add your hardware-specific parameters -->
</hardware>
```

**Common hardware interface plugins:**
- `ros2_control_demo_hardware/DemoHardware` - Demo hardware
- `your_package/YourCustomHardware` - Custom implementation

---

## Joint Limits

Joint limits are automatically loaded from `scara_params.yaml`:

| Joint | Lower Limit | Upper Limit | Units |
|-------|-------------|-------------|-------|
| `scara_shoulder_joint` | -0.995 rad (-57°) | 0.995 rad (+57°) | radians |
| `scara_elbow_joint` | -3.228 rad (-185°) | 3.228 rad (+185°) | radians |
| `scara_wrist_joint` | -6.28 rad (-360°) | 6.28 rad (+360°) | radians |

These limits are enforced by the hardware interface and controller.

---

## Topics and Actions

### Topics

| Topic | Type | Description |
|-------|------|-------------|
| `/joint_states` | `sensor_msgs/JointState` | All joint positions/velocities |
| `/scara_controller/controller_state` | `control_msgs/msg/JointTrajectoryControllerState` | Controller state |
| `/scara_controller/joint_trajectory` | `trajectory_msgs/JointTrajectory` | Current trajectory |

### Actions

| Action | Type | Description |
|--------|------|-------------|
| `/scara_controller/follow_joint_trajectory` | `control_msgs/action/FollowJointTrajectory` | Execute trajectory |

---

## Troubleshooting

### Controller Not Spawning

**Error:** `Controller 'scara_controller' not found`

**Solution:**
1. Check that `scara_controllers.yaml` is loaded:
   ```bash
   ros2 param list /controller_manager | grep scara
   ```
2. Verify controllers are declared in YAML
3. Check launch file includes controllers file

### Joints Not Moving

**Error:** Joints stay at zero position

**Solution:**
1. Verify hardware interface is active:
   ```bash
   ros2 node list | grep scara_hardware
   ```
2. Check joint states are publishing:
   ```bash
   ros2 topic echo /joint_states
   ```
3. Verify action server is available:
   ```bash
   ros2 action list | grep scara
   ```

### RViz Shows "Frame [map] does not exist"

**Solution:** Use the provided RViz config or manually set fixed frame to `world`:
- In RViz: Global Options → Fixed Frame → `world`

### Hardware Interface Errors

**Error:** `Failed to initialize hardware interface`

**Solution:**
1. Check hardware plugin name is correct
2. Verify all required parameters are set
3. For real hardware, check device connections
4. Review hardware interface logs:
   ```bash
   ros2 topic echo /rosout | grep hardware
   ```

---

## Configuration Changes

### Mount Offset Update

The mount offset was updated to position the SCARA arm 15 cm forward on the X-axis:

```yaml
mount:
  offset:
    xyz: [0.15, 0, 0.15]    # X: 15cm forward, Z: 15cm up
    rpy: [0, 0, 0]
```

This positions the SCARA base 15 cm in front of the `picker_frame` origin along the X-axis.

---

## Summary

The SCARA arm now has complete ros2_control support with:
- ✅ Independent hardware interface
- ✅ Dedicated trajectory controller
- ✅ Standalone launch file
- ✅ Full manipulator integration
- ✅ Action-based control interface
- ✅ Mock hardware for testing
- ✅ Easy hardware replacement

The system is ready for both simulation and real hardware deployment.

