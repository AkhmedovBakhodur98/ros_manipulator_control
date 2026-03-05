from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='joy',
            executable='joy_node',
            name='joy_node',
            parameters=[{
                'deadzone': 0.1,
                'autorepeat_rate': 20.0,
            }],
        ),
        Node(
            package='ar4_control',
            executable='teleop_joy',
            name='teleop_joy',
            output='screen',
            parameters=[{
                'max_speed_j1': 0.69,
                'max_speed_j2': 0.69,
                'max_speed_j3': 0.47,
                'max_speed_j4': 0.79,
                'max_speed_j5': 3.14,
                'max_speed_j6': 0.5,
            }],
        ),
    ])
