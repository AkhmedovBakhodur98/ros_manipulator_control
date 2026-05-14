# Known Issues and Workarounds

> Issues discovered during the EtherCAT stack survey (2026-05-13). All come from upstream GitHub issues and LinuxCNC community threads — verify with `grep` against the actual checked-out source before applying.

## 1. `CLOCK_REALTIME` in DC sync (bug in ICube driver)

**Severity:** high — silent failure under NTP clock adjustments.

In the ICube `ethercat_driver_ros2` source, the DC reference time is set from `CLOCK_REALTIME`:

```cpp
clock_gettime(CLOCK_REALTIME, &t);
ecrt_master_application_time(master_, EC_NEWTIMEVAL2NANO(t));
ecrt_master_sync_reference_clock(master_);
ecrt_master_sync_slave_clocks(master_);
```

`CLOCK_REALTIME` can jump backwards/forwards when NTP synchronizes the wall clock. When that happens DC sync between slaves breaks and slaves drop to SafeOP with `WorkingCounter = 0` after running cleanly for ~1 hour.

**The upstream IgH example (`examples/dc_user/main.c`) uses `CLOCK_MONOTONIC`** — that is the correct clock for a monotonic cyclic application time base.

**Fix (planned, one-line):**

```diff
-clock_gettime(CLOCK_REALTIME, &t);
+clock_gettime(CLOCK_MONOTONIC, &t);
```

This must be applied to the cloned `ethercat_driver_ros2` source after `git clone`. We will track this in our overlay/patch directory once the package is created.

