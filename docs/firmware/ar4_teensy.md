# AR4 Teensy 4.1 Firmware Documentation

## Overview

The `firmware/ar4_teensy/` directory contains a PlatformIO-based firmware for the Teensy 4.1 microcontroller that drives the AR4 arm's stepper motors. It provides a text-based serial protocol for position control, homing, and status queries. The firmware is designed to be **testable standalone** via a serial monitor before any ROS2 integration.

Currently controls all 6 joints: **J1** (base rotation), **J2** (shoulder), **J3** (elbow), **J4** (wrist roll), **J5** (wrist pitch), and **J6** (wrist yaw).

---

## Hardware

| Component | Model | Role |
|-----------|-------|------|
| Microcontroller | Teensy 4.1 | Step/dir pulse generation, protocol handling |
| Driver | MKS SERVO42C | Closed-loop stepper driver (step/dir input, self-enabling) |
| Motor (J1,J3,J5) | NEMA 17 | 200 full steps/rev |
| Motor (J2) | NEMA 23 | 200 full steps/rev |
| Motor (J4) | NEMA 11 (28hs5006a4) | 200 full steps/rev |
| Motor (J6) | NEMA 14 (14hs2812-pg19) | 200 full steps/rev |
| Reducer (J1) | Sumtor 42XG10 | 40:1 planetary gearbox |
| Reducer (J2) | Planetary | 100:1 planetary gearbox |
| Reducer (J3) | Sumtor 42XG50 | 50:1 planetary gearbox |
| Reducer (J4) | Planetary | 40:1 planetary gearbox |
| Actuator (J5) | 42BYGH47-T8×8-200mm | NEMA 17 + T8 lead screw (8mm lead, 200mm travel) |
| Driver (J6) | MKS 35D RS485 | Step/dir driver with 19:1 built-in planetary |
| Limit switch | V-156-1C25 (Omron) | NC wiring (COM+NC terminals) |

**Resolution (J1):** 200 steps/rev × 16 microsteps × 40:1 gear = **128 000 steps per output revolution** (0.0028125°/step).
**Resolution (J2):** 200 steps/rev × 16 microsteps × 100:1 gear = **320 000 steps per output revolution**.
**Resolution (J3):** 200 steps/rev × 16 microsteps × 50:1 gear = **160 000 steps per output revolution**.
**Resolution (J4):** 200 steps/rev × 16 microsteps × 40:1 gear = **128 000 steps per output revolution**.
**Resolution (J5):** 200 steps/rev × 16 microsteps = **3 200 steps per motor revolution** (no gear reducer — lead screw mechanism, effective ratio TBD via calibration).
**Resolution (J6):** 200 steps/rev × 16 microsteps × 19:1 gear = **60 800 steps per output revolution**.

### MKS SERVO42C Wiring

**J1:**

| MKS SERVO42C | Teensy 4.1 |
|---|---|
| STP | Pin 0 |
| DIR | Pin 1 |
| EN | not connected (self-enables) |
| COM | not connected (floating) |
| GND | shared GND (Teensy GND + 12V PSU GND) |

**J2:**

| MKS SERVO42C | Teensy 4.1 |
|---|---|
| STP | Pin 2 |
| DIR | Pin 3 (`dir_invert = true`) |
| EN | not connected |
| GND | shared GND |

**J3:**

| MKS SERVO42C | Teensy 4.1 |
|---|---|
| STP | Pin 4 (PLACEHOLDER) |
| DIR | Pin 5 (PLACEHOLDER) |
| EN | not connected |
| GND | shared GND |

**J4 (wrist roll — 40:1 planetary):**

| MKS SERVO42C | Teensy 4.1 |
|---|---|
| STP | Pin 6 |
| DIR | Pin 7 |
| EN | not connected |
| GND | shared GND |
| LIMIT | Pin 26 |

**J5 (wrist pitch — lead screw):**

| MKS SERVO42C | Teensy 4.1 |
|---|---|
| STP | Pin 8 |
| DIR | Pin 9 |
| EN | not connected |
| GND | shared GND |

