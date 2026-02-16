# rest_api_bridge Package Documentation

## Overview

The `rest_api_bridge` package provides a REST API layer for external WMS (Warehouse Management Systems) to control the robot manipulator via HTTP/JSON. Built with FastAPI and integrated with ROS2, following the original system architecture specification.

**Key features:**
- JWT authentication with bcrypt password hashing
- Async background task operations
- Mock mode for testing without robot hardware
- Interactive Swagger UI documentation
- Pydantic request/response validation
- ROS2 node integration

## Package Structure

```
src/rest_api_bridge/
├── package.xml                        # ROS2 package manifest
├── setup.py                           # Python package setup
├── setup.cfg                          # Installation configuration
├── README.md                          # Package README
├── resource/rest_api_bridge           # ament resource marker
├── rest_api_bridge/
│   ├── __init__.py
│   ├── api_server.py                  # Main FastAPI + ROS2 node
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py                    # JWT token generation
│   │   ├── health.py                  # Health & readiness endpoints
│   │   ├── container.py               # Container operations
│   │   ├── medicine.py                # Medicine operations
│   │   └── task.py                    # Task status & cancellation
│   ├── models/
│   │   ├── __init__.py
│   │   ├── requests.py                # Pydantic request models
│   │   └── responses.py               # Pydantic response models
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── jwt_auth.py                # JWT validation middleware
│   ├── services/
│   │   ├── __init__.py
│   │   └── mock_service.py            # Mock implementation
│   └── utils/
│       ├── __init__.py
│       └── config.py                  # Configuration loader
├── config/
│   └── rest_api_config.yaml           # Server & auth configuration
└── launch/
    └── rest_api_server.launch.py      # ROS2 launch file
```

---

## Quick Start

### Installation

```bash
# Install Python dependencies
pip3 install python-jose[cryptography] passlib 'bcrypt<4.0.0' --break-system-packages

# Build package
cd ~/manipulator_ros_control
colcon build --packages-select rest_api_bridge
source install/setup.bash
```

### Running

```bash
# Start server
ros2 run rest_api_bridge rest_api_server

# Or with launch file
ros2 launch rest_api_bridge rest_api_server.launch.py
```

### Quick Test

```bash
# Health check
curl http://localhost:8080/api/v1/health

# Get token
curl -X POST http://localhost:8080/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "wms_system", "client_secret": "demo_secret_2024"}'

# Interactive docs
open http://localhost:8080/api/v1/docs
```

---

## API Endpoints

**Base URL:** `http://localhost:8080/api/v1`

### Health & Status

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | No | Service health check |
| `/is_ready` | GET | Yes | System readiness check |

### Container Operations

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/getcontainer` | POST | Yes | Attach empty container to platform |
| `/retcontainer` | GET | Yes | Return container |

**Request (getcontainer):**
```json
{
  "unload": false
}
```

**Request (retcontainer) - query parameter:**
```
?unload=true
```

**Response (both):**
```json
{
  "status": "ok",
  "accepted": true
}
```

### Medicine Operations

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/get_items` | POST | Yes | Extract medicine from box |
| `/put_items` | POST | Yes | Place medicine into box |

**Request (get_items):**
```json
{
  "medicine_list": [
    {"image_id": "med-001", "raw_id": 0}
  ],
  "box_id": "BOX-12345",
  "task_id": "task-001"
}
```

**Request (put_items):**
```json
{
  "medicine_list": [{
    "image_id": "med-001",
    "cell_id": 0,
    "row_id": 2,
    "position": {"x_side": 0.5, "y_side": 1.2}
  }],
  "box_id": "BOX-67890",
  "task_id": "task-002"
}
```

**Response (both):**
```json
{
  "status": "ok",
  "accepted": true
}
```

### Task Management

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/task/status` | GET | Yes | Get current/last task status |
| `/task/cancel` | GET | Yes | Cancel current task |

**Response (task/status):**
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
    "message": "Retrieved 2 medicine(s) from BOX-12345",
    "medicine_qr": ["DM-FB75BFD1A76A", "DM-8781738E8D5F"],
    "container_id": null
  }
}
```

