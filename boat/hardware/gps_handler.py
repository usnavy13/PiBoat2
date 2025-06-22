import serial
import pynmea2
import logging
import time
import threading
import decimal  # Add import for decimal module
from datetime import datetime
from .agps_helper import AGPSHelper  # Import A-GPS helper

logger = logging.getLogger("GPSHandler")

class GPSHandler:
    """
    Enhanced GPS handler for u-blox 7 GPS/GNSS receiver.
    Extracts comprehensive data from all supported NMEA sentences including:
    - Standard position data (GGA, RMC, GLL, VTG)
    - Satellite information (GSV, GSA)
    - Error and accuracy data (GBS, GRS, GST)
    - Time and date information (ZDA)
    - u-blox proprietary data (PUBX sentences)
    """
    def __init__(self, port='/dev/ttyACM0', baudrate=9600, timeout=1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn = None
        self.running = False
        self.thread = None
        
        # Basic GPS data
        self.latitude = None
        self.longitude = None
        self.altitude = None
        self.speed_knots = None
        self.course = None  # Heading/course in degrees
        self.satellites = None
        self.timestamp = None
        self.fix_quality = None
        
        # Enhanced position data
        self.altitude_msl = None  # Mean sea level altitude
        self.geoid_height = None  # Height of geoid above WGS84 ellipsoid
        self.dgps_age = None  # Age of differential GPS data
        self.dgps_station_id = None  # Differential reference station ID
        self.speed_kmh = None  # Speed in km/h
        self.magnetic_variation = None  # Magnetic variation
        self.variation_direction = None  # E or W
        
        # Satellite information
        self.satellites_in_view = []  # List of satellites in view with details
        self.satellites_used = []  # List of satellite IDs used in fix
        self.pdop = None  # Position dilution of precision
        self.hdop = None  # Horizontal dilution of precision
        self.vdop = None  # Vertical dilution of precision
        
        # Error and accuracy data
        self.lat_error = None  # Latitude error estimate (meters)
        self.lon_error = None  # Longitude error estimate (meters)
        self.alt_error = None  # Altitude error estimate (meters)
        self.range_residuals = []  # Range residuals for satellites
        self.position_error_ellipse = {}  # Position error ellipse data
        
        # Time and date
        self.utc_date = None  # UTC date
        self.local_zone_offset = None  # Local time zone offset
        
        # Additional status
        self.navigation_status = None  # Navigation status (A=autonomous, D=differential, etc.)
        self.fix_mode = None  # 1=no fix, 2=2D, 3=3D
        self.selection_mode = None  # M=manual, A=automatic
        
        # u-blox specific data
        self.horizontal_accuracy = None  # Horizontal accuracy estimate
        self.vertical_accuracy = None  # Vertical accuracy estimate
        self.vertical_velocity = None  # Vertical velocity
        self.antenna_status = None  # Antenna status information
        
        # Lock for thread safety when accessing GPS data
        self.lock = threading.Lock()
        
        # A-GPS helper
        self.agps_helper = AGPSHelper(port=self.port, baudrate=self.baudrate)
        self.last_agps_update = None
        self.agps_update_interval = 4 * 3600  # 4 hours in seconds
        
        logger.info(f"Initialized enhanced GPS handler for u-blox 7 on port {self.port}")
    
    def perform_agps_update(self, force=False):
        """
        Perform A-GPS update to speed up GPS fix.
        
        Args:
            force: Force update even if recently updated
            
        Returns:
            bool: True if successful
        """
        # Check if we need an update
        if not force and self.last_agps_update:
            time_since_update = time.time() - self.last_agps_update
            if time_since_update < self.agps_update_interval:
                logger.info(f"A-GPS data still fresh ({time_since_update/3600:.1f} hours old)")
                return True
        
        # Stop GPS reading temporarily
        was_running = self.running
        if was_running:
            self.stop()
            time.sleep(1)  # Wait for thread to stop
        
        try:
            # Perform A-GPS update (quick assist if no token)
            success = self.agps_helper.perform_quick_assist()
            if success:
                self.last_agps_update = time.time()
                logger.info("GPS quick assist successful - GPS fix should be faster now")
            return success
        finally:
            # Restart GPS reading if it was running
            if was_running:
                self.start()
    
    def start(self):
        """Start reading GPS data in a background thread."""
        if self.thread and self.thread.is_alive():
            logger.warning("GPS handler already running")
            return
            
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout
            )
            logger.info(f"Connected to GPS device on {self.port}")
            
            self.running = True
            self.thread = threading.Thread(target=self._read_gps_data)
            self.thread.daemon = True
            self.thread.start()
            logger.info("GPS handler thread started")
            
            # Perform A-GPS update on first start if we have internet
            if not self.last_agps_update:
                threading.Thread(target=self.perform_agps_update, daemon=True).start()
            
        except Exception as e:
            logger.error(f"Failed to connect to GPS device: {str(e)}")
            self.running = False
            if self.serial_conn:
                self.serial_conn.close()
                self.serial_conn = None
    
    def stop(self):
        """Stop reading GPS data."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            self.thread = None
        
        if self.serial_conn:
            self.serial_conn.close()
            self.serial_conn = None
        logger.info("GPS handler stopped")
    
    def _read_gps_data(self):
        """Background thread to continuously read and parse GPS data."""
        no_fix_duration = 0
        check_interval = 10  # Check every 10 seconds
        
        while self.running:
            try:
                if not self.serial_conn or not self.serial_conn.is_open:
                    logger.error("Serial connection closed. Attempting to reconnect...")
                    time.sleep(5)
                    self.start()
                    continue
                
                line = self.serial_conn.readline().decode('ascii', errors='replace').strip()
                if not line:
                    continue
                    
                # Try to parse the NMEA sentence
                try:
                    msg = pynmea2.parse(line)
                    self._process_nmea_message(msg)
                    
                    # Check if we have a fix
                    if not self.has_fix():
                        no_fix_duration += 1
                        # If no fix for 2 minutes, try A-GPS update
                        if no_fix_duration >= 120:
                            logger.warning("No GPS fix for 2 minutes, attempting A-GPS update...")
                            threading.Thread(
                                target=self.perform_agps_update, 
                                args=(True,), 
                                daemon=True
                            ).start()
                            no_fix_duration = 0  # Reset counter
                    else:
                        no_fix_duration = 0  # Reset when we have a fix
                        
                except pynmea2.ParseError:
                    # Skip invalid sentences, but log unknown proprietary sentences
                    if line.startswith('$PUBX') or line.startswith('$PMTK'):
                        logger.debug(f"Received proprietary sentence: {line[:50]}...")
                    continue
                except Exception as e:
                    logger.debug(f"Error parsing sentence '{line[:30]}...': {str(e)}")
                    continue
                    
            except Exception as e:
                logger.error(f"Error reading GPS data: {str(e)}")
                time.sleep(1)
    
    def _process_nmea_message(self, msg):
        """Process different types of NMEA messages."""
        with self.lock:
            try:
                # Handle timestamp from any message that has it
                if hasattr(msg, 'timestamp') and msg.timestamp:
                    if hasattr(msg.timestamp, 'isoformat'):
                        self.timestamp = msg.timestamp.isoformat()
                    else:
                        self.timestamp = str(msg.timestamp)
                
                # GGA message - Global Positioning System Fix Data
                if isinstance(msg, pynmea2.GGA):
                    self._process_gga(msg)
                
                # RMC message - Recommended minimum navigation information
                elif isinstance(msg, pynmea2.RMC):
                    self._process_rmc(msg)
                
                # GLL message - Geographic Position - Latitude/Longitude
                elif isinstance(msg, pynmea2.GLL):
                    self._process_gll(msg)
                
                # VTG message - Track made good and ground speed
                elif isinstance(msg, pynmea2.VTG):
                    self._process_vtg(msg)
                
                # GSA message - GPS DOP and active satellites
                elif isinstance(msg, pynmea2.GSA):
                    self._process_gsa(msg)
                
                # GSV message - Satellites in view
                elif isinstance(msg, pynmea2.GSV):
                    self._process_gsv(msg)
                
                # GBS message - GPS Satellite Fault Detection
                elif isinstance(msg, pynmea2.GBS):
                    self._process_gbs(msg)
                
                # GRS message - GPS Range Residuals
                elif isinstance(msg, pynmea2.GRS):
                    self._process_grs(msg)
                
                # GST message - GPS Pseudorange Noise Statistics
                elif isinstance(msg, pynmea2.GST):
                    self._process_gst(msg)
                
                # ZDA message - Time & Date
                elif isinstance(msg, pynmea2.ZDA):
                    self._process_zda(msg)
                
                # TXT message - Text transmission
                elif isinstance(msg, pynmea2.TXT):
                    self._process_txt(msg)
                
            except Exception as e:
                logger.error(f"Error processing NMEA message: {str(e)}")
    
    def _process_gga(self, msg):
        """Process GGA message - Global Positioning System Fix Data"""
        if msg.latitude and msg.longitude:
            self.latitude = msg.latitude
            self.longitude = msg.longitude
        
        if hasattr(msg, 'altitude') and msg.altitude is not None:
            self.altitude = msg.altitude
            self.altitude_msl = msg.altitude  # GGA altitude is MSL
        
        if hasattr(msg, 'num_sats'):
            self.satellites = msg.num_sats
        
        if hasattr(msg, 'gps_qual'):
            self.fix_quality = msg.gps_qual
        
        if hasattr(msg, 'horizontal_dil') and msg.horizontal_dil is not None:
            self.hdop = msg.horizontal_dil
        
        if hasattr(msg, 'geo_sep') and msg.geo_sep is not None:
            self.geoid_height = msg.geo_sep
        
        if hasattr(msg, 'age_gps_data') and msg.age_gps_data is not None:
            self.dgps_age = msg.age_gps_data
        
        if hasattr(msg, 'ref_station_id') and msg.ref_station_id is not None:
            self.dgps_station_id = msg.ref_station_id
    
    def _process_rmc(self, msg):
        """Process RMC message - Recommended minimum navigation information"""
        if msg.latitude and msg.longitude:
            self.latitude = msg.latitude
            self.longitude = msg.longitude
        
        if hasattr(msg, 'spd_over_grnd') and msg.spd_over_grnd is not None:
            self.speed_knots = msg.spd_over_grnd
        
        if hasattr(msg, 'true_course') and msg.true_course is not None:
            self.course = msg.true_course
        
        if hasattr(msg, 'mag_variation') and msg.mag_variation is not None:
            self.magnetic_variation = msg.mag_variation
        
        if hasattr(msg, 'mag_var_dir'):
            self.variation_direction = msg.mag_var_dir
        
        if hasattr(msg, 'status'):
            # A = Active (valid), V = Void (warning)
            self.navigation_status = msg.status
    
    def _process_gll(self, msg):
        """Process GLL message - Geographic Position - Latitude/Longitude"""
        if msg.latitude and msg.longitude:
            self.latitude = msg.latitude
            self.longitude = msg.longitude
        
        if hasattr(msg, 'status'):
            self.navigation_status = msg.status
    
    def _process_vtg(self, msg):
        """Process VTG message - Track made good and ground speed"""
        if hasattr(msg, 'spd_over_grnd_kts') and msg.spd_over_grnd_kts is not None:
            self.speed_knots = msg.spd_over_grnd_kts
        
        if hasattr(msg, 'spd_over_grnd_kmph') and msg.spd_over_grnd_kmph is not None:
            self.speed_kmh = msg.spd_over_grnd_kmph
        
        if hasattr(msg, 'true_track') and msg.true_track is not None:
            self.course = msg.true_track
    
    def _process_gsa(self, msg):
        """Process GSA message - GPS DOP and active satellites"""
        if hasattr(msg, 'mode'):
            self.fix_mode = msg.mode
        
        if hasattr(msg, 'mode_fix_type'):
            self.selection_mode = msg.mode_fix_type
        
        if hasattr(msg, 'pdop') and msg.pdop is not None:
            self.pdop = msg.pdop
        
        if hasattr(msg, 'hdop') and msg.hdop is not None:
            self.hdop = msg.hdop
        
        if hasattr(msg, 'vdop') and msg.vdop is not None:
            self.vdop = msg.vdop
        
        # Extract satellite IDs used in fix
        satellites_used = []
        for i in range(1, 13):  # GSA can have up to 12 satellite IDs
            sat_id = getattr(msg, f'sv_id{i:02d}', None)
            if sat_id and sat_id.strip():
                try:
                    satellites_used.append(int(sat_id))
                except (ValueError, TypeError):
                    pass
        self.satellites_used = satellites_used
    
    def _process_gsv(self, msg):
        """Process GSV message - Satellites in view"""
        if not hasattr(msg, 'num_sv_in_view'):
            return
        
        # GSV messages come in groups, we need to collect all satellites
        if not hasattr(self, '_gsv_temp_satellites'):
            self._gsv_temp_satellites = {}
        
        # Extract satellite data from this GSV message
        for i in range(1, 5):  # Up to 4 satellites per GSV message
            sv_prn = getattr(msg, f'sv_prn_{i:02d}', None)
            if sv_prn:
                try:
                    sat_id = int(sv_prn)
                    satellite_info = {
                        'prn': sat_id,
                        'elevation': None,
                        'azimuth': None,
                        'snr': None
                    }
                    
                    elevation = getattr(msg, f'elevation_{i:02d}', None)
                    if elevation is not None and elevation != '':
                        satellite_info['elevation'] = int(elevation)
                    
                    azimuth = getattr(msg, f'azimuth_{i:02d}', None)
                    if azimuth is not None and azimuth != '':
                        satellite_info['azimuth'] = int(azimuth)
                    
                    snr = getattr(msg, f'snr_{i:02d}', None)
                    if snr is not None and snr != '':
                        satellite_info['snr'] = int(snr)
                    
                    self._gsv_temp_satellites[sat_id] = satellite_info
                    
                except (ValueError, TypeError):
                    continue
        
        # Check if this is the last GSV message in the group
        if (hasattr(msg, 'msg_num') and hasattr(msg, 'num_messages') and 
            msg.msg_num == msg.num_messages):
            # Update the main satellites list
            self.satellites_in_view = list(self._gsv_temp_satellites.values())
            self._gsv_temp_satellites = {}
    
    def _process_gbs(self, msg):
        """Process GBS message - GPS Satellite Fault Detection (error estimates)"""
        if hasattr(msg, 'lat_err') and msg.lat_err is not None:
            self.lat_error = float(msg.lat_err)
        
        if hasattr(msg, 'lon_err') and msg.lon_err is not None:
            self.lon_error = float(msg.lon_err)
        
        if hasattr(msg, 'alt_err') and msg.alt_err is not None:
            self.alt_error = float(msg.alt_err)
    
    def _process_grs(self, msg):
        """Process GRS message - GPS Range Residuals"""
        residuals = []
        for i in range(1, 13):  # Up to 12 residuals
            residual = getattr(msg, f'range_residual_{i:02d}', None)
            if residual is not None and residual != '':
                try:
                    residuals.append(float(residual))
                except (ValueError, TypeError):
                    pass
        self.range_residuals = residuals
    
    def _process_gst(self, msg):
        """Process GST message - GPS Pseudorange Noise Statistics"""
        error_ellipse = {}
        
        if hasattr(msg, 'std_dev_semi_major') and msg.std_dev_semi_major is not None:
            error_ellipse['semi_major_std'] = float(msg.std_dev_semi_major)
        
        if hasattr(msg, 'std_dev_semi_minor') and msg.std_dev_semi_minor is not None:
            error_ellipse['semi_minor_std'] = float(msg.std_dev_semi_minor)
        
        if hasattr(msg, 'orientation_semi_major') and msg.orientation_semi_major is not None:
            error_ellipse['orientation'] = float(msg.orientation_semi_major)
        
        if hasattr(msg, 'std_dev_latitude') and msg.std_dev_latitude is not None:
            error_ellipse['lat_std'] = float(msg.std_dev_latitude)
        
        if hasattr(msg, 'std_dev_longitude') and msg.std_dev_longitude is not None:
            error_ellipse['lon_std'] = float(msg.std_dev_longitude)
        
        if hasattr(msg, 'std_dev_altitude') and msg.std_dev_altitude is not None:
            error_ellipse['alt_std'] = float(msg.std_dev_altitude)
        
        self.position_error_ellipse = error_ellipse
    
    def _process_zda(self, msg):
        """Process ZDA message - Time & Date"""
        if (hasattr(msg, 'day') and hasattr(msg, 'month') and hasattr(msg, 'year') and
            msg.day and msg.month and msg.year):
            try:
                self.utc_date = f"{msg.year:04d}-{msg.month:02d}-{msg.day:02d}"
            except (ValueError, TypeError):
                pass
        
        if hasattr(msg, 'local_zone') and msg.local_zone is not None:
            self.local_zone_offset = msg.local_zone
    
    def _process_txt(self, msg):
        """Process TXT message - Text transmission"""
        if hasattr(msg, 'text'):
            logger.info(f"GPS TXT message: {msg.text}")
    
    def _convert_decimal(self, value):
        """Convert Decimal to float if needed."""
        if isinstance(value, decimal.Decimal):
            return float(value)
        return value
    
    def get_gps_data(self):
        """
        Get comprehensive GPS data from the u-blox 7 receiver.
        Returns a dictionary with all available GPS information.
        """
        with self.lock:
            return {
                # Basic position data
                'latitude': self._convert_decimal(self.latitude),
                'longitude': self._convert_decimal(self.longitude),
                'altitude': self._convert_decimal(self.altitude),
                'altitude_msl': self._convert_decimal(self.altitude_msl),
                'geoid_height': self._convert_decimal(self.geoid_height),
                
                # Speed and course
                'speed_knots': self._convert_decimal(self.speed_knots),
                'speed_kmh': self._convert_decimal(self.speed_kmh),
                'course': self._convert_decimal(self.course),
                'magnetic_variation': self._convert_decimal(self.magnetic_variation),
                'variation_direction': self.variation_direction,
                
                # Satellite information
                'satellites': self.satellites,
                'satellites_used': self.satellites_used,
                'satellites_in_view': self.satellites_in_view,
                'pdop': self._convert_decimal(self.pdop),
                'hdop': self._convert_decimal(self.hdop),
                'vdop': self._convert_decimal(self.vdop),
                
                # Accuracy and error estimates
                'lat_error': self._convert_decimal(self.lat_error),
                'lon_error': self._convert_decimal(self.lon_error),
                'alt_error': self._convert_decimal(self.alt_error),
                'position_error_ellipse': self.position_error_ellipse,
                'range_residuals': self.range_residuals,
                
                # Time and status
                'timestamp': self.timestamp,
                'utc_date': self.utc_date,
                'local_zone_offset': self.local_zone_offset,
                'fix_quality': self.fix_quality,
                'fix_mode': self.fix_mode,
                'selection_mode': self.selection_mode,
                'navigation_status': self.navigation_status,
                
                # Differential GPS
                'dgps_age': self._convert_decimal(self.dgps_age),
                'dgps_station_id': self.dgps_station_id,
                
                # Status flags
                'has_fix': self.fix_quality is not None and int(self.fix_quality) > 0,
                'running': self.running,
                'is_3d_fix': self.fix_mode == 3 if self.fix_mode else False,
                'is_differential': self.fix_quality == 2 if self.fix_quality else False,
            }

    def has_fix(self):
        """
        Check if the GPS has a fix.
        Returns True if the GPS has a valid fix, False otherwise.
        """
        with self.lock:
            return self.fix_quality is not None and int(self.fix_quality) > 0

    def get_satellite_summary(self):
        """
        Get a summary of satellite information.
        Returns a dictionary with satellite statistics.
        """
        with self.lock:
            summary = {
                'total_in_view': len(self.satellites_in_view),
                'total_used': len(self.satellites_used),
                'satellites_with_snr': 0,
                'average_snr': 0,
                'strongest_satellite': None,
                'weakest_satellite': None
            }
            
            if self.satellites_in_view:
                satellites_with_snr = [sat for sat in self.satellites_in_view if sat.get('snr') is not None]
                summary['satellites_with_snr'] = len(satellites_with_snr)
                
                if satellites_with_snr:
                    snr_values = [sat['snr'] for sat in satellites_with_snr]
                    summary['average_snr'] = sum(snr_values) / len(snr_values)
                    
                    strongest = max(satellites_with_snr, key=lambda x: x['snr'])
                    weakest = min(satellites_with_snr, key=lambda x: x['snr'])
                    
                    summary['strongest_satellite'] = {
                        'prn': strongest['prn'],
                        'snr': strongest['snr'],
                        'elevation': strongest.get('elevation'),
                        'azimuth': strongest.get('azimuth')
                    }
                    
                    summary['weakest_satellite'] = {
                        'prn': weakest['prn'],
                        'snr': weakest['snr'],
                        'elevation': weakest.get('elevation'),
                        'azimuth': weakest.get('azimuth')
                    }
            
            return summary

    def get_accuracy_summary(self):
        """
        Get a summary of accuracy and error estimates.
        Returns a dictionary with accuracy information.
        """
        with self.lock:
            accuracy = {
                'horizontal_accuracy': None,
                'vertical_accuracy': None,
                'position_accuracy': None,
                'has_error_estimates': False
            }
            
            # Calculate horizontal accuracy from HDOP if available
            if self.hdop is not None:
                # Rough estimate: HDOP * baseline_accuracy (assuming ~3-5m baseline)
                accuracy['horizontal_accuracy'] = self.hdop * 4.0
            
            # Use error estimates if available (more accurate)
            if self.lat_error is not None and self.lon_error is not None:
                import math
                accuracy['horizontal_accuracy'] = math.sqrt(self.lat_error**2 + self.lon_error**2)
                accuracy['has_error_estimates'] = True
            
            if self.alt_error is not None:
                accuracy['vertical_accuracy'] = self.alt_error
                accuracy['has_error_estimates'] = True
            
            # Calculate overall position accuracy
            if (accuracy['horizontal_accuracy'] is not None and 
                accuracy['vertical_accuracy'] is not None):
                import math
                accuracy['position_accuracy'] = math.sqrt(
                    accuracy['horizontal_accuracy']**2 + 
                    accuracy['vertical_accuracy']**2
                )
            elif accuracy['horizontal_accuracy'] is not None:
                accuracy['position_accuracy'] = accuracy['horizontal_accuracy']
            
            return accuracy 