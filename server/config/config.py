#!/usr/bin/env python3
"""
Configuration management for PiBoat2 server
Handles loading configuration from YAML files and environment variables
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class DatabaseConfig:
    """Database configuration"""
    url: str
    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 20


@dataclass
class MQTTConfig:
    """MQTT broker configuration"""
    broker_host: str
    broker_port: int = 1883
    use_tls: bool = False
    keepalive: int = 60
    qos: int = 1
    username: Optional[str] = None
    password: Optional[str] = None
    topics: Optional[Dict[str, str]] = None


@dataclass
class ServerConfig:
    """Server application configuration"""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


@dataclass
class SecurityConfig:
    """Security configuration"""
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30


@dataclass
class MonitoringConfig:
    """Monitoring and health check configuration"""
    health_check_interval: int = 60
    boat_timeout_minutes: int = 5


@dataclass
class Config:
    """Main configuration class"""
    database: DatabaseConfig
    mqtt: MQTTConfig
    server: ServerConfig
    security: SecurityConfig
    monitoring: MonitoringConfig
    environment: str = "development"
    log_level: str = "INFO"


class ConfigManager:
    """Configuration manager for loading and managing application config"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self.config_path = config_path or self._get_default_config_path()
        self._config = None
    
    def _get_default_config_path(self) -> str:
        """Get the default configuration file path"""
        # Look for config file in project root
        project_root = Path(__file__).parent.parent.parent
        config_file = project_root / "config" / "server_config.yaml"
        
        if config_file.exists():
            return str(config_file)
        else:
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
    
    def load_config(self) -> Config:
        """Load configuration from YAML file and environment variables"""
        if self._config is not None:
            return self._config
        
        try:
            # Load base configuration from YAML
            with open(self.config_path, 'r') as f:
                yaml_config = yaml.safe_load(f)
            
            # Process environment variable substitutions
            processed_config = self._process_env_vars(yaml_config)
            
            # Create configuration objects
            self._config = self._create_config_objects(processed_config)
            
            self.logger.info(f"Configuration loaded from {self.config_path}")
            return self._config
            
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            raise
    
    def _process_env_vars(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Process environment variable substitutions in configuration"""
        def replace_env_vars(obj):
            if isinstance(obj, dict):
                return {key: replace_env_vars(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [replace_env_vars(item) for item in obj]
            elif isinstance(obj, str) and obj.startswith('${') and obj.endswith('}'):
                # Extract environment variable name and default value
                env_expr = obj[2:-1]  # Remove ${ and }
                if ':' in env_expr:
                    env_name, default_value = env_expr.split(':', 1)
                    return os.getenv(env_name.strip(), default_value.strip())
                else:
                    env_value = os.getenv(env_expr.strip())
                    if env_value is None:
                        raise ValueError(f"Required environment variable not set: {env_expr}")
                    return env_value
            else:
                return obj
        
        return replace_env_vars(config)
    
    def _create_config_objects(self, config: Dict[str, Any]) -> Config:
        """Create typed configuration objects from dictionary"""
        
        # Database configuration
        db_config = config.get('database', {})
        database = DatabaseConfig(
            url=db_config.get('url', 'postgresql://piboat2:password@localhost/piboat2'),
            echo=db_config.get('echo', False),
            pool_size=db_config.get('pool_size', 10),
            max_overflow=db_config.get('max_overflow', 20)
        )
        
        # MQTT configuration
        mqtt_config = config.get('mqtt', {})
        mqtt = MQTTConfig(
            broker_host=mqtt_config.get('broker_host', 'localhost'),
            broker_port=mqtt_config.get('broker_port', 1883),
            use_tls=mqtt_config.get('use_tls', False),
            keepalive=mqtt_config.get('keepalive', 60),
            qos=mqtt_config.get('qos', 1),
            username=mqtt_config.get('username'),
            password=mqtt_config.get('password'),
            topics=mqtt_config.get('topics', {})
        )
        
        # Server configuration
        server_config = config.get('server', {})
        server = ServerConfig(
            host=server_config.get('host', '0.0.0.0'),
            port=server_config.get('port', 8000),
            debug=server_config.get('debug', False)
        )
        
        # Security configuration
        security_config = config.get('security', {})
        security = SecurityConfig(
            secret_key=security_config.get('secret_key', 'dev_secret_key'),
            algorithm=security_config.get('algorithm', 'HS256'),
            access_token_expire_minutes=security_config.get('access_token_expire_minutes', 30)
        )
        
        # Monitoring configuration
        monitoring_config = config.get('monitoring', {})
        monitoring = MonitoringConfig(
            health_check_interval=monitoring_config.get('health_check_interval', 60),
            boat_timeout_minutes=monitoring_config.get('boat_timeout_minutes', 5)
        )
        
        return Config(
            database=database,
            mqtt=mqtt,
            server=server,
            security=security,
            monitoring=monitoring,
            environment=os.getenv('ENVIRONMENT', 'development'),
            log_level=os.getenv('LOG_LEVEL', config.get('logging', {}).get('level', 'INFO'))
        )
    
    def get_database_url(self) -> str:
        """Get database URL with environment variable fallback"""
        config = self.load_config()
        
        # Check for Docker environment
        if os.getenv('DATABASE_URL'):
            return os.getenv('DATABASE_URL')
        
        return config.database.url
    
    def get_mqtt_config(self) -> MQTTConfig:
        """Get MQTT configuration with Docker environment support"""
        config = self.load_config()
        
        # Override with Docker environment variables if present
        if os.getenv('MQTT_BROKER_HOST'):
            config.mqtt.broker_host = os.getenv('MQTT_BROKER_HOST')
        if os.getenv('MQTT_BROKER_PORT'):
            config.mqtt.broker_port = int(os.getenv('MQTT_BROKER_PORT'))
        
        return config.mqtt


# Global configuration manager instance
config_manager = ConfigManager()


def get_config() -> Config:
    """Get the application configuration"""
    return config_manager.load_config()


def get_database_url() -> str:
    """Get the database URL"""
    return config_manager.get_database_url()


def get_mqtt_config() -> MQTTConfig:
    """Get the MQTT configuration"""
    return config_manager.get_mqtt_config()