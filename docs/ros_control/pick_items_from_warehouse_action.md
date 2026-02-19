# PickItemsFromWarehouse Action — Architectural Design

## Overview

The **PickItemsFromWarehouse** action server orchestrates picking medicines from an extracted box and placing them into a shipping container. It uses the SCARA arm to perform pick-and-place operations. Vision data is provided through a pluggable provider interface — currently a mock implementation that returns configurable positions, designed to be replaced with real vision services (`/FindBox`, `/ContSide`) in the future.

**Node:** `src/ros_control/src/pick_items_from_warehouse_server.py`
**Action:** `/PickItems`
**Package:** `ros_control`

---

## Position in System Data Flow

```
POST /getmedicine (REST API)
    │
    ├── GetContainer Action          ← attach shipping container
    ├── NavigateToAddress Action      ← move platform to box cell
    ├── ExtractBox Action            ← pull box out with SCARA hook
    │
    ├── PickItemsFromWarehouse Action  ◄── THIS NODE
    │       ├── VisionProvider.find_box()     (locate medicine in box)
    │       ├── ScaraClient                   (pick medicine from box)
    │       ├── VisionProvider.container_side() (find drop spot in container)
    │       └── ScaraClient                   (place medicine into container)
    │
    ├── ReturnBox Action             ← push box back into shelf
    └── PlaceContainer Action        ← return shipping container
```

---

## ROS2 Interfaces

### Action: PickItemsFromWarehouse.action

```
# Goal
ros_control/Medicament[] detection    # List of medicines to pick
ros_control/Address box               # Source box address on the shelf
---
# Result
bool success                          # true if all items picked and placed
string[] medicine_qr                  # DataMatrix codes of identified medicines
uint8 items_picked                    # Count of successfully picked items
uint8 items_total                     # Total items requested
float64 execution_time                # Total execution time (seconds)
string message                        # Result status message
---
# Feedback
string current_phase                  # Phase name (see Execution Flow)
uint8 current_item_index              # Current item (0-based)
uint8 total_items                     # Total items count
float32 progress_percentage           # Overall progress 0-100%
string message                        # Human-readable status
```

### Message: Medicament.msg

Metadata about a medicine unit to pick.

```
string image_id                       # Unique image identifier for the medicine
uint8 row_id                          # Row number within the box (0-based)
geometry_msgs/Point box_center        # Approximate center in world coordinates (meters)
```

---

## Vision Provider — Mock Architecture

Instead of creating ROS2 service interfaces (`FindBoxVision.srv`, `ContainerSide.srv`) now, vision data is provided through an internal **VisionProvider** abstraction. This keeps the same data contract that real vision services will eventually use.

### Data Classes (Python dataclasses, internal to server)

These mirror the reference architecture messages (`BoxDetection`, `MedicamentProfile`) but live as Python dataclasses inside the server module:

```python
@dataclass
class MedicamentProfile:
    length: float    # Longest horizontal dimension (meters)
    width: float     # Shortest horizontal dimension (meters)
    height: float    # Vertical dimension (meters)

@dataclass
class GraspPose:
    x: float         # Grasp X in world frame (meters)
    y: float         # Grasp Y in world frame (meters)
    z: float         # Grasp Z in world frame (meters)
    yaw: float       # Yaw rotation (radians)

@dataclass
class BoxDetection:
    grasp_pose: GraspPose
    box_center_x: float
    box_center_y: float
    box_center_z: float
    medicament: MedicamentProfile
    confidence: float          # 0.0-1.0
    approach_height: float     # Adaptive approach height (meters)
    is_valid: bool

@dataclass
class ContainerDropPoint:
    x: float         # Drop X in world frame (meters)
    y: float         # Drop Y in world frame (meters)
    z: float         # Drop Z in world frame (meters)
```

### VisionProvider Interface

```python
class VisionProvider(ABC):
    """Abstract interface for vision data. Matches future /FindBox and /ContSide services."""

    @abstractmethod
    def find_box(self, medicament: Medicament, box: Address) -> Tuple[bool, Optional[BoxDetection]]:
        """Locate a medicine in the extracted box.
        Returns (success, detection_result)."""
        ...

    @abstractmethod
    def container_side(self, item_index: int) -> Tuple[bool, Optional[ContainerDropPoint]]:
        """Find optimal drop coordinates in the shipping container.
        Returns (success, drop_point)."""
        ...
```

