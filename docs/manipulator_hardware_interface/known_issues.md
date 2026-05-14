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

## 11. Vendor docs we still want

We would like to ask StepperOnline support for:

- A full **EtherCAT communication manual** for the A6-EC series (object dictionary in machine-readable form, supported PDO assignments, SDO timing constraints).
- Any **DC sync** application note specific to A6-EC.
- Errata for the public ESI file (versioning).

The public PDF manual covers electrical wiring and parameters but is thin on the EtherCAT protocol layer.
