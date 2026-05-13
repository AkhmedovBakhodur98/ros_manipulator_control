# manipulator_hardware_interface Package Documentation

> **Status (2026-05-13): not implemented yet.** This document captures the design intent and planning notes from the EtherCAT stack research. Files referenced below do not exist yet — they are the planned layout.

## Overview

The `manipulator_hardware_interface` package will provide the EtherCAT hardware interface for the main manipulator (rail + selector + picker) and the SCARA arm, replacing the current Teensy-serial path used in `ar4_hardware_interface`. Drives are **StepperOnline A6-EC series servos** over EtherCAT (see [project motor upgrade memory](../../README.md) and [`scara_description`](../scara_description/package_structure.md) for the joint distribution).

**Key design choice:** we do **not** ship a custom `SystemInterface` C++ plugin. Instead we depend on the upstream [ICube-Robotics/ethercat_driver_ros2](https://github.com/ICube-Robotics/ethercat_driver_ros2) `EcCiA402Drive` plugin and provide the per-slave PDO configuration in YAML.

Reasons for not writing a C++ plugin:
- ICube's `EcCiA402Drive` is generic over CiA 402 servos and exposes mode-of-operation switching, DC sync and per-PDO entry mapping via YAML.
- The only A6-specific work needed is the PDO map (see [a6_pdo_mapping.md](a6_pdo_mapping.md)).
- A custom plugin would duplicate IgH lifecycle code already battle-tested upstream.

---

## Planned Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Controller Manager                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ manipulator_ec_hardware (ethercat_driver/EthercatDriver)│  │
│  │  ├── EcCiA402Drive slave 0 → Z axis (A6-750EC)        │  │
│  │  ├── EcCiA402Drive slave 1 → X axis (A6-750EC)        │  │
│  │  ├── EcCiA402Drive slave 2 → A axis (A6-750EC)        │  │
│  │  ├── EcCiA402Drive slave 3 → SCARA shoulder (A6-750EC) │  │
│  │  ├── EcCiA402Drive slave 4 → SCARA elbow   (A6-400EC) │  │
│  │  └── EcCiA402Drive slave 5 → SCARA wrist   (A6-200EC) │  │
│  └────────────────────────────┬───────────────────────────┘  │
└───────────────────────────────┼──────────────────────────────┘
                                │ EtherCAT (eno1, generic driver)
                                ▼
                       ┌─────────────────┐
                       │   IgH Master    │
                       │   (kernel mod)  │
                       └─────────────────┘
                                │
                                ▼ EtherCAT frames @ 1 kHz
                       [ A6 servo chain ]
```

The test bench is currently 2 slaves: 1× A6-750EC + 1× A6-200EC. Full chain is 6 slaves once the manipulator is integrated.

---

## Planned Package Layout

```
src/manipulator_hardware_interface/
├── CMakeLists.txt                       # ament_cmake
├── package.xml                          # depends on ethercat_driver, ros2_control
├── config/
│   ├── ethercat/
│   │   ├── a6_750ec_slave.yaml          # CiA 402 PDO map + DC for A6-750EC
│   │   ├── a6_400ec_slave.yaml          # CiA 402 PDO map + DC for A6-400EC
│   │   ├── a6_200ec_slave.yaml          # CiA 402 PDO map + DC for A6-200EC
│   │   └── master.yaml                  # EtherCAT master config (cycle_time, sync mode)
│   ├── manipulator_ros2_control.yaml    # ros2_control YAML for main manipulator joints
│   ├── scara_ros2_control.yaml          # ros2_control YAML for SCARA joints
│   └── controllers.yaml                 # controller_manager + JTC configuration
├── launch/
│   ├── ethercat_master.launch.py        # Brings up IgH master and ros2_control_node
│   └── diagnostics.launch.py            # ethercat slave state + jitter monitoring
├── udev/
│   └── 99-ethercat.rules                # eno1 permissions, optionally NIC rename
└── scripts/
    ├── irq_pinning.sh                   # Pins eno1 IRQ to isolated CPU at startup
    └── ethtool_tuning.sh                # NIC offload disables, coalescing tuning
```

The package will be `ament_cmake` (consistent with `ar4_hardware_interface`) even though it contains no C++ — this keeps install rules straightforward for the YAML and launch files.

---

## Joint → Slave Mapping (Planned)

| Slave # | Drive model | Robot | Joint | Notes |
|---------|-------------|-------|-------|-------|
| 0 | A6-750EC | manipulator | Z (vertical lift) | High inertia, long travel |
| 1 | A6-750EC | manipulator | X (linear rail) | High inertia, long travel |
| 2 | A6-750EC | manipulator | A (selector) | Medium |
| 3 | A6-750EC | SCARA | shoulder | Medium |
| 4 | A6-400EC | SCARA | elbow | Light |
| 5 | A6-200EC | SCARA | wrist | Lightest |

Exact bus order will be defined by physical daisy-chain order; we'll renumber here once the chain is laid out.

---

## Related Documentation

- [ethercat_setup.md](ethercat_setup.md) — IgH master install, NIC binding, slave discovery
- [rt_tuning.md](rt_tuning.md) — Real-time kernel tuning, IRQ pinning, NIC offload tuning
- [a6_pdo_mapping.md](a6_pdo_mapping.md) — A6-EC specific CiA 402 PDO map and scaling
- [known_issues.md](known_issues.md) — Known bugs in the upstream ICube driver and NIC compatibility notes
- [bringup.md](bringup.md) — Step-by-step bringup procedure (in progress)
- Upstream: [ICube-Robotics/ethercat_driver_ros2](https://github.com/ICube-Robotics/ethercat_driver_ros2)
- Existing analogue: [`ar4_hardware_interface/package_structure.md`](../ar4_hardware_interface/package_structure.md)
