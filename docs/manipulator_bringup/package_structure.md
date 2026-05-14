# Manipulator Bringup Package Documentation

## Overview

The `manipulator_bringup` package provides a unified launch system for starting all infrastructure components of the manipulator ROS2 control system. This package orchestrates the startup of robot descriptions, controllers, and high-level control interfaces, automatically configuring them based on system requirements.

**Key Features:**
- Single launch file to start entire system
- Automatic controller discovery and configuration
- Dynamic parameter generation for unified control interface
- Support for optional components (SCARA arm)
- Flexible configuration via launch arguments

---

## Package Structure

```
src/manipulator_bringup/
├── CMakeLists.txt                    # Build configuration
├── package.xml                       # Package metadata and dependencies
└── launch/
    ├── manipulator_bringup.launch.py # Main launch file (starts all manipulator infrastructure on mock hardware)
    ├── ar4_bringup.launch.py         # AR4 standalone bringup (ros2_control + RViz)
    ├── ar4_display.launch.py         # AR4 display-only (joint_state_publisher_gui + RViz, no ros2_control)
    └── ethercat_bench.launch.py      # Stage 6 EtherCAT single-slave bring-up (real A6-200EC, no mock, no action servers)
```

---

## File Descriptions

### Build Files

#### `CMakeLists.txt`
CMake build configuration for the ROS2 package.

**Key sections:**
- Finds required dependencies: `ament_cmake`
- Installs `launch/` directory

**Dependencies:**
- `ament_cmake` - ROS2 build system

#### `package.xml`
ROS2 package manifest defining package metadata and dependencies.

**Package information:**
- Name: `manipulator_bringup`
- Version: `0.1.0`
- Description: Unified launch system for manipulator ROS2 control infrastructure
- License: Apache-2.0

**Dependencies:**

| Category | Package | Purpose |
|----------|---------|---------|
| **Build** | `ament_cmake` | ROS2 build system |
| **Runtime** | `manipulator_description` | Manipulator robot description |
| **Runtime** | `scara_description` | SCARA arm description (optional) |
| **Runtime** | `ar4_description` | AR4 arm description (standalone) |
| **Runtime** | `ros_control` | Unified control interface |
| **Runtime** | `manipulator_hardware_interface` | EtherCAT slave PDO YAML and bench controllers (used by `ethercat_bench.launch.py`) |
| **Runtime** | `controller_manager` | Controller lifecycle management |
| **Runtime** | `robot_state_publisher` | TF tree publishing |
| **Runtime** | `rviz2` | Visualization (optional) |
| **Python** | `python3-yaml` | YAML parsing for controller config extraction |

---

## Launch Files

### `launch/manipulator_bringup.launch.py`

**Main launch file** that starts all manipulator infrastructure components.

**What it does:**
1. Starts robot description (manipulator + optional SCARA)
2. Starts ros2_control controller manager
3. Spawns all controllers (manipulator, gripper, optional SCARA)
4. Starts unified control interface (`move_joint_group_server`)
5. Optionally launches RViz2 visualization

**Key Features:**
- **Automatic controller discovery**: Parses controller YAML files to extract controller-to-joints mapping
- **Dynamic parameter generation**: Builds `controller_joints` parameter for `move_joint_group_server` automatically
- **Conditional component loading**: Only starts SCARA-related components when `use_scara:=true`
- **Single source of truth**: Uses existing controller YAML files, no duplication

**See:** [launch_files.md](launch_files.md) for detailed documentation.

### `launch/ar4_bringup.launch.py`

**AR4 standalone launch file** — starts the AR4 6-DOF arm with ros2_control and RViz.

**What it does:**
1. Processes AR4 xacro with `use_ros2_control:=true`
2. Starts `robot_state_publisher`
3. Starts `controller_manager` with `ar4_controllers.yaml`
4. Spawns `joint_state_broadcaster`
5. Spawns `arm_controller` (delayed, after joint_state_broadcaster via OnProcessExit)
6. Optionally launches RViz2 with pre-configured `ar4.rviz`

