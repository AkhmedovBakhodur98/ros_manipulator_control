#!/usr/bin/env python3
"""
Launch file for SCARA arm ros2_control

This launch file:
- Processes the xacro file with ros2_control enabled
- Starts robot_state_publisher
- Starts ros2_control controller_manager
- Spawns joint_state_broadcaster
- Spawns scara_controller (JointTrajectoryController)
- Optionally launches RViz2

Usage:
    ros2 launch scara_description scara_control.launch.py
    ros2 launch scara_description scara_control.launch.py rviz:=true
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, RegisterEventHandler
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():

    # Package directories
    pkg_share = FindPackageShare('scara_description')

    # Paths
    urdf_file = PathJoinSubstitution([pkg_share, 'urdf', 'robot.urdf.xacro'])
    controllers_file = PathJoinSubstitution([pkg_share, 'config', 'scara_controllers.yaml'])
    rviz_config_file = PathJoinSubstitution([pkg_share, 'rviz', 'scara_control.rviz'])

    # Launch arguments
    use_sim_time = LaunchConfiguration('use_sim_time')
    use_rviz = LaunchConfiguration('rviz')

    # Declare arguments
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation clock if true'
    )

    declare_rviz = DeclareLaunchArgument(
        'rviz',
        default_value='true',
        description='Launch RViz2 if true'
    )

    # Process xacro file with ros2_control enabled
    robot_description_content = ParameterValue(
        Command([
            'xacro ', urdf_file,
            ' use_ros2_control:=true'
        ]),
        value_type=str
    )

    # Robot state publisher node
    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description_content,
            'use_sim_time': use_sim_time
        }]
    )

    # ros2_control controller manager
    controller_manager_node = Node(
        package='controller_manager',
        executable='ros2_control_node',
        parameters=[
            {'robot_description': robot_description_content},
            controllers_file
        ],
        output='screen'
    )

    # Spawn joint_state_broadcaster
    spawn_joint_state_broadcaster = Node(
        package='controller_manager',
        executable='spawner',
        arguments=['joint_state_broadcaster', '--controller-manager', '/controller_manager'],
        output='screen'
    )

    # Spawn scara_controller (after joint_state_broadcaster)
    spawn_scara_controller = Node(
        package='controller_manager',
        executable='spawner',
        arguments=['scara_controller', '--controller-manager', '/controller_manager'],
        output='screen'
    )

    # Event handler: spawn scara_controller after joint_state_broadcaster is active
    delayed_scara_controller = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=spawn_joint_state_broadcaster,
            on_exit=[spawn_scara_controller]
        )
    )

    # RViz2 node (optional)
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config_file],
        parameters=[{'use_sim_time': use_sim_time}],
        condition=IfCondition(use_rviz)
    )

    return LaunchDescription([
        # Arguments
        declare_use_sim_time,
        declare_rviz,
        # Nodes
        robot_state_publisher_node,
        controller_manager_node,
        spawn_joint_state_broadcaster,
        delayed_scara_controller,
        rviz_node
    ])

