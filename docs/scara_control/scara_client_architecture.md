# ScaraClient Architecture

Architectural design document for the `ScaraClient` class — a self-contained, reusable control interface for the 3-DOF SCARA arm.

**Package:** `scara_control` (new `ament_python` package)
**Class:** `ScaraClient`
**Design principle:** Attach to any ROS2 node, works out of the box with `scara_controller`

---

## 1. Overview

`ScaraClient` is a composable Python class (not a Node) that provides a high-level API for SCARA arm manipulation. It communicates directly with the `scara_controller` (JointTrajectoryController) and `/joint_states` topic — no dependency on project-specific infrastructure like `move_joint_group_server`.

### Dependencies

| Dependency | Purpose |
|------------|---------|
| `scara_controller` (JointTrajectoryController) | Joint trajectory execution |
| `/joint_states` topic | Current joint position feedback |
| `scara_params.yaml` | Kinematic parameters (L1, L2), joint limits |

### What it does NOT depend on

- `move_joint_group_server`
- `ros_control` package
- `manipulator_description`
- Any project-specific action/service

---

## 2. SCARA Arm Specification

```
Joints:
  scara_shoulder_joint (theta1)  — revolute Z — [-57, +57] deg  — 1.6 rad/s
  scara_elbow_joint    (theta2)  — revolute Z — [-185, +185] deg — 1.5 rad/s
  scara_wrist_joint    (theta3)  — revolute Z — [-360, +360] deg — 3.3 rad/s

Kinematics:
  L1 = 0.4125 m  (shoulder -> elbow)
  L2 = 0.2625 m  (elbow -> wrist)
  TCP offset: [0, 0, -0.2] m from flange

Workspace:
  Min reach: L1 - L2 = 0.15 m
  Max reach: L1 + L2 = 0.675 m

Forward kinematics:
  x = L1*cos(theta1) + L2*cos(theta1 + theta2)
  y = L1*sin(theta1) + L2*sin(theta1 + theta2)
  phi = theta1 + theta2 + theta3  (TCP orientation)

Controller action:
  /scara_controller/follow_joint_trajectory (FollowJointTrajectory)
```

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
- Sends single-point `FollowJointTrajectory` goal
- Waits for result, returns `ScaraResult`

---

### 3.3 Inverse Kinematics (IK)

Move TCP to a target (x, y) position in SCARA base frame. The SCARA is a 2-DOF planar arm for positioning + 1 DOF for TCP orientation.

```python
async def move_to_point(
    self,
    x: float,              # target X in SCARA base frame [m]
    y: float,              # target Y in SCARA base frame [m]
    orientation: float = None,  # TCP orientation phi [rad], None = auto
    elbow_up: bool = True,     # IK solution selection (elbow-up or elbow-down)
    velocity: float = 1.0,     # velocity scaling factor [0.0 - 1.0]
) -> ScaraResult:
    """
    Move TCP to Cartesian point using inverse kinematics.
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
- Validates target is within workspace: `(L1-L2) <= sqrt(x^2+y^2) <= (L1+L2)`
- Computes IK, selects elbow-up or elbow-down solution
- Validates computed joint angles against limits
- If both solutions are outside joint limits — returns error
- If `orientation` is `None` — keeps current wrist angle (theta3 unchanged)
- Calls `move_joints()` with computed angles

---

### 3.4 Linear (Cartesian) Motion

Move TCP along a straight line in Cartesian space from current position to target. Unlike `move_to_point()` which plans in joint space (arc trajectory in Cartesian), this interpolates linearly in XY.

```python
async def move_linear(
    self,
    x: float,              # target X [m]
    y: float,              # target Y [m]
    orientation: float = None,  # TCP orientation [rad]
    velocity: float = 0.1,     # linear velocity [m/s]
    step_size: float = 0.005,  # interpolation step [m]
) -> ScaraResult:
    """
    Move TCP in a straight line in Cartesian space.
    Generates multi-point trajectory via IK at each interpolation step.
    """
```

**Behavior:**
1. Get current TCP position via FK from current joint angles
2. Compute straight-line path from current to target
3. Interpolate intermediate points along the line with `step_size` spacing
4. For each waypoint: compute IK (consistent elbow configuration)
5. If any waypoint is unreachable or outside joint limits — return error before moving
6. Build multi-point `FollowJointTrajectory` with timestamps based on `velocity`
7. Send trajectory, wait for result

**Why this matters:** Joint-space interpolation traces an arc. For tasks like following a shelf edge or precise placement, linear TCP motion is required.

---

### 3.5 Velocity Control

All motion methods accept velocity parameters. Internally, velocity is handled differently depending on the motion type:

| Motion type | Velocity parameter | Internal behavior |
|-------------|-------------------|-------------------|
| `move_joints()` | `velocity: float` (0.0-1.0 scaling) | Scales max velocity from config per joint. Time = max_distance / scaled_velocity |
| `move_to_point()` | `velocity: float` (0.0-1.0 scaling) | Same as `move_joints()` after IK |
| `move_linear()` | `velocity: float` (m/s, Cartesian) | Computes time per segment = step_size / velocity. Each waypoint gets cumulative `time_from_start` |

---

### 3.6 State & Kinematics Queries

Read-only methods for getting current arm state and computing kinematics without moving.

```python
def get_joint_positions(self) -> tuple[float, float, float]:
    """Return current (shoulder, elbow, wrist) joint angles [rad]."""

