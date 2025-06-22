#!/usr/bin/env python3
"""
PiBoat2 Simulator
Simulates boat behavior for testing without real hardware
"""

import os
import sys
import json
import time
import uuid
import logging
import argparse
import threading
from datetime import datetime
from typing import Dict, Any, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paho.mqtt.client as mqtt
from boat.config.mqtt_config import ConfigManager


class BoatSimulator:
    """
    Simulates a PiBoat2 for testing ground control systems
    Responds to MQTT commands and publishes realistic telemetry
    """
    
    def __init__(self, config_file: Optional[str] = None, boat_id: Optional[str] = None):
        self.logger = self._setup_logging()
        
        # Load configuration
        try:
            self.config_manager = ConfigManager(config_file)
            self.config = self.config_manager.load_config()
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            sys.exit(1)
        
        # Override boat ID if provided
        if boat_id:
            self.config.boat_id = boat_id
        
        # MQTT client
        self.client = mqtt.Client(client_id=f"sim_{self.config.boat_id}_{int(time.time())}")
        self.connected = False
        
        # Simulated boat state
        self.boat_state = {
            'position': {'lat': 40.7128, 'lon': -74.0060},  # Start at NYC
            'heading': 0.0,  # North
            'speed': 0.0,  # m/s
            'throttle_percent': 0,
            'rudder_angle': 0.0,
            'battery_voltage': 12.5,
            'temperature': 25.0,
            'motor_running': False,
            'emergency_stop': False,
            'navigation_mode': 'idle'
        }
        
        # Navigation state
        self.waypoint_target = None
        self.course_target = None
        self.position_hold_target = None
        
        # Topics
        self.topics = {
            'commands': f"boat/{self.config.boat_id}/commands",
            'config': f"boat/{self.config.boat_id}/config",
            'emergency': f"boat/{self.config.boat_id}/emergency",
            'status': f"boat/{self.config.boat_id}/status",
            'gps': f"boat/{self.config.boat_id}/gps",
            'ack': f"boat/{self.config.boat_id}/ack",
            'logs': f"boat/{self.config.boat_id}/logs",
            'heartbeat': f"boat/{self.config.boat_id}/heartbeat"
        }
        
        # Simulation parameters
        self.simulation_active = False
        self.simulation_thread = None
        self.update_interval = 1.0  # seconds
        
        # Setup MQTT callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
    
    def start_simulation(self) -> bool:
        """Start the boat simulation"""
        try:
            self.logger.info(f"Starting PiBoat2 Simulator for boat: {self.config.boat_id}")
            
            # Connect to MQTT broker
            if not self._connect_mqtt():
                return False
            
            # Start simulation loop
            self.simulation_active = True
            self.simulation_thread = threading.Thread(target=self._simulation_loop, daemon=True)
            self.simulation_thread.start()
            
            self.logger.info("✅ Boat simulator started successfully")
            
            # Publish startup message
            self._publish_log("INFO", "Simulator started", {
                'boat_id': self.config.boat_id,
                'version': '2.0.0_sim',
                'initial_position': self.boat_state['position']
            })
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start simulation: {e}")
            return False
    
    def stop_simulation(self):
        """Stop the boat simulation"""
        self.logger.info("Stopping boat simulation...")
        
        self.simulation_active = False
        
        if self.simulation_thread and self.simulation_thread.is_alive():
            self.simulation_thread.join(timeout=2)
        
        # Publish shutdown message
        if self.connected:
            self._publish_log("INFO", "Simulator stopping", {
                'boat_id': self.config.boat_id,
                'final_position': self.boat_state['position']
            })
            time.sleep(0.5)  # Give time for message to send
        
        # Disconnect MQTT
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
        
        self.logger.info("Boat simulation stopped")
    
    def _connect_mqtt(self) -> bool:
        """Connect to MQTT broker"""
        try:
            self.logger.info(f"Connecting to MQTT broker {self.config.mqtt.broker_host}:{self.config.mqtt.port}")
            
            # Authentication
            if self.config.mqtt.username and self.config.mqtt.password:
                self.client.username_pw_set(self.config.mqtt.username, self.config.mqtt.password)
            
            # TLS setup if needed
            if self.config.mqtt.use_tls:
                import ssl
                context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                self.client.tls_set_context(context)
            
            result = self.client.connect(
                self.config.mqtt.broker_host,
                self.config.mqtt.port,
                self.config.mqtt.keepalive
            )
            
            if result == mqtt.MQTT_ERR_SUCCESS:
                self.client.loop_start()
                
                # Wait for connection
                timeout = 10
                start_time = time.time()
                while not self.connected and (time.time() - start_time) < timeout:
                    time.sleep(0.1)
                
                return self.connected
            else:
                self.logger.error(f"MQTT connection failed: {result}")
                return False
                
        except Exception as e:
            self.logger.error(f"MQTT connection error: {e}")
            return False
    
    def _simulation_loop(self):
        """Main simulation loop"""
        self.logger.info("Simulation loop started")
        
        last_status_time = 0
        last_gps_time = 0
        last_heartbeat_time = 0
        
        status_interval = 10  # seconds
        gps_interval = 5     # seconds
        heartbeat_interval = 30  # seconds
        
        while self.simulation_active:
            try:
                current_time = time.time()
                
                # Update boat physics
                self._update_boat_physics()
                
                # Publish periodic messages
                if current_time - last_status_time >= status_interval:
                    self._publish_status()
                    last_status_time = current_time
                
                if current_time - last_gps_time >= gps_interval:
                    self._publish_gps_data()
                    last_gps_time = current_time
                
                if current_time - last_heartbeat_time >= heartbeat_interval:
                    self._publish_heartbeat()
                    last_heartbeat_time = current_time
                
                time.sleep(self.update_interval)
                
            except Exception as e:
                self.logger.error(f"Simulation loop error: {e}")
                time.sleep(1)
        
        self.logger.info("Simulation loop stopped")
    
    def _update_boat_physics(self):
        """Update simulated boat physics"""
        dt = self.update_interval
        
        # Simple physics simulation
        if not self.boat_state['emergency_stop'] and self.boat_state['motor_running']:
            # Convert throttle to speed (very simple model)
            max_speed = 5.0  # m/s (about 10 knots)
            target_speed = (self.boat_state['throttle_percent'] / 100.0) * max_speed
            
            # Simple acceleration
            speed_diff = target_speed - self.boat_state['speed']
            acceleration = speed_diff * 0.5  # Simple damping
            self.boat_state['speed'] += acceleration * dt
            
            # Update heading based on rudder
            if self.boat_state['speed'] > 0.1:  # Only turn if moving
                turn_rate = self.boat_state['rudder_angle'] * 2.0  # degrees per second
                self.boat_state['heading'] += turn_rate * dt
                self.boat_state['heading'] = self.boat_state['heading'] % 360
            
            # Update position based on speed and heading
            if self.boat_state['speed'] > 0:
                # Convert to lat/lon movement (very approximate)
                import math
                
                heading_rad = math.radians(self.boat_state['heading'])
                
                # Distance moved in meters
                distance = self.boat_state['speed'] * dt
                
                # Convert to lat/lon (approximate)
                lat_change = (distance * math.cos(heading_rad)) / 111320  # meters per degree lat
                lon_change = (distance * math.sin(heading_rad)) / (111320 * math.cos(math.radians(self.boat_state['position']['lat'])))
                
                self.boat_state['position']['lat'] += lat_change
                self.boat_state['position']['lon'] += lon_change
        else:
            # Gradually stop if emergency stop or motor off
            self.boat_state['speed'] *= 0.9  # Drag
            if self.boat_state['speed'] < 0.01:
                self.boat_state['speed'] = 0
        
        # Update battery (simple discharge model)
        if self.boat_state['motor_running'] and self.boat_state['throttle_percent'] > 0:
            discharge_rate = 0.001 * (self.boat_state['throttle_percent'] / 100.0)
            self.boat_state['battery_voltage'] -= discharge_rate * dt
            self.boat_state['battery_voltage'] = max(10.0, self.boat_state['battery_voltage'])
        
        # Update temperature (motor heating)
        if self.boat_state['motor_running'] and self.boat_state['throttle_percent'] > 0:
            heating_rate = 0.1 * (self.boat_state['throttle_percent'] / 100.0)
            self.boat_state['temperature'] += heating_rate * dt
        else:
            # Cooling
            cooling_rate = 0.05
            self.boat_state['temperature'] -= cooling_rate * dt
            self.boat_state['temperature'] = max(20.0, self.boat_state['temperature'])
    
    def _publish_status(self):
        """Publish status message"""
        status_data = {
            'timestamp': datetime.now().isoformat(),
            'uptime_seconds': time.time(),
            'reporting_active': True,
            'error_counts': {'gps_errors': 0, 'motor_errors': 0, 'mqtt_errors': 0},
            'gps': {
                'latitude': self.boat_state['position']['lat'],
                'longitude': self.boat_state['position']['lon'],
                'speed': self.boat_state['speed'],
                'heading': self.boat_state['heading'],
                'satellites': 8,
                'fix_quality': 1,
                'timestamp': datetime.now().isoformat()
            },
            'motors': {
                'throttle_percent': self.boat_state['throttle_percent'],
                'rudder_angle': self.boat_state['rudder_angle'],
                'motor_running': self.boat_state['motor_running'],
                'current_heading': self.boat_state['heading'],
                'battery_voltage': self.boat_state['battery_voltage'],
                'temperature': self.boat_state['temperature'],
                'timestamp': datetime.now().isoformat()
            },
            'navigation': {
                'mode': self.boat_state['navigation_mode'],
                'timestamp': datetime.now().isoformat()
            },
            'mqtt': {
                'connected': self.connected,
                'topics': list(self.topics.keys())
            }
        }
        
        if self.waypoint_target:
            status_data['navigation']['waypoint'] = self.waypoint_target
        
        self._publish_message('status', status_data)
    
    def _publish_gps_data(self):
        """Publish GPS data"""
        gps_data = {
            'latitude': self.boat_state['position']['lat'],
            'longitude': self.boat_state['position']['lon'],
            'altitude': 5.0,
            'speed': self.boat_state['speed'],
            'heading': self.boat_state['heading'],
            'accuracy': 3.0,
            'satellites': 8,
            'fix_quality': 1,
            'timestamp': datetime.now().isoformat()
        }
        
        self._publish_message('gps', gps_data)
    
    def _publish_heartbeat(self):
        """Publish heartbeat message"""
        heartbeat_data = {
            'timestamp': datetime.now().isoformat(),
            'boat_id': self.config.boat_id,
            'status': 'alive',
            'uptime': time.time()
        }
        
        self._publish_message('heartbeat', heartbeat_data)
    
    def _publish_message(self, topic_key: str, data: Dict[str, Any]):
        """Publish message to MQTT"""
        if not self.connected:
            return
        
        try:
            message = {
                'timestamp': datetime.now().isoformat(),
                'boat_id': self.config.boat_id,
                'type': f'{topic_key}_update',
                'data': data
            }
            
            topic = self.topics[topic_key]
            payload = json.dumps(message, default=str)
            
            result = self.client.publish(topic, payload, qos=self.config.mqtt.qos)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.logger.debug(f"Published {topic_key} message")
            else:
                self.logger.warning(f"Failed to publish {topic_key} message")
                
        except Exception as e:
            self.logger.error(f"Message publish error: {e}")
    
    def _publish_ack(self, command_id: str, success: bool, message: str):
        """Publish command acknowledgment"""
        ack_data = {
            'timestamp': datetime.now().isoformat(),
            'boat_id': self.config.boat_id,
            'command_id': command_id,
            'success': success,
            'message': message
        }
        
        try:
            topic = self.topics['ack']
            payload = json.dumps(ack_data)
            
            result = self.client.publish(topic, payload, qos=self.config.mqtt.qos)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.logger.debug(f"Published ACK for {command_id}")
            else:
                self.logger.warning(f"Failed to publish ACK for {command_id}")
                
        except Exception as e:
            self.logger.error(f"ACK publish error: {e}")
    
    def _publish_log(self, level: str, message: str, details: Dict[str, Any] = None):
        """Publish log message"""
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'boat_id': self.config.boat_id,
            'level': level,
            'message': message,
            'details': details or {}
        }
        
        try:
            topic = self.topics['logs']
            payload = json.dumps(log_data)
            
            result = self.client.publish(topic, payload, qos=self.config.mqtt.qos)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.logger.debug(f"Published log: {message}")
            else:
                self.logger.warning(f"Failed to publish log: {message}")
                
        except Exception as e:
            self.logger.error(f"Log publish error: {e}")
    
    def _handle_command(self, command: Dict[str, Any]):
        """Handle incoming command"""
        try:
            command_id = command.get('command_id', 'unknown')
            command_type = command.get('command_type')
            payload = command.get('payload', {})
            
            self.logger.info(f"Received command: {command_type} ({command_id})")
            
            success = False
            message = ""
            
            if command_type == 'navigation':
                success, message = self._handle_navigation_command(payload)
            elif command_type == 'control':
                success, message = self._handle_control_command(payload)
            elif command_type == 'status':
                success, message = self._handle_status_command(payload)
            elif command_type == 'emergency':
                success, message = self._handle_emergency_command(payload)
            else:
                success, message = False, f"Unknown command type: {command_type}"
            
            # Send ACK if required
            if command.get('requires_ack', True):
                self._publish_ack(command_id, success, message)
            
            self.logger.info(f"Command {command_id}: {'✅' if success else '❌'} {message}")
            
        except Exception as e:
            self.logger.error(f"Command handling error: {e}")
            command_id = command.get('command_id', 'unknown')
            self._publish_ack(command_id, False, f"Command processing error: {e}")
    
    def _handle_navigation_command(self, payload: Dict[str, Any]) -> tuple:
        """Handle navigation commands"""
        action = payload.get('action')
        
        if action == 'set_waypoint':
            lat = payload.get('latitude')
            lon = payload.get('longitude')
            max_speed = payload.get('max_speed', 50)
            
            self.waypoint_target = {
                'latitude': lat,
                'longitude': lon,
                'max_speed': max_speed,
                'arrival_radius': payload.get('arrival_radius', 10.0)
            }
            
            self.boat_state['navigation_mode'] = 'waypoint'
            return True, f"Waypoint set to {lat}, {lon}"
            
        elif action == 'set_course':
            heading = payload.get('heading')
            speed = payload.get('speed')
            duration = payload.get('duration', 60)
            
            self.course_target = {
                'heading': heading,
                'speed': speed,
                'duration': duration
            }
            
            self.boat_state['navigation_mode'] = 'course'
            self.boat_state['throttle_percent'] = speed
            self.boat_state['motor_running'] = True
            
            return True, f"Course set to {heading}° at {speed}%"
            
        elif action == 'hold_position':
            self.position_hold_target = self.boat_state['position'].copy()
            self.boat_state['navigation_mode'] = 'hold_position'
            
            return True, "Position hold engaged"
        
        return False, f"Unknown navigation action: {action}"
    
    def _handle_control_command(self, payload: Dict[str, Any]) -> tuple:
        """Handle control commands"""
        action = payload.get('action')
        
        if action == 'set_rudder':
            angle = payload.get('angle', 0)
            self.boat_state['rudder_angle'] = max(-45, min(45, angle))
            return True, f"Rudder set to {self.boat_state['rudder_angle']}°"
            
        elif action == 'set_throttle':
            speed = payload.get('speed', 0)
            self.boat_state['throttle_percent'] = max(0, min(100, speed))
            self.boat_state['motor_running'] = speed > 0
            
            return True, f"Throttle set to {self.boat_state['throttle_percent']}%"
            
        elif action == 'stop_motors':
            self.boat_state['throttle_percent'] = 0
            self.boat_state['motor_running'] = False
            self.boat_state['navigation_mode'] = 'idle'
            
            return True, "Motors stopped"
        
        return False, f"Unknown control action: {action}"
    
    def _handle_status_command(self, payload: Dict[str, Any]) -> tuple:
        """Handle status commands"""
        action = payload.get('action')
        
        if action == 'get_status':
            # Status will be published in next cycle
            return True, "Status requested"
        
        return False, f"Unknown status action: {action}"
    
    def _handle_emergency_command(self, payload: Dict[str, Any]) -> tuple:
        """Handle emergency commands"""
        action = payload.get('action')
        
        if action == 'emergency_stop':
            reason = payload.get('reason', 'Remote emergency command')
            
            self.boat_state['emergency_stop'] = True
            self.boat_state['throttle_percent'] = 0
            self.boat_state['rudder_angle'] = 0
            self.boat_state['motor_running'] = False
            self.boat_state['navigation_mode'] = 'emergency_stop'
            
            self._publish_log("CRITICAL", f"Emergency stop activated: {reason}")
            
            return True, f"Emergency stop activated: {reason}"
        
        return False, f"Unknown emergency action: {action}"
    
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            self.connected = True
            self.logger.info("Simulator connected to MQTT broker")
            
            # Subscribe to command topics
            command_topics = ['commands', 'config', 'emergency']
            for topic_key in command_topics:
                topic = self.topics[topic_key]
                result, _ = client.subscribe(topic, self.config.mqtt.qos)
                if result == mqtt.MQTT_ERR_SUCCESS:
                    self.logger.debug(f"Subscribed to {topic}")
                else:
                    self.logger.error(f"Failed to subscribe to {topic}")
        else:
            self.logger.error(f"Simulator connection failed: {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        self.connected = False
        if rc != 0:
            self.logger.warning(f"Simulator disconnected unexpectedly: {rc}")
    
    def _on_message(self, client, userdata, msg):
        """MQTT message received callback"""
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode('utf-8'))
            
            # Route messages
            if topic == self.topics['commands']:
                self._handle_command(payload)
            elif topic == self.topics['config']:
                self.logger.info("Configuration update received (simulated)")
            elif topic == self.topics['emergency']:
                self._handle_command(payload)
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to decode message: {e}")
        except Exception as e:
            self.logger.error(f"Message processing error: {e}")
    
    def _setup_logging(self):
        """Setup logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - SIM - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='PiBoat2 Simulator')
    parser.add_argument('-c', '--config', type=str,
                       help='Configuration file path')
    parser.add_argument('-b', '--boat-id', type=str,
                       help='Override boat ID')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    simulator = BoatSimulator(config_file=args.config, boat_id=args.boat_id)
    
    try:
        if simulator.start_simulation():
            print(f"🚤 PiBoat2 Simulator started for boat: {simulator.config.boat_id}")
            print("Press Ctrl+C to stop")
            
            # Keep running
            while True:
                time.sleep(1)
        else:
            print("Failed to start simulator")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nStopping simulator...")
        simulator.stop_simulation()
        sys.exit(0)
    except Exception as e:
        print(f"Simulator error: {e}")
        simulator.stop_simulation()
        sys.exit(1)


if __name__ == "__main__":
    main()