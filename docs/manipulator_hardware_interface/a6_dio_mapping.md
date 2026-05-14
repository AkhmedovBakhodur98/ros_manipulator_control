# A6-EC Series — Digital I/O Mapping

> Notes on the StepperOnline A6-EC CN1 digital I/O layout and how it surfaces in CiA 402 / our `manipulator_hardware_interface` config. All values verified against the **A6-EC user manual** (vendor PDF in [`vendor/A6-EC_series_servo_drive_manual.pdf`](vendor/A6-EC_series_servo_drive_manual.pdf), SHA256 `69753df5d63424a0cab709d43932a43e55012a8a06a9f31e3b364870c7e49731`) and against the bench A6-200EC at alias 6 (Stage 6.6a, 2026-05-14).

## CN1 Connector — DI/DO Pinout

DB15 user-control connector. Pin numbers from manual §3.7.2 (table on page 31 of the PDF, "CN1 user control terminal").

| Pin | Signal | Default function (manual table) |
|---|---|---|
| 10 | **DI1** | **Positive limit switch (P-OT)** |
| 9  | **DI2** | **Negative limit switch (N-OT)** |
| 8  | DI3 | Home switch |
| 7  | DI4 | Probe 2 |
| 11 | DI5 | Probe 1 |
| 13 | COM+ | Common terminal of DI |
| 14 | COM- | DI 0 V return |
| 15 | +24 V | Internal 24 V supply, 200 mA max |
| 1  | DO1+ | Servo ready (S-RDY) |
| 6  | DO1- | (DO1 emitter) |
| 3  | DO2+ | Fault (ALM) |
| 2  | DO2- | (DO2 emitter) |
| 5  | DO3+ | Brake (BK) |
| 4  | DO3- | (DO3 emitter) |

**Function-to-pin reassignment** is possible via vendor parameter group `0x2003` (DI function selection) and `0x2004` (DO function selection) — see manual §11.3 Group description. **For our bench we keep the factory defaults**, so no SDO writes for DI/DO function assignment are needed.

**Function codes** (manual Chapter 9):

- DI: `FunIN.1` S-ON, `FunIN.2` ALM-RST (both **only active in non-bus mode** — under EtherCAT the equivalents are 0x6040 ControlWord bits), `FunIN.4` Emergency Stop, `FunIN.5` HomeSwitch, `FunIN.6` **P-OT**, `FunIN.7` **N-OT**, `FunIN.30/31` Touch Probe 1/2.
- DO: `FunOUT.1` S-RDY, `FunOUT.2` TGON (motor at speed), `FunOUT.3` **BK** (brake — wired to 24 V brake-relay coil on motors with built-in brake), `FunOUT.4` **ALM** (fault), `FunOUT.5` WARN.

**DI electrical characteristics (manual §3.7.2):**

- 4.7 kΩ pull, opto-isolated. Internal 24 V supply on pin 15 sufficient for typical relay/sensor loads (< 200 mA total budget).
- **Cannot mix NPN and PNP** in the same DI bank — the same COM polarity has to be used for all DI on the connector.
- "Active" = current flowing through the DI opto. With the internal supply: tie COM- (pin 14) to the switch return; the switch closes between the DI pin and COM- (NPN-style sink).

**DO electrical characteristics (manual §3.7.2):**

- Open-collector optocoupler, **30 V max / 50 mA max**.
- **Flywheel diode mandatory** when driving a relay coil — without it the inductive kickback will damage the DO transistor.
- Brake wiring (manual §3.7.3, fig 3-7): DO3 → BK-RY relay coil → relay contact → 24 V brake-coil supply → motor brake. We use this on motors with built-in brake (any 750EC / 1000EC variant per the brake spec table).

## CiA 402 0x60FD Digital Inputs — Bit Layout

The drive maps each DI pin into two locations of the `0x60FD` (Digital Inputs, UINT32, RO, TPDO-mappable) word:

