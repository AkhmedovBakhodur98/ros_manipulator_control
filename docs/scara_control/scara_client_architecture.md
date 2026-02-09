# ScaraClient Architecture

Architectural design document for the `ScaraClient` class — a self-contained, reusable control interface for the SCARA arm with optional Z-axis support.

**Package:** `scara_control` (new `ament_python` package)
**Class:** `ScaraClient`
**Design principle:** Attach to any ROS2 node, works out of the box. Portable across projects.

---

## 1. Overview

`ScaraClient` is a composable Python class (not a Node) that provides a high-level API for SCARA arm manipulation. It communicates directly with joint trajectory controllers and the `/joint_states` topic — no dependency on project-specific infrastructure like `move_joint_group_server`.

The SCARA arm is a **planar 3-DOF arm** (XY positioning + TCP orientation). Since it mounts on a parent frame, Z-axis movement depends on the parent robot's joint. The `ScaraClient` supports an **optional configurable Z-axis joint** via a separate controller, enabling full 3D (XYZ + orientation) control when configured.

### Controller Architecture

```
ScaraClient communicates with TWO independent controllers:

1. scara_controller (always required)
   └── 3 SCARA joints: shoulder, elbow, wrist
   └── Action: /scara_controller/follow_joint_trajectory

2. Z-axis controller (optional, configurable)
   └── 1 parent joint: e.g. selector_frame_picker_frame_joint
   └── Action: e.g. /picker_z_controller/follow_joint_trajectory
   └── Configured via YAML — any project can specify its own Z joint/controller
```

### Dependencies

| Dependency | Required | Purpose |
|------------|----------|---------|
| `scara_controller` (JointTrajectoryController) | Yes | SCARA joint trajectory execution (XY + orientation) |
| Z-axis controller (JointTrajectoryController) | No | Z-axis movement via parent joint |
| `/joint_states` topic | Yes | Current joint position feedback |
| `scara_params.yaml` | Yes | Kinematic parameters (L1, L2), joint limits, client config |

### What it does NOT depend on

- `move_joint_group_server`
- `ros_control` package
- `manipulator_description`
- Any project-specific action/service

---

## 2. SCARA Arm Specification

### Own joints (3-DOF planar)

```
Joints:
  scara_shoulder_joint (theta1)  — revolute Z — [-57, +57] deg  — 1.6 rad/s
  scara_elbow_joint    (theta2)  — revolute Z — [-185, +185] deg — 1.5 rad/s
  scara_wrist_joint    (theta3)  — revolute Z — [-360, +360] deg — 3.3 rad/s

Kinematics:
  L1 = 0.4125 m  (shoulder -> elbow)
  L2 = 0.2625 m  (elbow -> wrist)
  TCP offset: [0, 0, -0.2] m from flange

Workspace (planar):
  Min reach: L1 - L2 = 0.15 m
  Max reach: L1 + L2 = 0.675 m

Forward kinematics:
  x = L1*cos(theta1) + L2*cos(theta1 + theta2)
  y = L1*sin(theta1) + L2*sin(theta1 + theta2)
  phi = theta1 + theta2 + theta3  (TCP orientation)
```

### Z-axis joint (from parent robot, optional)

```
In this project (manipulator):
  selector_frame_picker_frame_joint — prismatic Z — [-0.01, 0.3] m — 1.0 m/s
  Controller: picker_z_controller
  Action: /picker_z_controller/follow_joint_trajectory

In other projects:
  Any prismatic Z joint can be configured via scara_client config.
  The ScaraClient does not assume a specific joint name or controller.
```

### Effective DOF

| Configuration | DOF | Workspace |
|---------------|-----|-----------|
| SCARA only (no Z configured) | 3 | Planar: XY + orientation |
| SCARA + Z joint | 4 | 3D: XYZ + orientation |

---

## 3. Class API Design

### 3.1 Construction

