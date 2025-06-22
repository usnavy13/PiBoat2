#!/usr/bin/env python3
"""
Safety Monitor for PiBoat2
Implements safety checks, geofencing, and emergency procedures
"""

import math
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Callable
from dataclasses import dataclass

from ..hardware.gps_handler import GPSHandler
from ..hardware.motor_controller import MotorController


@dataclass
class GeofenceZone:
    """Geofence zone definition"""
    name: str
    center_lat: float
    center_lon: float
    radius_meters: float
    zone_type: str  # 'allowed' or 'forbidden'


@dataclass
class SafetyLimits:
    """Safety limit configuration"""
    max_speed_percent: int = 70
    max_rudder_angle: float = 45.0
    max_distance_from_start: float = 1000.0  # meters
    battery_voltage_min: float = 11.0
    temperature_max: float = 85.0  # Celsius
    gps_timeout_seconds: int = 30
    command_timeout_seconds: int = 60


class SafetyMonitor:
    """
    Monitors boat safety parameters and enforces limits
    Handles geofencing, system health, and emergency procedures
    """
    
    def __init__(self, gps_handler: GPSHandler, motor_controller: MotorController):
        self.gps_handler = gps_handler
        self.motor_controller = motor_controller
        self.logger = logging.getLogger(__name__)
        
        # Safety configuration
        self.safety_limits = SafetyLimits()
        self.geofence_zones: List[GeofenceZone] = []
        
        # Monitoring state
        self.monitoring_active = False
        self.safety_thread = None
        self.stop_monitoring = False
        
        # Starting position for distance checks
        self.start_position: Optional[Tuple[float, float]] = None
        
        # Last known positions and timestamps
        self.last_gps_update = None
        self.last_command_time = None
        self.last_position = None
        
        # Safety violation callbacks
        self.safety_callbacks: List[Callable[[str, str, Dict[str, Any]], None]] = []
        
        # Emergency stop state
        self.emergency_stop_active = False
        
        # Safety check intervals
        self.check_interval = 2.0  # seconds
        
        # Violation counters
        self.violation_counts = {
            'speed_violations': 0,
            'geofence_violations': 0,
            'battery_violations': 0,
            'temperature_violations': 0,
            'gps_timeout_violations': 0,
            'distance_violations': 0
        }
    
    def set_safety_limits(self, limits: Dict[str, Any]):
        """Update safety limits"""
        for key, value in limits.items():
            if hasattr(self.safety_limits, key):
                setattr(self.safety_limits, key, value)
                self.logger.info(f"Safety limit updated: {key} = {value}")
            else:
                self.logger.warning(f"Unknown safety limit: {key}")
    
    def add_geofence_zone(self, zone: GeofenceZone):
        """Add a geofence zone"""
        self.geofence_zones.append(zone)
        self.logger.info(f"Added geofence zone: {zone.name} ({zone.zone_type})")
    
    def remove_geofence_zone(self, zone_name: str) -> bool:
        """Remove a geofence zone by name"""
        for i, zone in enumerate(self.geofence_zones):
            if zone.name == zone_name:
                del self.geofence_zones[i]
                self.logger.info(f"Removed geofence zone: {zone_name}")
                return True
        return False
    
    def clear_geofence_zones(self):
        """Clear all geofence zones"""
        self.geofence_zones.clear()
        self.logger.info("All geofence zones cleared")
    
    def add_safety_callback(self, callback: Callable[[str, str, Dict[str, Any]], None]):
        """Add callback for safety violations"""
        self.safety_callbacks.append(callback)
    
    def set_start_position(self, latitude: float = None, longitude: float = None):
        """Set starting position for distance monitoring"""
        if latitude is None or longitude is None:
            # Use current GPS position
            try:
                gps_data = self.gps_handler.get_position()
                if gps_data and 'latitude' in gps_data and 'longitude' in gps_data:
                    self.start_position = (gps_data['latitude'], gps_data['longitude'])
                    self.logger.info(f"Start position set to current GPS: {self.start_position}")
                else:
                    self.logger.error("Cannot set start position - no GPS data available")
                    return False
            except Exception as e:
                self.logger.error(f"Failed to get GPS position for start location: {e}")
                return False
        else:
            self.start_position = (latitude, longitude)
            self.logger.info(f"Start position set to: {self.start_position}")
        
        return True
    
    def start_monitoring(self) -> bool:
        """Start safety monitoring"""
        if self.monitoring_active:
            self.logger.warning("Safety monitoring already active")
            return True
        
        try:
            # Set start position if not already set
            if not self.start_position:
                if not self.set_start_position():
                    self.logger.warning("Starting monitoring without start position")
            
            self.logger.info("Starting safety monitoring")
            self.stop_monitoring = False
            self.monitoring_active = True
            self.emergency_stop_active = False
            
            # Start monitoring thread
            self.safety_thread = threading.Thread(target=self._safety_monitoring_loop, daemon=True)
            self.safety_thread.start()
            
            self.logger.info("Safety monitoring started")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start safety monitoring: {e}")
            return False
    
    def stop_monitoring(self):
        """Stop safety monitoring"""
        self.logger.info("Stopping safety monitoring")
        
        self.stop_monitoring = True
        self.monitoring_active = False
        
        if self.safety_thread and self.safety_thread.is_alive():
            self.safety_thread.join(timeout=3)
        
        self.logger.info("Safety monitoring stopped")
    
    def trigger_emergency_stop(self, reason: str = "Manual trigger") -> bool:
        """Trigger emergency stop procedure"""
        self.logger.critical(f"EMERGENCY STOP TRIGGERED: {reason}")
        
        try:
            self.emergency_stop_active = True
            
            # Stop motors immediately
            motor_result = self.motor_controller.emergency_stop()
            
            # Notify safety callbacks
            self._notify_safety_violation("EMERGENCY_STOP", reason, {
                'motor_stop_success': motor_result,
                'timestamp': datetime.now().isoformat()
            })
            
            return motor_result
            
        except Exception as e:
            self.logger.error(f"Emergency stop failed: {e}")
            return False
    
    def check_immediate_safety(self) -> Dict[str, Any]:
        """Perform immediate safety check (non-blocking)"""
        safety_status = {
            'safe': True,
            'violations': [],
            'warnings': [],
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Check GPS availability
            gps_check = self._check_gps_health()
            if not gps_check['healthy']:
                safety_status['violations'].append({
                    'type': 'GPS_UNAVAILABLE',
                    'message': gps_check['message']
                })
                safety_status['safe'] = False
            
            # Check motor status
            motor_check = self._check_motor_health()
            if not motor_check['healthy']:
                safety_status['violations'].append({
                    'type': 'MOTOR_ISSUE',
                    'message': motor_check['message']
                })
                safety_status['safe'] = False
            
            # Check system health
            system_check = self._check_system_health()
            if not system_check['healthy']:
                if system_check['critical']:
                    safety_status['violations'].append({
                        'type': 'SYSTEM_CRITICAL',
                        'message': system_check['message']
                    })
                    safety_status['safe'] = False
                else:
                    safety_status['warnings'].append({
                        'type': 'SYSTEM_WARNING',
                        'message': system_check['message']
                    })
            
            # Check geofence if GPS is available
            if gps_check['healthy']:
                geofence_check = self._check_geofence()
                if not geofence_check['compliant']:
                    safety_status['violations'].append({
                        'type': 'GEOFENCE_VIOLATION',
                        'message': geofence_check['message']
                    })
                    safety_status['safe'] = False
        
        except Exception as e:
            safety_status['violations'].append({
                'type': 'SAFETY_CHECK_ERROR',
                'message': f"Safety check failed: {e}"
            })
            safety_status['safe'] = False
        
        return safety_status
    
    def get_status(self) -> Dict[str, Any]:
        """Get safety monitor status"""
        return {
            'monitoring_active': self.monitoring_active,
            'emergency_stop_active': self.emergency_stop_active,
            'start_position': self.start_position,
            'geofence_zones': len(self.geofence_zones),
            'violation_counts': self.violation_counts.copy(),
            'safety_limits': {
                'max_speed_percent': self.safety_limits.max_speed_percent,
                'max_rudder_angle': self.safety_limits.max_rudder_angle,
                'max_distance_from_start': self.safety_limits.max_distance_from_start,
                'battery_voltage_min': self.safety_limits.battery_voltage_min,
                'temperature_max': self.safety_limits.temperature_max,
                'gps_timeout_seconds': self.safety_limits.gps_timeout_seconds
            },
            'last_gps_update': self.last_gps_update.isoformat() if self.last_gps_update else None,
            'last_command_time': self.last_command_time.isoformat() if self.last_command_time else None
        }
    
    def update_command_time(self):
        """Update last command timestamp (called by command dispatcher)"""
        self.last_command_time = datetime.now()
    
    def _safety_monitoring_loop(self):
        """Main safety monitoring loop"""
        self.logger.info("Safety monitoring loop started")
        
        while not self.stop_monitoring:
            try:
                # Perform safety checks
                safety_check = self.check_immediate_safety()
                
                # Handle violations
                if not safety_check['safe']:
                    for violation in safety_check['violations']:
                        self._handle_safety_violation(violation['type'], violation['message'])
                
                # Update GPS timestamp
                try:
                    gps_data = self.gps_handler.get_position()
                    if gps_data:
                        self.last_gps_update = datetime.now()
                        if 'latitude' in gps_data and 'longitude' in gps_data:
                            self.last_position = (gps_data['latitude'], gps_data['longitude'])
                except:
                    pass  # GPS errors are handled in check_immediate_safety
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                self.logger.error(f"Safety monitoring loop error: {e}")
                time.sleep(self.check_interval)
        
        self.logger.info("Safety monitoring loop stopped")
    
    def _check_gps_health(self) -> Dict[str, Any]:
        """Check GPS system health"""
        try:
            gps_data = self.gps_handler.get_position()
            
            # Check if GPS data is available
            if not gps_data:
                return {
                    'healthy': False,
                    'message': 'No GPS data available'
                }
            
            # Check GPS timeout
            if self.last_gps_update:
                time_since_update = (datetime.now() - self.last_gps_update).total_seconds()
                if time_since_update > self.safety_limits.gps_timeout_seconds:
                    return {
                        'healthy': False,
                        'message': f'GPS timeout: {time_since_update:.1f}s since last update'
                    }
            
            # Check fix quality
            fix_quality = gps_data.get('fix_quality', 0)
            if fix_quality < 1:
                return {
                    'healthy': False,
                    'message': f'Poor GPS fix quality: {fix_quality}'
                }
            
            # Check satellite count
            satellites = gps_data.get('satellites', 0)
            if satellites < 4:
                return {
                    'healthy': False,
                    'message': f'Insufficient satellites: {satellites}'
                }
            
            return {'healthy': True, 'message': 'GPS healthy'}
            
        except Exception as e:
            return {
                'healthy': False,
                'message': f'GPS check error: {e}'
            }
    
    def _check_motor_health(self) -> Dict[str, Any]:
        """Check motor system health"""
        try:
            motor_status = self.motor_controller.get_status()
            
            if not motor_status:
                return {
                    'healthy': False,
                    'message': 'Motor status unavailable'
                }
            
            # Check battery voltage
            battery_voltage = motor_status.get('battery_voltage')
            if battery_voltage and battery_voltage < self.safety_limits.battery_voltage_min:
                self.violation_counts['battery_violations'] += 1
                return {
                    'healthy': False,
                    'message': f'Low battery voltage: {battery_voltage:.1f}V'
                }
            
            # Check temperature
            temperature = motor_status.get('temperature')
            if temperature and temperature > self.safety_limits.temperature_max:
                self.violation_counts['temperature_violations'] += 1
                return {
                    'healthy': False,
                    'message': f'High temperature: {temperature:.1f}°C'
                }
            
            # Check speed limit
            throttle_percent = motor_status.get('throttle_percent', 0)
            if abs(throttle_percent) > self.safety_limits.max_speed_percent:
                self.violation_counts['speed_violations'] += 1
                return {
                    'healthy': False,
                    'message': f'Speed limit exceeded: {throttle_percent}%'
                }
            
            # Check rudder angle
            rudder_angle = motor_status.get('rudder_angle', 0)
            if abs(rudder_angle) > self.safety_limits.max_rudder_angle:
                return {
                    'healthy': False,
                    'message': f'Rudder angle limit exceeded: {rudder_angle}°'
                }
            
            return {'healthy': True, 'message': 'Motors healthy'}
            
        except Exception as e:
            return {
                'healthy': False,
                'message': f'Motor check error: {e}'
            }
    
    def _check_system_health(self) -> Dict[str, Any]:
        """Check system health (CPU, memory, etc.)"""
        try:
            import psutil
            
            # Check CPU usage
            cpu_percent = psutil.cpu_percent()
            if cpu_percent > 90:
                return {
                    'healthy': False,
                    'critical': True,
                    'message': f'High CPU usage: {cpu_percent}%'
                }
            
            # Check memory usage
            memory = psutil.virtual_memory()
            if memory.percent > 90:
                return {
                    'healthy': False,
                    'critical': True,
                    'message': f'High memory usage: {memory.percent}%'
                }
            
            # Check disk space
            disk = psutil.disk_usage('/')
            if disk.percent > 95:
                return {
                    'healthy': False,
                    'critical': False,
                    'message': f'Low disk space: {disk.percent}%'
                }
            
            # Warning levels
            if cpu_percent > 70:
                return {
                    'healthy': False,
                    'critical': False,
                    'message': f'Elevated CPU usage: {cpu_percent}%'
                }
            
            if memory.percent > 80:
                return {
                    'healthy': False,
                    'critical': False,
                    'message': f'High memory usage: {memory.percent}%'
                }
            
            return {'healthy': True, 'message': 'System healthy'}
            
        except Exception as e:
            return {
                'healthy': False,
                'critical': False,
                'message': f'System check error: {e}'
            }
    
    def _check_geofence(self) -> Dict[str, Any]:
        """Check geofence compliance"""
        if not self.geofence_zones or not self.last_position:
            return {'compliant': True, 'message': 'No geofence zones or position'}
        
        try:
            current_lat, current_lon = self.last_position
            
            for zone in self.geofence_zones:
                distance = self._calculate_distance(
                    current_lat, current_lon,
                    zone.center_lat, zone.center_lon
                )
                
                if zone.zone_type == 'allowed':
                    # Must be inside allowed zone
                    if distance > zone.radius_meters:
                        self.violation_counts['geofence_violations'] += 1
                        return {
                            'compliant': False,
                            'message': f'Outside allowed zone "{zone.name}": {distance:.1f}m from center'
                        }
                elif zone.zone_type == 'forbidden':
                    # Must not be in forbidden zone
                    if distance <= zone.radius_meters:
                        self.violation_counts['geofence_violations'] += 1
                        return {
                            'compliant': False,
                            'message': f'Inside forbidden zone "{zone.name}": {distance:.1f}m from center'
                        }
            
            # Check distance from start position
            if self.start_position:
                start_distance = self._calculate_distance(
                    current_lat, current_lon,
                    self.start_position[0], self.start_position[1]
                )
                
                if start_distance > self.safety_limits.max_distance_from_start:
                    self.violation_counts['distance_violations'] += 1
                    return {
                        'compliant': False,
                        'message': f'Too far from start: {start_distance:.1f}m'
                    }
            
            return {'compliant': True, 'message': 'Geofence compliant'}
            
        except Exception as e:
            return {
                'compliant': False,
                'message': f'Geofence check error: {e}'
            }
    
    def _handle_safety_violation(self, violation_type: str, message: str):
        """Handle safety violation"""
        self.logger.warning(f"Safety violation: {violation_type} - {message}")
        
        violation_data = {
            'type': violation_type,
            'message': message,
            'timestamp': datetime.now().isoformat(),
            'position': self.last_position
        }
        
        # Critical violations trigger emergency stop
        critical_violations = [
            'GPS_UNAVAILABLE',
            'MOTOR_ISSUE',
            'SYSTEM_CRITICAL',
            'GEOFENCE_VIOLATION'
        ]
        
        if violation_type in critical_violations and not self.emergency_stop_active:
            self.trigger_emergency_stop(f"Safety violation: {violation_type}")
        
        # Notify callbacks
        self._notify_safety_violation(violation_type, message, violation_data)
    
    def _notify_safety_violation(self, violation_type: str, message: str, data: Dict[str, Any]):
        """Notify safety callbacks"""
        for callback in self.safety_callbacks:
            try:
                callback(violation_type, message, data)
            except Exception as e:
                self.logger.error(f"Safety callback error: {e}")
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two GPS coordinates (Haversine formula)"""
        # Convert to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        # Haversine formula
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        a = (math.sin(dlat/2)**2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2)
        c = 2 * math.asin(math.sqrt(a))
        
        # Earth radius in meters
        earth_radius = 6371000
        
        return earth_radius * c