| Bits | Source | Notes |
|---|---|---|
| 0 | **N-OT** logical state (`FunIN.7`) | CiA 402 standard bit 0. Set when `FunIN.7` evaluated active by the function selector. |
| 1 | **P-OT** logical state (`FunIN.6`) | CiA 402 standard bit 1. Set when `FunIN.6` evaluated active. |
| 2 | **HomeSwitch** logical state (`FunIN.5`) | CiA 402 standard bit 2. |
| 3..15 | reserved | per CiA 402; A6-EC reports 0. |
| 16 | DI1 raw line state | manufacturer-specific. Tracks the *physical* DI1 input regardless of how `FunIN.x` is assigned. |
| 17 | DI2 raw line state | manufacturer-specific. |
| 18 | DI3 raw line state | (assumed; not yet verified) |
| 19 | DI4 raw line state | (assumed) |
| 20 | DI5 raw line state | (assumed) |

**Verified on bench 2026-05-14 (Stage 6.6a, A6-200EC alias 6, default DI mapping):**

| Pressed | `0x60FD` reading | Decoded |
|---|---|---|
| Neither | `0x00000000` | all clear |
| P-OT (DI1) | `0x00010002` | bit 1 (CiA P-OT) + bit 16 (DI1 raw) |
| N-OT (DI2) | `0x00020001` | bit 0 (CiA N-OT) + bit 17 (DI2 raw) |

The pairing (CiA logical bit + raw bit always rise together for our default mapping) confirms the factory `FunIN.6 ↔ DI1`, `FunIN.7 ↔ DI2` assignment is in place — we don't need any vendor SDO writes to make P-OT and N-OT work.

## Drive-side blocking behaviour

When P-OT or N-OT is active, the drive **autonomously** stops motion in the corresponding direction (manual Chapter 9, function description "Active: Forward drive disabled" / "Active: Reverse drive disabled"). This is enforced inside the drive MCU's current loop, **independent of the EtherCAT cyclic data plane and our ros2_control loop**.

**Verified on bench 2026-05-14:** with P-OT held, sent `forward_position_controller` target = current + 20 000 counts (forward direction). Position did not advance toward the target (stayed within ~3.6k counts of the original — encoder noise / undriven freewheeling on the test pulley). StatusWord `0x6041` reported **bit 11 "Internal limit active" = 1** during the held window — that's the recommended observable from the application layer to know the drive is self-clamping. ErrorCode `0x603F = 0x5443` was latched (decoding pending — Chapter 10.1.3 of the manual; not blocking, drive remained in OperationEnabled).

**What this means for our stack:** safety on overtravel doesn't need to live in the ros2_control loop. The drive halts the axis on its own; our application can poll `0x6041` bit 11 (or watch `0x60FD` bit 0/1) to react in user-space (e.g. abort a trajectory, light up a UI flag).

## How it is wired in our slave YAML

[`config/ethercat/a6_200ec_slave.yaml`](../../src/manipulator_hardware_interface/config/ethercat/a6_200ec_slave.yaml) appends a single channel to TPDO 0x1A00:

```yaml
- {index: 0x60FD, sub_index: 0, type: uint32, state_interface: digital_inputs}
```

That exposes the entire 32-bit word as a `state_interface` named `digital_inputs` on `bench_joint`. Bit extraction is left to the consumer — for Stage 6.6a we only verify the word reaches `/dynamic_joint_states`. A future homing action server (Stage 6.6b) and a safety node will do the bit-masking themselves.

## Known unknowns / follow-ups

1. **`0x603F = 0x5443` decoding** — looks like a vendor-specific overtravel alarm. Manual Chapter 10.1.3 ("List of faults and alarms", page ~171) has the full table — confirm and document.
2. **DI3..DI5 raw bits in 0x60FD bits 18..20** — assumed by analogy with DI1/DI2 but not verified (we don't use those DIs on the bench).
3. **DI logic level / polarity vendor SDOs** — group `0x2003`, sub-indices not yet documented here. Not needed for default behaviour (NPN with internal +24 V).
4. **Stage 6.6b** — homing action server that switches mode_of_operation to 6, drives ControlWord bit 4 rising-edge, polls StatusWord bit 12 for completion. Uses `0x6098` (homing method 1 or 2 for limit-switch + Z), `0x6099:01/02` (search velocities — must be cut down from the factory defaults of ~6400/640 rpm), `0x609A` (acceleration), `0x607C` (offset).