```python
class ScaraClient:
    def __init__(self, node: Node, config_path: str = None):
        """
        Attach SCARA control to an existing ROS2 node.

        Args:
            node: Any ROS2 node instance
            config_path: Path to scara_params.yaml (auto-discovered if None)
        """
```

On construction:
- Loads kinematic parameters (L1, L2) and joint limits from `scara_params.yaml`
- Creates `ActionClient` for `/scara_controller/follow_joint_trajectory`
- If Z-axis configured in config: creates second `ActionClient` for Z controller
- Subscribes to `/joint_states` for current position feedback
- Validates controller availability

---

### 3.2 Joint Space Control

Direct joint angle control — move one or more SCARA joints to specified angles.

```python
async def move_joints(
    self,
    shoulder: float = None,  # theta1 [rad], None = keep current
    elbow: float = None,     # theta2 [rad], None = keep current
    wrist: float = None,     # theta3 [rad], None = keep current
    velocity: float = 1.0,   # velocity scaling factor [0.0 - 1.0]
) -> ScaraResult:
    """
    Move SCARA joints to target angles.
    Joints set to None stay at current position.
    Velocity is a scaling factor of max joint velocity.
    """
```

**Behavior:**
- Reads current joint positions from `/joint_states`
- Fills `None` values with current positions (joint stays in place)
- Validates target positions against joint limits from config
- Calculates trajectory time from velocity scaling and max distance
- Sends single-point `FollowJointTrajectory` goal to `scara_controller`
- Waits for result, returns `ScaraResult`

---

### 3.3 Z-Axis Control

Move the SCARA arm up/down via the parent Z-axis joint. Only available when Z-axis is configured.

```python
async def move_z(
    self,
    z: float,              # target Z position [m]
    velocity: float = 1.0, # velocity scaling factor [0.0 - 1.0]
) -> ScaraResult:
    """
    Move SCARA base along Z axis via parent joint.
    Raises ZAxisNotConfigured if no Z-axis joint is set up.
    """
```

**Behavior:**
- Validates Z-axis is configured (raises error if not)
- Reads current Z joint position from `/joint_states`
- Validates target against Z joint limits from config
- Sends single-point `FollowJointTrajectory` goal to Z controller
- Waits for result, returns `ScaraResult`

---

### 3.4 Inverse Kinematics (IK)

Move TCP to a target position in SCARA base frame. Supports 2D (x, y) and 3D (x, y, z) when Z-axis is configured.

```python
async def move_to_point(
    self,
    x: float,                     # target X in SCARA base frame [m]
    y: float,                     # target Y in SCARA base frame [m]
    z: float = None,              # target Z [m], None = keep current (requires Z-axis)
    orientation: float = None,    # TCP orientation phi [rad], None = auto
    elbow_up: bool = True,        # IK solution selection (elbow-up or elbow-down)
    velocity: float = 1.0,        # velocity scaling factor [0.0 - 1.0]
) -> ScaraResult:
    """
    Move TCP to Cartesian point using inverse kinematics.
    If z is specified and Z-axis is configured, moves Z first, then XY.
    """
```

**IK Equations (2R planar arm):**
```
Given target (x, y):

  cos(theta2) = (x^2 + y^2 - L1^2 - L2^2) / (2 * L1 * L2)

  theta2 = atan2(+/-sqrt(1 - cos^2(theta2)), cos(theta2))
           ^^ elbow_up = +sqrt, elbow_down = -sqrt

  theta1 = atan2(y, x) - atan2(L2*sin(theta2), L1 + L2*cos(theta2))

  theta3 = orientation - theta1 - theta2  (if orientation specified)
```

**Behavior:**
- Validates target is within planar workspace: `(L1-L2) <= sqrt(x^2+y^2) <= (L1+L2)`
- Computes IK, selects elbow-up or elbow-down solution
- Validates computed joint angles against limits
- If both solutions are outside joint limits — returns error
- If `orientation` is `None` — keeps current wrist angle (theta3 unchanged)
- If `z` is specified: calls `move_z(z)` first, then `move_joints()` for XY
- If `z` is `None`: calls `move_joints()` only

