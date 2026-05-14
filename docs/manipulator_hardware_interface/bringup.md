# Bringup Procedure

> **Status (2026-05-13): planning skeleton.** Nothing in this document is verified end-to-end — the dev machine has the RT kernel running but ROS 2 / IgH / `ethercat_driver_ros2` are not yet installed. This file will be filled in (and trimmed) as the test bench is brought up.

## Prerequisites Checklist

- [x] Hardware: 4× A6-750EC, 1× A6-400EC, 1× A6-200EC delivered
- [x] Dev machine `grenka`: Ryzen 7 3700X, Ubuntu 24.04.4 LTS, 16 GB
- [x] PREEMPT_RT kernel (`6.8.1-1048-realtime`) installed and booted
- [x] `eno1` (RTL8125) reserved for EtherCAT, WiFi for general internet
- [x] BIOS RT-tweaks applied (see [rt_tuning.md](rt_tuning.md))
- [x] GRUB RT flags applied
- [x] ROS 2 Jazzy installed (`ros-jazzy-desktop` + `ros-dev-tools` + `ros2_control` + `ros2_controllers`)
- [x] IgH master built and `ethercat.service` running (Stage 2)
- [x] `ethercat_driver_ros2` cloned and patched (Stage 5; patches in `patches/`)
- [x] Test bench connected: 1× A6-750EC + 1× A6-200EC daisy-chain (Stage 3)
- [x] Userspace RT limits raised (Stage 4; see [rt_tuning.md §Userspace RT Limits](rt_tuning.md))

## Stage 1 — System Tuning ✅ (closed 2026-05-13)

Follow [rt_tuning.md](rt_tuning.md):

1. BIOS: disable C-states, Cool'n'Quiet, **SMT**
2. GRUB flags: `isolcpus=1,2,3 nohz_full=1,2,3 rcu_nocbs=1,2,3 irqaffinity=0 processor.max_cstate=1 mitigations=off`
3. `update-grub` + reboot
4. Validate: `cyclictest` under `stress-ng` load, worst-case max latency < 100 µs

**Exit criterion:** worst-case latency ≤ 100 µs on isolated cores under load.

**Actual on `grenka` (60 s runs, see `/home/grenka/rt_logs/`):**

| Stage | Configuration | Idle max | Under-load max |
|---|---|---|---|
| Snapshot 1 | Stock RT kernel, SMT on, no tuning | 13 µs | 23 µs |
| Snapshot 2 | + BIOS SMT off / C-states off | 14 µs | 13 µs |
| Snapshot 3 (final) | + GRUB `isolcpus`/`nohz_full`/`rcu_nocbs`/`irqaffinity=0`/`max_cstate=1`/`mitigations=off`, cyclictest pinned to **CPU 1 (isolated)** | 6 µs | **7 µs** |

Final worst-case 7 µs is 14× below the 100 µs ceiling — generous headroom for IgH + ROS 2 jitter contributions to come.

## Stage 2 — EtherCAT Master Install ✅ (closed 2026-05-14 on `grenka`)

Follow [ethercat_setup.md](ethercat_setup.md). Sub-checklist with state on `grenka`:

