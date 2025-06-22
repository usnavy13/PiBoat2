#!/usr/bin/env python3
"""
Script to manually set compass calibration values
Use this if you have calibration values from a previous calibration session
"""

import sys
from pathlib import Path

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from boat.hardware.compass_handler import CompassHandler

def set_manual_calibration():
    """Set calibration values manually."""
    print("🧭 MANUAL COMPASS CALIBRATION SETUP")
    print("=" * 50)
    print()
    
    # Your successful calibration values:
    # X-axis offset: 10.00
    # Y-axis offset: -7.00
    
    print("Enter your calibration values from successful calibration:")
    print("(From your calibration: X=10.00, Y=-7.00)")
    print()
    
    try:
        x_offset = float(input("X-axis offset: ") or "10.00")
        y_offset = float(input("Y-axis offset: ") or "-7.00")
        declination = float(input("Magnetic declination (degrees, 0 if unknown): ") or "0")
        
        print(f"\nSetting calibration: X={x_offset}, Y={y_offset}, declination={declination}°")
        
        # Create compass handler and set calibration
        compass = CompassHandler()
        compass.set_calibration(x_offset, y_offset, declination)
        
        print("✅ Calibration values saved!")
        print(f"📁 Saved to: {compass.calibration_file}")
        print()
        print("These values will now be automatically loaded every time you use the compass.")
        
        # Test it
        print("\n🧪 Testing saved calibration...")
        if compass.start():
            import time
            time.sleep(2)
            
            for i in range(3):
                data = compass.get_compass_data()
                print(f"Test reading {i+1}: {data['heading']:.1f}° (quality: {data['data_quality']:.2f})")
                time.sleep(1)
            
            compass.stop()
        else:
            print("⚠️  Could not test compass (no sensor connected)")
            
        print("\n🎯 Your compass is now permanently calibrated!")
        
    except ValueError:
        print("❌ Invalid input. Please enter numeric values.")
    except Exception as e:
        print(f"❌ Error: {e}")

def show_current_calibration():
    """Show current calibration status."""
    print("\n📊 CURRENT CALIBRATION STATUS")
    print("-" * 40)
    
    compass = CompassHandler()
    info = compass.get_calibration_info()
    
    if info:
        print(f"X-axis offset: {info['hard_iron_offset_x']:.2f}")
        print(f"Y-axis offset: {info['hard_iron_offset_y']:.2f}")
        print(f"Magnetic declination: {info['declination']:.2f}°")
        print(f"Calibration age: {info['calibration_age_days']:.1f} days")
        print(f"Deviation table entries: {info['deviation_entries']}")
        print(f"Calibration file: {info['calibration_file']}")
        
        if info['calibration_age_days'] > 30:
            print("\n⚠️  Calibration is older than 30 days - consider recalibrating")
        elif info['calibration_age_days'] == float('inf'):
            print("\n❌ No calibration found - please calibrate compass")
        else:
            print("\n✅ Calibration is current and valid")
    else:
        print("❌ Could not read calibration information")

if __name__ == "__main__":
    while True:
        print("\nCOMPASS CALIBRATION MANAGER")
        print("=" * 30)
        print("1. Set manual calibration values")
        print("2. Show current calibration status")
        print("3. Exit")
        print()
        
        choice = input("Choose option (1-3): ").strip()
        
        if choice == "1":
            set_manual_calibration()
        elif choice == "2":
            show_current_calibration()
        elif choice == "3":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")
        
        print("\n" + "="*50 + "\n") 