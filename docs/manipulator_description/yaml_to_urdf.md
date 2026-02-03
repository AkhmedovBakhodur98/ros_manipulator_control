# How Parameters Flow from YAML to URDF

This document explains how parameters defined in `manipulator_params.yaml` are loaded and used in the URDF xacro files.

---

## Deep Dive: How Xacro Actually Works

### What is Xacro?

Xacro (XML Macro) is a **Python-based XML preprocessor**. It is NOT just a template engine - it embeds a full Python interpreter. When you run `xacro`, you are running a Python program that:

1. Parses the `.xacro` file as XML
2. Executes embedded Python expressions
3. Expands macros and substitutions
4. Outputs pure URDF XML

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  .xacro file    │ ───► │  Python/Xacro   │ ───► │  .urdf file     │
│  (XML + Python) │      │  Interpreter    │      │  (Pure XML)     │
└─────────────────┘      └─────────────────┘      └─────────────────┘
```

### The Two Expression Types

Xacro supports two different expression syntaxes that look similar but work differently:

#### 1. `$(...)` - ROS Substitution (Shell-like)
```xml
$(find manipulator_description)
```
- Executed by ROS **at runtime** or by xacro during processing
- `$(find pkg)` → Returns the filesystem path to a ROS package
- `$(arg name)` → Returns a launch argument value
- These are **string substitutions** - no math, no Python

#### 2. `${...}` - Python Expression (The Key Mechanism)
```xml
${base['base_link']['mesh']}
${2 + 3}
${params['mass'] * 9.81}
```
- Executed by xacro's **embedded Python interpreter**
- Full Python syntax supported inside `${...}`
- Can access xacro properties as Python variables
- Can call Python functions
- Returns the **evaluated result** as a string

### How `xacro.load_yaml()` Works Internally

When you write:
```xml
<xacro:property name="params" value="${xacro.load_yaml(config_file)}"/>
```

Here's what happens step-by-step:

```
Step 1: Xacro sees ${...} and knows to evaluate Python
        ↓
Step 2: Python expression: xacro.load_yaml(config_file)
        ↓
Step 3: xacro.load_yaml() is a Python function that:
        a) Opens the file at path 'config_file'
        b) Calls Python's yaml.safe_load() on file contents
        c) Returns a Python dictionary
        ↓
Step 4: The returned dict is stored in xacro property 'params'
        ↓
Step 5: 'params' is now a Python dict accessible in ${...} expressions
```

**The actual Python code inside xacro (simplified):**
```python
# Inside xacro source code
def load_yaml(filename):
    with open(filename, 'r') as f:
        return yaml.safe_load(f)
```

### How Property Access Works

After loading YAML, you have a Python dictionary. When you write:
```xml
<mass value="${base['base_link']['inertial']['mass']}"/>
```

The xacro interpreter does:

```python
# Xacro internally executes this Python:
result = base['base_link']['inertial']['mass']  # Returns: 32.4
# Then converts to string and inserts into XML:
# <mass value="32.4"/>
```

**This is pure Python dictionary access:**
```python
# Your YAML becomes this Python dict:
base = {
    'base_link': {
        'inertial': {
            'mass': 32.4,
            'origin': {
                'xyz': [2.0, 0.0, -0.045]
            }
        }
    }
}

# Accessing nested values:
base['base_link']                           # → dict with 'inertial', etc.
base['base_link']['inertial']               # → dict with 'mass', 'origin', etc.
base['base_link']['inertial']['mass']       # → 32.4 (float)
base['base_link']['inertial']['origin']['xyz']      # → [2.0, 0.0, -0.045] (list)
base['base_link']['inertial']['origin']['xyz'][0]   # → 2.0 (float)
```

### Processing Order: When Does Each Part Execute?

```
┌──────────────────────────────────────────────────────────────────────┐
│                        XACRO PROCESSING PHASES                        │
└──────────────────────────────────────────────────────────────────────┘

