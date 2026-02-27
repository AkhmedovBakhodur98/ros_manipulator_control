# AR4 Frame Reference

This document describes the coordinate frames for each link in the AR4 MK3 6-DOF robotic arm. Use this to understand the kinematic chain, joint transforms, and end-effector mounting.

---

## Coordinate System Convention

All frames follow the **ROS REP-103** convention:
- **X** = Forward (red axis in RViz)
- **Y** = Left (green axis in RViz)
- **Z** = Up (blue axis in RViz)

---

## Kinematic Tree

```
world
 └── [base_joint: fixed, xyz=(0, 0, 0), rpy=(0, 0, 0)]
     └── base_link (base housing)
         └── [J1: revolute Z, xyz=(0, 0, 0), rpy=(π, 0, 0)]
             └── link1 (shoulder)
                 └── [J2: revolute -Z, xyz=(0, 0.0642, -0.16977), rpy=(π/2, 0, -π/2)]
                     └── link2 (upper arm)
                         └── [J3: revolute -Z, xyz=(0, -0.305, 0.007), rpy=(0, 0, π)]
                             └── link3 (elbow)
                                 └── [J4: revolute -Z, xyz=(0, 0, 0), rpy=(π/2, 0, -π/2)]
                                     └── link4 (forearm)
                                         └── [J5: revolute X, xyz=(0, 0, -0.22263), rpy=(π, 0, -π/2)]
                                             └── link5 (wrist)
                                                 └── [J6: revolute Z, xyz=(0, 0, 0.03625), rpy=(0, 0, π)]
                                                     └── link6 (flange)
                                                         └── [ee_joint: fixed, xyz=(0, 0, 0), rpy=(0, 0, 0)]
                                                             └── ee_link (end effector)
```

---

## Joint Transform Details

Each joint defines a transform from the parent link frame to the child link frame at zero joint position.

### base_joint (fixed)

| Property | Value |
|----------|-------|
| Parent | `world` |
| Child | `base_link` |
| Type | fixed |
| Origin xyz | `(0, 0, 0)` |
| Origin rpy | `(0, 0, 0)` |

`base_link` is coincident with `world` — no offset, no rotation.

### J1 — Base Rotation (revolute)

| Property | Value |
|----------|-------|
| Parent | `base_link` |
| Child | `link1` |
| Origin xyz | `(0, 0, 0)` |
| Origin rpy | `(π, 0, 0)` — 180° roll |
| Axis | `(0, 0, 1)` — local Z |
| Limits | -170° to +170° |

The 180° roll flips the child frame's Y and Z relative to `base_link`. J1 rotates `link1` around its local Z axis (base yaw).

### J2 — Shoulder (revolute)

| Property | Value |
|----------|-------|
| Parent | `link1` |
| Child | `link2` |
| Origin xyz | `(0, 0.0642, -0.16977)` |
| Origin rpy | `(π/2, 0, -π/2)` |
| Axis | `(0, 0, -1)` — negative local Z |
| Limits | -42° to +90° |

Offset of 64.2 mm in Y and 169.77 mm in -Z (in `link1` frame). Frame reorientation via 90° roll and -90° yaw.

### J3 — Elbow (revolute)

| Property | Value |
|----------|-------|
| Parent | `link2` |
| Child | `link3` |
| Origin xyz | `(0, -0.305, 0.007)` |
| Origin rpy | `(0, 0, π)` |
| Axis | `(0, 0, -1)` — negative local Z |
| Limits | -89° to +52° |

Upper arm length: **305 mm** (offset in -Y of `link2` frame). Small 7 mm offset in Z. Frame rotated 180° in yaw.

### J4 — Forearm Roll (revolute)

| Property | Value |
|----------|-------|
| Parent | `link3` |
| Child | `link4` |
| Origin xyz | `(0, 0, 0)` |
| Origin rpy | `(π/2, 0, -π/2)` |
| Axis | `(0, 0, -1)` — negative local Z |
| Limits | -165° to +165° |

No positional offset — J4 is co-located with J3. Frame reorientation via 90° roll and -90° yaw.

### J5 — Wrist Pitch (revolute)

| Property | Value |
|----------|-------|
| Parent | `link4` |
| Child | `link5` |
| Origin xyz | `(0, 0, -0.22263)` |
| Origin rpy | `(π, 0, -π/2)` |
| Axis | `(1, 0, 0)` — local X |
| Limits | -105° to +105° |

Forearm length: **222.63 mm** (offset in -Z of `link4` frame). Frame rotated 180° roll and -90° yaw. Rotation axis is X (unlike other joints).

### J6 — Wrist Roll (revolute)

