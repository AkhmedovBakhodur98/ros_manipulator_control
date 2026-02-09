# ScaraClient Implementation

Detailed implementation documentation for the `ScaraClient` class — a composable Python library for SCARA arm control.

## Overview

`ScaraClient` is a composable class (not a Node) that attaches to any ROS2 node and provides high-level SCARA arm control. It communicates directly with joint trajectory controllers via `FollowJointTrajectory` action clients.

**Source file:** `src/scara_control/scara_control/scara_client.py`

---

## Data Types

### ScaraResult

Returned by all motion methods.

```python
@dataclass
class ScaraResult:
    success: bool                              # True if motion completed
    message: str                               # Status message
    joint_positions: tuple[float, float, float] # Final (shoulder, elbow, wrist) [rad]
    z_position: float                           # Final Z [m] (0.0 if no Z-axis)
    tcp_position: tuple[float, float, float]    # Final (x, y, phi) [m, m, rad]
    execution_time: float                       # Wall-clock seconds
```

### ElbowConfig

```python
class ElbowConfig(Enum):
    ELBOW_UP = "elbow_up"       # theta2 >= 0
    ELBOW_DOWN = "elbow_down"   # theta2 < 0
```

### CartesianPose

```python
@dataclass
class CartesianPose:
    x: float       # [m]
    y: float       # [m]
    phi: float     # TCP orientation [rad]
```

### IKSolution

```python
@dataclass
class IKSolution:
    shoulder: float        # theta1 [rad]
    elbow: float           # theta2 [rad]
    wrist: float           # theta3 [rad]
    valid: bool            # True if within joint limits
    elbow_config: ElbowConfig
```

### IKDiagnostic

Returned by `diagnose_ik_failure()` to explain why a target is unreachable.

```python
@dataclass
class IKDiagnostic:
    reason: str                 # 'too_far' | 'too_close' | 'joint_limit' | 'reachable'
    suggested_x_offset: float   # Base X adjustment needed [m]
    suggested_z_offset: float   # Base Z adjustment needed [m]
    distance: float             # Distance from base to target [m]
    workspace_min: float        # Min reach = L1 - L2 [m]
    workspace_max: float        # Max reach = L1 + L2 [m]
```

---

## Exceptions

| Exception | When Raised | Description |
|-----------|-------------|-------------|
| `ScaraNotReady` | `_send_scara_trajectory()` | SCARA controller action server not available within 5s |
| `ZAxisNotConfigured` | `move_z()`, `get_z_position()`, `get_tcp_position_3d()` | Z-axis method called but `z_axis.enabled: false` in config |
| `ZAxisNotReady` | `_send_z_trajectory()` | Z controller action server not available within 5s |

---

## Constructor

```python
ScaraClient(node: Node, config_path: str = None)
```

**Parameters:**
- `node` — Any ROS2 node instance. ScaraClient attaches its subscriptions and action clients to this node.
- `config_path` — Path to `scara_params.yaml`. If `None`, auto-discovers from `scara_description` package share directory (with source-tree fallback).

**On construction:**
1. Loads `scara_params.yaml` (kinematics, joint limits, client config)
2. Creates `/joint_states` subscriber (BEST_EFFORT QoS, `threading.Lock` for thread safety)
3. Creates `ActionClient` for `/scara_controller/follow_joint_trajectory`
4. If `z_axis.enabled: true` — creates second `ActionClient` for Z controller
5. If `tool.type: "service"` — creates `Trigger` service clients for tool activate/deactivate

**Config auto-discovery order:**
1. `get_package_share_directory('scara_description') / config / scara_params.yaml` (installed)
2. Source fallback: `<scara_client.py>/../../../scara_description/config/scara_params.yaml`

---

## State Queries (Synchronous)

These methods read current state without moving. Thread-safe via `threading.Lock`.

### get_joint_positions

```python
def get_joint_positions(self) -> tuple[float, float, float]
```

Returns current `(shoulder, elbow, wrist)` angles in radians from `/joint_states`. Returns `(0.0, 0.0, 0.0)` if no joint state received yet.

### get_z_position

```python
def get_z_position(self) -> float
```

Returns current Z position in meters. Raises `ZAxisNotConfigured` if Z-axis is disabled.

### get_tcp_position

```python
def get_tcp_position(self) -> tuple[float, float, float]
```

Returns `(x, y, phi)` — current TCP position via forward kinematics.