**Response (task/cancel):**
```json
{
  "status": "ok"
}
```

---

## Authentication

### JWT Token Flow

1. **Get Token:**
```bash
POST /api/v1/auth/token
{
  "client_id": "wms_system",
  "client_secret": "demo_secret_2024"
}
```

2. **Response:**
```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

3. **Use Token:**
```
Authorization: Bearer <access_token>
```

### Configuration

Edit `config/rest_api_config.yaml`:

```yaml
rest_api_bridge:
  ros__parameters:
    auth:
      enabled: true
      jwt:
        secret_key: "your-256-bit-secret-change-in-production"
        algorithm: "HS256"
        access_token_expire_minutes: 60
      clients:
        wms_system: "$2b$12$gxgYYP..."  # bcrypt hash
      allowed_clients:
        - "wms_system"
```

### Generate Credentials

```bash
# Generate JWT secret
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate password hash
python3 -c "from passlib.context import CryptContext; \
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto'); \
print(pwd_context.hash('your_password'))"
```

---

## Configuration

### Server Settings

```yaml
rest_api_bridge:
  ros__parameters:
    host: "0.0.0.0"
    port: 8080
    api_base_path: "/api/v1"
    mock_mode: true  # Set to false for real robot
```

### CORS Settings

```yaml
cors:
  enabled: true
  allow_origins:
    - "*"  # Change to specific domains in production
  allow_methods:
    - "GET"
    - "POST"
  allow_headers:
    - "*"
```

---

## Core Components

### api_server.py

Main application combining FastAPI with ROS2 node.

**Class:** `RestApiNode`

**Key Methods:**
- `_create_app()` - Creates FastAPI application
- `start_server()` - Starts uvicorn in background thread
- `stop_server()` - Graceful shutdown

**Features:**
- Loads configuration from YAML
- Creates mock or real service
- Configures CORS middleware
- Registers all routers
- Runs FastAPI in separate thread
- Spins ROS2 node in main thread

### models/requests.py

Pydantic models for request validation:

- `GetContainerRequest` - `{unload: bool}`
- `ReturnContainerRequest` - `{unload: bool}`
- `GetMedicineRequest` - `{medicine_list, box_id, task_id}`
- `PutMedicineRequest` - `{medicine_list, box_id, task_id}`
- `MedicineItem` - `{image_id, raw_id}`
- `MedicinePlacementItem` - `{image_id, cell_id, row_id, position}`

### models/responses.py

Pydantic models for response validation:

- `HealthResponse` - `{status}`
- `StartLoadingResponse` - `{status}`
- `AcceptedResponse` - `{status, accepted}`
- `TaskStatusResponse` - `{status, task}`
- `TaskInfo` - Full task information
- `TaskCancelResponse` - `{status}`
- `ErrorResponse` - `{status, error_code, message}`

### services/mock_service.py

Mock implementation that simulates robot operations without actual robot interaction.

**Class:** `MockService`

**Methods:**
- `get_container(request)` - Returns immediate success, generates container_id
- `return_container(request)` - Returns immediate success
- `get_medicine(request)` - Returns immediate success, generates medicine_qr array
- `put_medicine(request)` - Returns immediate success
- `get_task_status()` - Returns current/last task information
- `cancel_task()` - Cancels current task
- `start_loading()` - Returns system ready status

**Features:**
- Generates UUIDs for task_id and container_id
- Generates mock DataMatrix codes for medicine_qr
- Maintains current task state
- Logs all operations via ROS2 logger

### middleware/jwt_auth.py

JWT authentication middleware.

**Class:** `JWTAuthMiddleware`

**Features:**
- Validates JWT signature and expiration
- Checks client_id against allowed_clients
- Skips auth for `/health` and `/auth/token`
- Returns 401 for invalid tokens
- Returns 403 for unauthorized clients

---

## Architecture

### Request Flow

```
WMS Client
    │
    ▼
┌─────────────────────┐
│  JWT Authentication │
│   Middleware        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  FastAPI Router     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Pydantic           │
│  Validation         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  MockService or     │
│  RosService         │
└──────────┬──────────┘
           │
           ▼
      Response (202/200)
