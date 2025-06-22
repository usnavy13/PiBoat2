#!/usr/bin/env python3
"""
Server-side MQTT client for PiBoat2 ground control system
Handles communication with boats, command dispatch, and status monitoring
"""

import json
import time
import logging
import threading
import ssl
from datetime import datetime, timedelta
from typing import Dict, Callable, Optional, Any, List
from dataclasses import dataclass
from uuid import uuid4

import paho.mqtt.client as mqtt
from sqlalchemy.orm import Session

from ..config.config import get_mqtt_config
from ..database.database import get_database_manager
from ..database.models import Boat, Command, Log, GPSTrack, StatusUpdate, BoatStatus, CommandStatus, LogLevel


@dataclass
class ServerMQTTConfig:
    """Server MQTT configuration"""
    broker_host: str
    port: int = 1883
    use_tls: bool = False
    username: Optional[str] = None
    password: Optional[str] = None
    keepalive: int = 60
    qos: int = 1
    client_id: str = "piboat2_server"


class ServerMQTTClient:
    """
    Server-side MQTT client for boat communication
    Handles command dispatch, status monitoring, and data collection
    """
    
    def __init__(self):
        self.config = self._load_config()
        self.client = mqtt.Client(client_id=f"{self.config.client_id}_{int(time.time())}")
        self.logger = logging.getLogger(__name__)
        self.db_manager = get_database_manager()
        
        # Connection state
        self.connected = False
        self.reconnect_thread = None
        self.reconnect_delay = 1
        self.max_reconnect_delay = 60
        self._shutdown = False
        
        # Message handlers
        self.message_handlers: Dict[str, Callable] = {}
        self.connection_callbacks: List[Callable[[bool], None]] = []
        
        # Boat monitoring
        self.boat_heartbeats: Dict[str, datetime] = {}
        self.heartbeat_thread = None
        self.heartbeat_timeout = timedelta(minutes=5)
        
        # Setup client
        self._setup_client()
    
    def _load_config(self) -> ServerMQTTConfig:
        """Load MQTT configuration"""
        mqtt_config = get_mqtt_config()
        return ServerMQTTConfig(
            broker_host=mqtt_config.broker_host,
            port=mqtt_config.broker_port,
            use_tls=mqtt_config.use_tls,
            username=mqtt_config.username,
            password=mqtt_config.password,
            keepalive=mqtt_config.keepalive,
            qos=mqtt_config.qos
        )
    
    def _setup_client(self):
        """Configure MQTT client callbacks and settings"""
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_publish = self._on_publish
        self.client.on_subscribe = self._on_subscribe
        
        # Authentication
        if self.config.username and self.config.password:
            self.client.username_pw_set(self.config.username, self.config.password)
        
        # TLS setup
        if self.config.use_tls:
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            self.client.tls_set_context(context)
        
        # Setup message handlers
        self._setup_message_handlers()
    
    def _setup_message_handlers(self):
        """Setup handlers for different message types"""
        self.message_handlers = {
            'status': self._handle_status_message,
            'gps': self._handle_gps_message,
            'ack': self._handle_ack_message,
            'logs': self._handle_logs_message,
            'heartbeat': self._handle_heartbeat_message
        }
    
    def connect(self) -> bool:
        """Connect to MQTT broker"""
        try:
            self.logger.info(f"Connecting to MQTT broker {self.config.broker_host}:{self.config.port}")
            
            result = self.client.connect(
                self.config.broker_host,
                self.config.port,
                self.config.keepalive
            )
            
            if result == mqtt.MQTT_ERR_SUCCESS:
                self.client.loop_start()
                
                # Wait for connection confirmation
                timeout = 10
                start_time = time.time()
                while not self.connected and (time.time() - start_time) < timeout:
                    time.sleep(0.1)
                
                if self.connected:
                    self.logger.info("Server MQTT connection established")
                    self._start_heartbeat_monitor()
                    return True
                else:
                    self.logger.error("Server MQTT connection timeout")
                    return False
            else:
                self.logger.error(f"Server MQTT connection failed with code: {result}")
                return False
                
        except Exception as e:
            self.logger.error(f"Server MQTT connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from MQTT broker"""
        self._shutdown = True
        
        # Stop heartbeat monitoring
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=2)
        
        # Stop reconnection thread
        if self.reconnect_thread and self.reconnect_thread.is_alive():
            self.reconnect_thread.join(timeout=2)
        
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
        
        self.connected = False
        self.logger.info("Server MQTT client disconnected")
    
    def subscribe_to_boat_topics(self) -> bool:
        """Subscribe to all boat communication topics"""
        if not self.connected:
            self.logger.error("Cannot subscribe - not connected to broker")
            return False
        
        # Subscribe to wildcard topics for all boats
        topics = [
            ("boat/+/status", self.config.qos),
            ("boat/+/gps", self.config.qos),
            ("boat/+/ack", self.config.qos),
            ("boat/+/logs", self.config.qos),
            ("boat/+/heartbeat", self.config.qos)
        ]
        
        try:
            for topic, qos in topics:
                result, _ = self.client.subscribe(topic, qos)
                if result == mqtt.MQTT_ERR_SUCCESS:
                    self.logger.info(f"Subscribed to {topic}")
                else:
                    self.logger.error(f"Failed to subscribe to {topic}")
                    return False
            return True
            
        except Exception as e:
            self.logger.error(f"Subscription error: {e}")
            return False
    
    def send_command_to_boat(self, boat_id: str, command_type: str, payload: Dict[str, Any], 
                           priority: str = "medium", timeout_seconds: int = 30) -> str:
        """
        Send command to specific boat
        Returns command_id for tracking
        """
        if not self.connected:
            self.logger.error(f"Cannot send command to {boat_id} - not connected")
            return None
        
        command_id = str(uuid4())
        
        # Create command message
        message = {
            "command_id": command_id,
            "timestamp": datetime.now().isoformat(),
            "boat_id": boat_id,
            "command_type": command_type,
            "payload": payload,
            "priority": priority,
            "requires_ack": True,
            "timeout_seconds": timeout_seconds
        }
        
        # Store command in database
        try:
            with self.db_manager.session_scope() as session:
                command = Command(
                    command_id=command_id,
                    boat_id=boat_id,
                    command_type=command_type,
                    payload=payload,
                    status=CommandStatus.PENDING,
                    priority=priority,
                    timeout_seconds=timeout_seconds
                )
                session.add(command)
                session.commit()
        except Exception as e:
            self.logger.error(f"Failed to store command in database: {e}")
            return None
        
        # Determine topic based on command type
        if command_type == "emergency":
            topic = f"boat/{boat_id}/emergency"
        else:
            topic = f"boat/{boat_id}/commands"
        
        # Publish command
        try:
            payload_json = json.dumps(message, default=str)
            result = self.client.publish(topic, payload_json, qos=self.config.qos)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.logger.info(f"Command {command_id} sent to {boat_id}")
                
                # Update command status
                with self.db_manager.session_scope() as session:
                    command = session.query(Command).filter_by(command_id=command_id).first()
                    if command:
                        command.status = CommandStatus.SENT
                        command.sent_at = datetime.now()
                
                return command_id
            else:
                self.logger.error(f"Failed to send command to {boat_id}: {result.rc}")
                return None
                
        except Exception as e:
            self.logger.error(f"Command send error: {e}")
            return None
    
    def _handle_status_message(self, boat_id: str, message: Dict[str, Any]):
        """Handle boat status update"""
        try:
            with self.db_manager.session_scope() as session:
                # Update boat status
                boat = session.query(Boat).filter_by(boat_id=boat_id).first()
                if not boat:
                    # Register new boat
                    boat = Boat(
                        boat_id=boat_id,
                        name=f"Boat {boat_id}",
                        status=BoatStatus.ONLINE
                    )
                    session.add(boat)
                    self.logger.info(f"Registered new boat: {boat_id}")
                
                boat.status = BoatStatus.ONLINE
                boat.last_seen = datetime.now()
                
                # Store status update
                status_update = StatusUpdate(
                    boat_id=boat_id,
                    status_data=message.get('data', {})
                )
                session.add(status_update)
                
                # Update boat-specific data if available
                status_data = message.get('data', {})
                if 'battery_level' in status_data:
                    boat.battery_level = status_data['battery_level']
                
        except Exception as e:
            self.logger.error(f"Failed to handle status message from {boat_id}: {e}")
    
    def _handle_gps_message(self, boat_id: str, message: Dict[str, Any]):
        """Handle GPS position update"""
        try:
            gps_data = message.get('data', {})
            
            with self.db_manager.session_scope() as session:
                # Update boat's last known position
                boat = session.query(Boat).filter_by(boat_id=boat_id).first()
                if boat:
                    boat.last_gps_lat = gps_data.get('latitude')
                    boat.last_gps_lon = gps_data.get('longitude')
                    boat.last_gps_heading = gps_data.get('heading')
                    boat.last_gps_speed = gps_data.get('speed')
                    boat.last_seen = datetime.now()
                
                # Store GPS track
                gps_track = GPSTrack(
                    boat_id=boat_id,
                    latitude=gps_data.get('latitude'),
                    longitude=gps_data.get('longitude'),
                    heading=gps_data.get('heading'),
                    speed=gps_data.get('speed'),
                    altitude=gps_data.get('altitude'),
                    accuracy=gps_data.get('accuracy')
                )
                session.add(gps_track)
                
        except Exception as e:
            self.logger.error(f"Failed to handle GPS message from {boat_id}: {e}")
    
    def _handle_ack_message(self, boat_id: str, message: Dict[str, Any]):
        """Handle command acknowledgment"""
        try:
            command_id = message.get('command_id')
            success = message.get('success', False)
            ack_message = message.get('message', '')
            
            with self.db_manager.session_scope() as session:
                command = session.query(Command).filter_by(command_id=command_id).first()
                if command:
                    command.status = CommandStatus.COMPLETED if success else CommandStatus.FAILED
                    command.acknowledged_at = datetime.now()
                    if not success:
                        command.error_message = ack_message
                    
                    self.logger.info(f"Command {command_id} acknowledged: {'success' if success else 'failed'}")
                
        except Exception as e:
            self.logger.error(f"Failed to handle ACK message from {boat_id}: {e}")
    
    def _handle_logs_message(self, boat_id: str, message: Dict[str, Any]):
        """Handle log message from boat"""
        try:
            level_str = message.get('level', 'INFO')
            log_message = message.get('message', '')
            details = message.get('details', {})
            
            # Convert string level to enum
            try:
                level = LogLevel(level_str)
            except ValueError:
                level = LogLevel.INFO
            
            with self.db_manager.session_scope() as session:
                log_entry = Log(
                    boat_id=boat_id,
                    level=level,
                    message=log_message,
                    details=details
                )
                session.add(log_entry)
                
        except Exception as e:
            self.logger.error(f"Failed to handle log message from {boat_id}: {e}")
    
    def _handle_heartbeat_message(self, boat_id: str, message: Dict[str, Any]):
        """Handle heartbeat message"""
        self.boat_heartbeats[boat_id] = datetime.now()
        
        try:
            with self.db_manager.session_scope() as session:
                boat = session.query(Boat).filter_by(boat_id=boat_id).first()
                if boat:
                    boat.status = BoatStatus.ONLINE
                    boat.last_seen = datetime.now()
                    
        except Exception as e:
            self.logger.error(f"Failed to handle heartbeat from {boat_id}: {e}")
    
    def _start_heartbeat_monitor(self):
        """Start monitoring boat heartbeats"""
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            return
        
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_monitor_loop, daemon=True)
        self.heartbeat_thread.start()
    
    def _heartbeat_monitor_loop(self):
        """Monitor boat heartbeats and mark offline boats"""
        while not self._shutdown:
            try:
                current_time = datetime.now()
                offline_boats = []
                
                # Check for timed out boats
                for boat_id, last_heartbeat in self.boat_heartbeats.items():
                    if current_time - last_heartbeat > self.heartbeat_timeout:
                        offline_boats.append(boat_id)
                
                # Mark boats as offline
                if offline_boats:
                    with self.db_manager.session_scope() as session:
                        for boat_id in offline_boats:
                            boat = session.query(Boat).filter_by(boat_id=boat_id).first()
                            if boat and boat.status == BoatStatus.ONLINE:
                                boat.status = BoatStatus.OFFLINE
                                self.logger.warning(f"Boat {boat_id} marked as offline (heartbeat timeout)")
                
                # Remove expired heartbeats
                for boat_id in offline_boats:
                    self.boat_heartbeats.pop(boat_id, None)
                
                time.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                self.logger.error(f"Heartbeat monitor error: {e}")
                time.sleep(10)
    
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            self.connected = True
            self.logger.info("Server MQTT connected successfully")
            self.subscribe_to_boat_topics()
            
            # Reset reconnection delay
            self.reconnect_delay = 1
            
            # Notify connection callbacks
            for callback in self.connection_callbacks:
                try:
                    callback(True)
                except Exception as e:
                    self.logger.error(f"Connection callback error: {e}")
        else:
            self.logger.error(f"Server MQTT connection failed with code: {rc}")
            self.connected = False
    
    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        self.connected = False
        
        if rc != 0:
            self.logger.warning(f"Unexpected server MQTT disconnection: {rc}")
            
            # Start reconnection if not shutting down
            if not self._shutdown:
                self._start_reconnect()
        else:
            self.logger.info("Server MQTT disconnected cleanly")
        
        # Notify connection callbacks
        for callback in self.connection_callbacks:
            try:
                callback(False)
            except Exception as e:
                self.logger.error(f"Disconnection callback error: {e}")
    
    def _on_message(self, client, userdata, msg):
        """MQTT message received callback"""
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode('utf-8'))
            
            self.logger.debug(f"Server received message on {topic}: {len(msg.payload)} bytes")
            
            # Parse topic to extract boat_id and message type
            topic_parts = topic.split('/')
            if len(topic_parts) >= 3 and topic_parts[0] == 'boat':
                boat_id = topic_parts[1]
                message_type = topic_parts[2]
                
                # Route message to appropriate handler
                if message_type in self.message_handlers:
                    self.message_handlers[message_type](boat_id, payload)
                else:
                    self.logger.warning(f"No handler for message type: {message_type}")
            else:
                self.logger.warning(f"Invalid topic format: {topic}")
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to decode JSON message: {e}")
        except Exception as e:
            self.logger.error(f"Message processing error: {e}")
    
    def _on_publish(self, client, userdata, mid):
        """MQTT publish callback"""
        self.logger.debug(f"Server message published: {mid}")
    
    def _on_subscribe(self, client, userdata, mid, granted_qos):
        """MQTT subscribe callback"""
        self.logger.debug(f"Server subscription confirmed: {mid}, QoS: {granted_qos}")
    
    def _start_reconnect(self):
        """Start reconnection process"""
        if self.reconnect_thread and self.reconnect_thread.is_alive():
            return
        
        self.reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
        self.reconnect_thread.start()
    
    def _reconnect_loop(self):
        """Reconnection loop with exponential backoff"""
        while not self._shutdown and not self.connected:
            self.logger.info(f"Server attempting reconnection in {self.reconnect_delay} seconds...")
            time.sleep(self.reconnect_delay)
            
            if self._shutdown:
                break
            
            if self.connect():
                self.logger.info("Server reconnection successful")
                break
            else:
                # Exponential backoff
                self.reconnect_delay = min(
                    self.reconnect_delay * 2,
                    self.max_reconnect_delay
                )
    
    def is_connected(self) -> bool:
        """Check if connected to broker"""
        return self.connected
    
    def add_connection_callback(self, callback: Callable[[bool], None]):
        """Add callback for connection state changes"""
        self.connection_callbacks.append(callback)
    
    def get_connected_boats(self) -> List[str]:
        """Get list of currently connected boats"""
        return list(self.boat_heartbeats.keys())


# Global server MQTT client instance
server_mqtt_client = ServerMQTTClient()


def get_mqtt_client() -> ServerMQTTClient:
    """Get the global server MQTT client instance"""
    return server_mqtt_client