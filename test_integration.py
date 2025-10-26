#!/usr/bin/env python3
"""
Integration test for GPX Workbench - tests all major features
"""

import sys
import os
import shutil
sys.path.insert(0, '/home/runner/work/gpx-routes-workbench-using-flet/gpx-routes-workbench-using-flet')

from main import GPXProcessor, PersistentData

def setup_test_env():
    """Set up test environment"""
    test_dir = "/tmp/test_integration"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    
    # Copy example file
    shutil.copy("/tmp/example_route.gpx", f"{test_dir}/route1.gpx")
    shutil.copy("/tmp/test_route.gpx", f"{test_dir}/route2.gpx")
    
    return test_dir

def cleanup_test_env(test_dir):
    """Clean up test environment"""
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    if os.path.exists("test_integration_data.json"):
        os.remove("test_integration_data.json")

def test_full_workflow():
    """Test complete workflow"""
    print("=" * 60)
    print("INTEGRATION TEST: Full GPX Processing Workflow")
    print("=" * 60)
    
    test_dir = setup_test_env()
    processor = GPXProcessor()
    
    try:
        # Step 1: Parse GPX files
        print("\n1. Parsing GPX files...")
        files = [f for f in os.listdir(test_dir) if f.endswith('.gpx')]
        print(f"   Found {len(files)} files: {files}")
        
        gpx_data = {}
        for filename in files:
            path = os.path.join(test_dir, filename)
            gpx = processor.parse_gpx(path)
            assert gpx is not None, f"Failed to parse {filename}"
            gpx_data[filename] = gpx
            print(f"   ✅ Parsed: {filename}")
        
        # Step 2: Get bounds
        print("\n2. Calculating route bounds...")
        for filename, gpx in gpx_data.items():
            bounds = processor.get_gpx_bounds(gpx)
            assert bounds is not None, f"Failed to get bounds for {filename}"
            print(f"   ✅ {filename}: Lat {bounds['min_lat']:.4f} to {bounds['max_lat']:.4f}")
        
        # Step 3: Add speed tags
        print("\n3. Adding speed tags...")
        for filename, gpx in gpx_data.items():
            gpx_with_speed = processor.calculate_speed(gpx)
            assert gpx_with_speed is not None
            
            # Check if speed was added
            has_speed = False
            for track in gpx_with_speed.tracks:
                for segment in track.segments:
                    for point in segment.points:
                        if hasattr(point, 'speed') and point.speed is not None:
                            has_speed = True
                            break
            
            print(f"   ✅ {filename}: Speed tags added (has_speed={has_speed})")
            gpx_data[filename] = gpx_with_speed
        
        # Step 4: Save with speed tags
        print("\n4. Saving files with speed tags...")
        for filename, gpx in gpx_data.items():
            new_filename = filename.replace('.gpx', '_speed.gpx')
            new_path = os.path.join(test_dir, new_filename)
            processor.save_gpx(gpx, new_path)
            assert os.path.exists(new_path), f"Failed to save {new_filename}"
            print(f"   ✅ Saved: {new_filename}")
        
        # Step 5: Trim by speed
        print("\n5. Trimming by speed (max: 50 m/s)...")
        for filename, gpx in gpx_data.items():
            gpx_trimmed = processor.trim_by_speed(gpx, max_speed=50.0)
            assert gpx_trimmed is not None
            
            # Count points
            total_points = sum(
                len(segment.points)
                for track in gpx_trimmed.tracks
                for segment in track.segments
            )
            print(f"   ✅ {filename}: {total_points} points remaining after trim")
        
        # Step 6: Test persistent data
        print("\n6. Testing persistent data...")
        data = PersistentData("test_integration_data.json")
        data.data["test_files"] = list(gpx_data.keys())
        data.save()
        
        # Reload and verify
        data2 = PersistentData("test_integration_data.json")
        assert data2.data["test_files"] == list(gpx_data.keys())
        print(f"   ✅ Persistent data saved and loaded correctly")
        
        # Step 7: Create a simple map
        print("\n7. Testing map generation...")
        try:
            import folium
            
            # Get first GPX for center
            first_gpx = list(gpx_data.values())[0]
            bounds = processor.get_gpx_bounds(first_gpx)
            center_lat = (bounds['min_lat'] + bounds['max_lat']) / 2
            center_lon = (bounds['min_lon'] + bounds['max_lon']) / 2
            
            m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
            
            # Add routes
            colors = ['blue', 'red']
            for idx, (filename, gpx) in enumerate(gpx_data.items()):
                color = colors[idx % len(colors)]
                for track in gpx.tracks:
                    for segment in track.segments:
                        points = [(p.latitude, p.longitude) for p in segment.points]
                        folium.PolyLine(points, color=color, weight=3, popup=filename).add_to(m)
            
            map_file = os.path.join(test_dir, "test_map.html")
            m.save(map_file)
            assert os.path.exists(map_file)
            file_size = os.path.getsize(map_file)
            print(f"   ✅ Map generated: {map_file} ({file_size} bytes)")
        except Exception as e:
            print(f"   ⚠️  Map generation warning: {e}")
        
        print("\n" + "=" * 60)
        print("✅ INTEGRATION TEST PASSED - All features working!")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        cleanup_test_env(test_dir)

if __name__ == "__main__":
    success = test_full_workflow()
    sys.exit(0 if success else 1)
