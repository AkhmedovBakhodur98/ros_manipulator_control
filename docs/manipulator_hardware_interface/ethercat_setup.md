# EtherCAT Master Setup

> Host-level EtherCAT stack — IgH master, kernel modules, systemd integration. **Installed and verified on `grenka` 2026-05-14 (Stage 2 of [bringup.md](bringup.md)).** This document is the canonical recipe; the bringup checklist references it.

## Stack Choice

- **EtherCAT master:** IgH (etherlab.org) — kernel module + userspace tool `ethercat`.
- **ROS 2 integration:** [`ethercat_driver_ros2`](https://github.com/ICube-Robotics/ethercat_driver_ros2) (ICube-Robotics), `EcCiA402Drive` plugin.
- **NIC driver mode:** `generic` (RTL8125 has no native IgH driver — see [known_issues.md](known_issues.md)).
- **Target cycle time:** 1 ms (CSP with DC).

## Why IgH and not SOEM

We initially planned SOEM (userspace, no kernel module). After surveying the ROS 2 ecosystem in 2026-05, the only living generic CiA 402 driver under Jazzy is ICube's, and it is built on IgH. The SOEM-based [`synapticon_ros2_control`](https://github.com/synapticon/synapticon_ros2_control) is hardcoded to the Synapticon SOMANET drive — porting it to A6 would mean rewriting PDO mapping and SDO init from scratch. IgH gives us a faster path to working hardware.

## Install Procedure

Steps below were applied on `grenka` 2026-05-14 (Stage 2 of [bringup.md](bringup.md)). Annotations marked **gotcha** flag things that bit us during the run and are not obvious from upstream docs.

### 1. Install IgH master from source

```bash
# Dependencies
sudo apt install -y autoconf libtool pkg-config build-essential

# Clone (keep sources around — we may need to re-build / patch later)
sudo mkdir -p /opt/ethercat-src && sudo chown "$USER:$USER" /opt/ethercat-src
git clone https://gitlab.com/etherlab.org/ethercat.git /opt/ethercat-src
cd /opt/ethercat-src
# Default branch is `stable-1.6`. As of 2026-05-14 HEAD is 1.6.9.
# git checkout stable-1.6   # only needed if default ever changes

# Configure for generic driver + no EoE
./bootstrap
./configure --prefix=/usr/local \
            --enable-generic \
            --disable-8139too \
            --disable-eoe

# *** gotcha *** — `make` without arguments builds ONLY userspace.
# Kernel modules need a separate target.
make -j$(nproc)
make modules -j$(nproc)

# *** gotcha *** — if Secure Boot is enabled, the just-built unsigned
# .ko files will fail to load with `Key was rejected by service`.
# See known_issues.md §7. On `grenka` we disabled SB in BIOS for the
# dev box; production will use DKMS + MOK.

sudo make modules_install install
sudo depmod
```

What `make install` lays down:

| Path | What |
|---|---|
| `/lib/modules/$(uname -r)/ethercat/{master,devices}/*.ko` | kernel modules |
| `/usr/local/bin/ethercat` | userspace control tool |
| `/usr/local/sbin/ethercatctl` | start/stop script invoked by systemd |
| `/usr/local/lib/libethercat.so*` | shared lib for the ROS 2 driver |
| `/usr/local/etc/ethercat.conf` | **default config skeleton** (see §2) |
| `/lib/systemd/system/ethercat.service` | systemd unit (already in unit search path — no manual copy needed) |

### 2. Configure master

**gotcha** — `ethercatctl` reads `${prefix}/etc/ethercat.conf`, i.e. `/usr/local/etc/ethercat.conf` for our prefix. Writing to `/etc/ethercat.conf` (common Linux instinct) is **silently ignored**; the service will fail with `No network cards for EtherCAT specified` even though the file looks right.

Edit `/usr/local/etc/ethercat.conf`:

```ini
# MAC of the EtherCAT NIC. `ip link show eno1` to find it.
MASTER0_DEVICE="74:56:3c:30:04:57"

# Generic driver — RTL8125 has no native IgH driver.
DEVICE_MODULES="generic"

# *** important for generic mode *** — bring up eno1 before the master starts,
# otherwise frames time out. ethercatctl handles this when this list is set.
UPDOWN_INTERFACES="eno1"
```

### 3. Enable and start the systemd service

The unit ships pre-installed in `/lib/systemd/system/`. No need to copy it.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ethercat
sudo systemctl status ethercat --no-pager
```

If you ever need to override unit behavior (e.g. add `Requires=network.target` when not using `UPDOWN_INTERFACES`), drop a snippet into `/etc/systemd/system/ethercat.service.d/50-local.conf` — don't edit the upstream unit in `/lib/systemd/`.

### 4. Verify

```bash
# Modules loaded
lsmod | grep ec_
# Expected: ec_master, ec_generic

# Master in IDLE state
ethercat master

# With the test bench connected, slaves should show up (Stage 3)
ethercat slaves
# Expected (test bench): 2 slaves, A6-750EC + A6-200EC
```

## ROS 2 driver build

The ICube `ethercat_driver_ros2` build, clone command, pinned upstream HEAD, local patches, and verification steps are documented in **[bringup.md Stage 5](bringup.md)** and **[known_issues.md §1, §16](known_issues.md)**. The patches we maintain locally live in [`patches/`](patches/) and apply against the pinned upstream HEAD.

Key fact for this document: the driver expects `libethercat` and `ecrt.h` reachable from the prefix passed via `-DETHERLAB_DIR`. Our IgH is in `/usr/local/{lib,include}`, so the colcon command is:

```bash
colcon build --packages-up-to ethercat_driver_ros2 ethercat_generic_cia402_drive ethercat_manager \
             --cmake-args -DETHERLAB_DIR=/usr/local
```

## Slave configuration

A6-EC PDO mapping (verified PDOs, Object Dictionary subset we care about, scaling) is in [a6_pdo_mapping.md](a6_pdo_mapping.md). Verified identity (`vendor_id 0x00400000`, `product_id 0x00000715`, etc.) is also there.

A working **C reference** of the full single-slave bring-up — variable PDO remap via SDO, DC sync, CiA 402 state machine, sine target — is the [`tools/csp_smoke/`](../../tools/csp_smoke/) program from Stage 4. Stage 6 will translate the same configuration into per-slave YAML for `ros2_control` (no C++ plugin — see [package_structure.md](package_structure.md) for the rationale).

## Permissions

The IgH installer does **not** create the `ethercat` group or the udev rule for `/dev/EtherCAT0` (this surprised us — see [known_issues.md §10](known_issues.md)). After `make modules_install install` the device node appears as `crw------- root root`. One-time fix:

```bash
sudo groupadd -f ethercat
sudo tee /etc/udev/rules.d/99-ethercat.rules >/dev/null <<'EOF'
KERNEL=="EtherCAT[0-9]*", MODE="0660", GROUP="ethercat"
EOF
sudo udevadm control --reload
sudo udevadm trigger
sudo usermod -aG ethercat "$USER"
# log out and back in (or `newgrp ethercat` for the current shell only)
```

Verify: `ls -l /dev/EtherCAT0` → `crw-rw---- root ethercat`, then `/usr/local/bin/ethercat master` without `sudo` should print `Phase: Idle`.

NIC offload / coalescing tuning (a separate concern from device-node permissions) is in [rt_tuning.md](rt_tuning.md).

## What Happens at Bringup

1. `systemd` starts `ethercat.service`, which loads `ec_master` and `ec_generic` kernel modules and claims `eno1` as the EtherCAT NIC.
2. ROS 2 launches `controller_manager` via `manipulator_hardware_interface/launch/ethercat_master.launch.py`.
3. The `EthercatDriver` plugin reads slave YAMLs and the master config, opens domain 0, transitions slaves PreOP → SafeOP → OP.
4. Once in OP, ros2_control activation enables the joint state interfaces, then a `JointTrajectoryController` (or similar) is loaded.

`eno1` is dedicated to EtherCAT — internet is via WiFi. See the dev-machine memory for the rationale.
