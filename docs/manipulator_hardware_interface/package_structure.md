# manipulator_hardware_interface Package Documentation

> **Status (2026-05-14): Stage 6 closed (10-min soak passed).** The `src/manipulator_hardware_interface/` package now exists — config-only (no C++), shipping the A6-200EC slave PDO YAML and the bench `controllers.yaml`. The bench A6-200EC is brought to OP under `ros2_control` via `manipulator_bringup/launch/ethercat_bench.launch.py`, FPC tracks target with 1-count error, and a 600-second steady-state soak under `chrt -f 80` + NIC-IRQ-on-CPU-1 logs **zero** EtherCAT kernel events and zero controller_manager overruns. **Stage 6.5** remains partially open: persist the IRQ pin across reboots (the `ethercat-irq-pin.service` recipe in [rt_tuning.md](rt_tuning.md) is documented but not yet installed on `grenka`), and optionally wrap the launch as a systemd unit so the user does not need to remember `chrt`.

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

## Package Layout (current as of Stage 6, 2026-05-14)

```
src/manipulator_hardware_interface/
├── CMakeLists.txt                            # ament_cmake (project NONE — no C++)
├── package.xml                               # exec_depend: ethercat_driver, ethercat_generic_cia402_drive, joint_state_broadcaster, joint_trajectory_controller, forward_command_controller
└── config/
    ├── ethercat/
    │   └── a6_200ec_slave.yaml               # 1:1 of csp_smoke PDO/DC (variable 0x1600/0x1A00 + 0x6060/0x6061 remap, AssignActivate=0x300, auto_fault_reset)
    └── ethercat_bench_controllers.yaml       # controller_manager 1000 Hz + joint_state_broadcaster + forward_position_controller (active) + bench_trajectory_controller (inactive)
```

What is intentionally NOT here yet (will arrive at later stages):

- **`config/ethercat/a6_400ec_slave.yaml` / `a6_750ec_slave.yaml`** — only the bench drive (200EC) is needed for Stage 6. The 750EC bench drive has no motor and stays in PREOP. Other slaves arrive at Stage 7 (full chain).
- **`config/ethercat/master.yaml`** — IgH master config lives at `/usr/local/etc/ethercat.conf`, managed by `ethercatctl` (Stage 2). There is no per-launch master YAML for ICube — the master is a system service, not a launch-time process.
- **`launch/`** — launch wiring lives in `manipulator_bringup/launch/ethercat_bench.launch.py` to colocate with the existing manipulator/AR4/SCARA launches, not to scatter launch files across packages.
- **`udev/99-ethercat.rules`** — installed as a host config in Stage 2 (`/etc/udev/rules.d/99-ethercat.rules`), not packaged. See [bringup.md §Stage 2.8](bringup.md).
- **`scripts/irq_pinning.sh` / `ethtool_tuning.sh`** — currently lives as documentation in [rt_tuning.md](rt_tuning.md). Stage 6.5 may promote them to systemd units.

The package is `ament_cmake` (consistent with `ar4_hardware_interface`) even though it contains no C++ — this keeps install rules straightforward for the YAML files.

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

- [bringup.md](bringup.md) — Step-by-step bringup procedure (Stages 1-6 closed on `grenka`; Stage 6.5 RT-tuning is the next step)
- `../manipulator_description/package_structure.md` — `manipulator_ethercat_test.urdf.xacro` macro (`bench_joint` on EthercatDriver)
- `../manipulator_bringup/package_structure.md` — `ethercat_bench.launch.py` Stage 6 launch
- [ethercat_setup.md](ethercat_setup.md) — IgH master install, kernel modules, systemd service, /dev/EtherCAT0 permissions
- [rt_tuning.md](rt_tuning.md) — Real-time kernel tuning, IRQ pinning, NIC offload tuning, userspace RT limits under GDM
- [a6_pdo_mapping.md](a6_pdo_mapping.md) — A6-EC specific CiA 402 PDO map, verified identity, operational parameters
- [known_issues.md](known_issues.md) — Patches we maintain for the ICube driver, GDM/PAM trap, A6 sync-error finding, etc.
- [system/](system/) — Vendored host-system configs (systemd defaults, PAM limits) — apply on any machine joining the stack
- [patches/](patches/) — Local patches on top of ICube `ethercat_driver_ros2` upstream
- [vendor/](vendor/) — StepperOnline ESI XML (reference only, not loaded at runtime by IgH 1.6)
- [`tools/csp_smoke/`](../../tools/csp_smoke/) — Standalone C reference of the full single-slave bring-up (no ROS), used in Stage 4 to validate the PDO map and DC config that Stage 6 will encode in YAML
- Upstream: [ICube-Robotics/ethercat_driver_ros2](https://github.com/ICube-Robotics/ethercat_driver_ros2) (pinned at HEAD `066b81a2` on the `jazzy` branch as of 2026-05-14)
- Existing analogue: [`ar4_hardware_interface/package_structure.md`](../ar4_hardware_interface/package_structure.md)
