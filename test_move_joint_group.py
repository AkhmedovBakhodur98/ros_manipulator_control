#!/usr/bin/env python3
"""Test script to send a goal to move_joint_group action"""

import rclpy
from rclpy.action import ActionClient
from ros_control.action import MoveJointGroup


def main():
    rclpy.init()
    node = rclpy.create_node('test_move_joint_group')
    
    # Create action client
    action_client = ActionClient(node, MoveJointGroup, '/move_joint_group')
    
    # Wait for server
    node.get_logger().info('Waiting for action server...')
    if not action_client.wait_for_server(timeout_sec=5.0):
        node.get_logger().error('Action server not available!')
        return
    
    node.get_logger().info('Action server available!')
    
    # Create goal
    goal_msg = MoveJointGroup.Goal()
    goal_msg.joint_names = [
        'base_main_frame_joint',
        'main_frame_selector_frame_joint',
        'selector_frame_picker_frame_joint'
    ]
    goal_msg.target_positions = [0.5, 0.3, 0.2]  # Move to test positions
    goal_msg.max_velocity = [0.5, 0.5, 0.5]  # Moderate speed
    
    node.get_logger().info(f'Sending goal: {goal_msg.joint_names} -> {goal_msg.target_positions}')
    
    # Send goal
    send_goal_future = action_client.send_goal_async(goal_msg)
    rclpy.spin_until_future_complete(node, send_goal_future)
    
    goal_handle = send_goal_future.result()
    if not goal_handle.accepted:
        node.get_logger().error('Goal rejected!')
        return
    
    node.get_logger().info('Goal accepted! Waiting for result...')
    
    # Get result
    result_future = goal_handle.get_result_async()
    
    # Wait for feedback
    while rclpy.ok():
        rclpy.spin_once(node, timeout_sec=0.1)
        if result_future.done():
            break
        
        # Try to get feedback
        try:
            feedback_future = goal_handle.get_feedback_async()
            rclpy.spin_once(node, timeout_sec=0.1)
            if feedback_future.done():
                feedback = feedback_future.result()
                if feedback:
                    fb = feedback.feedback
                    node.get_logger().info(
                        f'Progress: {fb.progress_percentage:.1f}% - '
                        f'Current: {[f"{p:.3f}" for p in fb.current_positions]}'
                    )
        except:
            pass
    
    result = result_future.result().result
    node.get_logger().info(f'Result: success={result.success}, error={result.position_error:.4f}')
    node.get_logger().info(f'Message: {result.message}')
    node.get_logger().info(f'Final positions: {result.final_position}')
    
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()







