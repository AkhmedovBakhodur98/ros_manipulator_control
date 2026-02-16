from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'rest_api_bridge'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='akhmedov',
    maintainer_email='akhmedov@example.com',
    description='REST API bridge for manipulator control with JWT authentication',
    license='MIT',
    entry_points={
        'console_scripts': [
            'rest_api_server = rest_api_bridge.api_server:main',
        ],
    },
)
