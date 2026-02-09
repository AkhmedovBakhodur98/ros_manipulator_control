from setuptools import find_packages, setup

package_name = 'scara_control'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='akhmedov',
    maintainer_email='akhmedov@example.com',
    description='Reusable SCARA arm control library with IK, linear motion, and optional Z-axis support',
    license='MIT',
    entry_points={},
)
