# SCARA Arm Configuration Guide

This document explains all configurable parameters in `scara_params.yaml` and how they affect the robot behavior.

---

## Configuration File Location

```
scara_description/
└── config/
    └── scara_params.yaml    ← Main configuration file
```

---

## Configuration Sections

The YAML file is organized into four main sections:

```yaml
mount:        # Mounting position/orientation
kinematics:   # Arm geometry
links:        # Link properties (mesh, mass, inertia)
joints:       # Joint properties (limits, dynamics)
```

---

## 1. Mount Configuration

Controls where the SCARA attaches to its parent link.

```yaml
mount:
  offset:
    xyz: [0.15, 0, 0.15]    # Position offset [x, y, z] in meters
                            # X: 15cm forward, Y: 0, Z: 15cm up
    rpy: [0, 0, 0]          # Rotation offset [roll, pitch, yaw] in radians
```

### Position Offset (xyz)

The `xyz` offset is relative to the parent link's frame:

```
Parent Link Frame:

      Z (up)
      │
      │   xyz = [0, 0, 0.15]
      │        ↓
      ├───────[SCARA Base]
      │
      │
  Y───┼───X (forward)
      │
```

**Examples:**

| xyz Value | Effect | Use Case |
|-----------|--------|----------|
| `[0, 0, 0]` | SCARA at parent origin | Direct mount |
| `[0, 0, 0.15]` | 150mm above parent | Vertical clearance |
| `[0.15, 0, 0.15]` | 150mm forward + 150mm up | Default - forward offset |
| `[0.1, 0, 0]` | 100mm forward | Forward offset only |
| `[0, 0.2, 0.1]` | Sideways + up | Asymmetric mount |

### Rotation Offset (rpy)

The `rpy` (roll-pitch-yaw) rotation is applied in order: roll → pitch → yaw

| rpy Value | Effect | Use Case |
|-----------|--------|----------|
| `[0, 0, 0]` | No rotation | Default |
| `[0, 0, 1.5708]` | 90° yaw | Face sideways |
| `[0, 0, 3.1416]` | 180° yaw | Face backward |
| `[3.1416, 0, 0]` | 180° roll | Upside down |
| `[0, 1.5708, 0]` | 90° pitch | Tilted forward |

---

## 2. Kinematics Configuration

Defines the arm geometry (link lengths).

```yaml
kinematics:
  L1: 0.4125              # Shoulder to elbow length [meters]
  L2: 0.2625              # Elbow to wrist length [meters]
```

### Workspace Calculation

```
Minimum reach: |L1 - L2| = 0.15m   (arm folded)
Maximum reach:  L1 + L2  = 0.675m  (arm extended)
```

### Visual Representation

```
        ←── L1 = 0.4125m ──→←─ L2 = 0.2625m ─→

    Base        Shoulder          Elbow         Wrist/TCP
      ●────────────●────────────────●──────────────●
      │            │                │              │
    fixed     revolute Z       revolute Z     revolute Z
              (θ1: ±57°)       (θ2: ±185°)    (θ3: ±360°)
```

**Warning:** Changing L1/L2 requires matching mesh files. The default meshes are designed for the default values.

---

## 3. Links Configuration

Defines visual, collision, and inertial properties for each link.

### Link Structure

```yaml
links:
  link_name:
    mesh: "filename.STL"              # Mesh file (in meshes/scara/)
    color: [R, G, B, A]               # RGBA color [0-1]
    inertial:
      mass: 1.0                       # Mass in kg
      origin:
        xyz: [x, y, z]                # Center of mass position
        rpy: [r, p, y]                # Center of mass orientation
      inertia:
        ixx: 0.01                     # Inertia tensor components
        ixy: 0.0
        ixz: 0.0
        iyy: 0.01
        iyz: 0.0
        izz: 0.01
```

### Link List

| Link | Description | Default Mass |
|------|-------------|--------------|
| `scara_base_link` | Mounting bracket | 1.4882 kg |
| `scara_shoulder_link` | First arm segment | 4.227 kg |
| `scara_forearm_link` | Second arm segment | 2.5868 kg |
| `scara_flange_link` | Wrist flange | 0.004 kg |
| `tool_body_link` | Tool body | 0.425 kg |
| `tcp_link` | Tool center point (marker) | 0.01 kg |

### TCP Link Special Properties

The `tcp_link` has additional properties:

```yaml
tcp_link:
  color: [1.0, 0.5, 0.0, 1.0]   # Orange marker
  radius: 0.015                  # Sphere radius for visualization
```

### Color Reference

Common RGBA values:

| Color | RGBA |
|-------|------|
| Grey | `[0.5, 0.5, 0.5, 1.0]` |
| Orange | `[1.0, 0.5, 0.0, 1.0]` |
| Red | `[1.0, 0.0, 0.0, 1.0]` |
| Green | `[0.0, 1.0, 0.0, 1.0]` |
| Blue | `[0.0, 0.0, 1.0, 1.0]` |
| White | `[1.0, 1.0, 1.0, 1.0]` |

---

## 4. Joints Configuration

Defines joint types, limits, and dynamics.

### Joint Structure

```yaml
joints:
  joint_name:
    type: "revolute"              # Joint type
    origin:
      xyz: [0, 0, 0]              # Position relative to parent
      rpy: [0, 0, 0]              # Orientation relative to parent
    axis: [0, 0, 1]               # Rotation/translation axis
    limits:
      lower: -1.57                # Min position [rad or m]
      upper: 1.57                 # Max position [rad or m]
      effort: 10.0                # Max torque/force [Nm or N]
      velocity: 1.0               # Max velocity [rad/s or m/s]
    dynamics:
      damping: 0.5                # Damping coefficient
      friction: 0.1               # Friction coefficient
```

