# A6-EC Series PDO Mapping

> Notes on configuring StepperOnline A6-EC servo drives (A6-200EC, A6-400EC, A6-750EC) as CiA 402 slaves under IgH + `ethercat_driver_ros2`. As of 2026-05-13 no slave has been connected yet — these notes come from the StepperOnline ESI/manual and from LinuxCNC community experience (no public ROS 2 deployment of A6-EC exists yet, we are the first).

## What A6-EC actually is

StepperOnline A6-EC is a **standard CiA 402 servo drive** with EtherCAT communication. Complexity is comparable to Delta ASDA-A2/A3 or Leadshine ELP — far simpler than Beckhoff AX5000. 17-bit absolute encoder, DC sync up to 125 µs.

Modes of operation supported (relevant to us):
- **CSP** (Cyclic Synchronous Position) — what we'll use, mode 8
- CSV (Cyclic Synchronous Velocity) — mode 9, fallback for testing
- Homing — mode 6
- PP / PV — not used in real-time control

## The Critical Pitfall — Default PDO Group

A6-EC ships with **fixed PDO group 0x1701 / 0x1B01 as default**. Multiple LinuxCNC users hit the same wall: the slave gets stuck in SafeOP+Error when this group is active. The fix is to either:

1. Switch to a different fixed group (e.g. 0x1702/0x1B02), or
2. Use **variable mapping 0x1600 / 0x1A00** and define entries explicitly.

We will use variable mapping. It's slightly more verbose in YAML but guarantees we get exactly the entries we need.

## Object Dictionary (Subset We Care About)

| Index | Sub | Name | Type | Direction | Notes |
|-------|-----|------|------|-----------|-------|
| 0x6040 | 0 | ControlWord | UINT16 | Rx (master → slave) | CiA 402 state machine |
| 0x6041 | 0 | StatusWord | UINT16 | Tx | Slave state |
| 0x6060 | 0 | Mode of Operation | INT8 | Rx | 8 = CSP, 9 = CSV, 6 = Homing |
| 0x6061 | 0 | Mode of Operation Display | INT8 | Tx | Echoed by slave |
| 0x607A | 0 | Target Position | INT32 | Rx | encoder counts |
| 0x6064 | 0 | Actual Position | INT32 | Tx | encoder counts |
| 0x60FF | 0 | Target Velocity | **INT32** | Rx | counts/s — **S32, not U32** |
| 0x606C | 0 | Actual Velocity | INT32 | Tx | counts/s |
| 0x6071 | 0 | Target Torque | INT16 | Rx | 1/1000 of rated, optional |
| 0x6077 | 0 | Actual Torque | INT16 | Tx | 1/1000 of rated |
| 0x60B0 | 0 | Position Offset | INT32 | Rx | optional, for trajectory shaping |
| 0x60B8 | 0 | Touch Probe Function | UINT16 | Rx | optional |

**`target-velocity` (0x60FF) is signed INT32.** This is called out separately because some drives use U32 here, and the LinuxCNC threads explicitly note that A6 uses S32 — getting this wrong silently produces wrong direction at speeds > 2³¹ count/s.

## CSP PDO Map (Planned YAML)

