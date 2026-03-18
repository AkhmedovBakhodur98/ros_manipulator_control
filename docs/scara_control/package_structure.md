# scara_control Package Documentation

## Overview

The `scara_control` package provides a reusable Python library for high-level SCARA arm control. The core class `ScaraClient` attaches to any ROS2 node and communicates directly with joint trajectory controllers — no dependency on project-specific infrastructure like `move_joint_group_server`.

**Key design principle:** Composable library, not a standalone Node. Attach to any ROS2 node and get full SCARA control out of the box.

## Package Structure

```
src/scara_control/
├── package.xml                    # ament_python package manifest
├── setup.py                       # Python package setup (library + scara_lock_server node)
├── setup.cfg                      # ament_python install paths
├── resource/
│   └── scara_control              # ament resource index marker
└── scara_control/
    ├── __init__.py                # Re-exports all public types
    ├── scara_client.py            # ScaraClient implementation
    └── scara_lock_server.py       # Distributed lock node for SCARA mutual exclusion
```

---

## File Descriptions

### Build Files

#### `package.xml`
ROS2 package manifest for `ament_python` build type.

**Package information:**
- Name: `scara_control`
- Version: `0.1.0`
- Build type: `ament_python`
- License: MIT

**Dependencies:**

| Category | Package | Purpose |
|----------|---------|---------|
| **Build** | `ament_python` | ROS2 Python build system |
| **ROS2 Core** | `rclpy` | ROS2 Python client library |
| **Messages** | `control_msgs` | FollowJointTrajectory action |
| **Messages** | `trajectory_msgs` | JointTrajectoryPoint messages |
| **Messages** | `sensor_msgs` | JointState messages |
| **Messages** | `std_srvs` | Trigger service for tool control |
| **Messages** | `builtin_interfaces` | Duration type |
| **Exec** | `scara_description` | Config auto-discovery (scara_params.yaml) |
| **Exec** | `pyyaml` | YAML configuration parsing |

#### `setup.py`
Standard ament_python setup with `entry_points` for the `scara_lock_server` node:

```python
entry_points={
    'console_scripts': [
        'scara_lock_server = scara_control.scara_lock_server:main',
    ],
},
```

#### `setup.cfg`
Standard ament_python install script paths.

#### `resource/scara_control`
Empty marker file for the ament resource index. Required for `ros2 pkg list` discovery.

---

### Source Code

#### `scara_control/__init__.py`
Re-exports all public types for convenient importing:

```python
from scara_control import ScaraClient, ScaraResult, ElbowConfig
```

**Exported symbols:**

| Symbol | Type | Description |
|--------|------|-------------|
| `ScaraClient` | class | Main control interface |
| `ScaraResult` | dataclass | Motion result with positions and timing |
| `ElbowConfig` | enum | `ELBOW_UP` or `ELBOW_DOWN` |
| `CartesianPose` | dataclass | (x, y, phi) position |
| `IKSolution` | dataclass | IK result with validity |
| `IKDiagnostic` | dataclass | IK failure analysis |
| `ScaraNotReady` | exception | SCARA controller unavailable |
| `ZAxisNotConfigured` | exception | Z-axis method called without Z config |
| `ZAxisNotReady` | exception | Z controller unavailable |

#### `scara_control/scara_client.py`
Core implementation of the `ScaraClient` class.

**See detailed documentation:** [scara_client.md](scara_client.md)

#### `scara_control/scara_lock_server.py`
Lightweight ROS2 node providing a distributed lock for SCARA mutual exclusion. Prevents concurrent access to the SCARA arm from multiple action servers (e.g. `ExtractBoxServer` and `PickItemsFromWarehouseServer`).

**Services provided:**
- `/scara_lock/acquire` (`std_srvs/srv/Trigger`) — returns `success=True` if lock granted, `success=False` if already held
- `/scara_lock/release` (`std_srvs/srv/Trigger`) — releases the lock, returns `success=True`

Simple boolean state (`_held`) with logging. Uses `ReentrantCallbackGroup`.

---

## Architecture

### Two-Controller Design

