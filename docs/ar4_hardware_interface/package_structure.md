# ar4_hardware_interface Package Documentation

## Overview

The `ar4_hardware_interface` package provides a `ros2_control` `SystemInterface` plugin that communicates with a Teensy 4.1 microcontroller over serial to control real AR4 arm motors. Currently drives **J1** (base rotation), **J2** (shoulder), **J3** (elbow), and **J5** (wrist pitch), while J4 and J6 remain on `mock_components/GenericSystem`. Additional joints are added by moving their URDF `<joint>` block from the mock section to the real section.

**Key design:** Homing is **not** automatic. The arm starts reporting zero position for all joints. A calibration service (`/ar4_hardware/calibrate`) must be called explicitly to home the motors and enable position tracking.

---

## Architecture

```
┌──────────────────────────────────────────────┐
│                Controller Manager             │
│  ┌──────────────────┐  ┌──────────────────┐  │
│  │ ar4_real_hardware │  │ ar4_mock_hardware │  │
│  │ (Ar4System)       │  │ (GenericSystem)   │  │
│  │ J1+J2+J3+J5 real  │  │   J4+J6 mock      │  │
│  └────────┬──────────┘  └──────────────────┘  │
└───────────┼──────────────────────────────────┘
            │ Serial (115200 baud)
            ▼
     ┌──────────────┐
     │  Teensy 4.1   │──► J1: MKS SERVO42C ──► NEMA 17 + 40:1 reducer
     │  Step/Dir x4  │──► J2: MKS SERVO42C ──► NEMA 23 + 100:1 reducer
     │  Limit x4     │──► J3: MKS SERVO42C ──► NEMA 17 + 50:1 reducer
     └──────────────┘    J5: MKS SERVO42C ──► NEMA 17 + T8 lead screw
```

---

## Package Structure

```
src/ar4_hardware_interface/
├── CMakeLists.txt                              # Build configuration
├── package.xml                                 # ROS2 package manifest
├── ar4_hardware_interface_plugin.xml           # pluginlib plugin descriptor
├── include/ar4_hardware_interface/
│   ├── ar4_system.hpp                          # SystemInterface class + JointConfig
│   ├── serial_port.hpp                         # POSIX serial port wrapper
│   └── teensy_protocol.hpp                     # Typed serial protocol interface
└── src/
    ├── ar4_system.cpp                          # Plugin lifecycle + read/write
    ├── serial_port.cpp                         # Serial open/read/write/close
    └── teensy_protocol.cpp                     # Command/response serialization
```

---

## File Descriptions

### Build Files

#### `CMakeLists.txt`

CMake build configuration.
- Builds a shared library `ar4_hardware_interface`
- Exports pluginlib plugin descriptor
- Dependencies: `hardware_interface`, `pluginlib`, `rclcpp`, `rclcpp_lifecycle`, `std_srvs`

#### `package.xml`

ROS2 package manifest.

| Category | Package | Purpose |
|----------|---------|---------|
| Build | `ament_cmake` | Build system |
| Runtime | `hardware_interface` | `SystemInterface` base class |
| Runtime | `pluginlib` | Plugin registration |
| Runtime | `rclcpp` | ROS2 C++ client |
| Runtime | `rclcpp_lifecycle` | Lifecycle state types |
| Runtime | `std_srvs` | `Trigger` service for calibration |

#### `ar4_hardware_interface_plugin.xml`

Registers the plugin with pluginlib:
- **Plugin name:** `ar4_hardware_interface/Ar4System`
- **C++ class:** `ar4_hardware_interface::Ar4System`
- **Base class:** `hardware_interface::SystemInterface`

---

### Header Files

#### `include/ar4_hardware_interface/ar4_system.hpp`

Main hardware interface class.

**Struct `JointConfig`** — per-joint motor configuration parsed from URDF:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `string` | — | Joint name (e.g., `"J1"`) |
| `motor_id` | `int` | 0 | Teensy motor index |
| `steps_per_rev` | `int` | 200 | Full steps per motor revolution |
| `gear_ratio` | `double` | 10.0 | Reduction ratio |
| `microsteps` | `int` | 16 | Microstep setting |
| `home_offset_rad` | `double` | 0.0 | Position of limit switch in radians |

**Helper methods:**
- `stepsPerOutputRev()` → `steps_per_rev * microsteps * gear_ratio`
- `radToSteps(rad)` → convert radians to step count
- `stepsToRad(steps)` → convert step count to radians

**Class `Ar4System`** — `hardware_interface::SystemInterface` implementation.

#### `include/ar4_hardware_interface/serial_port.hpp`

POSIX serial port wrapper.

