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
│  │  MockService (test)  │  │
│  │  RosService (real)   │  │
│  └──────────┬───────────┘  │
└─────────────┼───────────────┘
              │ ROS2 Actions
              v
┌─────────────────────────────┐
│   ROS2 Action Servers       │
│  - /get_container      ✅  │
│  - /place_container    ✅  │
│  - /PickItems          ❌  │
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
# Default: real ROS2 connections
mock_mode: false

# Use mock mode for testing without ROS2 robot
mock_mode: true
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

Base URL: `http://localhost:8080/api/v1`

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/auth/token` | POST | No | Get JWT authentication token |
| `/health` | GET | No | Service health check |
| `/is_ready` | GET | Yes | System readiness (checks action servers) |
| `/getcontainer` | POST | Yes | Pick container (real ROS2 call) |
| `/retcontainer` | GET | Yes | Place container back (real ROS2 call) |
| `/get_items` | POST | Yes | Extract items (stub — `action_not_available`) |
| `/put_items` | POST | Yes | Place items (stub — `action_not_available`) |
| `/task/status` | GET | Yes | Current task status with progress |
| `/task/cancel` | GET | Yes | Cancel running task |

See [docs/rest_api_bridge/package_structure.md](../../docs/rest_api_bridge/package_structure.md) for full endpoint documentation.

## Quick Test

```bash
# Get token
TOKEN=$(curl -s -X POST http://localhost:8080/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id":"wms_system","client_secret":"demo_secret_2024"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Check readiness
curl -s http://localhost:8080/api/v1/is_ready -H "Authorization: Bearer $TOKEN"

# Pick container (real ROS2 call)
curl -s -X POST http://localhost:8080/api/v1/getcontainer \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"unload": false}'

# Poll task status
curl -s http://localhost:8080/api/v1/task/status -H "Authorization: Bearer $TOKEN"

# Place container back
curl -s "http://localhost:8080/api/v1/retcontainer?unload=false" \
  -H "Authorization: Bearer $TOKEN"
```

See [docs/rest_api_bridge/TESTING.md](../../docs/rest_api_bridge/TESTING.md) for full testing guide.

## Development

### Service Modes

**Real mode** (`mock_mode: false`, default):
- Connects to `/get_container` and `/place_container` ROS2 action servers
- Real-time progress feedback from action servers
- `get_items`/`put_items` return `action_not_available` (action type not yet implemented)
- 409 Conflict when another task is in progress

**Mock mode** (`mock_mode: true`):
- Returns immediate successful responses
- No actual robot movement
- Useful for frontend development and API testing

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
