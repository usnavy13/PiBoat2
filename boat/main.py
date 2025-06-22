#!/usr/bin/env python3
"""
PiBoat2 Main Application
Boat-side autonomous control system with MQTT communication
"""

import os
import sys
import time
import signal
import logging
import argparse
from datetime import datetime
from typing import Optional

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from boat.config.mqtt_config import ConfigManager, load_geofence_zones
from boat.communication.mqtt_client import MQTTClient
from boat.communication.command_dispatcher import CommandDispatcher
from boat.communication.status_reporter import StatusReporter
from boat.navigation.navigation_controller import NavigationController
from boat.navigation.safety_monitor import SafetyMonitor
from boat.hardware.motor_controller import MotorController
from boat.hardware.gps_handler import GPSHandler


class PiBoat2Application:
    """
    Main PiBoat2 application
    Manages all boat systems and MQTT communication
    """
    
    def __init__(self, config_file: Optional[str] = None):
        self.logger = self._setup_logging()
        self.config_manager = ConfigManager(config_file)
        self.config = None
        
        # System components
        self.mqtt_client: Optional[MQTTClient] = None
        self.command_dispatcher: Optional[CommandDispatcher] = None
        self.navigation_controller: Optional[NavigationController] = None
        self.status_reporter: Optional[StatusReporter] = None
        self.safety_monitor: Optional[SafetyMonitor] = None
        
        # Hardware components
        self.motor_controller: Optional[MotorController] = None
        self.gps_handler: Optional[GPSHandler] = None
        
        # Application state
        self.running = False
        self.shutdown_requested = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.logger.info("PiBoat2 Application initialized")
    
    def initialize(self) -> bool:
        """Initialize all boat systems"""
        try:
            self.logger.info("Initializing PiBoat2 systems...")
            
            # Load configuration
            self.config = self.config_manager.load_config()
            
            # Initialize hardware
            if not self._initialize_hardware():
                return False
            
            # Initialize communication
            if not self._initialize_communication():
                return False
            
            # Initialize navigation
            if not self._initialize_navigation():
                return False
            
            # Initialize safety monitoring
            if not self._initialize_safety():
                return False
            
            # Setup component relationships
            self._setup_component_relationships()
            
            self.logger.info("All systems initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Initialization failed: {e}")
            return False
    
    def start(self) -> bool:
        """Start the boat control system"""
        if not self.initialize():
            self.logger.error("Failed to initialize systems")
            return False
        
        try:
            self.logger.info("Starting PiBoat2 control system")
            
            # Connect to MQTT broker
            if not self.mqtt_client.connect():
                self.logger.error("Failed to connect to MQTT broker")
                return False
            
            # Start safety monitoring
            if not self.safety_monitor.start_monitoring():
                self.logger.error("Failed to start safety monitoring")
                return False
            
            # Start status reporting
            if not self.status_reporter.start_periodic_reporting():
                self.logger.error("Failed to start status reporting")
                return False
            
            self.running = True
            self.logger.info("PiBoat2 control system started successfully")
            
            # Publish startup status
            self._publish_startup_status()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start system: {e}")
            return False
    
    def run(self):
        """Main application loop"""
        if not self.running:
            self.logger.error("System not running - call start() first")
            return
        
        self.logger.info("Entering main application loop")
        
        try:
            while self.running and not self.shutdown_requested:
                # Main loop - most work is done in background threads
                # Just monitor system health and handle any maintenance tasks
                
                self._check_system_health()
                time.sleep(5)  # Check every 5 seconds
                
        except KeyboardInterrupt:
            self.logger.info("Shutdown requested by user")
        except Exception as e:
            self.logger.error(f"Main loop error: {e}")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Graceful shutdown of all systems"""
        if self.shutdown_requested:
            return  # Already shutting down
        
        self.logger.info("Shutting down PiBoat2 system...")
        self.shutdown_requested = True
        self.running = False
        
        try:
            # Stop all motors first (safety)
            if self.motor_controller:
                self.motor_controller.emergency_stop()
            
            # Stop navigation
            if self.navigation_controller:
                self.navigation_controller.stop_current_navigation()
            
            # Stop safety monitoring
            if self.safety_monitor:
                self.safety_monitor.stop_monitoring()
            
            # Stop status reporting
            if self.status_reporter:
                self.status_reporter.stop_periodic_reporting()
            
            # Publish shutdown status
            if self.mqtt_client and self.mqtt_client.is_connected():
                self._publish_shutdown_status()
                time.sleep(1)  # Give time for message to send
            
            # Disconnect MQTT
            if self.mqtt_client:
                self.mqtt_client.disconnect()
            
            # Close hardware connections
            if self.gps_handler:
                self.gps_handler.close()
            
            if self.motor_controller:
                self.motor_controller.close()
            
            self.logger.info("PiBoat2 system shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
    
    def _initialize_hardware(self) -> bool:
        """Initialize hardware components"""
        self.logger.info("Initializing hardware components...")
        
        try:
            # Initialize GPS handler
            gps_device = self.config.hardware['gps_device']
            gps_baudrate = self.config.hardware['gps_baudrate']
            
            self.gps_handler = GPSHandler(port=gps_device, baudrate=gps_baudrate)
            try:
                self.gps_handler.start()
                self.logger.info("GPS handler initialized and started")
            except Exception as e:
                self.logger.warning(f"GPS initialization failed: {e} - continuing without GPS")
                self.gps_handler = None
            
            # Initialize motor controller
            self.motor_controller = MotorController()
            try:
                self.motor_controller.initialize()
                self.logger.info("Motor controller initialized")
            except Exception as e:
                self.logger.error(f"Motor controller initialization failed: {e}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Hardware initialization failed: {e}")
            return False
    
    def _initialize_communication(self) -> bool:
        """Initialize MQTT communication"""
        self.logger.info("Initializing MQTT communication...")
        
        try:
            # Create MQTT client
            self.mqtt_client = MQTTClient(self.config.mqtt)
            
            # Create command dispatcher
            self.command_dispatcher = CommandDispatcher(
                self.motor_controller, 
                self.gps_handler
            )
            
            # Set safety limits from config
            safety_limits = {
                'max_speed_percent': self.config.safety.max_speed_percent,
                'max_rudder_angle': self.config.safety.max_rudder_angle,
                'command_timeout': self.config.safety.command_timeout_seconds
            }
            self.command_dispatcher.set_safety_limits(safety_limits)
            
            # Setup MQTT message callbacks
            self.mqtt_client.set_message_callback('commands', self._handle_command_message)
            self.mqtt_client.set_message_callback('config', self._handle_config_message)
            self.mqtt_client.set_message_callback('emergency', self._handle_emergency_message)
            
            # Setup connection callback
            self.mqtt_client.add_connection_callback(self._handle_connection_change)
            
            self.logger.info("MQTT communication initialized")
            return True
            
        except Exception as e:
            self.logger.error(f"Communication initialization failed: {e}")
            return False
    
    def _initialize_navigation(self) -> bool:
        """Initialize navigation system"""
        if not self.motor_controller:
            self.logger.error("Cannot initialize navigation - no motor controller")
            return False
        
        self.logger.info("Initializing navigation system...")
        
        try:
            # Create navigation controller
            self.navigation_controller = NavigationController(
                self.motor_controller,
                self.gps_handler
            )
            
            # Apply navigation configuration
            nav_config = self.config.navigation
            self.navigation_controller.update_interval = nav_config['update_interval']
            self.navigation_controller.heading_tolerance = nav_config['heading_tolerance']
            self.navigation_controller.max_turn_rate = nav_config['max_turn_rate']
            self.navigation_controller.position_tolerance = nav_config['position_tolerance']
            
            # Update PID parameters
            self.navigation_controller.heading_pid.update({
                'kp': nav_config['pid_kp'],
                'ki': nav_config['pid_ki'],
                'kd': nav_config['pid_kd']
            })
            
            self.logger.info("Navigation system initialized")
            return True
            
        except Exception as e:
            self.logger.error(f"Navigation initialization failed: {e}")
            return False
    
    def _initialize_safety(self) -> bool:
        """Initialize safety monitoring"""
        self.logger.info("Initializing safety monitoring...")
        
        try:
            # Create safety monitor
            self.safety_monitor = SafetyMonitor(
                self.gps_handler,
                self.motor_controller
            )
            
            # Set safety limits from config
            self.safety_monitor.set_safety_limits({
                'max_speed_percent': self.config.safety.max_speed_percent,
                'max_rudder_angle': self.config.safety.max_rudder_angle,
                'max_distance_from_start': self.config.safety.max_distance_from_start,
                'battery_voltage_min': self.config.safety.battery_voltage_min,
                'temperature_max': self.config.safety.temperature_max,
                'gps_timeout_seconds': self.config.safety.gps_timeout_seconds,
                'command_timeout_seconds': self.config.safety.command_timeout_seconds
            })
            
            # Load geofence zones
            geofence_zones = load_geofence_zones()
            for zone in geofence_zones:
                self.safety_monitor.add_geofence_zone(zone)
            
            # Add safety callback
            self.safety_monitor.add_safety_callback(self._handle_safety_violation)
            
            self.logger.info("Safety monitoring initialized")
            return True
            
        except Exception as e:
            self.logger.error(f"Safety initialization failed: {e}")
            return False
    
    def _setup_component_relationships(self):
        """Setup cross-references between components"""
        # Set navigation controller in command dispatcher
        if self.command_dispatcher and self.navigation_controller:
            self.command_dispatcher.set_navigation_controller(self.navigation_controller)
        
        # Set acknowledgment callback in command dispatcher
        if self.command_dispatcher and self.mqtt_client:
            self.command_dispatcher.set_ack_callback(self.mqtt_client.publish_ack)
        
        # Create status reporter
        if self.mqtt_client and self.gps_handler and self.motor_controller:
            self.status_reporter = StatusReporter(
                self.mqtt_client,
                self.gps_handler,
                self.motor_controller
            )
            
            # Set navigation controller in status reporter
            if self.navigation_controller:
                self.status_reporter.set_navigation_controller(self.navigation_controller)
            
            # Set reporting intervals from config
            reporting_config = self.config.reporting
            self.status_reporter.set_intervals(
                status=reporting_config['status_interval'],
                gps=reporting_config['gps_interval'],
                heartbeat=reporting_config['heartbeat_interval'],
                system=reporting_config['system_metrics_interval']
            )
    
    def _handle_command_message(self, message: dict):
        """Handle incoming command messages"""
        try:
            self.logger.info(f"Received command: {message.get('command_type')}")
            
            # Update safety monitor command timestamp
            if self.safety_monitor:
                self.safety_monitor.update_command_time()
            
            # Dispatch command
            if self.command_dispatcher:
                result = self.command_dispatcher.dispatch_command(message)
                
                if result.success:
                    self.logger.info(f"Command executed successfully: {result.message}")
                else:
                    self.logger.warning(f"Command failed: {result.message}")
            
        except Exception as e:
            self.logger.error(f"Command handling error: {e}")
    
    def _handle_config_message(self, message: dict):
        """Handle configuration update messages"""
        try:
            self.logger.info("Received configuration update")
            
            payload = message.get('payload', {})
            
            # Update safety limits
            if 'safety_limits' in payload:
                limits = payload['safety_limits']
                if self.safety_monitor:
                    self.safety_monitor.set_safety_limits(limits)
                if self.command_dispatcher:
                    self.command_dispatcher.set_safety_limits(limits)
                self.config_manager.update_safety_limits(**limits)
            
            # Update reporting intervals
            if 'reporting_intervals' in payload:
                intervals = payload['reporting_intervals']
                if self.status_reporter:
                    self.status_reporter.set_intervals(**intervals)
                self.config_manager.update_reporting_intervals(**intervals)
            
            # Save updated configuration
            self.config_manager.save_config()
            
            self.logger.info("Configuration updated successfully")
            
        except Exception as e:
            self.logger.error(f"Configuration update error: {e}")
    
    def _handle_emergency_message(self, message: dict):
        """Handle emergency messages"""
        try:
            self.logger.critical("Received emergency message")
            
            payload = message.get('payload', {})
            action = payload.get('action')
            reason = payload.get('reason', 'Remote emergency command')
            
            if action == 'emergency_stop':
                # Trigger emergency stop
                if self.safety_monitor:
                    self.safety_monitor.trigger_emergency_stop(reason)
                else:
                    # Fallback - stop motors directly
                    if self.motor_controller:
                        self.motor_controller.emergency_stop()
            
            self.logger.critical(f"Emergency action completed: {action}")
            
        except Exception as e:
            self.logger.error(f"Emergency handling error: {e}")
    
    def _handle_connection_change(self, connected: bool):
        """Handle MQTT connection state changes"""
        if connected:
            self.logger.info("MQTT connection established")
            # Publish reconnection status
            if self.status_reporter:
                self.status_reporter.publish_immediate_status()
        else:
            self.logger.warning("MQTT connection lost")
    
    def _handle_safety_violation(self, violation_type: str, message: str, data: dict):
        """Handle safety violations"""
        self.logger.warning(f"Safety violation: {violation_type} - {message}")
        
        # Publish safety violation as log
        if self.mqtt_client:
            self.mqtt_client.publish_log("WARNING", f"Safety violation: {violation_type}", {
                'violation_type': violation_type,
                'message': message,
                'data': data
            })
    
    def _check_system_health(self):
        """Periodic system health check"""
        try:
            # Check MQTT connection
            if not self.mqtt_client.is_connected():
                self.logger.warning("MQTT connection lost - attempting reconnection")
                self.mqtt_client.connect()
            
            # Check if emergency stop is active
            if self.safety_monitor and self.safety_monitor.emergency_stop_active:
                self.logger.warning("Emergency stop is active")
            
        except Exception as e:
            self.logger.error(f"System health check error: {e}")
    
    def _publish_startup_status(self):
        """Publish system startup status"""
        try:
            startup_data = {
                'event': 'system_startup',
                'timestamp': datetime.now().isoformat(),
                'boat_id': self.config.boat_id,
                'version': '2.0.0',
                'systems': {
                    'gps': self.gps_handler is not None,
                    'motors': self.motor_controller is not None,
                    'navigation': self.navigation_controller is not None,
                    'safety': self.safety_monitor is not None
                }
            }
            
            self.mqtt_client.publish_log("INFO", "System startup complete", startup_data)
            
        except Exception as e:
            self.logger.error(f"Failed to publish startup status: {e}")
    
    def _publish_shutdown_status(self):
        """Publish system shutdown status"""
        try:
            shutdown_data = {
                'event': 'system_shutdown',
                'timestamp': datetime.now().isoformat(),
                'boat_id': self.config.boat_id,
                'reason': 'graceful_shutdown'
            }
            
            self.mqtt_client.publish_log("INFO", "System shutdown initiated", shutdown_data)
            
        except Exception as e:
            self.logger.error(f"Failed to publish shutdown status: {e}")
    
    def _signal_handler(self, signum, frame):
        """Handle system signals"""
        self.logger.info(f"Received signal {signum}")
        self.shutdown_requested = True
        self.running = False
    
    def _setup_logging(self) -> logging.Logger:
        """Setup application logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('/var/log/piboat2/boat.log', mode='a')
            ]
        )
        
        # Create log directory if it doesn't exist
        os.makedirs('/var/log/piboat2', exist_ok=True)
        
        return logging.getLogger(__name__)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='PiBoat2 Autonomous Boat Control System')
    parser.add_argument('-c', '--config', type=str, 
                       help='Configuration file path')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--dry-run', action='store_true',
                       help='Initialize but do not start motors (testing mode)')
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create and run application
    app = PiBoat2Application(config_file=args.config)
    
    try:
        if app.start():
            print("PiBoat2 system started successfully")
            print("Press Ctrl+C to shutdown")
            
            if args.dry_run:
                print("DRY RUN MODE - Motors disabled")
                time.sleep(5)
                app.shutdown()
            else:
                app.run()
        else:
            print("Failed to start PiBoat2 system")
            sys.exit(1)
            
    except Exception as e:
        print(f"Application error: {e}")
        app.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()