#!/usr/bin/env python3
"""
Navigation Controller for PiBoat2
Handles waypoint navigation, course control, and position holding
"""

import math
import time
import logging
import threading
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

from ..hardware.motor_controller import MotorController
from ..hardware.gps_handler import GPSHandler


@dataclass
class Position:
    """GPS position data"""
    latitude: float
    longitude: float
    timestamp: datetime
    accuracy: Optional[float] = None


@dataclass
class NavigationState:
    """Current navigation state"""
    mode: str  # 'idle', 'waypoint', 'course', 'hold_position'
    target_lat: Optional[float] = None
    target_lon: Optional[float] = None
    target_heading: Optional[float] = None
    max_speed: int = 50
    arrival_radius: float = 10.0
    started_at: Optional[datetime] = None
    duration: Optional[int] = None


class NavigationController:
    """
    High-level navigation controller
    Manages waypoint navigation, course control, and position holding
    """
    
    def __init__(self, motor_controller: MotorController, gps_handler: GPSHandler):
        self.motor_controller = motor_controller
        self.gps_handler = gps_handler
        self.logger = logging.getLogger(__name__)
        
        # Navigation state
        self.state = NavigationState(mode='idle')
        self.current_position: Optional[Position] = None
        
        # Navigation thread
        self.navigation_thread = None
        self.stop_navigation = False
        
        # Navigation parameters
        self.update_interval = 1.0  # seconds
        self.heading_tolerance = 5.0  # degrees
        self.max_turn_rate = 30.0  # degrees per second
        
        # PID controller parameters for heading
        self.heading_pid = {
            'kp': 1.0,
            'ki': 0.1,
            'kd': 0.5,
            'integral': 0.0,
            'last_error': 0.0,
            'max_output': 45.0  # max rudder angle
        }
        
        # Position hold parameters
        self.hold_position_target: Optional[Position] = None
        self.position_tolerance = 5.0  # meters
    
    def navigate_to_waypoint(self, latitude: float, longitude: float, 
                           max_speed: int = 50, arrival_radius: float = 10.0) -> bool:
        """
        Start navigation to a specific waypoint
        Returns True if navigation started successfully
        """
        try:
            # Stop any current navigation
            self.stop_current_navigation()
            
            # Validate inputs
            if not (-90 <= latitude <= 90):
                self.logger.error(f"Invalid latitude: {latitude}")
                return False
            
            if not (-180 <= longitude <= 180):
                self.logger.error(f"Invalid longitude: {longitude}")
                return False
            
            if not (0 <= max_speed <= 100):
                self.logger.error(f"Invalid max_speed: {max_speed}")
                return False
            
            # Get current position
            current_pos = self._get_current_position()
            if not current_pos:
                self.logger.error("Cannot start navigation - no GPS position available")
                return False
            
            # Calculate distance to waypoint
            distance = self._calculate_distance(
                current_pos.latitude, current_pos.longitude,
                latitude, longitude
            )
            
            self.logger.info(f"Starting waypoint navigation to {latitude}, {longitude}")
            self.logger.info(f"Distance: {distance:.1f}m, max_speed: {max_speed}%, arrival_radius: {arrival_radius}m")
            
            # Update navigation state
            self.state = NavigationState(
                mode='waypoint',
                target_lat=latitude,
                target_lon=longitude,
                max_speed=max_speed,
                arrival_radius=arrival_radius,
                started_at=datetime.now()
            )
            
            # Start navigation thread
            self._start_navigation_thread()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start waypoint navigation: {e}")
            return False
    
    def set_course(self, heading: float, speed: int, duration: int = 60) -> bool:
        """
        Set boat to follow a specific heading at given speed
        Returns True if course set successfully
        """
        try:
            # Stop any current navigation
            self.stop_current_navigation()
            
            # Validate inputs
            if not (0 <= heading < 360):
                self.logger.error(f"Invalid heading: {heading}")
                return False
            
            if not (0 <= speed <= 100):
                self.logger.error(f"Invalid speed: {speed}")
                return False
            
            self.logger.info(f"Setting course: {heading}° at {speed}% for {duration}s")
            
            # Update navigation state
            self.state = NavigationState(
                mode='course',
                target_heading=heading,
                max_speed=speed,
                duration=duration,
                started_at=datetime.now()
            )
            
            # Start navigation thread
            self._start_navigation_thread()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to set course: {e}")
            return False
    
    def hold_position(self, max_drift: float = 5.0) -> bool:
        """
        Hold current position within specified drift tolerance
        Returns True if position hold started successfully
        """
        try:
            # Stop any current navigation
            self.stop_current_navigation()
            
            # Get current position
            current_pos = self._get_current_position()
            if not current_pos:
                self.logger.error("Cannot hold position - no GPS position available")
                return False
            
            self.logger.info(f"Holding position at {current_pos.latitude}, {current_pos.longitude}")
            self.logger.info(f"Max drift: {max_drift}m")
            
            # Update navigation state
            self.state = NavigationState(
                mode='hold_position',
                target_lat=current_pos.latitude,
                target_lon=current_pos.longitude,
                started_at=datetime.now()
            )
            
            self.hold_position_target = current_pos
            self.position_tolerance = max_drift
            
            # Start navigation thread
            self._start_navigation_thread()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start position hold: {e}")
            return False
    
    def stop_current_navigation(self):
        """Stop any active navigation"""
        self.logger.info("Stopping navigation")
        
        self.stop_navigation = True
        
        if self.navigation_thread and self.navigation_thread.is_alive():
            self.navigation_thread.join(timeout=2)
        
        # Stop motors
        self.motor_controller.stop_all_motors()
        
        # Reset state
        self.state = NavigationState(mode='idle')
        self.hold_position_target = None
        
        # Reset PID controller
        self._reset_pid_controller()
    
    def emergency_stop(self) -> bool:
        """Emergency stop - immediate halt of all navigation and motors"""
        self.logger.critical("EMERGENCY STOP - Navigation controller")
        
        try:
            # Stop navigation immediately
            self.stop_navigation = True
            
            # Emergency stop motors
            motor_result = self.motor_controller.emergency_stop()
            
            # Reset navigation state
            self.state = NavigationState(mode='idle')
            self.hold_position_target = None
            
            return motor_result
            
        except Exception as e:
            self.logger.error(f"Emergency stop error: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get current navigation status"""
        status = {
            'mode': self.state.mode,
            'timestamp': datetime.now().isoformat(),
        }
        
        if self.current_position:
            status['current_position'] = {
                'latitude': self.current_position.latitude,
                'longitude': self.current_position.longitude,
                'timestamp': self.current_position.timestamp.isoformat(),
                'accuracy': self.current_position.accuracy
            }
        
        if self.state.mode == 'waypoint':
            status['waypoint'] = {
                'target_lat': self.state.target_lat,
                'target_lon': self.state.target_lon,
                'max_speed': self.state.max_speed,
                'arrival_radius': self.state.arrival_radius
            }
            
            if self.current_position:
                distance = self._calculate_distance(
                    self.current_position.latitude, self.current_position.longitude,
                    self.state.target_lat, self.state.target_lon
                )
                bearing = self._calculate_bearing(
                    self.current_position.latitude, self.current_position.longitude,
                    self.state.target_lat, self.state.target_lon
                )
                status['waypoint'].update({
                    'distance_to_target': distance,
                    'bearing_to_target': bearing
                })
        
        elif self.state.mode == 'course':
            status['course'] = {
                'target_heading': self.state.target_heading,
                'max_speed': self.state.max_speed,
                'duration': self.state.duration
            }
            
            if self.state.started_at:
                elapsed = (datetime.now() - self.state.started_at).total_seconds()
                status['course']['elapsed_time'] = elapsed
        
        elif self.state.mode == 'hold_position':
            status['hold_position'] = {
                'target_lat': self.state.target_lat,
                'target_lon': self.state.target_lon,
                'position_tolerance': self.position_tolerance
            }
            
            if self.current_position and self.hold_position_target:
                drift = self._calculate_distance(
                    self.current_position.latitude, self.current_position.longitude,
                    self.hold_position_target.latitude, self.hold_position_target.longitude
                )
                status['hold_position']['current_drift'] = drift
        
        return status
    
    def _start_navigation_thread(self):
        """Start the navigation control thread"""
        self.stop_navigation = False
        self.navigation_thread = threading.Thread(target=self._navigation_loop, daemon=True)
        self.navigation_thread.start()
    
    def _navigation_loop(self):
        """Main navigation control loop"""
        self.logger.info(f"Navigation loop started - mode: {self.state.mode}")
        
        while not self.stop_navigation:
            try:
                # Update current position
                self._update_current_position()
                
                if not self.current_position:
                    self.logger.warning("No GPS position available")
                    time.sleep(self.update_interval)
                    continue
                
                # Execute navigation based on current mode
                if self.state.mode == 'waypoint':
                    self._navigate_to_waypoint_step()
                elif self.state.mode == 'course':
                    self._follow_course_step()
                elif self.state.mode == 'hold_position':
                    self._hold_position_step()
                
                time.sleep(self.update_interval)
                
            except Exception as e:
                self.logger.error(f"Navigation loop error: {e}")
                time.sleep(self.update_interval)
        
        self.logger.info("Navigation loop stopped")
    
    def _navigate_to_waypoint_step(self):
        """Single step of waypoint navigation"""
        if not (self.current_position and self.state.target_lat and self.state.target_lon):
            return
        
        # Calculate distance to waypoint
        distance = self._calculate_distance(
            self.current_position.latitude, self.current_position.longitude,
            self.state.target_lat, self.state.target_lon
        )
        
        # Check if we've arrived
        if distance <= self.state.arrival_radius:
            self.logger.info(f"Waypoint reached! Distance: {distance:.1f}m")
            self.stop_current_navigation()
            return
        
        # Calculate bearing to waypoint
        target_bearing = self._calculate_bearing(
            self.current_position.latitude, self.current_position.longitude,
            self.state.target_lat, self.state.target_lon
        )
        
        # Set heading and speed
        self._set_heading_and_speed(target_bearing, self.state.max_speed)
        
        self.logger.debug(f"Waypoint nav: distance={distance:.1f}m, bearing={target_bearing:.1f}°")
    
    def _follow_course_step(self):
        """Single step of course following"""
        if not self.state.target_heading:
            return
        
        # Check if duration has expired
        if self.state.duration and self.state.started_at:
            elapsed = (datetime.now() - self.state.started_at).total_seconds()
            if elapsed >= self.state.duration:
                self.logger.info(f"Course duration completed ({elapsed:.1f}s)")
                self.stop_current_navigation()
                return
        
        # Follow the specified heading
        self._set_heading_and_speed(self.state.target_heading, self.state.max_speed)
        
        self.logger.debug(f"Course following: heading={self.state.target_heading}°, speed={self.state.max_speed}%")
    
    def _hold_position_step(self):
        """Single step of position holding"""
        if not (self.current_position and self.hold_position_target):
            return
        
        # Calculate drift from target position
        drift = self._calculate_distance(
            self.current_position.latitude, self.current_position.longitude,
            self.hold_position_target.latitude, self.hold_position_target.longitude
        )
        
        # If drift is within tolerance, maintain position with minimal power
        if drift <= self.position_tolerance:
            self.motor_controller.set_throttle(0)
            self.logger.debug(f"Position hold: drift={drift:.1f}m (within tolerance)")
            return
        
        # Calculate bearing back to target position
        return_bearing = self._calculate_bearing(
            self.current_position.latitude, self.current_position.longitude,
            self.hold_position_target.latitude, self.hold_position_target.longitude
        )
        
        # Use low speed to return to position
        return_speed = min(30, int(drift * 2))  # Speed proportional to drift
        self._set_heading_and_speed(return_bearing, return_speed)
        
        self.logger.debug(f"Position hold: drift={drift:.1f}m, return_bearing={return_bearing:.1f}°")
    
    def _set_heading_and_speed(self, target_heading: float, speed: int):
        """Set boat heading using PID controller and speed"""
        # Get current heading from compass
        try:
            current_heading = self.motor_controller.get_current_heading()
            if current_heading is None:
                self.logger.warning("No compass heading available")
                return
        except Exception as e:
            self.logger.error(f"Failed to get current heading: {e}")
            return
        
        # Calculate heading error
        heading_error = self._normalize_angle(target_heading - current_heading)
        
        # PID controller for rudder angle
        rudder_angle = self._calculate_pid_output(heading_error)
        
        # Set throttle and rudder
        self.motor_controller.set_throttle(speed)
        self.motor_controller.set_rudder_angle(rudder_angle)
        
        self.logger.debug(f"Heading control: target={target_heading:.1f}°, current={current_heading:.1f}°, "
                         f"error={heading_error:.1f}°, rudder={rudder_angle:.1f}°, speed={speed}%")
    
    def _calculate_pid_output(self, error: float) -> float:
        """Calculate PID controller output for heading control"""
        dt = self.update_interval
        
        # Proportional term
        p_term = self.heading_pid['kp'] * error
        
        # Integral term
        self.heading_pid['integral'] += error * dt
        # Anti-windup
        if abs(self.heading_pid['integral']) > self.heading_pid['max_output']:
            self.heading_pid['integral'] = math.copysign(self.heading_pid['max_output'], self.heading_pid['integral'])
        i_term = self.heading_pid['ki'] * self.heading_pid['integral']
        
        # Derivative term
        d_term = self.heading_pid['kd'] * (error - self.heading_pid['last_error']) / dt
        self.heading_pid['last_error'] = error
        
        # Calculate output
        output = p_term + i_term + d_term
        
        # Limit output to max rudder angle
        output = max(-self.heading_pid['max_output'], min(self.heading_pid['max_output'], output))
        
        return output
    
    def _reset_pid_controller(self):
        """Reset PID controller state"""
        self.heading_pid['integral'] = 0.0
        self.heading_pid['last_error'] = 0.0
    
    def _update_current_position(self):
        """Update current GPS position"""
        try:
            gps_data = self.gps_handler.get_position()
            if gps_data and 'latitude' in gps_data and 'longitude' in gps_data:
                self.current_position = Position(
                    latitude=gps_data['latitude'],
                    longitude=gps_data['longitude'],
                    timestamp=datetime.now(),
                    accuracy=gps_data.get('accuracy')
                )
        except Exception as e:
            self.logger.error(f"Failed to update GPS position: {e}")
            self.current_position = None
    
    def _get_current_position(self) -> Optional[Position]:
        """Get current GPS position"""
        self._update_current_position()
        return self.current_position
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate distance between two GPS coordinates using Haversine formula
        Returns distance in meters
        """
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
    
    def _calculate_bearing(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate bearing from point 1 to point 2
        Returns bearing in degrees (0-359)
        """
        # Convert to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        dlon = lon2_rad - lon1_rad
        
        y = math.sin(dlon) * math.cos(lat2_rad)
        x = (math.cos(lat1_rad) * math.sin(lat2_rad) - 
             math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon))
        
        bearing_rad = math.atan2(y, x)
        bearing_deg = math.degrees(bearing_rad)
        
        # Normalize to 0-359 degrees
        return (bearing_deg + 360) % 360
    
    def _normalize_angle(self, angle: float) -> float:
        """Normalize angle to -180 to +180 degrees"""
        while angle > 180:
            angle -= 360
        while angle < -180:
            angle += 360
        return angle