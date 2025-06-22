#!/usr/bin/env python3
"""
Test script for the BMM150 compass sensor.
This script displays comprehensive compass data including heading,
raw magnetometer values, and connection status.
"""

import time
import signal
import sys
import logging
import math
from pathlib import Path

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from boat.hardware.compass_handler import CompassHandler

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("CompassTest")

class CompassTest:
    def __init__(self, clear_screen=False, verbose=False, calibration_mode=False):
        self.compass = None
        self.running = True
        self.clear_screen = clear_screen
        self.verbose = verbose
        self.calibration_mode = calibration_mode
        self.last_data = None
        self.calibration_data = []  # Store readings for calibration
        
        # Set up signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info("Received shutdown signal. Stopping compass test...")
        self.running = False
        if self.compass:
            self.compass.stop()
        sys.exit(0)
    
    def safe_float_format(self, value, decimal_places=1, default="N/A"):
        """Safely format a value as a float with specified decimal places."""
        if value is None:
            return default
        try:
            return f"{float(value):.{decimal_places}f}"
        except (ValueError, TypeError):
            return default
    
    def safe_int_format(self, value, default="N/A"):
        """Safely format a value as an integer."""
        if value is None:
            return default
        try:
            return f"{int(value)}"
        except (ValueError, TypeError):
            return default
    
    def get_cardinal_direction(self, heading):
        """Convert heading to cardinal direction."""
        if heading is None:
            return "N/A"
        
        try:
            heading = float(heading)
            directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                         "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
            index = int((heading + 11.25) / 22.5) % 16
            return directions[index]
        except (ValueError, TypeError):
            return "N/A"
    
    def format_compass_data(self, data):
        """Format comprehensive compass data for display."""
        lines = []
        lines.append("=" * 70)
        lines.append("BMM150 COMPASS SENSOR DATA")
        lines.append("=" * 70)
        
        # Connection Status
        if data['connected']:
            lines.append("🟢 Compass Status: CONNECTED")
        else:
            lines.append("🔴 Compass Status: DISCONNECTED")
        
        # Motion Status
        motion_status = "STATIONARY" if data.get('stationary', False) else "IN MOTION"
        if data.get('stationary', False):
            lines.append(f"📍 Motion Status: {motion_status} (enhanced filtering)")
        else:
            lines.append(f"🏃 Motion Status: {motion_status} (responsive filtering)")
        
        # Heading Information
        lines.append("")
        lines.append("🧭 HEADING:")
        if data['heading'] is not None:
            heading_str = self.safe_float_format(data['heading'], 1)
            cardinal = self.get_cardinal_direction(data['heading'])
            lines.append(f"  Filtered Heading: {heading_str}° ({cardinal})")
            
            # Show raw vs filtered comparison
            if data.get('raw_heading') is not None:
                raw_str = self.safe_float_format(data['raw_heading'], 1)
                diff = abs(data['heading'] - data['raw_heading'])
                if diff > 180:
                    diff = 360 - diff
                lines.append(f"  Raw Heading: {raw_str}° (diff: {diff:.1f}°)")
            
            # Visual compass representation
            try:
                heading_val = float(data['heading'])
                compass_visual = self.create_compass_visual(heading_val)
                lines.append(f"  Direction: {compass_visual}")
            except (ValueError, TypeError):
                pass
        else:
            lines.append("  Heading: N/A")
        
        # Raw Magnetometer Data
        lines.append("")
        lines.append("🧲 MAGNETOMETER DATA:")
        lines.append(f"  X-axis: {self.safe_int_format(data['x'])} (filtered)")
        lines.append(f"  Y-axis: {self.safe_int_format(data['y'])} (filtered)")
        lines.append(f"  Z-axis: {self.safe_int_format(data['z'])} (filtered)")
        
        # Calculate magnitude
        if all(v is not None for v in [data['x'], data['y'], data['z']]):
            try:
                magnitude = math.sqrt(data['x']**2 + data['y']**2 + data['z']**2)
                lines.append(f"  Magnitude: {self.safe_float_format(magnitude, 1)}")
            except (ValueError, TypeError):
                pass
        
        # Filtering Information
        lines.append("")
        lines.append("📊 FILTERING STATUS:")
        if data.get('buffer_size') is not None:
            lines.append(f"  Buffer Fill: {data['buffer_size']}/{getattr(self.compass, 'filter_size', 10)} readings")
        
        # Calibration Information
        lines.append("")
        lines.append("⚙️  CALIBRATION:")
        if hasattr(self.compass, 'hard_iron_offset_x'):
            offset_x = self.safe_float_format(self.compass.hard_iron_offset_x, 1)
            offset_y = self.safe_float_format(self.compass.hard_iron_offset_y, 1)
            declination = self.safe_float_format(self.compass.declination, 1)
            lines.append(f"  Hard Iron Offset X: {offset_x}")
            lines.append(f"  Hard Iron Offset Y: {offset_y}")
            lines.append(f"  Magnetic Declination: {declination}°")
        
        # Calibration mode information
        if self.calibration_mode:
            lines.append("")
            lines.append("📊 CALIBRATION MODE:")
            lines.append(f"  Data Points Collected: {len(self.calibration_data)}")
            if len(self.calibration_data) > 10:
                # Calculate basic statistics for calibration
                x_values = [d['x'] for d in self.calibration_data if d['x'] is not None]
                y_values = [d['y'] for d in self.calibration_data if d['y'] is not None]
                
                if x_values and y_values:
                    x_min, x_max = min(x_values), max(x_values)
                    y_min, y_max = min(y_values), max(y_values)
                    x_center = (x_min + x_max) / 2
                    y_center = (y_min + y_max) / 2
                    
                    lines.append(f"  X Range: {x_min} to {x_max} (center: {x_center:.1f})")
                    lines.append(f"  Y Range: {y_min} to {y_max} (center: {y_center:.1f})")
                    lines.append("  💡 Rotate the compass in all directions for calibration")
        
        lines.append("=" * 70)
        return "\n".join(lines)
    
    def create_compass_visual(self, heading):
        """Create a simple visual representation of the compass direction."""
        try:
            heading = float(heading)
            # Simple arrow representation
            if 337.5 <= heading or heading < 22.5:
                return "↑ N"
            elif 22.5 <= heading < 67.5:
                return "↗ NE"
            elif 67.5 <= heading < 112.5:
                return "→ E"
            elif 112.5 <= heading < 157.5:
                return "↘ SE"
            elif 157.5 <= heading < 202.5:
                return "↓ S"
            elif 202.5 <= heading < 247.5:
                return "↙ SW"
            elif 247.5 <= heading < 292.5:
                return "← W"
            elif 292.5 <= heading < 337.5:
                return "↖ NW"
            else:
                return "?"
        except (ValueError, TypeError):
            return "?"
    
    def data_changed(self, current_data, last_data):
        """Check if compass data has meaningfully changed."""
        if last_data is None:
            return True
        
        # Check for connection status change
        if current_data['connected'] != last_data.get('connected'):
            return True
        
        # Check for motion status change
        if current_data.get('stationary', False) != last_data.get('stationary', False):
            return True
        
        # Use different thresholds based on motion state
        motion_threshold = 1.0 if not current_data.get('stationary', False) else 2.0
        
        # Check for significant heading change
        if current_data['heading'] is not None and last_data.get('heading') is not None:
            try:
                curr_heading = float(current_data['heading'])
                last_heading = float(last_data['heading'])
                
                # Handle wrap-around (e.g., 359° to 1°)
                diff = abs(curr_heading - last_heading)
                if diff > 180:
                    diff = 360 - diff
                
                if diff > motion_threshold:
                    return True
            except (ValueError, TypeError):
                pass
        
        # Check for significant raw data changes (reduced threshold for motion)
        raw_threshold = 25 if not current_data.get('stationary', False) else 50
        for axis in ['x', 'y', 'z']:
            if (current_data[axis] is not None and last_data.get(axis) is not None):
                try:
                    curr_val = int(current_data[axis])
                    last_val = int(last_data[axis])
                    if abs(curr_val - last_val) > raw_threshold:
                        return True
                except (ValueError, TypeError):
                    pass
        
        return False
    
    def calculate_calibration(self):
        """Calculate hard iron calibration from collected data."""
        if len(self.calibration_data) < 20:
            logger.warning("Need at least 20 data points for calibration")
            return None, None
        
        x_values = [d['x'] for d in self.calibration_data if d['x'] is not None]
        y_values = [d['y'] for d in self.calibration_data if d['y'] is not None]
        
        if not x_values or not y_values:
            logger.warning("No valid data for calibration")
            return None, None
        
        # Simple hard iron calibration - find center point
        x_min, x_max = min(x_values), max(x_values)
        y_min, y_max = min(y_values), max(y_values)
        
        offset_x = (x_min + x_max) / 2
        offset_y = (y_min + y_max) / 2
        
        logger.info(f"Calculated calibration offsets: X={offset_x:.1f}, Y={offset_y:.1f}")
        return offset_x, offset_y
    
    def test_compass(self, bus_num=1):
        """Test compass with default behavior."""
        logger.info(f"Testing BMM150 compass on I2C bus {bus_num}")
        
        try:
            # Use default CompassHandler settings
            self.compass = CompassHandler(bus_num=bus_num)
            
            if not self.compass.start():
                logger.error("Failed to start compass. Check I2C connection and sensor.")
                return False
            
            logger.info("Compass started successfully. Waiting for data...")
            logger.info("Press Ctrl+C to stop the test.")
            
            if not self.verbose:
                logger.info("📊 Compass data will only be shown when there are meaningful changes")
                logger.info("💡 Use --verbose to see continuous updates")
            
            if self.calibration_mode:
                logger.info("🔧 Calibration mode enabled - rotate compass slowly in all directions")
                logger.info("   Press Ctrl+C when done to calculate calibration values")
            
            no_data_count = 0
            max_no_data = 10  # 10 seconds without data before showing warning
            last_log_time = time.time()
            data_shown = False
            stability_readings = []  # Track stability over time
            
            while self.running:
                data = self.compass.get_compass_data()
                
                # Track stability for stationary compass
                if data.get('stationary', False) and data['heading'] is not None:
                    stability_readings.append(data['heading'])
                    if len(stability_readings) > 30:  # Keep last 30 readings
                        stability_readings.pop(0)
                        
                        # Calculate stability statistics
                        if len(stability_readings) >= 10:
                            # Calculate circular standard deviation
                            angles_rad = [math.radians(h) for h in stability_readings]
                            mean_sin = sum(math.sin(a) for a in angles_rad) / len(angles_rad)
                            mean_cos = sum(math.cos(a) for a in angles_rad) / len(angles_rad)
                            
                            # Circular variance
                            R = math.sqrt(mean_sin**2 + mean_cos**2)
                            # Clamp R to valid range [0, 1] to prevent domain errors
                            R = max(0.0, min(1.0, R))
                            circular_var = 1 - R
                            
                            # Calculate circular standard deviation safely
                            if R > 0.001:  # Avoid log(0) and very small values
                                try:
                                    log_R = math.log(R)
                                    if log_R <= 0:  # Ensure -2 * log(R) >= 0 for sqrt
                                        circular_std = math.sqrt(-2 * log_R)
                                    else:
                                        circular_std = 0  # R > 1 case (shouldn't happen after clamping)
                                except (ValueError, OverflowError):
                                    circular_std = 0
                            else:
                                circular_std = math.pi  # Maximum circular standard deviation
                            
                            circular_std_deg = math.degrees(circular_std)
                            
                            # Log stability info periodically
                            current_time = time.time()
                            if current_time - last_log_time > 60:  # Every minute
                                logger.info(f"📐 Stability (last 30 readings): ±{circular_std_deg:.1f}° std deviation")
                                last_log_time = current_time
                
                # Store data for calibration if in calibration mode
                if self.calibration_mode and data['connected'] and data['x'] is not None:
                    self.calibration_data.append({
                        'x': data['x'],
                        'y': data['y'],
                        'z': data['z'],
                        'heading': data['heading']
                    })
                
                # Check if we should display this data
                should_show = False
                
                if self.verbose:
                    should_show = True
                elif self.data_changed(data, self.last_data):
                    should_show = True
                    logger.info("🧭 Compass data changed - showing update:")
                elif not data_shown:
                    should_show = True  # Show initial data
                    data_shown = True
                
                # Display data if needed
                if should_show:
                    if self.clear_screen and self.verbose:
                        print("\033[2J\033[H")  # Clear screen only in verbose mode
                    
                    print(self.format_compass_data(data))
                    
                    if not self.clear_screen:
                        print()  # Add blank line
                
                # Check status and log warnings
                current_time = time.time()
                if not data['connected']:
                    if current_time - last_log_time > 10:
                        logger.warning("⚠️  Compass not connected!")
                        last_log_time = current_time
                elif data['heading'] is None:
                    no_data_count += 1
                    if no_data_count >= max_no_data and current_time - last_log_time > 30:
                        logger.warning(f"⚠️  No compass data for {no_data_count} seconds. Check sensor connection.")
                        last_log_time = current_time
                else:
                    if no_data_count > 0:
                        logger.info(f"✅ Compass data received after {no_data_count} seconds")
                    no_data_count = 0  # Reset counter when we get data
                    
                    # Log periodically when we have data
                    if current_time - last_log_time > 30:
                        heading_str = self.safe_float_format(data['heading'], 1)
                        cardinal = self.get_cardinal_direction(data['heading'])
                        motion_status = "stationary" if data.get('stationary', False) else "moving"
                        logger.info(f"🧭 Compass active: Heading {heading_str}° ({cardinal}) - {motion_status}")
                        last_log_time = current_time
                
                # Store current data for comparison
                self.last_data = data.copy()
                
                time.sleep(0.5 if self.verbose else 1.0)
                
        except KeyboardInterrupt:
            logger.info("Test interrupted by user")
            
            # Show final stability report
            if len(stability_readings) >= 10:
                angles_rad = [math.radians(h) for h in stability_readings]
                mean_sin = sum(math.sin(a) for a in angles_rad) / len(angles_rad)
                mean_cos = sum(math.cos(a) for a in angles_rad) / len(angles_rad)
                R = math.sqrt(mean_sin**2 + mean_cos**2)
                # Clamp R to valid range [0, 1] to prevent domain errors
                R = max(0.0, min(1.0, R))
                
                # Calculate circular standard deviation safely
                if R > 0.001:  # Avoid log(0) and very small values
                    try:
                        log_R = math.log(R)
                        if log_R <= 0:  # Ensure -2 * log(R) >= 0 for sqrt
                            circular_std = math.sqrt(-2 * log_R)
                        else:
                            circular_std = 0  # R > 1 case (shouldn't happen after clamping)
                    except (ValueError, OverflowError):
                        circular_std = 0
                else:
                    circular_std = math.pi  # Maximum circular standard deviation
                
                circular_std_deg = math.degrees(circular_std)
                
                print("\n" + "="*50)
                print("STABILITY REPORT")
                print("="*50)
                print(f"Readings analyzed: {len(stability_readings)}")
                print(f"Standard deviation: ±{circular_std_deg:.1f}°")
                if circular_std_deg < 2:
                    print("✅ Excellent stability!")
                elif circular_std_deg < 5:
                    print("✅ Good stability")
                else:
                    print("⚠️  Consider calibration for better stability")
                print("="*50)
            
            # If in calibration mode, calculate and display calibration
            if self.calibration_mode and len(self.calibration_data) > 0:
                logger.info("Calculating calibration from collected data...")
                offset_x, offset_y = self.calculate_calibration()
                
                if offset_x is not None and offset_y is not None:
                    print("\n" + "="*50)
                    print("CALIBRATION RESULTS")
                    print("="*50)
                    print(f"Hard Iron Offset X: {offset_x:.1f}")
                    print(f"Hard Iron Offset Y: {offset_y:.1f}")
                    print("\nTo apply these calibration values, use:")
                    print(f"compass.set_calibration(offset_x={offset_x:.1f}, offset_y={offset_y:.1f})")
                    print("="*50)
                    
                    # Ask if user wants to apply calibration
                    try:
                        response = input("\nApply calibration now? (y/n): ").lower().strip()
                        if response in ['y', 'yes']:
                            self.compass.set_calibration(offset_x=offset_x, offset_y=offset_y)
                            logger.info("Calibration applied!")
                    except EOFError:
                        pass
        
        except Exception as e:
            logger.error(f"Test failed: {str(e)}")
            return False
        finally:
            if self.compass:
                self.compass.stop()
        
        return True

