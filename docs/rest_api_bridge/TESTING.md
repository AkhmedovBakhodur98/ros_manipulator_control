# REST API Bridge - Testing Guide

Complete testing guide with examples for the REST API Bridge.

## Starting the Server

```bash
# Build the package
cd ~/manipulator_ros_control
colcon build --packages-select rest_api_bridge
source install/setup.bash

# Start the server
ros2 run rest_api_bridge rest_api_server
```

**Expected output:**
```
[INFO] [rest_api_bridge]: Configuration loaded
[INFO] [rest_api_bridge]: Mock mode: True
[INFO] [rest_api_bridge]: Auth enabled: True
[INFO] [rest_api_bridge]: Using mock service implementation
[INFO] [rest_api_bridge]: CORS enabled
[INFO] [rest_api_bridge]: FastAPI application configured
[INFO] [rest_api_bridge]: Starting REST API server on 0.0.0.0:8080
[INFO] [rest_api_bridge]: API docs available at: http://0.0.0.0:8080/api/v1/docs
[INFO] [rest_api_bridge]: REST API server started successfully
[INFO] [rest_api_bridge]: ROS2 node spinning...
```

---

## Test Endpoints

### 1. Health Check (No Auth)

```bash
curl http://localhost:8080/api/v1/health | python3 -m json.tool
```

**Expected:**
```json
{
    "status": "ok"
}
```

---

### 2. Get JWT Token

```bash
curl -X POST http://localhost:8080/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "wms_system", "client_secret": "demo_secret_2024"}' | python3 -m json.tool
```

**Expected:**
```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 3600
}
```

**Save token for next requests:**
```bash
TOKEN=$(curl -s -X POST http://localhost:8080/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "wms_system", "client_secret": "demo_secret_2024"}' | \
  python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
```

---

### 3. Start Loading Check

```bash
curl http://localhost:8080/api/v1/is_ready \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**Expected:**
```json
{
    "status": "ok"
}
```

---

### 4. Get Container

```bash
curl -X POST http://localhost:8080/api/v1/getcontainer \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"unload": false}' | python3 -m json.tool
```

**Expected (HTTP 202):**
```json
{
    "status": "ok",
    "accepted": true
}
```

**Check task status:**
```bash
curl http://localhost:8080/api/v1/task/status \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**Expected:**
```json
{
    "status": "ok",
    "task": {
        "task_id": "38b32a48-30a0-4be3-8c1d-fae9d11af94e",
        "progress": 100,
        "current_operation": "getcontainer",
        "started_at": "2026-02-16T10:20:53.623178",
        "updated_at": "2026-02-16T10:20:53.623183",
        "finished_at": "2026-02-16T10:20:53.623185",
        "error_code": null,
        "message": "Container retrieved successfully (mock)",
        "medicine_qr": [],
        "container_id": "CNT-BBADD933"
    }
}
```

---

### 5. Return Container

```bash
curl "http://localhost:8080/api/v1/retcontainer?unload=true" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**Expected (HTTP 202):**
```json
{
    "status": "ok",
    "accepted": true
}
```

**Note:** This is a GET request with query parameter, not POST!

---

### 6. Get Medicine

```bash
curl -X POST http://localhost:8080/api/v1/get_items \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "medicine_list": [
      {"image_id": "med-001", "raw_id": 0},
      {"image_id": "med-002", "raw_id": 1}
    ],
    "box_id": "BOX-12345",
    "task_id": "task-001"
  }' | python3 -m json.tool
```

**Expected (HTTP 202):**
```json
{
    "status": "ok",
    "accepted": true
}
```

**Check task status:**
```bash
curl http://localhost:8080/api/v1/task/status \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**Expected:**
```json
{
    "status": "ok",
    "task": {
        "task_id": "task-001",
        "progress": 100,
        "current_operation": "get_items",
        "started_at": "2026-02-16T10:21:03.843498",
        "updated_at": "2026-02-16T10:21:03.843509",
        "finished_at": "2026-02-16T10:21:03.843513",
        "error_code": null,
        "message": "Retrieved 2 medicine(s) from BOX-12345 (mock)",
        "medicine_qr": [
            "DM-FB75BFD1A76A",
            "DM-8781738E8D5F"
        ],
        "container_id": null
    }
}
```