Phase 1: XML Parsing
├── Read .xacro file as XML document
├── Build XML tree structure
└── Identify xacro elements (<xacro:include>, <xacro:property>, etc.)

Phase 2: Include Resolution
├── Find all <xacro:include filename="..."/>
├── Recursively load and parse included files
└── Merge into single XML tree

Phase 3: Property Evaluation (THIS IS WHERE YAML LOADING HAPPENS)
├── Find all <xacro:property name="..." value="..."/>
├── Evaluate ${...} expressions using Python
│   ├── xacro.load_yaml() executes HERE
│   └── Python dicts created and stored
└── Properties become available for later expressions

Phase 4: Macro Expansion
├── Find all macro definitions <xacro:macro name="...">
├── Find all macro calls <xacro:macro_name .../>
├── Substitute macro body with parameters
└── Recursively expand nested macros

Phase 5: Expression Substitution (THIS IS WHERE VALUES INSERT)
├── Find all remaining ${...} in the XML
├── Evaluate each as Python expression
│   ├── ${base['base_link']['mesh']} → "base_link.STL"
│   └── ${params['mass'] * 2} → "64.8"
└── Replace ${...} with resulting string

Phase 6: Cleanup
├── Remove all xacro-specific elements
├── Resolve $(find ...) substitutions
└── Output pure URDF XML
```

### Concrete Execution Example

Let's trace exactly what happens when xacro processes this:

**Input file: `manipulator_base.urdf.xacro`**
```xml
<xacro:macro name="base_assembly" params="config_file">
  <xacro:property name="params" value="${xacro.load_yaml(config_file)}"/>
  <xacro:property name="base" value="${params['base_assembly']}"/>

  <link name="base_link">
    <inertial>
      <mass value="${base['base_link']['inertial']['mass']}"/>
    </inertial>
  </link>
</xacro:macro>
```

**Input file: `manipulator_params.yaml`**
```yaml
base_assembly:
  base_link:
    inertial:
      mass: 32.4
```

**Execution trace:**

```
1. Macro called with config_file = "/path/to/manipulator_params.yaml"

2. First property evaluation:
   Expression: xacro.load_yaml(config_file)
   Python executes:
     >>> import yaml
     >>> with open("/path/to/manipulator_params.yaml") as f:
     ...     result = yaml.safe_load(f)
     >>> result
     {'base_assembly': {'base_link': {'inertial': {'mass': 32.4}}}}

   params = {'base_assembly': {'base_link': {'inertial': {'mass': 32.4}}}}

3. Second property evaluation:
   Expression: params['base_assembly']
   Python executes:
     >>> params['base_assembly']
     {'base_link': {'inertial': {'mass': 32.4}}}

   base = {'base_link': {'inertial': {'mass': 32.4}}}

4. Expression substitution in <mass>:
   Expression: base['base_link']['inertial']['mass']
   Python executes:
     >>> base['base_link']['inertial']['mass']
     32.4

   String "32.4" replaces the ${...}

5. Final output:
   <link name="base_link">
     <inertial>
       <mass value="32.4"/>
     </inertial>
   </link>
```

### Why Arrays Need Index Access

YAML arrays become Python lists. You cannot directly insert a list into XML:

```yaml
origin:
  xyz: [2.0, 0.0, -0.045]
```

```python
# In Python:
origin['xyz']       # → [2.0, 0.0, -0.045]  (a list object)
origin['xyz'][0]    # → 2.0                  (a float)
origin['xyz'][1]    # → 0.0                  (a float)
origin['xyz'][2]    # → -0.045               (a float)
```

**Wrong (won't work):**
```xml
<origin xyz="${origin['xyz']}"/>
<!-- Would produce: <origin xyz="[2.0, 0.0, -0.045]"/> - Invalid! -->
```

**Correct (access each element):**
```xml
<origin xyz="${origin['xyz'][0]} ${origin['xyz'][1]} ${origin['xyz'][2]}"/>
<!-- Produces: <origin xyz="2.0 0.0 -0.045"/> - Valid! -->
```

### Python Expressions You Can Use

Since `${...}` is full Python, you can do:

```xml
<!-- Math operations -->
<mass value="${base['mass'] * 1000}"/>  <!-- kg to grams -->