**Launch arguments:**
| Argument | Default | Description |
|----------|---------|-------------|
| `use_sim_time` | `false` | Use simulation clock |
| `rviz` | `true` | Launch RViz2 |
| `serial_port` | `/dev/ttyACM0` | Teensy 4.1 serial port |
| `baud_rate` | `115200` | Serial baud rate |

**Usage:**
```bash
# Full AR4 bringup with RViz
ros2 launch manipulator_bringup ar4_bringup.launch.py

# Custom serial port
ros2 launch manipulator_bringup ar4_bringup.launch.py serial_port:=/dev/ttyUSB0

# Without RViz
ros2 launch manipulator_bringup ar4_bringup.launch.py rviz:=false
```

**Note:** This launch file is completely independent from the manipulator system. No action servers, no SCARA integration, no gripper.

### `launch/ar4_display.launch.py`

**AR4 display-only launch file** — visualization with manual joint control via sliders. No ros2_control, no hardware.

**What it does:**
1. Processes AR4 xacro with `use_ros2_control:=false`
2. Starts `robot_state_publisher`
3. Starts `joint_state_publisher_gui` (slider GUI for manual joint control)
4. Optionally launches RViz2

**Launch arguments:**
| Argument | Default | Description |
|----------|---------|-------------|
| `rviz` | `true` | Launch RViz2 |

**Usage:**
```bash
# Display with joint sliders and RViz
ros2 launch manipulator_bringup ar4_display.launch.py

# Without RViz (GUI sliders only)
ros2 launch manipulator_bringup ar4_display.launch.py rviz:=false
```

**Note:** No controllers, no hardware interface, no serial connection. Just visualization with manual joint manipulation.

### `launch/ethercat_bench.launch.py`

**Stage 6 single-slave EtherCAT bring-up.** Brings up the A6-200EC at EEPROM alias 6 (the bench drive with motor connected) under `ros2_control` and the ICube `ethercat_driver_ros2` stack. Intentionally minimal — no `move_joint_group_server`, no `gripper_service`, no SCARA, no RViz — purely a smoke / verification path for the EtherCAT data plane.

**What it does:**
1. Renders `manipulator_description/urdf/robot.urdf.xacro` with `hardware:=ethercat_bench` and `slave_config_dir:=$(find manipulator_hardware_interface)/config/ethercat`. The expanded URDF carries the full manipulator geometry plus a tiny `bench_joint` branch off `world`.
2. Starts `robot_state_publisher` (so `/robot_description` is available for tooling).
3. Starts `controller_manager` (`ros2_control_node`) with `manipulator_hardware_interface/config/ethercat_bench_controllers.yaml` (1000 Hz update rate, three controllers).
4. Spawns `joint_state_broadcaster` first.
5. After the broadcaster spawner exits, spawns `forward_position_controller` (active) and `bench_trajectory_controller` (loaded **inactive**, switch in via `ros2 control switch_controllers`).

**No launch arguments** — the configuration is hard-coded for the bench (alias 6, mode 8 / CSP, 1 kHz). Stage 7 will introduce a multi-slave variant with arguments.

**Usage:**

```bash
# Bench bring-up (master must be 'active', slave at alias 6 in PREOP)
ros2 launch manipulator_bringup ethercat_bench.launch.py

# Verification:
ros2 control list_hardware_components   # manipulator_ec_bench → state=active
ros2 control list_controllers           # joint_state_broadcaster + forward_position_controller active
ethercat slaves                         # alias 6 in OP
ros2 topic echo /joint_states --once    # bench_joint position in raw encoder counts

# Move (raw encoder counts; +30000 ≈ 0.23 motor rev):
ros2 topic pub --once /forward_position_controller/commands \
    std_msgs/msg/Float64MultiArray "{data: [<current+30000>]}"

# Switch to JTC (slow trajectory):
ros2 control switch_controllers \
    --deactivate forward_position_controller \
    --activate bench_trajectory_controller
```

