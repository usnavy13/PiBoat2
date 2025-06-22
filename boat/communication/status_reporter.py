#!/usr/bin/env python3
"""
Status Reporter for PiBoat2 MQTT System
Handles periodic status updates, GPS data, and telemetry reporting
"""

import time
import logging
import threading
import psutil
from datetime import datetime
from typing import Dict, Any, Optional, Callable

from .mqtt_client import MQTTClient
from ..hardware.gps_handler import GPSHandler
from ..hardware.motor_controller import MotorController


class StatusReporter:
    """
    Manages periodic status reporting and telemetry
    Publishes boat status, GPS data, and system health to MQTT
    """
    
    def __init__(self, mqtt_client: MQTTClient, gps_handler: GPSHandler, 
                 motor_controller: MotorController):
        self.mqtt_client = mqtt_client
        self.gps_handler = gps_handler
        self.motor_controller = motor_controller
        self.logger = logging.getLogger(__name__)
        
        # Reporting intervals (seconds)
        self.status_interval = 10
        self.gps_interval = 5
        self.heartbeat_interval = 30
        self.system_metrics_interval = 60
        
        # Reporting threads
        self.status_thread = None
        self.gps_thread = None
        self.heartbeat_thread = None
        self.system_thread = None
        
        # Control flags
        self.stop_reporting = False
        self.reporting_active = False
        
        # Navigation controller reference (set by main app)
        self.navigation_controller = None
        
        # Start time for uptime calculation
        self.start_time = time.time()
        
        # Last known values for change detection
        self.last_gps_data = None
        self.last_motor_status = None
        
        # Error counters
        self.error_counts = {
            'gps_errors': 0,
            'motor_errors': 0,
            'mqtt_errors': 0,
            'system_errors': 0
        }
    
    def set_navigation_controller(self, nav_controller):
        """Set navigation controller reference"""
        self.navigation_controller = nav_controller
    
    def set_intervals(self, status: int = None, gps: int = None, 
                     heartbeat: int = None, system: int = None):
        """Update reporting intervals"""
        if status is not None:
            self.status_interval = max(1, status)
        if gps is not None:
            self.gps_interval = max(1, gps)
        if heartbeat is not None:
            self.heartbeat_interval = max(10, heartbeat)
        if system is not None:
            self.system_metrics_interval = max(30, system)
        
        self.logger.info(f"Reporting intervals updated - Status: {self.status_interval}s, "
                        f"GPS: {self.gps_interval}s, Heartbeat: {self.heartbeat_interval}s, "
                        f"System: {self.system_metrics_interval}s")
    
    def start_periodic_reporting(self) -> bool:
        """Start all periodic reporting threads"""
        if self.reporting_active:
            self.logger.warning("Reporting already active")
            return True
        
        try:
            self.logger.info("Starting periodic reporting")
            self.stop_reporting = False
            self.reporting_active = True
            
            # Start reporting threads
            self._start_status_reporting()
            self._start_gps_reporting()
            self._start_heartbeat_reporting()
            self._start_system_reporting()
            
            self.logger.info("All reporting threads started")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start reporting: {e}")
            self.stop_periodic_reporting()
            return False
    
    def stop_periodic_reporting(self):
        """Stop all periodic reporting"""
        self.logger.info("Stopping periodic reporting")
        
        self.stop_reporting = True
        self.reporting_active = False
        
        # Wait for threads to finish
        threads = [self.status_thread, self.gps_thread, 
                  self.heartbeat_thread, self.system_thread]
        
        for thread in threads:
            if thread and thread.is_alive():
                thread.join(timeout=2)
        
        self.logger.info("Periodic reporting stopped")
    
    def publish_immediate_status(self) -> bool:
        """Publish immediate status update (not periodic)"""
        try:
            status_data = self._collect_full_status()
            return self.mqtt_client.publish_status(status_data)
        except Exception as e:
            self.logger.error(f"Failed to publish immediate status: {e}")
            self.error_counts['mqtt_errors'] += 1
            return False
    
    def publish_immediate_gps(self) -> bool:
        """Publish immediate GPS update (not periodic)"""
        try:
            gps_data = self._collect_gps_data()
            if gps_data:
                return self.mqtt_client.publish_gps_data(gps_data)
            return False
        except Exception as e:
            self.logger.error(f"Failed to publish immediate GPS: {e}")
            self.error_counts['mqtt_errors'] += 1
            return False
    
    def _start_status_reporting(self):
        """Start status reporting thread"""
        self.status_thread = threading.Thread(target=self._status_reporting_loop, daemon=True)
        self.status_thread.start()
    
    def _start_gps_reporting(self):
        """Start GPS reporting thread"""
        self.gps_thread = threading.Thread(target=self._gps_reporting_loop, daemon=True)
        self.gps_thread.start()
    
    def _start_heartbeat_reporting(self):
        """Start heartbeat reporting thread"""
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_reporting_loop, daemon=True)
        self.heartbeat_thread.start()
    
    def _start_system_reporting(self):
        """Start system metrics reporting thread"""
        self.system_thread = threading.Thread(target=self._system_reporting_loop, daemon=True)
        self.system_thread.start()
    
    def _status_reporting_loop(self):
        """Main status reporting loop"""
        self.logger.info(f"Status reporting started (interval: {self.status_interval}s)")
        
        while not self.stop_reporting:
            try:
                if self.mqtt_client.is_connected():
                    status_data = self._collect_full_status()
                    success = self.mqtt_client.publish_status(status_data)
                    
                    if success:
                        self.logger.debug("Status published successfully")
                    else:
                        self.error_counts['mqtt_errors'] += 1
                        self.logger.warning("Failed to publish status")
                else:
                    self.logger.debug("MQTT not connected, skipping status report")
                
            except Exception as e:
                self.error_counts['system_errors'] += 1
                self.logger.error(f"Status reporting error: {e}")
            
            time.sleep(self.status_interval)
        
        self.logger.info("Status reporting stopped")
    
    def _gps_reporting_loop(self):
        """GPS reporting loop"""
        self.logger.info(f"GPS reporting started (interval: {self.gps_interval}s)")
        
        while not self.stop_reporting:
            try:
                if self.mqtt_client.is_connected():
                    gps_data = self._collect_gps_data()
                    
                    if gps_data:
                        # Only publish if GPS data has changed significantly
                        if self._gps_data_changed(gps_data):
                            success = self.mqtt_client.publish_gps_data(gps_data)
                            
                            if success:
                                self.last_gps_data = gps_data
                                self.logger.debug("GPS data published")
                            else:
                                self.error_counts['mqtt_errors'] += 1
                                self.logger.warning("Failed to publish GPS data")
                    else:
                        self.logger.debug("No GPS data available")
                else:
                    self.logger.debug("MQTT not connected, skipping GPS report")
                
            except Exception as e:
                self.error_counts['gps_errors'] += 1
                self.logger.error(f"GPS reporting error: {e}")
            
            time.sleep(self.gps_interval)
        
        self.logger.info("GPS reporting stopped")
    
    def _heartbeat_reporting_loop(self):
        """Heartbeat reporting loop"""
        self.logger.info(f"Heartbeat reporting started (interval: {self.heartbeat_interval}s)")
        
        while not self.stop_reporting:
            try:
                if self.mqtt_client.is_connected():
                    success = self.mqtt_client.publish_heartbeat()
                    
                    if success:
                        self.logger.debug("Heartbeat published")
                    else:
                        self.error_counts['mqtt_errors'] += 1
                        self.logger.warning("Failed to publish heartbeat")
                else:
                    self.logger.debug("MQTT not connected, skipping heartbeat")
                
            except Exception as e:
                self.error_counts['system_errors'] += 1
                self.logger.error(f"Heartbeat reporting error: {e}")
            
            time.sleep(self.heartbeat_interval)
        
        self.logger.info("Heartbeat reporting stopped")
    
    def _system_reporting_loop(self):
        """System metrics reporting loop"""
        self.logger.info(f"System reporting started (interval: {self.system_metrics_interval}s)")
        
        while not self.stop_reporting:
            try:
                if self.mqtt_client.is_connected():
                    system_data = self._collect_system_metrics()
                    
                    # Publish as log message with system metrics
                    success = self.mqtt_client.publish_log("INFO", "System metrics", system_data)
                    
                    if success:
                        self.logger.debug("System metrics published")
                    else:
                        self.error_counts['mqtt_errors'] += 1
                        self.logger.warning("Failed to publish system metrics")
                else:
                    self.logger.debug("MQTT not connected, skipping system report")
                
            except Exception as e:
                self.error_counts['system_errors'] += 1
                self.logger.error(f"System reporting error: {e}")
            
            time.sleep(self.system_metrics_interval)
        
        self.logger.info("System reporting stopped")
    
    def _collect_full_status(self) -> Dict[str, Any]:
        """Collect comprehensive status data"""
        status = {
            'timestamp': datetime.now().isoformat(),
            'uptime_seconds': time.time() - self.start_time,
            'reporting_active': self.reporting_active,
            'error_counts': self.error_counts.copy()
        }
        
        # GPS status
        try:
            gps_data = self._collect_gps_data()
            status['gps'] = gps_data if gps_data else {'status': 'unavailable'}
        except Exception as e:
            status['gps'] = {'error': str(e)}
            self.error_counts['gps_errors'] += 1
        
        # Motor status
        try:
            motor_data = self._collect_motor_status()
            status['motors'] = motor_data if motor_data else {'status': 'unavailable'}
        except Exception as e:
            status['motors'] = {'error': str(e)}
            self.error_counts['motor_errors'] += 1
        
        # Navigation status
        if self.navigation_controller:
            try:
                nav_data = self.navigation_controller.get_status()
                status['navigation'] = nav_data
            except Exception as e:
                status['navigation'] = {'error': str(e)}
        else:
            status['navigation'] = {'status': 'not_available'}
        
        # MQTT connection status
        status['mqtt'] = {
            'connected': self.mqtt_client.is_connected(),
            'topics': list(self.mqtt_client.get_topics().keys())
        }
        
        return status
    
    def _collect_gps_data(self) -> Optional[Dict[str, Any]]:
        """Collect GPS position data"""
        try:
            gps_data = self.gps_handler.get_position()
            
            if gps_data and 'latitude' in gps_data and 'longitude' in gps_data:
                return {
                    'latitude': gps_data['latitude'],
                    'longitude': gps_data['longitude'],
                    'altitude': gps_data.get('altitude'),
                    'speed': gps_data.get('speed'),
                    'heading': gps_data.get('heading'),
                    'accuracy': gps_data.get('accuracy'),
                    'satellites': gps_data.get('satellites'),
                    'fix_quality': gps_data.get('fix_quality'),
                    'timestamp': datetime.now().isoformat()
                }
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to collect GPS data: {e}")
            return None
    
    def _collect_motor_status(self) -> Optional[Dict[str, Any]]:
        """Collect motor controller status"""
        try:
            motor_status = self.motor_controller.get_status()
            
            if motor_status:
                return {
                    'throttle_percent': motor_status.get('throttle_percent', 0),
                    'rudder_angle': motor_status.get('rudder_angle', 0),
                    'motor_running': motor_status.get('motor_running', False),
                    'current_heading': motor_status.get('current_heading'),
                    'battery_voltage': motor_status.get('battery_voltage'),
                    'temperature': motor_status.get('temperature'),
                    'timestamp': datetime.now().isoformat()
                }
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to collect motor status: {e}")
            return None
    
    def _collect_system_metrics(self) -> Dict[str, Any]:
        """Collect system performance metrics"""
        try:
            # CPU and memory usage
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Network statistics
            network = psutil.net_io_counters()
            
            # Load average (Linux)
            try:
                load_avg = psutil.getloadavg()
            except AttributeError:
                load_avg = [0, 0, 0]  # Not available on all platforms
            
            # Temperature (if available)
            temperature = None
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    # Get CPU temperature if available
                    for name, entries in temps.items():
                        if 'cpu' in name.lower() or 'coretemp' in name.lower():
                            if entries:
                                temperature = entries[0].current
                                break
            except (AttributeError, KeyError):
                pass
            
            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_available_mb': memory.available // (1024 * 1024),
                'disk_percent': disk.percent,
                'disk_free_gb': disk.free // (1024 * 1024 * 1024),
                'load_average': {
                    '1min': load_avg[0],
                    '5min': load_avg[1],
                    '15min': load_avg[2]
                },
                'network': {
                    'bytes_sent': network.bytes_sent,
                    'bytes_recv': network.bytes_recv,
                    'packets_sent': network.packets_sent,
                    'packets_recv': network.packets_recv
                },
                'temperature_celsius': temperature,
                'uptime_seconds': time.time() - self.start_time,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to collect system metrics: {e}")
            return {'error': str(e)}
    
    def _gps_data_changed(self, new_data: Dict[str, Any]) -> bool:
        """Check if GPS data has changed significantly"""
        if not self.last_gps_data:
            return True
        
        # Check position change (more than 1 meter)
        if ('latitude' in new_data and 'longitude' in new_data and
            'latitude' in self.last_gps_data and 'longitude' in self.last_gps_data):
            
            lat_diff = abs(new_data['latitude'] - self.last_gps_data['latitude'])
            lon_diff = abs(new_data['longitude'] - self.last_gps_data['longitude'])
            
            # Rough distance calculation (1 degree ≈ 111km)
            distance_change = ((lat_diff ** 2 + lon_diff ** 2) ** 0.5) * 111000
            
            if distance_change > 1.0:  # More than 1 meter
                return True
        
        # Check speed change (more than 0.5 m/s)
        if ('speed' in new_data and 'speed' in self.last_gps_data):
            speed_diff = abs(new_data['speed'] - self.last_gps_data['speed'])
            if speed_diff > 0.5:
                return True
        
        # Check heading change (more than 5 degrees)
        if ('heading' in new_data and 'heading' in self.last_gps_data):
            heading_diff = abs(new_data['heading'] - self.last_gps_data['heading'])
            # Handle heading wrap-around
            if heading_diff > 180:
                heading_diff = 360 - heading_diff
            if heading_diff > 5:
                return True
        
        # Always publish at least every 30 seconds
        last_time = self.last_gps_data.get('timestamp')
        if last_time:
            try:
                last_dt = datetime.fromisoformat(last_time)
                time_diff = (datetime.now() - last_dt).total_seconds()
                if time_diff > 30:
                    return True
            except:
                return True
        
        return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get status reporter status"""
        return {
            'reporting_active': self.reporting_active,
            'intervals': {
                'status': self.status_interval,
                'gps': self.gps_interval,
                'heartbeat': self.heartbeat_interval,
                'system': self.system_metrics_interval
            },
            'error_counts': self.error_counts.copy(),
            'uptime_seconds': time.time() - self.start_time
        }