| Property | Value |
|----------|-------|
| Parent | `link5` |
| Child | `link6` |
| Origin xyz | `(0, 0, 0.03625)` |
| Origin rpy | `(0, 0, π)` |
| Axis | `(0, 0, 1)` — local Z |
| Limits | -155° to +155° |

Flange offset: **36.25 mm** in Z. Frame rotated 180° in yaw.

### ee_joint (fixed)

| Property | Value |
|----------|-------|
| Parent | `link6` |
| Child | `ee_link` |
| Origin xyz | `(0, 0, 0)` |
| Origin rpy | `(0, 0, 0)` |

`ee_link` is coincident with `link6` — the mounting surface for end-effector tools.

---

## Link Summary

| # | Link | Description | Mass (kg) |
|---|------|-------------|-----------|
| 1 | `base_link` | Base housing | 0.710 |
| 2 | `link1` | Shoulder | 0.881 |
| 3 | `link2` | Upper arm | 0.577 |
| 4 | `link3` | Elbow | 0.179 |
| 5 | `link4` | Forearm | 0.349 |
| 6 | `link5` | Wrist | 0.116 |
| 7 | `link6` | Flange | 0.014 |
| 8 | `ee_link` | End effector mount | (virtual) |

**Total arm mass:** ~2.826 kg

---

## Key Dimensions

```
        ┌───────┐
        │ base  │  base_link
        │ link  │
        └───┬───┘
            │  J1 (yaw, ±170°)
        ┌───┴───┐
        │ link1 │  shoulder
        │       │  169.77 mm height
        └───┬───┘
            │  J2 (shoulder, -42° to +90°)
            │
     ┌──────┴──────┐
     │    link2    │  upper arm
     │  305.0 mm   │
     └──────┬──────┘
            │  J3 (elbow, -89° to +52°)
        ┌───┴───┐
        │ link3 │  J4 co-located (forearm roll, ±165°)
        └───┬───┘
            │
     ┌──────┴──────┐
     │    link4    │  forearm
     │  222.63 mm  │
     └──────┬──────┘
            │  J5 (wrist pitch, ±105°)
        ┌───┴───┐
        │ link5 │  wrist
        └───┬───┘
            │  J6 (wrist roll, ±155°)
        ┌───┴───┐
        │ link6 │  flange, 36.25 mm
        └───┬───┘
            │
         ee_link
```

---

## Joint Axis Summary

| Joint | Rotation Axis (local frame) | Function |
|-------|-----------------------------|----------|
| J1 | Z `(0,0,1)` | Base yaw |
| J2 | -Z `(0,0,-1)` | Shoulder pitch |
| J3 | -Z `(0,0,-1)` | Elbow pitch |
| J4 | -Z `(0,0,-1)` | Forearm roll |
| J5 | X `(1,0,0)` | Wrist pitch |
| J6 | Z `(0,0,1)` | Wrist roll |

---

## End-Effector Mounting

`ee_link` is the tool mounting frame, coincident with `link6`. To attach a tool (gripper, camera, etc.), create a fixed joint from `ee_link`:

```xml
<joint name="tool_joint" type="fixed">
  <parent link="ee_link"/>
  <child link="tool_link"/>
  <origin xyz="0 0 0.05" rpy="0 0 0"/>  <!-- 50mm offset example -->
</joint>
```

When using the `ar4_robot` macro with `tf_prefix`, reference `${tf_prefix}ee_link` as the parent.

---

## How to Visualize Frames in RViz

1. Launch AR4:
   ```bash
   ros2 launch manipulator_bringup ar4_bringup.launch.py
   ```

2. In RViz, add **TF** display:
   - Click "Add" -> "TF"
   - Enable "Show Names" to see frame labels
   - Enable "Show Axes" to see XYZ arrows

3. Frame colors in RViz:
   - **Red** = X-axis
   - **Green** = Y-axis
   - **Blue** = Z-axis

4. Check transforms via CLI:
   ```bash
   # ee_link pose relative to world
   ros2 run tf2_ros tf2_echo world ee_link

   # Any frame pair
   ros2 run tf2_ros tf2_echo base_link link4
   ```

---

## Coordinate Transform Chain

```
world -> base_link -> link1 -> link2 -> link3 -> link4 -> link5 -> link6 -> ee_link

Transforms:
  base_joint:   fixed,     xyz=(0, 0, 0)
  J1:           revolute Z,  ±170°
  J2:           revolute -Z, -42° to +90°,   offset 169.77 mm
  J3:           revolute -Z, -89° to +52°,   upper arm 305.0 mm
  J4:           revolute -Z, ±165°,           co-located with J3
  J5:           revolute X,  ±105°,           forearm 222.63 mm
  J6:           revolute Z,  ±155°,           flange 36.25 mm
  ee_joint:     fixed,     coincident with link6
```
