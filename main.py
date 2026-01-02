#!/usr/bin/env python3
"""
GPX Routes Workbench - A Flet app for processing iPhone Health exported GPX routes
"""

import flet as ft
import logging
import json
import os
import shutil
import zipfile
import webbrowser
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import gpxpy
import gpxpy.gpx
import requests


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('gpx_workbench.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class PersistentData:
    """Manages persistent application data"""
    
    def __init__(self, data_file: str = "app_data.json"):
        self.data_file = data_file
        self.data = self.load()
    
    def load(self) -> Dict:
        """Load data from JSON file"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading data: {e}")
                return self._get_default_data()
        return self._get_default_data()
    
    def save(self):
        """Save data to JSON file"""
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.data, f, indent=2)
            logger.info("Data saved successfully")
        except Exception as e:
            logger.error(f"Error saving data: {e}")
    
    def _get_default_data(self) -> Dict:
        """Return default data structure"""
        return {
            "temp_dir": "temp_gpx_routes",
            "selected_files": [],
            "hikes_api_url": "",
            "last_export_date": None
        }


class GPXProcessor:
    """Handles GPX file processing operations"""
    
    @staticmethod
    def parse_gpx(file_path: str, auto_add_speed: bool = False) -> Optional[gpxpy.gpx.GPX]:
        """Parse a GPX file and optionally add speed tags automatically"""
        try:
            with open(file_path, 'r') as gpx_file:
                gpx = gpxpy.parse(gpx_file)
                logger.info(f"Successfully parsed {file_path}")
                
                # Automatically add speed and distance tags if requested and not present
                if auto_add_speed and not GPXProcessor.has_speed_and_distance_tags(gpx):
                    logger.info(f"Auto-adding speed tags to {file_path}")
                    gpx = GPXProcessor.calculate_speed(gpx)
                    # Save the updated file
                    GPXProcessor.save_gpx(gpx, file_path)
                    logger.info(f"Speed tags auto-saved to {file_path}")
                
                return gpx
        except Exception as e:
            logger.error(f"Error parsing GPX file {file_path}: {e}")
            return None
    
    @staticmethod
    def has_speed_and_distance_tags(gpx: gpxpy.gpx.GPX) -> bool:
        """Check if GPX already has speed and distance-to-next tags"""
        for track in gpx.tracks:
            for segment in track.segments:
                if len(segment.points) > 1:
                    # Check first few points for speed and distance-to-next
                    for i, point in enumerate(segment.points[:3]):  # Check first 3 points
                        # Check for speed (should be present for points after the first)
                        if i > 0:
                            has_speed = point.speed is not None
                            # Also check in extensions
                            if not has_speed and hasattr(point, 'extensions') and point.extensions:
                                for ext in point.extensions:
                                    if hasattr(ext, 'tag') and 'speed' in ext.tag:
                                        has_speed = True
                                        break
                            if not has_speed:
                                return False
                        
                        # Check for distance-to-next (should be present for all but last point)
                        if i < len(segment.points) - 1:
                            has_distance = False
                            if hasattr(point, 'extensions') and point.extensions:
                                for ext in point.extensions:
                                    if hasattr(ext, 'tag') and 'distance-to-next' in ext.tag:
                                        has_distance = True
                                        break
                            if not has_distance:
                                return False
        return True
    
    @staticmethod
    def get_max_speed_and_distance(gpx: gpxpy.gpx.GPX) -> tuple[Optional[float], Optional[float]]:
        """Get maximum speed (m/s) and maximum distance-to-next (meters) from GPX file
        Returns: (max_speed_ms, max_distance_meters) or (None, None) if no tags found"""
        max_speed = None
        max_distance = None
        
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    # Check for speed in both attribute and extensions
                    speed_value = None
                    if point.speed is not None:
                        speed_value = point.speed
                    elif hasattr(point, 'extensions') and point.extensions:
                        for ext in point.extensions:
                            if hasattr(ext, 'tag') and 'speed' in ext.tag:
                                try:
                                    speed_value = float(ext.text)
                                    break
                                except (ValueError, AttributeError):
                                    pass
                    
                    if speed_value is not None:
                        if max_speed is None or speed_value > max_speed:
                            max_speed = speed_value
                    
                    # Check for distance-to-next in extensions
                    if hasattr(point, 'extensions') and point.extensions:
                        for ext in point.extensions:
                            if hasattr(ext, 'tag') and 'distance-to-next' in ext.tag:
                                try:
                                    distance = float(ext.text)
                                    if max_distance is None or distance > max_distance:
                                        max_distance = distance
                                except (ValueError, AttributeError):
                                    pass
        
        return max_speed, max_distance
    
    @staticmethod
    def calculate_speed(gpx: gpxpy.gpx.GPX) -> gpxpy.gpx.GPX:
        """Add speed tags and distance-to-next extension to GPX trackpoints"""
        for track in gpx.tracks:
            for segment in track.segments:
                points = segment.points
                for i in range(len(points)):
                    curr_point = points[i]
                    
                    # Calculate speed from previous point (for points after the first)
                    if i > 0:
                        prev_point = points[i - 1]
                        
                        # Calculate distance and time
                        distance = curr_point.distance_3d(prev_point)
                        if distance is None:
                            distance = curr_point.distance_2d(prev_point)
                        
                        time_diff = (curr_point.time - prev_point.time).total_seconds() if curr_point.time and prev_point.time else 0
                        
                        # Calculate speed (m/s)
                        if time_diff > 0 and distance is not None:
                            speed = distance / time_diff
                            # Add speed as extension (m/s)
                            curr_point.speed = speed
                    
                    # Calculate distance to next point (for all points except the last)
                    if i < len(points) - 1:
                        next_point = points[i + 1]
                        
                        # Calculate distance to next point
                        distance_to_next = next_point.distance_3d(curr_point)
                        if distance_to_next is None:
                            distance_to_next = next_point.distance_2d(curr_point)
                        
                        # Add distance-to-next as extension
                        if distance_to_next is not None:
                            # Create extensions element if it doesn't exist
                            if not hasattr(curr_point, 'extensions') or curr_point.extensions is None:
                                curr_point.extensions = []
                            
                            # Create the extension element
                            from xml.etree import ElementTree as ET
                            distance_elem = ET.Element('distance-to-next')
                            distance_elem.text = str(distance_to_next)
                            curr_point.extensions.append(distance_elem)
        
        logger.info("Speed tags and distance-to-next extensions added to GPX")
        return gpx
    
    @staticmethod
    def trim_by_speed(gpx: gpxpy.gpx.GPX, max_speed: float = 50.0) -> gpxpy.gpx.GPX:
        """Remove points with excessive speed (max_speed in m/s, UI uses mph)
        If 5 or more consecutive points exceed threshold, trim those and all following points."""
        removed_count = 0
        for track in gpx.tracks:
            for segment in track.segments:
                points_to_keep = []
                consecutive_high_speed = 0
                trim_all_remaining = False
                
                for i, point in enumerate(segment.points):
                    # If we've decided to trim all remaining points, skip this point
                    if trim_all_remaining:
                        removed_count += 1
                        continue
                    
                    if hasattr(point, 'speed') and point.speed is not None:
                        if point.speed > max_speed:
                            consecutive_high_speed += 1
                            
                            # Check if we've hit 5 consecutive high-speed points
                            if consecutive_high_speed >= 5:
                                # Remove the last 4 points we just added (the previous consecutive high-speed points)
                                points_removed_from_keep = min(4, len(points_to_keep))
                                if points_removed_from_keep > 0:
                                    points_to_keep = points_to_keep[:-points_removed_from_keep]
                                    removed_count += points_removed_from_keep
                                
                                # Mark to trim this point and all remaining
                                trim_all_remaining = True
                                removed_count += 1
                                logger.info(f"Found 5 consecutive high-speed points at index {i}, trimming remainder of route")
                            else:
                                removed_count += 1
                        else:
                            # Speed is within threshold, reset consecutive counter
                            consecutive_high_speed = 0
                            points_to_keep.append(point)
                    else:
                        # No speed data, keep the point and reset counter
                        consecutive_high_speed = 0
                        points_to_keep.append(point)
                
                segment.points = points_to_keep
        
        logger.info(f"Trimmed {removed_count} points with excessive speed")
        return gpx
    
    @staticmethod
    def save_gpx(gpx: gpxpy.gpx.GPX, file_path: str):
        """Save GPX to file"""
        try:
            with open(file_path, 'w') as f:
                f.write(gpx.to_xml())
            logger.info(f"GPX saved to {file_path}")
        except Exception as e:
            logger.error(f"Error saving GPX file: {e}")
    
    @staticmethod
    def get_gpx_bounds(gpx: gpxpy.gpx.GPX) -> Optional[Dict]:
        """Get bounding box of GPX route"""
        bounds = gpx.get_bounds()
        if bounds:
            return {
                'min_lat': bounds.min_latitude,
                'max_lat': bounds.max_latitude,
                'min_lon': bounds.min_longitude,
                'max_lon': bounds.max_longitude
            }
        return None


class GPXWorkbenchApp:
    """Main application class"""
    
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "GPX Routes Workbench"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.padding = 20
        self.page.scroll = "auto"
        
        self.persistent_data = PersistentData()
        self.processor = GPXProcessor()
        self.temp_dir = self.persistent_data.data["temp_dir"]
        
        # Ensure temp directory exists
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # File selection state
        self.selected_files: List[str] = []
        self.file_checkboxes: Dict[str, ft.Checkbox] = {}
        
        # UI Controls
        self.files_list_view = ft.ListView(expand=True, spacing=10, padding=10)
        self.status_text = ft.Text("Ready", size=14)
        self.map_output = ft.Text("", size=12)
        
        # Progress indicators for export extraction
        self.progress_ring = ft.ProgressRing(visible=False)
        self.progress_bar = ft.ProgressBar(visible=False, width=400)
        self.progress_text = ft.Text("", size=14, weight=ft.FontWeight.BOLD, visible=False)
        
        # Default to 30 days ago for cutoff date
        default_date = datetime.now() - timedelta(days=30)
        self.selected_cutoff_date = default_date
        
        # Initialize pickers (will be added to overlay in build_ui)
        self.pick_files_dialog = ft.FilePicker(on_result=self.on_files_selected)
        self.cutoff_date_picker = ft.DatePicker(
            on_change=self.on_cutoff_date_changed,
            on_dismiss=lambda e: None,
        )
        
        # Find the latest export.zip file (including numbered versions)
        downloads_dir = Path.home() / "Downloads"
        export_file = self.find_latest_export_file(downloads_dir)
        
        existing_gpx_count = 0
        if os.path.exists(self.temp_dir):
            existing_gpx_count = len([f for f in os.listdir(self.temp_dir) if f.endswith('.gpx')])
        
        self.has_export_zip = export_file is not None and existing_gpx_count == 0
        self.export_zip_path = export_file
        self.existing_files_count = existing_gpx_count
        logger.info(f"Export.zip check: found={export_file}, has_export_zip={self.has_export_zip}, existing_files={existing_gpx_count}")
        
        # Build UI first
        self.build_ui()
        
        # Force page update to render the UI including progress indicator
        self.page.update()
        
        # If export.zip found, extract it immediately (UI is now ready)
        if self.has_export_zip:
            self.auto_extract_health_export()
    
    def find_latest_export_file(self, downloads_dir: Path) -> Optional[Path]:
        """Find the latest export.zip file, checking for numbered versions like 'export 2.zip', 'export 3.zip', etc."""
        import re
        
        if not downloads_dir.exists():
            logger.info(f"Downloads directory does not exist: {downloads_dir}")
            return None
        
        # Pattern to match export.zip, export 2.zip, export 3.zip, etc.
        pattern = re.compile(r'^export(?: (\d+))?\.zip$', re.IGNORECASE)
        
        matches = []
        for file in downloads_dir.iterdir():
            if file.is_file():
                match = pattern.match(file.name)
                if match:
                    # Extract number (0 for plain export.zip, N for export N.zip)
                    number = int(match.group(1)) if match.group(1) else 0
                    matches.append((number, file))
                    logger.info(f"Found export file candidate: {file.name} (number={number})")
        
        if not matches:
            logger.info("No export files found in Downloads")
            return None
        
        # Return the file with the highest number
        matches.sort(reverse=True)
        latest_file = matches[0][1]
        logger.info(f"Selected export file: {latest_file.name} (from {len(matches)} candidates)")
        return latest_file
    
    def parse_export_xml_for_activities(self, extract_dir):
        """Parse Export.xml to extract workout activity types and associate them with GPX files"""
        import xml.etree.ElementTree as ET
        from datetime import datetime
        
        export_xml_path = extract_dir / "apple_health_export" / "Export.xml"
        
        if not export_xml_path.exists():
            logger.warning("Export.xml not found in health export")
            return {}
        
        try:
            logger.info("Parsing Export.xml for workout activity types...")
            tree = ET.parse(export_xml_path)
            root = tree.getroot()
            
            # Dictionary to store activity types by workout date/time
            workout_activities = {}
            
            # Find all Workout elements
            for workout in root.findall('.//Workout'):
                workout_type = workout.get('workoutActivityType', '')
                start_date = workout.get('startDate', '')
                
                if workout_type and start_date:
                    # Parse the start date to match with GPX file naming
                    try:
                        # Example startDate: "2025-10-10 14:40:23 -0500"
                        dt = datetime.strptime(start_date.split(' ')[0] + ' ' + start_date.split(' ')[1], '%Y-%m-%d %H:%M:%S')
                        
                        # Convert activity type to friendly name
                        activity_name = self.convert_activity_type(workout_type)
                        
                        # Store by date/time key for matching with GPX files
                        date_key = dt.strftime('%Y-%m-%d_%H.%M')
                        workout_activities[date_key] = activity_name
                        
                        logger.debug(f"Found workout: {date_key} -> {activity_name} ({workout_type})")
                        
                    except Exception as e:
                        logger.warning(f"Could not parse workout date {start_date}: {e}")
            
            logger.info(f"Found {len(workout_activities)} workout activities in Export.xml")
            return workout_activities
            
        except Exception as e:
            logger.error(f"Error parsing Export.xml: {e}")
            return {}
    
    def convert_activity_type(self, workout_type):
        """Convert Apple Health workout activity type to friendly name"""
        activity_mapping = {
            'HKWorkoutActivityTypeWalking': 'Walking',
            'HKWorkoutActivityTypeRunning': 'Running', 
            'HKWorkoutActivityTypeCycling': 'Biking',
            'HKWorkoutActivityTypeHiking': 'Hiking',
            'HKWorkoutActivityTypeSwimming': 'Swimming',
            'HKWorkoutActivityTypeYoga': 'Yoga',
            'HKWorkoutActivityTypeOther': 'Other',
            # Add more mappings as needed
        }
        
        return activity_mapping.get(workout_type, 'Walking')  # Default to Walking
    
    def match_gpx_to_activity(self, gpx_filename, workout_activities):
        """Match a GPX filename to its activity type using the workout activities dict"""
        import re
        
        # Extract date/time from GPX filename: route_2025-10-10_2.40pm.gpx
        match = re.match(r'route_(\d{4}-\d{2}-\d{2})_(\d{1,2})\.(\d{2})(am|pm)\.gpx', gpx_filename)
        
        if match:
            date_part, hour, minute, period = match.groups()
            hour = int(hour)
            
            # Convert 12-hour to 24-hour format
            if period == 'pm' and hour != 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0
            
            # Create key to match workout_activities
            date_key = f"{date_part}_{hour:02d}.{minute}"
            
            # Try exact match first, then try nearby times (within 5 minutes)
            if date_key in workout_activities:
                return workout_activities[date_key]
            
            # Try nearby times (GPX file times might be slightly different from workout start times)
            base_time = datetime.strptime(f"{date_part} {hour:02d}:{minute}", '%Y-%m-%d %H:%M')
            
            for key, activity in workout_activities.items():
                try:
                    workout_time = datetime.strptime(key, '%Y-%m-%d_%H.%M')
                    time_diff = abs((base_time - workout_time).total_seconds())
                    
                    # If within 5 minutes, consider it a match
                    if time_diff <= 300:  # 5 minutes
                        logger.info(f"Matched {gpx_filename} to {activity} (time diff: {time_diff:.0f}s)")
                        return activity
                except:
                    continue
        
        logger.warning(f"Could not match {gpx_filename} to any workout activity")
        return 'Walking'  # Default fallback
    
    def auto_extract_health_export(self):
        """Automatically check for and extract export.zip from Downloads folder"""
        try:
            # Check if GPX files already exist in temp directory
            if os.path.exists(self.temp_dir):
                existing_gpx = [f for f in os.listdir(self.temp_dir) if f.endswith('.gpx')]
                if existing_gpx:
                    logger.info(f"Skipping auto-extraction: {len(existing_gpx)} GPX files already exist in temp directory")
                    return
            
            # Use the export file path found during initialization
            if not self.export_zip_path or not self.export_zip_path.exists():
                logger.info("No export.zip found in Downloads folder")
                return
            
            downloads_path = self.export_zip_path
            logger.info(f"Found export file at {downloads_path}")
            
            # Show progress indicator
            filename = downloads_path.name
            self.progress_container.visible = True
            self.progress_ring.visible = True
            self.progress_text.visible = True
            self.progress_text.value = f"📦 Found {filename} in Downloads - extracting..."
            self.update_status(f"📦 Found {filename} in Downloads - extracting...")
            self.page.update()
            time.sleep(0.1)  # Give UI time to render
            
            # Extract to a temporary location
            extract_dir = Path(self.temp_dir) / "health_export_temp"
            
            # Remove old extraction if exists
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            
            logger.info("Extracting export.zip...")
            self.progress_text.value = f"📂 Extracting {filename}..."
            self.update_status(f"📂 Extracting {filename}...")
            self.page.update()
            time.sleep(0.1)
            with zipfile.ZipFile(downloads_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Parse Export.xml to get workout activity types
            self.progress_text.value = "📋 Parsing workout data..."
            self.update_status("📋 Parsing workout data...")
            self.page.update()
            time.sleep(0.1)
            workout_activities = self.parse_export_xml_for_activities(extract_dir)
            
            # Look for workout-routes folder
            workout_routes_path = extract_dir / "apple_health_export" / "workout-routes"
            
            if not workout_routes_path.exists():
                logger.warning(f"workout-routes folder not found in export.zip")
                # Clean up
                shutil.rmtree(extract_dir)
                return
            
            # Copy all GPX files from workout-routes to temp directory with activity-based names
            gpx_files = list(workout_routes_path.glob("*.gpx"))
            copied_count = 0
            total_files = len(gpx_files)
            
            # Show progress bar
            self.progress_bar.visible = True
            self.progress_bar.value = 0
            self.progress_text.value = f"🚶 Processing {total_files} workout routes..."
            self.update_status(f"🚶 Processing {total_files} workout routes...")
            self.page.update()
            time.sleep(0.1)
            
            for i, gpx_file in enumerate(gpx_files, 1):
                try:
                    # Update progress
                    progress = i / total_files
                    self.progress_bar.value = progress
                    if i % 5 == 0 or i == total_files:
                        self.progress_text.value = f"🚶 Processing workout routes... ({i}/{total_files})"
                        self.page.update()
                    if i % 10 == 0 or i == total_files:
                        self.update_status(f"🚶 Processing workout routes... ({i}/{total_files})")
                    
                    # Determine activity type for this GPX file
                    activity_type = self.match_gpx_to_activity(gpx_file.name, workout_activities)
                    
                    # Create new filename with activity type instead of "route"
                    new_filename = gpx_file.name.replace('route_', f'{activity_type.lower()}_')
                    dest_path = Path(self.temp_dir) / new_filename
                    
                    shutil.copy2(gpx_file, dest_path)
                    copied_count += 1
                    
                    logger.info(f"Copied {gpx_file.name} -> {new_filename} ({activity_type})")
                    
                    # Automatically add speed tags if not present
                    self.processor.parse_gpx(str(dest_path), auto_add_speed=True)
                except Exception as e:
                    logger.error(f"Error copying {gpx_file.name}: {e}")
            
            logger.info(f"Extracted {copied_count} GPX files from export.zip")
            
            # Clean up extraction directory
            self.progress_text.value = "🧹 Cleaning up..."
            self.update_status("🧹 Cleaning up...")
            self.page.update()
            time.sleep(0.1)
            shutil.rmtree(extract_dir)
            
            # Hide progress indicator
            self.progress_container.visible = False
            self.progress_ring.visible = False
            self.progress_bar.visible = False
            self.progress_text.visible = False
            
            # Update final status and refresh file list
            self.update_status(f"✅ Auto-extracted {copied_count} routes from Downloads/{filename}")
            self.page.update()
            self.refresh_file_list(None)
            
        except Exception as e:
            logger.error(f"Error auto-extracting health export: {e}")
    
    def build_ui(self):
        """Build the user interface"""
        
        # Header
        header = ft.Container(
            content=ft.Text(
                "GPX Routes Workbench",
                size=32,
                weight=ft.FontWeight.BOLD,
                color=ft.colors.BLUE_700
            ),
            padding=10
        )
        
        # Instructions section
        instructions = self.create_instructions_section()
        
        # File picker section
        file_picker_section = self.create_file_picker_section()
        
        # File list section
        file_list_section = self.create_file_list_section()
        
        # Processing controls
        processing_section = self.create_processing_section()
        
        # Status bar
        status_bar = ft.Container(
            content=self.status_text,
            padding=10,
            bgcolor=ft.colors.GREY_200,
            border_radius=5
        )
        
        # Progress indicator container (shown during export extraction)
        export_filename = self.export_zip_path.name if self.export_zip_path else "export.zip"
        self.progress_title = ft.Text(f"Processing {export_filename}", size=20, weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_700)
        self.progress_container = ft.Container(
            content=ft.Column([
                self.progress_title,
                ft.Row([self.progress_ring, self.progress_text], alignment=ft.MainAxisAlignment.CENTER),
                self.progress_bar
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=20,
            bgcolor=ft.colors.BLUE_50,
            border_radius=10,
            border=ft.border.all(2, ft.colors.BLUE_300),
            visible=self.has_export_zip  # Show immediately if export.zip exists
        )
        
        # Info container for when files already exist
        self.info_container = ft.Container(
            content=ft.Row([
                ft.Icon(ft.icons.CHECK_CIRCLE, color=ft.colors.GREEN_700, size=30),
                ft.Text(
                    f"✅ Found {self.existing_files_count} existing GPX file{'s' if self.existing_files_count != 1 else ''} in temp directory",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=ft.colors.GREEN_700
                )
            ], alignment=ft.MainAxisAlignment.CENTER),
            padding=15,
            bgcolor=ft.colors.GREEN_50,
            border_radius=10,
            border=ft.border.all(2, ft.colors.GREEN_300),
            visible=(self.existing_files_count > 0 and not self.has_export_zip)
        )
        
        # Set initial progress state if export.zip found
        if self.has_export_zip:
            logger.info("Setting initial progress state - export.zip will be processed")
            self.progress_ring.visible = True
            self.progress_text.visible = True
            self.progress_text.value = "🔍 Preparing to extract export.zip..."
        
        # Layout
        self.page.add(
            header,
            ft.Divider(),
            self.progress_container,
            self.info_container,
            instructions,
            ft.Divider(),
            file_picker_section,
            ft.Divider(),
            file_list_section,
            ft.Divider(),
            processing_section,
            ft.Divider(),
            status_bar
        )
        
        # Add pickers to overlay after UI is built
        self.page.overlay.append(self.pick_files_dialog)
        self.page.overlay.append(self.cutoff_date_picker)
        self.page.update()
    
    def create_instructions_section(self) -> ft.Column:
        """Create instructions for exporting iPhone health data"""
        instructions_text = """
How to Export Health Data from Your iPhone:

1. Open the Health app on your iPhone
2. Tap your profile picture or initials in the top right
3. Scroll down and tap "Export All Health Data"
4. Wait for the export to complete (may take several minutes)
5. Save the export.zip file to your Downloads folder on your computer

✨ AUTO-IMPORT: If export.zip is in your ~/Downloads folder when you launch this app,
   the workout routes will be automatically extracted to the temp directory!

Alternatively, you can manually:
6. Extract the export.zip file on your computer
7. Inside the extracted folder, look for the "workout-routes" folder
8. Use the file picker below to select and import the GPX route files

Note: The workout-routes folder contains individual .gpx files for each recorded workout with GPS data.
        """
        
        # Check if GPX files exist to determine initial collapsed state
        has_gpx_files = False
        if os.path.exists(self.temp_dir):
            existing_gpx = [f for f in os.listdir(self.temp_dir) if f.endswith('.gpx')]
            has_gpx_files = len(existing_gpx) > 0
        
        # Create the instructions content container
        self.instructions_content = ft.Container(
            content=ft.Text(instructions_text, size=14, selectable=True),
            padding=10,
            visible=not has_gpx_files  # Hidden if files exist, visible if empty
        )
        
        # Create toggle button
        self.instructions_toggle_icon = ft.Icon(
            ft.icons.EXPAND_MORE if not has_gpx_files else ft.icons.EXPAND_LESS,
            color=ft.colors.GREEN_700
        )
        
        def toggle_instructions(e):
            self.instructions_content.visible = not self.instructions_content.visible
            self.instructions_toggle_icon.name = ft.icons.EXPAND_LESS if self.instructions_content.visible else ft.icons.EXPAND_MORE
            self.page.update()
        
        # Create header with click to expand/collapse
        instructions_header = ft.Container(
            content=ft.Row([
                self.instructions_toggle_icon,
                ft.Text("📱 iPhone Health Data Export Instructions", 
                       size=18, weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_700),
                ft.Text("(click to expand/collapse)", size=12, color=ft.colors.GREEN_600, italic=True),
            ], spacing=10),
            on_click=toggle_instructions,
            padding=10,
        )
        
        return ft.Column([
            ft.Container(
                content=ft.Column([
                    instructions_header,
                    self.instructions_content,
                ]),
                bgcolor=ft.colors.GREEN_50,
                border_radius=10,
                border=ft.border.all(2, ft.colors.GREEN_200)
            )
        ])
    
    def create_file_picker_section(self) -> ft.Container:
        """Create file picker section"""
        
        # Create buttons (FilePicker and DatePicker are initialized in __init__)
        pick_files_button = ft.ElevatedButton(
            "📁 Select GPX Files",
            icon=ft.icons.FILE_OPEN,
            on_click=lambda _: self.pick_files_dialog.pick_files(
                allowed_extensions=["gpx"],
                allow_multiple=True
            ),
            style=ft.ButtonStyle(
                color=ft.colors.WHITE,
                bgcolor=ft.colors.BLUE_700
            )
        )
        
        clear_temp_button = ft.ElevatedButton(
            "🗑️ Clear Temp Directory",
            icon=ft.icons.DELETE,
            on_click=self.clear_temp_directory,
            style=ft.ButtonStyle(
                color=ft.colors.WHITE,
                bgcolor=ft.colors.RED_700
            )
        )
        
        self.cutoff_date_button = ft.ElevatedButton(
            f"📅 {self.selected_cutoff_date.strftime('%Y-%m-%d')}",
            on_click=self.open_cutoff_date_picker,
            tooltip="Select cutoff date",
            style=ft.ButtonStyle(
                bgcolor=ft.colors.GREY_300
            )
        )
        
        remove_old_button = ft.ElevatedButton(
            "🧹 Remove Files Before Date",
            icon=ft.icons.DELETE_SWEEP,
            on_click=self.remove_files_before_date,
            tooltip="Remove all GPX files older than the selected date",
            style=ft.ButtonStyle(
                color=ft.colors.WHITE,
                bgcolor=ft.colors.ORANGE_700
            )
        )
        
        return ft.Container(
            content=ft.Column([
                ft.Text("Import GPX Files", size=20, weight=ft.FontWeight.BOLD),
                ft.Row([pick_files_button, clear_temp_button], spacing=10),
                ft.Row([
                    ft.Text("Remove old files:", size=14),
                    self.cutoff_date_button,
                    remove_old_button
                ], spacing=10),
                ft.Text(f"Temp directory: {self.temp_dir}", size=12, italic=True)
            ]),
            padding=15,
            bgcolor=ft.colors.BLUE_50,
            border_radius=10
        )
    
    def create_file_list_section(self) -> ft.Container:
        """Create file list section with selection checkboxes"""
        
        select_all_button = ft.ElevatedButton(
            "Select All",
            icon=ft.icons.CHECK_BOX,
            on_click=self.select_all_files
        )
        
        deselect_all_button = ft.ElevatedButton(
            "Deselect All",
            icon=ft.icons.CHECK_BOX_OUTLINE_BLANK,
            on_click=self.deselect_all_files
        )
        
        refresh_button = ft.ElevatedButton(
            "🔄 Refresh List",
            icon=ft.icons.REFRESH,
            on_click=self.refresh_file_list
        )
        
        return ft.Container(
            content=ft.Column([
                ft.Text("Available GPX Routes", size=20, weight=ft.FontWeight.BOLD),
                ft.Row([select_all_button, deselect_all_button, refresh_button], spacing=10),
                ft.Container(
                    content=self.files_list_view,
                    height=200,
                    border=ft.border.all(1, ft.colors.GREY_400),
                    border_radius=5,
                    padding=5
                )
            ]),
            padding=15,
            bgcolor=ft.colors.GREY_50,
            border_radius=10
        )
    
    def create_processing_section(self) -> ft.Container:
        """Create processing controls section"""
        
        map_button = ft.ElevatedButton(
            "🗺️ Visualize Routes",
            icon=ft.icons.MAP,
            on_click=self.visualize_routes,
            style=ft.ButtonStyle(
                color=ft.colors.WHITE,
                bgcolor=ft.colors.PURPLE_700
            )
        )
        
        self.auto_open_map_checkbox = ft.Checkbox(
            label="Auto-open in browser",
            value=True,
            tooltip="Automatically open the map in your default browser after creation"
        )
        
        self.separate_maps_checkbox = ft.Checkbox(
            label="One file per route",
            value=False,
            tooltip="Create individual HTML files for each route instead of one combined file"
        )
        
        self.max_speed_field = ft.TextField(
            label="Max Speed (MPH)",
            value="5",
            width=150,
            hint_text="Default: 5 mph"
        )
        
        trim_button = ft.ElevatedButton(
            "✂️ Trim by Speed",
            icon=ft.icons.CONTENT_CUT,
            on_click=self.trim_by_speed,
            style=ft.ButtonStyle(
                color=ft.colors.WHITE,
                bgcolor=ft.colors.TEAL_700
            )
        )
        
        post_hikes_button = ft.ElevatedButton(
            "📤 Post to Hikes Blog",
            icon=ft.icons.UPLOAD,
            on_click=self.post_to_hikes,
            tooltip="Post selected routes to ~/GitHub/hikes repository",
            style=ft.ButtonStyle(
                color=ft.colors.WHITE,
                bgcolor=ft.colors.INDIGO_700
            )
        )
        
        return ft.Container(
            content=ft.Column([
                ft.Text("Processing Controls", size=20, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=ft.Row([self.auto_open_map_checkbox, self.separate_maps_checkbox, map_button], spacing=10),
                    height=50
                ),
                ft.Container(
                    content=ft.Row([self.max_speed_field, trim_button], spacing=10),
                    height=50
                ),
                ft.Container(
                    content=ft.Row([post_hikes_button], spacing=10),
                    height=50
                ),
                self.map_output
            ]),
            padding=15,
            bgcolor=ft.colors.AMBER_50,
            border_radius=10
        )
    
    def on_files_selected(self, e):
        """Handle file selection from file picker"""
        if e.files:
            logger.info(f"Selected {len(e.files)} files")
            copied_count = 0
            
            for file in e.files:
                try:
                    dest_path = os.path.join(self.temp_dir, os.path.basename(file.path))
                    shutil.copy2(file.path, dest_path)
                    copied_count += 1
                    logger.info(f"Copied {file.name} to temp directory")
                    
                    # Automatically add speed tags if not present
                    self.processor.parse_gpx(dest_path, auto_add_speed=True)
                except Exception as ex:
                    logger.error(f"Error copying {file.name}: {ex}")
            
            self.update_status(f"Copied {copied_count} file(s) to temp directory")
            self.refresh_file_list(None)
    
    def clear_temp_directory(self, e):
        """Clear the temporary directory"""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                os.makedirs(self.temp_dir, exist_ok=True)
                logger.info("Cleared temp directory")
                self.update_status("Temp directory cleared")
                self.refresh_file_list(None)
        except Exception as ex:
            logger.error(f"Error clearing temp directory: {ex}")
            self.update_status(f"Error: {ex}")
    
    def open_cutoff_date_picker(self, e):
        """Open the cutoff date picker dialog"""
        self.cutoff_date_picker.open = True
        self.page.update()
    
    def on_cutoff_date_changed(self, e):
        """Handle cutoff date selection"""
        if e.control.value:
            self.selected_cutoff_date = e.control.value
            self.cutoff_date_button.text = f"📅 {self.selected_cutoff_date.strftime('%Y-%m-%d')}"
            self.page.update()
            logger.info(f"Cutoff date selected: {self.selected_cutoff_date}")
    
    def remove_files_before_date(self, e):
        """Remove GPX files with dates older than the selected cutoff date"""
        if not os.path.exists(self.temp_dir):
            self.update_status("Temp directory does not exist")
            return
        
        try:
            gpx_files = [f for f in os.listdir(self.temp_dir) if f.endswith('.gpx')]
            removed_count = 0
            kept_count = 0
            
            for filename in gpx_files:
                file_date = self._extract_date_from_filename(filename)
                
                # Compare dates (ignoring time portion)
                if file_date.date() < self.selected_cutoff_date.date():
                    file_path = os.path.join(self.temp_dir, filename)
                    try:
                        os.remove(file_path)
                        removed_count += 1
                        logger.info(f"Removed old file: {filename} (date: {file_date.date()})")
                    except Exception as ex:
                        logger.error(f"Error removing {filename}: {ex}")
                else:
                    kept_count += 1
            
            self.update_status(f"Removed {removed_count} file(s) before {self.selected_cutoff_date.strftime('%Y-%m-%d')}, kept {kept_count}")
            self.refresh_file_list(None)
            
        except Exception as ex:
            logger.error(f"Error removing old files: {ex}")
            self.update_status(f"Error: {ex}")
    
    def _extract_date_from_filename(self, filename: str) -> datetime:
        """Extract datetime from filename for sorting (e.g., walking_2025-02-04_9.04am.gpx or route_2025-02-04_9.04am.gpx)"""
        import re
        try:
            # Parse format: activity_YYYY-MM-DD_H.MMam/pm.gpx (new format) or route_YYYY-MM-DD_H.MMam/pm.gpx (old format)
            # Match any word followed by underscore, then date/time pattern
            match = re.match(r'\w+_(\d{4})-(\d{2})-(\d{2})_(\d{1,2})\.(\d{2})(am|pm)\.gpx', filename)
            if match:
                year, month, day, hour, minute, period = match.groups()
                hour = int(hour)
                # Convert 12-hour to 24-hour format
                if period == 'pm' and hour != 12:
                    hour += 12
                elif period == 'am' and hour == 12:
                    hour = 0
                return datetime(int(year), int(month), int(day), hour, int(minute))
        except Exception as e:
            logger.warning(f"Could not parse date from filename {filename}: {e}")
        
        # Fallback to file modification time if parsing fails
        try:
            return datetime.fromtimestamp(os.path.getmtime(os.path.join(self.temp_dir, filename)))
        except:
            return datetime.min
    
    def refresh_file_list(self, e):
        """Refresh the list of GPX files"""
        self.files_list_view.controls.clear()
        self.file_checkboxes.clear()
        
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir, exist_ok=True)
            return
        
        gpx_files = [f for f in os.listdir(self.temp_dir) if f.endswith('.gpx')]
        
        # Sort by date extracted from filename in reverse chronological order (newest first)
        gpx_files.sort(key=self._extract_date_from_filename, reverse=True)
        
        if not gpx_files:
            self.files_list_view.controls.append(
                ft.Text("No GPX files found in temp directory", italic=True, color=ft.colors.GREY_700)
            )
        else:
            for filename in gpx_files:
                # Parse GPX to check for speed and distance tags
                file_path = os.path.join(self.temp_dir, filename)
                label_text = filename
                
                try:
                    gpx = self.processor.parse_gpx(file_path)
                    if gpx:
                        max_speed_ms, max_distance_m = self.processor.get_max_speed_and_distance(gpx)
                        
                        if max_speed_ms is not None and max_distance_m is not None:
                            # Convert m/s to mph (1 m/s = 2.23694 mph)
                            max_speed_mph = max_speed_ms * 2.23694
                            # Convert meters to feet (1 meter = 3.28084 feet)
                            max_distance_feet = max_distance_m * 3.28084
                            
                            label_text = f"{filename}  [Max: {max_speed_mph:.1f} mph, {max_distance_feet:.1f} ft]"
                except Exception as ex:
                    logger.warning(f"Could not read speed/distance from {filename}: {ex}")
                
                checkbox = ft.Checkbox(
                    label=label_text,
                    value=filename in self.selected_files,
                    on_change=lambda e, f=filename: self.on_file_checkbox_changed(f, e.control.value)
                )
                self.file_checkboxes[filename] = checkbox
                self.files_list_view.controls.append(checkbox)
        
        # Update instructions expansion state based on whether files exist
        if hasattr(self, 'instructions_content'):
            should_show = len(gpx_files) == 0
            self.instructions_content.visible = should_show
            if hasattr(self, 'instructions_toggle_icon'):
                self.instructions_toggle_icon.name = ft.icons.EXPAND_LESS if should_show else ft.icons.EXPAND_MORE
        
        self.page.update()
        logger.info(f"File list refreshed: {len(gpx_files)} files found")
    
    def on_file_checkbox_changed(self, filename: str, is_checked: bool):
        """Handle file checkbox change"""
        if is_checked and filename not in self.selected_files:
            self.selected_files.append(filename)
        elif not is_checked and filename in self.selected_files:
            self.selected_files.remove(filename)
        
        self.update_status(f"Selected {len(self.selected_files)} file(s)")
        logger.info(f"File selection changed: {filename} = {is_checked}")
    
    def select_all_files(self, e):
        """Select all files"""
        for filename, checkbox in self.file_checkboxes.items():
            checkbox.value = True
            if filename not in self.selected_files:
                self.selected_files.append(filename)
        
        self.page.update()
        self.update_status(f"Selected all {len(self.selected_files)} file(s)")
    
    def deselect_all_files(self, e):
        """Deselect all files"""
        for checkbox in self.file_checkboxes.values():
            checkbox.value = False
        
        self.selected_files.clear()
        self.page.update()
        self.update_status("Deselected all files")
    
    def visualize_routes(self, e):
        """Visualize selected routes"""
        if not self.selected_files:
            self.update_status("No files selected for visualization")
            return
        
        try:
            import folium
            
            if self.separate_maps_checkbox.value:
                # Create individual maps for each route
                created_files = []
                
                for filename in self.selected_files:
                    file_path = os.path.join(self.temp_dir, filename)
                    gpx_data = self.processor.parse_gpx(file_path)
                    
                    if gpx_data:
                        bounds = self.processor.get_gpx_bounds(gpx_data)
                        if bounds:
                            center_lat = (bounds['min_lat'] + bounds['max_lat']) / 2
                            center_lon = (bounds['min_lon'] + bounds['max_lon']) / 2
                            
                            m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
                            
                            # Add this route to the map
                            for track in gpx_data.tracks:
                                for segment in track.segments:
                                    points = [(point.latitude, point.longitude) for point in segment.points]
                                    folium.PolyLine(
                                        points, 
                                        color='blue', 
                                        weight=3, 
                                        opacity=0.7, 
                                        popup=filename,
                                        tooltip=filename
                                    ).add_to(m)
                            
                            # Save map with route name
                            html_filename = filename.replace('.gpx', '.html')
                            map_file = os.path.join(self.temp_dir, html_filename)
                            m.save(map_file)
                            created_files.append(map_file)
                            logger.info(f"Created individual map: {html_filename}")
                
                self.update_status(f"Created {len(created_files)} individual map file(s)")
                self.map_output.value = f"✅ Created {len(created_files)} individual map files\n" + "\n".join([os.path.basename(f) for f in created_files])
                
                # Auto-open in browser if checkbox is checked
                if self.auto_open_map_checkbox.value and created_files:
                    try:
                        for map_file in created_files:
                            webbrowser.open(f"file://{os.path.abspath(map_file)}")
                        logger.info(f"Opened {len(created_files)} maps in browser tabs")
                        self.map_output.value = f"✅ Created and opened {len(created_files)} individual maps in browser"
                    except Exception as browser_error:
                        logger.warning(f"Could not auto-open browser: {browser_error}")
                
            else:
                # Create a single combined map
                first_file = os.path.join(self.temp_dir, self.selected_files[0])
                gpx = self.processor.parse_gpx(first_file)
                
                if gpx:
                    bounds = self.processor.get_gpx_bounds(gpx)
                    if bounds:
                        center_lat = (bounds['min_lat'] + bounds['max_lat']) / 2
                        center_lon = (bounds['min_lon'] + bounds['max_lon']) / 2
                        
                        m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
                        
                        # Add all selected routes to the map
                        colors = ['blue', 'red', 'green', 'purple', 'orange', 'darkred', 'lightred', 'beige', 'darkblue', 'darkgreen']
                        
                        for idx, filename in enumerate(self.selected_files):
                            file_path = os.path.join(self.temp_dir, filename)
                            gpx_data = self.processor.parse_gpx(file_path)
                            
                            if gpx_data:
                                color = colors[idx % len(colors)]
                                
                                for track in gpx_data.tracks:
                                    for segment in track.segments:
                                        points = [(point.latitude, point.longitude) for point in segment.points]
                                        folium.PolyLine(
                                            points, 
                                            color=color, 
                                            weight=3, 
                                            opacity=0.7, 
                                            popup=filename,
                                            tooltip=filename
                                        ).add_to(m)
                        
                        # Save combined map
                        map_file = os.path.join(self.temp_dir, "routes_map.html")
                        m.save(map_file)
                        
                        self.update_status(f"Map created: {map_file}")
                        self.map_output.value = f"✅ Map saved to: {map_file}\nOpen this file in a web browser to view the routes."
                        logger.info(f"Map created with {len(self.selected_files)} routes")
                        
                        # Auto-open in browser if checkbox is checked
                        if self.auto_open_map_checkbox.value:
                            try:
                                webbrowser.open(f"file://{os.path.abspath(map_file)}")
                                logger.info("Opened map in browser")
                                self.map_output.value = f"✅ Map saved and opened in browser: {map_file}"
                            except Exception as browser_error:
                                logger.warning(f"Could not auto-open browser: {browser_error}")
                    
                    else:
                        self.update_status("Could not determine route bounds")
                else:
                    self.update_status("Error parsing first GPX file")
        
        except Exception as ex:
            logger.error(f"Error visualizing routes: {ex}")
            self.update_status(f"Error: {ex}")
        
        self.page.update()
    
    def trim_by_speed(self, e):
        """Trim selected routes by speed threshold"""
        if not self.selected_files:
            self.update_status("No files selected")
            return
        
        try:
            max_speed_mph = float(self.max_speed_field.value)
            # Convert MPH to m/s (1 mph = 0.44704 m/s)
            max_speed_ms = max_speed_mph * 0.44704
        except ValueError:
            self.update_status("Invalid max speed value")
            return
        
        processed_count = 0
        
        for filename in self.selected_files:
            file_path = os.path.join(self.temp_dir, filename)
            gpx = self.processor.parse_gpx(file_path)
            
            if gpx:
                # Ensure speed tags are present (should already exist from auto-processing)
                if not self.processor.has_speed_and_distance_tags(gpx):
                    gpx = self.processor.calculate_speed(gpx)
                
                # Trim by speed threshold (using m/s internally)
                gpx = self.processor.trim_by_speed(gpx, max_speed_ms)
                
                # Replace the original file
                self.processor.save_gpx(gpx, file_path)
                processed_count += 1
        
        self.update_status(f"Trimmed {processed_count} file(s) by speed (max: {max_speed_mph} mph)")
        self.refresh_file_list(None)
    
    def get_track_center(self, gpx):
        """Calculate map center (lat, lon) from a gpxpy track object"""
        lats = []
        lons = []
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    lats.append(point.latitude)
                    lons.append(point.longitude)
        if lats and lons:
            center_lat = sum(lats) / len(lats)
            center_lon = sum(lons) / len(lons)
            return (center_lat, center_lon)
        return (0, 0)
    
    def get_datetime(self, gpx):
        """Fetch the first <time> tag from a GPX and return a datetime object"""
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    if point.time:
                        return point.time
        return None
    
    def identify_place(self, lat, lon):
        """Use reverse geocoding to identify the location"""
        try:
            from geopy.geocoders import Nominatim
            geolocator = Nominatim(user_agent="gpx-routes-workbench")
            coord = f"{lat}, {lon}"
            location = geolocator.reverse(coord, timeout=10)
            if location:
                address = location.raw['address']
                town = address.get('town', '')
                city = address.get('city', '')
                county = address.get('county', '')
                
                if town:
                    return f"in {town}"
                elif city:
                    return f"in {city}"
                elif county:
                    return f"in {county}"
            return "Unknown Location"
        except Exception as e:
            logger.warning(f"Could not identify location: {e}")
            return "Unknown Location"
    
    def post_to_hikes(self, e):
        """Post selected routes to Hikes blog repository"""
        if not self.selected_files:
            self.update_status("No files selected")
            return
        
        # Get hikes repository path from environment or use default
        hikes_path = os.path.expanduser('~/GitHub/hikes')
        
        if not os.path.exists(hikes_path):
            self.update_status(f"Error: Hikes repository not found at {hikes_path}")
            return
        
        posted_count = 0
        
        for filename in self.selected_files:
            file_path = os.path.join(self.temp_dir, filename)
            
            try:
                # Parse GPX file
                gpx = self.processor.parse_gpx(file_path)
                if not gpx:
                    logger.error(f"Could not parse {filename}")
                    continue
                
                # Extract GPX metadata
                center = self.get_track_center(gpx)
                dt = self.get_datetime(gpx)
                
                if not dt:
                    logger.error(f"No datetime found in {filename}")
                    continue
                
                place = self.identify_place(center[0], center[1])
                
                # Extract activity type from filename (e.g., walking_2025-10-10_2.40pm.gpx)
                mode = "Walking"  # Default mode
                if '_' in filename:
                    activity_prefix = filename.split('_')[0]
                    mode = activity_prefix.capitalize()  # walking -> Walking, biking -> Biking, etc.
                
                # Format date/time for paths and frontmatter
                pub_date = dt.strftime('%Y-%m-%d')
                ym_path = dt.strftime('%Y/%m')
                title = f"{dt.strftime('%a %b %d')} at {dt.strftime('%-l%p').lower()} - {mode} {place}"
                weight = f"-{dt.strftime('%Y%m%d%H%M')}"
                
                # Create markdown file
                md_filename = filename.replace('.gpx', '.md')
                md_dir = os.path.join(hikes_path, 'content/hikes', ym_path)
                os.makedirs(md_dir, exist_ok=True)
                
                md_path = os.path.join(md_dir, md_filename)
                
                with open(md_path, 'w') as md_file:
                    # Write frontmatter
                    md_file.write("---\n")
                    md_file.write(f"title: {title}\n")
                    md_file.write(f"weight: {weight}\n")
                    md_file.write(f"publishDate: {pub_date}\n")
                    md_file.write(f"location: {place}\n")
                    md_file.write("highlight: false\n")
                    md_file.write(f"bike: {'True' if mode in ['Biking', 'Cycling'] else 'False'}\n")
                    md_file.write(f"trackType: {mode.lower()}\n")
                    md_file.write("trashBags: false\n")
                    md_file.write("trashRecyclables: false\n")
                    md_file.write("trashWeight: false\n")
                    md_file.write("weather: Weather data not available\n")
                    md_file.write("---\n")
                    
                    # Write leaflet map shortcodes
                    md_file.write('{{< leaflet-map mapHeight="500px" mapWidth="100%" >}}\n')
                    md_file.write(f'  {{{{< leaflet-track trackPath="{ym_path}/{filename}" lineColor=#c838d1 lineWeight="5" graphDetached=True >}}}}\n')
                    md_file.write('{{< /leaflet-map >}}\n')
                
                # Copy GPX file to static directory
                gpx_dir = os.path.join(hikes_path, 'static/gpx', ym_path)
                os.makedirs(gpx_dir, exist_ok=True)
                shutil.copy(file_path, os.path.join(gpx_dir, filename))
                
                posted_count += 1
                logger.info(f"Posted {filename} to Hikes")
                
            except Exception as ex:
                logger.error(f"Error posting {filename}: {ex}")
        
        # Git commit and push
        if posted_count > 0:
            try:
                import subprocess
                cwd = os.getcwd()
                os.chdir(hikes_path)
                
                subprocess.run(['git', 'pull'], check=True)
                subprocess.run(['git', 'add', '.'], check=True)
                subprocess.run(['git', 'commit', '-m', f'Posted {posted_count} routes from GPX Routes Workbench'], check=True)
                subprocess.run(['git', 'push'], check=True)
                
                os.chdir(cwd)
                self.update_status(f"Successfully posted {posted_count} route(s) to Hikes and pushed to GitHub")
                
            except subprocess.CalledProcessError as e:
                logger.error(f"Git error: {e}")
                os.chdir(cwd)
                self.update_status(f"Posted {posted_count} file(s) but git push failed")
            except Exception as e:
                logger.error(f"Error during git operations: {e}")
                os.chdir(cwd)
                self.update_status(f"Posted {posted_count} file(s) but git operations failed")
        else:
            self.update_status("No files were posted")
    
    def update_status(self, message: str):
        """Update status text"""
        self.status_text.value = f"{datetime.now().strftime('%H:%M:%S')} - {message}"
        self.page.update()
        logger.info(message)


def main(page: ft.Page):
    """Main entry point for the Flet app"""
    logger.info("Main function called, initializing app...")
    try:
        app = GPXWorkbenchApp(page)
        app.refresh_file_list(None)
        logger.info("App initialization complete")
    except Exception as e:
        logger.error(f"Error initializing app: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    logger.info("Starting Flet application...")
    ft.app(target=main, view=ft.AppView.FLET_APP)
