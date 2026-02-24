#!/usr/bin/env python3
"""
ScaraLockServer — lightweight distributed lock for SCARA arm access.

Provides two std_srvs/Trigger services:
  /scara_lock/acquire — returns success=True if lock granted, False if held
  /scara_lock/release — releases the lock, returns success=True
"""

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup
from std_srvs.srv import Trigger


class ScaraLockServer(Node):

    def __init__(self):
        super().__init__('scara_lock_server')

        self._held = False
        self._cb_group = ReentrantCallbackGroup()

        self.create_service(
            Trigger, '/scara_lock/acquire',
            self._acquire_cb, callback_group=self._cb_group,
        )
        self.create_service(
            Trigger, '/scara_lock/release',
            self._release_cb, callback_group=self._cb_group,
        )

        self.get_logger().info('ScaraLockServer started')

    def _acquire_cb(self, _request, response):
        if self._held:
            response.success = False
            response.message = 'Lock already held'
            self.get_logger().warn('Acquire rejected — lock already held')
        else:
            self._held = True
            response.success = True
            response.message = 'Lock acquired'
            self.get_logger().info('Lock acquired')
        return response

    def _release_cb(self, _request, response):
        if self._held:
            self._held = False
            response.success = True
            response.message = 'Lock released'
            self.get_logger().info('Lock released')
        else:
            response.success = True
            response.message = 'Lock was not held'
            self.get_logger().warn('Release called but lock was not held')
        return response


def main(args=None):
    rclpy.init(args=args)
    node = ScaraLockServer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