<!-- String formatting -->
<mesh filename="${'mesh_' + str(index) + '.stl'}"/>

<!-- Conditionals (ternary) -->
<limit upper="${10.0 if large_robot else 5.0}"/>

<!-- List comprehension (advanced) -->
<xacro:property name="total" value="${sum([j['mass'] for j in joints])}"/>

<!-- Function calls -->
<value>${round(params['inertia'], 4)}"/>
```

### The Full Pipeline Visualization

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              COMPLETE PIPELINE                               │
└─────────────────────────────────────────────────────────────────────────────┘

   manipulator_params.yaml                    robot.urdf.xacro
   ┌────────────────────┐                    ┌────────────────────┐
   │ base_assembly:     │                    │ <robot>            │
   │   base_link:       │                    │   <xacro:include   │
   │     mass: 32.4     │                    │     manipulator/>  │
   └────────┬───────────┘                    └─────────┬──────────┘
            │                                          │
            │                                          ▼
            │                               ┌────────────────────────┐
            │                               │ manipulator.urdf.xacro │
            │                               │ <xacro:base_assembly   │
            │                               │   config_file="..."/>  │
            │                               └─────────┬──────────────┘
            │                                         │
            │         ┌───────────────────────────────┘
            │         │
            ▼         ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │                     XACRO PYTHON INTERPRETER                      │
   │                                                                   │
   │  1. yaml.safe_load(file) ──► Python dict                         │
   │                                                                   │
   │  2. params = {                                                    │
   │       'base_assembly': {                                          │
   │         'base_link': {                                            │
   │           'mass': 32.4    ◄── This is a Python float now         │
   │         }                                                         │
   │       }                                                           │
   │     }                                                             │
   │                                                                   │
   │  3. Evaluate: ${params['base_assembly']['base_link']['mass']}    │
   │               └──────────────────┬───────────────────────────┘   │
   │                                  │                                │
   │                                  ▼                                │
   │                     Python returns: 32.4                          │
   │                                  │                                │
   │                                  ▼                                │
   │                     Convert to string: "32.4"                     │
   │                                  │                                │
   │                                  ▼                                │
   │                     Insert into XML: <mass value="32.4"/>         │
   └──────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                         ┌────────────────────────┐
                         │    Generated URDF      │
                         │ <robot name="...">     │
                         │   <link name="base">   │
                         │     <mass value="32.4"/>│
                         │   </link>              │
                         │ </robot>               │
                         └────────────────────────┘
```

---

## Overview

```
┌─────────────────────────────┐
│  manipulator_params.yaml    │  ← Parameters defined here
└──────────────┬──────────────┘
               │
               │  xacro.load_yaml()
               ▼
┌─────────────────────────────┐
│  Xacro Property (dict)      │  ← Loaded as Python dictionary
└──────────────┬──────────────┘
               │
               │  ${params['key']['subkey']}
               ▼
┌─────────────────────────────┐
│  URDF XML Elements          │  ← Values inserted into URDF
└─────────────────────────────┘
```

---

## Step 1: YAML File Structure

Parameters are organized hierarchically in `config/manipulator_params.yaml`:

```yaml
base_assembly:                          # Assembly group
  base_link:                            # Link name
    mesh: "base_link.STL"               # String parameter
    color: [0.79, 0.82, 0.93, 1.0]      # Array parameter
    inertial:                           # Nested group
      mass: 32.4                        # Numeric parameter
      origin:
        xyz: [2.0, 0.0, -0.045]         # Array parameter
        rpy: [0, 0, 0]
      inertia:
        ixx: 0.027337
        ixy: -6.8056e-16
        # ... more inertia values

  base_main_frame_joint:                # Joint name
    type: "prismatic"
    origin:
      xyz: [0, 0, 0]
      rpy: [0, 0, 0]
    axis: [1, 0, 0]
    limits:
      lower: 0.0
      upper: 4.0
      effort: 2000.0
      velocity: 2.0
    dynamics:
      damping: 0.0
      friction: 0.0
```

