#!/usr/bin/env python3
"""
AR4 display-only launch file

Launches robot_state_publisher + joint_state_publisher_gui + RViz2
for manual joint manipulation. No ros2_control, no hardware.

Usage:
    ros2 launch manipulator_bringup ar4_display.launch.py
    ros2 launch manipulator_bringup ar4_display.launch.py rviz:=false
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    ar4_pkg_share = FindPackageShare('ar4_description')

    urdf_file = PathJoinSubstitution([ar4_pkg_share, 'urdf', 'robot.urdf.xacro'])
    rviz_config_file = PathJoinSubstitution([ar4_pkg_share, 'rviz', 'ar4.rviz'])

    use_rviz = LaunchConfiguration('rviz')

    declare_rviz = DeclareLaunchArgument(
        'rviz',
        default_value='true',
        description='Launch RViz2 if true'
    )

    robot_description_content = ParameterValue(
        Command(['xacro ', urdf_file, ' use_ros2_control:=false']),
        value_type=str
    )

    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{'robot_description': robot_description_content}]
    )

    joint_state_publisher_gui_node = Node(
        package='joint_state_publisher_gui',
        executable='joint_state_publisher_gui',
        name='joint_state_publisher_gui',
        output='screen'
    )

    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config_file],
        condition=IfCondition(use_rviz)
    )

    return LaunchDescription([
        declare_rviz,
        robot_state_publisher_node,
        joint_state_publisher_gui_node,
        rviz_node
    ])
