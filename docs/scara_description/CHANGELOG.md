# SCARA Description Package - Changelog

## Recent Changes

### ros2_control Integration (Latest)

Added complete ros2_control support for the SCARA arm with independent controller.

#### New Files Created

1. **`urdf/scara_ros2_control.urdf.xacro`**
   - Hardware interface definition for SCARA joints
   - Uses `mock_components/GenericSystem` for testing
   - Loads joint limits from `scara_params.yaml`
   - Defines command/state interfaces for all 3 SCARA joints

2. **`config/scara_controllers.yaml`**
   - Controller configuration file
   - Defines `joint_state_broadcaster` and `scara_controller`
   - JointTrajectoryController with spline interpolation
   - 100 Hz update rate, 50 Hz state publishing

3. **`launch/scara_control.launch.py`**
   - Standalone launch file for SCARA with ros2_control
   - Starts controller_manager, joint_state_broadcaster, scara_controller
   - Optional RViz2 visualization
   - Supports `use_sim_time` and `rviz` arguments

4. **`rviz/scara_control.rviz`**
   - RViz configuration file
   - Fixed frame set to `world` (fixes "Frame [map] does not exist" error)
   - Pre-configured RobotModel and TF displays

5. **`docs/scara_description/ros2_control.md`**
   - Complete documentation for ros2_control integration
   - Usage examples, troubleshooting, hardware interface details

#### Modified Files

1. **`urdf/robot.urdf.xacro`**
   - Added `use_ros2_control` argument (default: `false`)
   - Includes `scara_ros2_control.urdf.xacro` conditionally
   - Instantiates `scara_ros2_control` macro when enabled

2. **`package.xml`**
   - Added dependencies:
     - `controller_manager`
     - `joint_state_broadcaster`
     - `joint_trajectory_controller`

3. **`config/scara_params.yaml`**
   - Updated mount offset:
     - X-axis: Changed from `0` to `0.15` m (15 cm forward)
     - Y-axis: `0` (no change)
     - Z-axis: `0.15` m (15 cm up, unchanged)

4. **`manipulator_description/urdf/robot.urdf.xacro`**
   - Includes SCARA ros2_control when SCARA is enabled
   - Conditionally instantiates `scara_ros2_control` macro

5. **`manipulator_description/launch/manipulator_control.launch.py`**
   - Loads SCARA controllers configuration
   - Spawns `scara_controller` when `use_scara:=true`
   - All controllers operate independently

6. **Documentation Updates**
   - `package_structure.md`: Added new files and ros2_control info
   - `integration.md`: Added ros2_control integration details
   - `configuration.md`: Updated mount offset examples

#### Features Added

- ✅ Independent SCARA controller (separate from manipulator)
- ✅ Action-based trajectory control (`/scara_controller/follow_joint_trajectory`)
- ✅ Mock hardware interface for testing
- ✅ Standalone launch file for SCARA testing
- ✅ Full integration with manipulator_description
- ✅ RViz configuration with correct fixed frame
- ✅ Complete documentation

#### Usage

**Standalone SCARA:**
```bash
ros2 launch scara_description scara_control.launch.py
```

**Manipulator with SCARA:**
```bash
ros2 launch manipulator_description manipulator_control.launch.py use_scara:=true
```

**Control SCARA:**
```bash
ros2 action send_goal /scara_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory "{
    trajectory: {
      joint_names: [scara_shoulder_joint, scara_elbow_joint, scara_wrist_joint],
      points: [{positions: [0.5, 0.3, 1.0], time_from_start: {sec: 2}}]
    }
  }"
```

#### Configuration Changes

**Mount Offset:**
- Previous: `xyz: [0, 0, 0.15]`
- Current: `xyz: [0.15, 0, 0.15]`
- Effect: SCARA base is now positioned 15 cm forward on X-axis from parent link

---

## Summary

The SCARA arm now has complete ros2_control support, allowing:
- Trajectory-based control via action interface
- Independent operation from manipulator controllers
- Easy hardware replacement (mock → real hardware)
- Full integration with existing manipulator system

All changes are backward compatible - existing code continues to work, with new ros2_control features available when enabled.