---

## Step 2: Loading YAML in Xacro

In each xacro file, the YAML is loaded using `xacro.load_yaml()`:

```xml
<!-- File: manipulator_base.urdf.xacro -->

<xacro:macro name="base_assembly" params="config_file">

  <!-- Load entire YAML file into 'params' dictionary -->
  <xacro:property name="params" value="${xacro.load_yaml(config_file)}"/>

  <!-- Extract specific assembly section -->
  <xacro:property name="base" value="${params['base_assembly']}"/>

  <!-- Now 'base' contains all base_assembly parameters -->

</xacro:macro>
```

**What happens:**
1. `xacro.load_yaml(config_file)` reads the YAML file
2. Returns a Python dictionary
3. Stored in xacro property `params`
4. Subset extracted to `base` for convenience

---

## Step 3: Accessing Parameters in URDF Elements

Parameters are accessed using `${}` syntax with Python dictionary notation:

### Example: Link Definition

**YAML:**
```yaml
base_assembly:
  base_link:
    mesh: "base_link.STL"
    color: [0.79216, 0.81961, 0.93333, 1.0]
    inertial:
      mass: 32.4
      origin:
        xyz: [2.0, 1.1102e-16, -0.045]
        rpy: [0, 0, 0]
      inertia:
        ixx: 0.027337
        ixy: -6.8056e-16
        ixz: 1.1565e-16
        iyy: 43.222
        iyz: -4.2465e-19
        izz: 43.205
```

**Xacro:**
```xml
<link name="base_link">
  <!-- Visual geometry -->
  <visual>
    <geometry>
      <!-- Access: base['base_link']['mesh'] → "base_link.STL" -->
      <mesh filename="file://$(find manipulator_description)/meshes/manipulator/${base['base_link']['mesh']}"/>
    </geometry>
    <material name="base_link_color">
      <!-- Access: base['base_link']['color'][0] → 0.79216 -->
      <!-- Access: base['base_link']['color'][1] → 0.81961 -->
      <!-- Access: base['base_link']['color'][2] → 0.93333 -->
      <!-- Access: base['base_link']['color'][3] → 1.0 -->
      <color rgba="${base['base_link']['color'][0]} ${base['base_link']['color'][1]} ${base['base_link']['color'][2]} ${base['base_link']['color'][3]}"/>
    </material>
  </visual>

  <!-- Inertial properties -->
  <inertial>
    <!-- Access nested: base['base_link']['inertial']['origin']['xyz'][0] → 2.0 -->
    <origin
      xyz="${base['base_link']['inertial']['origin']['xyz'][0]}
           ${base['base_link']['inertial']['origin']['xyz'][1]}
           ${base['base_link']['inertial']['origin']['xyz'][2]}"
      rpy="${base['base_link']['inertial']['origin']['rpy'][0]}
           ${base['base_link']['inertial']['origin']['rpy'][1]}
           ${base['base_link']['inertial']['origin']['rpy'][2]}"/>

    <!-- Access: base['base_link']['inertial']['mass'] → 32.4 -->
    <mass value="${base['base_link']['inertial']['mass']}"/>

    <!-- Access inertia tensor components -->
    <inertia
      ixx="${base['base_link']['inertial']['inertia']['ixx']}"
      ixy="${base['base_link']['inertial']['inertia']['ixy']}"
      ixz="${base['base_link']['inertial']['inertia']['ixz']}"
      iyy="${base['base_link']['inertial']['inertia']['iyy']}"
      iyz="${base['base_link']['inertial']['inertia']['iyz']}"
      izz="${base['base_link']['inertial']['inertia']['izz']}"/>
  </inertial>
</link>
```