**Reference:** [issue #101 comment from 2024-03-07](https://github.com/ICube-Robotics/ethercat_driver_ros2/issues/101) — the original reporter found this after extensive jitter investigation.

## 2. Issue #101 — Cycle-time jitter and architecture

**Severity:** lower than first feared.

`ethercat_driver_ros2` runs the EtherCAT cyclic send/receive inside the `ros2_control` `update()` thread, not in a dedicated RT thread. The community proposed decoupling them to a separate RT thread (similar to SOEM / SimpleECAT design). The patch was never written — issue has been open since 2024-01 with no PR.

**Why this is less scary than it sounds:** the original reporter's empirical numbers on a tuned PREEMPT_RT box (Intel I210 NIC + generic driver, 4 motors @ 1 kHz):

| Metric | Avg | Max |
|---|---|---|
| Read trigger jitter | 1 µs | 116 µs |
| Write trigger jitter | 5 µs | 503 µs |
| Frame release (on wire) | 1.000 ms | 2.024 ms |
| Frame overruns | 1 / 1,000,000 | — |

At our planned 1 ms cycle, a worst-case 503 µs jitter is well inside the budget (slaves with DC tolerate it because the SYNC0 fires from the slave's own clock). One overrun per million cycles is acceptable — controllers can ride through a single skipped target.

**Mitigations we will apply:**

- Run with isolated CPUs and pinned IRQs (see [rt_tuning.md](rt_tuning.md)) — this is what the reporter did to reach the numbers above.
- Keep the controller computation inside `update()` light. Heavy IK / MPC should NOT live in the controller_manager thread on a single-thread driver.
- If we later need sub-1ms cycles or run heavier controllers, fork ICube and implement the two-thread architecture.

## 3. RTL8125 has no native IgH driver

**Severity:** medium — we already know we're on generic.

The IgH upstream device matrix (<https://docs.etherlab.org/ethercat/1.5/doxygen/devicedrivers.html>) does not include the Realtek RTL8125 (2.5GbE). Our `eno1` will run via the `generic` IgH driver, which uses the standard kernel NIC driver and gives up some determinism in exchange.

Recent issue #101 comments (2026-05-04 / -06) show that even **Intel I225 / I226** with the native `igc` driver doesn't work out of the box — at least one user reported the NIC interface vanishing from `ip a` after MAC binding. The reporter himself stayed on generic. So:

- **Plan A:** stay on generic + careful RT tuning. Empirically usable up to 1 kHz on similar hardware.
- **Plan B (fallback):** add an Intel I210 (~$30 PCIe NIC) — known-good native driver path.
- **Plan C (do not pick):** Intel I225/I226 — native driver is broken in upstream IgH as of May 2026.

## 4. SOEM-based ROS 2 drivers are not generic

If we ever need to fall back to SOEM (e.g., generic IgH driver proves unstable), the only living ROS 2 SOEM integration is [`synapticon_ros2_control`](https://github.com/synapticon/synapticon_ros2_control). It's hardcoded to the Synapticon SOMANET drive — porting it to A6-EC means rewriting PDO map and SDO initialization. Budget several weeks if this path is chosen. The existing ICube YAML config for A6 (once written) is **not** reusable for the Synapticon driver.

## 5. No published ROS 2 deployment of A6-EC exists

As of 2026-05, public ROS 2 + A6 deployments do not exist. All deployment experience is on **LinuxCNC**. Key findings we have inherited:

- The default fixed PDO group 0x1701/0x1B01 fails — see [a6_pdo_mapping.md](a6_pdo_mapping.md).
- `target-velocity` (0x60FF) is `INT32`, not `UINT32`.
- StepperOnline only publishes a TwinCAT/Beckhoff tutorial — no IgH / LinuxCNC / ROS material from the vendor.

LinuxCNC threads we rely on:

- <https://forum.linuxcnc.org/ethercat/54965-stepperonline-a6-servo>
- <https://forum.linuxcnc.org/ethercat/57091-stepperonline-a6-1000ec-driver>
- <https://forum.linuxcnc.org/ethercat/58666-sanitycheck-my-plan-ethercat-stepperonline-a6>

## 7. Secure Boot blocks locally built kernel modules

**Severity:** medium — hard stop on first `systemctl start ethercat`, easy fix.

Stock Ubuntu 24.04 ships with Secure Boot enabled (`mokutil --sb-state`) and `/sys/kernel/security/lockdown` = `integrity`. Any locally built, unsigned `.ko` is refused by the kernel:

```
modprobe: ERROR: could not insert 'ec_master': Key was rejected by service
```

This is `ENOKEY` from `mod_verify_sig` — it does not log a stack trace, just the modprobe error above. The Canonical RT kernel itself is signed and still loads; only our `ec_master.ko` / `ec_generic.ko` are blocked.

**Options:**

1. **Disable Secure Boot in BIOS** — what we did on `grenka` for the dev box. Fast, but the production stand should pick option 2 or 3.
2. **Sign modules with MOK** — generate a Machine Owner Key, register it via `sudo mokutil --import MOK.der` (the shim prompts for a password and asks for confirmation in the MOK Manager screen on next boot), then sign each module with `kmodsign sha512 MOK.key MOK.der path/to/ec_master.ko`. Must be redone on every rebuild.
3. **Wrap IgH in DKMS** — write a `dkms.conf` for the IgH source tree so DKMS auto-rebuilds and auto-signs (with MOK) when the kernel updates. IgH is not packaged for DKMS upstream — this is ~1–2 hours of setup but pays for itself on a long-lived rig.

For the dev box, option 1 is acceptable. Once the test bench moves toward production, revisit and pick 2 or 3.

## 8. Default `make` target does not build kernel modules

**Severity:** low — confusing, not dangerous.

In the IgH source tree, `make` builds only userspace (`tool/ethercat`, `libethercat`). Kernel modules `ec_master.ko` / `ec_generic.ko` need a separate `make modules` target. The `make install` step calls `make modules_install` internally, so if you skip `make modules`, install will silently succeed installing zero modules and `lsmod | grep ec_` will return empty on first start.

Always run **both** `make` and `make modules` before `sudo make modules_install install`.

## 9. `ethercatctl` reads `${prefix}/etc/ethercat.conf`, not `/etc/ethercat.conf`

**Severity:** low — wasted ~10 minutes on `grenka`.

With `./configure --prefix=/usr/local`, the config path is `/usr/local/etc/ethercat.conf`. Editing `/etc/ethercat.conf` (the Linux convention) does nothing — `ethercatctl` reads from the prefix path and reports:

```
ERROR: No network cards for EtherCAT specified.
Please edit /usr/local/etc/ethercat.conf with root permissions...
```

The path is hardcoded in `ethercatctl` at install time (substituted from `@sysconfdir@`). Either write to the prefix path, or pass `-c /etc/ethercat.conf` via a service override.

## 10. `make install` does not create the `ethercat` group or udev rule

**Severity:** low — easy fix, but blocks non-root access until you notice.

After `sudo make modules_install install` the device node appears as `crw------- root root /dev/EtherCAT0`. The IgH installer does **not**:

- create the `ethercat` group,
- install a udev rule that hands the node to that group.

Result: only `sudo ethercat master` works, and any ROS 2 hardware_interface process must run as root — unacceptable for `ros2_control`.

**Fix (one-time, per host):**

```bash
sudo groupadd -f ethercat
sudo tee /etc/udev/rules.d/99-ethercat.rules >/dev/null <<'EOF'
KERNEL=="EtherCAT[0-9]*", MODE="0660", GROUP="ethercat"
EOF
sudo udevadm control --reload
sudo udevadm trigger
sudo usermod -aG ethercat "$USER"
# relogin (or `newgrp ethercat`) for group membership to take effect
```

Verify: `ls -l /dev/EtherCAT0` → `crw-rw---- root ethercat`, then `/usr/local/bin/ethercat master` without `sudo` should print `Phase: Idle`.

## 12. All A6-EC drives share Vendor + Product + Revision

**Severity:** medium — silent footgun if you bind axes by identity.

Verified on bench 2026-05-14: A6-200EC and A6-750EC return **identical** `0x1018:01..03`:

| | A6-200EC | A6-750EC |
|---|---|---|
| Vendor ID | `0x00400000` | `0x00400000` |
| Product Code | `0x00000715` | `0x00000715` |
| Revision (SDO `0x1018:03`) | `0x00005612` | `0x00005612` |
| Revision (SII) | `0x00002ef8` | `0x00002ef8` |
| Device Name (`0x1008`) | `AS715N-DRIVER` | `AS715N-DRIVER` |

Wattage (200 / 400 / 750 W) is mechanical/electrical, not encoded in the EtherCAT identity. **Do not rely on `vendor_id`+`product_id` to attach the right joint to the right drive** — the master will accept the first physical slave in the chain even if you wired them in the wrong order.

**Mitigation:** assign a unique **alias** in EEPROM for each drive and reference it in the `ros2_control` slave YAML.

```bash
# Persist alias 4 to slave currently at chain position 1:
sudo ethercat alias --alias 4 -p 1
sudo ethercat alias -p 1   # read back
# Power-cycle the drive; aliases are picked up at EtherCAT start-up.
```

On our bench: A6-200EC = alias `6`, A6-750EC = alias `4`. Production deployment must follow the same convention (per-axis alias map will live alongside the slave YAML).

## 13. Drive-side faults do not block EtherCAT discovery

**Severity:** low — *informational*, useful diagnostically.

When the A6-750EC came up on the bench without a motor connected, its seven-segment displayed `E202` ("encoder communication / no encoder"). Despite this, the slave reached `PREOP` cleanly, returned all standard CiA 301 SDOs, and stayed there indefinitely. The reason is structural: the ESC chip (LAN9252-class) runs its own state machine for EtherCAT init and only later hands off to the drive MCU for OP-mode work. Drive-side faults that block enable do not block PREOP.

**Use this for bring-up diagnostics:**

- Slave in `PREOP` + flag `+` (no AL error) → EtherCAT stack on the drive is healthy. Any "the drive won't enable" symptom is on the drive/motor side, not on EtherCAT.
- Slave missing from `ethercat slaves` or stuck in `INIT` → that *is* an EtherCAT-level problem (wiring, alias collision, mailbox config, etc.).

This separation will save time in Stage 4+ when we start chasing OP-state issues — check the EtherCAT layer is clean before debugging the CiA 402 state machine.

## 15. Momentary `WC=0/3` events under external load (A6-EC, 1 ms cycle)

**Severity:** low for single-axis smoke, **medium for multi-axis bring-up under disturbance**.

Observed in Stage 4 smoke (2026-05-14) on A6-200EC at alias 6, csp_smoke driving sine ±50000 counts @ 0.5 Hz, RT-loop on isolated CPU 1 at SCHED_FIFO 80:

- Operator manually loaded the pulley by hand during the cyclic phase.
- Drive **stayed in OperationEnabled** (`StatusWord = 0x1637`) the entire 24 s of operation — no application-visible fault, no following-error trip (`0x6065` window is 429,483 counts = ~3.3 rev, `0x6072` torque limit at 300 % rated).
- Kernel log (`journalctl -k`) caught **three brief `Working counter changed to 0/3` events**, each recovering to `3/3` within ~1 s. Each correlated with operator touching the pulley.
- After teardown, drive `0x603F` (ErrorCode) was latched at `0x8700` "Sync error" (CiA 402 standard code). The latch survives until the next Fault Reset.

**Hypothesis:** under sudden external load, the drive MCU spends more cycles in current-loop / commutation work and occasionally misses the EtherCAT cyclic-data deadline within the SYNC0 window. Master sees zero responding slaves for that one cycle, then the slave recovers on the next. The skipped cycle is logged by the drive as a sync error and latched in `0x603F`, but the drive does not transition to Fault — it keeps tracking.

The 0x8700 we read *after* the test ended is **not necessarily from teardown**. It could have been latched mid-operation by one of the three observed `WC=0/3` events. We can't disambiguate without a higher-resolution log (drive does not timestamp `0x603F` writes).

**Mitigations (not applied yet — capture for Stage 7 multi-axis):**

1. **Tune SYNC0 cycle shift** via SDO `0x1C32:03` (output) / `0x1C33:03` (input). Typical Panasonic / A6-derived recipe is 100–500 µs negative shift, which gives the drive MCU a chunk of the cycle to finish its work before the next SYNC0 fires. Default is 0 — almost no margin.
2. Consider stepping up cycle time to **2 ms** if a multi-axis bring-up shows sustained `WC=0/3` storms; revisit 1 ms once SYNC0 shift is dialed in.
3. Keep `Following Error Window` (`0x6065`) generous — current factory value 429,483 counts is fine, do not tighten without empirical justification.
4. Monitor `0x603F` periodically from the application loop (cheap PDO add) to catch sync-error latches early instead of finding them post-mortem.

**This is not a blocker for Stage 5 / 6 single-slave ROS bring-up.** A real concern only when (a) several axes share the bus and one disturbance can cascade, or (b) production load profile pushes the drive MCU consistently near the deadline.

## 16. `ETHERLAB_DIR` hardcoded in ICube CMakeLists, not a CACHE variable

**Severity:** medium — blocks downstream `find_package(ethercat_interface)` if IgH was installed somewhere other than `/usr/local/etherlab`.

ICube `ethercat_driver_ros2` (jazzy branch, HEAD `066b81a2f54a230af3f54160be41aa53657073e0` as of 2026-05-14) assumes IgH is installed at `/usr/local/etherlab/{include,lib,bin}`. The path is hardcoded in two `CMakeLists.txt`:

- `ethercat_interface/CMakeLists.txt:21` — `set(ETHERLAB_DIR /usr/local/etherlab)`
- `ethercat_manager/CMakeLists.txt:15`   — `set(ETHERLAB_DIR /usr/local/etherlab)`

Two issues if your IgH prefix is different (we used `/usr/local`, the IgH default):

1. **Compile silently succeeds** because `find_library(... HINTS .../etherlab/lib)` falls through to system search and picks up `/usr/local/lib/libethercat.so`. `#include "ecrt.h"` likewise finds `/usr/local/include/ecrt.h` via the default compiler search path. The build looks fine.
2. **Downstream `find_package(ethercat_interface)` HARD-FAILS** because `ament_export_include_directories(... ${ETHERLAB_DIR}/include)` bakes `/usr/local/etherlab/include` into the exported CMake config. CMake validates exported paths exist and aborts with:

   > `Imported target "ethercat_interface::ethercat_interface" includes non-existent path "/usr/local/etherlab/include" in its INTERFACE_INCLUDE_DIRECTORIES`

So `ethercat_generic_cia402_drive`, `ethercat_generic_slave`, etc., fail to configure.

Passing `-DETHERLAB_DIR=/usr/local` to colcon does **not** help, because `set(... )` without `CACHE` unconditionally overwrites any -D flag at configure time. CMake warns "Manually-specified variables were not used" — that's the tell.

**Fix (two-line patch, in the cloned source):**

```diff
-set(ETHERLAB_DIR /usr/local/etherlab)
+set(ETHERLAB_DIR /usr/local/etherlab CACHE PATH "Path to EtherLab/IgH installation prefix")
```

Apply to both `CMakeLists.txt` files. Then `colcon build --cmake-args -DETHERLAB_DIR=/usr/local` works.

Combined with [§1](#1-clock_realtime-in-dc-sync-bug-in-icube-driver) this becomes the **ICube driver patch we maintain locally** — see `docs/manipulator_hardware_interface/patches/ethercat_driver_ros2-icube.patch` (4 hunks, 6 lines changed total: 2 for CLOCK_MONOTONIC, 2 for `ETHERLAB_DIR CACHE PATH`). The patch is regenerated by `git diff` against the pinned upstream HEAD.

**Alternative (not chosen):** reinstall IgH under `/usr/local/etherlab` to match the ICube assumption. Pros: zero source patches. Cons: existing `ethercat.service`, ldconfig, `/usr/local/etc/ethercat.conf` paths all baked into the working Stage 2/3/4 setup — disruptive for no value.

## 14. Vendor docs we still want

We would like to ask StepperOnline support for:

- A full **EtherCAT communication manual** for the A6-EC series (object dictionary in machine-readable form, supported PDO assignments, SDO timing constraints).
- Any **DC sync** application note specific to A6-EC.
- Errata for the public ESI file (versioning).

The public PDF manual covers electrical wiring and parameters but is thin on the EtherCAT protocol layer.