```
Any ROS2 Node
┌──────────────┐
│              │    FollowJointTrajectory     ┌─────────────────────────┐
│  ScaraClient ├──────────────────────────────► scara_controller        │
│  (attached)  │                              │ (3 joints: XY + orient) │
│              │                              └─────────────────────────┘
│              │    FollowJointTrajectory     ┌─────────────────────────┐
│              ├──────────────────────────────► picker_z_controller     │
│              │    (optional)                │ (1 joint: Z axis)       │
│              │                              └─────────────────────────┘
│              │    /joint_states             ┌─────────────────────────┐
│              ◄──────────────────────────────┤ Joint State Broadcaster │
│              │                              └─────────────────────────┘
│              │    std_srvs/Trigger          ┌─────────────────────────┐
│              ├──────────────────────────────► Tool Service (optional) │
│              │                              └─────────────────────────┘
│              │    std_srvs/Trigger          ┌─────────────────────────┐
│              ├──────────────────────────────► ScaraLockServer         │
│              │    (optional)                │ /scara_lock/acquire     │
│              │                              │ /scara_lock/release     │
└──────────────┘                              └─────────────────────────┘
```

`ScaraClient` sends goals to **two independent controllers**. They never conflict because:
- `scara_controller` only claims SCARA joints (shoulder, elbow, wrist)
- Z controller only claims its one joint (e.g. `selector_frame_picker_frame_joint`)

For methods that involve both Z and XY (`move_to_point(z=...)`, `move_linear(z=...)`):
- **Z moves first**, then **XY moves** — sequential to prevent collisions

### What ScaraClient Does NOT Depend On

- `move_joint_group_server`
- `ros_control` package
- `manipulator_description`
- Any project-specific action/service

---

## Configuration

`ScaraClient` reads from `scara_description/config/scara_params.yaml`. Existing sections (`kinematics`, `joints`) provide link lengths and limits. The `scara_client` section (added for this package) provides runtime config.

**Config file:** `src/scara_description/config/scara_params.yaml`

### scara_client Section

```yaml
scara_client:
  controller_action: "/scara_controller/follow_joint_trajectory"
  joint_states_topic: "/joint_states"
  position_tolerance: 0.01    # rad
  timeout: 30.0               # seconds

  z_axis:
    enabled: true
    joint_name: "selector_frame_picker_frame_joint"
    controller_action: "/picker_z_controller/follow_joint_trajectory"
    limits: {lower: -0.01, upper: 0.3, velocity: 1.0}

  tool:
    type: "service"            # "service" | "topic" | "none"
    activate: "/scara_tool/activate"
    deactivate: "/scara_tool/deactivate"
    service_type: "std_srvs/srv/Trigger"
    settle_time: 0.5

  home:
    shoulder: 0.0
    elbow: 0.0
    wrist: 0.0
    z: 0.0

  elbow_flip:
    enabled: true
    joint_limit_margin: 0.15   # rad
    flip_duration: 1.5         # seconds
    z_unhook_offset: 0.03      # m

  linear_motion:
    max_deviation: 0.005       # m (5mm)

  defaults:
    velocity_scaling: 0.5
    linear_velocity: 0.1       # m/s
    linear_step_size: 0.005    # m
    elbow_up: true
```

### Portability

To use SCARA on a different Z mechanism:

```yaml
scara_client:
  z_axis:
    enabled: true
    joint_name: "my_lift_joint"
    controller_action: "/lift_controller/follow_joint_trajectory"
    limits: {lower: 0.0, upper: 1.0, velocity: 0.5}
```

Without Z-axis (pure planar):

```yaml
scara_client:
  z_axis:
    enabled: false
```

---

## ROS2 Interfaces

### Subscribed Topics

| Topic | Type | QoS | Description |
|-------|------|-----|-------------|
| `/joint_states` | `sensor_msgs/JointState` | BEST_EFFORT | Current joint positions |

### Action Clients

| Action | Type | Description |
|--------|------|-------------|
| `/scara_controller/follow_joint_trajectory` | `control_msgs/action/FollowJointTrajectory` | SCARA arm trajectory (always) |
| `/picker_z_controller/follow_joint_trajectory` | `control_msgs/action/FollowJointTrajectory` | Z-axis trajectory (optional) |

### Service Clients (Optional)

