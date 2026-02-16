"""Configuration loader for REST API Bridge."""

import yaml
from pathlib import Path
from typing import Dict, Any
from ament_index_python.packages import get_package_share_directory


def load_config(package_name: str = 'rest_api_bridge',
                config_file: str = 'rest_api_config.yaml',
                node_name: str = 'rest_api_bridge') -> Dict[str, Any]:
    """
    Load configuration from YAML file.

    Tries package share directory first, then falls back to source directory.
    Supports ros__parameters structure.

    Args:
        package_name: ROS2 package name
        config_file: Configuration file name
        node_name: Node name for extracting config

    Returns:
        Configuration dictionary
    """
    try:
        pkg_share = get_package_share_directory(package_name)
        config_path = Path(pkg_share) / 'config' / config_file
    except Exception:
        # Fallback for development
        config_path = Path(__file__).parent.parent.parent / 'config' / config_file

    if not config_path.exists():
        return get_default_config()

    with open(config_path, 'r') as f:
        yaml_data = yaml.safe_load(f)

    if not yaml_data:
        return get_default_config()

    # Extract config from various YAML structures
    config = None
    if node_name in yaml_data:
        node_config = yaml_data[node_name]
        if isinstance(node_config, dict) and 'ros__parameters' in node_config:
            config = node_config['ros__parameters']
        elif isinstance(node_config, dict):
            config = node_config
    elif 'ros__parameters' in yaml_data:
        config = yaml_data['ros__parameters']
    else:
        config = yaml_data

    if not config:
        config = {}

    # Deep merge with defaults
    default = get_default_config()
    merged = deep_merge(default, config)
    return merged


def deep_merge(base: Dict, override: Dict) -> Dict:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_default_config() -> Dict[str, Any]:
    """Return default configuration."""
    return {
        'host': '0.0.0.0',
        'port': 8080,
        'api_base_path': '/api/v1',
        'auth': {
            'enabled': True,
            'jwt': {
                'secret_key': 'your-256-bit-secret-change-in-production',
                'algorithm': 'HS256',
                'access_token_expire_minutes': 60
            },
            'clients': {},
            'allowed_clients': []
        },
        'mock_mode': True,
        'cors': {
            'enabled': True,
            'allow_origins': ['*'],
            'allow_methods': ['GET', 'POST'],
            'allow_headers': ['*']
        }
    }
