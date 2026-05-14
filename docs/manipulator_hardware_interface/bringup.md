# Bringup Procedure

> **Status (2026-05-13): planning skeleton.** Nothing in this document is verified end-to-end — the dev machine has the RT kernel running but ROS 2 / IgH / `ethercat_driver_ros2` are not yet installed. This file will be filled in (and trimmed) as the test bench is brought up.

## Prerequisites Checklist

- [x] Hardware: 4× A6-750EC, 1× A6-400EC, 1× A6-200EC delivered
- [x] Dev machine `grenka`: Ryzen 7 3700X, Ubuntu 24.04.4 LTS, 16 GB
- [x] PREEMPT_RT kernel (`6.8.1-1048-realtime`) installed and booted
- [x] `eno1` (RTL8125) reserved for EtherCAT, WiFi for general internet
- [x] BIOS RT-tweaks applied (see [rt_tuning.md](rt_tuning.md))
- [x] GRUB RT flags applied
- [ ] ROS 2 Jazzy installed
- [ ] IgH master built and `ethercat.service` running
- [ ] `ethercat_driver_ros2` cloned and patched (`CLOCK_REALTIME` → `CLOCK_MONOTONIC`, see [known_issues.md](known_issues.md))
- [ ] Test bench connected: 1× A6-750EC + 1× A6-200EC daisy-chain
- [ ] Vendor ESI XML installed at `/etc/ethercat/esi/`

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

## Stage 4 — Single-Slave PDO Validation (No ROS)

Before pulling in ROS 2, verify the PDO map works at the IgH level with a tiny custom CSP program or the LinuxCNC reference HAL config. This isolates A6 EtherCAT issues from ROS-side problems.

1. Write a minimal C program based on `examples/dc_user/main.c` in the IgH source
2. Configure variable PDO mapping 0x1600 / 0x1A00 per [a6_pdo_mapping.md](a6_pdo_mapping.md)
3. Set Mode of Operation = 8 (CSP), drive CiA 402 state machine to Operation Enabled
4. Send a slow sine wave on Target Position
5. Verify Actual Position follows, no `TIMED OUT` / `UNMATCHED` warnings in dmesg over 10 min

**Exit criterion:** motor follows a position sine wave smoothly, zero following-error faults.

## Stage 5 — Build `ethercat_driver_ros2`

1. Clone Jazzy branch into `src/`
2. Apply the `CLOCK_MONOTONIC` patch (see [known_issues.md](known_issues.md))
3. `rosdep install` + `colcon build`
4. `source install/setup.bash`

**Exit criterion:** package builds; `ros2 pkg prefix ethercat_driver` resolves.

## Stage 6 — Single-Slave ROS Bringup

1. Write `config/ethercat/a6_750ec_slave.yaml` from [a6_pdo_mapping.md](a6_pdo_mapping.md) sketch
2. Write a minimal `config/ros2_control_test.yaml` exposing only one joint
3. Launch via `manipulator_hardware_interface/launch/ethercat_master.launch.py`
4. Check:

```bash
ros2 control list_hardware_components   # Should be active
ros2 topic echo /joint_states --once     # Should report current position
ethercat slaves                          # Slave in OP
```

5. Drive the joint with a `JointTrajectoryController` slow trajectory

**Exit criterion:** joint moves under ros2_control, no SafeOP drops over 10 min.

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