**J6 (wrist yaw — MKS 35D RS485 + 19:1 built-in planetary):**

| MKS 35D RS485 | Teensy 4.1 |
|---|---|
| STP | Pin 10 |
| DIR | Pin 11 |
| EN | not connected |
| GND | shared GND |
| LIMIT | Pin 28 |

**Important:** The MKS SERVO42C accepts 3.3V–24V on STP/DIR pins. Teensy 3.3V works directly. A 50µs minimum pulse width is set in firmware via `setMinPulseWidth(50)` — the default AccelStepper pulse (~1µs) is too short for the SERVO42C. Tested down from 500µs; 50µs allows speeds up to ~20,000 steps/s.

### Limit Switch Wiring (V-156-1C25)

The switch has 3 terminals: COM, NC, NO. Use **COM → GND** and **NC → Teensy pin** with `INPUT_PULLUP`. Limit pins: J1=29, J2=30, J3=31, J4=26, J5=27, J6=28.

- Switch **not pressed** (NC closed): pin reads LOW (0)
- Switch **pressed/triggered** (NC opens): pin reads HIGH (1) → `LIMIT_TRIGGERED`

---

## Directory Structure

```
firmware/ar4_teensy/
├── platformio.ini          # PlatformIO config for Teensy 4.1
├── .venv/                  # Python venv with PlatformIO (gitignored)
├── include/
│   ├── config.h            # Global constants (baud, num joints, limit polarity)
│   ├── joints_config.h     # Per-joint config structs (pins, motion, homing)
│   ├── protocol.h          # Serial command parser interface
│   ├── motor.h             # AccelStepper wrapper + position tracking
│   └── homing.h            # Non-blocking homing state machine
└── src/
    ├── main.cpp            # setup(), loop(), limit protection, debug output
    ├── protocol.cpp        # Command parsing and handler dispatch
    ├── motor.cpp           # Motor initialization and AccelStepper control
    └── homing.cpp          # Homing sequence implementation
```

---

## File Descriptions

### `platformio.ini`

PlatformIO project configuration.

- **Board:** `teensy41`
- **Framework:** Arduino
- **Monitor speed:** 115200 baud
- **Library dependency:** `waspinator/AccelStepper@^1.64` (trapezoidal motion profiles)

### `include/config.h`

Global constants only. All per-joint configuration has been moved to `joints_config.h`.

| Constant | Value | Description |
|----------|-------|-------------|
| `SERIAL_BAUD` | 115200 | Serial baud rate |
| `NUM_JOINTS` | 6 | Number of active joints (J1–J6) |
| `LIMIT_TRIGGERED` | HIGH | Limit switch triggered state (NC switch opens → pullup → HIGH) |

Includes `joints_config.h` at the end, so any file including `config.h` gets access to the `JOINTS[]` array.

### `include/joints_config.h`

**Single place to edit** when changing pins, motor parameters, or adding joints.

**Structs:**
- `JointPinConfig` — `step_pin`, `dir_pin`, `limit_pin`, `dir_invert`
- `JointMotionConfig` — `max_speed` (steps/sec), `accel` (steps/sec²)
- `JointHomingConfig` — `speed_fast`, `speed_slow`, `backoff_steps`, `home_dir`, `home_offset_steps`
- `JointLimitsConfig` — `min_steps`, `max_steps`, `enabled` (software position limits)
- `JointConfig` — combines all above + `steps_per_output_rev` + `start_position_steps`

**Current J1 configuration:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `step_pin` | 0 | Step pulse output |
| `dir_pin` | 1 | Direction output |
| `limit_pin` | 29 | Limit switch input |
| `dir_invert` | false | No DIR inversion |
| `max_speed` | 12000 steps/s | Motion speed (~33.75°/s output) |
| `accel` | 6000 steps/s² | Acceleration |
| `speed_fast` | 4000 steps/s | Homing fast approach (not yet applied) |
| `speed_slow` | 500 steps/s | Homing slow approach (not yet applied) |
| `backoff_steps` | 800 | Back-off after switch trigger |
| `home_dir` | +1 | Direction toward limit switch |
| `home_offset_steps` | 60444 | Steps from zero to +170° switch |
| `limits.enabled` | false | No soft limits for J1 |
| `steps_per_output_rev` | 128000 | 200 × 16 × 40 |
| `start_position_steps` | 0 | Position assumed on `START` command (0°) |