**Motion order for 3D moves (z specified):**
1. Move Z to target height (via Z controller)
2. Move XY + orientation (via SCARA controller)

This sequential approach avoids collisions — the arm reaches the correct height before sweeping horizontally.

---

### 3.5 Linear (Cartesian) Motion

Move TCP along a straight line in Cartesian space from current position to target. Unlike `move_to_point()` which plans in joint space (arc trajectory in Cartesian), this interpolates linearly in XY.

```python
async def move_linear(
    self,
    x: float,              # target X [m]
    y: float,              # target Y [m]
    z: float = None,       # target Z [m], None = keep current (requires Z-axis)
    orientation: float = None,  # TCP orientation [rad]
    velocity: float = 0.1,     # linear velocity [m/s]
    step_size: float = 0.005,  # interpolation step [m]
    allow_elbow_flip: bool = False,  # allow mid-path elbow reconfiguration
) -> ScaraResult:
    """
    Move TCP in a straight line in Cartesian space.
    Generates multi-point trajectory via IK at each interpolation step.
    If z is specified, moves Z first, then linear XY.
    """
```

**Behavior:**
1. If `z` specified: move Z to target height first (via Z controller)
2. Get current TCP position via FK from current joint angles
3. Compute straight-line path from current to target in XY
4. Interpolate intermediate points along the line with `step_size` spacing
5. For each waypoint: compute IK (consistent elbow configuration)
6. **Verify linearity**: for each waypoint, compute FK from IK result and check deviation from intended straight line. If max deviation > `max_deviation` (default 5mm) — return error
7. If a waypoint hits joint limits and `allow_elbow_flip=True` — detect flip point and split trajectory (see 3.6)
8. If any waypoint is unreachable or outside joint limits (and no flip allowed) — return error before moving
9. Build multi-point `FollowJointTrajectory` with timestamps based on `velocity`
10. Send trajectory to `scara_controller`, wait for result

**Why this matters:** Joint-space interpolation traces an arc. For tasks like following a shelf edge or precise placement, linear TCP motion is required.

**Linear path verification:** After computing IK for all waypoints, the planner runs FK on each result and measures XY deviation from the ideal straight line. This catches numerical issues and ensures the arm actually follows the intended path. Configurable via `max_deviation` (default 5mm).

---

### 3.6 Elbow Flip During Linear Motion

During long linear paths (e.g. deep cabinet extraction), the elbow joint may approach its limit. Rather than failing, the arm can **automatically switch elbow configuration** (up ↔ down) mid-trajectory.

```python
async def move_linear_with_flip(
    self,
    x: float,
    y: float,
    z: float = None,
    orientation: float = None,
    velocity: float = 0.1,
    step_size: float = 0.005,
    on_before_flip: Callable = None,  # callback before flip (e.g. unhook tool)
    on_after_flip: Callable = None,   # callback after flip (e.g. rehook tool)
) -> ScaraResult:
    """
    Linear motion with automatic elbow reconfiguration when joint limits approached.
    Executes callbacks before/after the flip for tool management.
    """
```

**How elbow flip works:**

```
Phase 1: Linear path with ELBOW_DOWN     Phase 2: Linear path with ELBOW_UP

  ──●────●────●────●──►FLIP              FLIP►──●────●────●────●──
    elbow approaching limit               elbow now has room
```

**Algorithm:**
1. Plan linear path with current elbow config
2. At each waypoint, check if elbow joint is within `joint_limit_margin` (default 0.15 rad) of its limit
3. When margin reached — mark as **flip point**
4. Split trajectory into two segments:
   - Segment 1: start → flip point (original elbow config)
   - Segment 2: flip point → end (alternate elbow config)
5. Verify IK is valid for segment 2 with alternate config
6. Execute:
   1. Send segment 1 trajectory → wait
   2. Call `on_before_flip()` callback (e.g. raise Z to unhook tool)
   3. Execute elbow flip motion (move joints to new config at flip point)
   4. Call `on_after_flip()` callback (e.g. lower Z to rehook tool)
   5. Send segment 2 trajectory → wait