**Class `SerialPort`:**
- `open(device, baud_rate)` → configure termios (8N1, raw mode, no flow control)
- `writeLine(line)` → write string + `\n`
- `readLine(timeout_ms=50)` → poll-based line reader, strips `\r\n`
- `close()` → close file descriptor
- `isOpen()` → check if port is open

Supports baud rates: 9600, 19200, 38400, 57600, 115200, 230400, 460800.

#### `include/ar4_hardware_interface/teensy_protocol.hpp`

Thread-safe typed interface for the Teensy serial protocol.

**Class `TeensyProtocol`:**

| Method | Serial Command | Return |
|--------|---------------|--------|
| `ping()` | `PING` → `PONG` | `bool` |
| `enable()` | `EN` → `OK` | `bool` |
| `disable()` | `DIS` → `OK` | `bool` |
| `moveTo(id, steps)` | `MT <id> <steps>` → `OK` | `bool` |
| `getPositions()` | `GP` → `POS <s0> ...` | `vector<long>` |
| `home(id, timeout_ms=30000)` | `HOME <id>` → `HOMED <id>` | `bool` |
| `stop()` | `STOP` → `OK` | `bool` |
| `mutex()` | — | `std::mutex&` |

All methods lock a `std::mutex` to protect serial access from concurrent calls (read/write from CM thread, calibrate from service callback thread).

---

### Source Files

#### `src/ar4_system.cpp`

Plugin lifecycle and real-time read/write loop.

**Lifecycle methods:**

| Method | What it does |
|--------|-------------|
| `on_init(params)` | Parse URDF `<param>` tags: `serial_port`, `baud_rate`, per-joint `motor_id`, `steps_per_rev`, `gear_ratio`, `microsteps`, `home_offset_rad` |
| `on_configure()` | Open serial port, wait 2s for Teensy boot, send `PING`, create `/ar4_hardware/calibrate` service |
| `on_activate()` | Send `EN`, set commands = current state (no jump) |
| `on_deactivate()` | Send `DIS` |
| `on_cleanup()` | Reset service, close serial port |

**Real-time loop:**

| Method | Behavior |
|--------|----------|
| `read()` | If not homed: report 0.0 for all joints. If homed: send `GP`, convert steps → radians, compute velocity from position delta |
| `write()` | If not homed: skip. If homed: for each joint, convert commanded radians → steps, send `MT` if changed |

**Calibrate service** (`std_srvs/Trigger` on `/ar4_hardware/calibrate`):
- Iterates over all configured joints, sends `HOME <motor_id>` with 30s timeout
- On success: sets `is_homed_ = true`, position tracking becomes active
- On failure: reports which motor failed, `is_homed_` stays false

#### `src/serial_port.cpp`

POSIX termios serial implementation.
- Opens device in non-blocking mode (`O_NONBLOCK`)
- Configures raw mode (no echo, no canonical processing, no signals)
- Uses `poll()` with deadline for timeout-based line reading
- Reads character-by-character until `\n`

#### `src/teensy_protocol.cpp`

Command serialization and response parsing.
- `sendAndExpect(cmd, expected_prefix, timeout_ms)` — sends command, reads lines until matching prefix or timeout
- Skips informational lines (e.g., Teensy boot messages)
- Returns `ERR` lines so callers can detect firmware-level errors

---

## URDF Configuration

The plugin is activated through URDF `<ros2_control>` blocks in `ar4_ros2_control.urdf.xacro`:

```xml
<ros2_control name="ar4_real_hardware" type="system">
  <hardware>
    <plugin>ar4_hardware_interface/Ar4System</plugin>
    <param name="serial_port">/dev/ttyACM0</param>
    <param name="baud_rate">115200</param>
  </hardware>

  <joint name="J1">
    <param name="motor_id">0</param>
    <param name="steps_per_rev">200</param>
    <param name="gear_ratio">40.0</param>
    <param name="microsteps">16</param>
    <param name="home_offset_rad">2.967</param>
    ...
  </joint>

  <joint name="J2">
    <param name="motor_id">1</param>
    <param name="steps_per_rev">200</param>
    <param name="gear_ratio">40.0</param>
    <param name="microsteps">16</param>
    <param name="home_offset_rad">-0.7330</param>
    ...
  </joint>

  <joint name="J3">
    <param name="motor_id">2</param>
    <param name="steps_per_rev">200</param>
    <param name="gear_ratio">50.0</param>
    <param name="microsteps">16</param>
    <param name="home_offset_rad">-1.5533</param>
    ...
  </joint>
</ros2_control>
```

**Hardware-level parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `serial_port` | `/dev/ttyACM0` | Teensy USB serial device |
| `baud_rate` | `115200` | Serial baud rate |

