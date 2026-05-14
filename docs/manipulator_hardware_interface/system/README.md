# System configuration reference

Vendored copies of the host-system config files used to bring up EtherCAT
on `grenka`. They live here so a second machine (and later, the production
controller) can replicate the setup verbatim without re-deriving it.

The authoritative rationale is in [rt_tuning.md](../rt_tuning.md);
this directory is just the file payloads.

| File in this dir | Install path | Purpose |
|---|---|---|
| [`systemd-99-ethercat-rt.conf`](systemd-99-ethercat-rt.conf) | `/etc/systemd/system.conf.d/99-ethercat-rt.conf` | Raises `RLIMIT_RTPRIO`/`RLIMIT_MEMLOCK` defaults for all systemd-managed services, including `user@<UID>.service`. Required on Ubuntu 24.04 + GDM. |
| [`limits.d-99-ethercat-rt.conf`](limits.d-99-ethercat-rt.conf) | `/etc/security/limits.d/99-ethercat-rt.conf` | Same limits via `pam_limits.so`. Covers SSH and TTY login paths. Not sufficient under GDM alone — keep both. |
| [`ethercat-irq-pin.sh`](ethercat-irq-pin.sh) | `/usr/local/sbin/ethercat-irq-pin.sh` | Moves every eno1 hardware IRQ to CPU 1 (isolated). Without it the cyclic thread on CPU 1 cross-cores into the NIC IRQ on CPU 0 every PDO read → 3.2 ms read time → slave drops. Verified Stage 6 (2026-05-14). |
| [`ethercat-irq-pin.service`](ethercat-irq-pin.service) | `/etc/systemd/system/ethercat-irq-pin.service` | One-shot systemd unit that runs the script after `ethercat.service` so the IRQ pin survives reboots. |

**Apply RT-limits** (one-time, host-wide):

```bash
sudo cp systemd-99-ethercat-rt.conf  /etc/systemd/system.conf.d/99-ethercat-rt.conf
sudo cp limits.d-99-ethercat-rt.conf /etc/security/limits.d/99-ethercat-rt.conf
sudo reboot
# verify in a fresh gnome-terminal: ulimit -r → 95, ulimit -l → unlimited
```

**Apply IRQ pin** (one-time, host-wide):

```bash
sudo install -m 0755 ethercat-irq-pin.sh /usr/local/sbin/ethercat-irq-pin.sh
sudo install -m 0644 ethercat-irq-pin.service /etc/systemd/system/ethercat-irq-pin.service
sudo systemctl daemon-reload
sudo systemctl enable --now ethercat-irq-pin.service
# verify: cat /proc/irq/$(grep eno1 /proc/interrupts | awk -F: '{print $1}' | tr -d ' ')/effective_affinity
# expect: 00000002 (CPU 1)
```
