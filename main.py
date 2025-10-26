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
from datetime import datetime
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
    def trim_by_speed(gpx: gpxpy.gpx.GPX, max_speed: float = 50.0) -> gpxpy.gpx.GPX:
        """Remove points with excessive speed (default: 50 m/s ~= 180 km/h)"""
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
        
        self.build_ui()
    
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
    
    def create_instructions_section(self) -> ft.Container:
        """Create instructions for exporting iPhone health data"""
        instructions_text = """
How to Export Health Data from Your iPhone:

1. Open the Health app on your iPhone
2. Tap your profile picture or initials in the top right
3. Scroll down and tap "Export All Health Data"
4. Wait for the export to complete (may take several minutes)
5. Share the export.zip file to your computer (via AirDrop, email, or cloud storage)
6. Extract the export.zip file on your computer
7. Inside the extracted folder, look for the "workout-routes" folder
8. Use the file picker below to select and import the GPX route files

Note: The workout-routes folder contains individual .gpx files for each recorded workout with GPS data.
        """
        
        return ft.Container(
            content=ft.Column([
                ft.Text("📱 iPhone Health Data Export Instructions", 
                       size=20, weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_700),
                ft.Text(instructions_text, size=14, selectable=True),
            ]),
            padding=15,
            bgcolor=ft.colors.GREEN_50,
            border_radius=10,
            border=ft.border.all(2, ft.colors.GREEN_200)
        )
    
    def create_file_picker_section(self) -> ft.Container:
        """Create file picker section"""
        
        # File picker dialogs
        self.pick_files_dialog = ft.FilePicker(on_result=self.on_files_selected)
        self.page.overlay.append(self.pick_files_dialog)
        
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
        
        return ft.Container(
            content=ft.Column([
                ft.Text("Import GPX Files", size=20, weight=ft.FontWeight.BOLD),
                ft.Row([pick_files_button, clear_temp_button], spacing=10),
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
        
        add_speed_button = ft.ElevatedButton(
            "⚡ Add Speed Tags",
            icon=ft.icons.SPEED,
            on_click=self.add_speed_tags,
            style=ft.ButtonStyle(
                color=ft.colors.WHITE,
                bgcolor=ft.colors.ORANGE_700
            )
        )
        
        self.max_speed_field = ft.TextField(
            label="Max Speed (m/s)",
            value="50",
            width=150,
            hint_text="Default: 50 m/s"
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
        
        self.hikes_url_field = ft.TextField(
            label="Hikes API URL",
            value=self.persistent_data.data.get("hikes_api_url", ""),
            expand=True,
            hint_text="https://api.example.com/hikes"
        )
        
        post_hikes_button = ft.ElevatedButton(
            "📤 Post to Hikes",
            icon=ft.icons.UPLOAD,
            on_click=self.post_to_hikes,
            style=ft.ButtonStyle(
                color=ft.colors.WHITE,
                bgcolor=ft.colors.INDIGO_700
            )
        )
        
        return ft.Container(
            content=ft.Column([
                ft.Text("Processing Controls", size=20, weight=ft.FontWeight.BOLD),
                ft.Row([map_button, add_speed_button], spacing=10),
                ft.Row([self.max_speed_field, trim_button], spacing=10),
                ft.Row([self.hikes_url_field, post_hikes_button], spacing=10),
                self.map_output
            ]),
            padding=15,
            bgcolor=ft.colors.AMBER_50,
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
    
    def refresh_file_list(self, e):
        """Refresh the list of GPX files"""
        self.files_list_view.controls.clear()
        self.file_checkboxes.clear()
        
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir, exist_ok=True)
            return
        
        gpx_files = [f for f in os.listdir(self.temp_dir) if f.endswith('.gpx')]
        gpx_files.sort()
        
        if not gpx_files:
            self.files_list_view.controls.append(
                ft.Text("No GPX files found in temp directory", italic=True, color=ft.colors.GREY_700)
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
                                    folium.PolyLine(points, color=color, weight=3, opacity=0.7, 
                                                   popup=filename).add_to(m)
                    
                    # Save map
                    map_file = os.path.join(self.temp_dir, "routes_map.html")
                    m.save(map_file)
                    
                    self.update_status(f"Map created: {map_file}")
                    self.map_output.value = f"✅ Map saved to: {map_file}\nOpen this file in a web browser to view the routes."
                    logger.info(f"Map created with {len(self.selected_files)} routes")
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
            max_speed = float(self.max_speed_field.value)
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
                # Then trim
                gpx = self.processor.trim_by_speed(gpx, max_speed)
                
                # Save with _trimmed suffix
                new_filename = filename.replace('.gpx', '_trimmed.gpx')
                new_path = os.path.join(self.temp_dir, new_filename)
                self.processor.save_gpx(gpx, new_path)
                processed_count += 1
        
        self.update_status(f"Trimmed {processed_count} file(s) by speed")
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
