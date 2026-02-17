# REST API Bridge — ROS2 Integration Architecture

> Based on: `ya_robot_manipulator/docs/system-architecture-full-ru.md` and current `rest_api_bridge` codebase.

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Implemented and working |
| ⚠️ | Partially implemented / needs update |
| ❌ | Not yet implemented |

---

## Contents

1. [Current State Summary](#current-state-summary)
2. [API Discrepancies](#api-discrepancies)
3. [REST → ROS2 Mapping](#rest--ros2-mapping)
4. [Composite Workflows](#composite-workflows)
5. [ROS2 Interfaces Status](#ros2-interfaces-status)
6. [Threading & Async Architecture](#threading--async-architecture)
7. [What Needs to Be Done](#what-needs-to-be-done)

---

## Current State Summary

### `rest_api_bridge` package

| Component | Status | Notes |
|-----------|--------|-------|
| FastAPI server (`api_server.py`) | ✅ | Runs in background thread alongside ROS2 spin |
| JWT auth middleware | ✅ | Bearer token, bcrypt, config-driven |
| Router: `GET /health` | ✅ | No auth required |
| Router: `GET /is_ready` | ✅ | Checks `/get_container` and `/place_container` server reachability |
| Router: `POST /getcontainer` | ✅ | Real ROS2 call to `/get_container` action |
| Router: `GET /retcontainer` | ✅ | Real ROS2 call to `/place_container` action |
| Router: `POST /get_items` | ⚠️ | Accepts task, returns `error_code: action_not_available` (ROS2 action type not implemented) |
| Router: `POST /put_items` | ⚠️ | Accepts task, returns `error_code: action_not_available` (ROS2 action type not implemented) |
| Router: `GET /task/status` | ✅ | Returns current/last task info with real-time progress |
| Router: `GET /task/cancel` | ✅ | Cancels active ROS2 goal via `cancel_goal_async()` |
| Pydantic request/response models | ✅ | Validated input/output |
| `MockService` | ✅ | Instant fake responses, usable for testing (`mock_mode: true`) |
| `RosService` (real ROS2 clients) | ✅ | Connects to `/get_container` and `/place_container`; stubs for `get_items`/`put_items` |
| `mock_mode=false` branch | ✅ | Instantiates `RosService` (default in config) |
| HTTPException re-raise in routers | ✅ | 409 Conflict propagates correctly from `RosService` |

### `ros_control` package — Action/Message definitions

| Interface | Status | Notes |
|-----------|--------|-------|
| `msg/Address.msg` | ✅ | Used in ExtractBox goal |
| `action/MoveJointGroup.action` | ✅ | Joint movement, used internally by servers |
| `action/GetContainer.action` | ✅ | Empty goal (just a trigger) |
| `action/PlaceContainer.action` | ✅ | Empty goal (just a trigger) |
| `action/NavigateToAddress.action` | ✅ | Inline address fields (not using Address msg) |
| `action/ExtractBox.action` | ✅ | Uses `ros_control/Address box` in goal |
| `msg/Medicament.msg` | ❌ | Needed for PickItemsFromWarehouse goal |
| `action/PickItemsFromWarehouse.action` | ❌ | topic `/PickItems` — pick/place medicine + return box internally |
| `action/ContainerJaws.action` | ⚠️ | Spec defines this as an action; implemented as `std_srvs/Trigger` services `/gripper/open` and `/gripper/close` in `gripper_service.py`. Called internally by `get_container_server.py` — REST bridge does not need to call it directly. |

### Action server implementations

| Server | Status | Notes |
|--------|--------|-------|
| `get_container_server.py` | ✅ | Opens gripper → moves to container → closes → lifts |
| `place_container_server.py` | ✅ | Returns container to storage |
| `navigate_to_address_server.py` | ✅ | Platform rail navigation by address |
| `extract_box_server.py` | ✅ | Calls NavigateToAddress internally + SCARA extraction |
| `move_joint_group_server.py` | ✅ | Joint group coordinated movement |
| `gripper_service.py` | ✅ | `/gripper/open` and `/gripper/close` Trigger services — controls container jaw joints; called internally by `get_container_server.py` |
| `pick_items_server.py` | ❌ | Lives in `ya_robot_manipulator` repo, not in this project |
| `return_box_server.py` | ❌ | Lives in `ya_robot_manipulator` repo, not in this project |

---

## API Discrepancies

The architecture spec (`system-architecture-full-ru.md`) and current implementation differ in several places.

| # | Spec (architecture doc) | Current implementation | Status |
|---|------------------------|----------------------|--------|
| 1 | `GET /startloading` | `GET /is_ready` | ❌ Needs alignment with WMS team |
| 2 | `POST /getmedicine` | `POST /get_items` | ❌ Needs alignment with WMS team |
| 3 | `POST /putmedicine` | `POST /put_items` | ❌ Needs alignment with WMS team |
| 4 | `GET /retcontainer` with JSON body `{"unload": bool}` | `GET /retcontainer?unload=bool` (query param) | ⚠️ Both work for GET; confirm with WMS |
| 5 | `task.current_operation` values: `getmedicine`, `putmedicine` | `get_items`, `put_items` | ❌ Must match chosen endpoint names |

---

## REST → ROS2 Mapping

### `GET /is_ready` ✅

Checks reachability of `/get_container` and `/place_container` action servers via `wait_for_server(timeout=2s)`.

```
is_ready()
    ├── wait_for_server(/get_container,    timeout=2s)  ✅
    └── wait_for_server(/place_container,  timeout=2s)  ✅
```

Returns `"ok"` when both servers are reachable, `"not ready"` otherwise.

---

### `POST /getcontainer` ✅

Calls `/get_container` action server. Returns 202 immediately, runs goal in worker thread.

```
get_container(unload: bool)
    └── /get_container action  ✅ empty goal (trigger)
          Feedback: { current_step, progress_percentage }  ← streamed to task status
          Result: { success, message, execution_time }
```

> **Note:** `unload` flag from the REST request is NOT passed to the ROS2 action
> (the current `GetContainer.action` has an empty goal). Container selection by
> `unload` type must be handled at the config level or the action server must be
> updated to accept the flag.

---

### `GET /retcontainer` ✅

Calls `/place_container` action server. Returns 202 immediately, runs goal in worker thread.

```
return_container(unload: bool)
    └── /place_container action  ✅ empty goal (trigger)
          Feedback: { current_step, progress_percentage }  ← streamed to task status
          Result: { success, message, execution_time }
```

> **Note:** Same as above — `unload` flag is not forwarded.

---

### `POST /get_items` (getmedicine) ⚠️ stub

The `PickItemsFromWarehouse` action type and server do not exist yet. The task is accepted (202) but immediately finishes with `error_code: "action_not_available"`.

```
get_items(medicine_list, box_id, task_id)
    └── stub worker: sets error_code="action_not_available", progress=0, finished_at=now
```

When `PickItemsFromWarehouse` server is implemented, this will become a real action call:

```
get_items(medicine_list, box_id, task_id)
    │
    ├── Parse box_id → Address          ← box_id format: box_{l|r}_{cabinet}_{row}_{col}
    │
    └── /PickItems action               ← ❌ server NOT exist (PickItemsFromWarehouse type)
          Goal: { detection: Medicament[], box: Address }
          Internally orchestrates:
            ExtractBox → NavigateToAddress + SCARA hook extraction
            FindBoxVision + TriggerGraspbox + ContainerSide
            ReturnBox → NavigateToAddress + SCARA push back
          Result: { success, message }
          DM scanner codes collected from /dm_scanner topic during execution.

task.medicine_qr = codes collected from /dm_scanner topic
```

---

### `POST /put_items` (putmedicine) ⚠️ stub

Same as `get_items` — task accepted, immediately fails with `error_code: "action_not_available"`.

```
put_items(medicine_list, box_id, task_id)
    └── stub worker: sets error_code="action_not_available", progress=0, finished_at=now
```

---

## Composite Workflows

### `get_items` step-by-step

```
Input: { medicine_list: [{image_id, raw_id}], box_id, task_id }

Step 1:  Parse box_id → Address
         Format: "box_l_0_2_1"
         → Address{side="left", cabinet_num=0, row=2, column=1}

Step 2:  /PickItems action  (type: PickItemsFromWarehouse)
         Goal: {
           detection: Medicament[],   ← image_id, raw_id, box_center=(0,0,0)
           box: Address
         }
         VisionNode fills actual box_center during execution.
         DM codes collected from /dm_scanner topic during execution.

         Internal orchestration (transparent to REST bridge):
           ExtractBox → NavigateToAddress + SCARA hook extraction
           FindBoxVision + TriggerGraspbox + ContainerSide
           ReturnBox → NavigateToAddress + SCARA push back

         Result: { success, message }

Output: task.medicine_qr = N DataMatrix codes from /dm_scanner
```

### `put_items` step-by-step

```
Input: { medicine_list: [{image_id, cell_id, row_id, position}], box_id, task_id }

Step 1:  Parse box_id → Address

Step 2:  /PickItems action  (type: PickItemsFromWarehouse)
         Goal: {
           detection: Medicament[],
           box: Address
         }
         Medicament.box_center carries placement coordinates:
           x = position.x_side
           y = position.y_side

         Internal orchestration (transparent to REST bridge):
           ExtractBox → NavigateToAddress + SCARA hook extraction
           SCARA place items at given coordinates
           ReturnBox → NavigateToAddress + SCARA push back
```

---

## ROS2 Interfaces Status

### Interfaces that need to be created in `ros_control`

#### `msg/Medicament.msg` ❌
```
string image_id
uint8 row_id
geometry_msgs/Point box_center
```

#### `action/PickItems.action` ❌
```
# Goal
ros_control/Medicament[] detection
ros_control/Address box
---
# Result
bool success
string message
---
# Feedback
int32 items_picked
int32 items_total
string current_step
```

#### `action/ReturnBox.action` ❌
```
# Goal
ros_control/Address box
string box_id
---
# Result
bool success
bool box_released
string returned_to_address
float64 execution_time
string message
---
# Feedback
float64 progress
string current_phase
```

### Interfaces that exist but may need updates

#### `action/GetContainer.action` ⚠️
Currently has empty goal. Architecture spec expects `container_id: string` in the goal
(to select which container to pick, from `container_storage.yaml`).
The current server ignores this and uses config directly — acceptable for now.

#### `action/NavigateToAddress.action` ⚠️
Uses inline fields (`side`, `cabinet_num`, `row`, `column`) instead of `ros_control/Address box`.
Inconsistent with `ExtractBox.action` which uses `ros_control/Address`.
Changing this would require updating `navigate_to_address_server.py` and `extract_box_server.py`.

---

## Threading & Async Architecture

### Problem

FastAPI handlers run in the uvicorn thread. ROS2 action calls require the ROS2 executor
(main thread) to be spinning to process callbacks. A naive blocking call from the
FastAPI thread would deadlock.

### Solution

```
Main Thread                     Worker Thread (one per task)
────────────────                ──────────────────────────────
rclpy.spin(node)                threading.Thread.start()
    │                                │
    │  resolves futures via spin      │  step 1: client.send_goal_async(goal)
    │ ◄──────────────────────────────┤  polls: while not future.done(): sleep(0.05)
    │                                │  step 2: goal_handle.get_result_async()
    │ ◄──────────────────────────────┤  polls: while not future.done(): sleep(0.05)
    │                                │  update task.progress
    │                                │  ... next step ...

FastAPI Thread (uvicorn)
────────────────────────
POST /get_items
    → service.get_items(request)      # launches worker thread, returns immediately
    → return AcceptedResponse(202)

GET /task/status
    → service.get_task_status()       # thread-safe read with lock
    → return TaskStatusResponse

GET /task/cancel
    → service.cancel_task()           # sets flag + calls goal_handle.cancel_goal_async()
    → return TaskCancelResponse
```

### Key implementation rules

1. **Worker thread** — one `threading.Thread` per task, daemon=True
2. **Thread-safety** — `threading.Lock` on `current_task` and `active_goal_handle`
3. **Future polling** — `while not future.done(): sleep(0.05)` — main spin resolves futures
4. **409 Conflict** — reject new task if `current_task.finished_at is None`
5. **Cancellation** — set `cancel_requested=True` + call `goal_handle.cancel_goal_async()`
6. **Re-raise HTTPException** — routers must re-raise `HTTPException` before the generic `except Exception` handler

---

## What Needs to Be Done

### Completed

1. ✅ `services/ros_service.py` — `RosService` class with action clients for `/get_container` and `/place_container`
2. ✅ `api_server.py` — `mock_mode=false` branch instantiates `RosService`
3. ✅ Routers — re-raise `HTTPException` for 409 Conflict propagation
4. ✅ Config — `mock_mode: false` is now the default
5. ✅ `get_items`/`put_items` — accept task (202), return `error_code: action_not_available`

### Remaining

#### In `ros_control` package
6. ❌ Add `msg/Medicament.msg`
7. ❌ Add `action/PickItemsFromWarehouse.action` (topic: `/PickItems`)
8. ❌ Update `CMakeLists.txt` — register new msg/action in `rosidl_generate_interfaces`

#### In `ya_robot_manipulator` repo (external)
9. ❌ Implement `/PickItems` action server in `scara_control/src/pick_item_from_storage.py`
   (type: `PickItemsFromWarehouse` — handles pick/place + ReturnBox internally)

#### In `rest_api_bridge` (when PickItems is ready)
10. ❌ Update `RosService` — replace stubs with real action clients for `get_items`/`put_items`

#### Alignment
11. ❌ Agree with WMS team on endpoint names (`/getmedicine` vs `/get_items`, etc.)
