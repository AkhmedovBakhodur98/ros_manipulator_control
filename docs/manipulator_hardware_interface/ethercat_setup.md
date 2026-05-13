# EtherCAT Master Setup

> Notes for installing and configuring the IgH EtherCAT master on the `grenka` dev machine. As of 2026-05-13, none of this is installed yet — these are planning notes derived from the upstream documentation and from issue research.

## Stack Choice

- **EtherCAT master:** IgH (etherlab.org) — kernel module + userspace tool `ethercat`.
- **ROS 2 integration:** [`ethercat_driver_ros2`](https://github.com/ICube-Robotics/ethercat_driver_ros2) (ICube-Robotics), `EcCiA402Drive` plugin.
- **NIC driver mode:** `generic` (RTL8125 has no native IgH driver — see [known_issues.md](known_issues.md)).
- **Target cycle time:** 1 ms (CSP with DC).

## Why IgH and not SOEM

We initially planned SOEM (userspace, no kernel module). After surveying the ROS 2 ecosystem in 2026-05, the only living generic CiA 402 driver under Jazzy is ICube's, and it is built on IgH. The SOEM-based [`synapticon_ros2_control`](https://github.com/synapticon/synapticon_ros2_control) is hardcoded to the Synapticon SOMANET drive — porting it to A6 would mean rewriting PDO mapping and SDO init from scratch. IgH gives us a faster path to working hardware.

## Install Procedure (Planned)

### 1. Install IgH master from source

```bash
# Dependencies
sudo apt install -y autoconf libtool pkg-config

# Clone
git clone https://gitlab.com/etherlab.org/ethercat.git /tmp/ethercat
cd /tmp/ethercat
git checkout stable-1.6   # or master if 1.6 lags

# Configure for generic driver + no MII
./bootstrap
./configure --prefix=/usr/local \
            --enable-generic \
            --disable-8139too \
            --disable-eoe

make -j$(nproc)
sudo make modules_install install
sudo depmod
```

### 2. Configure master

Edit `/etc/ethercat.conf`:

```ini
MASTER0_DEVICE="<MAC_OF_eno1>"
DEVICE_MODULES="generic"
```

Get the MAC: `ip link show eno1`.

### 3. Install systemd service

```bash
sudo cp /tmp/ethercat/script/ethercat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ethercat
sudo systemctl start ethercat
```

### 4. Verify

```bash
# Master should be in IDLE state
ethercat master

# With the test bench connected, slaves should show up
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
