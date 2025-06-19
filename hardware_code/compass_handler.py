import smbus2 as smbus
import math
import time
import logging
import threading
from collections import deque
import statistics
import json
import os

logger = logging.getLogger("CompassHandler")

# BMM150 address and register definitions
BMM150_ADDR = 0x13
BMM150_CHIP_ID_REG = 0x40
BMM150_DATA_X_LSB = 0x42
BMM150_DATA_X_MSB = 0x43
BMM150_DATA_Y_LSB = 0x44
BMM150_DATA_Y_MSB = 0x45
BMM150_DATA_Z_LSB = 0x46
BMM150_DATA_Z_MSB = 0x47
BMM150_POWER_CONTROL_REG = 0x4B
BMM150_OP_MODE_REG = 0x4C
BMM150_CHIP_ID = 0x32

class CompassHandler:
    """
    Handles reading and parsing data from a BMM150 compass sensor.
    This class reads magnetometer data from an I2C bus and calculates
    the magnetic heading with filtering for improved stability.
    """
    def __init__(self, bus_num=1, filter_size=10, outlier_threshold=20):
        self.bus_num = bus_num
        self.bus = None
        
        # Add thread safety lock
        self._data_lock = threading.Lock()
        
        self.heading = 0
        self.raw_heading = 0
        self.filtered_heading = 0
        self.x = 0
        self.y = 0
        self.z = 0
        self.connected = False
        self.running = False
        self.thread = None
        self.hard_iron_offset_x = 0  # Calibration offsets
        self.hard_iron_offset_y = 0
        self.declination = 0  # Magnetic declination for true north correction
        
        # Data quality tracking for marine environment
        self.data_quality_score = 0.0  # 0-1 score of data reliability
        self.interference_detected = False
        self.last_valid_reading_time = 0
        
        # Filtering parameters
        self.filter_size = filter_size
        self.outlier_threshold = outlier_threshold
        
        # Filtering buffers
        self.x_buffer = deque(maxlen=filter_size)
        self.y_buffer = deque(maxlen=filter_size)
        self.z_buffer = deque(maxlen=filter_size)
        self.heading_buffer = deque(maxlen=filter_size)
        
        # Motion detection - adjusted for sensor noise characteristics
        self.motion_threshold = 10  # degrees change to detect motion (increased from 5)
        self.stationary_count = 0
        self.min_stationary_readings = 10  # Require more readings to be considered stationary
        self.motion_hysteresis = 3  # Extra threshold when already in motion to prevent flapping
        
        # Exponential moving average factor
        self.ema_alpha = 0.3  # Lower values = more smoothing
        
        # Marine-specific parameters
        self.max_reasonable_field_strength = 2000  # Max reasonable magnetic field (μT)
        self.min_reasonable_field_strength = 100   # Min reasonable magnetic field (μT)
        self.deviation_table = {}  # Compass deviation table for boat-specific corrections
        
        # Error recovery
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        self.bus_recovery_interval = 30  # seconds
        
        # Calibration persistence
        self.calibration_file = "compass_calibration.json"
        
        # Auto-load existing calibration on startup
        self._load_calibration()

    def start(self):
        """
        Initialize and start the compass sensor.
        Returns True if successful, False otherwise.
        """
        try:
            # Initialize I2C bus
            self.bus = smbus.SMBus(self.bus_num)
            
            # Check chip ID - with retry logic to handle potential I2C instability
            retry_count = 0
            max_retries = 3
            chip_id = None
            
            while retry_count < max_retries:
                try:
                    chip_id = self.bus.read_byte_data(BMM150_ADDR, BMM150_CHIP_ID_REG)
                    logger.info(f"Read chip ID: {chip_id:#x} (attempt {retry_count+1})")
                    break
                except Exception as e:
                    retry_count += 1
                    logger.warning(f"Failed to read chip ID (attempt {retry_count}): {str(e)}")
                    time.sleep(0.5)  # Wait before retry
            
            # If we couldn't read the chip ID after all retries, fail
            if chip_id is None:
                logger.error("Failed to read BMM150 chip ID after multiple attempts")
                return False
                
            # Accept either 0x32 (standard) or 0x00 (variant) 
            if chip_id != 0x32 and chip_id != 0x00:
                logger.warning(f"Unexpected BMM150 chip ID: {chip_id:#x}, expected either 0x32 or 0x00")
                return False
            
            logger.info(f"BMM150 compass found with chip ID: {chip_id:#x}")
            
            # Power up the sensor
            self.bus.write_byte_data(BMM150_ADDR, BMM150_POWER_CONTROL_REG, 0x01)
            time.sleep(0.1)
            
            # Set normal mode
            self.bus.write_byte_data(BMM150_ADDR, BMM150_OP_MODE_REG, 0x00)
            time.sleep(0.1)
            
            self.connected = True
            
            # Start reading thread
            self.running = True
            self.thread = threading.Thread(target=self._read_compass_data)
            self.thread.daemon = True
            self.thread.start()
            
            logger.info("Compass handler started successfully with filtering enabled")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize compass: {str(e)}")
            self.connected = False
            return False
    
    def stop(self):
        """Stop the compass data reading thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        
        if self.bus and self.connected:
            try:
                # Put sensor to sleep mode
                self.bus.write_byte_data(BMM150_ADDR, BMM150_POWER_CONTROL_REG, 0x00)
            except Exception as e:
                logger.error(f"Error putting compass to sleep: {str(e)}")
        
        logger.info("Compass handler stopped")
    
    def _twos_complement(self, val, bits):
        """Convert two's complement value."""
        if (val & (1 << (bits - 1))) != 0:
            val = val - (1 << bits)
        return val
    
    def _is_outlier(self, new_heading, buffer):
        """Check if a new heading reading is an outlier."""
        if len(buffer) < 3:
            return False
        
        # Calculate median of recent readings
        recent_headings = list(buffer)[-3:]
        median_heading = statistics.median(recent_headings)
        
        # Calculate circular distance between new reading and median
        diff = abs(new_heading - median_heading)
        if diff > 180:
            diff = 360 - diff
        
        return diff > self.outlier_threshold
    
    def _circular_mean(self, angles):
        """Calculate circular mean of angles in degrees."""
        if not angles:
            return None
        
        # Convert to radians and calculate circular mean
        sin_sum = sum(math.sin(math.radians(angle)) for angle in angles)
        cos_sum = sum(math.cos(math.radians(angle)) for angle in angles)
        
        mean_angle = math.atan2(sin_sum, cos_sum)
        return (math.degrees(mean_angle) + 360) % 360
    
    def _detect_motion(self, new_raw_heading):
        """Detect if compass is in motion based on raw heading changes with hysteresis."""
        if len(self.heading_buffer) < 3:
            return False
        
        # Use different thresholds based on current state to prevent flapping
        current_threshold = self.motion_threshold
        if self.stationary_count < self.min_stationary_readings:
            # If we think we're in motion, require a bit more evidence to stay in motion
            current_threshold = self.motion_threshold + self.motion_hysteresis
        
        # Compare against recent raw readings, not filtered ones
        if hasattr(self, '_recent_raw_headings') and len(self._recent_raw_headings) >= 3:
            # Check change over last few readings - look for consistent motion
            recent_changes = []
            for i in range(1, min(4, len(self._recent_raw_headings))):
                prev_raw = self._recent_raw_headings[-i-1]
                curr_raw = self._recent_raw_headings[-i]
                diff = abs(curr_raw - prev_raw)
                if diff > 180:
                    diff = 360 - diff
                recent_changes.append(diff)
            
            # Require multiple significant changes to indicate motion
            significant_changes = [c for c in recent_changes if c > current_threshold]
            
            if len(significant_changes) >= 2:  # At least 2 out of last 3 changes are significant
                self.stationary_count = 0
                return True
        
        # If no significant motion detected, increment stationary counter
        self.stationary_count += 1
        return False
    
    def _read_compass_data(self):
        """Thread function to continuously read compass data."""
        last_chip_id_check = 0
        chip_id_check_interval = 60  # Check chip ID every 60 seconds
        
        # Track recent raw headings for better motion detection
        self._recent_raw_headings = deque(maxlen=10)
        
        while self.running:
            try:
                if not self.connected:
                    time.sleep(1)
                    continue
                
                # Periodically verify chip ID to detect if it changes
                current_time = time.time()
                if current_time - last_chip_id_check > chip_id_check_interval:
                    try:
                        chip_id = self.bus.read_byte_data(BMM150_ADDR, BMM150_CHIP_ID_REG)
                        logger.debug(f"Periodic chip ID check: {chip_id:#x}")
                        if chip_id != 0x32 and chip_id != 0x00:
                            logger.warning(f"Chip ID changed during operation to {chip_id:#x}")
                    except Exception as e:
                        logger.warning(f"Failed to check chip ID during operation: {str(e)}")
                    
                    last_chip_id_check = current_time
                
                # Read the raw data
                x_lsb = self.bus.read_byte_data(BMM150_ADDR, BMM150_DATA_X_LSB)
                x_msb = self.bus.read_byte_data(BMM150_ADDR, BMM150_DATA_X_MSB)
                y_lsb = self.bus.read_byte_data(BMM150_ADDR, BMM150_DATA_Y_LSB)
                y_msb = self.bus.read_byte_data(BMM150_ADDR, BMM150_DATA_Y_MSB)
                z_lsb = self.bus.read_byte_data(BMM150_ADDR, BMM150_DATA_Z_LSB)
                z_msb = self.bus.read_byte_data(BMM150_ADDR, BMM150_DATA_Z_MSB)
                
                # Convert to 16-bit values
                x_raw = (x_msb << 8) | x_lsb
                y_raw = (y_msb << 8) | y_lsb
                z_raw = (z_msb << 8) | z_lsb
                
                # Apply two's complement
                x = self._twos_complement(x_raw >> 3, 13)
                y = self._twos_complement(y_raw >> 3, 13)
                z = self._twos_complement(z_raw >> 1, 15)
                
                # Apply hard iron calibration
                x -= self.hard_iron_offset_x
                y -= self.hard_iron_offset_y
                
                # Add to filtering buffers
                self.x_buffer.append(x)
                self.y_buffer.append(y)
                self.z_buffer.append(z)
                
                # Calculate raw heading
                raw_heading = math.atan2(y, x) * 180.0 / math.pi
                raw_heading = (raw_heading + 360) % 360
                self.raw_heading = raw_heading
                
                # Apply magnetic declination
                raw_heading += self.declination
                raw_heading = (raw_heading + 360) % 360
                
                # Track raw headings for motion detection
                self._recent_raw_headings.append(raw_heading)
                
                # Detect motion using raw headings
                in_motion = self._detect_motion(raw_heading)
                
                # Check for outliers only if not in rapid motion
                is_outlier = False
                if not in_motion or self.stationary_count > 2:
                    is_outlier = self._is_outlier(raw_heading, self.heading_buffer)
                
                if not is_outlier:
                    self.heading_buffer.append(raw_heading)
                    
                    # Apply different filtering based on motion state
                    if in_motion and self.stationary_count < 3:
                        # Use very light filtering for motion - prioritize responsiveness
                        if len(self.heading_buffer) >= 2:
                            # Just average last 2 readings for quick response
                            recent_headings = list(self.heading_buffer)[-2:]
                            filtered_heading = self._circular_mean(recent_headings)
                        else:
                            filtered_heading = raw_heading
                        
                        # Use high alpha for fast response during motion
                        motion_alpha = 0.8
                    elif self.stationary_count < self.min_stationary_readings:
                        # Transition state - moderate filtering
                        if len(self.heading_buffer) >= 3:
                            filtered_heading = self._circular_mean(list(self.heading_buffer)[-3:])
                        else:
                            filtered_heading = raw_heading
                        motion_alpha = 0.5
                    else:
                        # Stationary - use stronger filtering
                        if len(self.heading_buffer) >= self.filter_size:
                            filtered_heading = self._circular_mean(list(self.heading_buffer))
                        else:
                            filtered_heading = self._circular_mean(list(self.heading_buffer))
                        motion_alpha = self.ema_alpha
                    
                    # Apply exponential moving average with dynamic alpha
                    if self.filtered_heading == 0:  # First reading
                        self.filtered_heading = filtered_heading
                    else:
                        # Handle circular averaging for EMA
                        diff = filtered_heading - self.filtered_heading
                        if diff > 180:
                            diff -= 360
                        elif diff < -180:
                            diff += 360
                        
                        self.filtered_heading += motion_alpha * diff
                        self.filtered_heading = (self.filtered_heading + 360) % 360
                    
                    # Store filtered raw values using median filter
                    if len(self.x_buffer) >= 3:
                        filtered_x = statistics.median(list(self.x_buffer)[-3:])
                        filtered_y = statistics.median(list(self.y_buffer)[-3:])
                        filtered_z = statistics.median(list(self.z_buffer)[-3:])
                    else:
                        filtered_x = x
                        filtered_y = y
                        filtered_z = z
                    
                    # Validate data quality for marine environment
                    quality_score = self._assess_data_quality(filtered_x, filtered_y, filtered_z, raw_heading)
                    interference = self._detect_interference(filtered_x, filtered_y, filtered_z)
                    
                    # Thread-safe update of shared data
                    with self._data_lock:
                        self.heading = self.filtered_heading
                        self.x = filtered_x
                        self.y = filtered_y
                        self.z = filtered_z
                        self.data_quality_score = quality_score
                        self.interference_detected = interference
                        if quality_score > 0.7:  # Good quality reading
                            self.last_valid_reading_time = time.time()
                else:
                    logger.debug(f"Rejected outlier heading: {raw_heading:.1f}°")
                
                # Read at 10Hz for better motion detection
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error reading compass data: {str(e)}")
                self.consecutive_errors += 1
                
                # Attempt bus recovery if too many consecutive errors
                if self.consecutive_errors >= self.max_consecutive_errors:
                    logger.warning(f"Too many consecutive errors ({self.consecutive_errors}), attempting bus recovery")
                    if self._attempt_bus_recovery():
                        self.consecutive_errors = 0
                        logger.info("Bus recovery successful")
                    else:
                        logger.error("Bus recovery failed, waiting before retry")
                        time.sleep(self.bus_recovery_interval)
                        self.consecutive_errors = 0
                else:
                    time.sleep(1)
    
    def get_heading(self):
        """Return the current filtered heading in degrees (0-360)."""
        with self._data_lock:
            return self.heading
    
    def get_raw_heading(self):
        """Return the current unfiltered heading in degrees (0-360)."""
        with self._data_lock:
            return self.raw_heading
    
    def get_compass_data(self):
        """Return a dictionary with all compass data."""
        with self._data_lock:
            return {
                'heading': self.heading,
                'raw_heading': self.raw_heading,
                'filtered_heading': self.filtered_heading,
                'x': self.x,
                'y': self.y,
                'z': self.z,
                'connected': self.connected,
                'stationary': self.stationary_count >= self.min_stationary_readings,
                'buffer_size': len(self.heading_buffer),
                'data_quality': self.data_quality_score,
                'interference_detected': self.interference_detected,
                'last_valid_reading_age': time.time() - self.last_valid_reading_time if self.last_valid_reading_time > 0 else float('inf')
            }
    
    def set_calibration(self, offset_x=0, offset_y=0, declination=0):
        """
        Set calibration parameters for the compass.
        
        Args:
            offset_x: Hard iron calibration offset for X axis
            offset_y: Hard iron calibration offset for Y axis
            declination: Magnetic declination angle (difference between magnetic and true north)
        """
        self.hard_iron_offset_x = offset_x
        self.hard_iron_offset_y = offset_y
        self.declination = declination
        logger.info(f"Compass calibration set: offsets X={offset_x}, Y={offset_y}, declination={declination}°")
        
        # Auto-save calibration data
        self._save_calibration()
    
    def set_filter_parameters(self, filter_size=10, outlier_threshold=20, ema_alpha=0.3, motion_threshold=10):
        """
        Adjust filtering parameters for different use cases.
        
        Args:
            filter_size: Size of moving average buffer (higher = more smoothing)
            outlier_threshold: Threshold in degrees for outlier rejection
            ema_alpha: Exponential moving average factor (0.1-0.5, lower = more smoothing)
            motion_threshold: Threshold in degrees for motion detection
        """
        self.filter_size = filter_size
        self.outlier_threshold = outlier_threshold
        self.ema_alpha = ema_alpha
        self.motion_threshold = motion_threshold
        
        # Resize buffers if needed
        self.x_buffer = deque(self.x_buffer, maxlen=filter_size)
        self.y_buffer = deque(self.y_buffer, maxlen=filter_size)
        self.z_buffer = deque(self.z_buffer, maxlen=filter_size)
        self.heading_buffer = deque(self.heading_buffer, maxlen=filter_size)
        
        logger.info(f"Filter parameters updated: filter_size={filter_size}, outlier_threshold={outlier_threshold}°, "
                   f"ema_alpha={ema_alpha}, motion_threshold={motion_threshold}°")
    
    def reset_filters(self):
        """Reset all filtering buffers."""
        self.x_buffer.clear()
        self.y_buffer.clear()
        self.z_buffer.clear()
        self.heading_buffer.clear()
        self.stationary_count = 0
        self.filtered_heading = 0
        logger.info("Compass filters reset")
    
    def _assess_data_quality(self, x, y, z, heading):
        """
        Assess the quality of compass data for marine environment.
        Returns a score from 0.0 (poor) to 1.0 (excellent).
        """
        quality_score = 1.0
        
        # Check magnetic field strength - should be within reasonable Earth field range
        field_strength = math.sqrt(x*x + y*y + z*z)
        if field_strength < self.min_reasonable_field_strength or field_strength > self.max_reasonable_field_strength:
            quality_score *= 0.3  # Very poor quality if field strength is unreasonable
            logger.warning(f"Unusual magnetic field strength: {field_strength:.1f}")
        
        # Check for data stability in heading buffer
        if len(self.heading_buffer) >= 5:
            recent_headings = list(self.heading_buffer)[-5:]
            heading_variance = statistics.variance(recent_headings) if len(recent_headings) > 1 else 0
            
            # Penalize high variance (noisy readings)
            if heading_variance > 100:  # Very unstable
                quality_score *= 0.5
            elif heading_variance > 50:  # Moderately unstable
                quality_score *= 0.7
            elif heading_variance > 20:  # Slightly unstable
                quality_score *= 0.9
        
        # Check if any axis is saturated (indicates strong local interference)
        max_reasonable_axis_value = 1500  # Adjust based on your sensor calibration
        if abs(x) > max_reasonable_axis_value or abs(y) > max_reasonable_axis_value or abs(z) > max_reasonable_axis_value:
            quality_score *= 0.4
            logger.warning(f"Possible axis saturation: X={x}, Y={y}, Z={z}")
        
        return max(0.0, min(1.0, quality_score))
    
    def _detect_interference(self, x, y, z):
        """
        Detect magnetic interference common in marine environments.
        Returns True if significant interference is detected.
        """
        # Calculate magnetic field strength
        field_strength = math.sqrt(x*x + y*y + z*z)
        
        # Check for rapid field strength changes (engine interference)
        if hasattr(self, '_prev_field_strength'):
            field_change = abs(field_strength - self._prev_field_strength)
            if field_change > 200:  # Rapid field change indicates interference
                self._prev_field_strength = field_strength
                return True
        
        self._prev_field_strength = field_strength
        
        # Check for unusual field strength
        if field_strength < self.min_reasonable_field_strength or field_strength > self.max_reasonable_field_strength:
            return True
        
        # Check for heading instability during stationary periods
        if (self.stationary_count >= self.min_stationary_readings and 
            len(self.heading_buffer) >= 5):
            recent_headings = list(self.heading_buffer)[-5:]
            if len(recent_headings) > 1:
                heading_std = statistics.stdev(recent_headings)
                if heading_std > 15:  # High deviation during stationary period
                    return True
        
        return False
    
    def is_data_reliable(self, min_quality=0.7, max_age_seconds=5.0):
        """
        Check if compass data is reliable for navigation.
        
        Args:
            min_quality: Minimum quality score required (0.0-1.0)
            max_age_seconds: Maximum age of last valid reading in seconds
        
        Returns:
            bool: True if data is reliable for navigation
        """
        with self._data_lock:
            # Check data quality score
            if self.data_quality_score < min_quality:
                return False
            
            # Check if interference is detected
            if self.interference_detected:
                return False
            
            # Check data freshness
            if self.last_valid_reading_time > 0:
                age = time.time() - self.last_valid_reading_time
                if age > max_age_seconds:
                    return False
            else:
                return False  # No valid readings yet
            
            # Check connection status
            if not self.connected:
                return False
            
            return True
    
    def get_heading_with_confidence(self):
        """
        Get heading with confidence information.
        
        Returns:
            tuple: (heading, confidence_score, is_reliable)
        """
        with self._data_lock:
            confidence = self.data_quality_score * (0.5 if self.interference_detected else 1.0)
            is_reliable = self.is_data_reliable()
            return self.heading, confidence, is_reliable
    
    def _attempt_bus_recovery(self):
        """
        Attempt to recover from I2C bus errors.
        Returns True if recovery successful, False otherwise.
        """
        try:
            # Close existing bus connection
            if self.bus:
                try:
                    self.bus.close()
                except:
                    pass
            
            # Wait a moment
            time.sleep(2)
            
            # Reinitialize I2C bus
            self.bus = smbus.SMBus(self.bus_num)
            
            # Try to read chip ID to verify recovery
            chip_id = self.bus.read_byte_data(BMM150_ADDR, BMM150_CHIP_ID_REG)
            if chip_id == 0x32 or chip_id == 0x00:
                # Reinitialize sensor
                self.bus.write_byte_data(BMM150_ADDR, BMM150_POWER_CONTROL_REG, 0x01)
                time.sleep(0.1)
                self.bus.write_byte_data(BMM150_ADDR, BMM150_OP_MODE_REG, 0x00)
                time.sleep(0.1)
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Bus recovery failed: {str(e)}")
            return False
    
    def set_deviation_table(self, deviation_table):
        """
        Set compass deviation table for boat-specific corrections.
        
        Args:
            deviation_table: Dictionary mapping heading ranges to deviation corrections
                           Format: {(min_heading, max_heading): deviation_degrees, ...}
                           Example: {(0, 45): -2.5, (45, 90): -1.2, ...}
        """
        self.deviation_table = deviation_table.copy()
        logger.info(f"Compass deviation table set with {len(deviation_table)} entries")
    
    def _apply_deviation_correction(self, heading):
        """
        Apply compass deviation correction based on current heading.
        
        Args:
            heading: Raw compass heading in degrees
            
        Returns:
            Corrected heading in degrees
        """
        if not self.deviation_table:
            return heading
        
        # Find applicable deviation correction
        for (min_heading, max_heading), deviation in self.deviation_table.items():
            if min_heading <= heading <= max_heading:
                corrected_heading = heading + deviation
                return (corrected_heading + 360) % 360
        
        return heading
    
    def calibrate_compass(self, duration_seconds=60):
        """
        Perform compass calibration by collecting data while boat rotates.
        This is a simplified calibration - for production use, implement full
        ellipse fitting for hard and soft iron correction.
        
        Args:
            duration_seconds: How long to collect calibration data
            
        Returns:
            Tuple of (success, hard_iron_x, hard_iron_y, message)
        """
        logger.info(f"Starting compass calibration for {duration_seconds} seconds")
        logger.info("Slowly rotate the boat through 360 degrees during calibration")
        
        # Collect raw magnetometer data
        x_readings = []
        y_readings = []
        start_time = time.time()
        
        while time.time() - start_time < duration_seconds:
            if self.connected and len(self.x_buffer) > 0:
                x_readings.append(self.x)
                y_readings.append(self.y)
            time.sleep(0.5)
        
        if len(x_readings) < 20:
            return False, 0, 0, "Insufficient data collected for calibration"
        
        # Calculate hard iron offsets (simple method)
        offset_x = (max(x_readings) + min(x_readings)) / 2
        offset_y = (max(y_readings) + min(y_readings)) / 2
        
        # Apply calibration
        self.set_calibration(offset_x, offset_y, self.declination)
        
        logger.info(f"Calibration complete: X offset={offset_x:.1f}, Y offset={offset_y:.1f}")
        
        # Auto-save calibration data
        self._save_calibration()
        
        return True, offset_x, offset_y, "Calibration successful"
    
    def _save_calibration(self):
        """Save calibration data to file."""
        try:
            calibration_data = {
                'hard_iron_offset_x': self.hard_iron_offset_x,
                'hard_iron_offset_y': self.hard_iron_offset_y,
                'declination': self.declination,
                'deviation_table': self.deviation_table,
                'timestamp': time.time(),
                'version': '1.0'
            }
            
            with open(self.calibration_file, 'w') as f:
                json.dump(calibration_data, f, indent=2)
            
            logger.info(f"Calibration data saved to {self.calibration_file}")
            
        except Exception as e:
            logger.error(f"Failed to save calibration data: {str(e)}")
    
    def _load_calibration(self):
        """Load calibration data from file."""
        try:
            if os.path.exists(self.calibration_file):
                with open(self.calibration_file, 'r') as f:
                    calibration_data = json.load(f)
                
                # Load calibration values
                self.hard_iron_offset_x = calibration_data.get('hard_iron_offset_x', 0)
                self.hard_iron_offset_y = calibration_data.get('hard_iron_offset_y', 0)
                self.declination = calibration_data.get('declination', 0)
                self.deviation_table = calibration_data.get('deviation_table', {})
                
                # Convert string keys back to tuples for deviation table
                if self.deviation_table and isinstance(list(self.deviation_table.keys())[0], str):
                    new_deviation_table = {}
                    for key_str, value in self.deviation_table.items():
                        # Parse "(start, end)" string back to tuple
                        key_tuple = eval(key_str)  # Safe since we control the format
                        new_deviation_table[key_tuple] = value
                    self.deviation_table = new_deviation_table
                
                timestamp = calibration_data.get('timestamp', 0)
                age_days = (time.time() - timestamp) / (24 * 3600)
                
                logger.info(f"Loaded calibration: X={self.hard_iron_offset_x:.2f}, Y={self.hard_iron_offset_y:.2f}, "
                           f"declination={self.declination:.2f}° (age: {age_days:.1f} days)")
                
                if age_days > 30:
                    logger.warning("Calibration data is older than 30 days - consider recalibrating")
                    
            else:
                logger.info("No existing calibration file found - using default values")
                
        except Exception as e:
            logger.error(f"Failed to load calibration data: {str(e)}")
            logger.info("Using default calibration values")
    
    def get_calibration_info(self):
        """Get current calibration information."""
        try:
            if os.path.exists(self.calibration_file):
                with open(self.calibration_file, 'r') as f:
                    calibration_data = json.load(f)
                
                timestamp = calibration_data.get('timestamp', 0)
                age_days = (time.time() - timestamp) / (24 * 3600)
                
                return {
                    'hard_iron_offset_x': self.hard_iron_offset_x,
                    'hard_iron_offset_y': self.hard_iron_offset_y,
                    'declination': self.declination,
                    'calibration_age_days': age_days,
                    'calibration_file': self.calibration_file,
                    'deviation_entries': len(self.deviation_table)
                }
            else:
                return {
                    'hard_iron_offset_x': self.hard_iron_offset_x,
                    'hard_iron_offset_y': self.hard_iron_offset_y,
                    'declination': self.declination,
                    'calibration_age_days': float('inf'),
                    'calibration_file': 'Not found',
                    'deviation_entries': len(self.deviation_table)
                }
        except Exception as e:
            logger.error(f"Error getting calibration info: {str(e)}")
            return None