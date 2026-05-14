# Real-Time Tuning for EtherCAT @ 1 kHz

> Concentrated tuning recipe for the `grenka` dev machine (Ryzen 7 3700X, 8C/16T, RTL8125 NIC on `eno1`, Ubuntu 24.04 + PREEMPT_RT 6.8.1-1048-realtime). Most of this is derived from issue research (see [known_issues.md](known_issues.md)) and from Linux Foundation / Canonical RT guides.

## Why we need this

Default Ubuntu scheduling produces worst-case jitter in the multi-millisecond range — orders of magnitude beyond our 1 ms EtherCAT cycle budget. With proper isolation + NIC tuning on PREEMPT_RT we expect:

| Metric | Target | Source |
|---|---|---|
| `cyclictest` worst-case latency (1h, under stress-ng load) | < 100 µs | LF RT guide |
| EtherCAT frame release jitter (max) | < 500 µs | Empirical (issue #101, Intel I210 + generic) |
| Frame overruns per 1M cycles | ≤ 1 | Empirical (issue #101) |

Generic RTL8125 driver will add some jitter vs a native driver, but as documented in [known_issues.md](known_issues.md), even Intel I225 with the native `igc` driver does not work out of the box with IgH — generic is the common path.

## CPU Topology Plan

Ryzen 7 3700X = 8 physical cores. **SMT отключён в BIOS** → 8 логических CPU, 1 thread/core (см. BIOS-секцию ниже).

| Core(s) | Use |
|---------|-----|
| 0 | System: kernel housekeeping, IRQs, normal userspace |
| 1–3 | **Isolated** — EtherCAT master + ros2_control RT loop |
| 4–7 | Normal userspace (controllers, planners, perception, ROS nodes) |

С отключённым SMT не нужно отдельно сторониться sibling-тредов: каждое ядро — это один поток.

## GRUB Configuration

Edit `/etc/default/grub`:

```
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash \
  isolcpus=1,2,3 \
  nohz_full=1,2,3 \
  rcu_nocbs=1,2,3 \
  irqaffinity=0 \
  processor.max_cstate=1 \
  mitigations=off"
```

| Flag | What it does |
|---|---|
| `isolcpus=1,2,3` | Removes CPUs 1–3 from the default scheduler — no tasks land there unless explicitly pinned |
| `nohz_full=1,2,3` | Tickless mode on isolated CPUs (kills the per-CPU clock interrupt jitter) |
| `rcu_nocbs=1,2,3` | RCU callbacks routed away from isolated CPUs |
| `irqaffinity=0` | At boot, all IRQs go to CPU 0 (we'll move the NIC IRQ explicitly afterwards) |
| `processor.max_cstate=1` | Disable deep C-states (wakeup latency). Generic, работает и на Intel, и на AMD. На Intel-системах добавляется `intel_pstate=disable`; на AMD аналог не требуется — `cpupower frequency-set -g performance` или BIOS Cool'n'Quiet off (см. BIOS-секцию ниже) делают то же самое. |
| `mitigations=off` | Disables Spectre/Meltdown mitigations — non-negligible RT improvement, acceptable on an air-gapped dev machine |

> Опциональные флаги, не применённые на `grenka` по умолчанию: `amd_iommu=off` (на Ryzen 3700X в наших тестах разницы не дал; включать, если IOMMU подтверждённо вносит jitter) и `intel_pstate=disable` (только для Intel).

Then:

```bash
sudo update-grub
sudo reboot
```

Verify after reboot: `cat /proc/cmdline` should show the flags.

## IRQ Pinning for `eno1`

GRUB sends all IRQs to CPU 0 at boot, but the NIC driver may move them later. We force-pin via systemd at every boot.

```bash
# /usr/local/sbin/ethercat-irq-pin.sh
#!/bin/bash
set -e
IRQS=$(grep -E '^[0-9]+:' /proc/interrupts | grep eno1 | awk '{print $1}' | tr -d ':')
for irq in $IRQS; do
    echo 2 > /proc/irq/$irq/smp_affinity   # mask 0b0010 = CPU 1
done
```

Make it executable and register:

```bash
sudo chmod +x /usr/local/sbin/ethercat-irq-pin.sh

# /etc/systemd/system/ethercat-irq-pin.service
[Unit]
Description=Pin eno1 EtherCAT NIC IRQs to isolated CPU
After=network.target ethercat.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/ethercat-irq-pin.sh
RemainAfterExit=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ethercat-irq-pin.service
```

## NIC Tuning (`ethtool`)

Even the generic driver respects most ethtool offload toggles. Recipe from Pieterjan in issue #101 (Intel I210, but mostly portable):

```bash
# /usr/local/sbin/ethercat-nic-tune.sh
#!/bin/bash
NIC=eno1

# Disable everything that batches/coalesces frames
ethtool -K $NIC gso off gro off tso off
ethtool -K $NIC tx off rx off
ethtool -K $NIC sg off lro off

# Coalescing: send immediately
ethtool -C $NIC rx-usecs 0 tx-usecs 0 rx-frames 1 tx-frames 1 || true

# Lock link speed (RTL8125 supports up to 2.5G — EtherCAT runs at 100M, lock there)
ethtool -s $NIC speed 100 duplex full autoneg off
```

Register the same way as the IRQ-pin service. Note: not all parameters are supported by the generic driver — `|| true` swallows the harmless ones.

## Userspace RT Limits

Before any userspace process can call `sched_setscheduler(SCHED_FIFO, ...)` or `mlockall()`, the kernel needs to see non-zero `RLIMIT_RTPRIO` and a generous `RLIMIT_MEMLOCK` for that process. Default Ubuntu shell has `ulimit -r = 0` and `ulimit -l ≈ 50% of RAM` — both must be raised.

### The Ubuntu 24.04 + GDM trap

The "obvious" answer is to drop a file in `/etc/security/limits.d/`:

```bash
# /etc/security/limits.d/99-ethercat-rt.conf
@ethercat   -   rtprio   95
@ethercat   -   memlock  unlimited
```

**This is necessary but not sufficient.** `pam_limits.so` is wired into `/etc/pam.d/login` (TTY console) and `/etc/pam.d/sshd` — so SSH and Ctrl+Alt+F<n> consoles get the limits. But on a normal **desktop GDM/Wayland login**, the process tree looks like:

```
systemd (PID 1) ── user@1000.service ── systemd --user ── gnome-shell ── gnome-terminal-server ── bash
```

`systemd --user` is **not** spawned through PAM — it's launched directly by the system `systemd` via `user@<UID>.service`. So `pam_limits.so` from `/etc/pam.d/gdm-password` applies to the GDM session leader, but **not** to children of `systemd --user`. Open a graphical terminal, run `ulimit -r` — still `0`.

### The fix that works under GDM

Raise the limits via systemd defaults, which `user@<UID>.service` inherits:

```bash
sudo mkdir -p /etc/systemd/system.conf.d
sudo tee /etc/systemd/system.conf.d/99-ethercat-rt.conf >/dev/null <<'EOF'
[Manager]
DefaultLimitRTPRIO=95
DefaultLimitMEMLOCK=infinity
EOF
sudo reboot
```

After reboot, `ulimit -r` in `gnome-terminal` → `95`, `ulimit -l` → `unlimited`. `/etc/security/limits.d/99-ethercat-rt.conf` is still useful (covers SSH/TTY paths) — keep both.

### Why 95, not 99

Linux kernel reserves the highest real-time priorities for internal threads:

- **99** — migration threads, watchdogs, RCU boost. User code preempting these can hang the kernel.
- **80** — typical EtherCAT cyclic thread priority (IgH's own examples, ICube's `ethercat_driver_ros2`).

The csp_smoke binary asks for priority **80**. The systemd ceiling is set to **95**, which provides headroom for ros2_control + IgH kernel master thread (also at 80) without giving userspace code the ability to starve kernel-critical threads.

If you raise the systemd ceiling to 99, any buggy userspace loop running at priority 99 — even briefly — can soft-lock the machine. Don't.

## Real-Time Process Priorities

When launching the controller_manager:

```bash
chrt -f 80 ros2 launch manipulator_bringup ethercat_bench.launch.py
```

Or, better, set `SCHED_FIFO` from inside the launch via `Node(prefix='chrt -f 80')` (untested — Stage 6.5 follow-up).

**Verified 2026-05-14 (Stage 6 exit criterion soak):** with `chrt -f 80` on the launch *and* the `ethercat-irq-pin.service` from above active, a 600-second steady-state run logged **zero** `Working counter` / `UNMATCHED` / `SKIPPED` / `TIMED OUT` events. **Do NOT add `taskset -c 1`** to the wrapper — pinning the entire ros2_control_node process tree to CPU 1 forces ROS callbacks to compete with the cyclic thread on the same core and produces 2–4 ms PDO read times. The right shape is: NIC IRQ + RT cyclic thread on CPU 1 (cache co-located), ROS callbacks left for the scheduler on CPU 0.

The EtherCAT kernel thread (`ec_master_0`) is already at SCHED_FIFO 80 from IgH defaults — verify with `ps -eLo pid,tid,class,rtprio,comm | grep ec_master`.

## Verification Protocol

Before trusting the system, run this sequence on every fresh setup:

```bash
# 1. Baseline cyclictest, idle
cyclictest -t1 -p 99 -i 1000 -l 100000 -m

# 2. Under load
stress-ng --cpu $(nproc) --io 4 --vm 2 --vm-bytes 1G &
cyclictest -t1 -p 99 -i 1000 -l 3600000 -m   # 1h run
kill %1
```

Expected: max latency under load < 100 µs. If higher, investigate (BIOS C-states, SMT siblings, etc.).

**Reference result on `grenka` (2026-05-13, full tuning applied):**

```
cyclictest -a 1 -t1 -p 99 -i 1000 -l 60000 -m          # pinned to isolated CPU 1
# under stress-ng --cpu 16 --io 4 --vm 2 --vm-bytes 512M
T: 0  Min: 1  Act: 2  Avg: 2  Max: 7
```

Logs and reusable script in `/home/grenka/rt_logs/` (`rt-snapshot3.sh`).

> Sanity check after isolation: `nproc` будет показывать **5** (CPUs 0,4–7), а не 8 — это нормально, isolcpus прячет 1–3 от `sched_getaffinity()`. Реальное число онлайн-ядер — `nproc --all` (= 8) или `cat /sys/devices/system/cpu/online`.

Then with EtherCAT running:

```bash
# Watch for missed frames in dmesg
sudo dmesg -wH | grep -iE 'ethercat|wc|timed out'

# Watch master state
watch -n 1 ethercat master
```

A healthy run has zero `TIMED OUT` / `UNMATCHED` warnings during operation.

## BIOS Settings (Reminder)

On the Ryzen 7 3700X board (`grenka`):

- **Disable** Cool'n'Quiet / PSS Support / Global C-State Control
- **Disable** SMT — без этого не достигнуть стабильного worst-case под нагрузкой (на нашей машине дало −43% jitter без других правок: 23 µs → 13 µs). Теряем половину логических CPU, но получаем 8 «честных» ядер вместо 16 конкурирующих за L1.
- **Disable** PSPP / Spread Spectrum
- **Enable** Memory Profile to XMP/DOCP — stable RAM clocks matter
- **Disable** any "Eco mode" / "Energy Save"

## Cross-References

- [Issue #101](https://github.com/ICube-Robotics/ethercat_driver_ros2/issues/101) — the empirical numbers and rationale come from here
- [Canonical RT tuning guide](https://ubuntu.com/blog/real-time-kernel-tuning)
- [Linux Foundation cyclictest howto](https://wiki.linuxfoundation.org/realtime/documentation/howto/tools/cyclictest/start)
