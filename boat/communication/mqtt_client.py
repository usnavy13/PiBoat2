#!/usr/bin/env python3
"""
MQTT Client for PiBoat2 Communication System
Handles MQTT connection, message routing, and communication with ground control
"""

import json
import time
import logging
import threading
import ssl
from datetime import datetime
from typing import Dict, Callable, Optional, Any
from dataclasses import dataclass

import paho.mqtt.client as mqtt


@dataclass
class MQTTConfig:
    """MQTT connection configuration"""
    broker_host: str
    port: int = 1883
    use_tls: bool = False
    boat_id: str = "piboat2_default"
    username: Optional[str] = None
    password: Optional[str] = None
    keepalive: int = 60
    qos: int = 1
    reconnect_delay_min: int = 1
    reconnect_delay_max: int = 60


class MQTTClient:
    """
    MQTT client for boat communication with ground control station
    Handles connection management, message routing, and error recovery
    """
    
    def __init__(self, config: MQTTConfig):
        self.config = config
        self.client = mqtt.Client(client_id=f"{config.boat_id}_{int(time.time())}")
        self.logger = logging.getLogger(__name__)
        
        # Connection state
        self.connected = False
        self.reconnect_thread = None
        self.reconnect_delay = config.reconnect_delay_min
        self._shutdown = False
        
        # Message callbacks
        self.message_callbacks = {}
        self.connection_callbacks = []
        
        # Topics
        self.topics = {
            'commands': f"boat/{config.boat_id}/commands",
            'config': f"boat/{config.boat_id}/config",
            'emergency': f"boat/{config.boat_id}/emergency",
            'status': f"boat/{config.boat_id}/status",
            'gps': f"boat/{config.boat_id}/gps",
            'ack': f"boat/{config.boat_id}/ack",
            'logs': f"boat/{config.boat_id}/logs",
            'heartbeat': f"boat/{config.boat_id}/heartbeat"
        }
        
        # Setup client callbacks
        self._setup_client()
    
    def _setup_client(self):
        """Configure MQTT client with callbacks and settings"""
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
    
    def connect(self) -> bool:
        """
        Connect to MQTT broker
        Returns True if connection successful, False otherwise
        """
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
                    self.logger.info("MQTT connection established")
                    self._reset_reconnect_delay()
                    return True
                else:
                    self.logger.error("MQTT connection timeout")
                    return False
            else:
                self.logger.error(f"MQTT connection failed with code: {result}")
                return False
                
        except Exception as e:
            self.logger.error(f"MQTT connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from MQTT broker"""
        self._shutdown = True
        
        if self.reconnect_thread and self.reconnect_thread.is_alive():
            self.reconnect_thread.join(timeout=2)
        
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
        
        self.connected = False
        self.logger.info("MQTT client disconnected")
    
    def subscribe_to_commands(self) -> bool:
        """Subscribe to command topics"""
        if not self.connected:
            self.logger.error("Cannot subscribe - not connected to broker")
            return False
        
        topics = [
            (self.topics['commands'], self.config.qos),
            (self.topics['config'], self.config.qos),
            (self.topics['emergency'], self.config.qos)
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
    
    def publish_message(self, topic_key: str, message: Dict[str, Any], retain: bool = False) -> bool:
        """
        Publish message to specified topic
        Args:
            topic_key: Key from self.topics dict
            message: Message dictionary to publish
            retain: Whether to retain message on broker
        """
        if not self.connected:
            self.logger.warning(f"Cannot publish to {topic_key} - not connected")
            return False
        
        if topic_key not in self.topics:
            self.logger.error(f"Unknown topic key: {topic_key}")
            return False
        
        try:
            topic = self.topics[topic_key]
            payload = json.dumps(message, default=str)
            
            result = self.client.publish(topic, payload, qos=self.config.qos, retain=retain)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.logger.debug(f"Published to {topic}: {len(payload)} bytes")
                return True
            else:
                self.logger.error(f"Failed to publish to {topic}: {result.rc}")
                return False
                
        except Exception as e:
            self.logger.error(f"Publish error: {e}")
            return False
    
    def publish_status(self, status_data: Dict[str, Any]) -> bool:
        """Publish status update"""
        message = {
            "timestamp": datetime.now().isoformat(),
            "boat_id": self.config.boat_id,
            "type": "status_update",
            "data": status_data
        }
        return self.publish_message('status', message)
    
    def publish_gps_data(self, gps_data: Dict[str, Any]) -> bool:
        """Publish GPS position data"""
        message = {
            "timestamp": datetime.now().isoformat(),
            "boat_id": self.config.boat_id,
            "type": "gps_update",
            "data": gps_data
        }
        return self.publish_message('gps', message)
    
    def publish_ack(self, command_id: str, success: bool, message: str = "") -> bool:
        """Publish command acknowledgment"""
        ack_message = {
            "timestamp": datetime.now().isoformat(),
            "boat_id": self.config.boat_id,
            "command_id": command_id,
            "success": success,
            "message": message
        }
        return self.publish_message('ack', ack_message)
    
    def publish_log(self, level: str, message: str, details: Dict[str, Any] = None) -> bool:
        """Publish log message"""
        log_message = {
            "timestamp": datetime.now().isoformat(),
            "boat_id": self.config.boat_id,
            "level": level,
            "message": message,
            "details": details or {}
        }
        return self.publish_message('logs', log_message)
    
    def publish_heartbeat(self) -> bool:
        """Publish heartbeat message"""
        heartbeat = {
            "timestamp": datetime.now().isoformat(),
            "boat_id": self.config.boat_id,
            "status": "alive",
            "uptime": time.time()
        }
        return self.publish_message('heartbeat', heartbeat, retain=True)
    
    def set_message_callback(self, topic_key: str, callback: Callable[[Dict[str, Any]], None]):
        """Set callback function for specific topic"""
        if topic_key in self.topics:
            self.message_callbacks[topic_key] = callback
            self.logger.info(f"Set callback for {topic_key}")
        else:
            self.logger.error(f"Unknown topic key: {topic_key}")
    
    def add_connection_callback(self, callback: Callable[[bool], None]):
        """Add callback for connection state changes"""
        self.connection_callbacks.append(callback)
    
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            self.connected = True
            self.logger.info("MQTT connected successfully")
            
            # Subscribe to command topics
            self.subscribe_to_commands()
            
            # Notify connection callbacks
            for callback in self.connection_callbacks:
                try:
                    callback(True)
                except Exception as e:
                    self.logger.error(f"Connection callback error: {e}")
        else:
            self.logger.error(f"MQTT connection failed with code: {rc}")
            self.connected = False
    
    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        self.connected = False
        
        if rc != 0:
            self.logger.warning(f"Unexpected MQTT disconnection: {rc}")
            
            # Start reconnection if not shutting down
            if not self._shutdown:
                self._start_reconnect()
        else:
            self.logger.info("MQTT disconnected cleanly")
        
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
            
            self.logger.debug(f"Received message on {topic}: {len(msg.payload)} bytes")
            
            # Find matching topic key
            topic_key = None
            for key, topic_path in self.topics.items():
                if topic_path == topic:
                    topic_key = key
                    break
            
            if topic_key and topic_key in self.message_callbacks:
                try:
                    self.message_callbacks[topic_key](payload)
                except Exception as e:
                    self.logger.error(f"Message callback error for {topic}: {e}")
            else:
                self.logger.warning(f"No callback registered for topic: {topic}")
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to decode JSON message: {e}")
        except Exception as e:
            self.logger.error(f"Message processing error: {e}")
    
    def _on_publish(self, client, userdata, mid):
        """MQTT publish callback"""
        self.logger.debug(f"Message published: {mid}")
    
    def _on_subscribe(self, client, userdata, mid, granted_qos):
        """MQTT subscribe callback"""
        self.logger.debug(f"Subscription confirmed: {mid}, QoS: {granted_qos}")
    
    def _start_reconnect(self):
        """Start reconnection process"""
        if self.reconnect_thread and self.reconnect_thread.is_alive():
            return
        
        self.reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
        self.reconnect_thread.start()
    
    def _reconnect_loop(self):
        """Reconnection loop with exponential backoff"""
        while not self._shutdown and not self.connected:
            self.logger.info(f"Attempting reconnection in {self.reconnect_delay} seconds...")
            time.sleep(self.reconnect_delay)
            
            if self._shutdown:
                break
            
            if self.connect():
                self.logger.info("Reconnection successful")
                break
            else:
                # Exponential backoff
                self.reconnect_delay = min(
                    self.reconnect_delay * 2,
                    self.config.reconnect_delay_max
                )
    
    def _reset_reconnect_delay(self):
        """Reset reconnection delay to minimum"""
        self.reconnect_delay = self.config.reconnect_delay_min
    
    def is_connected(self) -> bool:
        """Check if connected to broker"""
        return self.connected
    
    def get_topics(self) -> Dict[str, str]:
        """Get all topic mappings"""
        return self.topics.copy()