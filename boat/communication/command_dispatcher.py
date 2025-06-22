#!/usr/bin/env python3
"""
Command Dispatcher for PiBoat2 MQTT Control System
Routes and validates incoming commands, executes them through hardware controllers
"""

import json
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass

from ..hardware.motor_controller import MotorController
from ..hardware.gps_handler import GPSHandler


@dataclass
class CommandResult:
    """Result of command execution"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error_code: Optional[str] = None


class CommandDispatcher:
    """
    Dispatches and validates MQTT commands
    Routes commands to appropriate hardware controllers
    """
    
    def __init__(self, motor_controller: MotorController, gps_handler: GPSHandler):
        self.motor_controller = motor_controller
        self.gps_handler = gps_handler
        self.logger = logging.getLogger(__name__)
        
        # Navigation controller will be set by main application
        self.navigation_controller = None
        
        # Command handlers
        self.command_handlers = {
            'navigation': self._handle_navigation_command,
            'control': self._handle_control_command,
            'status': self._handle_status_command,
            'config': self._handle_config_command,
            'emergency': self._handle_emergency_command
        }
        
        # Safety limits
        self.safety_limits = {
            'max_speed_percent': 70,
            'max_rudder_angle': 45.0,
            'command_timeout': 30,
            'emergency_stop_timeout': 5
        }
        
        # Command acknowledgment callback
        self.ack_callback: Optional[Callable[[str, bool, str], None]] = None
    
    def set_navigation_controller(self, nav_controller):
        """Set navigation controller reference"""
        self.navigation_controller = nav_controller
    
    def set_ack_callback(self, callback: Callable[[str, bool, str], None]):
        """Set callback for sending command acknowledgments"""
        self.ack_callback = callback
    
    def set_safety_limits(self, limits: Dict[str, Any]):
        """Update safety limits"""
        self.safety_limits.update(limits)
        self.logger.info(f"Safety limits updated: {limits}")
    
    def dispatch_command(self, message: Dict[str, Any]) -> CommandResult:
        """
        Main command dispatcher
        Validates and routes commands to appropriate handlers
        """
        try:
            # Validate message structure
            validation_result = self._validate_command(message)
            if not validation_result.success:
                self._send_ack(message.get('command_id'), False, validation_result.message)
                return validation_result
            
            command_type = message.get('command_type')
            command_id = message.get('command_id')
            
            self.logger.info(f"Processing command {command_id}: {command_type}")
            
            # Route to appropriate handler
            if command_type in self.command_handlers:
                result = self.command_handlers[command_type](message)
            else:
                result = CommandResult(
                    success=False,
                    message=f"Unknown command type: {command_type}",
                    error_code="UNKNOWN_COMMAND_TYPE"
                )
            
            # Send acknowledgment if required
            if message.get('requires_ack', True):
                self._send_ack(command_id, result.success, result.message)
            
            return result
            
        except Exception as e:
            error_msg = f"Command dispatch error: {e}"
            self.logger.error(error_msg)
            
            command_id = message.get('command_id', 'unknown')
            self._send_ack(command_id, False, error_msg)
            
            return CommandResult(
                success=False,
                message=error_msg,
                error_code="DISPATCH_ERROR"
            )
    
    def _validate_command(self, message: Dict[str, Any]) -> CommandResult:
        """Validate command message structure and content"""
        required_fields = ['command_id', 'timestamp', 'boat_id', 'command_type', 'payload']
        
        # Check required fields
        for field in required_fields:
            if field not in message:
                return CommandResult(
                    success=False,
                    message=f"Missing required field: {field}",
                    error_code="MISSING_FIELD"
                )
        
        # Validate command_id format
        try:
            uuid.UUID(message['command_id'])
        except ValueError:
            return CommandResult(
                success=False,
                message="Invalid command_id format (must be UUID)",
                error_code="INVALID_COMMAND_ID"
            )
        
        # Validate timestamp
        try:
            datetime.fromisoformat(message['timestamp'].replace('Z', '+00:00'))
        except ValueError:
            return CommandResult(
                success=False,
                message="Invalid timestamp format (must be ISO8601)",
                error_code="INVALID_TIMESTAMP"
            )
        
        # Validate command type
        valid_types = ['navigation', 'control', 'status', 'config', 'emergency']
        if message['command_type'] not in valid_types:
            return CommandResult(
                success=False,
                message=f"Invalid command_type. Must be one of: {valid_types}",
                error_code="INVALID_COMMAND_TYPE"
            )
        
        # Validate priority
        if 'priority' in message:
            valid_priorities = ['critical', 'high', 'medium', 'low']
            if message['priority'] not in valid_priorities:
                return CommandResult(
                    success=False,
                    message=f"Invalid priority. Must be one of: {valid_priorities}",
                    error_code="INVALID_PRIORITY"
                )
        
        return CommandResult(success=True, message="Command validated successfully")
    
    def _handle_navigation_command(self, message: Dict[str, Any]) -> CommandResult:
        """Handle navigation commands"""
        if not self.navigation_controller:
            return CommandResult(
                success=False,
                message="Navigation controller not available",
                error_code="NO_NAV_CONTROLLER"
            )
        
        payload = message['payload']
        action = payload.get('action')
        
        try:
            if action == 'set_waypoint':
                return self._execute_set_waypoint(payload)
            elif action == 'set_course':
                return self._execute_set_course(payload)
            elif action == 'hold_position':
                return self._execute_hold_position(payload)
            else:
                return CommandResult(
                    success=False,
                    message=f"Unknown navigation action: {action}",
                    error_code="UNKNOWN_NAV_ACTION"
                )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Navigation command error: {e}",
                error_code="NAV_EXECUTION_ERROR"
            )
    
    def _handle_control_command(self, message: Dict[str, Any]) -> CommandResult:
        """Handle direct control commands"""
        payload = message['payload']
        action = payload.get('action')
        
        try:
            if action == 'set_rudder':
                return self._execute_set_rudder(payload)
            elif action == 'set_throttle':
                return self._execute_set_throttle(payload)
            elif action == 'stop_motors':
                return self._execute_stop_motors()
            else:
                return CommandResult(
                    success=False,
                    message=f"Unknown control action: {action}",
                    error_code="UNKNOWN_CONTROL_ACTION"
                )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Control command error: {e}",
                error_code="CONTROL_EXECUTION_ERROR"
            )
    
    def _handle_status_command(self, message: Dict[str, Any]) -> CommandResult:
        """Handle status request commands"""
        payload = message['payload']
        action = payload.get('action')
        
        try:
            if action == 'get_status':
                include = payload.get('include', ['gps', 'motors', 'system'])
                status_data = self._collect_status_data(include)
                return CommandResult(
                    success=True,
                    message="Status collected successfully",
                    data=status_data
                )
            else:
                return CommandResult(
                    success=False,
                    message=f"Unknown status action: {action}",
                    error_code="UNKNOWN_STATUS_ACTION"
                )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Status command error: {e}",
                error_code="STATUS_EXECUTION_ERROR"
            )
    
    def _handle_config_command(self, message: Dict[str, Any]) -> CommandResult:
        """Handle configuration commands"""
        payload = message['payload']
        action = payload.get('action')
        
        try:
            if action == 'update_safety_limits':
                limits = payload.get('limits', {})
                self.set_safety_limits(limits)
                return CommandResult(
                    success=True,
                    message="Safety limits updated successfully"
                )
            else:
                return CommandResult(
                    success=False,
                    message=f"Unknown config action: {action}",
                    error_code="UNKNOWN_CONFIG_ACTION"
                )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Config command error: {e}",
                error_code="CONFIG_EXECUTION_ERROR"
            )
    
    def _handle_emergency_command(self, message: Dict[str, Any]) -> CommandResult:
        """Handle emergency commands"""
        payload = message['payload']
        action = payload.get('action')
        
        try:
            if action == 'emergency_stop':
                reason = payload.get('reason', 'unspecified')
                return self._execute_emergency_stop(reason)
            else:
                return CommandResult(
                    success=False,
                    message=f"Unknown emergency action: {action}",
                    error_code="UNKNOWN_EMERGENCY_ACTION"
                )
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Emergency command error: {e}",
                error_code="EMERGENCY_EXECUTION_ERROR"
            )
    
    def _execute_set_waypoint(self, payload: Dict[str, Any]) -> CommandResult:
        """Execute set waypoint command"""
        required_fields = ['latitude', 'longitude']
        for field in required_fields:
            if field not in payload:
                return CommandResult(
                    success=False,
                    message=f"Missing required field for set_waypoint: {field}",
                    error_code="MISSING_WAYPOINT_FIELD"
                )
        
        latitude = payload['latitude']
        longitude = payload['longitude']
        max_speed = payload.get('max_speed', 50)
        arrival_radius = payload.get('arrival_radius', 10.0)
        
        # Validate coordinates
        if not (-90 <= latitude <= 90):
            return CommandResult(
                success=False,
                message="Invalid latitude (must be -90 to 90)",
                error_code="INVALID_LATITUDE"
            )
        
        if not (-180 <= longitude <= 180):
            return CommandResult(
                success=False,
                message="Invalid longitude (must be -180 to 180)",
                error_code="INVALID_LONGITUDE"
            )
        
        # Validate speed limit
        if max_speed > self.safety_limits['max_speed_percent']:
            return CommandResult(
                success=False,
                message=f"Speed exceeds safety limit ({self.safety_limits['max_speed_percent']}%)",
                error_code="SPEED_LIMIT_EXCEEDED"
            )
        
        # Execute waypoint navigation
        result = self.navigation_controller.navigate_to_waypoint(
            latitude, longitude, max_speed, arrival_radius
        )
        
        if result:
            return CommandResult(
                success=True,
                message=f"Navigation to waypoint started: {latitude}, {longitude}"
            )
        else:
            return CommandResult(
                success=False,
                message="Failed to start waypoint navigation",
                error_code="NAV_START_FAILED"
            )
    
    def _execute_set_course(self, payload: Dict[str, Any]) -> CommandResult:
        """Execute set course command"""
        required_fields = ['heading', 'speed']
        for field in required_fields:
            if field not in payload:
                return CommandResult(
                    success=False,
                    message=f"Missing required field for set_course: {field}",
                    error_code="MISSING_COURSE_FIELD"
                )
        
        heading = payload['heading']
        speed = payload['speed']
        duration = payload.get('duration', 60)
        
        # Validate heading
        if not (0 <= heading < 360):
            return CommandResult(
                success=False,
                message="Invalid heading (must be 0-359 degrees)",
                error_code="INVALID_HEADING"
            )
        
        # Validate speed
        if speed > self.safety_limits['max_speed_percent']:
            return CommandResult(
                success=False,
                message=f"Speed exceeds safety limit ({self.safety_limits['max_speed_percent']}%)",
                error_code="SPEED_LIMIT_EXCEEDED"
            )
        
        # Execute course setting
        result = self.navigation_controller.set_course(heading, speed, duration)
        
        if result:
            return CommandResult(
                success=True,
                message=f"Course set: {heading}° at {speed}% for {duration}s"
            )
        else:
            return CommandResult(
                success=False,
                message="Failed to set course",
                error_code="COURSE_SET_FAILED"
            )
    
    def _execute_hold_position(self, payload: Dict[str, Any]) -> CommandResult:
        """Execute hold position command"""
        max_drift = payload.get('max_drift', 5.0)
        
        result = self.navigation_controller.hold_position(max_drift)
        
        if result:
            return CommandResult(
                success=True,
                message=f"Position hold engaged (max drift: {max_drift}m)"
            )
        else:
            return CommandResult(
                success=False,
                message="Failed to engage position hold",
                error_code="POSITION_HOLD_FAILED"
            )
    
    def _execute_set_rudder(self, payload: Dict[str, Any]) -> CommandResult:
        """Execute set rudder command"""
        if 'angle' not in payload:
            return CommandResult(
                success=False,
                message="Missing required field for set_rudder: angle",
                error_code="MISSING_RUDDER_ANGLE"
            )
        
        angle = payload['angle']
        
        # Validate rudder angle
        max_angle = self.safety_limits['max_rudder_angle']
        if not (-max_angle <= angle <= max_angle):
            return CommandResult(
                success=False,
                message=f"Rudder angle exceeds safety limit (±{max_angle}°)",
                error_code="RUDDER_LIMIT_EXCEEDED"
            )
        
        # Execute rudder command
        result = self.motor_controller.set_rudder_angle(angle)
        
        if result:
            return CommandResult(
                success=True,
                message=f"Rudder set to {angle}°"
            )
        else:
            return CommandResult(
                success=False,
                message="Failed to set rudder angle",
                error_code="RUDDER_SET_FAILED"
            )
    
    def _execute_set_throttle(self, payload: Dict[str, Any]) -> CommandResult:
        """Execute set throttle command"""
        if 'speed' not in payload:
            return CommandResult(
                success=False,
                message="Missing required field for set_throttle: speed",
                error_code="MISSING_THROTTLE_SPEED"
            )
        
        speed = payload['speed']
        ramp_time = payload.get('ramp_time', 1.0)
        
        # Validate speed
        if speed > self.safety_limits['max_speed_percent']:
            return CommandResult(
                success=False,
                message=f"Speed exceeds safety limit ({self.safety_limits['max_speed_percent']}%)",
                error_code="SPEED_LIMIT_EXCEEDED"
            )
        
        # Execute throttle command
        result = self.motor_controller.set_throttle(speed, ramp_time)
        
        if result:
            return CommandResult(
                success=True,
                message=f"Throttle set to {speed}% (ramp: {ramp_time}s)"
            )
        else:
            return CommandResult(
                success=False,
                message="Failed to set throttle",
                error_code="THROTTLE_SET_FAILED"
            )
    
    def _execute_stop_motors(self) -> CommandResult:
        """Execute motor stop command"""
        result = self.motor_controller.stop_all_motors()
        
        if result:
            return CommandResult(
                success=True,
                message="All motors stopped"
            )
        else:
            return CommandResult(
                success=False,
                message="Failed to stop motors",
                error_code="MOTOR_STOP_FAILED"
            )
    
    def _execute_emergency_stop(self, reason: str) -> CommandResult:
        """Execute emergency stop"""
        self.logger.critical(f"EMERGENCY STOP initiated: {reason}")
        
        # Stop all motors immediately
        motor_result = self.motor_controller.emergency_stop()
        
        # Stop navigation if active
        if self.navigation_controller:
            nav_result = self.navigation_controller.emergency_stop()
        else:
            nav_result = True
        
        if motor_result and nav_result:
            return CommandResult(
                success=True,
                message=f"Emergency stop completed: {reason}"
            )
        else:
            return CommandResult(
                success=False,
                message="Emergency stop partially failed",
                error_code="EMERGENCY_STOP_PARTIAL_FAILURE"
            )
    
    def _collect_status_data(self, include: list) -> Dict[str, Any]:
        """Collect system status data"""
        status = {
            'timestamp': datetime.now().isoformat(),
            'system': {}
        }
        
        if 'gps' in include and self.gps_handler:
            try:
                gps_data = self.gps_handler.get_position()
                status['gps'] = gps_data
            except Exception as e:
                status['gps'] = {'error': str(e)}
        
        if 'motors' in include and self.motor_controller:
            try:
                motor_status = self.motor_controller.get_status()
                status['motors'] = motor_status
            except Exception as e:
                status['motors'] = {'error': str(e)}
        
        if 'navigation' in include and self.navigation_controller:
            try:
                nav_status = self.navigation_controller.get_status()
                status['navigation'] = nav_status
            except Exception as e:
                status['navigation'] = {'error': str(e)}
        
        if 'system' in include:
            import psutil
            try:
                status['system'] = {
                    'cpu_percent': psutil.cpu_percent(),
                    'memory_percent': psutil.virtual_memory().percent,
                    'disk_percent': psutil.disk_usage('/').percent,
                    'uptime': time.time()
                }
            except Exception as e:
                status['system'] = {'error': str(e)}
        
        return status
    
    def _send_ack(self, command_id: str, success: bool, message: str):
        """Send command acknowledgment"""
        if self.ack_callback:
            try:
                self.ack_callback(command_id, success, message)
            except Exception as e:
                self.logger.error(f"Failed to send acknowledgment: {e}")