**Configuration:**
```yaml
scara_client:
  elbow_flip:
    enabled: true
    joint_limit_margin: 0.15    # rad — trigger flip this far from limit
    flip_duration: 1.5          # seconds for the flip motion itself
    z_unhook_offset: 0.03       # m — Z raise before flip (if Z-axis available)
```

**Use case:** Extracting a box from a deep shelf. The arm enters in ELBOW_DOWN, pulls the box, hits the elbow limit mid-retraction, flips to ELBOW_UP, and continues pulling. The callbacks allow unhooking/rehooking the box during the flip.

---

### 3.6 Velocity Control

All motion methods accept velocity parameters. Internally, velocity is handled differently depending on the motion type:

| Motion type | Velocity parameter | Internal behavior |
|-------------|-------------------|-------------------|
| `move_joints()` | `velocity: float` (0.0-1.0 scaling) | Scales max velocity from config per joint. Time = max_distance / scaled_velocity |
| `move_z()` | `velocity: float` (0.0-1.0 scaling) | Scales max velocity of Z joint. Time = distance / scaled_velocity |
| `move_to_point()` | `velocity: float` (0.0-1.0 scaling) | Same as `move_joints()` after IK. Z uses same scaling. |
| `move_linear()` | `velocity: float` (m/s, Cartesian) | Computes time per segment = step_size / velocity. Each waypoint gets cumulative `time_from_start` |
| `move_linear_with_flip()` | `velocity: float` (m/s, Cartesian) | Same as `move_linear()`. Flip motion uses `elbow_flip.flip_duration` from config |
| `move_home()` | `velocity: float` (0.0-1.0 scaling) | Same as `move_joints()` |

---

### 3.7 State & Kinematics Queries

Read-only methods for getting current arm state and computing kinematics without moving.

```python
def get_joint_positions(self) -> tuple[float, float, float]:
    """Return current (shoulder, elbow, wrist) joint angles [rad]."""

def get_z_position(self) -> float:
    """
    Return current Z position [m].
    Raises ZAxisNotConfigured if no Z-axis joint is set up.
    """

def get_tcp_position(self) -> tuple[float, float, float]:
    """
    Return current TCP (x, y, phi) in SCARA base frame via FK.
      x, y — position [m]
      phi  — orientation [rad]
    """

def get_tcp_position_3d(self) -> tuple[float, float, float, float]:
    """
    Return current TCP (x, y, z, phi).
    Raises ZAxisNotConfigured if no Z-axis joint is set up.
    """

def compute_fk(self, shoulder: float, elbow: float, wrist: float) -> tuple[float, float, float]:
    """
    Forward kinematics: joint angles -> (x, y, phi).
    Pure computation, no movement.
    """

def compute_ik(self, x: float, y: float, orientation: float = 0.0, elbow_up: bool = True) -> tuple[float, float, float]:
    """
    Inverse kinematics: (x, y, phi) -> joint angles.
    Pure computation, no movement. Raises ValueError if unreachable.
    """

def is_reachable(self, x: float, y: float) -> bool:
    """Check if (x, y) is within SCARA planar workspace."""

def has_z_axis(self) -> bool:
    """Check if Z-axis joint is configured and available."""

def get_elbow_config(self) -> ElbowConfig:
    """
    Return current elbow configuration based on elbow joint angle.
      ELBOW_UP   if theta2 > 0
      ELBOW_DOWN if theta2 < 0
    """

def diagnose_ik_failure(self, x: float, y: float, orientation: float = 0.0) -> IKDiagnostic:
    """
    Analyze why IK fails for a target and suggest corrections.
    Returns diagnostic with:
      - reason: 'too_far' | 'too_close' | 'joint_limit' | 'reachable'
      - suggested_x_offset: float — how much to shift base X to make target reachable
      - suggested_z_offset: float — how much to shift base Z
      - distance: float — distance from base to target
      - workspace_min/max: float — workspace bounds
    """
```