**Per-joint parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `motor_id` | Yes | Teensy motor index (0-based) |
| `steps_per_rev` | Yes | Motor full steps per revolution |
| `gear_ratio` | Yes | Reduction ratio |
| `microsteps` | Yes | Microstep setting on driver |
| `home_offset_rad` | Yes | Limit switch position in radians from zero |

---

## Homing and Calibration

### Not-Homed State (default on startup)

- `read()` reports `position = 0.0`, `velocity = 0.0` for all joints
- `write()` does not send any `MT` commands to Teensy
- Teensy also rejects `MT` commands for unhomed motors (defense in depth)
- Controllers can run but J1, J2, J3, J5 will not physically move

### Calibration Procedure

```bash
# Trigger homing
ros2 service call /ar4_hardware/calibrate std_srvs/srv/Trigger

# Response on success:
#   success: true
#   message: "All joints homed successfully"

# Response on failure:
#   success: false
#   message: "Homing failed for one or more joints"
```

After successful calibration:
- `read()` sends `GP` and converts step counts to radians
- `write()` converts commanded radians to steps and sends `MT` commands
- Position is referenced to the limit switch offset (e.g., +170° = 2.967 rad)

---

## Thread Safety

| Thread | Access |
|--------|--------|
| Controller Manager (read/write) | Calls `read()` and `write()` on the CM update thread |
| Service callback (calibrate) | Runs on the node's executor thread |

All serial access goes through `TeensyProtocol`, which locks a `std::mutex` around every command/response exchange. This prevents interleaved serial communication between the CM thread and the service callback thread.

---

## Building

```bash
cd ~/manipulator_ros_control
colcon build --packages-select ar4_hardware_interface
source install/setup.bash
```

**Verify plugin registration:**
```bash
ros2 pkg prefix ar4_hardware_interface
# Should print the install path

# Check plugin is discoverable
ros2 control list_hardware_components
# After launching, should show: ar4_j1_hardware [active]
```

---

## Usage

### Launch with Real Hardware

```bash
# Default serial port (/dev/ttyACM0)
ros2 launch manipulator_bringup ar4_bringup.launch.py

# Custom serial port
ros2 launch manipulator_bringup ar4_bringup.launch.py serial_port:=/dev/ttyUSB0

# Custom baud rate
ros2 launch manipulator_bringup ar4_bringup.launch.py baud_rate:=230400
```

### Check Hardware Status

```bash
# List hardware components
ros2 control list_hardware_components
# Expected:
#   ar4_real_hardware   [active]  ar4_hardware_interface/Ar4System   (J1, J2, J3, J5)
#   ar4_mock_hardware   [active]  mock_components/GenericSystem      (J4, J6)

# Monitor joint states
ros2 topic echo /joint_states --once
```

### Calibrate and Move

```bash
# 1. Home all real joints
ros2 service call /ar4_hardware/calibrate std_srvs/srv/Trigger

# 2. Move J1 to 0.5 rad (~28.6°)
ros2 action send_goal /arm_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory "{
    trajectory: {
      joint_names: [J1, J2, J3, J4, J5, J6],
      points: [{positions: [0.5, 0.0, 0.0, 0.0, 0.0, 0.0], time_from_start: {sec: 3}}]
    }
  }"
```

---

## Adding a New Joint

To move a joint from mock to real hardware (e.g., J4 or J6):

1. **`ar4_ros2_control.urdf.xacro`** — Move the joint's `<joint>` block from `ar4_mock_hardware` to `ar4_real_hardware`, add motor params (`motor_id`, `steps_per_rev`, `gear_ratio`, `microsteps`, `home_offset_rad`).
2. **Teensy firmware** — Increase `NUM_JOINTS`, add joint entry to `JOINTS[]` array in `joints_config.h`.
3. **No changes** to `ar4_system.cpp`, `serial_port.cpp`, `teensy_protocol.cpp`, or launch files.

### J5 Wiring (MKS SERVO42C + NEMA 17 + T8 lead screw)

| MKS SERVO42C | Teensy 4.1 |
|---|---|
| STP | Pin 8 |
| DIR | Pin 9 |
| EN | not connected (self-enables) |
| GND | shared GND |

| Limit Switch | Teensy 4.1 |
|---|---|
| COM | GND |
| NC | Pin 27 |

**Note:** J5 uses a T8×8mm lead screw linear actuator instead of a gear reducer. The lead screw converts linear motion to wrist rotation via a linkage. The `gear_ratio` in URDF is a placeholder (1.0) — calibrate empirically after wiring.

---

## Related Documentation

- **Teensy Firmware:** `../firmware/ar4_teensy.md`
- **AR4 Description:** `../ar4_description/package_structure.md`
- **AR4 Bringup Launch:** `../manipulator_bringup/launch_files.md`
- **Project Overview:** `../project_structure/overview.md`