**Current J2 configuration:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `step_pin` | 2 | Step pulse output |
| `dir_pin` | 3 | Direction output |
| `limit_pin` | 30 | Limit switch input |
| `dir_invert` | true | Invert DIR signal via AccelStepper |
| `max_speed` | 8000 steps/s | Motion speed |
| `accel` | 4000 steps/s² | Acceleration |
| `speed_fast` | 3000 steps/s | Homing fast approach |
| `speed_slow` | 400 steps/s | Homing slow approach |
| `backoff_steps` | 800 | Back-off after switch trigger |
| `home_dir` | -1 | Direction toward limit switch (negative) |
| `home_offset_steps` | -37333 | Steps from zero to -42° switch |
| `limits.min_steps` | -39111 | -44° soft limit |
| `limits.max_steps` | 80000 | +90° soft limit |
| `limits.enabled` | true | Soft limits active |
| `steps_per_output_rev` | 320000 | 200 × 16 × 100 |
| `start_position_steps` | 64889 | Position assumed on `START` command (73°) |

**Current J3 configuration:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `step_pin` | 4 | Step pulse output (PLACEHOLDER — set actual pins) |
| `dir_pin` | 5 | Direction output (PLACEHOLDER — set actual pins) |
| `limit_pin` | 31 | Limit switch input |
| `dir_invert` | true | DIR signal inverted to match URDF joint axis |
| `max_speed` | 6000 steps/s | Motion speed |
| `accel` | 3000 steps/s² | Acceleration |
| `speed_fast` | 2000 steps/s | Homing fast approach |
| `speed_slow` | 300 steps/s | Homing slow approach |
| `backoff_steps` | 800 | Back-off after switch trigger |
| `home_dir` | +1 | Direction toward limit switch (positive, after dir invert) |
| `home_offset_steps` | 39556 | Steps from zero to +89° switch |
| `limits.min_steps` | -23111 | -52° soft limit |
| `limits.max_steps` | 39556 | +89° soft limit |
| `limits.enabled` | true | Soft limits active |
| `steps_per_output_rev` | 160000 | 200 × 16 × 50 |
| `start_position_steps` | 2800 | Position assumed on `START` command (+6.3°) |

**Current J4 configuration:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `step_pin` | 6 | Step pulse output |
| `dir_pin` | 7 | Direction output |
| `limit_pin` | 26 | Limit switch input |
| `dir_invert` | false | No DIR inversion |
| `max_speed` | 8000 steps/s | Motion speed |
| `accel` | 4000 steps/s² | Acceleration |
| `speed_fast` | 4000 steps/s | Homing fast approach |
| `speed_slow` | 800 steps/s | Homing slow approach |
| `backoff_steps` | 800 | Back-off after switch trigger |
| `home_dir` | -1 | Direction toward limit switch (negative) |
| `home_offset_steps` | -64000 | Steps from zero to switch (-180°) |
| `limits.min_steps` | -64000 | PLACEHOLDER soft limit |
| `limits.max_steps` | 64000 | PLACEHOLDER soft limit |
| `limits.enabled` | true | Soft limits active |
| `steps_per_output_rev` | 128000 | 200 × 16 × 40 |
| `start_position_steps` | 0 | Position assumed on `START` command (0°) |