**IK diagnostics** help the caller decide what to do when a target is unreachable. Instead of just returning "failed", the client explains **why** it failed and **what adjustment** would fix it. For example, if the target is 0.7m away (max reach is 0.675m), it reports `too_far` and suggests moving the base 0.025m closer.

**Mirrored elbow selection:** When working on symmetric structures (e.g. left/right shelves), opposite sides benefit from opposite elbow configs for natural-looking motion:
- Right side targets (y < 0): `ELBOW_DOWN` — shoulder rotates positive
- Left side targets (y > 0): `ELBOW_UP` — shoulder rotates negative

The `move_to_point()` method's `elbow_up` parameter handles this. The caller can use `get_elbow_config()` to detect the current config and plan accordingly.

---

### 3.8 Home Position

Return the SCARA arm to a configurable home pose.

```python
async def move_home(self, velocity: float = 0.5) -> ScaraResult:
    """
    Move all SCARA joints (and Z if configured) to home position.
    Home position is defined in config.
    """
```

**Behavior:**
1. If Z-axis configured: move Z to `home.z` first
2. Move SCARA joints to `home.shoulder`, `home.elbow`, `home.wrist`

**Configuration:**
```yaml
scara_client:
  home:
    shoulder: 0.0
    elbow: 0.0
    wrist: 0.0
    z: 0.0           # only used if Z-axis configured
```

---

### 3.9 Tool Trigger (Picker Logic)

The SCARA arm may have an end-effector tool (gripper, suction, etc.) at the TCP. The client provides a generic tool interface that can be configured to work with whatever tool is mounted.

```python
async def trigger_tool(self, activate: bool = True) -> ScaraResult:
    """
    Activate or deactivate the end-effector tool.

    The tool interface is configured via config:
      tool:
        type: "service"          # "service" or "topic"
        activate: "/scara_tool/activate"    # service/topic name
        deactivate: "/scara_tool/deactivate"
        service_type: "std_srvs/srv/Trigger"
        settle_time: 0.5         # seconds to wait after trigger
    """

async def pick_at(
    self,
    x: float,
    y: float,
    z: float = None,           # Z height (requires Z-axis)
    velocity: float = 0.5,
) -> ScaraResult:
    """
    High-level pick sequence:
      1. Move to (x, y, z) via move_to_point()
      2. Activate tool (trigger_tool(True))
      3. Return success/failure
    """

async def place_at(
    self,
    x: float,
    y: float,
    z: float = None,           # Z height (requires Z-axis)
    velocity: float = 0.5,
) -> ScaraResult:
    """
    High-level place sequence:
      1. Move to (x, y, z) via move_to_point()
      2. Deactivate tool (trigger_tool(False))
      3. Return success/failure
    """
```

**Design rationale:** The tool mechanism is decoupled from the arm — configured via YAML, not hardcoded. This allows the same `ScaraClient` to work with a pneumatic gripper, electromagnetic picker, suction cup, etc.

---

## 4. Data Types

```python
@dataclass
class ScaraResult:
    success: bool
    message: str
    joint_positions: tuple[float, float, float]  # final (shoulder, elbow, wrist)
    z_position: float                             # final Z position [m] (0.0 if no Z-axis)
    tcp_position: tuple[float, float, float]      # final (x, y, phi) in SCARA base frame
    execution_time: float                          # seconds

class ElbowConfig(Enum):
    ELBOW_UP = "elbow_up"       # theta2 > 0
    ELBOW_DOWN = "elbow_down"   # theta2 < 0

@dataclass
class CartesianPose:
    x: float       # [m]
    y: float       # [m]
    phi: float     # TCP orientation [rad]

@dataclass
class IKSolution:
    shoulder: float    # theta1 [rad]
    elbow: float       # theta2 [rad]
    wrist: float       # theta3 [rad]
    valid: bool        # within joint limits
    elbow_config: ElbowConfig

@dataclass
class IKDiagnostic:
    reason: str             # 'too_far' | 'too_close' | 'joint_limit' | 'reachable'
    suggested_x_offset: float   # base X adjustment [m] to reach target
    suggested_z_offset: float   # base Z adjustment [m] (if applicable)
    distance: float             # distance from base to target [m]
    workspace_min: float        # min reach [m]
    workspace_max: float        # max reach [m]
```

