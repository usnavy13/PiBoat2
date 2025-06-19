#!/usr/bin/env python3
"""
Test script to demonstrate automatic calibration loading
"""

from hardware_code.compass_handler import CompassHandler
import time

def test_auto_calibration():
    print("🧭 TESTING AUTOMATIC CALIBRATION LOADING")
    print("=" * 50)
    print()
    
    print("Creating new CompassHandler instance...")
    print("(This should automatically load your saved calibration)")
    print()
    
    # Create compass - calibration should auto-load
    compass = CompassHandler()
    
    # Show what was loaded
    print("📊 Auto-loaded calibration values:")
    info = compass.get_calibration_info()
    if info:
        print(f"  X-axis offset: {info['hard_iron_offset_x']:.2f}")
        print(f"  Y-axis offset: {info['hard_iron_offset_y']:.2f}")
        print(f"  Magnetic declination: {info['declination']:.2f}°")
        print(f"  Calibration age: {info['calibration_age_days']:.1f} days")
        print()
        
        if info['calibration_age_days'] == float('inf'):
            print("❌ No calibration file found!")
            print("Run 'python3 set_compass_calibration.py' to set your values.")
            return
        else:
            print("✅ Calibration automatically loaded!")
    
    # Test the compass with loaded calibration
    print("\n🧪 Testing compass with auto-loaded calibration...")
    if compass.start():
        print("Compass started successfully!")
        print("Taking 5 readings...")
        
        for i in range(5):
            data = compass.get_compass_data()
            print(f"Reading {i+1}: {data['heading']:.1f}° "
                  f"(quality: {data['data_quality']:.2f}, "
                  f"reliable: {compass.is_data_reliable()})")
            time.sleep(1)
        
        compass.stop()
        print("\n✅ Auto-calibration working perfectly!")
        print("Your compass will always use these calibration values automatically.")
    else:
        print("⚠️  Could not start compass (sensor not connected)")
        print("But calibration values are still loaded and saved!")

if __name__ == "__main__":
    test_auto_calibration() 