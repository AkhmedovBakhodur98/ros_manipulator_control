# Documentation Overview

This directory contains comprehensive documentation for the manipulator ROS2 control system, including both the main manipulator and the SCARA arm modules.

---

## Documentation Structure

```
docs/
├── README.md                          # This file
├── manipulator_description/           # Main manipulator documentation
│   ├── frames_reference.md            # Coordinate frame reference
│   ├── package_structure.md           # Package structure and files
│   └── yaml_to_urdf.md                # Parameter flow from YAML to URDF
└── scara_description/                  # SCARA arm documentation
    ├── CHANGELOG.md                   # Recent changes and updates
    ├── configuration.md               # Configuration guide
    ├── integration.md                 # Integration with other robots
    ├── package_structure.md            # Package structure and files
    └── ros2_control.md                # ros2_control integration
```

---

## Quick Navigation

### For New Users

**Getting Started:**
1. Start with [manipulator_description/package_structure.md](manipulator_description/package_structure.md) to understand the main system
2. Read [scara_description/package_structure.md](scara_description/package_structure.md) to learn about the SCARA module
3. Review [scara_description/integration.md](scara_description/integration.md) to see how components work together

**Configuration:**
- [scara_description/configuration.md](scara_description/configuration.md) - Configure SCARA parameters
- [manipulator_description/yaml_to_urdf.md](manipulator_description/yaml_to_urdf.md) - Understand parameter system

**Control:**
- [scara_description/ros2_control.md](scara_description/ros2_control.md) - Control SCARA with ros2_control

**Reference:**
- [manipulator_description/frames_reference.md](manipulator_description/frames_reference.md) - Frame coordinate systems

---

## Manipulator Description Documentation

### [frames_reference.md](manipulator_description/frames_reference.md)
**Purpose:** Reference guide for coordinate frames in the manipulator system.

**Contents:**
- Coordinate system conventions (ROS REP-103)
- Frame chain from `world` to `picker_frame`
- `picker_frame` coordinate system details
- SCARA mount offset explanations
- Common mount configurations
- How to visualize frames in RViz

**When to read:** When you need to understand where to mount attachments or understand frame relationships.

---

### [package_structure.md](manipulator_description/package_structure.md)
**Purpose:** Complete overview of the manipulator_description package structure and files.

**Contents:**
- Package organization
- File descriptions (CMakeLists.txt, package.xml, config files, launch files, meshes, URDF/xacro)
- Robot kinematic structure (links and joints)
- Usage examples
- Dependencies
- ros2_control architecture
- Control examples

**When to read:** First document to read for understanding the manipulator system. Essential for developers.

---

### [yaml_to_urdf.md](manipulator_description/yaml_to_urdf.md)
**Purpose:** Deep dive into how parameters flow from YAML configuration files to URDF.

**Contents:**
- How xacro works (Python-based XML preprocessor)
- YAML loading mechanism (`xacro.load_yaml()`)
- Parameter access patterns
- Complete data flow examples
- Python expressions in xacro
- Debugging tips

**When to read:** When you need to modify parameters, understand the configuration system, or debug parameter issues.

---

## SCARA Description Documentation

### [CHANGELOG.md](scara_description/CHANGELOG.md)
**Purpose:** Recent changes and updates to the SCARA arm package.

**Contents:**
- Latest ros2_control integration
- New files created
- Modified files
- Features added
- Usage examples
- Configuration changes

**When to read:** To stay updated on recent changes or understand what's new in the package.

---

### [configuration.md](scara_description/configuration.md)
**Purpose:** Complete guide to configuring SCARA arm parameters.

**Contents:**
- Configuration file structure (`scara_params.yaml`)
- Mount configuration (position and orientation offsets)
- Kinematics configuration (link lengths L1, L2)
- Links configuration (mesh, color, inertial properties)
- Joints configuration (limits, dynamics)
- Complete configuration examples
- Common modifications
- Validation methods

**When to read:** When you need to customize SCARA parameters, adjust mount position, or modify joint limits.

---

### [integration.md](scara_description/integration.md)
**Purpose:** Guide for integrating the SCARA arm with other robots.

**Contents:**
- Understanding parent frames
- Step-by-step integration process
- Configuration options
- Common integration patterns
- Mount offset configuration
- Integration with manipulator_description
- Troubleshooting
- Advanced topics (link prefixes)
- API reference

**When to read:** When you want to attach SCARA to a different robot or understand how it integrates with the manipulator.

---

### [package_structure.md](scara_description/package_structure.md)
**Purpose:** Complete overview of the scara_description package structure and files.

**Contents:**
- Package organization
- File descriptions (build files, config files, launch files, meshes, URDF/xacro)
- Robot kinematic structure
- SCARA kinematics (workspace, joint specifications, forward kinematics)
- Usage examples
- Integration examples
- Dependencies
- ROS2 topics

