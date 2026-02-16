# REST API Bridge

REST API layer that provides HTTP/JSON endpoints for external systems (WMS) to control the robot manipulator. Built with FastAPI and integrated with ROS2.

## Features

- **FastAPI Framework**: High-performance async REST API with automatic OpenAPI documentation
- **JWT Authentication**: Secure token-based authentication for API clients
- **Mock Mode**: Test API endpoints without ROS2 dependencies
- **ROS2 Integration**: Seamless integration with existing ROS2 action servers
- **Interactive Documentation**: Auto-generated Swagger UI at `/api/v1/docs`
- **CORS Support**: Configurable cross-origin resource sharing
- **Type Validation**: Pydantic models for request/response validation

## Architecture

```
┌─────────────────┐
│   WMS System    │
│  (External)     │
└────────┬────────┘
         │ HTTP/JSON
         │ (JWT Auth)
         v
┌─────────────────────────────┐
│    REST API Bridge          │
│                             │
│  ┌──────────────────────┐  │
│  │  FastAPI Routers     │  │
│  │  - Health            │  │
│  │  - Container Ops     │  │
│  │  - Medicine Ops      │  │
│  │  - Task Management   │  │
│  └──────────┬───────────┘  │
│             │               │
│  ┌──────────v───────────┐  │
│  │  Service Layer       │  │
│  │  (Mock / ROS2)       │  │
│  └──────────┬───────────┘  │
└─────────────┼───────────────┘
              │ ROS2 Actions
              v
┌─────────────────────────────┐
│   ROS2 Action Servers       │
│  - get_container            │
│  - navigate_to_address      │
│  - extract_box              │
│  - move_joint_group         │
└─────────────────────────────┘
```

## Installation

### Dependencies

The package requires the following Python packages:

```bash
sudo apt install python3-fastapi python3-uvicorn python3-pydantic \
                 python3-jose python3-cryptography python3-passlib
```

### Build

```bash
cd ~/manipulator_ros_control
colcon build --packages-select rest_api_bridge
source install/setup.bash
```

## Configuration

Edit `config/rest_api_config.yaml`:

### Server Settings

```yaml
rest_api_bridge:
  ros__parameters:
    host: "0.0.0.0"
    port: 8080
    api_base_path: "/api/v1"
```

### Authentication Settings

#### Generate JWT Secret Key

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

#### Generate Client Password Hash

```bash
python3 -c "from passlib.context import CryptContext; \
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto'); \
print(pwd_context.hash('your_secret_here'))"
```

#### Configure Clients

```yaml
auth:
  enabled: true
  jwt:
    secret_key: "generated-secret-key"
    algorithm: "HS256"
    access_token_expire_minutes: 60
  clients:
    wms_system: "$2b$12$hashed_password"
  allowed_clients:
    - "wms_system"
```

### Operation Mode

```yaml
# Use mock mode for testing without ROS2 robot
mock_mode: true

# Set to false for real robot operations
mock_mode: false
```

## Usage

### Start Server

#### Standalone

```bash
ros2 run rest_api_bridge rest_api_server
```

#### With Launch File

```bash
ros2 launch rest_api_bridge rest_api_server.launch.py
```

### Access Documentation

Open your browser to view interactive API docs:

```
http://localhost:8080/api/v1/docs
```

## API Endpoints

### Authentication

#### POST /api/v1/auth/token

Generate JWT access token.

**Request:**
```json
{
  "client_id": "wms_system",
  "client_secret": "your_secret"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### Health Check

#### GET /api/v1/health

Check service health (no auth required).

**Response:**
```json
{
  "status": "healthy",
  "mock_mode": true,
  "timestamp": "2024-01-15T10:30:00.000Z"
}
```

#### GET /api/v1/startloading

Verify system readiness (requires auth).

**Response:**
```json
{
  "ready": true,
  "nodes_status": {
    "manipulator_controller": "active",
    "picker_z_controller": "active",
    "gripper_controller": "active",
    "navigation": "active"
  },
  "message": "All systems operational"
}
```

### Container Operations

#### POST /api/v1/container/get

Retrieve container from storage.

**Headers:**
```
Authorization: Bearer <jwt_token>
```

**Request:**
```json
{
  "container_id": "CNT-12345"
}
```

**Response:**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "message": "Container CNT-12345 retrieved successfully",
  "progress": 1.0
}
```

#### POST /api/v1/container/return

Return container to storage.

**Request:**
```json
{
  "container_id": "CNT-12345"
}
```