### Joint List

| Joint | Type | Axis | Range | Max Velocity | Max Effort |
|-------|------|------|-------|--------------|------------|
| `scara_shoulder_joint` | revolute | Z | ±57° | 1.6 rad/s | 20 Nm |
| `scara_elbow_joint` | revolute | Z | ±185° | 1.5 rad/s | 3.3 Nm |
| `scara_wrist_joint` | revolute | Z | ±360° | 3.3 rad/s | 5 Nm |
| `tool_fix_joint` | fixed | - | - | - | - |
| `tool_to_tcp_joint` | fixed | - | - | - | - |

### Joint Limits Explained

```yaml
limits:
  lower: -0.995       # Minimum angle in radians (-57°)
  upper: 0.995        # Maximum angle in radians (+57°)
  effort: 20.0        # Maximum torque in Nm
  velocity: 1.6       # Maximum angular velocity in rad/s
```

**Conversions:**
- Degrees to radians: `rad = deg × π/180`
- Radians to degrees: `deg = rad × 180/π`

| Degrees | Radians |
|---------|---------|
| 57° | 0.995 |
| 90° | 1.571 |
| 180° | 3.142 |
| 185° | 3.228 |
| 360° | 6.283 |

### Joint Dynamics

```yaml
dynamics:
  damping: 1.0        # Viscous damping (resistance to motion)
  friction: 0.5       # Coulomb friction (static resistance)
```

| Parameter | Effect of Higher Value |
|-----------|----------------------|
| `damping` | Slower, smoother motion |
| `friction` | More resistance to start moving |

**Typical values:**

| Joint Type | Damping | Friction |
|------------|---------|----------|
| High precision | 0.1 - 0.5 | 0.1 - 0.3 |
| Standard | 0.5 - 1.0 | 0.3 - 0.5 |
| Heavy duty | 1.0 - 2.0 | 0.5 - 1.0 |

---

## Complete Configuration Example

```yaml
# SCARA Arm Parameters
# Custom configuration for warehouse robot

# ============================================================================
# MOUNTING CONFIGURATION
# ============================================================================
mount:
  offset:
    xyz: [0, 0, 0.2]        # 200mm above parent
    rpy: [0, 0, 0]          # No rotation

# ============================================================================
# KINEMATIC PARAMETERS
# ============================================================================
kinematics:
  L1: 0.4125                # Shoulder to elbow [m]
  L2: 0.2625                # Elbow to wrist [m]

# ============================================================================
# LINKS
# ============================================================================
links:
  scara_base_link:
    mesh: "scara_base_link.STL"
    color: [0.3, 0.3, 0.3, 1.0]    # Dark grey
    inertial:
      mass: 1.4882
      origin: {xyz: [0, 0.075726, -0.025], rpy: [0, 0, 0]}
      inertia: {ixx: 0.0084886, ixy: 0, ixz: 0,
                iyy: 0.0022117, iyz: 0, izz: 0.01008}

  scara_shoulder_link:
    mesh: "scara_shoulder_link.STL"
    color: [0.7, 0.7, 0.7, 1.0]    # Light grey
    inertial:
      mass: 4.227
      origin: {xyz: [0.20625, 0, 0.025], rpy: [0, 0, 0]}
      inertia: {ixx: 0.0105, ixy: 0, ixz: 0,
                iyy: 0.1069, iyz: 0, izz: 0.1156}

  # ... (other links)

  tcp_link:
    color: [1.0, 0.0, 0.0, 1.0]    # Red marker
    radius: 0.02                    # Larger marker
    inertial:
      mass: 0.01
      origin: {xyz: [0, 0, 0], rpy: [0, 0, 0]}
      inertia: {ixx: 0.000001, ixy: 0, ixz: 0,
                iyy: 0.000001, iyz: 0, izz: 0.000001}

# ============================================================================
# JOINTS
# ============================================================================
joints:
  scara_shoulder_joint:
    type: "revolute"
    origin: {xyz: [0, 0, 0], rpy: [0, 0, 0]}
    axis: [0, 0, 1]
    limits:
      lower: -1.57              # ±90° instead of ±57°
      upper: 1.57
      effort: 25.0              # Increased torque
      velocity: 2.0             # Faster
    dynamics:
      damping: 0.8
      friction: 0.4

  # ... (other joints)

  tool_to_tcp_joint:
    type: "fixed"
    origin: {xyz: [0, 0, -0.25], rpy: [0, 0, 0]}  # Longer tool
```

---

## Validation

### Check YAML Syntax

```bash
python3 -c "import yaml; yaml.safe_load(open('src/scara_description/config/scara_params.yaml'))"
```

### Generate and Check URDF

```bash
# Generate URDF
ros2 run xacro xacro src/scara_description/urdf/robot.urdf.xacro > /tmp/scara.urdf

# Check for errors
check_urdf /tmp/scara.urdf
```

### Visualize Changes

```bash
ros2 launch scara_description display.launch.py
```

---

## Common Modifications

### Change Mount Height

```yaml
mount:
  offset:
    xyz: [0, 0, 0.3]    # Change from 0.15 to 0.3
```

### Rotate SCARA 90°

```yaml
mount:
  offset:
    rpy: [0, 0, 1.5708]  # 90° around Z
```

### Increase Joint Speed

```yaml
joints:
  scara_shoulder_joint:
    limits:
      velocity: 2.5      # Increase from 1.6
```

### Change Link Color

```yaml
links:
  scara_shoulder_link:
    color: [0.0, 0.5, 1.0, 1.0]  # Blue
```

### Adjust TCP Position

```yaml
joints:
  tool_to_tcp_joint:
    origin: {xyz: [0, 0, -0.3], rpy: [0, 0, 0]}  # Longer reach
```
