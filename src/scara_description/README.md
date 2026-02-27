# SCARA Description Package

A ROS2 package providing URDF/Xacro robot description for a 3-DOF SCARA (Selective Compliance Assembly Robot Arm). This package is designed as a **modular, reusable component** that can be attached to any parent robot.

## Features

- ✅ **3-DOF SCARA Arm** - Shoulder, elbow, and wrist joints
- ✅ **Modular Design** - Easily attachable to any robot
- ✅ **ros2_control Support** - Independent trajectory controller
- ✅ **Fully Configurable** - All parameters in YAML
- ✅ **Complete Documentation** - Integration guides and examples
- ✅ **Standalone Testing** - Launch files for independent testing

## Quick Start

### Build the Package

```bash
cd /path/to/workspace
colcon build --symlink-install --packages-select scara_description
source install/setup.bash
```

### Visualize Standalone SCARA

```bash
# Basic visualization with GUI
ros2 launch scara_description display.launch.py

# With ros2_control
ros2 launch scara_description scara_control.launch.py
```

### Control the Arm

```bash
# Send trajectory goal
ros2 action send_goal /scara_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory "{
    trajectory: {
      joint_names: [scara_shoulder_joint, scara_elbow_joint, scara_wrist_joint],
      points: [{positions: [0.5, 0.3, 1.0], time_from_start: {sec: 2}}]
    }
  }"
```

## Robot Specifications

### Kinematics

- **Link Lengths:**
  - L1 (Shoulder to Elbow): 0.4125 m
  - L2 (Elbow to Wrist): 0.2625 m
- **Workspace:**
  - Minimum reach: 0.15 m (arm folded)
  - Maximum reach: 0.675 m (arm extended)

### Joint Limits

| Joint | Range | Max Velocity | Max Effort |
|-------|-------|--------------|------------|
| Shoulder (θ1) | ±57° | 1.6 rad/s | 20 Nm |
| Elbow (θ2) | ±185° | 1.5 rad/s | 3.3 Nm |
| Wrist (θ3) | ±360° | 3.3 rad/s | 5 Nm |

### Forward Kinematics

```
x = L1·cos(θ1) + L2·cos(θ1 + θ2)
y = L1·sin(θ1) + L2·sin(θ1 + θ2)
φ = θ1 + θ2 + θ3  (end-effector orientation)
```

## Package Structure

```
scara_description/
├── config/
│   ├── scara_params.yaml          # All SCARA parameters
│   └── scara_controllers.yaml    # ros2_control configuration
├── launch/
│   ├── display.launch.py          # Standalone visualization
│   └── scara_control.launch.py   # ros2_control launch
├── meshes/scara/                  # STL mesh files
├── rviz/
│   └── scara_control.rviz         # RViz configuration
└── urdf/
    ├── scara_arm.urdf.xacro       # Main SCARA macro
    ├── scara_ros2_control.urdf.xacro  # Hardware interface
    └── robot.urdf.xacro          # Standalone robot
```

## Integration with Other Robots

### Basic Integration

```xml
<!-- In your robot's xacro file -->
<xacro:include filename="$(find scara_description)/urdf/scara_arm.urdf.xacro"/>

<xacro:scara_arm
  parent_link="your_attachment_link"
  config_file="$(find scara_description)/config/scara_params.yaml"/>
```

### With ros2_control

```xml
<!-- Include ros2_control hardware interface -->
<xacro:include filename="$(find scara_description)/urdf/scara_ros2_control.urdf.xacro"/>

<!-- Instantiate SCARA arm -->
<xacro:scara_arm
  parent_link="your_attachment_link"
  config_file="$(find scara_description)/config/scara_params.yaml"/>

<!-- Add ros2_control hardware interface -->
<xacro:scara_ros2_control
  config_file="$(find scara_description)/config/scara_params.yaml"/>
```

### Integration with manipulator_description

The SCARA arm is already integrated with `manipulator_description`:

```bash
# Launch manipulator with SCARA
ros2 launch manipulator_description manipulator_control.launch.py use_scara:=true
```

This provides:
- **manipulator_controller** - Controls manipulator joints
- **gripper_controller** - Controls gripper jaws
- **scara_controller** - Controls SCARA joints (independent)

## Configuration

All parameters are configured in `config/scara_params.yaml`:

### Mount Offset

```yaml
mount:
  offset:
    xyz: [0.15, 0, 0.15]    # X: 15cm forward, Z: 15cm up
    rpy: [0, 0, 0]          # No rotation
```

### Custom Configuration

1. Copy the default config:
   ```bash
   cp src/scara_description/config/scara_params.yaml \
      src/your_package/config/my_scara_params.yaml
   ```

2. Edit parameters (mount offset, joint limits, etc.)

3. Reference your config:
   ```xml
   <xacro:scara_arm
     parent_link="your_link"
     config_file="$(find your_package)/config/my_scara_params.yaml"/>
   ```