### MockVisionProvider

The mock implementation computes positions from config parameters and the medicine's `row_id`/`box_center`:

```python
class MockVisionProvider(VisionProvider):
    def find_box(self, medicament, box) -> Tuple[bool, Optional[BoxDetection]]:
        grasp_x = medicament.box_center.x + config['grasp_offset_x']
        grasp_y = (medicament.box_center.y
                   + config['grasp_offset_y']
                   + medicament.row_id * config['row_spacing_y'])
        grasp_z = config['grasp_z']
        # Returns BoxDetection with computed grasp_pose, confidence=1.0, is_valid=True

    def container_side(self, item_index: int) -> Tuple[bool, Optional[ContainerDropPoint]]:
        # Base container position + item_index * item_spacing_x
        x = config['place_x'] + item_index * config['item_spacing_x']
        y = config['place_y']
        z = config['place_z']
```

### Future: RealVisionProvider

When real vision services are ready, a `RealVisionProvider` will replace the mock by calling actual ROS2 services (`/FindBox`, `/ContSide`). No changes to the action server logic — just swap the provider.

---

## Key Design Decisions

### 1. VisionProvider abstraction instead of ROS2 services

Vision is accessed through an internal Python ABC (`VisionProvider`), not ROS2 service interfaces. This avoids creating `.srv` files and service infrastructure that cannot be tested yet. The `MockVisionProvider` returns configurable positions computed from medicine metadata and config offsets. When real vision nodes are ready, a `RealVisionProvider` can be plugged in with zero changes to the action server logic.

### 2. Mock computes positions from input data

The mock doesn't return hardcoded values — it derives grasp positions from:
- `medicament.box_center` (approximate world position from the goal)
- `medicament.row_id` (offset within the box via `row_spacing_y`)
- Config offsets (fine-tuning for the specific robot setup)

Drop positions use a base container position plus `item_spacing_x * item_index` to spread items across the container.

### 3. ScaraClient used directly (not via ExtractBox sub-goal)

Pick-and-place is a tight loop of small SCARA moves (approach -> pick -> transit -> place) that doesn't map to existing action servers. Using ScaraClient directly gives fine-grained control over each sub-move.

### 4. continue_on_item_failure strategy

When one medicine fails to pick (e.g., mock reports invalid detection), the server continues to the next item by default. The result reports `items_picked` vs `items_total` so the caller knows partial success. This matches warehouse workflow: it's better to pick 9/10 items than to abort entirely.

### 5. Cancellation handling

The server stores no sub-action-client goals (all interactions are ScaraClient calls which complete quickly). Cancellation is checked between items and between sub-phases within each item. On cancel, the server reports partial results.

### 6. Tool failures are non-fatal

`trigger_tool()` failures are logged as warnings but do not abort the item. This allows the full pick-and-place sequence to run in mock hardware environments where no tool service (`/scara_tool/activate`, `/scara_tool/deactivate`) is available.

### 7. Blocking sleep for settle times

Settle times after grasp/release use `time.sleep()` (blocking) instead of `asyncio.sleep()`. ROS2's `MultiThreadedExecutor` does not provide a standard asyncio event loop, so `asyncio.sleep()` raises `RuntimeError`. Blocking sleep is acceptable because the server runs in a `MultiThreadedExecutor` with `ReentrantCallbackGroup`, so one blocked thread does not stall the node.

---

## Files

### New Files

| File | Description |
|------|-------------|
| `src/ros_control/action/PickItemsFromWarehouse.action` | Action definition |
| `src/ros_control/msg/Medicament.msg` | Medicine metadata message |
| `src/ros_control/src/pick_items_from_warehouse_server.py` | Action server + VisionProvider + MockVisionProvider |
| `src/ros_control/config/pick_items_from_warehouse_config.yaml` | Server configuration |

### Modified Files

| File | Change |
|------|--------|
| `src/ros_control/CMakeLists.txt` | Add action, message, and server to build |
| `src/manipulator_bringup/launch/manipulator_bringup.launch.py` | Add server node (after scara_controller) |

---

## See Also

- [pick_items_from_warehouse_server.md](pick_items_from_warehouse_server.md) — Implementation details
- [extract_box_server.md](extract_box_server.md) — ExtractBox action server (upstream in pipeline)