### get_tcp_position_3d

```python
def get_tcp_position_3d(self) -> tuple[float, float, float, float]
```

Returns `(x, y, z, phi)`. Raises `ZAxisNotConfigured` if Z-axis is disabled.

### has_z_axis

```python
def has_z_axis(self) -> bool
```

Returns `True` if Z-axis is configured and enabled.

### get_elbow_config

```python
def get_elbow_config(self) -> ElbowConfig
```

Returns `ELBOW_UP` if current elbow angle >= 0, else `ELBOW_DOWN`.

---

## Kinematics (Pure Computation)

No ROS communication, no movement. Can be called from any thread.

### compute_fk

```python
def compute_fk(self, shoulder: float, elbow: float, wrist: float) -> tuple[float, float, float]
```

Forward kinematics: `(theta1, theta2, theta3)` -> `(x, y, phi)`.

```
x   = L1 * cos(theta1) + L2 * cos(theta1 + theta2)
y   = L1 * sin(theta1) + L2 * sin(theta1 + theta2)
phi = theta1 + theta2 + theta3
```

### compute_ik

```python
def compute_ik(self, x: float, y: float, orientation: float = 0.0, elbow_up: bool = True) -> tuple[float, float, float]
```

Inverse kinematics: `(x, y, phi)` -> `(theta1, theta2, theta3)`. Raises `ValueError` if unreachable.

**IK equations (2R planar):**
```
cos(theta2) = (x^2 + y^2 - L1^2 - L2^2) / (2 * L1 * L2)
theta2 = atan2(+/-sqrt(1 - cos^2(theta2)), cos(theta2))
         elbow_up = +sqrt, elbow_down = -sqrt
theta1 = atan2(y, x) - atan2(L2*sin(theta2), L1 + L2*cos(theta2))
theta3 = orientation - theta1 - theta2
```

### is_reachable

```python
def is_reachable(self, x: float, y: float) -> bool
```

Returns `True` if `(L1 - L2) <= sqrt(x^2 + y^2) <= (L1 + L2)`.

### diagnose_ik_failure

```python
def diagnose_ik_failure(self, x: float, y: float, orientation: float = 0.0) -> IKDiagnostic
```

Analyzes why IK fails and suggests corrections:

| Reason | Meaning | Suggestion |
|--------|---------|------------|
| `too_far` | Target beyond max reach | `suggested_x_offset` = how much closer the base must be |
| `too_close` | Target inside min reach | `suggested_x_offset` = how much further the base must be |
| `joint_limit` | Workspace OK but both IK solutions exceed limits | — |
| `reachable` | Target is valid (at least one IK solution within limits) | — |

---

## Motion Methods (Async)

All motion methods are `async` and return `ScaraResult`. They must be called with `await` from an async context (e.g. a ROS2 action callback using `ReentrantCallbackGroup` + `MultiThreadedExecutor`).

### move_joints

```python
async def move_joints(
    self,
    shoulder: float = None,  # None = keep current
    elbow: float = None,
    wrist: float = None,
    velocity: float = 1.0,   # 0.0-1.0 scaling factor
) -> ScaraResult
```

Move SCARA joints to target angles. Joints set to `None` stay at current position.

**Trajectory time calculation:**
```
For each joint:
    time_i = |target_i - current_i| / (max_velocity_i * velocity_scaling)
total_time = max(time_i for all joints)       # bottleneck joint
total_time = max(total_time, 0.1)             # minimum 100ms
```

**Important:** Sends ALL 3 SCARA joints per trajectory point — required by `allow_partial_joints_goal: false` in scara_controller config.

### move_z

```python
async def move_z(self, z: float, velocity: float = 1.0) -> ScaraResult
```

Move Z-axis to target position. Raises `ZAxisNotConfigured` if disabled.

Validates target against Z joint limits before sending. Time calculation mirrors `move_joints` but for the single Z joint.

### move_to_point

```python
async def move_to_point(
    self,
    x: float, y: float,
    z: float = None,
    orientation: float = None,  # None = keep current phi
    elbow_up: bool = True,
    velocity: float = 1.0,
) -> ScaraResult
```

Move TCP to Cartesian point via IK.

**Motion order:**
1. If `z` specified: `move_z(z)` first (via Z controller)
2. Compute IK for (x, y, orientation)
3. If primary IK solution exceeds limits: try alternate elbow config
4. If both solutions fail: return `ScaraResult(success=False)`
5. Send joint trajectory to SCARA controller

