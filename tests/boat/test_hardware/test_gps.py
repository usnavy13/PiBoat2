#!/usr/bin/env python3
"""
Enhanced test script for the u-blox 7 GPS receiver.
This script displays comprehensive GPS data including satellite information,
accuracy estimates, and all available positioning data.
"""

import time
import signal
import sys
import logging
import json
from pathlib import Path

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from boat.hardware.gps_handler import GPSHandler

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("GPSTest")

class EnhancedGPSTest:
    def __init__(self, clear_screen=False, verbose=False, detailed=False):
        self.gps = None
        self.running = True
        self.clear_screen = clear_screen
        self.verbose = verbose
        self.detailed = detailed  # Show detailed satellite and accuracy info
        self.last_data = None
        
        # Set up signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info("Received shutdown signal. Stopping GPS test...")
        self.running = False
        if self.gps:
            self.gps.stop()
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
    
    def format_gps_data(self, data):
        """Format comprehensive GPS data for display."""
        lines = []
        lines.append("=" * 80)
        lines.append("u-blox 7 GPS/GNSS RECEIVER DATA")
        lines.append("=" * 80)
        
        # Fix Status
        if data['has_fix']:
            fix_type = "3D" if data.get('is_3d_fix') else "2D" if data.get('fix_mode') == 2 else "Fix"
            differential = " (DGPS)" if data.get('is_differential') else ""
            lines.append(f"🟢 GPS Fix: {fix_type}{differential} (Quality: {data['fix_quality']})")
        else:
            lines.append(f"🔴 GPS Fix: NO FIX")
        
        lines.append(f"Running: {'YES' if data['running'] else 'NO'}")
        lines.append(f"Navigation Status: {data.get('navigation_status', 'N/A')}")
        lines.append(f"Selection Mode: {data.get('selection_mode', 'N/A')}")
        
        # Time and Date
        lines.append("")
        lines.append("📅 TIME & DATE:")
        lines.append(f"  UTC Time: {data['timestamp'] or 'N/A'}")
        lines.append(f"  UTC Date: {data.get('utc_date', 'N/A')}")
        if data.get('local_zone_offset') is not None:
            offset_str = self.safe_float_format(data['local_zone_offset'], 0)
            lines.append(f"  Local Zone Offset: {offset_str} hours")
        
        # Position Data
        lines.append("")
        lines.append("🌍 POSITION:")
        if data['latitude'] is not None and data['longitude'] is not None:
            lat_str = self.safe_float_format(data['latitude'], 8)
            lon_str = self.safe_float_format(data['longitude'], 8)
            lines.append(f"  Latitude:  {lat_str}°")
            lines.append(f"  Longitude: {lon_str}°")
        else:
            lines.append("  Position: N/A")
        
        if data['altitude'] is not None:
            alt_str = self.safe_float_format(data['altitude'], 1)
            lines.append(f"  Altitude (MSL): {alt_str} m")
        if data.get('geoid_height') is not None:
            geoid_str = self.safe_float_format(data['geoid_height'], 1)
            lines.append(f"  Geoid Height: {geoid_str} m")
        
        # Speed and Course
        lines.append("")
        lines.append("🧭 MOTION:")
        if data['speed_knots'] is not None:
            speed_knots = self.safe_float_format(data['speed_knots'], 1)
            if speed_knots != "N/A":
                try:
                    knots_val = float(data['speed_knots'])
                    speed_kmh = data.get('speed_kmh') or (knots_val * 1.852)
                    speed_mph = knots_val * 1.151
                    kmh_str = self.safe_float_format(speed_kmh, 1)
                    mph_str = self.safe_float_format(speed_mph, 1)
                    lines.append(f"  Speed: {speed_knots} knots ({kmh_str} km/h, {mph_str} mph)")
                except (ValueError, TypeError):
                    lines.append(f"  Speed: {speed_knots} knots")
            else:
                lines.append("  Speed: N/A")
        else:
            lines.append("  Speed: N/A")
        
        if data['course'] is not None:
            course_str = self.safe_float_format(data['course'], 1)
            lines.append(f"  Course (True): {course_str}°")
        
        if data.get('magnetic_variation') is not None:
            variation_str = self.safe_float_format(data['magnetic_variation'], 1)
            direction = data.get('variation_direction', '')
            lines.append(f"  Magnetic Variation: {variation_str}° {direction}")
        
        # Satellite Information
        lines.append("")
        lines.append("🛰️  SATELLITES:")
        lines.append(f"  Satellites Used: {len(data.get('satellites_used', []))}")
        lines.append(f"  Satellites in View: {len(data.get('satellites_in_view', []))}")
        if data.get('satellites') is not None:
            sat_count = self.safe_int_format(data['satellites'])
            lines.append(f"  Satellites (GGA): {sat_count}")
        
        # Get satellite summary
        if hasattr(self.gps, 'get_satellite_summary'):
            try:
                sat_summary = self.gps.get_satellite_summary()
                if sat_summary['satellites_with_snr'] > 0:
                    avg_snr = self.safe_float_format(sat_summary['average_snr'], 1)
                    lines.append(f"  Average SNR: {avg_snr} dB")
                    if sat_summary['strongest_satellite']:
                        strongest = sat_summary['strongest_satellite']
                        lines.append(f"  Strongest: PRN {strongest['prn']} ({strongest['snr']} dB)")
            except Exception as e:
                logger.debug(f"Error getting satellite summary: {e}")
        
        # Dilution of Precision
        lines.append("")
        lines.append("📊 DILUTION OF PRECISION (DOP):")
        if data.get('pdop') is not None:
            pdop_str = self.safe_float_format(data['pdop'], 2)
            lines.append(f"  PDOP (Position): {pdop_str}")
        if data.get('hdop') is not None:
            hdop_str = self.safe_float_format(data['hdop'], 2)
            lines.append(f"  HDOP (Horizontal): {hdop_str}")
        if data.get('vdop') is not None:
            vdop_str = self.safe_float_format(data['vdop'], 2)
            lines.append(f"  VDOP (Vertical): {vdop_str}")
        
        # Accuracy Estimates
        lines.append("")
        lines.append("🎯 ACCURACY ESTIMATES:")
        
        # Get accuracy summary
        if hasattr(self.gps, 'get_accuracy_summary'):
            try:
                accuracy = self.gps.get_accuracy_summary()
                if accuracy['horizontal_accuracy'] is not None:
                    est_type = "Error-based" if accuracy['has_error_estimates'] else "DOP-based"
                    hacc_str = self.safe_float_format(accuracy['horizontal_accuracy'], 1)
                    lines.append(f"  Horizontal: ~{hacc_str} m ({est_type})")
                if accuracy['vertical_accuracy'] is not None:
                    vacc_str = self.safe_float_format(accuracy['vertical_accuracy'], 1)
                    lines.append(f"  Vertical: ~{vacc_str} m")
                if accuracy['position_accuracy'] is not None:
                    pacc_str = self.safe_float_format(accuracy['position_accuracy'], 1)
                    lines.append(f"  Overall Position: ~{pacc_str} m")
            except Exception as e:
                logger.debug(f"Error getting accuracy summary: {e}")
        
        # Error estimates (if available)
        if (data.get('lat_error') is not None or data.get('lon_error') is not None or 
            data.get('alt_error') is not None):
            lines.append("")
            lines.append("📏 ERROR ESTIMATES:")
            if data.get('lat_error') is not None:
                lat_err = self.safe_float_format(data['lat_error'], 2)
                lines.append(f"  Latitude Error: ±{lat_err} m")
            if data.get('lon_error') is not None:
                lon_err = self.safe_float_format(data['lon_error'], 2)
                lines.append(f"  Longitude Error: ±{lon_err} m")
            if data.get('alt_error') is not None:
                alt_err = self.safe_float_format(data['alt_error'], 2)
                lines.append(f"  Altitude Error: ±{alt_err} m")
        
        # Differential GPS Info
        if data.get('dgps_age') is not None or data.get('dgps_station_id') is not None:
            lines.append("")
            lines.append("📡 DIFFERENTIAL GPS:")
            if data.get('dgps_age') is not None:
                age_str = self.safe_float_format(data['dgps_age'], 1)
                lines.append(f"  Data Age: {age_str} seconds")
            if data.get('dgps_station_id') is not None:
                lines.append(f"  Station ID: {data['dgps_station_id']}")
        
        # Detailed Information (if requested)
        if self.detailed:
            # Satellite Details
            if data.get('satellites_in_view'):
                lines.append("")
                lines.append("🛰️  SATELLITE DETAILS:")
                lines.append("  PRN  Elev  Azim   SNR  Used")
                lines.append("  --- ----- ----- ----- ----")
                
                used_prns = set(data.get('satellites_used', []))
                for sat in sorted(data['satellites_in_view'], key=lambda x: x['prn']):
                    prn = sat['prn']
                    elevation = f"{sat['elevation']:3d}°" if sat['elevation'] is not None else "  -"
                    azimuth = f"{sat['azimuth']:3d}°" if sat['azimuth'] is not None else "  -"
                    snr = f"{sat['snr']:2d}dB" if sat['snr'] is not None else " - "
                    used = " ✓ " if prn in used_prns else "   "
                    lines.append(f"  {prn:3d}  {elevation}  {azimuth}  {snr}  {used}")
            
            # Position Error Ellipse
            if data.get('position_error_ellipse'):
                ellipse = data['position_error_ellipse']
                lines.append("")
                lines.append("🎯 POSITION ERROR ELLIPSE:")
                if ellipse.get('semi_major_std'):
                    major_str = self.safe_float_format(ellipse['semi_major_std'], 2)
                    lines.append(f"  Semi-major axis std: {major_str} m")
                if ellipse.get('semi_minor_std'):
                    minor_str = self.safe_float_format(ellipse['semi_minor_std'], 2)
                    lines.append(f"  Semi-minor axis std: {minor_str} m")
                if ellipse.get('orientation'):
                    orient_str = self.safe_float_format(ellipse['orientation'], 1)
                    lines.append(f"  Orientation: {orient_str}°")
            
            # Range Residuals
            if data.get('range_residuals'):
                lines.append("")
                lines.append("📏 RANGE RESIDUALS:")
                residuals_list = []
                for r in data['range_residuals'][:6]:
                    res_str = self.safe_float_format(r, 2)
                    if res_str != "N/A":
                        residuals_list.append(f"{res_str}m")
                
                if residuals_list:
                    residuals_str = ", ".join(residuals_list)
                    lines.append(f"  {residuals_str}")
                    if len(data['range_residuals']) > 6:
                        lines.append("  (and more...)")
        
        lines.append("=" * 80)
        return "\n".join(lines)
    
    def data_changed(self, current_data, last_data):
        """Check if GPS data has meaningfully changed."""
        if last_data is None:
            return True
        
        # Check for fix status change
        if current_data['has_fix'] != last_data.get('has_fix'):
            return True
        
        # Check for running status change
        if current_data['running'] != last_data.get('running'):
            return True
        
        # Check for satellite count change
        current_sats = len(current_data.get('satellites_in_view', []))
        last_sats = len(last_data.get('satellites_in_view', []))
        if current_sats != last_sats:
            return True
        
        # Check satellites used change
        current_used = set(current_data.get('satellites_used', []))
        last_used = set(last_data.get('satellites_used', []))
        if current_used != last_used:
            return True
        
        # If we have a fix, check for position changes (>5m)
        if current_data['has_fix'] and last_data.get('has_fix'):
            try:
                curr_lat = float(current_data.get('latitude', 0))
                curr_lon = float(current_data.get('longitude', 0))
                last_lat = float(last_data.get('latitude', 0))
                last_lon = float(last_data.get('longitude', 0))
                
                # Simple distance check (roughly 5 meters in degrees)
                lat_diff = abs(curr_lat - last_lat)
                lon_diff = abs(curr_lon - last_lon)
                if lat_diff > 0.00005 or lon_diff > 0.00005:  # ~5m
                    return True
            except (ValueError, TypeError):
                pass
        
        # Check for accuracy changes
        if self.detailed:
            try:
                current_hdop = float(current_data.get('hdop', 0))
                last_hdop = float(last_data.get('hdop', 0))
                if abs(current_hdop - last_hdop) > 0.1:
                    return True
            except (ValueError, TypeError):
                pass
        
        return False
    
    def test_enhanced_gps(self, port=None, baudrate=9600):
        """Test GPS with enhanced data display."""
        port_info = f"custom port {port}" if port else "default port (/dev/ttyACM0)"
        logger.info(f"Testing u-blox 7 GPS with {port_info}")
        
        try:
            if port:
                self.gps = GPSHandler(port=port, baudrate=baudrate)
            else:
                self.gps = GPSHandler()
            
            self.gps.start()
            
            logger.info("GPS started. Waiting for data...")
            logger.info("Press Ctrl+C to stop the test.")
            
            if not self.verbose:
                logger.info("📊 GPS data will only be shown when there are meaningful changes")
                logger.info("💡 Use --verbose to see continuous updates")
            
            if self.detailed:
                logger.info("🔍 Detailed mode enabled - showing satellite details and accuracy info")
            
            no_data_count = 0
            max_no_data = 30  # 30 seconds without data before showing warning
            last_log_time = time.time()
            data_shown = False
            
            while self.running:
                data = self.gps.get_gps_data()
                
                # Check if we should display this data
                should_show = False
                
                if self.verbose:
                    should_show = True
                elif self.data_changed(data, self.last_data):
                    should_show = True
                    logger.info("📡 GPS data changed - showing update:")
                elif not data_shown:
                    should_show = True  # Show initial data
                    data_shown = True
                
                # Display data if needed
                if should_show:
                    if self.clear_screen and self.verbose:
                        print("\033[2J\033[H")  # Clear screen only in verbose mode
                    
                    print(self.format_gps_data(data))
                    
                    if not self.clear_screen:
                        print()  # Add blank line
                
                # Check status and log warnings
                current_time = time.time()
                if not data['running']:
                    if current_time - last_log_time > 10:
                        logger.warning("⚠️  GPS handler not running!")
                        last_log_time = current_time
                elif data['latitude'] is None and data['longitude'] is None:
                    no_data_count += 1
                    if no_data_count >= max_no_data and current_time - last_log_time > 30:
                        logger.warning(f"⚠️  No GPS data for {no_data_count} seconds. Check device and sky view.")
                        last_log_time = current_time
                else:
                    if no_data_count > 0:
                        logger.info(f"✅ GPS data received after {no_data_count} seconds")
                    no_data_count = 0  # Reset counter when we get data
                    
                    # Log periodically when we have a fix
                    if data['has_fix'] and current_time - last_log_time > 30:
                        sats_used = len(data.get('satellites_used', []))
                        try:
                            lat_val = float(data['latitude'])
                            lon_val = float(data['longitude'])
                            logger.info(f"🛰️  GPS fix active: {sats_used} satellites used, {lat_val:.6f}, {lon_val:.6f}")
                        except (ValueError, TypeError):
                            logger.info(f"🛰️  GPS fix active: {sats_used} satellites used")
                        last_log_time = current_time
                
                # Store current data for comparison
                self.last_data = data.copy()
                
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Test interrupted by user")
        except Exception as e:
            logger.error(f"Test failed: {str(e)}")
        finally:
            if self.gps:
                self.gps.stop()