---

## 5. Configuration

`ScaraClient` reads from `scara_params.yaml` (already exists) plus a new `scara_client` section:

```yaml
# Existing sections (already in scara_params.yaml):
kinematics:
  L1: 0.4125
  L2: 0.2625

joints:
  scara_shoulder_joint:
    limits: { lower: -0.995, upper: 0.995, velocity: 1.6 }
  scara_elbow_joint:
    limits: { lower: -3.228, upper: 3.228, velocity: 1.5 }
  scara_wrist_joint:
    limits: { lower: -6.28, upper: 6.28, velocity: 3.3 }

# New section for ScaraClient:
scara_client:
  # SCARA controller (always required)
  controller_action: "/scara_controller/follow_joint_trajectory"
  joint_states_topic: "/joint_states"
  position_tolerance: 0.01    # rad
  timeout: 30.0               # seconds

  # Z-axis configuration (optional)
  # When omitted or z_axis.enabled is false, ScaraClient works in 2D (XY only)
  z_axis:
    enabled: true
    joint_name: "selector_frame_picker_frame_joint"
    controller_action: "/picker_z_controller/follow_joint_trajectory"
    limits: { lower: -0.01, upper: 0.3, velocity: 1.0 }

  # Tool configuration (optional)
  tool:
    type: "service"                        # "service" or "topic" or "none"
    activate: "/scara_tool/activate"
    deactivate: "/scara_tool/deactivate"
    service_type: "std_srvs/srv/Trigger"
    settle_time: 0.5

  # Home position
  home:
    shoulder: 0.0
    elbow: 0.0
    wrist: 0.0
    z: 0.0                        # only used if Z-axis configured

  # Elbow flip configuration (for move_linear_with_flip)
  elbow_flip:
    enabled: true
    joint_limit_margin: 0.15      # rad — trigger flip this far from elbow limit
    flip_duration: 1.5            # seconds for the flip motion
    z_unhook_offset: 0.03         # m — Z raise before flip (if Z-axis and callbacks)

  # Linear motion parameters
  linear_motion:
    max_deviation: 0.005          # m (5mm) — max FK deviation from straight line
    waypoint_count: 15            # default number of waypoints for move_linear

  # Default motion parameters
  defaults:
    velocity_scaling: 0.5         # default velocity factor
    linear_velocity: 0.1          # m/s for move_linear
    linear_step_size: 0.005       # m for move_linear interpolation
    elbow_up: true                # default IK solution
```

### Portability example — different project

In another project where SCARA is mounted on a different Z mechanism:

```yaml
scara_client:
  controller_action: "/scara_controller/follow_joint_trajectory"
  z_axis:
    enabled: true
    joint_name: "my_lift_joint"
    controller_action: "/lift_controller/follow_joint_trajectory"
    limits: { lower: 0.0, upper: 1.0, velocity: 0.5 }
```

Or without Z-axis at all (pure planar):

```yaml
scara_client:
  controller_action: "/scara_controller/follow_joint_trajectory"
  z_axis:
    enabled: false
```

---

## 6. Communication Diagram

