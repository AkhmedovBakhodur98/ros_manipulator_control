# manipulator_hardware_interface Package Documentation

> **Status (2026-06-08): Stage 6 + 6.5 (IRQ-pin) + 6.6a closed on bench (10-min soak, 2 slaves); Stage 6.6b code in tree, hardware verify pending.** The `manipulator_hardware_interface` package ships the generic `a6_slave.yaml` (one PDO map for all A6N variants — 200EC / 400EC / 750EC share product code 0x00000715) and two controllers YAMLs: bench (single slave) and full (6 slaves). Stage 6.6b extended the slave YAML with `control_word` command_interface, `status_word` state_interface and an SDO init block for homing parameters (method 35 = current-pos-zero by default). The full URDF, JointTrajectoryController + helper `ForwardCommandController`s on `control_word` / `mode_of_operation`, homing action server, safety / limit monitor and a 4 h soak harness are all in tree. Next hardware step (operator-scheduled): connect all 6 drives, burn aliases 1..6 via `docs/.../system/ethercat-alias-program.sh`, run the soak test (`manipulator_diagnostics/launch/soak_test.launch.py`, 3-4 h sine motion on all 6 joints).

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

## Package Layout (current as of Stage 6.6b, 2026-06-08)

```
src/manipulator_hardware_interface/
├── CMakeLists.txt                            # ament_cmake (project NONE — no C++)
├── package.xml                               # exec_depend: ethercat_driver, ethercat_generic_cia402_drive, joint_state_broadcaster, joint_trajectory_controller, forward_command_controller
└── config/
    ├── ethercat/
    │   └── a6_slave.yaml                     # Generic A6N PDO/DC + SDO init (was a6_200ec_slave.yaml; ESI declares one product code for 200/400/750EC, one YAML drives all 6 drives). Variable 0x1600/0x1A00, AssignActivate=0x300, auto_fault_reset, control_word command_interface, status_word state_interface, sdo_config for homing (0x6098=35, 0x6099/609A bench-safe).
    ├── ethercat_bench_controllers.yaml       # Single-slave bench: 1000 Hz controller_manager + JSB + FPC (active) + bench JTC (inactive). Survives for regression Stage 6.6a-style probes.
    └── ethercat_full_controllers.yaml       # 6-slave full chain (Stage 6.6b): 1000 Hz controller_manager + JSB on 6 joints + manipulator_trajectory_controller (active) + control_word_controller + mode_of_operation_controller (inactive — activated by homing action server on demand).
```

The split between bench and full controllers YAMLs is deliberate: the bench config still drives a one-axis regression environment if we ever need to bisect a problem to a single drive without disassembling the production chain. The slave YAML is shared.

What is intentionally NOT here:

- **Per-variant slave YAMLs** (`a6_200ec_slave.yaml`, `a6_400ec_slave.yaml`, `a6_750ec_slave.yaml`) — ESI XML in [vendor/](vendor/) declares a single `<Type ProductCode="#x00000715">A6N Servo Driver</Type>` for the entire family. They share the object dictionary; one YAML suffices.
- **`config/ethercat/master.yaml`** — IgH master config lives at `/usr/local/etc/ethercat.conf`, managed by `ethercatctl` (Stage 2). There is no per-launch master YAML for ICube — the master is a system service, not a launch-time process.
- **`launch/`** — launch wiring lives in `manipulator_bringup/launch/` (`ethercat_bench.launch.py`, `ethercat_full.launch.py`) and `manipulator_diagnostics/launch/soak_test.launch.py`, not scattered into this package.
- **`udev/99-ethercat.rules`** — installed as a host config in Stage 2 (`/etc/udev/rules.d/99-ethercat.rules`), not packaged. See [bringup.md §Stage 2.8](bringup.md).

The package is `ament_cmake` (consistent with `ar4_hardware_interface`) even though it contains no C++ — this keeps install rules straightforward for the YAML files.

---

## Joint → Drive Mapping (Stage 6.6b, EEPROM aliases burned by `ethercat-alias-program.sh`)

| URDF joint | Robot | Model | Alias | Position-in-chain |
|------------|-------|-------|-------|-------------------|
| `base_main_frame_joint` | manipulator | A6-750EC | 1 | 0 |
| `main_frame_selector_frame_joint` | manipulator | A6-750EC | 2 | 1 |
| `selector_frame_picker_frame_joint` | manipulator | A6-750EC | 3 | 2 |
| `scara_shoulder_joint` | SCARA | A6-750EC | 4 | 3 |
| `scara_elbow_joint` | SCARA | A6-400EC | 5 | 4 |
| `scara_wrist_joint` | SCARA | A6-200EC | 6 | 5 |

The Y-jaws (`selector_left_container_jaw_joint`, `selector_right_container_jaw_joint`) are NOT actuated by EtherCAT — they appear in the geometric URDF for visualisation only.

The URDF (`manipulator_ethercat_full.urdf.xacro`) addresses drives by `alias` (with `position=0` placeholder), so once `ethercat-alias-program.sh` has burned the EEPROM aliases the physical cable order can be reshuffled without editing config.

---

## Related Documentation

- [bringup.md](bringup.md) — Step-by-step bringup procedure (Stages 1-6 + 6.5 IRQ-pin + 6.6a closed on bench; Stage 6.6b code in tree, hardware verify pending)
- [a6_dio_mapping.md](a6_dio_mapping.md) — A6-EC CN1 DI/DO pinout, `0x60FD` bit layout, drive-side overtravel behaviour
- `../../src/manipulator_description/urdf/manipulator/manipulator_ethercat_test.urdf.xacro` — single bench joint on EthercatDriver (Stage 6 regression environment)
- `../../src/manipulator_description/urdf/manipulator/manipulator_ethercat_full.urdf.xacro` — 6-joint full chain on EthercatDriver (Stage 6.6b, addressed by alias)
- `../../src/manipulator_bringup/launch/ethercat_bench.launch.py` — Single-slave bring-up
- `../../src/manipulator_bringup/launch/ethercat_full.launch.py` — Full 6-slave bring-up + homing action server + safety monitor
- `../../src/manipulator_diagnostics/launch/soak_test.launch.py` — 3-4 h soak test on top of `ethercat_full` (sine on all 6 joints + CSV metrics + auto-shutdown)
- `../../src/manipulator_msgs/` — `HomeJoints.action`, `OvertravelEvent.msg` (Stage 6.6b interfaces)
- `../../src/manipulator_homing/` — `homing_action_server` (CiA 402 mode 6 driver) + `safety_monitor` (lifts the JTC SUCCEEDED-while-clamped trap from Stage 6.6a)
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
