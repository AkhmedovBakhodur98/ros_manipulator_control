from setuptools import setup
from glob import glob

package_name = 'manipulator_homing'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='bakhodur',
    maintainer_email='fedoseevph1@gmail.com',
    description='Homing action server and safety/limit-monitor node for the EtherCAT manipulator.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'homing_action_server = manipulator_homing.homing_action_server:main',
            'safety_monitor = manipulator_homing.safety_monitor:main',
        ],
    },
)