```
                                          ┌────────────────────────────┐
                                          │   scara_controller         │
                                          │  (JointTrajectoryCtrl)     │
                         FollowJoint      │                            │
                         Trajectory.Goal  │  /scara_controller/        │
Any ROS2 Node           ────────────────► │  follow_joint_trajectory   │
┌──────────────┐       │                  └─────────┬──────────────────┘
│              │       │                            │
│  ScaraClient ├───────┤                            │ XY commands
│  (attached)  │       │                            ▼
│              │       │                    [Hardware Interface]
│              │       │
│              │       │  ┌────────────────────────────┐
│              │       │  │   picker_z_controller       │
│              │       │  │  (JointTrajectoryCtrl)      │
│              ├───────┤  │                             │
│              │       │  │  /picker_z_controller/      │
│              │       └► │  follow_joint_trajectory    │
│              │          └─────────┬───────────────────┘
│              │                    │
│              │                    │ Z commands
│              │                    ▼
│              │            [Hardware Interface]
│              │
│              ├───┐   /joint_states
└──────────────┘   │   ◄──────────────  [Joint State Broadcaster]
                   │
                   ├── /scara_tool/activate
                   │   ─────────────────►  [Tool Service/Topic]
                   │
                   │   scara_params.yaml
                   └── (L1, L2, limits, z_axis, tool config)
```

### Two-controller coordination

The `ScaraClient` sends goals to **two independent controllers**. They never conflict because:
- `scara_controller` only claims SCARA joints (shoulder, elbow, wrist)
- Z controller only claims its one joint (e.g. `selector_frame_picker_frame_joint`)
- Different joints, different command interfaces, no ros2_control claim conflict

For methods that involve both Z and XY (`move_to_point(z=...)`, `move_linear(z=...)`):
- **Z moves first** (via Z controller), then **XY moves** (via SCARA controller)
- Sequential execution prevents collisions during height changes

---

## 7. Package Structure

```
src/scara_control/
├── package.xml                    # ament_python, depends on scara_description
├── setup.py
├── setup.cfg
├── resource/
│   └── scara_control              # ament resource marker
└── scara_control/
    ├── __init__.py
    └── scara_client.py            # ScaraClient class
```

**package.xml dependencies:**
- `rclpy`
- `control_msgs` (FollowJointTrajectory)
- `trajectory_msgs`
- `sensor_msgs` (JointState)
- `std_srvs` (Trigger for tool)
- `scara_description` (for config auto-discovery)

---

## 8. Usage Examples

### Basic — move joints (XY only)

```python
from scara_control.scara_client import ScaraClient

class MyNode(Node):
    def __init__(self):
        super().__init__('my_node')
        self.scara = ScaraClient(self)

    async def demo(self):
        # Move shoulder and elbow, keep wrist
        result = await self.scara.move_joints(shoulder=0.5, elbow=-1.0)

        # Move all joints, slow
        result = await self.scara.move_joints(
            shoulder=0.0, elbow=0.0, wrist=0.0, velocity=0.3
        )
```

### Z-axis control

```python
    async def adjust_height(self):
        # Move SCARA base to Z=0.15m
        result = await self.scara.move_z(z=0.15)

        # Check current height
        z = self.scara.get_z_position()
```

### IK — move to point (2D and 3D)

```python
    async def reach_target(self):
        # 2D: move TCP to (x=0.5, y=0.1), auto-select elbow config
        result = await self.scara.move_to_point(x=0.5, y=0.1)

        # 3D: move to height first, then XY
        result = await self.scara.move_to_point(
            x=0.4, y=-0.2, z=0.2, orientation=1.57, elbow_up=False
        )
```

### Linear motion

```python
    async def trace_line(self):
        # Slow linear move at 5 cm/s
        result = await self.scara.move_linear(
            x=0.6, y=0.0, velocity=0.05
        )

        # Linear move with Z adjustment first
        result = await self.scara.move_linear(
            x=0.5, y=0.1, z=0.1, velocity=0.05
        )
```

### Pick and place (3D)

```python
    async def pick_and_place(self):
        result = await self.scara.pick_at(x=0.5, y=0.1, z=0.05)
        if result.success:
            result = await self.scara.place_at(x=0.3, y=-0.1, z=0.2)
```

### Linear motion with elbow flip (deep extraction)