### Medicine Operations

#### POST /api/v1/medicine/get

Extract medicine from cabinet.

**Request:**
```json
{
  "side": "left",
  "cabinet_num": 2,
  "row": 1,
  "column": 0,
  "item_count": 1
}
```

**Response:**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "completed",
  "message": "Retrieved 1 item(s) from left-2-1-0",
  "progress": 1.0
}
```

#### POST /api/v1/medicine/put

Place medicine into cabinet.

**Request:**
```json
{
  "side": "right",
  "cabinet_num": 3,
  "row": 2,
  "column": 1,
  "item_count": 2
}
```

### Task Management

#### GET /api/v1/task/status?task_id={task_id}

Query task status.

**Response:**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "operation": "get_medicine",
  "progress": 1.0,
  "message": "Task completed successfully",
  "started_at": "2024-01-15T10:30:00.000Z",
  "completed_at": "2024-01-15T10:30:15.000Z"
}
```

#### POST /api/v1/task/cancel?task_id={task_id}

Cancel a running task.

**Response:**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "message": "Task cancelled successfully"
}
```

## Testing with curl

### 1. Get Authentication Token

```bash
curl -X POST http://localhost:8080/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "wms_system", "client_secret": "demo_secret_2024"}'
```

Save the returned `access_token`.

### 2. Call API Endpoints

```bash
# Health check (no auth)
curl http://localhost:8080/api/v1/health

# Start loading (with auth)
curl http://localhost:8080/api/v1/startloading \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"

# Get medicine
curl -X POST http://localhost:8080/api/v1/medicine/get \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "side": "left",
    "cabinet_num": 2,
    "row": 1,
    "column": 0,
    "item_count": 1
  }'

# Check task status
curl "http://localhost:8080/api/v1/task/status?task_id=YOUR_TASK_ID" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

## Testing with Python

```python
import requests

# Base URL
base_url = "http://localhost:8080/api/v1"

# 1. Authenticate
auth_response = requests.post(
    f"{base_url}/auth/token",
    json={
        "client_id": "wms_system",
        "client_secret": "demo_secret_2024"
    }
)
token = auth_response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 2. Get medicine
response = requests.post(
    f"{base_url}/medicine/get",
    headers=headers,
    json={
        "side": "left",
        "cabinet_num": 2,
        "row": 1,
        "column": 0,
        "item_count": 1
    }
)
task_id = response.json()["task_id"]
print(f"Task created: {task_id}")

# 3. Check status
status_response = requests.get(
    f"{base_url}/task/status",
    headers=headers,
    params={"task_id": task_id}
)
print(f"Status: {status_response.json()}")
```

## Development

### Mock Mode

Mock mode allows testing without ROS2 robot:

- Returns immediate successful responses
- No actual robot movement
- Useful for frontend development and API testing

Set `mock_mode: true` in config.

### Adding Real ROS2 Integration

To add real ROS2 action calls:

1. Create `services/ros_service.py` with same interface as `MockService`
2. Add `ActionClient` for ROS2 actions
3. Implement async action goal sending with feedback
4. Switch service based on `mock_mode` in `api_server.py`

Example:

```python
from rclpy.action import ActionClient
from ros_control.action import GetContainer

class RosService:
    def __init__(self, node):
        self.node = node
        self.get_container_client = ActionClient(
            node, GetContainer, 'get_container'
        )

    async def get_container(self, request):
        goal = GetContainer.Goal()
        goal.container_id = request.container_id

        future = self.get_container_client.send_goal_async(goal)
        # Handle feedback and result...
```

## Security Notes

1. **Change JWT Secret**: Always generate a new secret for production
2. **Secure Client Secrets**: Use strong passwords and bcrypt hashing
3. **CORS Configuration**: In production, specify exact allowed origins
4. **HTTPS**: Use reverse proxy (nginx) for HTTPS in production
5. **Network Security**: Restrict API access with firewall rules

## Troubleshooting

### Server Won't Start

Check if port is already in use:
```bash
sudo lsof -i :8080
```

Change port in config if needed.

### Authentication Fails

1. Verify client credentials in config
2. Check JWT secret key matches
3. Ensure token hasn't expired
4. Verify client_id is in `allowed_clients` list

### Import Errors

Ensure all dependencies are installed:
```bash
pip3 install fastapi uvicorn pydantic python-jose[cryptography] passlib[bcrypt]
```

## License

MIT

## Maintainer

akhmedov@example.com