**Note:** `medicine_qr` array contains DataMatrix IDs for extracted medicines!

---

### 7. Put Medicine

```bash
curl -X POST http://localhost:8080/api/v1/put_items \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "medicine_list": [
      {
        "image_id": "med-001",
        "cell_id": 0,
        "row_id": 2,
        "position": {"x_side": 0.5, "y_side": 1.2}
      }
    ],
    "box_id": "BOX-67890",
    "task_id": "task-002"
  }' | python3 -m json.tool
```

**Expected (HTTP 202):**
```json
{
    "status": "ok",
    "accepted": true
}
```

---

### 8. Task Cancel

```bash
curl http://localhost:8080/api/v1/task/cancel \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**Expected:**
```json
{
    "status": "ok"
}
```

---

## Complete Test Script

Save this as `test_api.sh`:

```bash
#!/bin/bash

BASE_URL="http://localhost:8080/api/v1"

echo "=== 1. Health Check ==="
curl -s "$BASE_URL/health" | python3 -m json.tool

echo -e "\n=== 2. Get JWT Token ==="
TOKEN=$(curl -s -X POST "$BASE_URL/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"client_id": "wms_system", "client_secret": "demo_secret_2024"}' | \
  python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

echo "Token: ${TOKEN:0:50}..."

echo -e "\n=== 3. Start Loading ==="
curl -s "$BASE_URL/is_ready" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo -e "\n=== 4. Get Container ==="
curl -s -X POST "$BASE_URL/getcontainer" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"unload": false}' | python3 -m json.tool

echo -e "\n=== 5. Task Status (after getcontainer) ==="
curl -s "$BASE_URL/task/status" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo -e "\n=== 6. Get Medicine ==="
curl -s -X POST "$BASE_URL/get_items" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "medicine_list": [
      {"image_id": "med-001", "raw_id": 0},
      {"image_id": "med-002", "raw_id": 1}
    ],
    "box_id": "BOX-12345",
    "task_id": "task-get-001"
  }' | python3 -m json.tool

echo -e "\n=== 7. Task Status (after get_items) ==="
curl -s "$BASE_URL/task/status" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo -e "\n=== 8. Put Medicine ==="
curl -s -X POST "$BASE_URL/put_items" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "medicine_list": [{
      "image_id": "med-001",
      "cell_id": 0,
      "row_id": 2,
      "position": {"x_side": 0.5, "y_side": 1.2}
    }],
    "box_id": "BOX-67890",
    "task_id": "task-put-001"
  }' | python3 -m json.tool

echo -e "\n=== 9. Return Container ==="
curl -s "$BASE_URL/retcontainer?unload=true" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo -e "\n=== 10. Task Cancel ==="
curl -s "$BASE_URL/task/cancel" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo -e "\nAll tests completed!"
```

**Run it:**
```bash
chmod +x test_api.sh
./test_api.sh
```

---

## Python Test Script

```python
#!/usr/bin/env python3
import requests
import json

BASE_URL = "http://localhost:8080/api/v1"

