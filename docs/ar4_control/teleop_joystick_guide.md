# DualShock 4 Joystick Teleop — Quick Start Guide

Step-by-step guide to control the AR4 arm with a DualShock 4 (CUH-ZCT2E) controller.

---

## Prerequisites

### 1. Install joy package

```bash
sudo apt install ros-jazzy-joy
```

### 2. Connect DualShock 4 via Bluetooth

1. On the DS4, hold **SHARE + PS** buttons until the light bar flashes rapidly (pairing mode)
2. On the PC, pair via Bluetooth settings or command line:
   ```bash
   bluetoothctl
   scan on
   # Wait for "Wireless Controller" to appear
   pair <MAC_ADDRESS>
   connect <MAC_ADDRESS>
   trust <MAC_ADDRESS>
   ```
3. Verify the controller appears:
   ```bash
   ls /dev/input/js0
   ```

### 3. Build the workspace

```bash
cd ~/manipulator_ros_control
source /opt/ros/jazzy/setup.bash
colcon build
```

### 4. Flash the firmware

Close any serial monitor, then:

```bash
cd ~/manipulator_ros_control/firmware/ar4_teensy
source .venv/bin/activate
pio run -t upload
```

---

## Launch

All commands assume you are in `~/manipulator_ros_control`.

### Terminal 1 — Hardware interface + controllers

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch manipulator_bringup ar4_bringup.launch.py
```

Add `rviz:=false` to skip RViz visualization.

Wait for the log line:
```
Activated (homed=false)
```

### Terminal 2 — Teleop node

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch ar4_control teleop_joy.launch.py
```

Wait for:
```
Teleop ready. Speed scale: 0.5. Press SHARE to START, OPTIONS to STOP.
Opened joystick: PS4 Controller.
```

### Terminal 3 — Mark arm as homed

Position the arm at its start pose, then:

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 service call /ar4_hardware/start std_srvs/srv/Trigger
```

Or simply press **SHARE** on the DS4 controller.

The arm is now ready — move the sticks.

---

## DS4 Controls

| Input | Action |
|-------|--------|
| Left stick X | J1 — base rotation |
| Left stick Y | J2 — shoulder |
| Right stick Y | J3 — elbow |
| Right stick X | J4 — forearm roll |
| L1 | J5 — negative direction |
| R1 | J5 — positive direction |
| Square | Go to all zeros (trajectory, 5 seconds) |
| Cross | Speed scale down (min 0.1) |
| Triangle | Speed scale up (max 1.0) |
| SHARE | START — mark all joints homed at start positions |
| OPTIONS | Emergency stop — all joints stop immediately |

**J6** is not mapped to any joystick input.

**Speed scale** starts at 0.5 (50% of max speed). Adjust with Cross/Triangle.

---

## Safety

- **Watchdog**: if the teleop node crashes or disconnects, all motors stop automatically within 200ms
- **Firmware limits**: hard and soft position limits are enforced regardless of joystick input
- **Speed clamping**: firmware clamps jog speed to each joint's configured `max_speed`
- **Deadzone**: 0.1 deadzone on analog sticks prevents accidental drift
- **Emergency stop**: press OPTIONS at any time to stop all joints instantly

---

## Troubleshooting

### Controller not detected

```bash
# Check if js0 exists
ls /dev/input/js*

# Check kernel sees the controller
cat /proc/bus/input/devices | grep -A 4 "Wireless Controller"
```

If not found, re-pair via Bluetooth.

### Sticks move but joints don't respond

1. Check that START was called (SHARE button or service call)
2. Check jog messages are flowing:
   ```bash
   ros2 topic echo /ar4_hardware/jog
   ```
3. Check hardware interface logs for errors

### Teensy did not respond to PING

Close any serial monitor — the serial port can only be used by one program at a time.

### Wrong button mapping

The button indices are for DS4 over Bluetooth (16 buttons, 6 axes). USB connection may have different indices. To detect the correct mapping:

```bash
ros2 topic echo /joy
# Press buttons one at a time and note which index changes
```

---

## Monitoring

```bash
# Watch jog velocities being published
ros2 topic echo /ar4_hardware/jog

# Watch raw joystick input
ros2 topic echo /joy

# Watch joint states (positions in radians)
ros2 topic echo /joint_states
```