```yaml
# config/ethercat/a6_750ec_slave.yaml (sketch — verify against ESI before deploying)
vendor_id: 0x000004F2          # TODO: confirm from STEPPERONLINE_A6_Servo_V0.04.xml
product_id: 0x00000001         # TODO: confirm

# DC clocks: SYNC0 + SYNC1 active, 0-shift, 1 ms cycle
assign_activate: 0x0300
sync0_cycle: 1000000           # ns = 1 ms
sync0_shift: 500000            # half-cycle shift; verify empirically

sm:
  - { index: 2, type: output, watchdog: enable, pdos: [0x1600] }
  - { index: 3, type: input,  watchdog: disable, pdos: [0x1A00] }

rpdo:
  - index: 0x1600
    channels:
      - { index: 0x6040, sub_index: 0, type: uint16 }   # ControlWord
      - { index: 0x607A, sub_index: 0, type: int32  }   # Target Position
      - { index: 0x60B0, sub_index: 0, type: int32  }   # Position Offset
      - { index: 0x6060, sub_index: 0, type: int8   }   # Mode of Operation

tpdo:
  - index: 0x1A00
    channels:
      - { index: 0x6041, sub_index: 0, type: uint16 }   # StatusWord
      - { index: 0x6064, sub_index: 0, type: int32  }   # Actual Position
      - { index: 0x606C, sub_index: 0, type: int32  }   # Actual Velocity
      - { index: 0x6077, sub_index: 0, type: int16  }   # Actual Torque
      - { index: 0x6061, sub_index: 0, type: int8   }   # Mode Display

sdo:
  # Set CSP mode at startup (mirrored by PDO at runtime)
  - { index: 0x6060, sub_index: 0, value: 8, type: int8 }
  # Optional: gear ratios, encoder resolution, position limits — to be filled
```

The A6-750EC, A6-400EC and A6-200EC share the same object dictionary (same CiA 402 implementation). Differences are mechanical (rated torque/speed) and electrical (current). The same YAML structure applies — only the per-joint scaling and limits change.

## Scaling

Position counts and velocity units are encoder-native. A6-EC has a **17-bit absolute encoder** → 131072 counts per motor revolution.

Per-joint conversion (in the ros2_control YAML, not the slave YAML):

```
joint_position_rad = (counts / 131072) * (2π / gear_ratio)
joint_velocity_rad_per_sec = (counts_per_sec / 131072) * (2π / gear_ratio)
```

`gear_ratio` is documented per joint in [`manipulator_description/package_structure.md`](../manipulator_description/package_structure.md) and [`scara_description/package_structure.md`](../scara_description/package_structure.md). The `EcCiA402Drive` plugin handles the count↔rad conversion via its `mechanical_reduction` and `count_per_motor_revolution` parameters.

## CiA 402 State Machine

`EcCiA402Drive` handles the state machine for us, but for debugging it's useful to know the dance:

```
NotReadyToSwitchOn (0x40)
   │  power on
   ▼
SwitchOnDisabled (0x40 | 0x40)
   │  Shutdown (0x06)
   ▼
ReadyToSwitchOn (0x21)
   │  Switch On (0x07)
   ▼
SwitchedOn (0x23)
   │  Enable Operation (0x0F)
   ▼
OperationEnabled (0x27)  ← motor is now responding to PDO target
```

When debugging, `ethercat upload 0x6041 0 -p 0` reads the current StatusWord directly via SDO.

## ESI File Reference

The authoritative source for `vendor_id`, `product_id`, allowed Sync Manager configurations, and the full object dictionary is the StepperOnline ESI XML:

<https://www.omc-stepperonline.com/index.php?route=product/product/get_file&file=5072/STEPPERONLINE_A6_Servo_V0.04.xml>

The IgH master can load this directly:

```bash
sudo cp STEPPERONLINE_A6_Servo_V0.04.xml /etc/ethercat/esi/
sudo systemctl restart ethercat
ethercat slaves -v   # should show readable device name and supported PDOs
```

Manual PDF (object dictionary in human-readable form):
<https://www.omc-stepperonline.com/download/A6-EC_series_servo_drive_manual.pdf>

## Useful References

- [LinuxCNC thread — first A6 deployment](https://forum.linuxcnc.org/ethercat/54965-stepperonline-a6-servo)
- [LinuxCNC thread — A6-1000EC, working CSP config](https://forum.linuxcnc.org/ethercat/57091-stepperonline-a6-1000ec-driver)
- [StepperOnline Beckhoff/TwinCAT tutorial](https://help.stepperonline.com/en/article/configuration-tutorial-for-a6-ec-series-servo-motors-with-beckhoff-plc-8f31i8/) — sanity-check the PDO config they use
- [ICube CiA 402 config docs](https://icube-robotics.github.io/ethercat_driver_ros2/user_guide/config_cia402_drive.html)