**When to read:** First document to read for understanding the SCARA system. Essential for developers.

---

### [ros2_control.md](scara_description/ros2_control.md)
**Purpose:** Complete documentation for ros2_control integration with SCARA.

**Contents:**
- Architecture overview
- Files created for ros2_control
- Standalone usage
- Integration with manipulator_description
- Hardware interface (mock and real hardware)
- Joint limits
- Topics and actions
- Troubleshooting
- Configuration changes

**When to read:** When you need to control SCARA programmatically, understand the control architecture, or integrate with real hardware.

---

## Documentation by Use Case

### I want to...

**...understand the overall system:**
- Start with [manipulator_description/package_structure.md](manipulator_description/package_structure.md)
- Then read [scara_description/package_structure.md](scara_description/package_structure.md)

**...integrate SCARA with my robot:**
- Read [scara_description/integration.md](scara_description/integration.md)
- Reference [manipulator_description/frames_reference.md](manipulator_description/frames_reference.md) for frame understanding

**...configure SCARA parameters:**
- Read [scara_description/configuration.md](scara_description/configuration.md)
- Reference [manipulator_description/yaml_to_urdf.md](manipulator_description/yaml_to_urdf.md) for parameter system details

**...control SCARA programmatically:**
- Read [scara_description/ros2_control.md](scara_description/ros2_control.md)

**...understand coordinate frames:**
- Read [manipulator_description/frames_reference.md](manipulator_description/frames_reference.md)

**...modify or extend the system:**
- Read [manipulator_description/yaml_to_urdf.md](manipulator_description/yaml_to_urdf.md) for parameter system
- Read package structure documents for file organization

**...see what's new:**
- Read [scara_description/CHANGELOG.md](scara_description/CHANGELOG.md)

---

## Key Concepts

### Coordinate Frames
All frames follow **ROS REP-103** convention:
- **X** = Forward (red axis in RViz)
- **Y** = Left (green axis in RViz)
- **Z** = Up (blue axis in RViz)

See [manipulator_description/frames_reference.md](manipulator_description/frames_reference.md) for details.

### Parameter System
Parameters are defined in YAML files and loaded into URDF via xacro:
- `manipulator_params.yaml` - Main manipulator parameters
- `scara_params.yaml` - SCARA arm parameters

See [manipulator_description/yaml_to_urdf.md](manipulator_description/yaml_to_urdf.md) for how this works.

### ros2_control Integration
Both manipulator and SCARA support ros2_control:
- Independent controllers for each subsystem
- Action-based trajectory control
- Mock hardware interfaces for testing

See [scara_description/ros2_control.md](scara_description/ros2_control.md) for SCARA control details.

---

## Package Relationships

```
manipulator_description (main system)
    │
    ├── Base assembly (rail + carriage)
    ├── Selector assembly (vertical lift + gripper)
    ├── Picker assembly (fine adjustment)
    │
    └── scara_description (optional module)
        └── SCARA arm (3-DOF arm)
            └── Attaches to picker_frame
```

The SCARA arm is a **modular, reusable component** that can be:
- Used standalone
- Attached to manipulator_description
- Integrated with other robots

---

## Quick Reference

### Launch Commands

**Manipulator only:**
```bash
ros2 launch manipulator_description display.launch.py
ros2 launch manipulator_description manipulator_control.launch.py
```

**Manipulator with SCARA:**
```bash
ros2 launch manipulator_description display.launch.py use_scara:=true
ros2 launch manipulator_description manipulator_control.launch.py use_scara:=true
```

**SCARA standalone:**
```bash
ros2 launch scara_description display.launch.py
ros2 launch scara_description scara_control.launch.py
```

### Configuration Files

- `src/manipulator_description/config/manipulator_params.yaml` - Main manipulator parameters
- `src/scara_description/config/scara_params.yaml` - SCARA parameters
- `src/manipulator_description/config/manipulator_controllers.yaml` - Manipulator controllers
- `src/scara_description/config/scara_controllers.yaml` - SCARA controllers

### Key Links

- `picker_frame` - Default parent for SCARA mounting
- `scara_base_link` - SCARA mounting point
- `tcp_link` - SCARA tool center point

---

## Contributing

When adding or modifying documentation:

1. **Keep it organized:** Place documentation in the appropriate package subdirectory
2. **Be consistent:** Follow the existing documentation style and structure
3. **Include examples:** Provide practical usage examples
4. **Cross-reference:** Link to related documents
5. **Update this README:** Add new documents to the appropriate sections

---

## Questions?

If you have questions about:
- **System architecture:** See package structure documents
- **Configuration:** See configuration guides
- **Integration:** See integration guides
- **Control:** See ros2_control documentation
- **Frames:** See frames reference

For code-related questions, refer to the source code in `src/manipulator_description/` and `src/scara_description/`.

