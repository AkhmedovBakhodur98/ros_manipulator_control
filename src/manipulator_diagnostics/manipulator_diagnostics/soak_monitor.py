"""Soak / jitter monitor for the full-chain EtherCAT bring-up.

What it watches and what each thing tells us:

  /dynamic_joint_states (high-rate)
    Frame-to-frame delta = upper bound on the propagation jitter from
    EtherCAT cycle -> hardware_interface read -> JointStateBroadcaster
    publish. Not a 1:1 measurement of PDO jitter (the broadcaster runs
    at state_publish_rate, not the master cycle) but a regression
    signal: if a 4 h soak shows the max delta drifting over time, the
    bus is degrading even if no kernel WC drop has been logged yet.

  /overtravel_events (from manipulator_homing/safety_monitor)
    Cumulative count + last seen. Non-zero during a soak is a hard
    fail unless we deliberately pressed a switch.

  /diagnostics (controller_manager + ros2_control DiagnosticArray)
    Cycle-time and overrun-count keys when ros2_control publishes
    them. Filtered to the manipulator hardware so we don't pick up
    unrelated nodes' diagnostics.

  ethercat master (IgH userspace tool, subprocess every poll period)
    Lost frames and tx-errors per device. Anything but zero is the
    canonical signature of a bus problem.

  kernel log (journalctl -k since the previous tick)
    The Stage 6 exit criterion shape: count "EtherCAT WARNING" lines
    matching the four classic patterns (WC=0, UNMATCHED, SKIPPED,
    TIMED OUT). Requires journalctl to be readable; if not, the
    counters stay at zero with a one-shot warning at startup.

One CSV row per `sample_period_sec`. A console summary every
`summary_period_sec` so an operator following the test sees only
deltas, not 4 hours of scroll (per feedback-bench-interactive memo:
snapshot-summary > realtime log spam).
"""

import csv
import os
import re
import subprocess
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from control_msgs.msg import DynamicJointState
from diagnostic_msgs.msg import DiagnosticArray

from manipulator_msgs.msg import OvertravelEvent


_EC_KERNEL_PATTERNS = {
    'kernel_wc_zero':    re.compile(r'WC=0|working counter'),
    'kernel_unmatched':  re.compile(r'UNMATCHED', re.IGNORECASE),
    'kernel_skipped':    re.compile(r'SKIPPED', re.IGNORECASE),
    'kernel_timed_out':  re.compile(r'TIMED ?OUT', re.IGNORECASE),
}

# Output of `ethercat master`. We grep the parts we care about
# rather than fully parsing the indented block — the IgH tool format
# is stable enough across versions for this to be safe.
_EC_LOST_FRAMES = re.compile(r'^\s*Lost frames:\s+(\d+)', re.MULTILINE)
_EC_TX_ERRORS   = re.compile(r'^\s*Tx errors:\s+(\d+)', re.MULTILINE)
_EC_SLAVES_OP   = re.compile(r'^\s*Slaves:\s+(\d+)', re.MULTILINE)