**Generated URDF:**
```xml
<link name="base_link">
  <visual>
    <geometry>
      <mesh filename="file:///path/to/meshes/manipulator/base_link.STL"/>
    </geometry>
    <material name="base_link_color">
      <color rgba="0.79216 0.81961 0.93333 1.0"/>
    </material>
  </visual>
  <inertial>
    <origin xyz="2.0 1.1102e-16 -0.045" rpy="0 0 0"/>
    <mass value="32.4"/>
    <inertia ixx="0.027337" ixy="-6.8056e-16" ixz="1.1565e-16"
             iyy="43.222" iyz="-4.2465e-19" izz="43.205"/>
  </inertial>
</link>
```

---

### Example: Joint Definition

**YAML:**
```yaml
base_assembly:
  base_main_frame_joint:
    type: "prismatic"
    origin:
      xyz: [0, 0, 0]
      rpy: [0, 0, 0]
    axis: [1, 0, 0]
    limits:
      lower: 0.0
      upper: 4.0
      effort: 2000.0
      velocity: 2.0
    dynamics:
      damping: 0.0
      friction: 0.0
```

**Xacro:**
```xml
<joint name="base_main_frame_joint" type="${base['base_main_frame_joint']['type']}">

  <!-- Joint origin -->
  <origin
    xyz="${base['base_main_frame_joint']['origin']['xyz'][0]}
         ${base['base_main_frame_joint']['origin']['xyz'][1]}
         ${base['base_main_frame_joint']['origin']['xyz'][2]}"
    rpy="${base['base_main_frame_joint']['origin']['rpy'][0]}
         ${base['base_main_frame_joint']['origin']['rpy'][1]}
         ${base['base_main_frame_joint']['origin']['rpy'][2]}"/>

  <parent link="base_link"/>
  <child link="main_frame"/>

  <!-- Motion axis -->
  <axis xyz="${base['base_main_frame_joint']['axis'][0]}
             ${base['base_main_frame_joint']['axis'][1]}
             ${base['base_main_frame_joint']['axis'][2]}"/>

  <!-- Joint limits -->
  <limit
    lower="${base['base_main_frame_joint']['limits']['lower']}"
    upper="${base['base_main_frame_joint']['limits']['upper']}"
    effort="${base['base_main_frame_joint']['limits']['effort']}"
    velocity="${base['base_main_frame_joint']['limits']['velocity']}"/>

  <!-- Dynamics -->
  <dynamics
    damping="${base['base_main_frame_joint']['dynamics']['damping']}"
    friction="${base['base_main_frame_joint']['dynamics']['friction']}"/>

</joint>
```

**Generated URDF:**
```xml
<joint name="base_main_frame_joint" type="prismatic">
  <origin xyz="0 0 0" rpy="0 0 0"/>
  <parent link="base_link"/>
  <child link="main_frame"/>
  <axis xyz="1 0 0"/>
  <limit lower="0.0" upper="4.0" effort="2000.0" velocity="2.0"/>
  <dynamics damping="0.0" friction="0.0"/>
</joint>
```

---

## Parameter Access Pattern Summary

| YAML Path | Xacro Access | Example Value |
|-----------|--------------|---------------|
| `base_assembly.base_link.mesh` | `${base['base_link']['mesh']}` | `"base_link.STL"` |
| `base_assembly.base_link.color[0]` | `${base['base_link']['color'][0]}` | `0.79216` |
| `base_assembly.base_link.inertial.mass` | `${base['base_link']['inertial']['mass']}` | `32.4` |
| `base_assembly.base_link.inertial.origin.xyz[0]` | `${base['base_link']['inertial']['origin']['xyz'][0]}` | `2.0` |
| `base_assembly.base_main_frame_joint.type` | `${base['base_main_frame_joint']['type']}` | `"prismatic"` |
| `base_assembly.base_main_frame_joint.limits.upper` | `${base['base_main_frame_joint']['limits']['upper']}` | `4.0` |

---

