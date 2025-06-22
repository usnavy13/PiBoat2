#!/usr/bin/env python3
"""
Test script for the MotorController class
Tests all functionality including rudder control, throttle control, and emergency procedures
"""

import time
import sys
import signal
import logging
from pathlib import Path

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from boat.hardware.motor_controller import MotorController

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("MotorControllerTest")

class MotorControllerTest:
    def __init__(self):
        self.motor_controller = MotorController()
        self.test_running = True
        
    def signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        logger.info("Received interrupt signal, shutting down...")
        self.test_running = False
        self.motor_controller.cleanup()
        sys.exit(0)
    
    def test_initialization(self):
        """Test motor controller initialization"""
        logger.info("=== Testing Initialization ===")
        
        success = self.motor_controller.initialize()
        if success:
            logger.info("✓ Motor controller initialized successfully")
            return True
        else:
            logger.error("✗ Motor controller initialization failed")
            return False
    
    def test_rudder_control(self):
        """Test rudder control across its range"""
        logger.info("\n=== Testing Rudder Control ===")
        
        # Get the current maximum rudder angle
        max_angle = self.motor_controller.get_max_rudder_angle()
        logger.info(f"Testing with maximum rudder angle limit: ±{max_angle}°")
        
        # Test center position
        logger.info("Testing center position (0°)")
        if not self.motor_controller.set_rudder(0):
            logger.error("✗ Failed to set rudder to center")
            return False
        time.sleep(2)
        
        # Test port positions
        logger.info("Testing port positions...")
        successful_tests = 0
        for angle in [-45, -90, -135]:
            logger.info(f"Setting rudder to {angle}°")
            if self.motor_controller.set_rudder(angle):
                logger.info(f"✓ Successfully set rudder to {angle}°")
                successful_tests += 1
                time.sleep(1.5)
            else:
                logger.info(f"ℹ Rudder angle {angle}° rejected (outside configured limit of ±{max_angle}°)")
        
        # Return to center
        logger.info("Returning to center...")
        self.motor_controller.set_rudder(0)
        time.sleep(2)
        
        # Test starboard positions
        logger.info("Testing starboard positions...")
        for angle in [45, 90, 135]:
            logger.info(f"Setting rudder to {angle}°")
            if self.motor_controller.set_rudder(angle):
                logger.info(f"✓ Successfully set rudder to {angle}°")
                successful_tests += 1
                time.sleep(1.5)
            else:
                logger.info(f"ℹ Rudder angle {angle}° rejected (outside configured limit of ±{max_angle}°)")
        
        # Return to center
        logger.info("Returning to center...")
        self.motor_controller.set_rudder(0)
        time.sleep(2)
        
        logger.info(f"✓ Rudder control tests completed - {successful_tests} angles tested successfully")
        return True
    
    def test_rudder_limits(self):
        """Test rudder limit checking"""
        logger.info("\n=== Testing Rudder Limits ===")
        
        # Get the current maximum rudder angle
        max_angle = self.motor_controller.get_max_rudder_angle()
        logger.info(f"Testing limits with maximum rudder angle: ±{max_angle}°")
        
        # Test angles that should always be rejected (beyond hardware limits)
        extreme_angles = [-200, -150, 150, 200]
        logger.info("Testing extreme angles (beyond hardware limits)...")
        for angle in extreme_angles:
            logger.info(f"Testing extreme angle: {angle}°")
            result = self.motor_controller.set_rudder(angle)
            if result:
                logger.error(f"✗ Should have rejected extreme angle {angle}°")
                return False
            else:
                logger.info(f"✓ Correctly rejected extreme angle {angle}°")
        
        # Test angles just beyond the configured limit
        if max_angle < 135:  # Only test if we have a more restrictive limit than hardware
            beyond_limit_angles = [-(max_angle + 1), max_angle + 1]
            logger.info(f"Testing angles just beyond configured limit (±{max_angle}°)...")
            for angle in beyond_limit_angles:
                logger.info(f"Testing angle beyond limit: {angle}°")
                result = self.motor_controller.set_rudder(angle)
                if result:
                    logger.error(f"✗ Should have rejected angle {angle}° (beyond configured limit)")
                    return False
                else:
                    logger.info(f"✓ Correctly rejected angle {angle}° (beyond configured limit)")
        
        # Test valid boundary angles (at the configured limit)
        boundary_angles = [-max_angle, max_angle]
        logger.info(f"Testing boundary angles (±{max_angle}°)...")
        for angle in boundary_angles:
            logger.info(f"Testing boundary angle: {angle}°")
            result = self.motor_controller.set_rudder(angle)
            if not result:
                logger.error(f"✗ Should have accepted boundary angle {angle}°")
                return False
            else:
                logger.info(f"✓ Correctly accepted boundary angle {angle}°")
            time.sleep(0.5)
        
        # Return to center
        self.motor_controller.set_rudder(0)
        time.sleep(1)
        
        logger.info("✓ Rudder limit tests passed")
        return True
    
    def test_throttle_control(self):
        """Test throttle control with ramping"""
        logger.info("\n=== Testing Throttle Control ===")
        
        # Start from neutral
        logger.info("Setting throttle to neutral (0%)")
        if not self.motor_controller.set_throttle(0):
            logger.error("✗ Failed to set throttle to neutral")
            return False
        time.sleep(2)
        
        # Test forward thrust
        logger.info("Testing forward thrust...")
        for thrust in [25, 50, 75]:
            logger.info(f"Setting thrust to {thrust}%")
            if not self.motor_controller.set_throttle(thrust, ramp_time=2.0):
                logger.error(f"✗ Failed to set thrust to {thrust}%")
                return False
            time.sleep(3)  # Wait for ramping to complete
        
        # Return to neutral
        logger.info("Returning to neutral...")
        self.motor_controller.set_throttle(0, ramp_time=2.0)
        time.sleep(3)
        
        # Test reverse thrust
        logger.info("Testing reverse thrust...")
        for thrust in [-25, -50, -75]:
            logger.info(f"Setting thrust to {thrust}%")
            if not self.motor_controller.set_throttle(thrust, ramp_time=2.0):
                logger.error(f"✗ Failed to set thrust to {thrust}%")
                return False
            time.sleep(3)  # Wait for ramping to complete
        
        # Return to neutral
        logger.info("Returning to neutral...")
        self.motor_controller.set_throttle(0, ramp_time=1.0)
        time.sleep(2)
        
        logger.info("✓ Throttle control tests completed successfully")
        return True
    
    def test_throttle_limits(self):
        """Test throttle limit checking"""
        logger.info("\n=== Testing Throttle Limits ===")
        
        # Test invalid thrust values
        invalid_thrusts = [-150, -101, 101, 150]
        for thrust in invalid_thrusts:
            logger.info(f"Testing invalid thrust: {thrust}%")
            result = self.motor_controller.set_throttle(thrust)
            if result:
                logger.error(f"✗ Should have rejected thrust {thrust}%")
                return False
            else:
                logger.info(f"✓ Correctly rejected thrust {thrust}%")
        
        logger.info("✓ Throttle limit tests passed")
        return True
    
    def test_combined_control(self):
        """Test simultaneous rudder and throttle control"""
        logger.info("\n=== Testing Combined Control ===")
        
        # Get max angle and use a safe test angle
        max_angle = self.motor_controller.get_max_rudder_angle()
        test_angle = min(45, max_angle * 0.8)  # Use 45° or 80% of max, whichever is smaller
        logger.info(f"Using test angle: ±{test_angle}° (max configured: ±{max_angle}°)")
        
        # Set rudder to starboard and forward thrust
        logger.info(f"Setting rudder to {test_angle}° starboard and 30% forward thrust")
        if not self.motor_controller.set_rudder(test_angle):
            logger.warning(f"Could not set rudder to {test_angle}°, using center position")
            self.motor_controller.set_rudder(0)
        time.sleep(1)
        self.motor_controller.set_throttle(30, ramp_time=2.0)
        time.sleep(3)
        
        # Set rudder to port and continue forward
        logger.info(f"Setting rudder to {-test_angle}° port, maintaining thrust")
        if not self.motor_controller.set_rudder(-test_angle):
            logger.warning(f"Could not set rudder to {-test_angle}°, using center position")
            self.motor_controller.set_rudder(0)
        time.sleep(2)
        
        # Stop and center
        logger.info("Stopping and centering...")
        self.motor_controller.set_throttle(0, ramp_time=1.5)
        self.motor_controller.set_rudder(0)
        time.sleep(2)
        
        logger.info("✓ Combined control tests completed successfully")
        return True
    
    def test_status_reporting(self):
        """Test status reporting functionality"""
        logger.info("\n=== Testing Status Reporting ===")
        
        # Get max angle and use a safe test angle
        max_angle = self.motor_controller.get_max_rudder_angle()
        test_angle = min(30, max_angle * 0.6)  # Use 30° or 60% of max, whichever is smaller
        
        # Set some known values
        logger.info(f"Setting rudder to {test_angle}° for status test")
        if not self.motor_controller.set_rudder(test_angle):
            logger.warning(f"Could not set rudder to {test_angle}°, using 0°")
            test_angle = 0
            self.motor_controller.set_rudder(0)
        
        self.motor_controller.set_throttle(50, ramp_time=1.0)
        time.sleep(2)
        
        # Get status
        status = self.motor_controller.get_motor_status()
        logger.info(f"Current status: {status}")
        
        # Verify status values
        if status['initialized'] != True:
            logger.error("✗ Status shows not initialized")
            return False
        
        if abs(status['rudder_position'] - test_angle) > 0.1:
            logger.error(f"✗ Rudder position mismatch: expected {test_angle}, got {status['rudder_position']}")
            return False
        
        # Verify max_rudder_angle is reported in status
        if 'max_rudder_angle' not in status:
            logger.error("✗ Status missing max_rudder_angle field")
            return False
        
        if status['max_rudder_angle'] != max_angle:
            logger.error(f"✗ Max rudder angle mismatch: expected {max_angle}, got {status['max_rudder_angle']}")
            return False
        
        # Note: throttle might still be ramping, so we check if it's moving toward 50
        logger.info(f"✓ Status reporting working - Rudder: {status['rudder_position']}°, Throttle: {status['throttle']}%, Max Angle: ±{status['max_rudder_angle']}°")
        
        # Return to neutral
        self.motor_controller.set_throttle(0)
        self.motor_controller.set_rudder(0)
        time.sleep(2)
        
        return True
    
    def test_emergency_stop(self):
        """Test emergency stop functionality"""
        logger.info("\n=== Testing Emergency Stop ===")
        
        # Get max angle and use a safe test angle
        max_angle = self.motor_controller.get_max_rudder_angle()
        test_angle = min(90, max_angle)  # Use 90° or max, whichever is smaller
        
        # Set some motion
        logger.info("Setting up motion for emergency stop test...")
        if not self.motor_controller.set_rudder(test_angle):
            logger.info(f"Could not set rudder to {test_angle}°, using center position for test")
            self.motor_controller.set_rudder(0)
        self.motor_controller.set_throttle(60, ramp_time=3.0)
        time.sleep(1)  # Let it start ramping
        
        # Emergency stop
        logger.info("Executing emergency stop...")
        success = self.motor_controller.stop()
        if not success:
            logger.error("✗ Emergency stop failed")
            return False
        
        time.sleep(2)
        
        # Check status
        status = self.motor_controller.get_motor_status()
        logger.info(f"Status after emergency stop: {status}")
        
        # Reset rudder to center
        self.motor_controller.set_rudder(0)
        time.sleep(1)
        
        logger.info("✓ Emergency stop test completed")
        return True
    
    def interactive_test(self):
        """Interactive test mode for manual control"""
        logger.info("\n=== Interactive Test Mode ===")
        max_angle = self.motor_controller.get_max_rudder_angle()
        logger.info("Commands:")
        logger.info(f"  r <angle>  - Set rudder angle (-{max_angle} to {max_angle}) [configured limit]")
        logger.info("  t <thrust> - Set thrust (-100 to 100)")
        logger.info("  s          - Status")
        logger.info("  stop       - Emergency stop")
        logger.info("  quit       - Exit interactive mode")
        
        while self.test_running:
            try:
                command = input("\nEnter command: ").strip().split()
                if not command:
                    continue
                
                cmd = command[0].lower()
                
                if cmd == 'quit':
                    break
                elif cmd == 'r' and len(command) > 1:
                    try:
                        angle = float(command[1])
                        self.motor_controller.set_rudder(angle)
                    except ValueError:
                        logger.error("Invalid angle value")
                elif cmd == 't' and len(command) > 1:
                    try:
                        thrust = float(command[1])
                        self.motor_controller.set_throttle(thrust)
                    except ValueError:
                        logger.error("Invalid thrust value")
                elif cmd == 's':
                    status = self.motor_controller.get_motor_status()
                    logger.info(f"Status: {status}")
                elif cmd == 'stop':
                    self.motor_controller.stop()
                else:
                    logger.info("Unknown command")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error in interactive mode: {e}")
    
    def run_all_tests(self):
        """Run all automated tests"""
        logger.info("Starting Motor Controller Tests")
        logger.info("=" * 50)
        
        # Setup signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        
        try:
            # Test initialization
            if not self.test_initialization():
                logger.error("Initialization failed, stopping tests")
                return False
            
            # Run all tests
            tests = [
                self.test_rudder_limits,
                self.test_throttle_limits,
                self.test_rudder_control,
                self.test_throttle_control,
                self.test_combined_control,
                self.test_status_reporting,
                self.test_emergency_stop
            ]
            
            for test in tests:
                if not self.test_running:
                    break
                if not test():
                    logger.error(f"Test {test.__name__} failed")
                    return False
            
            logger.info("\n" + "=" * 50)
            logger.info("✓ All automated tests passed successfully!")
            
            # Ask if user wants interactive mode
            try:
                response = input("\nDo you want to run interactive test mode? (y/n): ").strip().lower()
                if response in ['y', 'yes']:
                    self.interactive_test()
            except KeyboardInterrupt:
                pass
                
        except Exception as e:
            logger.error(f"Test execution error: {e}")
            return False
        finally:
            # Cleanup
            logger.info("\nCleaning up...")
            self.motor_controller.cleanup()
            logger.info("Tests completed")
        
        return True

def main():
    """Main test function"""
    print("Motor Controller Test Suite")
    print("This test requires actual Raspberry Pi hardware with PWM channels")
    print("Make sure your hardware is connected before proceeding")
    
    try:
        response = input("\nContinue with tests? (y/n): ").strip().lower()
        if response not in ['y', 'yes']:
            print("Tests cancelled")
            return
    except KeyboardInterrupt:
        print("\nTests cancelled")
        return
    
    test_suite = MotorControllerTest()
    test_suite.run_all_tests()

if __name__ == "__main__":
    main() 