```

### Integration with ROS2

```
┌─────────────────────┐
│   REST API Bridge   │
│   (FastAPI + ROS2)  │
└──────────┬──────────┘
           │ (Future: mock_mode=false)
           │
           ▼
┌─────────────────────┐
│  ROS2 Action Clients│
│  - /get_container   │
│  - /navigate_to_... │
│  - /extract_box     │
└─────────────────────┘
```

---

## HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 202 | Accepted (async operation started) |
| 400 | Bad Request |
| 403 | Forbidden (auth failed) |
| 409 | Conflict (state error) |
| 422 | Unprocessable Entity (validation) |
| 500 | Internal Server Error |

---

## Testing

### Manual Testing

```bash
# Get token
TOKEN=$(curl -s -X POST http://localhost:8080/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "wms_system", "client_secret": "demo_secret_2024"}' | \
  python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# Test getcontainer
curl -X POST http://localhost:8080/api/v1/getcontainer \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"unload": false}'

# Test get_items
curl -X POST http://localhost:8080/api/v1/get_items \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "medicine_list": [{"image_id": "med-001", "raw_id": 0}],
    "box_id": "BOX-12345",
    "task_id": "task-001"
  }'

# Check task status
curl http://localhost:8080/api/v1/task/status \
  -H "Authorization: Bearer $TOKEN"
```

See [TESTING.md](TESTING.md) for complete testing guide.

---

## Dependencies

### Python Packages

```bash
pip3 install python-jose[cryptography] passlib 'bcrypt<4.0.0' --break-system-packages
```

**Important:** Use `bcrypt<4.0.0` for compatibility with system passlib 1.7.4.

See [DEPENDENCIES.md](DEPENDENCIES.md) for details.

---

## Security

### Production Deployment

1. **Change JWT secret** - Generate new random key
2. **Use strong passwords** - Minimum 16 characters
3. **Restrict CORS origins** - Specify exact domains
4. **Use HTTPS** - Deploy behind nginx with SSL
5. **Firewall rules** - Restrict API access
6. **Environment variables** - Store secrets securely

### Example Nginx Config

```nginx
server {
    listen 443 ssl;
    server_name api.robot.company.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location /api/v1/ {
        proxy_pass http://localhost:8080/api/v1/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Troubleshooting

### Port Already in Use

```bash
# Find and kill process
lsof -ti:8080 | xargs kill -9
```

### Authentication Fails

1. Check client_id in `allowed_clients`
2. Verify bcrypt hash matches password
3. Check JWT secret_key
4. Ensure token hasn't expired

### Import Errors

```bash
# Install dependencies
pip3 install python-jose[cryptography] passlib 'bcrypt<4.0.0' --break-system-packages
```

### Bcrypt Compatibility Error

```bash
# Downgrade bcrypt
pip3 install 'bcrypt<4.0.0' --break-system-packages --force-reinstall
```

---

## Future Development

### Adding Real ROS2 Integration

1. Create `services/ros_service.py`:
```python
from rclpy.action import ActionClient
from ros_control.action import GetContainer

class RosService:
    def __init__(self, node):
        self.node = node
        self.get_container_client = ActionClient(
            node, GetContainer, '/get_container'
        )
    
    def get_container(self, request):
        # Send ROS2 action goal
        # Wait for result
        # Return AcceptedResponse
```

2. Update `api_server.py`:
```python
if self.config.get('mock_mode', True):
    self.service = MockService(self)
else:
    self.service = RosService(self)
```

3. Set `mock_mode: false` in config

---

## Related Documentation

- **API Reference**: [API_REFERENCE.md](API_REFERENCE.md) - Complete endpoint documentation
- **Testing Guide**: [TESTING.md](TESTING.md) - Testing procedures and examples
- **Dependencies**: [DEPENDENCIES.md](DEPENDENCIES.md) - Python package installation
- **Package README**: `src/rest_api_bridge/README.md` - Quick start guide

---

## Building

```bash
cd ~/manipulator_ros_control
colcon build --packages-select rest_api_bridge
source install/setup.bash
```

---

## License

MIT

## Maintainer

akhmedov@example.com