| Service | Type | Description |
|---------|------|-------------|
| `/scara_tool/activate` | `std_srvs/srv/Trigger` | Activate end-effector tool |
| `/scara_tool/deactivate` | `std_srvs/srv/Trigger` | Deactivate end-effector tool |
| `/scara_lock/acquire` | `std_srvs/srv/Trigger` | Acquire distributed SCARA lock (backward compatible — works without lock server) |
| `/scara_lock/release` | `std_srvs/srv/Trigger` | Release distributed SCARA lock |

### Services Provided (by `scara_lock_server`)

| Service | Type | Description |
|---------|------|-------------|
| `/scara_lock/acquire` | `std_srvs/srv/Trigger` | Acquire the SCARA lock (`success=True` if granted) |
| `/scara_lock/release` | `std_srvs/srv/Trigger` | Release the SCARA lock |

---

## Usage Examples

### Basic — Move Joints

```python
from scara_control import ScaraClient

class MyNode(Node):
    def __init__(self):
        super().__init__('my_node')
        self.scara = ScaraClient(self)

    async def demo(self):
        result = await self.scara.move_joints(shoulder=0.5, elbow=-1.0)
        result = await self.scara.move_joints(
            shoulder=0.0, elbow=0.0, wrist=0.0, velocity=0.3
        )
```

### IK — Move to Point

```python
    async def reach_target(self):
        result = await self.scara.move_to_point(x=0.5, y=0.1)
        result = await self.scara.move_to_point(
            x=0.4, y=-0.2, z=0.2, orientation=1.57, elbow_up=False
        )
```

### Pick and Place

```python
    async def pick_and_place(self):
        result = await self.scara.pick_at(x=0.5, y=0.1, z=0.05)
        if result.success:
            result = await self.scara.place_at(x=0.3, y=-0.1, z=0.2)
```

### Query State (No Movement)

```python
    def check_state(self):
        x, y, phi = self.scara.get_tcp_position()
        if self.scara.is_reachable(0.6, 0.1):
            theta1, theta2, theta3 = self.scara.compute_ik(0.6, 0.1)
        config = self.scara.get_elbow_config()  # ELBOW_UP or ELBOW_DOWN
```

---

## Distributed Lock (SCARA Mutual Exclusion)

When multiple action servers (e.g. `ExtractBoxServer`, `PickItemsFromWarehouseServer`) share the same physical SCARA arm, concurrent access must be prevented. The `scara_lock_server` node provides a simple distributed lock:

1. **Lock server** (`scara_lock_server`) holds a boolean `_held` state
2. **ScaraClient** provides `acquire()` / `release()` methods that call the lock services
3. **Action servers** call `acquire()` before SCARA work and `release()` in a `finally` block

**Backward compatible:** If the lock server is not running, `acquire()` returns `True` with a warning — existing code works unchanged.

**How it works end-to-end:**
```
PickItemsFromWarehouse:
  Phase 2 → calls ExtractBox action
               ExtractBox acquires lock ✓
               ExtractBox does SCARA work
               ExtractBox releases lock
  Phase 3 → PickItems acquires lock ✓
             PickItems does pick-and-place
             PickItems releases lock

Collision blocked: ExtractBox during PickItems Phase 3
  PickItems holds lock
  ExtractBox tries acquire → fails → returns "SCARA arm is busy"
```

---

## Building

```bash
cd ~/manipulator_ros_control
colcon build --packages-select scara_control
source install/setup.bash
```

**Verify:**
```bash
ros2 pkg list | grep scara_control
python3 -c "from scara_control import ScaraClient, ScaraResult, ElbowConfig"

# Verify lock server node
ros2 run scara_control scara_lock_server
# In another terminal:
ros2 service list | grep scara_lock
```

---

## Related Documentation

- **ScaraClient Implementation:** [scara_client.md](scara_client.md)
- **Architecture Design:** [scara_client_architecture.md](scara_client_architecture.md)
- **SCARA Description:** `docs/scara_description/package_structure.md`
- **SCARA Controllers:** `src/scara_description/config/scara_controllers.yaml`
- **SCARA Parameters:** `src/scara_description/config/scara_params.yaml`