class SoakMonitor(Node):

    def __init__(self) -> None:
        super().__init__('soak_monitor')

        self.declare_parameter('csv_path', '/tmp/soak_test.csv')
        self.declare_parameter('sample_period_sec', 1.0)
        self.declare_parameter('summary_period_sec', 300.0)  # 5 min
        self.declare_parameter('ethercat_poll_period_sec', 30.0)
        self.declare_parameter('ethercat_binary', 'ethercat')
        self.declare_parameter('dynamic_joint_states_topic',
                               '/dynamic_joint_states')
        self.declare_parameter('overtravel_topic', '/overtravel_events')
        self.declare_parameter('diagnostics_topic', '/diagnostics')

        sample_period = float(self.get_parameter('sample_period_sec').value)
        summary_period = float(self.get_parameter('summary_period_sec').value)
        ec_poll = float(self.get_parameter('ethercat_poll_period_sec').value)

        # Rolling buffer of state-frame arrival timestamps. Sized so
        # one second of frames at 100 Hz (typical broadcaster rate) plus
        # headroom fits without reallocations.
        self._frame_times: deque[float] = deque(maxlen=2048)
        self._frame_count_total = 0

        self._sw_bit11_total = 0   # internal-limit-active (mode-irrelevant)
        self._sw_bit13_total = 0   # homing error in mode 6, following error in CSP
        # Previous bit state per joint so we count edges, not levels.
        self._sw_bit11_prev: dict[str, bool] = {}
        self._sw_bit13_prev: dict[str, bool] = {}

        self._overtravel_total = 0
        self._last_overtravel_joint: Optional[str] = None

        # IgH metrics, cumulative-since-master-start (we capture the
        # first reading at t0 as the baseline and report deltas in
        # summaries — IgH itself never resets these without restart).
        self._ec_lost_frames_baseline: Optional[int] = None
        self._ec_tx_errors_baseline: Optional[int] = None
        self._ec_lost_frames_last: Optional[int] = None
        self._ec_tx_errors_last: Optional[int] = None
        self._ec_slaves_last: Optional[int] = None

        # Kernel WC counters: deltas-since-previous-poll.
        self._kernel_totals: dict[str, int] = {k: 0 for k in _EC_KERNEL_PATTERNS}
        self._kernel_last_check_unix: float = time.time()
        self._kernel_disabled = False  # flipped if journalctl is unreadable

        cb_group = ReentrantCallbackGroup()
        self.create_subscription(
            DynamicJointState,
            self.get_parameter('dynamic_joint_states_topic').value,
            self._state_cb,
            10,
            callback_group=cb_group,
        )
        self.create_subscription(
            OvertravelEvent,
            self.get_parameter('overtravel_topic').value,
            self._overtravel_cb,
            50,
            callback_group=cb_group,
        )
        self.create_subscription(
            DiagnosticArray,
            self.get_parameter('diagnostics_topic').value,
            self._diagnostics_cb,
            10,
            callback_group=cb_group,
        )

        self._diag_cycle_time_us: Optional[float] = None
        self._diag_overrun_total: int = 0

        # CSV setup — open and write header before the first sample
        # timer fires so we don't race with the row write.
        csv_path = str(self.get_parameter('csv_path').value)
        os.makedirs(os.path.dirname(csv_path) or '.', exist_ok=True)
        self._csv_file = open(csv_path, 'w', newline='', buffering=1)
        self._csv = csv.writer(self._csv_file)
        self._csv.writerow([
            't_utc', 't_elapsed_sec',
            'frames_total', 'frame_dt_ms_avg', 'frame_dt_ms_max',
            'sw_bit11_total', 'sw_bit13_total',
            'overtravel_total',
            'jtc_cycle_time_us', 'jtc_overrun_total',
            'ec_lost_frames_delta', 'ec_tx_errors_delta', 'ec_slaves_in_op',
            'kernel_wc_zero_delta', 'kernel_unmatched_delta',
            'kernel_skipped_delta', 'kernel_timed_out_delta',
        ])
        self._t_zero = time.time()

        # Per-sample state for kernel/EC deltas (reset every row).
        self._kernel_delta = {k: 0 for k in _EC_KERNEL_PATTERNS}
        self._ec_lost_delta = 0
        self._ec_tx_delta = 0

        self._sample_timer = self.create_timer(
            sample_period, self._write_sample_row, callback_group=cb_group,
        )
        self._summary_timer = self.create_timer(
            summary_period, self._print_summary, callback_group=cb_group,
        )
        self._ec_timer = self.create_timer(
            ec_poll, self._poll_ethercat_and_kernel, callback_group=cb_group,
        )

        self.get_logger().info(
            f'SoakMonitor up: csv={csv_path} '
            f'sample={sample_period}s summary={summary_period}s '
            f'ec_poll={ec_poll}s'
        )

    # ----- subscribers -----

    def _state_cb(self, msg: DynamicJointState) -> None:
        # ROS clock at receive time — close enough to the broadcaster
        # publish time for jitter analysis without needing the message
        # header (DynamicJointState carries one but it may be the
        # broadcaster's local clock).
        self._frame_times.append(self.get_clock().now().nanoseconds * 1e-9)
        self._frame_count_total += 1

        for name, iv in zip(msg.joint_names, msg.interface_values):
            sw_value: Optional[int] = None
            for iface, value in zip(iv.interface_names, iv.values):
                if iface == 'status_word':
                    sw_value = int(value)
                    break
            if sw_value is None:
                continue
            b11 = bool(sw_value & (1 << 11))
            b13 = bool(sw_value & (1 << 13))
            if b11 and not self._sw_bit11_prev.get(name, False):
                self._sw_bit11_total += 1
            if b13 and not self._sw_bit13_prev.get(name, False):
                self._sw_bit13_total += 1
            self._sw_bit11_prev[name] = b11
            self._sw_bit13_prev[name] = b13

    def _overtravel_cb(self, msg: OvertravelEvent) -> None:
        # safety_monitor publishes on edges (rise + fall). Count only
        # the rising edges; falling ones come in with all booleans
        # cleared.
        if msg.p_ot_active or msg.n_ot_active or msg.internal_limit_active:
            self._overtravel_total += 1
            self._last_overtravel_joint = msg.joint_name

    def _diagnostics_cb(self, msg: DiagnosticArray) -> None:
        # ros2_control publishes per-controller / per-manager status
        # arrays. We don't know exact key spelling across distros so
        # match loosely on substrings — anything that calls itself
        # "overrun" / "cycle time" / "period" is interesting.
        for status in msg.status:
            name = status.name.lower()
            if 'controller_manager' not in name and 'ros2_control' not in name:
                continue
            for kv in status.values:
                key = kv.key.lower()
                try:
                    val = float(kv.value)
                except ValueError:
                    continue
                if 'overrun' in key:
                    # Sometimes diagnostics report counts, sometimes
                    # bools — accept whichever and treat the largest
                    # observed value as the cumulative count.
                    if val > self._diag_overrun_total:
                        self._diag_overrun_total = int(val)
                elif 'cycle' in key and 'time' in key:
                    # ms vs us in different reports — normalise on the
                    # assumption a 1 kHz loop reports under 1000.
                    self._diag_cycle_time_us = val if val < 1000.0 else val * 1000.0

    # ----- timers -----

    def _write_sample_row(self) -> None:
        now = time.time()
        t_utc = datetime.now(timezone.utc).isoformat(timespec='milliseconds')
        elapsed = now - self._t_zero

        deltas = []
        last_t = None
        for t in self._frame_times:
            if last_t is not None:
                deltas.append((t - last_t) * 1000.0)
            last_t = t
        if deltas:
            avg = sum(deltas) / len(deltas)
            mx = max(deltas)
        else:
            avg = 0.0
            mx = 0.0

        self._csv.writerow([
            t_utc, f'{elapsed:.3f}',
            self._frame_count_total, f'{avg:.3f}', f'{mx:.3f}',
            self._sw_bit11_total, self._sw_bit13_total,
            self._overtravel_total,
            f'{self._diag_cycle_time_us:.2f}' if self._diag_cycle_time_us is not None else '',
            self._diag_overrun_total,
            self._ec_lost_delta, self._ec_tx_delta, self._ec_slaves_last or '',
            self._kernel_delta['kernel_wc_zero'],
            self._kernel_delta['kernel_unmatched'],
            self._kernel_delta['kernel_skipped'],
            self._kernel_delta['kernel_timed_out'],
        ])
        # Deltas are per-row; reset after writing.
        for k in self._kernel_delta:
            self._kernel_delta[k] = 0
        self._ec_lost_delta = 0
        self._ec_tx_delta = 0

    def _print_summary(self) -> None:
        elapsed_min = (time.time() - self._t_zero) / 60.0
        self.get_logger().info(
            f'[soak +{elapsed_min:6.1f} min] '
            f'frames={self._frame_count_total} '
            f'sw_bit11={self._sw_bit11_total} '
            f'sw_bit13={self._sw_bit13_total} '
            f'overtravel={self._overtravel_total}'
            + (f' last={self._last_overtravel_joint}' if self._last_overtravel_joint else '')
            + f' jtc_overrun={self._diag_overrun_total}'
            + f' ec_lost={self._ec_lost_frames_last} ec_tx_err={self._ec_tx_errors_last}'
            + f' kernel(wc0/unm/skp/to)={self._kernel_totals["kernel_wc_zero"]}'
            f'/{self._kernel_totals["kernel_unmatched"]}'
            f'/{self._kernel_totals["kernel_skipped"]}'
            f'/{self._kernel_totals["kernel_timed_out"]}'
        )

    def _poll_ethercat_and_kernel(self) -> None:
        self._poll_ethercat()
        self._poll_kernel()

    def _poll_ethercat(self) -> None:
        try:
            res = subprocess.run(
                [str(self.get_parameter('ethercat_binary').value), 'master'],
                check=False, capture_output=True, text=True, timeout=3.0,
            )
        except FileNotFoundError:
            self.get_logger().warn(
                'ethercat binary not found — set parameter ethercat_binary '
                'or add /usr/local/bin to PATH.'
            )
            return
        except subprocess.TimeoutExpired:
            self.get_logger().warn('ethercat master timed out (3 s)')
            return
        if res.returncode != 0:
            self.get_logger().warn(
                f'ethercat master exited {res.returncode}: {res.stderr.strip()}'
            )
            return

        # Sum across all devices — single-NIC bring-up has one, but a
        # redundant setup could have two and we want the total.
        lost = sum(int(x) for x in _EC_LOST_FRAMES.findall(res.stdout))
        tx_err = sum(int(x) for x in _EC_TX_ERRORS.findall(res.stdout))
        slaves = _EC_SLAVES_OP.search(res.stdout)
        self._ec_slaves_last = int(slaves.group(1)) if slaves else None

        if self._ec_lost_frames_baseline is None:
            self._ec_lost_frames_baseline = lost
            self._ec_tx_errors_baseline = tx_err
            self._ec_lost_frames_last = lost
            self._ec_tx_errors_last = tx_err
            return

        self._ec_lost_delta = lost - (self._ec_lost_frames_last or lost)
        self._ec_tx_delta = tx_err - (self._ec_tx_errors_last or tx_err)
        self._ec_lost_frames_last = lost
        self._ec_tx_errors_last = tx_err

    def _poll_kernel(self) -> None:
        if self._kernel_disabled:
            return
        try:
            res = subprocess.run(
                ['journalctl', '-k', '--since',
                 f'@{int(self._kernel_last_check_unix)}',
                 '--no-pager', '-q'],
                check=False, capture_output=True, text=True, timeout=5.0,
            )
        except FileNotFoundError:
            self.get_logger().warn(
                'journalctl not available — kernel WC counters disabled'
            )
            self._kernel_disabled = True
            return
        except subprocess.TimeoutExpired:
            self.get_logger().warn('journalctl timed out (5 s)')
            return
        if res.returncode != 0:
            # Could be a permission issue. Don't spam the log — flip
            # the disabled bit and move on.
            self.get_logger().warn(
                f'journalctl exited {res.returncode}; disabling kernel counters'
            )
            self._kernel_disabled = True
            return

        self._kernel_last_check_unix = time.time()
        lines = res.stdout.splitlines()
        for key, pat in _EC_KERNEL_PATTERNS.items():
            n = sum(1 for line in lines if pat.search(line))
            self._kernel_delta[key] += n
            self._kernel_totals[key] += n

    # ----- shutdown -----

    def destroy_node(self) -> bool:
        try:
            self._csv_file.flush()
            self._csv_file.close()
        except Exception:
            pass
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = SoakMonitor()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
