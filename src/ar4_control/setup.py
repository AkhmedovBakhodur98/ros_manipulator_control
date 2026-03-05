import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'ar4_control'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='akhmedov',
    maintainer_email='akhmedov@example.com',
    description='AR4 6-DOF arm control package',
    license='MIT',
    entry_points={
        'console_scripts': [
            'teleop_joy = ar4_control.teleop_joy:main',
        ],
    },
)
