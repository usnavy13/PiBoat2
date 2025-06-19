#!/usr/bin/env python3
"""
Simple Compass Calibration Script for Marine Use
"""

import time
import math
from hardware_code.compass_handler import CompassHandler

def calibrate_compass_basic():
    """Perform basic compass calibration."""
    print("🧭 COMPASS CALIBRATION")
    print("=" * 50)
    
    # Initialize compass
    print("Initializing compass...")
    compass = CompassHandler()
    
    if not compass.start():
        print("❌ Failed to initialize compass!")
        return
    
    print("✅ Compass connected")
    time.sleep(2)
    
    # Show initial reading
    data = compass.get_compass_data()
    print(f"Current heading: {data['heading']:.1f}°")
    print()
    
    # Instructions
    print("📋 CALIBRATION PROCEDURE:")
    print("1. Take boat to open water away from metal structures")
    print("2. Turn off radar, fish finder, and other electronics")
    print("3. When ready, you'll rotate boat slowly 360° in 60 seconds")
    print("4. Maintain steady speed throughout rotation")
    print()
    
    input("Press Enter when ready to start calibration...")
    
    print("\n🔄 Starting calibration countdown...")
    for i in range(3, 0, -1):
        print(f"   {i}...")
        time.sleep(1)
    
    print("\n🚤 START ROTATION NOW - Complete 360° in 60 seconds!")
    print("=" * 50)
    
    # Perform calibration
    success, x_offset, y_offset, message = compass.calibrate_compass(duration_seconds=60)
    
    print("\n" + "=" * 50)
    
    if success:
        print("✅ CALIBRATION SUCCESSFUL!")
        print(f"X-axis offset: {x_offset:.2f}")
        print(f"Y-axis offset: {y_offset:.2f}")
        print("\nThese offsets are now active.")
        
        # Test readings
        print("\n🧪 Testing calibrated compass:")
        for i in range(3):
            data = compass.get_compass_data()
            print(f"Reading {i+1}: {data['heading']:.1f}° (quality: {data['data_quality']:.2f})")
            time.sleep(1)
    else:
        print(f"❌ CALIBRATION FAILED: {message}")
    
    compass.stop()

def quick_compass_test():
    """Quick test of compass readings."""
    print("\n🔍 COMPASS TEST")
    print("-" * 30)
    
    compass = CompassHandler()
    if not compass.start():
        print("❌ Failed to initialize compass!")
        return
    
    print("Taking 10 readings...")
    headings = []
    
    for i in range(10):
        data = compass.get_compass_data()
        if data['connected']:
            headings.append(data['heading'])
            print(f"Reading {i+1}: {data['heading']:.1f}° (quality: {data['data_quality']:.2f})")
        time.sleep(0.5)
    
    if headings:
        avg_heading = sum(headings) / len(headings)
        # Calculate standard deviation
        variance = sum((h - avg_heading)**2 for h in headings) / len(headings)
        std_dev = math.sqrt(variance)
        
        print(f"\nResults:")
        print(f"Average heading: {avg_heading:.1f}°")
        print(f"Stability: ±{std_dev:.1f}°")
        
        if std_dev < 2:
            print("✅ Excellent stability!")
        elif std_dev < 5:
            print("⚠️  Good stability")
        else:
            print("❌ Poor stability - consider recalibration")
    
    compass.stop()

def main():
    print("BOAT COMPASS CALIBRATION")
    print("=" * 40)
    print()
    print("Choose an option:")
    print("1. Calibrate compass (main calibration)")
    print("2. Test compass accuracy")
    print("3. Exit")
    print()
    
    while True:
        choice = input("Enter choice (1-3): ").strip()
        
        if choice == "1":
            calibrate_compass_basic()
        elif choice == "2":
            quick_compass_test()
        elif choice == "3":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")
        
        print("\n" + "="*40 + "\n")

if __name__ == "__main__":
    main() 