**Current J5 configuration (PLACEHOLDER — calibrate with real hardware):**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `step_pin` | 8 | Step pulse output |
| `dir_pin` | 9 | Direction output |
| `limit_pin` | 27 | Limit switch input |
| `dir_invert` | false | No DIR inversion |
| `max_speed` | 800 steps/s | Motion speed |
| `accel` | 400 steps/s² | Acceleration |
| `speed_fast` | 300 steps/s | Homing fast approach |
| `speed_slow` | 100 steps/s | Homing slow approach |
| `backoff_steps` | 800 | Back-off after switch trigger |
| `home_dir` | -1 | Direction toward limit switch (negative) |
| `home_offset_steps` | 5000 | PLACEHOLDER — steps from zero to switch |
| `limits.min_steps` | -5500 | PLACEHOLDER soft limit |
| `limits.max_steps` | 5500 | PLACEHOLDER soft limit |
| `limits.enabled` | true | Soft limits active |
| `steps_per_output_rev` | 32000 | ~80mm travel on T8 lead screw (homing search distance) |
| `start_position_steps` | 1067 | Position assumed on `START` command (12°) |

**Note:** J5 uses a T8×8mm lead screw linear actuator instead of a planetary gearbox. The `steps_per_output_rev` value is a placeholder — the actual steps-to-radians conversion must be calibrated empirically by measuring angular displacement for a known number of steps.

**Current J6 configuration:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `step_pin` | 10 | Step pulse output |
| `dir_pin` | 11 | Direction output |
| `limit_pin` | 28 | Limit switch input |
| `dir_invert` | false | No DIR inversion |
| `max_speed` | 2000 steps/s | Motion speed |
| `accel` | 1000 steps/s² | Acceleration |
| `speed_fast` | 1000 steps/s | Homing fast approach |
| `speed_slow` | 200 steps/s | Homing slow approach |
| `backoff_steps` | 800 | Back-off after switch trigger |
| `home_dir` | +1 | Direction toward limit switch (positive) |
| `home_offset_steps` | 30400 | Steps from zero to switch (≈ +180°) |
| `limits.min_steps` | -30400 | PLACEHOLDER soft limit |
| `limits.max_steps` | 30400 | PLACEHOLDER soft limit |
| `limits.enabled` | true | Soft limits active |
| `steps_per_output_rev` | 60800 | 200 × 16 × 19 |
| `start_position_steps` | 0 | Position assumed on `START` command (0°) |

**Note:** J6 uses an MKS 35D RS485 driver with a built-in 19:1 planetary gearbox (not a separate MKS SERVO42C + external reducer).

### `include/protocol.h`

Serial command parser interface. Commands are newline-terminated ASCII strings at 115200 baud.

**Functions:**
- `Protocol::init()` — reset command buffer
- `Protocol::poll()` — read characters from Serial, dispatch complete lines
- `Protocol::respond(msg)` — send a response line
- `Protocol::respondError(code, msg)` — send `ERR <code> <msg>`

### `include/motor.h`

Motor controller class wrapping AccelStepper. No enable/disable — MKS SERVO42C self-enables.

**Class `Motor`:**
- `init(step_pin, dir_pin, max_speed, accel)` — configure pins, set 50µs min pulse width
- `moveTo(target_steps)` — command absolute position (returns false if homing or jogging)
- `forceMoveTo(target_steps)` — bypasses homing guard (used internally by homing code)
- `jogAt(speed_steps_per_sec)` — start velocity-mode jogging (saves maxSpeed, sets far-away target)
- `stopJog()` — decelerate and restore original maxSpeed
- `isJogging()` — true if currently in jog mode
- `currentPosition()` / `setCurrentPosition(pos)` — read/set step counter
- `isRunning()` — true if motor is moving
- `distanceToGo()` — remaining distance to target (sign indicates direction)
- `run()` — must be called every loop() to generate step pulses (includes debug output)
- `stop()` — decelerate to zero speed
- `setHomed(bool)` / `isHomed()` — homing status flags
- `setHoming(bool)` / `isHoming()` — homing-in-progress flags

**Global:** `Motor motors[NUM_JOINTS]` array, `motors_init()` function (loop-based, reads from `JOINTS[]`).

### `include/homing.h`

Non-blocking homing state machine.

**States:** `IDLE` → `APPROACH_FAST` → `BACKOFF` → `APPROACH_SLOW` → `SET_REFERENCE` → `DONE`