def test_api():
    # 1. Health check
    print("=== 1. Health Check ===")
    response = requests.get(f"{BASE_URL}/health")
    print(json.dumps(response.json(), indent=2))

    # 2. Get token
    print("\n=== 2. Get Token ===")
    auth_response = requests.post(
        f"{BASE_URL}/auth/token",
        json={"client_id": "wms_system", "client_secret": "demo_secret_2024"}
    )
    token = auth_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"Token: {token[:50]}...")

    # 3. Start loading
    print("\n=== 3. Start Loading ===")
    response = requests.get(f"{BASE_URL}/is_ready", headers=headers)
    print(json.dumps(response.json(), indent=2))

    # 4. Get container
    print("\n=== 4. Get Container ===")
    response = requests.post(
        f"{BASE_URL}/getcontainer",
        headers=headers,
        json={"unload": False}
    )
    print(f"Status Code: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

    # 5. Check task status
    print("\n=== 5. Task Status ===")
    response = requests.get(f"{BASE_URL}/task/status", headers=headers)
    task = response.json()
    print(json.dumps(task, indent=2))
    print(f"Container ID: {task['task']['container_id']}")

    # 6. Get medicine
    print("\n=== 6. Get Medicine ===")
    response = requests.post(
        f"{BASE_URL}/get_items",
        headers=headers,
        json={
            "medicine_list": [
                {"image_id": "med-001", "raw_id": 0},
                {"image_id": "med-002", "raw_id": 1}
            ],
            "box_id": "BOX-12345",
            "task_id": "task-001"
        }
    )
    print(f"Status Code: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

    # 7. Check task status with medicine QR
    print("\n=== 7. Task Status (with medicine QR) ===")
    response = requests.get(f"{BASE_URL}/task/status", headers=headers)
    task = response.json()
    print(f"Medicine QR codes: {task['task']['medicine_qr']}")

    # 8. Put medicine
    print("\n=== 8. Put Medicine ===")
    response = requests.post(
        f"{BASE_URL}/put_items",
        headers=headers,
        json={
            "medicine_list": [{
                "image_id": "med-001",
                "cell_id": 0,
                "row_id": 2,
                "position": {"x_side": 0.5, "y_side": 1.2}
            }],
            "box_id": "BOX-67890",
            "task_id": "task-002"
        }
    )
    print(f"Status Code: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

    # 9. Return container
    print("\n=== 9. Return Container ===")
    response = requests.get(
        f"{BASE_URL}/retcontainer",
        headers=headers,
        params={"unload": True}
    )
    print(f"Status Code: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

    # 10. Cancel task
    print("\n=== 10. Cancel Task ===")
    response = requests.get(f"{BASE_URL}/task/cancel", headers=headers)
    print(json.dumps(response.json(), indent=2))

    print("\nAll tests completed!")

if __name__ == "__main__":
    test_api()
```

**Run it:**
```bash
chmod +x test_api.py
python3 test_api.py
```

---

## Interactive Documentation

Access Swagger UI:
```
http://localhost:8080/api/v1/docs
```

Features:
- Test all endpoints in browser
- View request/response schemas
- Automatic authentication with JWT
- No curl or code needed

---

## Troubleshooting

### Server Won't Start

**Check if port is in use:**
```bash
lsof -ti:8080
```

**Kill existing process:**
```bash
lsof -ti:8080 | xargs kill -9
```

### Authentication Fails

**Check credentials in config:**
```bash
cat install/rest_api_bridge/share/rest_api_bridge/config/rest_api_config.yaml
```

**Verify client_id and password hash match**

### Connection Refused

**Server not running. Start it:**
```bash
ros2 run rest_api_bridge rest_api_server
```

### Import Errors

**Install dependencies:**
```bash
pip3 install python-jose[cryptography] passlib 'bcrypt<4.0.0' --break-system-packages
```

---

## Expected Results Summary

| Endpoint | Method | Status | Response |
|----------|--------|--------|----------|
| /health | GET | 200 | `{"status": "ok"}` |
| /is_ready | GET | 200 | `{"status": "ok"}` |
| /getcontainer | POST | 202 | `{"status": "ok", "accepted": true}` |
| /retcontainer | GET | 202 | `{"status": "ok", "accepted": true}` |
| /get_items | POST | 202 | `{"status": "ok", "accepted": true}` |
| /put_items | POST | 202 | `{"status": "ok", "accepted": true}` |
| /task/status | GET | 200 | `{"status": "ok", "task": {...}}` |
| /task/cancel | GET | 200 | `{"status": "ok"}` |

---

## Notes

- All async operations return HTTP 202 (Accepted)
- Task status contains `medicine_qr` array after get_items
- Task status contains `container_id` after getcontainer
- `/retcontainer` is GET with query parameter, not POST!
- All timestamps are in ISO 8601 format
- JWT tokens expire after 60 minutes by default