## Launch Files

### `display.launch.py`
Standalone visualization with manual joint control.

**Usage:**
```bash
ros2 launch scara_description display.launch.py
ros2 launch scara_description display.launch.py gui:=false
```

### `scara_control.launch.py`
Standalone launch with ros2_control support.

**Usage:**
```bash
ros2 launch scara_description scara_control.launch.py
ros2 launch scara_description scara_control.launch.py rviz:=false
```

## ros2_control

The SCARA arm has its own independent ros2_control setup:

- **Hardware Interface:** `scara_hardware` (mock_components/GenericSystem)
- **Controller:** `scara_controller` (JointTrajectoryController)
- **Action Interface:** `/scara_controller/follow_joint_trajectory`

### Control Example

```bash
# Move to specific position
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

# Return to home
ros2 action send_goal /scara_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory "{
    trajectory: {
      joint_names: [scara_shoulder_joint, scara_elbow_joint, scara_wrist_joint],
      points: [{positions: [0.0, 0.0, 0.0], time_from_start: {sec: 2}}]
    }
  }"
```

## Dependencies

### Build Dependencies
- `ament_cmake`
- `urdf`
- `xacro`

### Runtime Dependencies
- `robot_state_publisher`
- `joint_state_publisher_gui` (for display.launch.py)
- `rviz2`
- `controller_manager` (for ros2_control)
- `joint_state_broadcaster` (for ros2_control)
- `joint_trajectory_controller` (for ros2_control)

## Documentation

Detailed documentation is available in `docs/scara_description/`:

- **[package_structure.md](../docs/scara_description/package_structure.md)** - Package structure and file descriptions
- **[integration.md](../docs/scara_description/integration.md)** - Integration guide with other robots
- **[ros2_control.md](../docs/scara_description/ros2_control.md)** - Complete ros2_control documentation
- **[configuration.md](../docs/scara_description/configuration.md)** - Configuration parameter reference
- **[CHANGELOG.md](../docs/scara_description/CHANGELOG.md)** - Recent changes and updates

## Robot Structure

### Links (6 total)
- `scara_base_link` - Mounting bracket
- `scara_shoulder_link` - First arm segment (L1)
- `scara_forearm_link` - Second arm segment (L2)
- `scara_flange_link` - Wrist flange
- `tool_body_link` - Tool mounting body
- `tcp_link` - Tool center point (visual marker)

### Joints (6 total)
- `scara_mount_joint` - Fixed joint to parent link
- `scara_shoulder_joint` - Base rotation (θ1)
- `scara_elbow_joint` - Arm reach (θ2)
- `scara_wrist_joint` - End-effector rotation (θ3)
- `tool_fix_joint` - Flange to tool body
- `tool_to_tcp_joint` - Tool body to TCP

## Troubleshooting

### RViz Shows "Frame [map] does not exist"
**Solution:** Use the provided RViz config or set fixed frame to `world`:
- In RViz: Global Options → Fixed Frame → `world`

### Controller Not Spawning
**Solution:** Check that controllers YAML is loaded:
```bash
ros2 param list /controller_manager | grep scara
```

### Joints Not Moving
**Solution:** Verify hardware interface and action server:
```bash
ros2 node list | grep scara
ros2 action list | grep scara
ros2 topic echo /joint_states
```

### Package Not Found
**Solution:** Build and source the workspace:
```bash
colcon build --packages-select scara_description
source install/setup.bash
```

## Examples

### Standalone Testing
```bash
# Build
colcon build --packages-select scara_description
source install/setup.bash

# Launch with ros2_control
ros2 launch scara_description scara_control.launch.py

# Control the arm
ros2 action send_goal /scara_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory "{
    trajectory: {
      joint_names: [scara_shoulder_joint, scara_elbow_joint, scara_wrist_joint],
      points: [{positions: [0.5, 0.3, 1.0], time_from_start: {sec: 2}}]
    }
  }"
```

### With Manipulator
```bash
# Launch combined system
ros2 launch manipulator_description manipulator_control.launch.py use_scara:=true

# Control manipulator
ros2 action send_goal /manipulator_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory "{
    trajectory: {
      joint_names: [base_main_frame_joint, main_frame_selector_frame_joint, selector_frame_picker_frame_joint],
      points: [{positions: [1.0, 0.5, 0.2], time_from_start: {sec: 2}}]
    }
  }"

# Control SCARA (simultaneously)
ros2 action send_goal /scara_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory "{
    trajectory: {
      joint_names: [scara_shoulder_joint, scara_elbow_joint, scara_wrist_joint],
      points: [{positions: [0.5, 0.3, 1.0], time_from_start: {sec: 2}}]
    }
  }"
```

## License

MIT

## Maintainer

akhmedov

---

For more information, see the [detailed documentation](../docs/scara_description/).