def main():
    """Main test function."""
    print("Enhanced u-blox 7 GPS/GNSS Test")
    print("================================")
    print()
    
    # Check for options
    clear_screen = "--clear" in sys.argv
    if clear_screen:
        sys.argv.remove("--clear")
    
    verbose = "--verbose" in sys.argv
    if verbose:
        sys.argv.remove("--verbose")
    
    detailed = "--detailed" in sys.argv
    if detailed:
        sys.argv.remove("--detailed")
    
    # Parse port and baudrate
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        port = sys.argv[1]
        baudrate = int(sys.argv[2]) if len(sys.argv) > 2 else 9600
        print(f"Using custom port: {port} at {baudrate} baud")
    else:
        port = None
        baudrate = 9600
        print("Using default port: /dev/ttyACM0 at 9600 baud")
        print("\nUsage: python test_gps.py [port] [baudrate] [options]")
        print("Example: python test_gps.py /dev/ttyUSB0 4800 --verbose --detailed")
        print("Options:")
        print("  --clear     Clear screen between updates (use with --verbose)")
        print("  --verbose   Show continuous GPS updates (default: only changes)")
        print("  --detailed  Show detailed satellite and accuracy information")
    
    print()
    
    test = EnhancedGPSTest(clear_screen=clear_screen, verbose=verbose, detailed=detailed)
    test.test_enhanced_gps(port=port, baudrate=baudrate)

if __name__ == "__main__":
    main() 