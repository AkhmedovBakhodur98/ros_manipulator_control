#!/usr/bin/env python3
"""
Launch file for MoveJointGroup action server
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    # Package directories
    pkg_share = FindPackageShare('ros_control')
    
    # Paths
    config_file = PathJoinSubstitution([
        pkg_share, 'config', 'move_joint_group_config.yaml'
    ])
    
    # Launch arguments
    use_sim_time = LaunchConfiguration('use_sim_time')
    
    # Declare arguments
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation clock if true'
    )
    
    # MoveJointGroup action server node
    move_joint_group_server_node = Node(
        package='ros_control',
        executable='move_joint_group_server.py',
        name='move_joint_group_server',
        output='screen',
        parameters=[
            {'use_sim_time': use_sim_time},
            config_file
        ]
    )
    
    return LaunchDescription([
        declare_use_sim_time,
        move_joint_group_server_node
    ])






