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
    def parse_gpx(file_path: str) -> Optional[gpxpy.gpx.GPX]:
        """Parse a GPX file"""
        try:
            with open(file_path, 'r') as gpx_file:
                gpx = gpxpy.parse(gpx_file)
                logger.info(f"Successfully parsed {file_path}")
                return gpx
        except Exception as e:
            logger.error(f"Error parsing GPX file {file_path}: {e}")
            return None
    
    @staticmethod
    def calculate_speed(gpx: gpxpy.gpx.GPX) -> gpxpy.gpx.GPX:
        """Add speed tags to GPX trackpoints"""
        for track in gpx.tracks:
            for segment in track.segments:
                points = segment.points
                for i in range(1, len(points)):
                    prev_point = points[i - 1]
                    curr_point = points[i]
                    
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
        
        logger.info("Speed tags added to GPX")
        return gpx
    
    @staticmethod
    @staticmethod
    def trim_by_speed(gpx: gpxpy.gpx.GPX, max_speed: float = 50.0) -> gpxpy.gpx.GPX:
        """Remove points with excessive speed (max_speed in m/s, UI uses mph)"""
        removed_count = 0
        for track in gpx.tracks:
            for segment in track.segments:
                points_to_keep = []
                for point in segment.points:
                    if hasattr(point, 'speed') and point.speed is not None:
                        if point.speed <= max_speed:
                            points_to_keep.append(point)
                        else:
                            removed_count += 1
                    else:
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
        
        # Auto-extract export.zip from Downloads if found
        self.auto_extract_health_export()
        
        self.build_ui()
    
    def auto_extract_health_export(self):
        """Automatically check for and extract export.zip from Downloads folder"""
        try:
            # Check if GPX files already exist in temp directory
            if os.path.exists(self.temp_dir):
                existing_gpx = [f for f in os.listdir(self.temp_dir) if f.endswith('.gpx')]
                if existing_gpx:
                    logger.info(f"Skipping auto-extraction: {len(existing_gpx)} GPX files already exist in temp directory")
                    return
            
            # Get the user's home directory and construct Downloads path
            downloads_path = Path.home() / "Downloads" / "export.zip"
            
            if not downloads_path.exists():
                logger.info("No export.zip found in Downloads folder")
                return
            
            logger.info(f"Found export.zip at {downloads_path}")
            
            # Extract to a temporary location
            extract_dir = Path(self.temp_dir) / "health_export_temp"
            
            # Remove old extraction if exists
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            
            logger.info("Extracting export.zip...")
            with zipfile.ZipFile(downloads_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Look for workout-routes folder
            workout_routes_path = extract_dir / "apple_health_export" / "workout-routes"
            
            if not workout_routes_path.exists():
                logger.warning(f"workout-routes folder not found in export.zip")
                # Clean up
                shutil.rmtree(extract_dir)
                return
            
            # Copy all GPX files from workout-routes to temp directory
            gpx_files = list(workout_routes_path.glob("*.gpx"))
            copied_count = 0
            
            for gpx_file in gpx_files:
                try:
                    dest_path = Path(self.temp_dir) / gpx_file.name
                    shutil.copy2(gpx_file, dest_path)
                    copied_count += 1
                except Exception as e:
                    logger.error(f"Error copying {gpx_file.name}: {e}")
            
            logger.info(f"Extracted {copied_count} GPX files from export.zip")
            
            # Clean up extraction directory
            shutil.rmtree(extract_dir)
            
            # Update the status in the UI if it's ready
            if hasattr(self, 'status_text'):
                self.update_status(f"Auto-extracted {copied_count} routes from Downloads/export.zip")
            
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
                color=ft.Colors.BLUE_700
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
            bgcolor=ft.Colors.GREY_200,
            border_radius=5
        )
        
        # Layout
        self.page.add(
            header,
            ft.Divider(),
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
            ft.Icons.EXPAND_MORE if not has_gpx_files else ft.Icons.EXPAND_LESS,
            color=ft.Colors.GREEN_700
        )
        
        def toggle_instructions(e):
            self.instructions_content.visible = not self.instructions_content.visible
            self.instructions_toggle_icon.name = ft.Icons.EXPAND_LESS if self.instructions_content.visible else ft.Icons.EXPAND_MORE
            self.page.update()
        
        # Create header with click to expand/collapse
        instructions_header = ft.Container(
            content=ft.Row([
                self.instructions_toggle_icon,
                ft.Text("📱 iPhone Health Data Export Instructions", 
                       size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700),
                ft.Text("(click to expand/collapse)", size=12, color=ft.Colors.GREEN_600, italic=True),
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
                bgcolor=ft.Colors.GREEN_50,
                border_radius=10,
                border=ft.border.all(2, ft.Colors.GREEN_200)
            )
        ])
    
    def create_file_picker_section(self) -> ft.Container:
        """Create file picker section"""
        
        # File picker dialogs
        self.pick_files_dialog = ft.FilePicker(on_result=self.on_files_selected)
        self.page.overlay.append(self.pick_files_dialog)
        
        pick_files_button = ft.ElevatedButton(
            "📁 Select GPX Files",
            icon=ft.Icons.FILE_OPEN,
            on_click=lambda _: self.pick_files_dialog.pick_files(
                allowed_extensions=["gpx"],
                allow_multiple=True
            ),
            style=ft.ButtonStyle(
                color=ft.Colors.WHITE,
                bgcolor=ft.Colors.BLUE_700
            )
        )
        
        clear_temp_button = ft.ElevatedButton(
            "🗑️ Clear Temp Directory",
            icon=ft.Icons.DELETE,
            on_click=self.clear_temp_directory,
            style=ft.ButtonStyle(
                color=ft.Colors.WHITE,
                bgcolor=ft.Colors.RED_700
            )
        )
        
        # Date picker for removing old files
        self.cutoff_date_picker = ft.DatePicker(
            on_change=self.on_cutoff_date_changed,
            on_dismiss=lambda e: None,
        )
        self.page.overlay.append(self.cutoff_date_picker)
        
        # Default to 30 days ago
        default_date = datetime.now() - timedelta(days=30)
        self.selected_cutoff_date = default_date
        
        self.cutoff_date_button = ft.ElevatedButton(
            f"📅 {default_date.strftime('%Y-%m-%d')}",
            on_click=lambda _: self.cutoff_date_picker.pick_date(),
            tooltip="Select cutoff date",
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.GREY_300
            )
        )
        
        remove_old_button = ft.ElevatedButton(
            "🧹 Remove Files Before Date",
            icon=ft.Icons.DELETE_SWEEP,
            on_click=self.remove_files_before_date,
            tooltip="Remove all GPX files older than the selected date",
            style=ft.ButtonStyle(
                color=ft.Colors.WHITE,
                bgcolor=ft.Colors.ORANGE_700
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
            bgcolor=ft.Colors.BLUE_50,
            border_radius=10
        )
    
    def create_file_list_section(self) -> ft.Container:
        """Create file list section with selection checkboxes"""
        
        select_all_button = ft.ElevatedButton(
            "Select All",
            icon=ft.Icons.CHECK_BOX,
            on_click=self.select_all_files
        )
        
        deselect_all_button = ft.ElevatedButton(
            "Deselect All",
            icon=ft.Icons.CHECK_BOX_OUTLINE_BLANK,
            on_click=self.deselect_all_files
        )
        
        refresh_button = ft.ElevatedButton(
            "🔄 Refresh List",
            icon=ft.Icons.REFRESH,
            on_click=self.refresh_file_list
        )
        
        return ft.Container(
            content=ft.Column([
                ft.Text("Available GPX Routes", size=20, weight=ft.FontWeight.BOLD),
                ft.Row([select_all_button, deselect_all_button, refresh_button], spacing=10),
                ft.Container(
                    content=self.files_list_view,
                    height=200,
                    border=ft.border.all(1, ft.Colors.GREY_400),
                    border_radius=5,
                    padding=5
                )
            ]),
            padding=15,
            bgcolor=ft.Colors.GREY_50,
            border_radius=10
        )
    
    def create_processing_section(self) -> ft.Container:
        """Create processing controls section"""
        
        map_button = ft.ElevatedButton(
            "🗺️ Visualize Routes",
            icon=ft.Icons.MAP,
            on_click=self.visualize_routes,
            style=ft.ButtonStyle(
                color=ft.Colors.WHITE,
                bgcolor=ft.Colors.PURPLE_700
            )
        )
        
        self.auto_open_map_checkbox = ft.Checkbox(
            label="Auto-open in browser",
            value=True,
            tooltip="Automatically open the map in your default browser after creation"
        )
        
        add_speed_button = ft.ElevatedButton(
            "⚡ Add Speed Tags",
            icon=ft.Icons.SPEED,
            on_click=self.add_speed_tags,
            style=ft.ButtonStyle(
                color=ft.Colors.WHITE,
                bgcolor=ft.Colors.ORANGE_700
            )
        )
        
        self.max_speed_field = ft.TextField(
            label="Max Speed (MPH)",
            value="5",
            width=150,
            hint_text="Default: 5 mph"
        )
        
        trim_button = ft.ElevatedButton(
            "✂️ Trim by Speed",
            icon=ft.Icons.CONTENT_CUT,
            on_click=self.trim_by_speed,
            style=ft.ButtonStyle(
                color=ft.Colors.WHITE,
                bgcolor=ft.Colors.TEAL_700
            )
        )
        
        self.hikes_url_field = ft.TextField(
            label="Hikes API URL",
            value=self.persistent_data.data.get("hikes_api_url", ""),
            expand=True,
            hint_text="https://api.example.com/hikes"
        )
        
        post_hikes_button = ft.ElevatedButton(
            "📤 Post to Hikes",
            icon=ft.Icons.UPLOAD,
            on_click=self.post_to_hikes,
            style=ft.ButtonStyle(
                color=ft.Colors.WHITE,
                bgcolor=ft.Colors.INDIGO_700
            )
        )
        
        return ft.Container(
            content=ft.Column([
                ft.Text("Processing Controls", size=20, weight=ft.FontWeight.BOLD),
                ft.Row([map_button, self.auto_open_map_checkbox, add_speed_button], spacing=10),
                ft.Row([self.max_speed_field, trim_button], spacing=10),
                ft.Row([self.hikes_url_field, post_hikes_button], spacing=10),
                self.map_output
            ]),
            padding=15,
            bgcolor=ft.Colors.AMBER_50,
            border_radius=10
        )
    
    def on_files_selected(self, e: ft.FilePickerResultEvent):
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
        """Extract datetime from filename for sorting (e.g., route_2025-02-04_9.04am.gpx)"""
        import re
        try:
            # Parse format: route_YYYY-MM-DD_H.MMam/pm.gpx
            match = re.match(r'route_(\d{4})-(\d{2})-(\d{2})_(\d{1,2})\.(\d{2})(am|pm)\.gpx', filename)
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
                ft.Text("No GPX files found in temp directory", italic=True, color=ft.Colors.GREY_700)
            )
        else:
            for filename in gpx_files:
                checkbox = ft.Checkbox(
                    label=filename,
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
                self.instructions_toggle_icon.name = ft.Icons.EXPAND_LESS if should_show else ft.Icons.EXPAND_MORE
        
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
            
            # Create a map centered on the first route
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
                                        tooltip=filename  # Add hover text showing filename
                                    ).add_to(m)
                    
                    # Save map
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
    
    def add_speed_tags(self, e):
        """Add speed tags to selected routes"""
        if not self.selected_files:
            self.update_status("No files selected")
            return
        
        processed_count = 0
        
        for filename in self.selected_files:
            file_path = os.path.join(self.temp_dir, filename)
            gpx = self.processor.parse_gpx(file_path)
            
            if gpx:
                gpx = self.processor.calculate_speed(gpx)
                
                # Save with _speed suffix
                new_filename = filename.replace('.gpx', '_speed.gpx')
                new_path = os.path.join(self.temp_dir, new_filename)
                self.processor.save_gpx(gpx, new_path)
                processed_count += 1
        
        self.update_status(f"Added speed tags to {processed_count} file(s)")
        self.refresh_file_list(None)
    
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
                # First add speed if not present
                gpx = self.processor.calculate_speed(gpx)
                # Then trim (using m/s internally)
                gpx = self.processor.trim_by_speed(gpx, max_speed_ms)
                
                # Save with _trimmed suffix
                new_filename = filename.replace('.gpx', '_trimmed.gpx')
                new_path = os.path.join(self.temp_dir, new_filename)
                self.processor.save_gpx(gpx, new_path)
                processed_count += 1
        
        self.update_status(f"Trimmed {processed_count} file(s) by speed (max: {max_speed_mph} mph)")
        self.refresh_file_list(None)
    
    def post_to_hikes(self, e):
        """Post selected routes to Hikes API"""
        if not self.selected_files:
            self.update_status("No files selected")
            return
        
        api_url = self.hikes_url_field.value.strip()
        
        if not api_url:
            self.update_status("Please enter a Hikes API URL")
            return
        
        # Save API URL to persistent data
        self.persistent_data.data["hikes_api_url"] = api_url
        self.persistent_data.save()
        
        posted_count = 0
        
        for filename in self.selected_files:
            file_path = os.path.join(self.temp_dir, filename)
            
            try:
                with open(file_path, 'r') as f:
                    gpx_data = f.read()
                
                # Post to API (adjust payload structure as needed for your API)
                response = requests.post(
                    api_url,
                    files={'gpx': (filename, gpx_data, 'application/gpx+xml')},
                    timeout=30
                )
                
                if response.status_code == 200 or response.status_code == 201:
                    posted_count += 1
                    logger.info(f"Posted {filename} to Hikes API")
                else:
                    logger.error(f"Failed to post {filename}: {response.status_code}")
            
            except Exception as ex:
                logger.error(f"Error posting {filename}: {ex}")
        
        self.update_status(f"Posted {posted_count}/{len(self.selected_files)} file(s) to Hikes")
    
    def update_status(self, message: str):
        """Update status text"""
        self.status_text.value = f"{datetime.now().strftime('%H:%M:%S')} - {message}"
        self.page.update()
        logger.info(message)


def main(page: ft.Page):
    """Main entry point for the Flet app"""
    app = GPXWorkbenchApp(page)
    app.refresh_file_list(None)


if __name__ == "__main__":
    ft.app(target=main)