**Class `HomingSequence`:**
- `start(motor_id)` — begin homing (returns false if already active)
- `update()` — advance state machine (call every loop), returns true on completion
- `isActive()` — true if homing is in progress
- `motorId()` — which motor is being homed

### `src/main.cpp`

Entry point. In `loop()`:
1. `Protocol::poll()` — process serial commands
2. `homing.update()` — advance homing state machine, send `HOMED <id>` on completion
3. **Direction-aware hard limit protection** — instant stop if limit switch triggered outside homing AND motor is moving toward the switch. Movement away from the switch is allowed (required to leave the switch after homing). Uses `distanceToGo()` and `home_dir` to determine direction.
4. **Software position limits** — for joints with `limits.enabled` (e.g. J2), monitors position after homing. If motor is at or beyond a soft limit and moving further out of bounds, instant stop via `setCurrentPosition()`. Direction-aware: only stops movement toward the exceeded limit. Prints `DBG SOFT_LIMIT motor=X` on stop.
5. **Debug position output** — prints position every 2 seconds while moving, and once when target reached
6. `motors[i].run()` — generate step pulses for all motors

### `src/protocol.cpp`

Command dispatcher. Parses commands from the serial buffer and calls handlers:

| Command | Handler | Behavior |
|---------|---------|----------|
| `PING` | `handlePing()` | Responds `PONG` |
| `EN` | `handleEnable()` | No-op (protocol compat), responds `OK` |
| `DIS` | `handleDisable()` | No-op (protocol compat), responds `OK` |
| `MT <id> <steps>` | `handleMoveTo()` | Absolute position in steps. Rejected if not homed or outside soft limits |
| `GP` | `handleGetPositions()` | Responds `POS <s0> [s1 ...]` |
| `HOME <id>` | `handleHome()` | Starts homing. Response `HOMED <id>` sent asynchronously |
| `START` | `handleStart()` | Mark all joints as homed at their `start_position_steps`. Rejected if any motor is homing |
| `JOG <id> <speed>` | `handleJog()` | Velocity-mode jogging. Speed in steps/s (sign = direction). Clamped to per-joint `max_speed`. Requires homed. `JOG <id> 0` decelerates to stop |
| `STOP` | `handleStop()` | Emergency stop, decelerate all motors. Properly clears jog state for jogging motors |
| `RDPIN` | `handleReadPin()` | Shows limit switch pin state for all joints |
| `TEST [id]` | inline | Sends 200 manual step pulses on specified joint (default: J0, hardware debug) |
| `SCAN` | inline | Reads all digital pins 0–41 (pin identification debug) |

**Error codes:**

| Code | Constant | Meaning |
|------|----------|---------|
| 1 | `ERR_UNKNOWN_CMD` | Unrecognized command (prints received command for debug) |
| 2 | `ERR_BAD_ARGS` | Missing or invalid arguments |
| 3 | `ERR_MOTOR_BUSY` | Motor is homing or not yet homed |
| 4 | `ERR_INVALID_ID` | Motor ID out of range |

### `src/motor.cpp`

Motor initialization. Configures AccelStepper in `DRIVER` mode with 50µs minimum pulse width for MKS SERVO42C compatibility. Uses loop-based `motors_init()` reading from `JOINTS[]` config array. Includes step-level debug output every 2 seconds during movement.

### `src/homing.cpp`

Homing sequence implementation. All parameters read from `JOINTS[motor_id_]` config.

**Sequence:**
1. **APPROACH_FAST** — Move toward limit switch for up to one full revolution (128000 steps). If switch already triggered, skip to BACKOFF. On switch trigger: **instant stop** via `setCurrentPosition()` (no deceleration overshoot).
2. **BACKOFF** — Move away from switch by `backoff_steps` (800).
3. **APPROACH_SLOW** — Move toward switch for precision. On switch trigger: **instant stop** via `setCurrentPosition()`.
4. **SET_REFERENCE** — Set position to `home_offset_steps` (60444 steps = +170°).
5. **DONE** — Motor marked as homed. `MT` commands now accepted.

