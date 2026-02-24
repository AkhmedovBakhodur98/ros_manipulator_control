# PickItemsFromWarehouse Action — Architectural Design

## Overview

The **PickItemsFromWarehouse** action server is the orchestrator for the medicine picking workflow. It extracts a box from the shelf (via `/extract_box` action), picks medicines from it using the SCARA arm, and places them into a shipping container. Vision data is provided through a pluggable provider interface — currently a mock implementation that returns configurable positions, designed to be replaced with real vision services (`/FindBox`, `/ContSide`) in the future.

**Node:** `src/ros_control/src/pick_items_from_warehouse_server.py`
**Action:** `/PickItems`
**Package:** `ros_control`

---

## Position in System Data Flow

```
POST /getmedicine (REST API)
    │
    ├── GetContainer Action              ← attach shipping container
    │
    ├── PickItemsFromWarehouse Action    ◄── THIS NODE (orchestrator)
    │       ├── ExtractBox Action              (navigate + extract box)
    │       │       ├── NavigateToAddress       (move platform to cell)
    │       │       └── ScaraClient             (hook + retract box)
    │       ├── VisionProvider.find_box()       (locate medicine in box)
    │       ├── ScaraClient                     (pick medicine from box)
    │       ├── VisionProvider.container_side() (find drop spot in container)
    │       └── ScaraClient                     (place medicine into container)
    │
    ├── ReturnBox Action                 ← push box back into shelf
    └── PlaceContainer Action            ← return shipping container
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
geometry_msgs/Point box_center        # Approximate center in SCARA base frame (meters)
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
    x: float         # Grasp X in SCARA base frame (meters)
    y: float         # Grasp Y in SCARA base frame (meters)
    z: float         # Grasp Z — picker_z axis position (meters)
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
    x: float         # Drop X in SCARA base frame (meters)
    y: float         # Drop Y in SCARA base frame (meters)
    z: float         # Drop Z — picker_z axis position (meters)
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

When real vision services are ready, a `RealVisionProvider` will replace the mock by calling actual ROS2 services (`/FindBox`, `/ContSide`). No changes to the action server logic — just swap the provider. The `mock.enabled` config flag controls which provider is used; setting it to `false` currently raises `RuntimeError` until `RealVisionProvider` is implemented.

---

## Key Design Decisions

### 1. Orchestrator pattern — PickItems calls ExtractBox

PickItemsFromWarehouse is the orchestrator for the full picking workflow. It calls `/extract_box` as a sub-action before starting the pick-and-place cycle. This means a single goal triggers the entire sequence: navigate platform → extract box → pick items → return home. Cancellation is forwarded to the active ExtractBox goal handle.

### 2. VisionProvider abstraction instead of ROS2 services

Vision is accessed through an internal Python ABC (`VisionProvider`), not ROS2 service interfaces. This avoids creating `.srv` files and service infrastructure that cannot be tested yet. The `MockVisionProvider` returns configurable positions computed from medicine metadata and config offsets. When real vision nodes are ready, a `RealVisionProvider` can be plugged in with zero changes to the action server logic. The `mock.enabled` config flag gates the provider selection.

### 3. Mock computes positions from input data

The mock doesn't return hardcoded values — it derives grasp positions from:
- `medicament.box_center` (approximate world position from the goal)
- `medicament.row_id` (offset within the box via `row_spacing_y`)
- Config offsets (fine-tuning for the specific robot setup)

Drop positions use a base container position plus `item_spacing_x * item_index` to spread items across the container.

### 4. ScaraClient used directly for pick-and-place

Pick-and-place is a tight loop of small SCARA moves (approach -> pick -> transit -> place) that doesn't map to existing action servers. Using ScaraClient directly gives fine-grained control over each sub-move. Box extraction, however, is delegated to the ExtractBox action server.

### 5. continue_on_item_failure strategy

When one medicine fails to pick (e.g., mock reports invalid detection), the server continues to the next item by default. The result reports `items_picked` vs `items_total` so the caller knows partial success. This matches warehouse workflow: it's better to pick 9/10 items than to abort entirely.

### 6. Cancellation handling with sub-goal forwarding

The server stores the active ExtractBox goal handle (`_active_extract_goal_handle`) for cancellation forwarding. During the pick-and-place phase, cancellation and per-item timeout are checked between each sub-step. On cancel, the server reports partial results.

### 7. Tool failures are non-fatal

`trigger_tool()` failures are logged as warnings but do not abort the item. This allows the full pick-and-place sequence to run in mock hardware environments where no tool service (`/scara_tool/activate`, `/scara_tool/deactivate`) is available.

### 8. Blocking sleep for settle times

Settle times after grasp/release use `time.sleep()` (blocking) instead of `asyncio.sleep()`. ROS2's `MultiThreadedExecutor` does not provide a standard asyncio event loop, so `asyncio.sleep()` raises `RuntimeError`. Blocking sleep is acceptable because the server runs in a `MultiThreadedExecutor` with `ReentrantCallbackGroup`, so one blocked thread does not stall the node.

### 9. Timeout enforcement

Both `per_item_timeout` and `total_timeout` are enforced. Total timeout is checked before each item in the main loop. Per-item timeout is checked at each cancellation checkpoint within `_pick_and_place_item`. Detection retries (`max_detection_retries`) wrap the `find_box()` call.

### 10. Two-stage approach descent

The approach uses `approach_offset_z` for an intermediate descent: safe_z → approach_z (grasp.z + offset) at approach velocity, then approach_z → pick_z (grasp.z - grasp_offset_z) at slower pick velocity. This gives controlled deceleration before contact.

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
- [extract_box_server.md](extract_box_server.md) — ExtractBox action server (called as sub-action)