**RT-tuning required for stability** (Stage 6 exit criterion — verified 2026-05-14, 600 s clean): wrap as `chrt -f 80 ros2 launch manipulator_bringup ethercat_bench.launch.py`, AND ensure the eno1 NIC IRQ is pinned to CPU 1 (one-shot `sudo bash -c 'echo 2 > /proc/irq/56/smp_affinity'`, or persist via the `ethercat-irq-pin.service` recipe in `docs/manipulator_hardware_interface/rt_tuning.md`). Both knobs together drive `Working counter`/`UNMATCHED`/`SKIPPED`/`TIMED OUT` to **zero** over a 10-minute soak. Without the IRQ pin, even with `chrt`, you get ≈ 1 `TIMED OUT` per 44 s. **Never add `taskset -c 1`** — co-locating the ROS callbacks with the RT thread on the isolated CPU produces multi-millisecond PDO read times. See `docs/manipulator_hardware_interface/bringup.md` Stage 6 for the measurement table.

---

## Architecture

### System Integration

```
┌─────────────────────────────────────────────────────────────────┐
│              manipulator_bringup.launch.py                      │
│                    (Orchestrator)                               │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│   Robot       │  │   Controller  │  │   Unified     │
│   Description │  │   Manager     │  │   Control     │
│               │  │               │  │   Interface  │
│ - URDF/Xacro  │  │ - Controllers │  │ - Action      │
│ - TF Tree     │  │ - Hardware    │  │   Server     │
│               │  │   Interface   │  │               │
└───────┬───────┘  └───────┬───────┘  └───────┬───────┘
        │                  │                   │
        └──────────────────┼───────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │   Hardware Interface  │
              │   (Mock/Real)          │
              └────────────────────────┘
```

### Component Flow

```
1. Launch manipulator_bringup.launch.py
   │
   ├─► Parse controller YAML files
   │   ├─► manipulator_controllers.yaml
   │   └─► scara_controllers.yaml (if use_scara)
   │
   ├─► Extract controller->joints mapping
   │   ├─► manipulator_controller: [base_main_frame_joint, ...]
   │   ├─► gripper_controller: [selector_left_container_jaw_joint, ...]
   │   └─► scara_controller: [scara_shoulder_joint, ...] (if enabled)
   │
   ├─► Start robot_state_publisher
   │   └─► Publishes TF tree from URDF
   │
   ├─► Start controller_manager
   │   ├─► Loads hardware interface
   │   └─► Manages controller lifecycle
   │
   ├─► Spawn controllers
   │   ├─► joint_state_broadcaster (always)
   │   ├─► manipulator_controller (always)
   │   ├─► gripper_controller (always)
   │   └─► scara_controller (if use_scara)
   │
   ├─► Start move_joint_group_server
   │   └─► Passes controller_joints parameter (auto-generated)
   │
   └─► Start RViz2 (optional)
       └─► Visualization
```

---

## Design Decisions

### Why Automatic Controller Discovery?

**Problem:** `move_joint_group_server` needs to know which joints belong to which controllers.

**Options Considered:**
1. **Manual YAML config** - Separate file with controller->joints mapping
2. **Automatic parsing** - Extract from existing controller YAML files

**Decision: Automatic parsing**

**Rationale:**
- **Single source of truth**: Controller YAML files already define joints
- **No duplication**: Avoids maintaining two separate configs
- **Automatic sync**: Changes to controllers automatically reflected
- **Less error-prone**: No risk of config drift

### Controller Mapping Extraction

The launch file parses controller YAML files to extract:

```yaml
# From manipulator_controllers.yaml
manipulator_controller:
  ros__parameters:
    joints:
      - base_main_frame_joint
      - main_frame_selector_frame_joint
      - selector_frame_picker_frame_joint

# Extracted mapping:
controller_joints = {
  'manipulator_controller': [
    'base_main_frame_joint',
    'main_frame_selector_frame_joint',
    'selector_frame_picker_frame_joint'
  ],
  'gripper_controller': [...],
  'scara_controller': [...]  # if use_scara
}
```

This mapping is passed to `move_joint_group_server` as a ROS2 parameter.

### Excluded Controllers

