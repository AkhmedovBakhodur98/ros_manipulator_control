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

## Stage 3 — Slave Discovery

1. Power up the test bench (2 slaves)
2. Plug the daisy-chain into `eno1`
3. Check:

```bash
ethercat slaves
# Expected:
# 0  0:0  PREOP  +  StepperOnline A6-750EC (or similar product string)
# 1  0:1  PREOP  +  StepperOnline A6-200EC
```

4. Read identification SDOs:

```bash
ethercat upload --type uint32 0x1018 1   # Vendor ID
ethercat upload --type uint32 0x1018 2   # Product Code
ethercat upload --type string 0x1008 0   # Device name
```

5. Cross-check against the ESI XML — these are the values that go into `vendor_id`/`product_id` of the slave YAML.

**Exit criterion:** both slaves visible in `PREOP`, vendor/product IDs match the ESI.

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
