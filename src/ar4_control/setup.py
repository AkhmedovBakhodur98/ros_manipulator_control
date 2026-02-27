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
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='akhmedov',
    maintainer_email='akhmedov@example.com',
    description='AR4 6-DOF arm control package (placeholder for future development)',
    license='MIT',
    entry_points={
        'console_scripts': [],
    },
)
