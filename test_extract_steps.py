#!/usr/bin/env python3
"""Step-by-step extraction test. Waits for Enter between each step."""

import asyncio
import math
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup
from scara_control.scara_client import ScaraClient
import threading


class StepTest(Node):
    def __init__(self):
        super().__init__('step_test')
        self.cb = ReentrantCallbackGroup()
        self.scara = ScaraClient(self)
        self.get_logger().info('ScaraClient ready. Starting step-by-step test...')

    async def run_steps(self):
        log = self.get_logger()

        # Config values (same as extract_box_config.yaml)
        z_offset = 0.03
        z_above_box = 0.10
        wrist_angle = math.pi / 2  # left side
        approach_x = 0.20
        approach_y = 0.22  # approach_depth(0.20) + y_inside(0.02)
        retract_x = 0.20
        retract_y = -0.38  # -overshoot for left side

        steps = [
            ('2a', f'Rotate wrist to {wrist_angle:.4f} rad'),
            ('2b', f'Raise Z +{z_offset}m (above handle plate)'),
            ('2c', f'Approach to ({approach_x}, {approach_y})'),
            ('2d', f'Lower Z -{z_offset}m (hook engages)'),
            ('2e', f'Retract to ({retract_x}, {retract_y}) with elbow flip'),
            ('2f', f'Raise Z +{z_above_box}m (disengage hook)'),
            ('2g', 'Home'),
        ]

        for step_id, desc in steps:
            log.info(f'\n>>> NEXT: Step {step_id} — {desc}')
            log.info('    Press Enter in terminal to execute...')
            await asyncio.get_event_loop().run_in_executor(None, input)

            log.info(f'--- Executing step {step_id} ---')

            if step_id == '2a':
                r = await self.scara.move_joints(wrist=wrist_angle)
            elif step_id == '2b':
                cur_z = self.scara.get_z_position()
                log.info(f'    Z: {cur_z:.4f} -> {cur_z + z_offset:.4f}')
                r = await self.scara.move_z(cur_z + z_offset, velocity=0.05)
            elif step_id == '2c':
                r = await self.scara.move_to_point(
                    x=approach_x, y=approach_y, velocity=0.5)
            elif step_id == '2d':
                cur_z = self.scara.get_z_position()
                log.info(f'    Z: {cur_z:.4f} -> {cur_z - z_offset:.4f}')
                r = await self.scara.move_z(cur_z - z_offset, velocity=0.05)
            elif step_id == '2e':
                r = await self.scara.move_linear(
                    x=retract_x, y=retract_y,
                    velocity=0.05, step_size=0.005,
                    allow_elbow_flip=True)
            elif step_id == '2f':
                cur_z = self.scara.get_z_position()
                log.info(f'    Z: {cur_z:.4f} -> {cur_z + z_above_box:.4f}')
                r = await self.scara.move_z(cur_z + z_above_box, velocity=0.05)
            elif step_id == '2g':
                r = await self.scara.move_home()

            if r.success:
                log.info(f'    Step {step_id} OK')
            else:
                log.error(f'    Step {step_id} FAILED: {r.message}')
                break

        log.info('Done. Ctrl+C to exit.')


async def main_async(node):
    await node.run_steps()


def main():
    rclpy.init()
    node = StepTest()
    executor = MultiThreadedExecutor()
    executor.add_node(node)

    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()

    asyncio.get_event_loop().run_until_complete(main_async(node))

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