**Orientation handling:** When `orientation=None`, the current TCP phi is preserved (wrist compensates for shoulder/elbow changes).

### move_linear

```python
async def move_linear(
    self,
    x: float, y: float,
    z: float = None,
    orientation: float = None,
    velocity: float = 0.1,       # m/s (Cartesian)
    step_size: float = 0.005,    # m interpolation step
    allow_elbow_flip: bool = False,
) -> ScaraResult
```

Straight-line TCP motion in Cartesian space. Generates multi-point trajectory via IK at each interpolation step.

**Algorithm:**
1. If `z` specified: move Z first
2. Compute current TCP via FK
3. Interpolate straight line from current to target with `step_size` spacing
4. For each waypoint: compute IK with consistent elbow config
5. **Verify linearity:** FK each IK result, check deviation from ideal line. Fail if > `max_deviation` (default 5mm)
6. If waypoint unreachable and `allow_elbow_flip=True`: delegate to `move_linear_with_flip()`
7. Build multi-point `FollowJointTrajectory` with `time_from_start = step_size / velocity * index`
8. Send to SCARA controller

**Why not joint-space interpolation?** Joint-space interpolation traces an arc in Cartesian space. For tasks like following a shelf edge or precise placement, linear TCP motion is required.

### move_linear_with_flip

```python
async def move_linear_with_flip(
    self,
    x: float, y: float,
    z: float = None,
    orientation: float = None,
    velocity: float = 0.1,
    step_size: float = 0.005,
    on_before_flip: Callable = None,
    on_after_flip: Callable = None,
) -> ScaraResult
```

Linear motion with automatic elbow reconfiguration when approaching joint limits.

**Algorithm:**
1. Plan segment 1 with current elbow config
2. At each waypoint, check elbow angle vs. limit margin (`joint_limit_margin`, default 0.15 rad)
3. When margin reached: mark flip point
4. Plan segment 2 with alternate elbow config
5. Execute:
   - Send segment 1 trajectory -> wait
   - Call `on_before_flip()` (e.g. raise Z to unhook tool)
   - Send flip motion (single point to seg2[0]) -> wait
   - Call `on_after_flip()` (e.g. lower Z to rehook)
   - Send segment 2 trajectory -> wait

**Use case:** Extracting a box from a deep shelf. The arm enters in ELBOW_DOWN, pulls the box, hits the elbow limit mid-retraction, flips to ELBOW_UP, and continues.

### move_home

```python
async def move_home(self, velocity: float = 0.5) -> ScaraResult
```

Move to configured home position. Z first (if configured), then SCARA joints.

Home position is defined in config:
```yaml
scara_client:
  home:
    shoulder: 0.0
    elbow: 0.0
    wrist: 0.0
    z: 0.0
```

---

## Tool Control (Async)

### trigger_tool

```python
async def trigger_tool(self, activate: bool = True) -> ScaraResult
```

Activate or deactivate the end-effector tool via configured service. Returns `ScaraResult(success=False)` if tool type is `"none"` or service is unavailable.

Waits `settle_time` (from config) after triggering.

### pick_at

```python
async def pick_at(self, x: float, y: float, z: float = None, velocity: float = 0.5) -> ScaraResult
```

High-level pick: `move_to_point()` then `trigger_tool(activate=True)`.

### place_at

```python
async def place_at(self, x: float, y: float, z: float = None, velocity: float = 0.5) -> ScaraResult
```

High-level place: `move_to_point()` then `trigger_tool(activate=False)`.

---

## Error Handling

Motion methods return `ScaraResult(success=False, message=...)` for recoverable errors. Exceptions are raised only for unrecoverable configuration issues.

| Error | Type | When |
|-------|------|------|
| Target outside joint limits | `ScaraResult(success=False)` | `move_joints()`, `move_to_point()` |
| Target unreachable (IK) | `ScaraResult(success=False)` | `move_to_point()` |
| Both IK solutions exceed limits | `ScaraResult(success=False)` | `move_to_point()` |
| Z target outside limits | `ScaraResult(success=False)` | `move_z()` |
| Trajectory rejected | `ScaraResult(success=False)` | Any motion method |
| Linear deviation exceeded | `ScaraResult(success=False)` | `move_linear()` |
| Elbow flip failed | `ScaraResult(success=False)` | `move_linear_with_flip()` |
| Tool not configured | `ScaraResult(success=False)` | `trigger_tool()` |
| SCARA controller unavailable | `ScaraNotReady` (exception) | Any motion method |
| Z-axis not configured | `ZAxisNotConfigured` (exception) | `move_z()`, `get_z_position()` |
| Z controller unavailable | `ZAxisNotReady` (exception) | `move_z()` |