def main():
    """Main test function."""
    print("BMM150 Compass Sensor Test")
    print("==========================")
    print()
    
    # Check for options
    clear_screen = "--clear" in sys.argv
    if clear_screen:
        sys.argv.remove("--clear")
    
    verbose = "--verbose" in sys.argv
    if verbose:
        sys.argv.remove("--verbose")
    
    calibration_mode = "--calibrate" in sys.argv
    if calibration_mode:
        sys.argv.remove("--calibrate")
    
    # Parse I2C bus number
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        try:
            bus_num = int(sys.argv[1])
            print(f"Using I2C bus: {bus_num}")
        except ValueError:
            print(f"Invalid bus number: {sys.argv[1]}")
            return
    else:
        bus_num = 1
        print("Using default I2C bus: 1")
        print("\nUsage: python test_compass.py [bus_num] [options]")
        print("Example: python test_compass.py 1 --verbose")
        print("Options:")
        print("  --clear     Clear screen between updates (use with --verbose)")
        print("  --verbose   Show continuous compass updates (default: only changes)")
        print("  --calibrate Calibration mode - collect data and calculate offsets")
    
    print("\nUsing default compass settings (same as CompassHandler() in your code)")
    print()
    
    test = CompassTest(clear_screen=clear_screen, verbose=verbose, calibration_mode=calibration_mode)
    success = test.test_compass(bus_num=bus_num)
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main() 