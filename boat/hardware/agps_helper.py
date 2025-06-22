#!/usr/bin/env python3
"""
A-GPS (Assisted GPS) Helper for u-blox GPS modules.
This module downloads assistance data from u-blox AssistNow servers
and injects it into the GPS module to dramatically reduce cold start time.
"""

import serial
import requests
import time
import logging
import struct
from datetime import datetime, timezone

logger = logging.getLogger("AGPSHelper")

class AGPSHelper:
    """
    Handles A-GPS assistance data for u-blox GPS modules.
    Downloads ephemeris, almanac, and time assistance data to speed up GPS fix.
    """
    
    # u-blox AssistNow Online servers
    ASSISTNOW_SERVERS = [
        "https://online-live1.services.u-blox.com",
        "https://online-live2.services.u-blox.com"
    ]
    
    # UBX protocol constants
    UBX_SYNC1 = 0xB5
    UBX_SYNC2 = 0x62
    UBX_CLASS_AID = 0x0B  # AssistNow Aiding class
    UBX_CLASS_CFG = 0x06  # Configuration class
    
    def __init__(self, port='/dev/ttyACM0', baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        
    def connect(self):
        """Connect to the GPS module."""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1
            )
            logger.info(f"Connected to GPS module on {self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to GPS: {str(e)}")
            return False
    
    def disconnect(self):
        """Disconnect from the GPS module."""
        if self.serial_conn:
            self.serial_conn.close()
            self.serial_conn = None
    
    def get_approximate_location(self):
        """
        Get approximate location from IP address.
        Returns: tuple (latitude, longitude) or None
        """
        try:
            ip_response = requests.get('https://ipapi.co/json/', timeout=5)
            if ip_response.status_code == 200:
                ip_data = ip_response.json()
                lat = ip_data.get('latitude')
                lon = ip_data.get('longitude')
                if lat and lon:
                    logger.info(f"Got approximate location from IP: {lat}, {lon}")
                    return float(lat), float(lon)
        except Exception as e:
            logger.warning(f"Could not get IP location: {str(e)}")
        return None
    
    def download_assistance_data(self, token=None, use_ip_location=True):
        """
        Download assistance data from u-blox AssistNow servers.
        
        Args:
            token: Optional authentication token for u-blox services
            use_ip_location: Use IP-based location for initial position estimate
        
        Returns:
            bytes: Raw assistance data or None if download failed
        """
        # Build request parameters
        params = {
            'gnss': 'gps,glo,gal,bds',  # GPS, GLONASS, Galileo, BeiDou
            'format': 'mga',  # Multiple GNSS Assistance format
            'datatype': 'eph,alm,aux'  # Ephemeris, Almanac, Auxiliary data
        }
        
        if token:
            params['token'] = token
        
        # Try to get approximate location from IP for better assistance
        if use_ip_location:
            location = self.get_approximate_location()
            if location:
                params['lat'] = str(location[0])
                params['lon'] = str(location[1])
                params['alt'] = '0'
                params['pacc'] = '10000'  # 10km accuracy
        
        # Try downloading from servers
        for server in self.ASSISTNOW_SERVERS:
            try:
                url = f"{server}/GetOnlineData.ashx"
                logger.info(f"Downloading assistance data from {server}...")
                
                response = requests.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.content
                    logger.info(f"Downloaded {len(data)} bytes of assistance data")
                    return data
                else:
                    logger.warning(f"Server returned status {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Failed to download from {server}: {str(e)}")
        
        logger.error("Failed to download assistance data from all servers")
        return None
    
    def inject_assistance_data(self, data):
        """
        Inject assistance data into the GPS module.
        
        Args:
            data: Raw assistance data bytes
            
        Returns:
            bool: True if injection successful
        """
        if not self.serial_conn or not data:
            return False
        
        try:
            # Send data in chunks to avoid overwhelming the module
            chunk_size = 512
            total_chunks = (len(data) + chunk_size - 1) // chunk_size
            
            logger.info(f"Injecting assistance data in {total_chunks} chunks...")
            
            for i in range(0, len(data), chunk_size):
                chunk = data[i:i + chunk_size]
                self.serial_conn.write(chunk)
                time.sleep(0.1)  # Small delay between chunks
                
                # Log progress
                chunk_num = i // chunk_size + 1
                if chunk_num % 10 == 0:
                    logger.info(f"Progress: {chunk_num}/{total_chunks} chunks")
            
            logger.info("Assistance data injection complete")
            return True
            
        except Exception as e:
            logger.error(f"Failed to inject assistance data: {str(e)}")
            return False
    
    def set_system_time(self):
        """
        Send accurate system time to GPS module to speed up fix.
        u-blox modules can use accurate time to narrow satellite search.
        """
        try:
            # Get current UTC time
            now = datetime.now(timezone.utc)
            
            # Build UBX-AID-INI message (Time and Position Aiding)
            # This gives the GPS a time hint to speed up acquisition
            msg_class = 0x0B  # AID class
            msg_id = 0x01     # INI message
            
            # Time accuracy: 10ms (10000 microseconds)
            time_acc = 10000
            
            # Build payload
            payload = struct.pack('<IIiII',
                0,  # Position ECEF X (0 = no position)
                0,  # Position ECEF Y
                0,  # Position ECEF Z
                0,  # Position accuracy (0 = no position)
                time_acc  # Time accuracy in microseconds
            )
            
            # Calculate week number and time of week
            gps_epoch = datetime(1980, 1, 6, tzinfo=timezone.utc)
            time_since_epoch = now - gps_epoch
            weeks = int(time_since_epoch.days / 7)
            tow_ms = int((time_since_epoch.seconds + 
                         time_since_epoch.days * 86400 -
                         weeks * 604800) * 1000)
            
            payload += struct.pack('<HH', weeks, 0)  # Week number
            payload += struct.pack('<I', tow_ms)  # Time of week in ms
            
            # Send UBX message
            self._send_ubx_message(msg_class, msg_id, payload)
            
            logger.info(f"Sent time assistance: GPS week {weeks}, TOW {tow_ms}ms")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set system time: {str(e)}")
            return False
    
    def set_approximate_position(self, latitude, longitude, accuracy_meters=10000):
        """
        Send approximate position to GPS module to speed up fix.
        
        Args:
            latitude: Latitude in degrees
            longitude: Longitude in degrees  
            accuracy_meters: Position accuracy in meters (default 10km)
        """
        try:
            # Convert lat/lon to ECEF coordinates
            import math
            
            # WGS84 parameters
            a = 6378137.0  # Earth's radius in meters
            e2 = 0.00669437999014  # First eccentricity squared
            
            lat_rad = math.radians(latitude)
            lon_rad = math.radians(longitude)
            
            N = a / math.sqrt(1 - e2 * math.sin(lat_rad)**2)
            
            x = N * math.cos(lat_rad) * math.cos(lon_rad)
            y = N * math.cos(lat_rad) * math.sin(lon_rad)
            z = N * (1 - e2) * math.sin(lat_rad)
            
            # Build UBX-AID-INI message with position
            msg_class = 0x0B  # AID class
            msg_id = 0x01     # INI message
            
            # Build payload with position
            payload = struct.pack('<iiiiI',
                int(x * 100),  # ECEF X in cm
                int(y * 100),  # ECEF Y in cm
                int(z * 100),  # ECEF Z in cm
                accuracy_meters * 100,  # Position accuracy in cm
                0  # Time accuracy (0 = no time)
            )
            
            # Send UBX message
            self._send_ubx_message(msg_class, msg_id, payload)
            
            logger.info(f"Sent position assistance: {latitude:.4f}, {longitude:.4f} (±{accuracy_meters}m)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set approximate position: {str(e)}")
            return False
    
    def _send_ubx_message(self, msg_class, msg_id, payload):
        """Send a UBX protocol message to the GPS module."""
        # Build message
        msg = bytes([self.UBX_SYNC1, self.UBX_SYNC2, msg_class, msg_id])
        msg += struct.pack('<H', len(payload))
        msg += payload
        
        # Calculate checksum
        ck_a = 0
        ck_b = 0
        for byte in msg[2:]:  # Skip sync bytes
            ck_a = (ck_a + byte) & 0xFF
            ck_b = (ck_b + ck_a) & 0xFF
        
        msg += bytes([ck_a, ck_b])
        
        # Send message
        self.serial_conn.write(msg)
    
    def perform_quick_assist(self):
        """
        Perform a quick time and position assist without downloading data.
        This can reduce cold start time from 12+ minutes to 1-2 minutes.
        
        Returns:
            bool: True if successful
        """
        logger.info("Starting quick GPS assist...")
        
        # Connect to GPS
        if not self.connect():
            return False
        
        try:
            # Set system time first
            if not self.set_system_time():
                logger.warning("Failed to set system time")
            else:
                time.sleep(0.5)
            
            # Try to set approximate position from IP
            location = self.get_approximate_location()
            if location:
                self.set_approximate_position(location[0], location[1])
                time.sleep(0.5)
            
            logger.info("Quick GPS assist completed")
            return True
            
        finally:
            self.disconnect()
    
    def perform_agps_update(self, token=None):
        """
        Perform a complete A-GPS update.
        
        Args:
            token: Optional u-blox service token
            
        Returns:
            bool: True if successful
        """
        logger.info("Starting A-GPS update...")
        
        # If no token provided, just do quick assist
        if not token:
            logger.warning("No u-blox token provided. Using quick assist only.")
            return self.perform_quick_assist()
        
        # Download assistance data
        data = self.download_assistance_data(token)
        if not data:
            logger.error("Failed to download assistance data, falling back to quick assist")
            return self.perform_quick_assist()
        
        # Connect to GPS
        if not self.connect():
            return False
        
        try:
            # Set system time first
            self.set_system_time()
            time.sleep(0.5)
            
            # Inject assistance data
            if not self.inject_assistance_data(data):
                return False
            
            logger.info("A-GPS update completed successfully")
            return True
            
        finally:
            self.disconnect()
    
    def clear_assistance_data(self):
        """
        Clear all assistance data from GPS module (forces cold start).
        Useful for testing cold start performance.
        """
        if not self.connect():
            return False
        
        try:
            # UBX-AID-INI with flags to clear all data
            msg_class = 0x0B  # AID class
            msg_id = 0x01     # INI message
            
            # Flags: Clear all assistance data
            flags = 0x01  # Clear ephemeris
            flags |= 0x02  # Clear almanac
            flags |= 0x04  # Clear health
            flags |= 0x08  # Clear position
            flags |= 0x10  # Clear clock drift
            flags |= 0x20  # Clear oscillator parameters
            flags |= 0x40  # Clear UTC parameters
            flags |= 0x80  # Clear ionosphere parameters
            
            payload = struct.pack('<I', flags)
            self._send_ubx_message(msg_class, msg_id, payload)
            
            logger.info("Cleared all GPS assistance data")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear assistance data: {str(e)}")
            return False
        finally:
            self.disconnect()


def main():
    """Example usage of AGPSHelper."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("\nGPS Quick Assist Test")
    print("=" * 50)
    print("This will send time and approximate position to your GPS")
    print("to speed up cold start from 12+ minutes to 1-2 minutes.")
    print()
    
    # Create helper
    agps = AGPSHelper()
    
    # Perform quick assist (no token needed)
    success = agps.perform_quick_assist()
    
    if success:
        print("\n✓ GPS quick assist successful!")
        print("Your GPS should now get a fix much faster (1-2 minutes)")
        print("\nFor even faster fixes (under 30 seconds), you need:")
        print("- A u-blox AssistNow token from https://www.u-blox.com/")
        print("- Then run: agps.perform_agps_update(token='your_token')")
    else:
        print("\n✗ GPS quick assist failed")
        print("Check the logs for details")


if __name__ == "__main__":
    main() 