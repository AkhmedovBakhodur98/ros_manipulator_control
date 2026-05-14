# A6-EC Series PDO Mapping

> Notes on configuring StepperOnline A6-EC servo drives (A6-200EC, A6-400EC, A6-750EC) as CiA 402 slaves under IgH + `ethercat_driver_ros2`. Identity values below were verified on real hardware on `grenka` 2026-05-14 (Stage 3 of [bringup.md](bringup.md)). Object-dictionary subset is from StepperOnline manual + LinuxCNC community (no public ROS 2 deployment of A6-EC exists yet, we are the first).

## Verified Identity (from physical drives, 2026-05-14)

Read via `ethercat upload -p <N>` on bench (1× A6-200EC + 1× A6-750EC, both in `PREOP`):

| SDO | Value |
|---|---|
| `0x1018:01` Vendor ID | `0x00400000` |
| `0x1018:02` Product Code | `0x00000715` |
| `0x1018:03` Revision | `0x00005612` (via SDO) / `0x00002ef8` (via SII) |
| `0x1018:04` Serial Number | `0x00000000` (not flashed by vendor) |
| `0x1008` Device Name | `AS715N-DRIVER` |
| `0x1009` HW Version | `V001` |
| `0x100A` SW Version | `V512` |
| Order number (SII) | `ANCTL AS715N Servo Driver` |
| Group (SII) | `AC Servo Driver` |

**Critical: all A6-EC drives share the same Vendor+Product+Revision.** Identity SDOs from A6-200EC and A6-750EC on the bench were byte-identical. The wattage (200W vs 750W) is **not** distinguishable via EtherCAT-level identity — it lives in the motor/drive hardware (FETs, current sensors) and possibly in vendor-specific SDOs (TBD when ESI XML lands). Bind axes via:

1. **Alias in EEPROM** (preferred, what we use on the bench): `ethercat alias --alias N -p <pos>` writes a unique number, survives reboots, and is what `ros2_control` YAML should reference. On the bench: A6-200EC = alias `6`, A6-750EC = alias `4`.
2. **Ring position** (slave 0, 1, 2, ...) — fragile: re-cabling reshuffles indices.

**Revision mismatch SDO vs SII:** SDO `0x1018:03` returns `0x5612` (firmware-reported), SII (EEPROM) carries `0x2ef8`. Both come from the same drive — they are independent fields. `ros2_control` slave matching uses the SII value (that's what the master sees during scan).

## What A6-EC actually is

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
# config/ethercat/a6_750ec_slave.yaml (sketch — sync_*/PDO map still to verify on bench)
vendor_id: 0x00400000          # verified 2026-05-14 from drive SDO 0x1018:01
product_id: 0x00000715         # verified 2026-05-14 from drive SDO 0x1018:02
revision_number: 0x00002ef8    # SII value (used by master during scan)
alias: 4                       # bench A6-750EC; A6-200EC uses alias 6

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

Vendor ESI XML is checked into the repo at [`vendor/STEPPERONLINE_A6_Servo_V0.04.xml`](vendor/STEPPERONLINE_A6_Servo_V0.04.xml) (310 KB, SHA256 `b8e96d8a0d1e5da413c3be0255be1df6a16cde55bc89a2d1800bf13b6490e9f6`).

Source:
<https://www.omc-stepperonline.com/index.php?route=product/product/get_file&file=5072/STEPPERONLINE_A6_Servo_V0.04.xml>

**Note on IgH usage:** IgH 1.6 master does **not** auto-load ESI files at runtime — the master reads SII from each slave's EEPROM at scan time. The XML is for our own reference (mapping IDs to documentation, finding mappable PDO entries, sanity-checking SM addresses). No need to copy it anywhere on the host.

**Version mismatch with hardware (not blocking):** the XML describes `A6N_sAxis_V0.04`. Our bench drives report `AS715N_sAxis_V0.10` (newer). All CiA 402 standard objects we care about (0x6040, 0x607A, 0x6060/61, etc.) are version-stable, but if we hit a vendor-specific object that doesn't behave as the XML says, suspect the version delta.

**Confirmed against hardware (2026-05-14):**

| Field | XML | Hardware (SDO/SII) | Match |
|---|---|---|---|
| Vendor ID | `0x00400000` | `0x00400000` | ✓ |
| Product Code | `0x00000715` | `0x00000715` | ✓ |
| Revision | `0x00002EF8` | `0x00002EF8` (SII) | ✓ |
| ProfileNo | 402 | — (implicit from SDOs) | ✓ |
| MBox Out / SM0 | `0x1000` / 256 B | `0x1000/256` | ✓ |
| MBox In / SM1 | `0x1400` / 256 B | `0x1400/256` | ✓ |
| SM2 (Outputs) | `0x1800`, 12 B default | — | n/a (set at runtime) |
| SM3 (Inputs) | `0x1C00`, 28 B default | — | n/a (set at runtime) |
| DC AssignActivate | `0x300` | — | — (we will set this) |

**Variable PDOs (Fixed="0") — what's actually pre-mapped:**

- `0x1600` ships with: `0x6040` Controlword, `0x607A` Target Position, `0x60B8` Touch Probe Function (only 3 entries — **Mode of Operation `0x6060` not pre-mapped, we must add it**).
- `0x1A00` ships with: `0x6041` Statusword, `0x6064` Position Actual, `0x603F` Error Code, `0x60B9/BA/BC` Touch Probe, `0x60FD` Digital Inputs (**Mode Display `0x6061` and Actual Velocity `0x606C` not pre-mapped, must be added**).

The Fixed-1 group `0x1701/0x1B01` (the default SM2/SM3 assignment) does not include `0x6060/0x6061` either — which is why CSP locks up in SafeOP+Error on it. Conclusion stands: reconfigure variable `0x1600/0x1A00` via SDO writes to `0x1600:0..N` and `0x1A00:0..N` before the slave transitions to PREOP→SafeOP.

Manual PDF (object dictionary in human-readable form):
<https://www.omc-stepperonline.com/download/A6-EC_series_servo_drive_manual.pdf>

## Useful References

- [LinuxCNC thread — first A6 deployment](https://forum.linuxcnc.org/ethercat/54965-stepperonline-a6-servo)
- [LinuxCNC thread — A6-1000EC, working CSP config](https://forum.linuxcnc.org/ethercat/57091-stepperonline-a6-1000ec-driver)
- [StepperOnline Beckhoff/TwinCAT tutorial](https://help.stepperonline.com/en/article/configuration-tutorial-for-a6-ec-series-servo-motors-with-beckhoff-plc-8f31i8/) — sanity-check the PDO config they use
- [ICube CiA 402 config docs](https://icube-robotics.github.io/ethercat_driver_ros2/user_guide/config_cia402_drive.html)
