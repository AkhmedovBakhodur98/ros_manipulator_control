#!/usr/bin/env python3
"""
Launch file for REST API Bridge server
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    # Package directories
    pkg_share = FindPackageShare('rest_api_bridge')

    # Paths
    config_file = PathJoinSubstitution([
        pkg_share, 'config', 'rest_api_config.yaml'
    ])

    # Launch arguments
    use_sim_time = LaunchConfiguration('use_sim_time')

    # Declare arguments
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation clock if true'
    )

    # REST API server node
    rest_api_server_node = Node(
        package='rest_api_bridge',
        executable='rest_api_server',
        name='rest_api_bridge',
        output='screen',
        parameters=[
            {'use_sim_time': use_sim_time},
            config_file
        ]
    )

    return LaunchDescription([
        declare_use_sim_time,
        rest_api_server_node
    ])