- [x] **2.1 Build deps** — `autoconf libtool pkg-config` (build-essential was already installed).
- [x] **2.2 Clone IgH** — `git clone https://gitlab.com/etherlab.org/ethercat.git /opt/ethercat-src` (default branch is `stable-1.6`, current HEAD `b709e581 Version bump to 1.6.9`). `/opt/ethercat-src` is owned by `grenka:grenka` (post-`sudo mkdir` + `chown`) so configure/build run without sudo.
- [x] **2.3 Configure** — `./bootstrap && ./configure --prefix=/usr/local --enable-generic --disable-8139too --disable-eoe`. Confirmed kernel sources at `/usr/src/linux-headers-6.8.1-1048-realtime (Kernel 6.8)`, EoE off.
- [x] **2.4 Build** — `make -j$(nproc)` (userspace only) **then `make modules -j$(nproc)` separately** (kernel modules are NOT built by the default target — see [ethercat_setup.md](ethercat_setup.md) §1). Produced `master/ec_master.ko` and `devices/ec_generic.ko`.
- [x] **2.5 Install** — `sudo make modules_install install && sudo depmod` — modules into `/lib/modules/$(uname -r)/ethercat/`, `ethercat` tool into `/usr/local/bin/`, libs into `/usr/local/lib/`, systemd unit into `/lib/systemd/system/ethercat.service`.
- [x] **2.6 Master config** — wrote `/usr/local/etc/ethercat.conf` (NOT `/etc/ethercat.conf` — `ethercatctl` reads from prefix path) with `MASTER0_DEVICE="74:56:3c:30:04:57"`, `DEVICE_MODULES="generic"`, `UPDOWN_INTERFACES="eno1"`.
- [x] **2.7 Start service** — Secure Boot disabled in BIOS (`mokutil --sb-state` = `disabled`), then `sudo systemctl restart ethercat` → `active (exited)`, `lsmod` shows `ec_master` + `ec_generic`, `sudo ethercat master` → `Phase: Idle`, `Link: DOWN` (expected — slave not yet connected, that's Stage 3). See [known_issues.md §7](known_issues.md) for the long-term DKMS path that avoids disabling SB.
- [x] **2.8 User group** — IgH installer does **not** create the `ethercat` group or udev rule (see [known_issues.md §10](known_issues.md)). Manual: `groupadd -f ethercat`, `/etc/udev/rules.d/99-ethercat.rules` with `KERNEL=="EtherCAT[0-9]*", MODE="0660", GROUP="ethercat"`, `udevadm control --reload && udevadm trigger`, `usermod -aG ethercat $USER`, relogin. Verified: `groups | grep ethercat`, `/dev/EtherCAT0` → `root:ethercat 0660`, `/usr/local/bin/ethercat master` без sudo → `Phase: Idle`.

**Exit criterion met:** `ethercat master` reports `Phase: Idle`, kernel modules `ec_master` and `ec_generic` loaded, accessible to `grenka` без sudo.

**Note:** NIC tuning script + IRQ pin script (`ethtool -K eno1 ...`, `/proc/irq/<n>/smp_affinity` for the NIC IRQ) are tracked separately under [rt_tuning.md](rt_tuning.md) Stage 3-equivalent — they're NOT prerequisites to bringing the master to `IDLE`, only to keeping jitter low at runtime.

## Stage 3 — Slave Discovery ✅ (closed 2026-05-14 on `grenka`)

Bench topology (per [project-motor-upgrade](../../../ros_manipulator_control)): `eno1 → A6-200EC (alias 6, motor connected) → A6-750EC (alias 4, motor not connected — too heavy for the test bench)`.

1. ✅ Both drives powered, daisy-chain plugged into `eno1`.
2. ✅ `ethercat slaves` after bringing the chain up:

   ```
   0  6:0  PREOP  +  AS715N_sAxis_V0.10
   1  4:0  PREOP  +  AS715N_sAxis_V0.10
   ```

   Both in `PREOP`, flag `+` (no AL error). Note that the device-name string is the same — see Stage-3 finding below.

3. ✅ Identification SDOs read from both slaves (`ethercat upload -p {0,1} 0x1018 1..4`, `0x1008`, `0x1009`, `0x100A`). Full table is in [a6_pdo_mapping.md §Verified Identity](a6_pdo_mapping.md).

4. ✅ Cross-check vendor/product against ESI — *deferred*. We have hardware-authoritative IDs from the live drives (`0x00400000 / 0x00000715`). The ESI XML is more useful in Stage 4 to enumerate mappable PDO entries — will fetch then.

**Findings worth carrying forward:**

- **All A6-EC drives share Vendor+Product+Revision** (`0x00400000 / 0x00000715 / 0x00002ef8` SII). 200EC and 750EC on the bench were byte-identical at the EtherCAT identity layer. Disambiguate via **EEPROM alias** (bench: 200EC=6, 750EC=4) or chain position. ICube `ros2_control` YAML supports `alias:` — that's the path. See [a6_pdo_mapping.md §Verified Identity](a6_pdo_mapping.md).
- **Drive-side faults (e.g. `E202` "no encoder" when motor disconnected) do not block EtherCAT discovery.** The 750EC came up to PREOP cleanly while displaying `E202` on its seven-segment, because the ESC chip (LAN9252/AX58100-class) operates independently of the drive MCU's enable logic. Useful diagnostically: PREOP + AL-flag clean = the EtherCAT stack on the drive is healthy, even if the drive is refusing to enable due to a motor-side condition.
- **No `Enable SDO Info`** on this firmware — `ethercat sdos` cannot enumerate the object dictionary. We have to know SDO indices in advance (CiA 402 standard + manual).

**Exit criterion met:** both slaves visible in `PREOP`, vendor/product IDs captured and recorded.

## Stage 4 — Single-Slave PDO Validation (No ROS) ✅ (closed 2026-05-14 on `grenka`)

Verifies the PDO map works at the IgH level with a tiny custom CSP program — isolates A6 EtherCAT issues from ROS-side problems before pulling in ROS 2.

Implementation: [tools/csp_smoke/csp_smoke.c](../../tools/csp_smoke/csp_smoke.c) (~250 LOC, single-slave, targets A6-200EC at alias 6).

- [x] **4.1 RT-limits for userspace** — see [rt_tuning.md §Userspace RT limits](rt_tuning.md). On Ubuntu 24.04 + GDM, `pam_limits.so` is not enough — `gnome-terminal-server` inherits from `systemd --user`, which never goes through PAM. Use `DefaultLimitRTPRIO`/`DefaultLimitMEMLOCK` in `/etc/systemd/system.conf.d/`. After reboot: `ulimit -r=95`, `ulimit -l=unlimited`.
- [x] **4.2 Build** — `cd tools/csp_smoke && make`. Builds against `/usr/local/include/ecrt.h`, links `-lethercat`. Zero warnings.
- [x] **4.3 PDO map** — variable `0x1600` (ControlWord 0x6040, Target Position 0x607A, Mode of Operation 0x6060) and `0x1A00` (StatusWord 0x6041, Position Actual 0x6064, Mode Display 0x6061, Velocity Actual 0x606C). DC `AssignActivate=0x300` from ESI, SYNC0 cycle 1 ms, shift 0.
- [x] **4.4 RT-thread** — `mlockall`, `sched_setaffinity` to CPU 1 (isolated), `SCHED_FIFO` priority **80** (NOT max — 99 is reserved for kernel watchdog/migration threads).
- [x] **4.5 Run** — `timeout --signal=INT 15s ./csp_smoke`. CiA 402 transitions observed: `NotReady → SwitchOnDisabled → ReadyToSwitchOn → SwitchedOn → OperationEnabled`. Fault Reset (CW=0x0080) also tested when a leftover fault from a prior run was present — state machine handled it cleanly.
- [x] **4.6 Motion** — sine wave ±5000 counts @ 0.2 Hz (~14° of motor shaft) on Target Position. Actual Position follows with lag ~50–100 counts.
- [x] **4.7 Kernel log clean during steady state** — `journalctl -k --since` shows `Domain 0: Working counter changed to 3/3` once at start, then **zero** `TIMED OUT` / `UNMATCHED` / `SKIPPED` warnings over the entire 10 s of cyclic operation. (Pre-OP transition phase produces some UNMATCHED — expected, slaves not yet exchanging full process data.)

**Exit criterion met:** motor followed the sine smoothly, no following-error faults, kernel log clean in steady state.

## Stage 5 — Build `ethercat_driver_ros2` ✅ (closed 2026-05-14 on `grenka`)

ROS 2 Jazzy installed (`ros-jazzy-desktop` + `ros-dev-tools` + `ros-jazzy-ros2-control` + `ros-jazzy-ros2-controllers` + `python3-colcon-common-extensions` + `python3-rosdep`). `rosdep init && rosdep update` done.

Sub-checklist:

- [x] **5.1 Clone** — `git clone --branch jazzy --depth 1 https://github.com/ICube-Robotics/ethercat_driver_ros2.git src/ethercat_driver_ros2`. Pinned upstream HEAD `066b81a2f54a230af3f54160be41aa53657073e0`.
- [x] **5.2 Patches** — applied locally, recorded in [patches/ethercat_driver_ros2-icube.patch](patches/ethercat_driver_ros2-icube.patch):
  - **CLOCK_MONOTONIC** in `ec_master.cpp:312` and `:375` (see [known_issues.md §1](known_issues.md)).
  - **ETHERLAB_DIR as CACHE PATH** in `ethercat_interface/CMakeLists.txt:21` and `ethercat_manager/CMakeLists.txt:15` (see [known_issues.md §16](known_issues.md)). Without this, `-DETHERLAB_DIR` is silently ignored and downstream packages fail to configure.
- [x] **5.3 rosdep deps** — `rosdep install --from-paths src/ethercat_driver_ros2 --ignore-src --rosdistro jazzy --simulate` returns empty; everything is satisfied by `ros-jazzy-desktop` + `ros2-control` + `ros2-controllers`.
- [x] **5.4 colcon build** — `source /opt/ros/jazzy/setup.bash && colcon build --packages-up-to ethercat_driver_ros2 ethercat_generic_cia402_drive ethercat_manager --cmake-args -DETHERLAB_DIR=/usr/local`. All 7 packages finish (`ethercat_driver`, `ethercat_driver_ros2`, `ethercat_generic_cia402_drive`, `ethercat_generic_slave`, `ethercat_interface`, `ethercat_manager`, `ethercat_msgs`).
- [x] **5.5 Linkage verified** — `ldd install/ethercat_generic_cia402_drive/lib/libethercat_generic_cia402_drive_plugin.so` shows `libethercat_interface.so → install/...` and `libethercat.so.1 → /usr/local/lib/libethercat.so.1` (our Stage 2 IgH).
- [x] **5.6 ros2 pkg prefix resolves** for all four meaningful packages (`ethercat_driver`, `ethercat_driver_ros2`, `ethercat_generic_cia402_drive`, `ethercat_manager`).

**Exit criterion met:** all packages build, link against `/usr/local/lib/libethercat.so.1`, and `ros2 pkg prefix ethercat_driver` resolves.

## Stage 6 — Single-Slave ROS Bringup ✅ closed (2026-05-14 on `grenka`)

**What landed (2026-05-14):**

- New package `manipulator_hardware_interface` (ament_cmake, no C++) with:
  - `config/ethercat/a6_200ec_slave.yaml` — 1:1 translation of csp_smoke PDO/DC config (variable 0x1600/0x1A00 with explicit 0x6060/0x6061 remap, AssignActivate=0x300, `auto_fault_reset: true` so a stale `0x603F=0x8700` from a prior run does not block first OperationEnabled).
  - `config/ethercat_bench_controllers.yaml` — `controller_manager` at 1000 Hz, `joint_state_broadcaster`, `forward_position_controller` (active), `bench_trajectory_controller` (inactive).
- New xacro in `manipulator_description/urdf/manipulator/manipulator_ethercat_test.urdf.xacro` (macro `manipulator_ethercat_bench`) — one `bench_joint` paired with a tiny `world → bench_link` tree, `<ros2_control>` block with `EthercatDriver` + `EcCiA402Drive` (alias 6, position 0, mode 8 / CSP). `bench_joint` MUST exist as a geometric `<joint>` in the URDF — `ros2_control_node` aborts with `Joint 'bench_joint' not found in URDF` if you try to declare it only inside `<ros2_control>`.
- `robot.urdf.xacro` gained a `hardware:=mock|ethercat_bench` arg + `slave_config_dir:=...` arg; mock branch is unchanged. `slave_config_dir` is supplied at launch time (avoids `manipulator_description` reverse-depending on `manipulator_hardware_interface`).
- New launch in `manipulator_bringup/launch/ethercat_bench.launch.py` (a thin one-component launch — does NOT pull in the production action-server zoo from `manipulator_bringup.launch.py`).

**Functional verification (2026-05-14):**

| Check | Result |
|---|---|
| `ros2 control list_hardware_components` | `manipulator_ec_bench` `state=active`, read/write 1000 Hz |
| `ros2 control list_controllers` | `joint_state_broadcaster` active, `forward_position_controller` active, `bench_trajectory_controller` inactive |
| `ethercat slaves` | A6-200EC alias 6 → **OP** (A6-750EC alias 4 stays PREOP — not in our YAML, master ignores it) |
| `/joint_states` | bench_joint position publishes at 100 Hz from `joint_state_broadcaster` |
| FPC command (target = current + 30000 counts ≈ 0.23 motor rev) | Actual position arrived at target with **1 count** following error — CSP tracking nominal |

**Exit criterion verification (10-minute soak, 2026-05-14):**

| Phase | Window | Working counter | UNMATCHED | SKIPPED | TIMED OUT | ros2_control overruns |
|---|---|---|---|---|---|---|
| Baseline (no RT tuning) | ~10 s steady-state | ~10–30 / s | ~10–25 / s | ~3–8 / s | occasional | 0 |
| `chrt -f 80` only | 44 s steady-state | 4 | 3 | 3 | **1** | 0 |
| `chrt -f 80` + IRQ pin to CPU 1 | 60 s idle + 15 s active (5 FPC steps) | 0 | 0 | 0 | 0 | 0 |
| **`chrt -f 80` + IRQ pin to CPU 1** | **600 s idle (exit criterion soak)** | **0** | **0** | **0** | **0** | **0** |

Slave finished the 10-minute soak still in **OP**. FPC tracking error stayed at ≤ 1 count throughout the active phase (target 167130 → actual 167129).

**Bring-up recipe (post-Stage 6):**

```bash
# One-time per boot (or via systemd-unit; see Stage 6.5 below):
sudo bash -c 'echo 2 > /proc/irq/56/smp_affinity'   # NIC IRQ → CPU 1 (isolated)

# Launch:
chrt -f 80 ros2 launch manipulator_bringup ethercat_bench.launch.py
```

`chrt -f 80` raises the SCHED_FIFO priority of the `ros2_control_node` worker from the controller_manager default of 50; the system limit is 95 (set by `system.conf.d/99-ethercat-rt.conf` from Stage 4). `taskset -c 1` was tried but **made things worse** — pinning the whole process tree to CPU 1 forced ROS callbacks to compete with the RT thread on the same core, producing 2–4 ms PDO read times and overruns. Letting the scheduler keep ROS callbacks on CPU 0 (NIC IRQ co-located with the RT-thread cache on CPU 1 is what matters) is the right shape.

## Stage 6.6a — Endstops on 200EC ✅ closed (2026-05-14)

Extends the bench slave map with the digital-input word so application code can see the limit-switch state, and confirms that the drive enforces overtravel autonomously without our ros2_control loop.

**Changes (single commit):**

- `config/ethercat/a6_200ec_slave.yaml` — TPDO 0x1A00 gains one entry: `{index: 0x60FD, sub_index: 0, type: uint32, state_interface: digital_inputs}`. No SDO writes — factory DI function mapping (DI1=P-OT, DI2=N-OT, DI3=Home, DI4=Probe2, DI5=Probe1) is already what we want; vendor `0x2003` group is left at defaults.
- `manipulator_description/urdf/manipulator/manipulator_ethercat_test.urdf.xacro` — `bench_joint` gets a 4th state_interface `digital_inputs`. ICube's generic plugin propagates it to `/dynamic_joint_states`.

**Verified on bench:**

| Test | Result |
|---|---|
| `bench_joint/digital_inputs` appears in `ros2 control list_hardware_interfaces` | ✅ |
| `/dynamic_joint_states` carries `digital_inputs` value alongside position/velocity | ✅ |
| P-OT pressed → `0x60FD = 0x00010002` (CiA bit 1 + raw DI1 bit 16) | ✅ |
| N-OT pressed → `0x60FD = 0x00020001` (CiA bit 0 + raw DI2 bit 17) | ✅ |
| With P-OT held, FPC target = current + 20000 (forward) → position does not advance | ✅ — drive self-clamps |
| StatusWord `0x6041` bit 11 ("Internal limit active") = 1 during the hold | ✅ |

Drive latched `0x603F = 0x5443` (vendor alarm code, decoding deferred to Chapter 10.1.3 of the manual; not blocking — drive stayed in OperationEnabled).

The full DI/DO map and bit semantics are in [a6_dio_mapping.md](a6_dio_mapping.md). Manual is vendored at [`vendor/A6-EC_series_servo_drive_manual.pdf`](vendor/A6-EC_series_servo_drive_manual.pdf).

**Stage 6.6b (deferred)** — write a homing action server that switches `mode_of_operation` to 6, drives ControlWord bit 4 rising edge, polls StatusWord bit 12 for completion, then switches back to CSP. Will use CiA 402 homing method 1 (search N-OT then nearest Z) or 2 (search P-OT then Z) — see [a6_pdo_mapping.md §CiA 402 State Machine](a6_pdo_mapping.md) and the Homing parameters table in [a6_dio_mapping.md](a6_dio_mapping.md). Speeds (`0x6099:01/02`) must be cut from the factory ~6400/640 rpm defaults to bench-safe values (~50000/5000 counts/s).

## Stage 6.5 — RT-tuning persistence ✅ IRQ-pin closed (2026-05-14); launch wrapper / thread_priority deferred

Stage 6 verified the recipe works in a one-off shell; Stage 6.5 makes it survive a reboot.

**IRQ pin — closed:** `ethercat-irq-pin.service` ([system/ethercat-irq-pin.service](system/ethercat-irq-pin.service)) runs [`/usr/local/sbin/ethercat-irq-pin.sh`](system/ethercat-irq-pin.sh) once after `ethercat.service`, walks every eno1 IRQ in `/proc/interrupts` and writes `2` to its `smp_affinity`. Installed and enabled on `grenka` 2026-05-14 — `systemctl status` reports `active (exited)`, journal logs `pinned IRQ 56 → CPU 1 (effective: 00000002)`. The script is per-IRQ so it survives any future NIC driver change that adds rx/tx queues with their own IRQs. Reboot verification still pending (the box is in continuous use), but the unit is `WantedBy=multi-user.target` and `enabled` so first reboot after this lands closes that loop.

**Deferred to Stage 7+ (decide if/when needed):**

1. **Wrap the launch in a systemd unit** (`manipulator-ec-bench.service`) with `CPUSchedulingPolicy=fifo`, `CPUSchedulingPriority=80`, `LimitRTPRIO=95`, `LimitMEMLOCK=infinity`. Removes the need to remember `chrt` and gives a clean `journalctl -u` path. Cosmetic for dev work; matters more once the chain becomes a production setup.
2. **`controller_manager` ROS parameter `thread_priority`** — if it actually overrides the SCHED_FIFO 50 default, we drop the `chrt` wrapper entirely. Untested in our setup; not blocking.
3. **NIC offload tuning** (`ethtool -K eno1 gso off gro off ...`, link speed lock) — recipe already in [rt_tuning.md §NIC Tuning](rt_tuning.md). Stage 6 exit criterion passed *without* it on a 2-slave bus, so deferred until Stage 7 multi-slave shows whether it's actually needed.

## Stage 7 — Full Chain Bringup

After successful single-slave validation:

1. Connect all 6 slaves in the production daisy-chain order
2. Add YAML configs for A6-400EC and A6-200EC
3. Add ros2_control YAML for full manipulator + SCARA joint set
4. Bring up; validate joint-by-joint with low-amplitude motion

**Exit criterion:** all 6 joints respond, jitter monitoring is clean, no overruns in 1h continuous operation.

## Stage 8 — Integration with Existing Stack

1. Reconcile with `manipulator_description` URDF — joint names, limits
2. Hook into `manipulator_bringup` launch files
3. Sunset the Teensy-based path for production manipulator (AR4 keeps its Teensy interface — that arm is unaffected)

---

## Anti-Goals

- Do NOT attempt SOEM as plan B until plan A (IgH + generic) is empirically broken (see [known_issues.md](known_issues.md), section 4).
- Do NOT try the `igc` driver for I225/I226 NICs — broken in upstream IgH as of May 2026.
- Do NOT chase cycle times < 1 ms before all of the above is stable at 1 ms.