Uses `forceMoveTo()` to bypass the homing guard in `Motor::moveTo()`. Uses `setCurrentPosition()` instead of `stop()` for instant stop on limit trigger — prevents overshoot at high speeds.

**Debug output:** Prints state transitions via Serial (e.g., `DBG HOME approaching fast...`, `DBG HOME fast approach triggered, backing off`).

---

## Serial Protocol Reference

**Settings:** 115200 baud, 8N1, newline (`\n`) terminated.

### Commands

| Command | Format | Response | Notes |
|---------|--------|----------|-------|
| Ping | `PING` | `PONG` | Connection check |
| Enable | `EN` | `OK` | No-op (SERVO42C self-enables), kept for protocol compat |
| Disable | `DIS` | `OK` | No-op, kept for protocol compat |
| Move to | `MT <id> <steps>` | `OK` | Absolute position in steps. Rejected if not homed or jogging |
| Jog | `JOG <id> <speed>` | `OK` | Velocity jogging. Speed in steps/s, sign = direction. `JOG <id> 0` stops. Clamped to `max_speed` |
| Get positions | `GP` | `POS <s0> [s1 ...]` | Current step counts, space-separated |
| Home | `HOME <id>` | `HOMED <id>` | Asynchronous — response sent when homing completes |
| Start | `START` | `OK` | Skip homing — assume all joints at configured start pose |
| Stop | `STOP` | `OK` | Emergency stop, decelerate all motors |
| Read pins | `RDPIN` | `J0 pin=29 val=X ...` | Limit switch state for all joints |
| Test pulses | `TEST [id]` | `DBG TEST done...` | 200 manual step pulses on specified joint (default: 0) |
| Scan pins | `SCAN` | `0=X 1=X ... 41=X` | All digital pin states |
| (any error) | — | `ERR <code> <msg>` | See error codes above |

### Behavior During Homing

- `GP` — works normally, returns current position
- `MT` — returns `ERR 3 Motor is homing`
- `JOG` — returns `ERR 3 Motor is homing`
- `HOME` — returns `ERR 3 Already homing`
- `START` — returns `ERR 3 Motor is homing`
- `STOP` — stops all motors (including homing motor)

### JOG Command Details

`JOG <id> <speed>` enables velocity-mode jogging for real-time joystick control.

**How it works:**
1. Saves the motor's current `maxSpeed`
2. Sets `maxSpeed` to `|speed|`
3. Sets target to ±2,000,000,000 steps (effectively infinite) in the direction of `speed`
4. AccelStepper's `run()` handles smooth acceleration/deceleration
5. `JOG <id> 0` calls `stop()` to decelerate, then restores original `maxSpeed`
6. Jog state auto-clears in `run()` when deceleration completes

**Guards:**
- Rejected if motor is not homed (`ERR 3`)
- Rejected if motor is homing (`ERR 3`)
- Speed is clamped to per-joint `max_speed` (from `joints_config.h`)
- `MT` commands are rejected while jogging
- Hard/soft limit protection continues to work unchanged during jogging

### Hard Limit Protection

Outside of homing, the limit switch is monitored every loop iteration. The protection is **direction-aware**: if the switch is triggered while a motor is moving **toward** the switch (same direction as `home_dir`), the motor stops instantly (position set to current, no deceleration). Movement **away** from the switch is allowed — this is required to leave the switch position after homing. A debug message `DBG LIMIT HIT motor=X` is printed on stop.

### Software Position Limits

For joints with `limits.enabled = true` (J2, J3, J4, J5, J6), software limits are enforced in two places:

1. **Command rejection** (`handleMoveTo`) — `MT` commands targeting a position outside `[min_steps, max_steps]` are rejected with `ERR 2 Position outside soft limits`.
2. **Runtime monitoring** (`loop()`) — After homing, if a motor reaches or exceeds a soft limit boundary and is still moving further out of bounds, it is stopped instantly via `setCurrentPosition()`. Direction-aware: movement away from the exceeded limit is allowed. Prints `DBG SOFT_LIMIT motor=X`.

