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

Apply both, then `sudo reboot`. Verify with `ulimit -r` (expect `95`) and
`ulimit -l` (expect `unlimited`) in a fresh `gnome-terminal` window.
