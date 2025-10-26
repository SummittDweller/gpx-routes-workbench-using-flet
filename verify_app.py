#!/usr/bin/env python3
"""
Quick verification that the app can be imported and initialized
"""

import sys
import os

# Test imports
print("Testing imports...")
try:
    import flet as ft
    print("✅ Flet imported")
    import gpxpy
    print("✅ gpxpy imported")
    import folium
    print("✅ folium imported")
    import requests
    print("✅ requests imported")
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

# Test main module imports
sys.path.insert(0, '/home/runner/work/gpx-routes-workbench-using-flet/gpx-routes-workbench-using-flet')

try:
    from main import PersistentData, GPXProcessor, GPXWorkbenchApp
    print("✅ Main module imported successfully")
except ImportError as e:
    print(f"❌ Main module import error: {e}")
    sys.exit(1)

# Test initialization of classes (without UI)
try:
    pd = PersistentData("test_verify_data.json")
    print(f"✅ PersistentData initialized: {list(pd.data.keys())}")
    
    proc = GPXProcessor()
    print("✅ GPXProcessor initialized")
    
    # Clean up
    if os.path.exists("test_verify_data.json"):
        os.remove("test_verify_data.json")
    
except Exception as e:
    print(f"❌ Initialization error: {e}")
    sys.exit(1)

print("\n" + "=" * 50)
print("✅ All verification checks passed!")
print("The application is ready to run with: python main.py")
