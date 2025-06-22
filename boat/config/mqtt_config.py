#!/usr/bin/env python3
"""
MQTT Configuration Management for PiBoat2
Handles configuration loading, validation, and environment variable management
"""

import os
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict

try:
    import yaml
except ImportError:
    print("PyYAML not installed. Install with: pip install pyyaml")
    yaml = None

from ..communication.mqtt_client import MQTTConfig
from ..navigation.safety_monitor import SafetyLimits, GeofenceZone


@dataclass
class BoatConfig:
    """Complete boat configuration"""
    boat_id: str
    mqtt: MQTTConfig
    safety: SafetyLimits
    navigation: Dict[str, Any]
    reporting: Dict[str, Any]
    hardware: Dict[str, Any]


class ConfigManager:
    """
    Manages boat configuration from multiple sources:
    - Environment variables
    - YAML configuration files
    - Runtime configuration updates
    """
    
    def __init__(self, config_file: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self.config_file = config_file or "/home/pi/PiBoat2/config/boat_config.yaml"
        self.config: Optional[BoatConfig] = None
        
        # Default configuration values
        self.defaults = {
            'boat_id': 'piboat2_default',
            'mqtt': {
                'broker_host': 'localhost',
                'port': 1883,
                'use_tls': False,
                'username': None,
                'password': None,
                'keepalive': 60,
                'qos': 1,
                'reconnect_delay_min': 1,
                'reconnect_delay_max': 60
            },
            'safety': {
                'max_speed_percent': 70,
                'max_rudder_angle': 45.0,
                'max_distance_from_start': 1000.0,
                'battery_voltage_min': 11.0,
                'temperature_max': 85.0,
                'gps_timeout_seconds': 30,
                'command_timeout_seconds': 60
            },
            'navigation': {
                'update_interval': 1.0,
                'heading_tolerance': 5.0,
                'max_turn_rate': 30.0,
                'position_tolerance': 5.0,
                'pid_kp': 1.0,
                'pid_ki': 0.1,
                'pid_kd': 0.5
            },
            'reporting': {
                'status_interval': 10,
                'gps_interval': 5,
                'heartbeat_interval': 30,
                'system_metrics_interval': 60
            },
            'hardware': {
                'gps_device': '/dev/ttyUSB0',
                'gps_baudrate': 9600,
                'compass_i2c_address': 0x1e,
                'motor_controller_device': '/dev/ttyUSB1'
            }
        }
    
    def load_config(self) -> BoatConfig:
        """Load configuration from all sources"""
        self.logger.info("Loading boat configuration")
        
        # Start with defaults
        config_dict = self._deep_copy_dict(self.defaults)
        
        # Override with file configuration
        file_config = self._load_config_file()
        if file_config:
            config_dict = self._merge_configs(config_dict, file_config)
        
        # Override with environment variables
        env_config = self._load_env_config()
        config_dict = self._merge_configs(config_dict, env_config)
        
        # Create configuration objects
        try:
            # Create MQTT config
            mqtt_config = MQTTConfig(
                broker_host=config_dict['mqtt']['broker_host'],
                port=config_dict['mqtt']['port'],
                use_tls=config_dict['mqtt']['use_tls'],
                boat_id=config_dict['boat_id'],
                username=config_dict['mqtt']['username'],
                password=config_dict['mqtt']['password'],
                keepalive=config_dict['mqtt']['keepalive'],
                qos=config_dict['mqtt']['qos'],
                reconnect_delay_min=config_dict['mqtt']['reconnect_delay_min'],
                reconnect_delay_max=config_dict['mqtt']['reconnect_delay_max']
            )
            
            # Create safety limits
            safety_limits = SafetyLimits(
                max_speed_percent=config_dict['safety']['max_speed_percent'],
                max_rudder_angle=config_dict['safety']['max_rudder_angle'],
                max_distance_from_start=config_dict['safety']['max_distance_from_start'],
                battery_voltage_min=config_dict['safety']['battery_voltage_min'],
                temperature_max=config_dict['safety']['temperature_max'],
                gps_timeout_seconds=config_dict['safety']['gps_timeout_seconds'],
                command_timeout_seconds=config_dict['safety']['command_timeout_seconds']
            )
            
            # Create boat config
            self.config = BoatConfig(
                boat_id=config_dict['boat_id'],
                mqtt=mqtt_config,
                safety=safety_limits,
                navigation=config_dict['navigation'],
                reporting=config_dict['reporting'],
                hardware=config_dict['hardware']
            )
            
            self.logger.info(f"Configuration loaded successfully for boat: {self.config.boat_id}")
            self._log_config_summary()
            
            return self.config
            
        except Exception as e:
            self.logger.error(f"Failed to create configuration: {e}")
            raise ValueError(f"Invalid configuration: {e}")
    
    def save_config(self, config_file: Optional[str] = None) -> bool:
        """Save current configuration to file"""
        if not self.config:
            self.logger.error("No configuration loaded to save")
            return False
        
        save_file = config_file or self.config_file
        
        try:
            # Convert to dictionary
            config_dict = {
                'boat_id': self.config.boat_id,
                'mqtt': asdict(self.config.mqtt),
                'safety': asdict(self.config.safety),
                'navigation': self.config.navigation,
                'reporting': self.config.reporting,
                'hardware': self.config.hardware
            }
            
            # Remove boat_id from mqtt section (it's duplicated)
            if 'boat_id' in config_dict['mqtt']:
                del config_dict['mqtt']['boat_id']
            
            # Save to YAML file
            os.makedirs(os.path.dirname(save_file), exist_ok=True)
            
            with open(save_file, 'w') as f:
                yaml.dump(config_dict, f, default_flow_style=False, indent=2)
            
            self.logger.info(f"Configuration saved to: {save_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save configuration: {e}")
            return False
    
    def update_mqtt_config(self, **kwargs) -> bool:
        """Update MQTT configuration at runtime"""
        if not self.config:
            self.logger.error("No configuration loaded")
            return False
        
        try:
            # Update MQTT config fields
            for key, value in kwargs.items():
                if hasattr(self.config.mqtt, key):
                    setattr(self.config.mqtt, key, value)
                    self.logger.info(f"MQTT config updated: {key} = {value}")
                else:
                    self.logger.warning(f"Unknown MQTT config field: {key}")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update MQTT config: {e}")
            return False
    
    def update_safety_limits(self, **kwargs) -> bool:
        """Update safety limits at runtime"""
        if not self.config:
            self.logger.error("No configuration loaded")
            return False
        
        try:
            # Update safety limits fields
            for key, value in kwargs.items():
                if hasattr(self.config.safety, key):
                    setattr(self.config.safety, key, value)
                    self.logger.info(f"Safety limit updated: {key} = {value}")
                else:
                    self.logger.warning(f"Unknown safety limit field: {key}")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update safety limits: {e}")
            return False
    
    def update_reporting_intervals(self, **kwargs) -> bool:
        """Update reporting intervals at runtime"""
        if not self.config:
            self.logger.error("No configuration loaded")
            return False
        
        try:
            # Update reporting intervals
            for key, value in kwargs.items():
                if key in self.config.reporting:
                    self.config.reporting[key] = max(1, int(value))
                    self.logger.info(f"Reporting interval updated: {key} = {value}")
                else:
                    self.logger.warning(f"Unknown reporting interval: {key}")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update reporting intervals: {e}")
            return False
    
    def get_config(self) -> Optional[BoatConfig]:
        """Get current configuration"""
        return self.config
    
    def _load_config_file(self) -> Optional[Dict[str, Any]]:
        """Load configuration from YAML file"""
        if not os.path.exists(self.config_file):
            self.logger.info(f"Config file not found: {self.config_file}")
            return None
        
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            self.logger.info(f"Loaded config from: {self.config_file}")
            return config
            
        except Exception as e:
            self.logger.error(f"Failed to load config file: {e}")
            return None
    
    def _load_env_config(self) -> Dict[str, Any]:
        """Load configuration from environment variables"""
        env_config = {}
        
        # Boat ID
        if os.getenv('BOAT_ID'):
            env_config['boat_id'] = os.getenv('BOAT_ID')
        
        # MQTT configuration
        mqtt_config = {}
        if os.getenv('MQTT_BROKER_HOST'):
            mqtt_config['broker_host'] = os.getenv('MQTT_BROKER_HOST')
        if os.getenv('MQTT_BROKER_PORT'):
            mqtt_config['port'] = int(os.getenv('MQTT_BROKER_PORT'))
        if os.getenv('MQTT_USE_TLS'):
            mqtt_config['use_tls'] = os.getenv('MQTT_USE_TLS').lower() in ['true', '1', 'yes']
        if os.getenv('MQTT_USERNAME'):
            mqtt_config['username'] = os.getenv('MQTT_USERNAME')
        if os.getenv('MQTT_PASSWORD'):
            mqtt_config['password'] = os.getenv('MQTT_PASSWORD')
        if os.getenv('MQTT_KEEPALIVE'):
            mqtt_config['keepalive'] = int(os.getenv('MQTT_KEEPALIVE'))
        if os.getenv('MQTT_QOS'):
            mqtt_config['qos'] = int(os.getenv('MQTT_QOS'))
        
        if mqtt_config:
            env_config['mqtt'] = mqtt_config
        
        # Safety configuration
        safety_config = {}
        if os.getenv('MAX_SPEED_PERCENT'):
            safety_config['max_speed_percent'] = int(os.getenv('MAX_SPEED_PERCENT'))
        if os.getenv('MAX_RUDDER_ANGLE'):
            safety_config['max_rudder_angle'] = float(os.getenv('MAX_RUDDER_ANGLE'))
        if os.getenv('MAX_DISTANCE_FROM_START'):
            safety_config['max_distance_from_start'] = float(os.getenv('MAX_DISTANCE_FROM_START'))
        if os.getenv('BATTERY_VOLTAGE_MIN'):
            safety_config['battery_voltage_min'] = float(os.getenv('BATTERY_VOLTAGE_MIN'))
        if os.getenv('TEMPERATURE_MAX'):
            safety_config['temperature_max'] = float(os.getenv('TEMPERATURE_MAX'))
        if os.getenv('GPS_TIMEOUT_SECONDS'):
            safety_config['gps_timeout_seconds'] = int(os.getenv('GPS_TIMEOUT_SECONDS'))
        
        if safety_config:
            env_config['safety'] = safety_config
        
        # Reporting configuration
        reporting_config = {}
        if os.getenv('STATUS_REPORT_INTERVAL'):
            reporting_config['status_interval'] = int(os.getenv('STATUS_REPORT_INTERVAL'))
        if os.getenv('GPS_UPDATE_INTERVAL'):
            reporting_config['gps_interval'] = int(os.getenv('GPS_UPDATE_INTERVAL'))
        if os.getenv('HEARTBEAT_INTERVAL'):
            reporting_config['heartbeat_interval'] = int(os.getenv('HEARTBEAT_INTERVAL'))
        if os.getenv('SYSTEM_METRICS_INTERVAL'):
            reporting_config['system_metrics_interval'] = int(os.getenv('SYSTEM_METRICS_INTERVAL'))
        
        if reporting_config:
            env_config['reporting'] = reporting_config
        
        # Hardware configuration
        hardware_config = {}
        if os.getenv('GPS_DEVICE'):
            hardware_config['gps_device'] = os.getenv('GPS_DEVICE')
        if os.getenv('GPS_BAUDRATE'):
            hardware_config['gps_baudrate'] = int(os.getenv('GPS_BAUDRATE'))
        if os.getenv('COMPASS_I2C_ADDRESS'):
            hardware_config['compass_i2c_address'] = int(os.getenv('COMPASS_I2C_ADDRESS'), 16)
        if os.getenv('MOTOR_CONTROLLER_DEVICE'):
            hardware_config['motor_controller_device'] = os.getenv('MOTOR_CONTROLLER_DEVICE')
        
        if hardware_config:
            env_config['hardware'] = hardware_config
        
        if env_config:
            self.logger.info("Loaded configuration from environment variables")
        
        return env_config
    
    def _merge_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Merge two configuration dictionaries"""
        result = self._deep_copy_dict(base)
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _deep_copy_dict(self, d: Dict[str, Any]) -> Dict[str, Any]:
        """Deep copy a dictionary"""
        result = {}
        for key, value in d.items():
            if isinstance(value, dict):
                result[key] = self._deep_copy_dict(value)
            else:
                result[key] = value
        return result
    
    def _log_config_summary(self):
        """Log configuration summary"""
        if not self.config:
            return
        
        self.logger.info("Configuration Summary:")
        self.logger.info(f"  Boat ID: {self.config.boat_id}")
        self.logger.info(f"  MQTT Broker: {self.config.mqtt.broker_host}:{self.config.mqtt.port}")
        self.logger.info(f"  MQTT TLS: {self.config.mqtt.use_tls}")
        self.logger.info(f"  Max Speed: {self.config.safety.max_speed_percent}%")
        self.logger.info(f"  Max Distance: {self.config.safety.max_distance_from_start}m")
        self.logger.info(f"  Status Interval: {self.config.reporting['status_interval']}s")
        self.logger.info(f"  GPS Interval: {self.config.reporting['gps_interval']}s")


def load_geofence_zones(config_file: str = None) -> List[GeofenceZone]:
    """Load geofence zones from configuration file"""
    geofence_file = config_file or "/home/pi/PiBoat2/config/geofence_zones.yaml"
    
    if not os.path.exists(geofence_file):
        return []
    
    try:
        with open(geofence_file, 'r') as f:
            zones_data = yaml.safe_load(f)
        
        zones = []
        for zone_data in zones_data.get('zones', []):
            zone = GeofenceZone(
                name=zone_data['name'],
                center_lat=zone_data['center_lat'],
                center_lon=zone_data['center_lon'],
                radius_meters=zone_data['radius_meters'],
                zone_type=zone_data['zone_type']
            )
            zones.append(zone)
        
        logging.getLogger(__name__).info(f"Loaded {len(zones)} geofence zones")
        return zones
        
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to load geofence zones: {e}")
        return []


def save_geofence_zones(zones: List[GeofenceZone], config_file: str = None) -> bool:
    """Save geofence zones to configuration file"""
    geofence_file = config_file or "/home/pi/PiBoat2/config/geofence_zones.yaml"
    
    try:
        zones_data = {
            'zones': [asdict(zone) for zone in zones]
        }
        
        os.makedirs(os.path.dirname(geofence_file), exist_ok=True)
        
        with open(geofence_file, 'w') as f:
            yaml.dump(zones_data, f, default_flow_style=False, indent=2)
        
        logging.getLogger(__name__).info(f"Saved {len(zones)} geofence zones to {geofence_file}")
        return True
        
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to save geofence zones: {e}")
        return False