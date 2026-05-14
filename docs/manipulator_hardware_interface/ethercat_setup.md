# EtherCAT Master Setup

> Notes for installing and configuring the IgH EtherCAT master on the `grenka` dev machine. As of 2026-05-13, none of this is installed yet — these are planning notes derived from the upstream documentation and from issue research.

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

## Build `ethercat_driver_ros2`

```bash
# ROS 2 Jazzy assumed (not yet installed on grenka as of 2026-05-13)
cd ~/ros_manipulator_control/src
git clone --branch jazzy https://github.com/ICube-Robotics/ethercat_driver_ros2.git
cd ..
rosdep install --from-paths src --ignore-src -r -y
colcon build --packages-select ethercat_driver ethercat_master_interface ethercat_interface
```

## Slave Configuration

A6-EC PDO mapping is described in [a6_pdo_mapping.md](a6_pdo_mapping.md). Slave YAML files will live in `config/ethercat/` of this package.

Reference shape (from ICube examples):

```yaml
vendor_id: 0x000004F2          # StepperOnline (verify against ESI XML)
product_id: 0x00000001         # verify against ESI XML
assign_activate: 0x0300        # DC enable, sync0 + sync1
sm: [...]                      # Sync Manager config
rpdo:
  - index: 0x1600              # variable mapping — NOT 0x1701 (see known_issues)
    channels:
      - { index: 0x6040, sub_index: 0, type: uint16 }   # ControlWord
      - { index: 0x607A, sub_index: 0, type: int32  }   # Target Position
      - { index: 0x60FF, sub_index: 0, type: int32  }   # Target Velocity (S32!)
      - { index: 0x6060, sub_index: 0, type: int8   }   # Mode of Operation
tpdo:
  - index: 0x1A00
    channels:
      - { index: 0x6041, sub_index: 0, type: uint16 }   # StatusWord
      - { index: 0x6064, sub_index: 0, type: int32  }   # Actual Position
      - { index: 0x606C, sub_index: 0, type: int32  }   # Actual Velocity
      - { index: 0x6077, sub_index: 0, type: int16  }   # Actual Torque
      - { index: 0x6061, sub_index: 0, type: int8   }   # Mode Display
```

The exact `vendor_id`/`product_id` and SM config must come from the StepperOnline ESI file:
<https://www.omc-stepperonline.com/index.php?route=product/product/get_file&file=5072/STEPPERONLINE_A6_Servo_V0.04.xml>

## Permissions

Add the developer user to the `ethercat` group (created by `make install`) so the userspace `ethercat` command and the ROS 2 driver can talk to the master without `sudo`:

```bash
sudo usermod -aG ethercat $USER
# log out and back in
```

Also drop a udev rule for `eno1`:

```
# /etc/udev/rules.d/99-ethercat.rules
KERNEL=="eno1", RUN+="/usr/sbin/ethtool -K eno1 gso off gro off tso off"
```

(NIC tuning details in [rt_tuning.md](rt_tuning.md).)

## What Happens at Bringup

1. `systemd` starts `ethercat.service`, which loads `ec_master` and `ec_generic` kernel modules and claims `eno1` as the EtherCAT NIC.
2. ROS 2 launches `controller_manager` via `manipulator_hardware_interface/launch/ethercat_master.launch.py`.
3. The `EthercatDriver` plugin reads slave YAMLs and the master config, opens domain 0, transitions slaves PreOP → SafeOP → OP.
4. Once in OP, ros2_control activation enables the joint state interfaces, then a `JointTrajectoryController` (or similar) is loaded.

`eno1` is dedicated to EtherCAT — internet is via WiFi. See the dev-machine memory for the rationale.
