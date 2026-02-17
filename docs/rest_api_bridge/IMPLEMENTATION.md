# REST API Bridge — ROS2 Integration (Implemented)

> **Status:** Implemented and tested.
> **Package modified:** `rest_api_bridge` only. No changes to `ros_control`.

---

## Overview

`RosService` connects the REST API bridge to real ROS2 action servers:

| REST endpoint | ROS2 action | Status |
|---------------|-------------|--------|
| `POST /getcontainer` | `/get_container` (`GetContainer`) | **Working** — real ROS2 call |
| `GET /retcontainer` | `/place_container` (`PlaceContainer`) | **Working** — real ROS2 call |
| `POST /get_items` | — | **Stub** — returns `error_code: action_not_available` |
| `POST /put_items` | — | **Stub** — returns `error_code: action_not_available` |
| `GET /is_ready` | `wait_for_server` on both clients | **Working** — checks server reachability |

`get_items` and `put_items` are stubs because the `PickItemsFromWarehouse` action type and server do not exist yet. They accept the task (202) and immediately fail with a clear error code.

---

## Files Changed

| # | File | Action |
|---|------|--------|
| 1 | `rest_api_bridge/services/ros_service.py` | **Created** — `RosService` class |
| 2 | `rest_api_bridge/api_server.py` | **Edited** — `mock_mode=false` branch uses `RosService` |
| 3 | `rest_api_bridge/routers/container.py` | **Edited** — re-raise `HTTPException` |
| 4 | `rest_api_bridge/routers/medicine.py` | **Edited** — re-raise `HTTPException` |
| 5 | `rest_api_bridge/routers/task.py` | **Edited** — re-raise `HTTPException` |
| 6 | `rest_api_bridge/routers/health.py` | **Edited** — add try/except with re-raise |
| 7 | `config/rest_api_config.yaml` | **Edited** — `mock_mode: false` |

---

## RosService Architecture

### Threading model

```
Main Thread                     Worker Thread (one per task)
────────────────                ──────────────────────────────
rclpy.spin(node)                threading.Thread(daemon=True)
    │                                │
    │  resolves futures via spin      │  send_goal_async(goal)
    │ ◄──────────────────────────────┤  polls: while not future.done(): sleep(0.05)
    │                                │  goal_handle.get_result_async()
    │ ◄──────────────────────────────┤  polls: while not future.done(): sleep(0.05)
    │                                │  _update_task(progress, message, ...)

FastAPI Thread (uvicorn)
────────────────────────
POST /getcontainer
    → service.get_container(request)      # _assert_not_busy() → launches worker → returns 202
GET /task/status
    → service.get_task_status()           # thread-safe read under _task_lock
GET /task/cancel
    → service.cancel_task()               # sets _cancel_requested + cancel_goal_async()
```

### Key design decisions

1. **Worker threads** — one `threading.Thread(daemon=True)` per task. FastAPI returns 202 immediately.
2. **Thread safety** — `threading.Lock` (`_task_lock`) protects `_current_task`, `_cancel_requested`, `_goal_handle`.
3. **Future polling** — worker polls `future.done()` with `sleep(0.05)`. The main thread's `rclpy.spin()` resolves futures.
4. **Feedback streaming** — `_on_feedback()` callback updates `_current_task.progress` and `message` in real-time.
5. **409 Conflict** — `_assert_not_busy()` raises `HTTPException(409)` if a task is running. Routers re-raise it.
6. **Cancellation** — `cancel_task()` sets `_cancel_requested=True`. Worker checks flag between poll iterations and calls `goal_handle.cancel_goal_async()`.
7. **Stubs** — `get_items`/`put_items` use `_run_stub_worker()` that immediately sets `error_code: action_not_available`.

### Public methods (same interface as MockService)

| Method | Description |
|--------|-------------|
| `is_ready()` | `wait_for_server(2s)` on `/get_container` and `/place_container` |
| `get_container(request)` | Sends `GetContainer.Goal()` to `/get_container` via worker thread |
| `return_container(request)` | Sends `PlaceContainer.Goal()` to `/place_container` via worker thread |
| `get_items(request)` | Accepts task, worker immediately fails with `action_not_available` |
| `put_items(request)` | Accepts task, worker immediately fails with `action_not_available` |
| `get_task_status()` | Returns current task state (thread-safe) |
| `cancel_task()` | Sets cancel flag + cancels active ROS2 goal |

---

## Router fix: HTTPException re-raise

All routers had:
```python
except Exception as e:
    raise HTTPException(status_code=500, ...)
```

This swallowed `HTTPException(409)` from `RosService._assert_not_busy()`. Fixed to:
```python
except HTTPException:
    raise
except Exception as e:
    raise HTTPException(status_code=500, ...)
```

Applied in: `container.py`, `medicine.py`, `task.py`, `health.py`.

---

## Testing results

Tested with `manipulator_bringup.launch.py` running (all action servers active).

### `/is_ready` — with servers running
```json
{"status": "ok"}
```

### `/is_ready` — without servers
```json
{"status": "not ready"}
```

### `/getcontainer` — real ROS2 execution (~8s)
```
POST /getcontainer → 202
task/status: 0%  "Opening gripper"
task/status: 25% "Moving to container"
task/status: 50% "Closing gripper"
task/status: 75% "Lifting container"
task/status: 100% "Container picked successfully"  finished_at set, error_code null
```

### `/retcontainer` — real ROS2 execution (~3s)
```
GET /retcontainer?unload=false → 202
task/status: 0%  "Moving to place position"
task/status: 33% "Opening gripper"
task/status: 66% "Retracting"
task/status: 100% "Container placed successfully"  finished_at set, error_code null
```

### `/get_items` — stub
```
POST /get_items → 202
task/status: 0%  error_code="action_not_available"
               message="get_items action is not available (ROS2 action type not implemented)"
```

### 409 Conflict — busy rejection
```
POST /getcontainer → 202  (task running)
GET  /retcontainer → 409  {"error_code": "task_in_progress", "message": "Another task is currently running"}
```

---

## Known limitations

| Issue | Detail | Resolution |
|-------|--------|------------|
| `unload` flag not forwarded | `GetContainer.action` and `PlaceContainer.action` have empty goals | Extend action goal or handle in server config |
| `container_id` not returned | `GetContainer` result does not include container QR | Update action server result definition |
| `/PickItems` server missing | `get_items` and `put_items` return `action_not_available` | Implement `PickItemsFromWarehouse` action type + server |
| No feedback for stubs | Stubs finish instantly without progress updates | Will be replaced with real action calls |

---

## Next steps

1. Create `msg/Medicament.msg` and `action/PickItemsFromWarehouse.action` in `ros_control`
2. Implement `/PickItems` action server (in `ya_robot_manipulator` repo)
3. Replace stubs in `RosService` with real action clients for `get_items`/`put_items`
