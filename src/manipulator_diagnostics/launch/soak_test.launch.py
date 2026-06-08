# Long-running soak test for the full 6-slave EtherCAT chain.
#
# Wraps the production ethercat_full.launch.py + sine_trajectory_driver
# + soak_monitor. A TimerAction fires Shutdown after `duration_min`
# minutes so the operator doesn't have to babysit the run end.
#
# Recommended invocation (matches the Stage 6 RT recipe):
#
#   sudo bash -c 'echo 2 > /proc/irq/56/smp_affinity'   # if not auto'd
#   chrt -f 80 ros2 launch manipulator_diagnostics soak_test.launch.py \
#       duration_min:=240 csv_path:=/tmp/soak_2026-06-09.csv
#
# cyclictest is intentionally NOT auto-started here — it needs prio 99
# (sudo) to produce useful numbers, and running it as the same process
# tree as the controllers conflates failure modes. Run it in a separate
# root shell alongside this launch:
#
#   sudo cyclictest -p 99 -t -m -i 1000 --output=/tmp/cyclictest.log

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    Shutdown,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    duration_min = LaunchConfiguration('duration_min')
    csv_path = LaunchConfiguration('csv_path')
    use_scara = LaunchConfiguration('use_scara')
    with_stress = LaunchConfiguration('with_stress')

    full_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(PathJoinSubstitution([
            FindPackageShare('manipulator_bringup'),
            'launch',
            'ethercat_full.launch.py',
        ])),
        launch_arguments={'use_scara': use_scara}.items(),
    )

    sine_driver = Node(
        package='manipulator_diagnostics',
        executable='sine_trajectory_driver',
        output='both',
        # Defaults inside the node are tuned for the bench-interactive
        # band (5-10 rpm on the motor side); override here only if the
        # operator explicitly wants a different load profile.
    )

    soak_monitor = Node(
        package='manipulator_diagnostics',
        executable='soak_monitor',
        output='both',
        parameters=[{'csv_path': csv_path}],
    )

    # Optional CPU load alongside the soak — off by default. Useful
    # if the unloaded run passes cleanly and we want a stress-aware
    # second pass. NOT recommended for the first soak: it conflates
    # bus-driver issues with CPU-contention issues.
    stress = ExecuteProcess(
        cmd=['stress-ng', '--cpu', '4', '--vm', '2', '--vm-bytes', '256M',
             '--timeout', '0'],
        output='log',
        condition=IfCondition(with_stress),
    )

    # Auto-shutdown after the configured duration. TimerAction expects
    # seconds; the float multiplication keeps fractional minutes
    # working (helpful for short smoke tests, e.g. duration_min:=0.5).
    def _shutdown_after(context, *args, **kwargs):
        secs = float(context.perform_substitution(duration_min)) * 60.0
        return [TimerAction(
            period=secs,
            actions=[Shutdown(reason=f'soak duration {secs:.0f} s reached')],
        )]

    from launch.actions import OpaqueFunction
    auto_shutdown = OpaqueFunction(function=_shutdown_after)

    return LaunchDescription([
        DeclareLaunchArgument(
            'duration_min', default_value='240.0',
            description='Soak duration in minutes; Shutdown event fires after this elapses.'),
        DeclareLaunchArgument(
            'csv_path', default_value='/tmp/soak_test.csv',
            description='Where soak_monitor writes the per-second metrics row.'),
        DeclareLaunchArgument(
            'use_scara', default_value='true',
            description='Pass-through to ethercat_full.launch.py (false = base 3 axes only).'),
        DeclareLaunchArgument(
            'with_stress', default_value='false',
            description='Run stress-ng alongside the soak (off by default — keeps the bus '
                        'measurement honest; flip on for a second pass after a clean run).'),
        full_launch,
        sine_driver,
        soak_monitor,
        stress,
        auto_shutdown,
    ])
