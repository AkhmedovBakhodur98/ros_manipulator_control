#!/bin/bash
# Pin all eno1 (EtherCAT NIC) hardware IRQs to CPU 1, the first isolated core
# (see /etc/default/grub: isolcpus=1,2,3).
#
# Why: by default ALL hardware IRQs land on CPU 0 (kernel cmdline irqaffinity=0
# from Stage 1 RT tuning). When ros2_control_node's cyclic thread sits on CPU 1
# but the NIC IRQ fires on CPU 0, every PDO read incurs a cross-core sync —
# read time balloons from <100 us to 3.2 ms, slave drops out of OP. Co-locating
# the IRQ handler with the cyclic thread on the same isolated core (cache hot,
# zero IPI) is what gets the kernel log to zero events over a 10-min soak.
#
# Verified 2026-05-14 in Stage 6 exit criterion run on `grenka`. See
# docs/manipulator_hardware_interface/bringup.md Stage 6 + rt_tuning.md.

set -e

IRQS=$(grep -E '^[[:space:]]*[0-9]+:' /proc/interrupts | grep eno1 | awk '{print $1}' | tr -d ':')

if [ -z "$IRQS" ]; then
    echo "ethercat-irq-pin: no eno1 IRQs found in /proc/interrupts — is the NIC up?" >&2
    exit 1
fi

for irq in $IRQS; do
    echo 2 > "/proc/irq/$irq/smp_affinity"   # mask 0b0010 = CPU 1
    echo "ethercat-irq-pin: pinned IRQ $irq → CPU 1 (effective: $(cat /proc/irq/$irq/effective_affinity))"
done
