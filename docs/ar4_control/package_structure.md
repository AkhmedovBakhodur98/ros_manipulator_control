# ar4_control Package Documentation

## Overview

The `ar4_control` package provides control nodes for the AR4 arm. Currently includes a DualShock 4 joystick teleoperation node for real-time velocity-mode joint control.

## Package Structure

```
src/ar4_control/
├── package.xml                    # ament_python package manifest
├── setup.py                       # Python package setup
├── setup.cfg                      # ament_python install paths
├── resource/
│   └── ar4_control                # ament resource index marker
├── ar4_control/
│   ├── __init__.py                # Empty
│   └── teleop_joy.py             # DualShock 4 joystick teleop node
└── launch/
    └── teleop_joy.launch.py      # Launch joy_node + teleop_joy
```

---

## File Descriptions

### `ar4_control/teleop_joy.py`

ROS2 node that maps DualShock 4 (CUH-ZCT2E) inputs to joint jog velocities.

**Subscriptions:**
- `/joy` (`sensor_msgs/Joy`) — joystick input from `joy_node`

**Publications:**
- `/ar4_hardware/jog` (`std_msgs/Float64MultiArray`) — 6-element array of joint velocities in rad/s

**Service clients:**
- `/ar4_hardware/start` (`std_srvs/Trigger`) — mark all joints homed

**DS4 Bluetooth button/axis mapping:**

| Input | Index | Action |
|-------|-------|--------|
| Left stick X | axes[0] | J1 (base rotation) |
| Left stick Y | axes[1] | J2 (shoulder) |
| Right stick X | axes[2] | J4 (forearm roll) |
| Right stick Y | axes[3] | J3 (elbow) |
| L1 | buttons[9] | J5 negative |
| R1 | buttons[10] | J5 positive |
| Cross | buttons[0] | Speed scale down (min 0.1) |
| Square | buttons[2] | Go to all zeros (trajectory, 5s) |
| Triangle | buttons[3] | Speed scale up (max 1.0) |
| SHARE | buttons[7] | Call `/ar4_hardware/start` |
| OPTIONS | buttons[6] | Emergency stop (publish all zeros) |

**Note:** J6 is not mapped to any joystick input.

**Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_speed_j1` | 0.5 | Max J1 speed (rad/s) |
| `max_speed_j2` | 0.5 | Max J2 speed (rad/s) |
| `max_speed_j3` | 0.5 | Max J3 speed (rad/s) |
| `max_speed_j4` | 0.5 | Max J4 speed (rad/s) |
| `max_speed_j5` | 0.5 | Max J5 speed (rad/s) |
| `max_speed_j6` | 0.5 | Max J6 speed (rad/s) |

**Action clients:**
- `/arm_controller/follow_joint_trajectory` (`control_msgs/FollowJointTrajectory`) — used by Square button to move all joints to zero

**Features:**
- Deadzone (0.1) on analog sticks prevents drift
- Speed scale (0.1–1.0) adjustable via Cross/Triangle buttons, default 0.5
- Edge detection on buttons (only triggers on press, not hold)
- Go-to-zero (Square): stops jogging, sends trajectory to move all joints to 0.0 over 5 seconds

### `launch/teleop_joy.launch.py`

Launches `joy_node` (from `ros-jazzy-joy` package) and `teleop_joy` together.

**joy_node parameters:**
- `deadzone`: 0.1
- `autorepeat_rate`: 20.0 Hz

---

## Dependencies

| Category | Package | Purpose |
|----------|---------|---------|
| **Build** | `ament_python` | ROS2 Python build system |
| **ROS2 Core** | `rclpy` | ROS2 Python client library |
| **Messages** | `control_msgs` | FollowJointTrajectory action |
| **Messages** | `trajectory_msgs` | JointTrajectoryPoint messages |
| **Messages** | `sensor_msgs` | Joy messages |
| **Messages** | `std_msgs` | Float64MultiArray for jog |
| **Messages** | `std_srvs` | Trigger service for start |
| **Exec** | `ar4_description` | Robot description |
| **System** | `ros-jazzy-joy` | Joystick driver node |

---

## Usage

### Prerequisites

```bash
# Install joy package
sudo apt install ros-jazzy-joy

# Connect DS4 via Bluetooth or USB
ls /dev/input/js0   # Should exist
```

### Launch

```bash
# Terminal 1: Launch hardware interface
ros2 launch manipulator_bringup ar4_bringup.launch.py

# Terminal 2: Launch teleop
ros2 launch ar4_control teleop_joy.launch.py

# Press SHARE on DS4 to call START, then move sticks
```

### Monitor

```bash
# Watch jog commands
ros2 topic echo /ar4_hardware/jog

# Watch joystick raw input
ros2 topic echo /joy
```

---

## Safety

- **Watchdog:** Hardware interface stops all motors if no jog message for 200ms
- **Firmware limits:** Hard/soft position limits enforced regardless of jog input
- **Speed clamping:** Firmware clamps jog speed to per-joint `max_speed`
- **Emergency stop:** OPTIONS button publishes all zeros immediately
- **Deadzone:** Prevents accidental drift from stick noise

---

## Related Documentation

- **AR4 Hardware Interface:** `../ar4_hardware_interface/package_structure.md`
- **Teensy Firmware:** `../firmware/ar4_teensy.md`
- **AR4 Description:** `../ar4_description/package_structure.md`
- **AR4 Bringup Launch:** `../manipulator_bringup/launch_files.md`
