#!/usr/bin/env python3
"""
Comprehensive MQTT System Test Script for PiBoat2
Tests all MQTT communication and control functionality
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
from typing import Dict, Any, List, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paho.mqtt.client as mqtt
from boat.config.mqtt_config import ConfigManager


class MQTTSystemTester:
    """
    Comprehensive MQTT system tester
    Simulates ground control commands and validates boat responses
    """
    
    def __init__(self, config_file: Optional[str] = None):
        self.logger = self._setup_logging()
        
        # Load configuration
        self.config_manager = ConfigManager(config_file)
        self.config = self.config_manager.load_config()
        
        # MQTT client for testing
        self.client = mqtt.Client(client_id=f"test_client_{int(time.time())}")
        self.connected = False
        
        # Test state
        self.responses = {}
        self.test_results = []
        self.current_test = None
        
        # Topics
        self.boat_id = self.config.boat_id
        self.topics = {
            'commands': f"boat/{self.boat_id}/commands",
            'config': f"boat/{self.boat_id}/config", 
            'emergency': f"boat/{self.boat_id}/emergency",
            'status': f"boat/{self.boat_id}/status",
            'gps': f"boat/{self.boat_id}/gps",
            'ack': f"boat/{self.boat_id}/ack",
            'logs': f"boat/{self.boat_id}/logs",
            'heartbeat': f"boat/{self.boat_id}/heartbeat"
        }
        
        # Setup MQTT callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        
        # Test timeout
        self.test_timeout = 30  # seconds
    
    def connect(self) -> bool:
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
            self.logger.error(f"Connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from MQTT broker"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
        self.connected = False
    
    def run_all_tests(self) -> bool:
        """Run all MQTT system tests"""
        self.logger.info("Starting comprehensive MQTT system tests")
        
        if not self.connect():
            self.logger.error("Failed to connect to MQTT broker")
            return False
        
        try:
            # Subscribe to response topics
            self._subscribe_to_responses()
            
            # Run test suite
            tests_passed = 0
            total_tests = 0
            
            # Basic connectivity tests
            if self._test_basic_connectivity():
                tests_passed += 1
            total_tests += 1
            
            # Command tests
            if self._test_navigation_commands():
                tests_passed += 1
            total_tests += 1
            
            if self._test_control_commands():
                tests_passed += 1
            total_tests += 1
            
            if self._test_status_commands():
                tests_passed += 1
            total_tests += 1
            
            if self._test_config_commands():
                tests_passed += 1
            total_tests += 1
            
            if self._test_emergency_commands():
                tests_passed += 1
            total_tests += 1
            
            # Response validation tests
            if self._test_response_validation():
                tests_passed += 1
            total_tests += 1
            
            # Performance tests
            if self._test_message_throughput():
                tests_passed += 1
            total_tests += 1
            
            # Print results
            self._print_test_summary(tests_passed, total_tests)
            
            return tests_passed == total_tests
            
        except Exception as e:
            self.logger.error(f"Test execution error: {e}")
            return False
        finally:
            self.disconnect()
    
    def _test_basic_connectivity(self) -> bool:
        """Test basic MQTT connectivity and heartbeat"""
        self.logger.info("Testing basic connectivity...")
        
        try:
            # Wait for heartbeat message
            start_time = time.time()
            heartbeat_received = False
            
            while (time.time() - start_time) < 35:  # Wait longer than heartbeat interval
                if 'heartbeat' in self.responses:
                    heartbeat_received = True
                    break
                time.sleep(1)
            
            if heartbeat_received:
                self.logger.info("✅ Heartbeat received - basic connectivity OK")
                return True
            else:
                self.logger.error("❌ No heartbeat received")
                return False
                
        except Exception as e:
            self.logger.error(f"Basic connectivity test failed: {e}")
            return False
    
    def _test_navigation_commands(self) -> bool:
        """Test navigation command processing"""
        self.logger.info("Testing navigation commands...")
        
        try:
            # Test set waypoint command
            waypoint_cmd = self._create_command('navigation', {
                'action': 'set_waypoint',
                'latitude': 40.7128,
                'longitude': -74.0060,
                'max_speed': 50,
                'arrival_radius': 10.0
            })
            
            if not self._send_command_and_wait_ack(waypoint_cmd):
                return False
            
            # Test set course command
            course_cmd = self._create_command('navigation', {
                'action': 'set_course',
                'heading': 270.0,
                'speed': 30,
                'duration': 60
            })
            
            if not self._send_command_and_wait_ack(course_cmd):
                return False
            
            # Test hold position command
            hold_cmd = self._create_command('navigation', {
                'action': 'hold_position',
                'max_drift': 5.0
            })
            
            if not self._send_command_and_wait_ack(hold_cmd):
                return False
            
            self.logger.info("✅ Navigation commands test passed")
            return True
            
        except Exception as e:
            self.logger.error(f"Navigation commands test failed: {e}")
            return False
    
    def _test_control_commands(self) -> bool:
        """Test direct control commands"""
        self.logger.info("Testing control commands...")
        
        try:
            # Test set rudder command
            rudder_cmd = self._create_command('control', {
                'action': 'set_rudder',
                'angle': -20.0
            })
            
            if not self._send_command_and_wait_ack(rudder_cmd):
                return False
            
            # Test set throttle command  
            throttle_cmd = self._create_command('control', {
                'action': 'set_throttle',
                'speed': 25,
                'ramp_time': 2.0
            })
            
            if not self._send_command_and_wait_ack(throttle_cmd):
                return False
            
            # Test stop motors command
            stop_cmd = self._create_command('control', {
                'action': 'stop_motors'
            })
            
            if not self._send_command_and_wait_ack(stop_cmd):
                return False
            
            self.logger.info("✅ Control commands test passed")
            return True
            
        except Exception as e:
            self.logger.error(f"Control commands test failed: {e}")
            return False
    
    def _test_status_commands(self) -> bool:
        """Test status request commands"""
        self.logger.info("Testing status commands...")
        
        try:
            # Test get status command
            status_cmd = self._create_command('status', {
                'action': 'get_status',
                'include': ['gps', 'motors', 'system']
            })
            
            if not self._send_command_and_wait_ack(status_cmd):
                return False
            
            # Verify status messages are being received
            start_time = time.time()
            status_received = False
            
            while (time.time() - start_time) < 15:  # Wait for status update
                if 'status' in self.responses:
                    status_received = True
                    break
                time.sleep(1)
            
            if not status_received:
                self.logger.error("❌ No status messages received")
                return False
            
            self.logger.info("✅ Status commands test passed")
            return True
            
        except Exception as e:
            self.logger.error(f"Status commands test failed: {e}")
            return False
    
    def _test_config_commands(self) -> bool:
        """Test configuration update commands"""
        self.logger.info("Testing config commands...")
        
        try:
            # Test safety limits update
            config_cmd = self._create_config_command({
                'safety_limits': {
                    'max_speed_percent': 60,
                    'max_rudder_angle': 40.0
                }
            })
            
            if not self._send_config_and_wait_ack(config_cmd):
                return False
            
            # Test reporting intervals update
            config_cmd2 = self._create_config_command({
                'reporting_intervals': {
                    'status_interval': 15,
                    'gps_interval': 8
                }
            })
            
            if not self._send_config_and_wait_ack(config_cmd2):
                return False
            
            self.logger.info("✅ Config commands test passed")
            return True
            
        except Exception as e:
            self.logger.error(f"Config commands test failed: {e}")
            return False
    
    def _test_emergency_commands(self) -> bool:
        """Test emergency commands"""
        self.logger.info("Testing emergency commands...")
        
        try:
            # Test emergency stop command
            emergency_cmd = self._create_emergency_command({
                'action': 'emergency_stop',
                'reason': 'test_emergency_stop'
            })
            
            # Send emergency command (no ACK expected for emergency)
            topic = self.topics['emergency']
            payload = json.dumps(emergency_cmd)
            
            result = self.client.publish(topic, payload, qos=self.config.mqtt.qos)
            
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                self.logger.error(f"❌ Failed to send emergency command")
                return False
            
            # Wait a moment for processing
            time.sleep(2)
            
            self.logger.info("✅ Emergency commands test passed")
            return True
            
        except Exception as e:
            self.logger.error(f"Emergency commands test failed: {e}")
            return False
    
    def _test_response_validation(self) -> bool:
        """Test response message validation"""
        self.logger.info("Testing response validation...")
        
        try:
            # Test invalid command (should get negative ACK)
            invalid_cmd = self._create_command('invalid_type', {
                'action': 'invalid_action'
            })
            
            command_id = invalid_cmd['command_id']
            topic = self.topics['commands']
            payload = json.dumps(invalid_cmd)
            
            result = self.client.publish(topic, payload, qos=self.config.mqtt.qos)
            
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                self.logger.error("❌ Failed to send invalid command")
                return False
            
            # Wait for negative ACK
            start_time = time.time()
            ack_received = False
            
            while (time.time() - start_time) < self.test_timeout:
                if command_id in self.responses.get('ack', {}):
                    ack_data = self.responses['ack'][command_id]
                    if not ack_data.get('success', True):  # Should be negative ACK
                        ack_received = True
                        break
                time.sleep(0.1)
            
            if not ack_received:
                self.logger.error("❌ No negative ACK received for invalid command")
                return False
            
            self.logger.info("✅ Response validation test passed")
            return True
            
        except Exception as e:
            self.logger.error(f"Response validation test failed: {e}")
            return False
    
    def _test_message_throughput(self) -> bool:
        """Test message throughput and latency"""
        self.logger.info("Testing message throughput...")
        
        try:
            # Send multiple status requests rapidly
            command_ids = []
            start_time = time.time()
            
            for i in range(5):
                status_cmd = self._create_command('status', {
                    'action': 'get_status',
                    'include': ['system']
                })
                command_ids.append(status_cmd['command_id'])
                
                topic = self.topics['commands']
                payload = json.dumps(status_cmd)
                self.client.publish(topic, payload, qos=self.config.mqtt.qos)
                
                time.sleep(0.1)  # Small delay between commands
            
            # Wait for all ACKs
            acks_received = 0
            timeout = time.time() + self.test_timeout
            
            while time.time() < timeout and acks_received < len(command_ids):
                for cmd_id in command_ids:
                    if cmd_id in self.responses.get('ack', {}) and cmd_id not in [r['command_id'] for r in self.test_results]:
                        acks_received += 1
                        latency = time.time() - start_time
                        self.test_results.append({
                            'command_id': cmd_id,
                            'latency': latency
                        })
                time.sleep(0.1)
            
            if acks_received == len(command_ids):
                avg_latency = sum(r['latency'] for r in self.test_results[-acks_received:]) / acks_received
                self.logger.info(f"✅ Throughput test passed - {acks_received} commands, avg latency: {avg_latency:.2f}s")
                return True
            else:
                self.logger.error(f"❌ Throughput test failed - only {acks_received}/{len(command_ids)} ACKs received")
                return False
                
        except Exception as e:
            self.logger.error(f"Throughput test failed: {e}")
            return False
    
    def _subscribe_to_responses(self):
        """Subscribe to all response topics"""
        response_topics = ['status', 'gps', 'ack', 'logs', 'heartbeat']
        
        for topic_key in response_topics:
            topic = self.topics[topic_key]
            result, _ = self.client.subscribe(topic, self.config.mqtt.qos)
            if result == mqtt.MQTT_ERR_SUCCESS:
                self.logger.debug(f"Subscribed to {topic}")
            else:
                self.logger.error(f"Failed to subscribe to {topic}")
    
    def _create_command(self, command_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a command message"""
        return {
            'command_id': str(uuid.uuid4()),
            'timestamp': datetime.now().isoformat(),
            'boat_id': self.boat_id,
            'command_type': command_type,
            'payload': payload,
            'priority': 'medium',
            'requires_ack': True,
            'timeout_seconds': 30
        }
    
    def _create_config_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a configuration command"""
        return {
            'command_id': str(uuid.uuid4()),
            'timestamp': datetime.now().isoformat(),
            'boat_id': self.boat_id,
            'command_type': 'config',
            'payload': payload,
            'priority': 'medium',
            'requires_ack': True
        }
    
    def _create_emergency_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create an emergency command"""
        return {
            'command_id': str(uuid.uuid4()),
            'timestamp': datetime.now().isoformat(),
            'boat_id': self.boat_id,
            'command_type': 'emergency',
            'payload': payload,
            'priority': 'critical',
            'requires_ack': False
        }
    
    def _send_command_and_wait_ack(self, command: Dict[str, Any]) -> bool:
        """Send command and wait for acknowledgment"""
        command_id = command['command_id']
        topic = self.topics['commands']
        payload = json.dumps(command)
        
        # Send command
        result = self.client.publish(topic, payload, qos=self.config.mqtt.qos)
        
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            self.logger.error(f"❌ Failed to send command {command_id}")
            return False
        
        # Wait for ACK
        start_time = time.time()
        while (time.time() - start_time) < self.test_timeout:
            if command_id in self.responses.get('ack', {}):
                ack_data = self.responses['ack'][command_id]
                if ack_data.get('success', False):
                    self.logger.debug(f"✅ ACK received for {command_id}")
                    return True
                else:
                    self.logger.error(f"❌ Negative ACK for {command_id}: {ack_data.get('message')}")
                    return False
            time.sleep(0.1)
        
        self.logger.error(f"❌ Timeout waiting for ACK for {command_id}")
        return False
    
    def _send_config_and_wait_ack(self, config_cmd: Dict[str, Any]) -> bool:
        """Send config command and wait for acknowledgment"""
        command_id = config_cmd['command_id']
        topic = self.topics['config']
        payload = json.dumps(config_cmd)
        
        # Send config command
        result = self.client.publish(topic, payload, qos=self.config.mqtt.qos)
        
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            self.logger.error(f"❌ Failed to send config command {command_id}")
            return False
        
        # Wait for processing (config commands may not send ACK)
        time.sleep(2)
        self.logger.debug(f"✅ Config command sent: {command_id}")
        return True
    
    def _print_test_summary(self, passed: int, total: int):
        """Print test results summary"""
        self.logger.info("=" * 50)
        self.logger.info("MQTT SYSTEM TEST SUMMARY")
        self.logger.info("=" * 50)
        self.logger.info(f"Tests Passed: {passed}/{total}")
        self.logger.info(f"Success Rate: {(passed/total)*100:.1f}%")
        
        if passed == total:
            self.logger.info("🎉 ALL TESTS PASSED! MQTT system is functioning correctly.")
        else:
            self.logger.warning(f"⚠️  {total-passed} test(s) failed. Check boat system and MQTT configuration.")
        
        # Print response statistics
        if self.responses:
            self.logger.info("\nResponse Statistics:")
            for topic, data in self.responses.items():
                if isinstance(data, dict):
                    self.logger.info(f"  {topic}: {len(data)} messages")
                else:
                    self.logger.info(f"  {topic}: data received")
    
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            self.connected = True
            self.logger.info("Test client connected to MQTT broker")
        else:
            self.logger.error(f"Test client connection failed: {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        self.connected = False
        if rc != 0:
            self.logger.warning(f"Test client disconnected unexpectedly: {rc}")
    
    def _on_message(self, client, userdata, msg):
        """MQTT message received callback"""
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode('utf-8'))
            
            # Categorize message by topic
            for topic_key, topic_path in self.topics.items():
                if topic_path == topic:
                    if topic_key not in self.responses:
                        self.responses[topic_key] = {}
                    
                    if topic_key == 'ack':
                        # Store ACKs by command_id
                        command_id = payload.get('command_id')
                        if command_id:
                            self.responses[topic_key][command_id] = payload
                    else:
                        # Store latest message for other topics
                        self.responses[topic_key] = payload
                    
                    self.logger.debug(f"Received {topic_key} message")
                    break
                    
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to decode message: {e}")
        except Exception as e:
            self.logger.error(f"Message processing error: {e}")
    
    def _setup_logging(self) -> logging.Logger:
        """Setup test logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)


def main():
    """Main test entry point"""
    parser = argparse.ArgumentParser(description='PiBoat2 MQTT System Tester')
    parser.add_argument('-c', '--config', type=str,
                       help='Configuration file path')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--individual', action='store_true',
                       help='Run individual tests interactively')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    tester = MQTTSystemTester(config_file=args.config)
    
    try:
        if args.individual:
            print("Individual test mode not implemented yet")
            sys.exit(1)
        else:
            success = tester.run_all_tests()
            sys.exit(0 if success else 1)
            
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        tester.disconnect()
        sys.exit(1)
    except Exception as e:
        print(f"Test error: {e}")
        tester.disconnect()
        sys.exit(1)


if __name__ == "__main__":
    main()