---

## Implementation Patterns

### Thread Safety

Joint state updates use `threading.Lock`:

```python
def _joint_state_cb(self, msg):
    with self._lock:
        for i, name in enumerate(msg.name):
            if i < len(msg.position):
                self._joint_states[name] = msg.position[i]

def get_joint_positions(self):
    with self._lock:
        return (
            self._joint_states.get('scara_shoulder_joint', 0.0),
            ...
        )
```

This matches the existing pattern in `move_joint_group_server.py`.

### Async Action Client Pattern

Matches the pattern used in `get_container_server.py`:

```python
handle = await self._scara_client.send_goal_async(goal)
if not handle.accepted:
    return False, 'Goal rejected'
result = await handle.get_result_async()
```

### Trajectory Points

Single-point trajectories are used for `move_joints()`, `move_z()`, `move_to_point()`:

```python
point = JointTrajectoryPoint()
point.positions = [t1, t2, t3]    # All 3 SCARA joints required
point.time_from_start = Duration(sec=2, nanosec=0)
# No velocities set — for single-point trajectory, last point velocity must be zero
```

Multi-point trajectories are used for `move_linear()`:

```python
for i, waypoint in enumerate(waypoints):
    point = JointTrajectoryPoint()
    point.positions = waypoint
    point.time_from_start = make_duration(step_size / velocity * (i + 1))
    points.append(point)
```

### QoS for Joint States

BEST_EFFORT reliability, matching the joint state broadcaster:

```python
qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, depth=10)
```

### Config Auto-Discovery

Uses `ament_index_python` for installed packages, with source-tree fallback for development:

```python
try:
    pkg_share = get_package_share_directory('scara_description')
    p = Path(pkg_share) / 'config' / 'scara_params.yaml'
except Exception:
    p = Path(__file__).resolve().parents[3] / 'scara_description' / 'config' / 'scara_params.yaml'
```

---

## SCARA Arm Specification

| Parameter | Value |
|-----------|-------|
| L1 (shoulder -> elbow) | 0.4125 m |
| L2 (elbow -> wrist) | 0.2625 m |
| Min reach | 0.15 m |
| Max reach | 0.675 m |
| Shoulder limits | [-0.995, +0.995] rad (±57 deg) |
| Elbow limits | [-3.228, +3.228] rad (±185 deg) |
| Wrist limits | [-6.28, +6.28] rad (±360 deg) |
| Shoulder max velocity | 1.6 rad/s |
| Elbow max velocity | 1.5 rad/s |
| Wrist max velocity | 3.3 rad/s |

### Z-axis (This Project)

| Parameter | Value |
|-----------|-------|
| Joint | `selector_frame_picker_frame_joint` |
| Type | Prismatic Z |
| Limits | [-0.01, 0.3] m |
| Max velocity | 1.0 m/s |
| Controller | `picker_z_controller` |

---

## Velocity Reference

| Motion Method | `velocity` Parameter | Internal Meaning |
|---------------|---------------------|------------------|
| `move_joints()` | 0.0 - 1.0 | Scaling factor of max joint velocity |
| `move_z()` | 0.0 - 1.0 | Scaling factor of max Z velocity |
| `move_to_point()` | 0.0 - 1.0 | Same as `move_joints()` after IK |
| `move_linear()` | m/s (Cartesian) | `time_per_step = step_size / velocity` |
| `move_linear_with_flip()` | m/s (Cartesian) | Same as `move_linear()`, flip uses `flip_duration` |
| `move_home()` | 0.0 - 1.0 | Same as `move_joints()` |

---

## See Also

- **Package overview:** [package_structure.md](package_structure.md)
- **Architecture design:** [scara_client_architecture.md](scara_client_architecture.md)
- **SCARA controllers config:** `src/scara_description/config/scara_controllers.yaml`
- **SCARA parameters:** `src/scara_description/config/scara_params.yaml`
- **ros2_control integration:** `docs/scara_description/ros2_control.md`