## Complete Data Flow

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         manipulator_params.yaml                             │
│                                                                             │
│  base_assembly:                                                             │
│    base_link:                                                               │
│      mesh: "base_link.STL"                                                  │
│      inertial:                                                              │
│        mass: 32.4                                                           │
└────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ config_file parameter passed to macro
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                      manipulator.urdf.xacro                                 │
│                                                                             │
│  <xacro:base_assembly                                                       │
│    config_file="$(find manipulator_description)/config/manipulator_params.yaml"/>│
└────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ config_file received by macro
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                    manipulator_base.urdf.xacro                              │
│                                                                             │
│  <xacro:macro name="base_assembly" params="config_file">                    │
│                                                                             │
│    <!-- Step 1: Load YAML file -->                                          │
│    <xacro:property name="params" value="${xacro.load_yaml(config_file)}"/>  │
│                                                                             │
│    <!-- Step 2: Extract assembly section -->                                │
│    <xacro:property name="base" value="${params['base_assembly']}"/>         │
│                                                                             │
│    <!-- Step 3: Use parameters in URDF elements -->                         │
│    <link name="base_link">                                                  │
│      <visual>                                                               │
│        <mesh filename=".../${base['base_link']['mesh']}"/>                  │
│      </visual>                                                              │
│      <inertial>                                                             │
│        <mass value="${base['base_link']['inertial']['mass']}"/>             │
│      </inertial>                                                            │
│    </link>                                                                  │
│                                                                             │
│  </xacro:macro>                                                             │
└────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ xacro processes and substitutes values
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                         Generated URDF                                      │
│                                                                             │
│  <link name="base_link">                                                    │
│    <visual>                                                                 │
│      <mesh filename=".../base_link.STL"/>                                   │
│    </visual>                                                                │
│    <inertial>                                                               │
│      <mass value="32.4"/>                                                   │
│    </inertial>                                                              │
│  </link>                                                                    │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## File Relationships

```
robot.urdf.xacro
    │
    ├── includes materials.xacro
    │
    ├── includes manipulator/manipulator.urdf.xacro
    │       │
    │       ├── includes manipulator_base.urdf.xacro
    │       │       └── loads config/manipulator_params.yaml
    │       │           └── uses params['base_assembly']
    │       │
    │       ├── includes manipulator_selector.urdf.xacro
    │       │       └── loads config/manipulator_params.yaml
    │       │           └── uses params['selector_assembly']
    │       │
    │       └── includes manipulator_picker.urdf.xacro
    │               └── loads config/manipulator_params.yaml
    │                   └── uses params['picker_assembly']
    │
    └── calls <xacro:manipulator config_file="...manipulator_params.yaml"/>
```

---

## Why This Architecture?

### Benefits of YAML + Xacro

| Benefit | Description |
|---------|-------------|
| **Separation of concerns** | Parameters in YAML, structure in Xacro |
| **Easy updates** | Change values in YAML without editing XML |
| **Single source of truth** | All parameters in one file |
| **Readable** | YAML is cleaner than XML for configuration |
| **Maintainable** | Update CAD values without understanding Xacro |
| **Reusable** | Same Xacro with different YAML for variants |

### When to Edit Each File

| Task | Edit File |
|------|-----------|
| Change mass, inertia, colors | `manipulator_params.yaml` |
| Change joint limits | `manipulator_params.yaml` |
| Change mesh filename | `manipulator_params.yaml` |
| Add new link/joint | Both YAML and Xacro |
| Change robot structure | Xacro files |
| Change parameter names | Both YAML and Xacro |

---

## Debugging Tips

### View Generated URDF
```bash
ros2 run xacro xacro src/manipulator_description/urdf/robot.urdf.xacro
```

### Check for YAML Errors
```bash
python3 -c "import yaml; yaml.safe_load(open('src/manipulator_description/config/manipulator_params.yaml'))"
```

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `KeyError: 'xxx'` | Typo in parameter name | Check YAML key spelling |
| `list index out of range` | Array index wrong | Check array length in YAML |
| `could not find file` | Wrong config_file path | Check `$(find ...)` path |
| `None has no attribute` | Missing YAML section | Add missing parameter to YAML |