def get_tcp_position(self) -> tuple[float, float, float]:
    """
    Return current TCP (x, y, phi) in SCARA base frame via FK.
      x, y — position [m]
      phi  — orientation [rad]
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
    """Check if (x, y) is within SCARA workspace."""
```

---

### 3.7 Tool Trigger (Picker Logic)

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
    approach_height: float = 0.0,  # not applicable for planar SCARA, reserved
    velocity: float = 0.5,
) -> ScaraResult:
    """
    High-level pick sequence:
      1. Move to (x, y) via move_to_point()
      2. Activate tool (trigger_tool(True))
      3. Return success/failure
    """

async def place_at(
    self,
    x: float,
    y: float,
    velocity: float = 0.5,
) -> ScaraResult:
    """
    High-level place sequence:
      1. Move to (x, y) via move_to_point()
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
    tcp_position: tuple[float, float, float]      # final (x, y, phi)
    execution_time: float                          # seconds
```

---

## 5. Configuration

`ScaraClient` reads from `scara_params.yaml` (already exists) plus a new optional section:

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
  controller_action: "/scara_controller/follow_joint_trajectory"
  joint_states_topic: "/joint_states"
  position_tolerance: 0.01    # rad
  timeout: 30.0               # seconds

  # Tool configuration (optional)
  tool:
    type: "service"                        # "service" or "topic" or "none"
    activate: "/scara_tool/activate"
    deactivate: "/scara_tool/deactivate"
    service_type: "std_srvs/srv/Trigger"
    settle_time: 0.5

  # Default motion parameters
  defaults:
    velocity_scaling: 0.5       # default velocity factor
    linear_velocity: 0.1        # m/s for move_linear
    linear_step_size: 0.005     # m for move_linear interpolation
    elbow_up: true              # default IK solution
```

---

## 6. Communication Diagram

```
                                            ┌──────────────────────────┐
                                            │   scara_controller       │
                                            │  (JointTrajectoryCtrl)   │
                                            │                          │
                         FollowJoint        │  /scara_controller/      │
Any ROS2 Node            Trajectory.Goal    │  follow_joint_trajectory │
┌──────────────┐        ──────────────────► │                          │
│              │       │                    └──────────┬───────────────┘
│  ScaraClient ├───────┤                               │
│  (attached)  │       │                               │ commands
│              ├───┐   │    /joint_states               ▼
└──────────────┘   │   │   ◄────────────────   [Hardware Interface]
                   │   │
                   │   │    /scara_tool/activate
                   │   └── ─────────────────►  [Tool Service/Topic]
                   │
                   │   scara_params.yaml
                   └── (L1, L2, limits, tool config)
```

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

### Basic — move joints

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

### IK — move to point

```python
    async def reach_target(self):
        # Move TCP to (x=0.5, y=0.1), auto-select elbow config
        result = await self.scara.move_to_point(x=0.5, y=0.1)

        # With specific orientation and elbow-down
        result = await self.scara.move_to_point(
            x=0.4, y=-0.2, orientation=1.57, elbow_up=False
        )
```

### Linear motion

```python
    async def trace_line(self):
        # Slow linear move at 5 cm/s
        result = await self.scara.move_linear(
            x=0.6, y=0.0, velocity=0.05
        )
```

### Pick and place

```python
    async def pick_and_place(self):
        result = await self.scara.pick_at(x=0.5, y=0.1)
        if result.success:
            result = await self.scara.place_at(x=0.3, y=-0.1)
```

### Query state (no movement)

```python
    async def check_state(self):
        x, y, phi = self.scara.get_tcp_position()
        print(f"TCP at ({x:.3f}, {y:.3f}), orientation {phi:.3f}")

        if self.scara.is_reachable(0.6, 0.1):
            theta1, theta2, theta3 = self.scara.compute_ik(0.6, 0.1)
```

---

## 9. Error Handling

| Error | When | Behavior |
|-------|------|----------|
| `ScaraNotReady` | Controller not available on construction | Raise exception |
| `TargetUnreachable` | IK has no solution / point outside workspace | Return `ScaraResult(success=False)` |
| `JointLimitViolation` | Computed angles exceed config limits | Return `ScaraResult(success=False)` |
| `TrajectoryRejected` | Controller rejects trajectory goal | Return `ScaraResult(success=False)` |
| `ExecutionTimeout` | Motion exceeds configured timeout | Cancel goal, return `ScaraResult(success=False)` |
| `ToolNotConfigured` | `trigger_tool()` called with `tool.type: "none"` | Return `ScaraResult(success=False)` |

---

## 10. Open Questions

1. **Collision avoidance** — Should `ScaraClient` check for self-collision (elbow folding into base)? Or leave that to the caller?
2. **Namespace support** — Should joint names and topic names support prefixing for multi-SCARA setups? (e.g., `/scara_left/scara_controller/...`)
3. **Home position** — Should there be a `move_home()` method with a configurable home pose?
4. **Trajectory blending** — Should `move_linear()` support blending between segments for continuous motion, or is stop-at-each-waypoint sufficient?
5. **Tool types** — Current design covers service-based and topic-based tools. Are there other tool interfaces needed?