The following controllers are **not** included in the mapping:
- `joint_state_broadcaster` - Not a control controller, only publishes state

Only **control controllers** (those that accept commands) are included:
- `manipulator_controller` - Trajectory control
- `gripper_controller` - Position control
- `scara_controller` - Trajectory control (if enabled)

---

## Dependencies

### Package Dependencies

| Package | Purpose |
|---------|---------|
| `manipulator_description` | Robot description and controllers |
| `scara_description` | SCARA arm description (optional) |
| `ros_control` | Unified control action server |
| `controller_manager` | Controller lifecycle management |
| `robot_state_publisher` | TF tree publishing |
| `rviz2` | Visualization (optional) |

### Python Dependencies

| Package | Purpose |
|---------|---------|
| `python3-yaml` | YAML parsing for controller config extraction |

---

## Usage

### Basic Usage

**Start full system (manipulator only):**
```bash
ros2 launch manipulator_bringup manipulator_bringup.launch.py
```

**Start with SCARA arm:**
```bash
ros2 launch manipulator_bringup manipulator_bringup.launch.py use_scara:=true
```

**Start without visualization:**
```bash
ros2 launch manipulator_bringup manipulator_bringup.launch.py rviz:=false
```

**Start with simulation time:**
```bash
ros2 launch manipulator_bringup manipulator_bringup.launch.py use_sim_time:=true
```

### Launch Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `use_scara` | `false` | Attach SCARA arm to picker_frame |
| `rviz` | `true` | Launch RViz2 visualization |
| `use_sim_time` | `false` | Use simulation clock |

---

## What Gets Started

When you launch `manipulator_bringup.launch.py`, the following infrastructure is started:

### Always Started

1. **robot_state_publisher**
   - Publishes TF tree from URDF
   - Topic: `/robot_description`

2. **controller_manager** (ros2_control_node)
   - Manages controller lifecycle
   - Services: `/controller_manager/*`

3. **joint_state_broadcaster**
   - Publishes joint states
   - Topic: `/joint_states`

4. **manipulator_controller**
   - Trajectory control for main axes
   - Action: `/manipulator_controller/follow_joint_trajectory`

5. **gripper_controller**
   - Position control for gripper jaws
   - Topic: `/gripper_controller/commands`

6. **move_joint_group_server**
   - Unified control interface
   - Action: `/move_joint_group`
   - Automatically configured with controller->joints mapping

### Conditionally Started

7. **scara_controller** (if `use_scara:=true`)
   - Trajectory control for SCARA arm
   - Action: `/scara_controller/follow_joint_trajectory`

8. **rviz2** (if `rviz:=true`)
   - 3D visualization
   - Uses pre-configured RViz config

---

## Benefits

### For Users

- **Simple**: One command to start everything
- **Automatic**: No manual configuration needed
- **Flexible**: Launch arguments for customization
- **Complete**: All infrastructure in one place

### For Developers

- **Maintainable**: Single source of truth for controller configs
- **Extensible**: Easy to add new controllers or components
- **Consistent**: Same launch file for all scenarios
- **Documented**: Clear architecture and design decisions

---

## Future Extensions

Potential additions to the bringup package:

1. **Multiple launch variants**
   - `manipulator_only.launch.py` - Just manipulator (no SCARA, no unified control)
   - `full_system.launch.py` - Convenience wrapper for full system

2. **Monitoring and diagnostics**
   - System health monitoring
   - Controller status checking
   - Diagnostic aggregator

3. **Configuration validation**
   - Verify controller configs before starting
   - Check for missing dependencies
   - Validate joint names

4. **Logging configuration**
   - Centralized log configuration
   - Log level management

---

## Related Documentation

- **Launch Files**: [launch_files.md](launch_files.md) - Detailed launch file documentation
- **Manipulator Description**: `../manipulator_description/package_structure.md`
- **SCARA Description**: `../scara_description/package_structure.md`
- **AR4 Description**: `../ar4_description/package_structure.md`
- **AR4 Control**: `../ar4_control/package_structure.md`
- **Unified Control**: `../ros_control/package_structure.md`

