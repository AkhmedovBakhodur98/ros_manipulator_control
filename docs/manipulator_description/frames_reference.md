# Manipulator Frame Reference

This document describes the coordinate frames for each link in the manipulator system. Use this to understand where to mount attachments like the SCARA arm.

---

## Coordinate System Convention

All frames follow the **ROS REP-103** convention:
- **X** = Forward (red axis in RViz)
- **Y** = Left (green axis in RViz)
- **Z** = Up (blue axis in RViz)

---

## Main Frame Chain

```
world
 │
 └── base_link (railway base)
      │   Frame: X=along rail, Y=perpendicular, Z=up
      │
      └── main_frame (carriage, moves on X)
           │   Frame: same orientation as base_link
           │
           └── selector_frame (vertical lift, moves on Z)
                │   Frame: same orientation
                │
                ├── left_container_jaw (moves on -Y)
                ├── right_container_jaw (moves on +Y)
                │
                └── picker_frame (fine Z adjustment)  ◄── SCARA MOUNTS HERE
                     │
                     │   Frame origin: at joint connection point
                     │   X = forward (along rail direction)
                     │   Y = left (perpendicular to rail)
                     │   Z = up (vertical)
                     │
                     └── [SCARA arm when enabled]
```

---

## picker_frame Coordinate System

This is the default parent for SCARA mounting.

```
                    Z (up)
                    │
                    │
                    │    ┌─────────────┐
                    │    │             │
                    │    │  picker     │
                    │    │  frame      │
                    │    │  (cyan)     │
                    │    │             │
            Y ◄─────┼────┤             │
          (left)    │    │             │
                    │    └─────────────┘
                    │
                    └────────────► X (forward, along rail)
                   Origin
```

### Frame Details

| Property | Value | Description |
|----------|-------|-------------|
| **Origin** | Joint connection point | Where picker_frame connects to selector_frame |
| **X-axis** | Along rail | Same direction as main_frame travel |
| **Y-axis** | Perpendicular to rail | Points to "left" side |
| **Z-axis** | Vertical up | Same as world Z |
| **Position from selector** | `[-0.138, 0, 0.144]` m | Offset from selector_frame origin |

---

## SCARA Mount Offset Explained

When you set `mount.offset` in `scara_params.yaml`, you're defining where `scara_base_link` sits relative to `picker_frame`:

```yaml
mount:
  offset:
    xyz: [0, 0, 0.15]    # 150mm above picker_frame origin
    rpy: [0, 0, 0]       # Same orientation as picker_frame
```

### Visual Representation

```
                         Z
                         │
                         │   ┌─────────────────┐
                         │   │  SCARA base     │ ← scara_base_link
                         │   └────────┬────────┘
                         │            │
           offset.z=0.15 │            │ mount offset
                         │            │
                         │   ┌────────┴────────┐
                 Y ◄─────┼───┤  picker_frame   │
                         │   └─────────────────┘
                         │
                         └──────────────────────► X
                       picker_frame
                         origin
```

---

## Common Mount Configurations

### Default: Centered Above

```yaml
mount:
  offset:
    xyz: [0, 0, 0.15]     # 150mm up
    rpy: [0, 0, 0]        # No rotation
```

```
Side view (X-Z plane):

     SCARA
       │
       │ 0.15m
       ▼
  ┌─────────┐
  │ picker  │
  └─────────┘
```

### Forward Offset

```yaml
mount:
  offset:
    xyz: [0.1, 0, 0.15]   # 100mm forward, 150mm up
    rpy: [0, 0, 0]
```

```
Side view (X-Z plane):

         SCARA
           │
           │ 0.15m
           ▼
      ┌─────────┐
      │         │
  ┌───┴─────────┘
  │ picker  │
  └─────────┘
      ←0.1m→
```

### Rotated 90° (SCARA faces Y direction)

```yaml
mount:
  offset:
    xyz: [0, 0, 0.15]
    rpy: [0, 0, 1.5708]   # 90° around Z
```

```
Top view (X-Y plane):

  Before rotation:          After rotation:

       SCARA                     SCARA
         │                    ───────►
         │                    shoulder
         ▼                    reaches Y
      shoulder
      reaches X
```

### Rotated 180° (SCARA faces backward)

```yaml
mount:
  offset:
    xyz: [0, 0, 0.15]
    rpy: [0, 0, 3.1416]   # 180° around Z
```

---

## How to Visualize Frames in RViz

1. Launch with SCARA enabled:
   ```bash
   ros2 launch manipulator_description display.launch.py use_scara:=true
   ```

2. In RViz, add **TF** display:
   - Click "Add" → "TF"
   - Enable "Show Names" to see frame labels
   - Enable "Show Axes" to see XYZ arrows

3. Frame colors in RViz:
   - **Red** = X-axis
   - **Green** = Y-axis
   - **Blue** = Z-axis

---

## All Link Frames Summary

| Link | Origin Location | X Direction | Z Direction |
|------|-----------------|-------------|-------------|
| `world` | Global origin | Forward | Up |
| `base_link` | Rail start | Along rail | Up |
| `main_frame` | On carriage | Along rail | Up |
| `selector_frame` | On vertical lift | Along rail | Up |
| `picker_frame` | On picker | Along rail | Up |
| `scara_base_link` | Mount point | **Configurable** | Up |

---

## Tips for Choosing Mount Offset

1. **Check clearance**: Ensure SCARA doesn't collide with selector_frame or container jaws

2. **Consider workspace**: SCARA reach is 0.15m - 0.675m from its base

3. **Test in RViz**: Adjust offset values and reload to visualize

4. **Use TF frames**: Check actual positions with:
   ```bash
   ros2 run tf2_ros tf2_echo picker_frame scara_base_link
   ```

---

## Coordinate Transform Chain

To understand SCARA TCP position in world frame:

```
world → base_link → main_frame → selector_frame → picker_frame → scara_base_link → ... → tcp_link

Transforms:
  world_to_base:         fixed, xyz=[0,0,0.09]
  base_main_frame:       prismatic X, range [0, 4]m
  main_selector:         prismatic Z, range [-0.01, 1.5]m
  selector_picker:       prismatic Z, range [-0.01, 0.3]m
  scara_mount:           fixed, from config (default: xyz=[0,0,0.15])
  scara_shoulder:        revolute Z, range [±57°]
  scara_elbow:           revolute Z, range [±185°]
  scara_wrist:           revolute Z, range [±360°]
  tool_to_tcp:           fixed, xyz=[0,0,-0.2]
```
