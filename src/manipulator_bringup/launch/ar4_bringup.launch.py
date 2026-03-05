#!/usr/bin/env python3
"""
AR4 6-DOF arm standalone bringup launch file

Launches the AR4 arm with ros2_control (mock hardware) and RViz visualization.
No integration with the manipulator system - fully standalone.

Usage:
    ros2 launch manipulator_bringup ar4_bringup.launch.py
    ros2 launch manipulator_bringup ar4_bringup.launch.py rviz:=false
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
    ar4_pkg_share = FindPackageShare('ar4_description')

    # Paths
    urdf_file = PathJoinSubstitution([ar4_pkg_share, 'urdf', 'robot.urdf.xacro'])
    controllers_file = PathJoinSubstitution([ar4_pkg_share, 'config', 'ar4_controllers.yaml'])
    rviz_config_file = PathJoinSubstitution([ar4_pkg_share, 'rviz', 'ar4.rviz'])

    # Launch arguments
    use_sim_time = LaunchConfiguration('use_sim_time')
    use_rviz = LaunchConfiguration('rviz')
    serial_port = LaunchConfiguration('serial_port')
    baud_rate = LaunchConfiguration('baud_rate')

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

    declare_serial_port = DeclareLaunchArgument(
        'serial_port',
        default_value='/dev/ttyACM0',
        description='Serial port for Teensy 4.1'
    )

    declare_baud_rate = DeclareLaunchArgument(
        'baud_rate',
        default_value='115200',
        description='Baud rate for Teensy serial communication'
    )

    # Process xacro file with ros2_control enabled
    robot_description_content = ParameterValue(
        Command([
            'xacro ', urdf_file,
            ' use_ros2_control:=true',
            ' serial_port:=', serial_port,
            ' baud_rate:=', baud_rate
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

    # Spawn arm_controller (after joint_state_broadcaster)
    spawn_arm_controller = Node(
        package='controller_manager',
        executable='spawner',
        arguments=['arm_controller', '--controller-manager', '/controller_manager'],
        output='screen'
    )

    # Event handler: spawn arm_controller after joint_state_broadcaster is active
    delayed_arm_controller = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=spawn_joint_state_broadcaster,
            on_exit=[spawn_arm_controller]
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
        declare_serial_port,
        declare_baud_rate,
        # Nodes
        robot_state_publisher_node,
        controller_manager_node,
        spawn_joint_state_broadcaster,
        delayed_arm_controller,
        rviz_node
    ])