```python
    async def extract_from_shelf(self):
        # Define callbacks for tool management during flip
        async def unhook():
            await self.scara.move_z(self.scara.get_z_position() + 0.03)

        async def rehook():
            await self.scara.move_z(self.scara.get_z_position() - 0.03)

        # Deep retraction with automatic elbow reconfiguration
        result = await self.scara.move_linear_with_flip(
            x=0.4, y=0.0,           # retract to y=0
            velocity=0.05,
            on_before_flip=unhook,   # raise Z before flip
            on_after_flip=rehook,    # lower Z after flip
        )
```

### Home position

```python
    async def reset(self):
        await self.scara.move_home(velocity=0.3)
```

### IK diagnostics

```python
    async def smart_reach(self, x, y):
        if not self.scara.is_reachable(x, y):
            diag = self.scara.diagnose_ik_failure(x, y)
            if diag.reason == 'too_far':
                # Target is beyond reach — need to move base closer
                print(f"Need to shift base by X={diag.suggested_x_offset:.3f}m")
            elif diag.reason == 'too_close':
                # Target is inside min reach — need to move base away
                print(f"Too close, shift base by X={diag.suggested_x_offset:.3f}m")
            return
        await self.scara.move_to_point(x=x, y=y)
```

### Mirrored elbow selection

```python
    async def pick_from_side(self, x, y):
        # Select elbow config based on target side for symmetric motion
        elbow_up = y > 0  # left side: elbow up, right side: elbow down
        await self.scara.move_to_point(x=x, y=y, elbow_up=elbow_up)
```

### Query state (no movement)

```python
    async def check_state(self):
        x, y, phi = self.scara.get_tcp_position()
        print(f"TCP at ({x:.3f}, {y:.3f}), orientation {phi:.3f}")

        if self.scara.has_z_axis():
            x, y, z, phi = self.scara.get_tcp_position_3d()
            print(f"TCP at ({x:.3f}, {y:.3f}, {z:.3f}), orientation {phi:.3f}")

        if self.scara.is_reachable(0.6, 0.1):
            theta1, theta2, theta3 = self.scara.compute_ik(0.6, 0.1)

        # Check current elbow config
        config = self.scara.get_elbow_config()
        print(f"Elbow: {config}")  # ELBOW_UP or ELBOW_DOWN
```

---

## 9. Error Handling

| Error | When | Behavior |
|-------|------|----------|
| `ScaraNotReady` | SCARA controller not available on construction | Raise exception |
| `ZAxisNotConfigured` | Z method called but `z_axis.enabled: false` | Raise exception |
| `ZAxisNotReady` | Z controller not available on construction (when configured) | Raise exception |
| `TargetUnreachable` | IK has no solution / point outside workspace | Return `ScaraResult(success=False)` |
| `JointLimitViolation` | Computed angles or Z position exceed config limits | Return `ScaraResult(success=False)` |
| `TrajectoryRejected` | Controller rejects trajectory goal | Return `ScaraResult(success=False)` |
| `ExecutionTimeout` | Motion exceeds configured timeout | Cancel goal, return `ScaraResult(success=False)` |
| `LinearDeviationExceeded` | FK verification shows path deviation > `max_deviation` | Return `ScaraResult(success=False)` before moving |
| `ElbowFlipFailed` | Cannot find valid alternate elbow config at flip point | Return `ScaraResult(success=False)` |
| `ToolNotConfigured` | `trigger_tool()` called with `tool.type: "none"` | Return `ScaraResult(success=False)` |

---

## 10. Open Questions

1. **Collision avoidance** — Should `ScaraClient` check for self-collision (elbow folding into base)? Or leave that to the caller?
2. **Namespace support** — Should joint names and topic names support prefixing for multi-SCARA setups? (e.g., `/scara_left/scara_controller/...`)
3. **Trajectory blending** — Should `move_linear()` support blending between segments for continuous motion, or is stop-at-each-waypoint sufficient?
4. **Tool types** — Current design covers service-based and topic-based tools. Are there other tool interfaces needed?
5. **Simultaneous Z+XY** — Currently Z moves first, then XY (safe). Should there be an option to move Z and XY simultaneously for speed?