J2 soft limits: -39111 steps (-44°) to 80000 steps (+90°). The limit switch at -42° provides physical protection near the lower end; the +90° upper end has no physical stop, so the soft limit is the only protection.

J3 soft limits: -39556 steps (-89°) to 23111 steps (+52°). The limit switch at -89° provides physical protection near the lower end.

---

## Building and Flashing

### Prerequisites

- [PlatformIO](https://platformio.org/) (CLI or IDE)
- Teensy 4.1 connected via USB

### Using the project venv

A Python venv with PlatformIO is available in the firmware directory:

```bash
cd firmware/ar4_teensy
source .venv/bin/activate
```

### Build and Upload

```bash
cd firmware/ar4_teensy

# Build only
pio run

# Build and upload (close serial monitor first!)
pio run -t upload

# Open serial monitor
pio device monitor -b 115200
```

**Note:** The serial monitor must be closed before flashing. If the Teensy doesn't respond to upload, press the **program button** on the board.

---

## Testing (Standalone, No ROS2)

Open a serial monitor at 115200 baud and send commands manually:

```
# 1. Check connection
PING
→ PONG

# 2. Check limit switch wiring
RDPIN
→ J0 pin=29 val=0 open         (switch not pressed)
→ J0 pin=29 val=1 TRIGGERED    (switch pressed)

# 3. Test motor wiring (200 manual pulses)
TEST
→ DBG toggling step=6 dir=7
→ DBG TEST done, 200 pulses sent
→ (motor should visibly move)

# 4a. Option A: Home J1 via limit switch
HOME 0
→ DBG HOME start motor=0 limit_pin=29 pin_state=0
→ DBG HOME approaching fast...
→ (trigger switch) DBG HOME fast approach triggered, backing off
→ DBG HOME backoff done, approaching slow...
→ (trigger switch) DBG HOME slow approach triggered, setting reference
→ DBG HOME done, position set to 60444
→ HOMED 0

# 4b. Option B: Skip homing — manually position arm, then send START
#     Arm must be placed at the configured start pose (J1=0°, J2=73°)
START
→ OK

# 5. Check position (should be at home offset or start_position_steps)
GP
→ POS 60444

# 6. Move to 0° (center)
MT 0 0
→ OK
→ DBG motor=0 pos=58000    (every 2 seconds)
→ DBG motor=0 pos=55500
→ ...
→ DBG motor=0 REACHED pos=0

# 7. Jog J1 at 2000 steps/s (velocity mode)
JOG 0 2000
→ OK
→ (motor starts moving continuously)

# 8. Stop jog (decelerates)
JOG 0 0
→ OK

# 9. Stop all
STOP
→ OK
```

---

## Adding a New Joint

All 6 joints (J1–J6) are configured in the `JOINTS[]` array. To modify a joint's parameters, edit the corresponding entry in `joints_config.h`.

**Firmware motor indices:** 0=J1, 1=J2, 2=J3, 3=J4, 4=J5, 5=J6. The firmware doesn't know about ROS joint names — the URDF `motor_id` parameter maps ROS joints to firmware indices.

---

## Known Issues / TODO

- **Homing speeds not applied:** `speed_fast` and `speed_slow` in `JointHomingConfig` are defined but not yet used — homing runs at the motor's `max_speed`. Implement speed switching during homing phases.
- **J3 pins are placeholders:** Step=4, Dir=5 are marked PLACEHOLDER in `joints_config.h`. Set actual pins before wiring J3.
- **J5 calibration needed:** Offset, limits, and `steps_per_output_rev` are placeholders. Calibrate with real hardware.
- **J6 speeds are conservative:** max_speed=2000, accel=1000 — tune after testing with real hardware.
- **Debug output:** Verbose `DBG` serial messages are enabled. Consider adding a debug flag or removing before production.

---

## Related Documentation

- **Hardware Interface (ROS2 side):** `../ar4_hardware_interface/package_structure.md`
- **AR4 Description:** `../ar4_description/package_structure.md`
- **AR4 Bringup Launch:** `../manipulator_bringup/launch_files.md`
