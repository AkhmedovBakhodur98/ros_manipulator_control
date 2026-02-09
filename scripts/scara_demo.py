#!/usr/bin/env python3
"""
ScaraClient visual demo — run with the full system + RViz.

Usage:
    Terminal 1:
        ros2 launch manipulator_bringup manipulator_bringup.launch.py use_scara:=true

    Terminal 2:
        python3 scripts/scara_demo.py
"""

import time
import threading
import asyncio
import math

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup

from scara_control import ScaraClient


class ScaraDemoNode(Node):
    def __init__(self):
        super().__init__('scara_demo')
        self.cb_group = ReentrantCallbackGroup()
        self.scara = ScaraClient(self)

    async def run_demo(self):
        self.get_logger().info('=== ScaraClient Visual Demo ===')
        self.get_logger().info('Waiting 2s for joint states...')
        await asyncio.sleep(2.0)

        # Show initial state
        s, e, w = self.scara.get_joint_positions()
        x, y, phi = self.scara.get_tcp_position()
        self.get_logger().info(
            f'Initial: joints=({s:.3f}, {e:.3f}, {w:.3f}), '
            f'TCP=({x:.3f}, {y:.3f}, phi={phi:.3f})'
        )

        # --- Test 1: Move joints ---
        self.get_logger().info('')
        self.get_logger().info('--- Test 1: move_joints (shoulder=0.5, elbow=1.0) ---')
        r = await self.scara.move_joints(shoulder=0.5, elbow=1.0, velocity=0.5)
        self._log_result('move_joints', r)
        await asyncio.sleep(0.5)

        # --- Test 2: Move to point via IK ---
        self.get_logger().info('')
        self.get_logger().info('--- Test 2: move_to_point (x=0.5, y=0.15, elbow_up) ---')
        r = await self.scara.move_to_point(x=0.5, y=0.15, elbow_up=True, velocity=0.5)
        self._log_result('move_to_point', r)
        await asyncio.sleep(0.5)

        # --- Test 3: Move to point with other elbow config ---
        self.get_logger().info('')
        self.get_logger().info('--- Test 3: move_to_point (x=0.5, y=0.15, elbow_down) ---')
        r = await self.scara.move_to_point(x=0.5, y=0.15, elbow_up=False, velocity=0.5)
        self._log_result('move_to_point (elbow_down)', r)
        await asyncio.sleep(0.5)

        # --- Test 4: Move to point with orientation ---
        self.get_logger().info('')
        self.get_logger().info('--- Test 4: move_to_point (x=0.5, y=0.0, orientation=0.0) ---')
        r = await self.scara.move_to_point(
            x=0.5, y=0.0, orientation=0.0, elbow_up=True, velocity=0.5
        )
        self._log_result('move_to_point (orientation=0)', r)
        await asyncio.sleep(0.5)

        # --- Test 5: Z-axis move (if configured) ---
        if self.scara.has_z_axis():
            self.get_logger().info('')
            self.get_logger().info('--- Test 5: move_z (z=0.15) ---')
            try:
                r = await self.scara.move_z(z=0.15, velocity=0.5)
                self._log_result('move_z (0.15)', r)
                await asyncio.sleep(0.5)

                self.get_logger().info('--- Test 5b: move_z (z=0.0) ---')
                r = await self.scara.move_z(z=0.0, velocity=0.5)
                self._log_result('move_z (0.0)', r)
                await asyncio.sleep(0.5)
            except Exception as e:
                self.get_logger().warn(f'Z-axis test skipped: {e}')
        else:
            self.get_logger().info('Skipping Z-axis test (not configured)')

        # --- Test 6: Linear motion ---
        self.get_logger().info('')
        self.get_logger().info('--- Test 6: move_linear (0.5, 0.0) -> (0.5, 0.15) ---')
        # First go to start point
        await self.scara.move_to_point(x=0.5, y=0.0, elbow_up=True, velocity=0.5)
        await asyncio.sleep(0.3)
        # Linear move
        r = await self.scara.move_linear(x=0.5, y=0.15, velocity=0.05)
        self._log_result('move_linear', r)
        await asyncio.sleep(0.5)

        # --- Test 7: IK diagnostics ---
        self.get_logger().info('')
        self.get_logger().info('--- Test 7: IK diagnostics ---')
        diag = self.scara.diagnose_ik_failure(1.0, 0.0)
        self.get_logger().info(
            f'  Target (1.0, 0.0): {diag.reason}, '
            f'need to shift base by {diag.suggested_x_offset:.3f}m'
        )
        diag = self.scara.diagnose_ik_failure(0.05, 0.0)
        self.get_logger().info(f'  Target (0.05, 0.0): {diag.reason}')
        diag = self.scara.diagnose_ik_failure(0.5, 0.1)
        self.get_logger().info(f'  Target (0.5, 0.1): {diag.reason}')

        # --- Test 8: Home ---
        self.get_logger().info('')
        self.get_logger().info('--- Test 8: move_home ---')
        r = await self.scara.move_home(velocity=0.3)
        self._log_result('move_home', r)

        # Final state
        self.get_logger().info('')
        x, y, phi = self.scara.get_tcp_position()
        self.get_logger().info(f'Final TCP: ({x:.3f}, {y:.3f}, phi={phi:.3f})')
        self.get_logger().info('=== Demo complete ===')

    def _log_result(self, name: str, r):
        status = 'OK' if r.success else 'FAIL'
        self.get_logger().info(
            f'  [{status}] {name}: {r.message} '
            f'(joints={tuple(f"{v:.3f}" for v in r.joint_positions)}, '
            f'tcp=({r.tcp_position[0]:.3f}, {r.tcp_position[1]:.3f}), '
            f't={r.execution_time:.2f}s)'
        )


def main():
    rclpy.init()
    node = ScaraDemoNode()

    executor = MultiThreadedExecutor()
    executor.add_node(node)

    # Spin in background thread
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()

    # Run async demo
    try:
        asyncio.run(node.run_demo())
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
