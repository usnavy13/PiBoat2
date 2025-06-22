#!/usr/bin/env python3
"""
Standalone Boat Component Tester
Test individual boat components without MQTT server
"""

import os
import sys
import time
import logging
import argparse
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from boat.hardware.motor_controller import MotorController
from boat.hardware.gps_handler import GPSHandler
from boat.navigation.navigation_controller import NavigationController
from boat.navigation.safety_monitor import SafetyMonitor
from boat.config.mqtt_config import ConfigManager


class BoatComponentTester:
    """Test boat components independently"""
    
    def __init__(self, config_file=None):
        self.logger = self._setup_logging()
        
        # Try to load config, use defaults if failed
        try:
            self.config_manager = ConfigManager(config_file)
            self.config = self.config_manager.load_config()
        except Exception as e:
            self.logger.warning(f"Config load failed, using defaults: {e}")
            self.config = None
        
        # Components
        self.motor_controller = None
        self.gps_handler = None
        self.navigation_controller = None
        self.safety_monitor = None
    
    def test_gps_component(self) -> bool:
        """Test GPS handler standalone"""
        self.logger.info("🛰️  Testing GPS Component")
        self.logger.info("-" * 40)
        
        try:
            # Get GPS device from config or use default
            if self.config:
                gps_device = self.config.hardware.get('gps_device', '/dev/ttyUSB0')
                gps_baudrate = self.config.hardware.get('gps_baudrate', 9600)
            else:
                gps_device = '/dev/ttyUSB0'
                gps_baudrate = 9600
            
            self.logger.info(f"Initializing GPS: {gps_device} @ {gps_baudrate}")
            
            self.gps_handler = GPSHandler(port=gps_device, baudrate=gps_baudrate)
            
            self.gps_handler.start()
            # Wait a moment for GPS to start
            time.sleep(1)
            
            self.logger.info("✅ GPS initialized successfully")
            
            # Test GPS data reading
            self.logger.info("Reading GPS data for 30 seconds...")
            start_time = time.time()
            readings = 0
            
            while (time.time() - start_time) < 30:
                try:
                    gps_data = self.gps_handler.get_gps_data()
                    
                    if gps_data:
                        readings += 1
                        lat = gps_data.get('latitude', 'N/A')
                        lon = gps_data.get('longitude', 'N/A')
                        sats = gps_data.get('satellites', 'N/A')
                        fix = gps_data.get('fix_quality', 'N/A')
                        
                        print(f"\r📍 Lat: {lat}, Lon: {lon}, Sats: {sats}, Fix: {fix} ({readings} readings)", end='')
                    else:
                        print("\r📍 No GPS data available", end='')
                    
                    time.sleep(1)
                    
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    self.logger.error(f"GPS read error: {e}")
            
            print()  # New line
            
            if readings > 0:
                self.logger.info(f"✅ GPS test completed - {readings} readings in 30s")
                return True
            else:
                self.logger.warning("⚠️  No GPS readings obtained")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ GPS test failed: {e}")
            return False
        finally:
            if self.gps_handler:
                self.gps_handler.stop()
    
    def test_motor_component(self) -> bool:
        """Test motor controller standalone"""
        self.logger.info("🚤 Testing Motor Controller Component")
        self.logger.info("-" * 40)
        
        try:
            # Get motor device from config or use default
            if self.config:
                motor_device = self.config.hardware.get('motor_controller_device', '/dev/ttyUSB1')
            else:
                motor_device = '/dev/ttyUSB1'
            
            self.logger.info(f"Initializing Motor Controller: {motor_device}")
            
            self.motor_controller = MotorController()
            
            if not self.motor_controller.initialize():
                self.logger.error("❌ Motor controller initialization failed")
                return False
            
            self.logger.info("✅ Motor controller initialized successfully")
            
            # Test motor status
            self.logger.info("Reading motor status...")
            status = self.motor_controller.get_motor_status()
            
            if status:
                self.logger.info("📊 Motor Status:")
                for key, value in status.items():
                    self.logger.info(f"   {key}: {value}")
            else:
                self.logger.warning("⚠️  No motor status available")
            
            # Test safe motor movements (low values)
            self.logger.info("Testing safe motor movements...")
            
            # Small rudder test
            self.logger.info("Testing rudder: -10° → 0° → +10° → 0°")
            
            movements = [
                ("Rudder -10°", lambda: self.motor_controller.set_rudder(-10)),
                ("Wait 2s", lambda: time.sleep(2)),
                ("Rudder 0°", lambda: self.motor_controller.set_rudder(0)),
                ("Wait 2s", lambda: time.sleep(2)),
                ("Rudder +10°", lambda: self.motor_controller.set_rudder(10)),
                ("Wait 2s", lambda: time.sleep(2)),
                ("Rudder 0°", lambda: self.motor_controller.set_rudder(0)),
            ]
            
            for description, action in movements:
                try:
                    self.logger.info(f"  {description}")
                    action()
                except Exception as e:
                    self.logger.error(f"❌ Motor test failed at '{description}': {e}")
                    return False
            
            # Test throttle (very low)
            self.logger.info("Testing throttle: 5% → 0%")
            try:
                self.motor_controller.set_throttle(5)  # Very low throttle
                time.sleep(2)
                self.motor_controller.set_throttle(0)
                self.logger.info("✅ Throttle test completed")
            except Exception as e:
                self.logger.error(f"❌ Throttle test failed: {e}")
                return False
            
            # Final safety stop
            self.logger.info("Final safety stop...")
            self.motor_controller.stop()
            
            self.logger.info("✅ Motor controller test completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Motor controller test failed: {e}")
            return False
        finally:
            if self.motor_controller:
                try:
                    self.motor_controller.stop()
                    self.motor_controller.cleanup()
                except:
                    pass
    
    def test_navigation_component(self) -> bool:
        """Test navigation controller (simulation mode)"""
        self.logger.info("🧭 Testing Navigation Controller (Simulation)")
        self.logger.info("-" * 40)
        
        try:
            # Create mock components for navigation testing
            from unittest.mock import Mock
            
            mock_motor = Mock()
            mock_motor.get_current_heading.return_value = 180.0  # Facing south
            mock_motor.set_throttle = Mock()
            mock_motor.set_rudder_angle = Mock()
            mock_motor.stop_all_motors = Mock()
            mock_motor.emergency_stop = Mock(return_value=True)
            
            mock_gps = Mock()
            mock_gps.get_position.return_value = {
                'latitude': 40.7128,
                'longitude': -74.0060,
                'accuracy': 3.0,
                'satellites': 8,
                'fix_quality': 1
            }
            
            self.logger.info("✅ Mock components created")
            
            # Create navigation controller
            self.navigation_controller = NavigationController(mock_motor, mock_gps)
            
            # Test waypoint navigation
            self.logger.info("Testing waypoint navigation...")
            result = self.navigation_controller.navigate_to_waypoint(
                latitude=40.7200,  # About 800m north
                longitude=-74.0060,
                max_speed=30,
                arrival_radius=10.0
            )
            
            if result:
                self.logger.info("✅ Waypoint navigation started")
                
                # Let it run for a few seconds
                time.sleep(3)
                
                # Get status
                status = self.navigation_controller.get_status()
                self.logger.info("📊 Navigation Status:")
                for key, value in status.items():
                    if isinstance(value, dict):
                        self.logger.info(f"   {key}:")
                        for subkey, subvalue in value.items():
                            self.logger.info(f"     {subkey}: {subvalue}")
                    else:
                        self.logger.info(f"   {key}: {value}")
                
                # Stop navigation
                self.navigation_controller.stop_current_navigation()
                self.logger.info("✅ Navigation stopped")
            else:
                self.logger.error("❌ Failed to start waypoint navigation")
                return False
            
            # Test course setting
            self.logger.info("Testing course setting...")
            result = self.navigation_controller.set_course(heading=90, speed=25, duration=5)
            
            if result:
                self.logger.info("✅ Course set successfully")
                time.sleep(2)
                self.navigation_controller.stop_current_navigation()
            else:
                self.logger.error("❌ Failed to set course")
                return False
            
            # Test position hold
            self.logger.info("Testing position hold...")
            result = self.navigation_controller.hold_position(max_drift=5.0)
            
            if result:
                self.logger.info("✅ Position hold engaged")
                time.sleep(2)
                self.navigation_controller.stop_current_navigation()
            else:
                self.logger.error("❌ Failed to engage position hold")
                return False
            
            self.logger.info("✅ Navigation controller test completed")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Navigation test failed: {e}")
            return False
    
    def test_safety_component(self) -> bool:
        """Test safety monitor (simulation mode)"""
        self.logger.info("🛡️  Testing Safety Monitor (Simulation)")
        self.logger.info("-" * 40)
        
        try:
            from unittest.mock import Mock
            
            # Create mock components
            mock_gps = Mock()
            mock_gps.get_position.return_value = {
                'latitude': 40.7128,
                'longitude': -74.0060,
                'accuracy': 3.0,
                'satellites': 8,
                'fix_quality': 1
            }
            
            mock_motor = Mock()
            mock_motor.get_status.return_value = {
                'throttle_percent': 0,
                'rudder_angle': 0,
                'motor_running': False,
                'battery_voltage': 12.5,
                'temperature': 25.0
            }
            mock_motor.emergency_stop = Mock(return_value=True)
            
            self.logger.info("✅ Mock components created")
            
            # Create safety monitor
            self.safety_monitor = SafetyMonitor(mock_gps, mock_motor)
            
            # Set start position
            if self.safety_monitor.set_start_position():
                self.logger.info("✅ Start position set")
            else:
                self.logger.warning("⚠️  Failed to set start position")
            
            # Test safety check
            self.logger.info("Testing immediate safety check...")
            safety_status = self.safety_monitor.check_immediate_safety()
            
            self.logger.info("📊 Safety Status:")
            self.logger.info(f"   Safe: {safety_status['safe']}")
            self.logger.info(f"   Violations: {len(safety_status['violations'])}")
            self.logger.info(f"   Warnings: {len(safety_status['warnings'])}")
            
            for violation in safety_status['violations']:
                self.logger.warning(f"   ❌ {violation['type']}: {violation['message']}")
            
            for warning in safety_status['warnings']:
                self.logger.info(f"   ⚠️  {warning['type']}: {warning['message']}")
            
            # Test safety limits update
            self.logger.info("Testing safety limits update...")
            self.safety_monitor.set_safety_limits({
                'max_speed_percent': 50,
                'max_rudder_angle': 30.0
            })
            self.logger.info("✅ Safety limits updated")
            
            # Test emergency stop
            self.logger.info("Testing emergency stop...")
            if self.safety_monitor.trigger_emergency_stop("Test emergency stop"):
                self.logger.info("✅ Emergency stop triggered successfully")
            else:
                self.logger.error("❌ Emergency stop failed")
                return False
            
            # Get safety status
            status = self.safety_monitor.get_status()
            self.logger.info("📊 Safety Monitor Status:")
            for key, value in status.items():
                if isinstance(value, dict):
                    self.logger.info(f"   {key}:")
                    for subkey, subvalue in value.items():
                        self.logger.info(f"     {subkey}: {subvalue}")
                else:
                    self.logger.info(f"   {key}: {value}")
            
            self.logger.info("✅ Safety monitor test completed")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Safety monitor test failed: {e}")
            return False
    
    def test_configuration(self) -> bool:
        """Test configuration management"""
        self.logger.info("⚙️  Testing Configuration Management")
        self.logger.info("-" * 40)
        
        try:
            if not self.config:
                self.logger.warning("⚠️  No configuration loaded, testing defaults...")
                
                # Test with default config
                config_manager = ConfigManager()
                config = config_manager.load_config()
                
                if config:
                    self.logger.info("✅ Default configuration loaded")
                    self.logger.info(f"   Boat ID: {config.boat_id}")
                    self.logger.info(f"   MQTT Broker: {config.mqtt.broker_host}:{config.mqtt.port}")
                else:
                    self.logger.error("❌ Failed to load default configuration")
                    return False
            else:
                self.logger.info("✅ Configuration loaded successfully")
                self.logger.info(f"   Boat ID: {self.config.boat_id}")
                self.logger.info(f"   MQTT Broker: {self.config.mqtt.broker_host}:{self.config.mqtt.port}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Configuration test failed: {e}")
            return False
    
    def run_all_tests(self) -> bool:
        """Run all component tests"""
        self.logger.info("🚀 Running All Boat Component Tests")
        self.logger.info("=" * 50)
        
        tests = [
            ("Configuration", self.test_configuration),
            ("GPS Component", self.test_gps_component),
            ("Motor Component", self.test_motor_component),
            ("Navigation Component", self.test_navigation_component),
            ("Safety Component", self.test_safety_component),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            self.logger.info(f"\n{'='*20} {test_name} {'='*20}")
            
            try:
                if test_func():
                    passed += 1
                    self.logger.info(f"✅ {test_name} PASSED")
                else:
                    self.logger.error(f"❌ {test_name} FAILED")
            except Exception as e:
                self.logger.error(f"❌ {test_name} FAILED with exception: {e}")
            
            self.logger.info(f"{'='*50}")
        
        # Summary
        self.logger.info(f"\n🏁 TEST SUMMARY")
        self.logger.info(f"Tests Passed: {passed}/{total}")
        self.logger.info(f"Success Rate: {(passed/total)*100:.1f}%")
        
        if passed == total:
            self.logger.info("🎉 ALL TESTS PASSED!")
        else:
            self.logger.warning(f"⚠️  {total-passed} test(s) failed")
        
        return passed == total
    
    def _setup_logging(self):
        """Setup logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='PiBoat2 Component Tester')
    parser.add_argument('-c', '--config', type=str,
                       help='Configuration file path')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('-t', '--test', choices=['gps', 'motor', 'nav', 'safety', 'config', 'all'],
                       default='all', help='Specific test to run')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    tester = BoatComponentTester(config_file=args.config)
    
    try:
        if args.test == 'all':
            success = tester.run_all_tests()
        elif args.test == 'gps':
            success = tester.test_gps_component()
        elif args.test == 'motor':
            success = tester.test_motor_component()
        elif args.test == 'nav':
            success = tester.test_navigation_component()
        elif args.test == 'safety':
            success = tester.test_safety_component()
        elif args.test == 'config':
            success = tester.test_configuration()
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Test error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()