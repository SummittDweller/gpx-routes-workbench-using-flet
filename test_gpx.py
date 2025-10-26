#!/usr/bin/env python3
"""
Test script for GPX processing functionality
"""

import sys
import os

# Add the main directory to path
sys.path.insert(0, '/home/runner/work/gpx-routes-workbench-using-flet/gpx-routes-workbench-using-flet')

from main import GPXProcessor, PersistentData
import shutil

def test_persistent_data():
    """Test persistent data management"""
    print("Testing Persistent Data...")
    
    # Clean up any existing test data
    if os.path.exists("test_app_data.json"):
        os.remove("test_app_data.json")
    
    data = PersistentData("test_app_data.json")
    assert data.data is not None
    assert "temp_dir" in data.data
    
    # Modify and save
    data.data["test_key"] = "test_value"
    data.save()
    
    # Load again
    data2 = PersistentData("test_app_data.json")
    assert data2.data["test_key"] == "test_value"
    
    # Clean up
    os.remove("test_app_data.json")
    
    print("✅ Persistent Data test passed")


def test_gpx_processor():
    """Test GPX processing"""
    print("\nTesting GPX Processor...")
    
    processor = GPXProcessor()
    
    # Test parsing
    gpx = processor.parse_gpx("/tmp/test_route.gpx")
    assert gpx is not None
    print("✅ GPX parsing works")
    
    # Test bounds
    bounds = processor.get_gpx_bounds(gpx)
    assert bounds is not None
    assert "min_lat" in bounds
    print(f"✅ GPX bounds: {bounds}")
    
    # Test speed calculation
    gpx_with_speed = processor.calculate_speed(gpx)
    assert gpx_with_speed is not None
    print("✅ Speed calculation works")
    
    # Save to temp file
    temp_output = "/tmp/test_output.gpx"
    processor.save_gpx(gpx_with_speed, temp_output)
    assert os.path.exists(temp_output)
    print("✅ GPX saving works")
    
    # Test trimming
    gpx_trimmed = processor.trim_by_speed(gpx_with_speed, max_speed=50.0)
    assert gpx_trimmed is not None
    print("✅ Speed-based trimming works")
    
    # Clean up
    os.remove(temp_output)
    
    print("✅ All GPX Processor tests passed")


def test_temp_directory():
    """Test temp directory creation"""
    print("\nTesting temp directory...")
    
    test_dir = "/tmp/test_gpx_routes"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    
    os.makedirs(test_dir, exist_ok=True)
    assert os.path.exists(test_dir)
    print("✅ Temp directory creation works")
    
    # Clean up
    shutil.rmtree(test_dir)


if __name__ == "__main__":
    print("Running GPX Workbench Tests...\n")
    print("=" * 50)
    
    try:
        test_persistent_data()
        test_gpx_processor()
        test_temp_directory()
        
        print("\n" + "=" * 50)
        print("✅ All tests passed!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
