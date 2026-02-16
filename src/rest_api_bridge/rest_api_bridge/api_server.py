"""REST API Bridge Server - Main application."""

import rclpy
from rclpy.node import Node
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import signal
import sys
from threading import Thread

from rest_api_bridge.utils.config import load_config
from rest_api_bridge.services.mock_service import MockService
from rest_api_bridge.routers.auth import create_auth_router
from rest_api_bridge.routers.health import create_health_router
from rest_api_bridge.routers.container import create_container_router
from rest_api_bridge.routers.medicine import create_medicine_router
from rest_api_bridge.routers.task import create_task_router
from rest_api_bridge.middleware.jwt_auth import create_jwt_dependency


class RestApiNode(Node):
    """ROS2 node for REST API Bridge."""

    def __init__(self):
        """Initialize REST API node."""
        super().__init__('rest_api_bridge')

        # Load configuration
        self.config = load_config()
        self.get_logger().info('Configuration loaded')
        self.get_logger().info(f"Mock mode: {self.config.get('mock_mode', True)}")
        self.get_logger().info(f"Auth enabled: {self.config.get('auth', {}).get('enabled', True)}")

        # Initialize service (mock or real)
        if self.config.get('mock_mode', True):
            self.service = MockService(self)
            self.get_logger().info('Using mock service implementation')
        else:
            # TODO: Initialize real ROS2 service when implemented
            self.get_logger().warn('Real ROS2 service not yet implemented, using mock')
            self.service = MockService(self)

        # Create FastAPI application
        self.app = self._create_app()

        # Uvicorn server instance
        self.server = None
        self.server_thread = None

    def _create_app(self) -> FastAPI:
        """
        Create and configure FastAPI application.

        Returns:
            Configured FastAPI app
        """
        api_base = self.config.get('api_base_path', '/api/v1')

        app = FastAPI(
            title="Robot Manipulator REST API",
            description="REST API bridge for robot manipulator control with JWT authentication",
            version="0.1.0",
            docs_url=f"{api_base}/docs",
            redoc_url=f"{api_base}/redoc",
            openapi_url=f"{api_base}/openapi.json"
        )

        # Configure CORS
        cors_config = self.config.get('cors', {})
        if cors_config.get('enabled', True):
            app.add_middleware(
                CORSMiddleware,
                allow_origins=cors_config.get('allow_origins', ['*']),
                allow_credentials=True,
                allow_methods=cors_config.get('allow_methods', ['GET', 'POST']),
                allow_headers=cors_config.get('allow_headers', ['*']),
            )
            self.get_logger().info('CORS enabled')

        # Create JWT authentication dependency
        jwt_auth = create_jwt_dependency(self.config, self.get_logger())

        # Create and include routers
        auth_router = create_auth_router(self.config, self.get_logger())
        health_router = create_health_router(self.service, self.config, jwt_auth)
        container_router = create_container_router(self.service, jwt_auth)
        medicine_router = create_medicine_router(self.service, jwt_auth)
        task_router = create_task_router(self.service, jwt_auth)

        # Include routers at API base path
        app.include_router(auth_router, prefix=api_base)
        app.include_router(health_router, prefix=api_base)
        app.include_router(container_router, prefix=api_base)
        app.include_router(medicine_router, prefix=api_base)
        app.include_router(task_router, prefix=api_base)

        self.get_logger().info('FastAPI application configured')

        return app

    def start_server(self):
        """Start the FastAPI server in a separate thread."""
        host = self.config.get('host', '0.0.0.0')
        port = self.config.get('port', 8080)

        self.get_logger().info(f'Starting REST API server on {host}:{port}')
        self.get_logger().info(f'API docs available at: http://{host}:{port}{self.config.get("api_base_path", "/api/v1")}/docs')

        # Configure uvicorn server
        config = uvicorn.Config(
            self.app,
            host=host,
            port=port,
            log_level="info",
            access_log=True
        )
        self.server = uvicorn.Server(config)

        # Run server in separate thread
        self.server_thread = Thread(target=self.server.run, daemon=True)
        self.server_thread.start()

        self.get_logger().info('REST API server started successfully')

    def stop_server(self):
        """Stop the FastAPI server."""
        if self.server:
            self.get_logger().info('Stopping REST API server...')
            self.server.should_exit = True
            if self.server_thread:
                self.server_thread.join(timeout=5.0)
            self.get_logger().info('REST API server stopped')


# Global node instance for signal handling
node_instance = None


def signal_handler(sig, frame):
    """Handle shutdown signals."""
    global node_instance
    if node_instance:
        node_instance.get_logger().info('Shutdown signal received')
        node_instance.stop_server()
        rclpy.shutdown()
    sys.exit(0)


def main(args=None):
    """Main entry point for REST API server."""
    global node_instance

    # Initialize ROS2
    rclpy.init(args=args)

    # Create node
    node_instance = RestApiNode()

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Start FastAPI server
        node_instance.start_server()

        # Spin ROS2 node
        node_instance.get_logger().info('ROS2 node spinning...')
        rclpy.spin(node_instance)

    except KeyboardInterrupt:
        node_instance.get_logger().info('Keyboard interrupt received')
    except Exception as e:
        node_instance.get_logger().error(f'Error in main loop: {str(e)}')
    finally:
        # Cleanup
        node_instance.stop_server()
        node_instance.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
