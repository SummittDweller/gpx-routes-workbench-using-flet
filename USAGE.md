# Usage Guide - GPX Routes Workbench

## Quick Start

### 1. First Time Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

### 2. Basic Workflow

1. **Export iPhone Health Data** (see detailed instructions below)
2. **Import GPX Files** into the app
3. **Select Routes** you want to process
4. **Process Routes** using the available tools
5. **Post to Hikes Blog** (optional)

## Detailed Instructions

### Exporting iPhone Health Data

The app displays these instructions on startup; this section provides a detailed guide.

#### Step-by-Step Process

1. **Open Health App**
   - Launch the Health app on your iPhone
   - This is the pre-installed app with a white icon and a red heart

2. **Access Your Profile**
   - Tap your profile picture or initials in the top-right corner
   - Or tap "Summary" at the bottom and then your profile icon

3. **Initiate Export**
   - Scroll down to the "Privacy" section
   - Tap "Export All Health Data"
   - Tap "Export" to confirm

4. **Wait for Export**
   - The export process may take 5-30 minutes depending on data volume
   - You'll see a progress indicator
   - Keep the Health app open during export

5. **Share the Export**
   - When complete, tap the share icon
   - Options include:
     - **AirDrop**: Quick transfer to nearby Mac
     - **Email**: Send to yourself (may hit size limits)
     - **iCloud Drive**: Save to cloud storage
     - **Files App**: Save locally on iPhone

6. **Transfer to Computer**
   - Get the `export.zip` file to your computer
   - The file is typically 100MB-2GB depending on data

7. **Extract the Archive**
   - Unzip the `export.zip` file
   - Look for the `apple_health_export` folder
   - Inside, find the `workout-routes` subfolder
   - This contains your GPX files!

### Using the Application

#### Importing GPX Files

1. **Click "📁 Select GPX Files"**
   - Opens a file picker dialog
   - Navigate to your `workout-routes` folder
   - Select one or more `.gpx` files
   - Click "Open"

2. **Files Are Copied**
   - Selected files are copied to `temp_gpx_routes/` directory
   - Original files remain unchanged
   - Work with copies safely

#### Selecting Routes

**Individual Selection:**
- Click checkboxes next to route filenames
- Selected routes are highlighted

**Bulk Selection:**
- **Select All**: Checks all route checkboxes
- **Deselect All**: Unchecks all checkboxes
- Useful when working with many files

**Refresh List:**
- Click "🔄 Refresh List" to update the file list
- Useful after manually adding/removing files from temp directory

#### Processing Operations

##### 1. Visualize Routes (🗺️)

**What it does:**
- Creates an interactive HTML map
- Displays all selected routes in different colors
- Each route is a colored line on the map

**How to use:**
1. Select one or more routes
2. Click "🗺️ Visualize Routes"
3. Map saved to `temp_gpx_routes/routes_map.html`
4. Open the HTML file in any web browser

**Use cases:**
- Compare multiple workout routes
- Identify route patterns
- Verify GPS data quality

##### 2. Add Speed Tags (⚡)

**What it does:**
- Calculates speed between consecutive GPS points
- Adds speed data to trackpoints
- Speed calculated in meters per second (m/s)

**How to use:**
1. Select routes to process
2. Click "⚡ Add Speed Tags"
3. New files created with `_speed.gpx` suffix

**Example:**
- Original: `run_2024-01-15.gpx`
- New file: `run_2024-01-15_speed.gpx`

**Speed Calculation:**
```
Speed (m/s) = Distance / Time
- Distance: 3D distance between points (if elevation available)
- Time: Difference in timestamps
```

##### 3. Trim by Speed (✂️)

**What it does:**
- Removes GPS points with unrealistic speeds
- Filters out GPS errors and glitches
- Default threshold: 5 mph

**How to use:**
1. Set max speed in "Max Speed (MPH)" field
2. Select routes to trim
3. Click "✂️ Trim by Speed"
4. New files created with `_trimmed.gpx` suffix

**Speed Reference:**
- Walking: 2-4 mph
- Running: 5-12 mph
- Cycling: 8-25 mph
- Driving: 25-70 mph
- Highway: 55-80 mph

**Recommended thresholds:**
- Walking/Hiking: 5-10 mph
- Running: 12-20 mph
- Cycling: 20-35 mph
- Mixed activities: 15-30 mph

##### 4. Post to Hikes Blog (📤)

**What it does:**
- Generates hike markdown files in your local Hikes repo
- Copies GPX files to the Hikes static gpx directory
- Performs git pull/add/commit/push in the Hikes repo
- Adds reverse-geocoded location and historical weather to generated frontmatter

**How to use:**
1. Ensure your Hikes repository exists at `~/GitHub/hikes`
2. Select routes to post
3. Click "📤 Post to Hikes Blog"

**Output Paths:**
- Markdown: `~/GitHub/hikes/content/hikes/YYYY/MM/*.md`
- GPX: `~/GitHub/hikes/static/gpx/YYYY/MM/*.gpx`

**Git Behavior:**
- Runs `git pull`, `git add .`, `git commit`, and `git push` after posting files.

**Weather Details:**
- During posting, the app looks up historical weather near the GPX track center and first timestamp using the Open-Meteo archive API.
- If lookup fails or data is incomplete, it falls back to `Weather data not available`.

### File Management

#### Temporary Directory

**Location:** `temp_gpx_routes/`

**Purpose:**
- Working directory for imported files
- Processed files stored here
- Safe to delete contents when done

**Clear Temp Directory:**
- Click "🗑️ Clear Temp Directory"
- Removes all files from temp folder
- Useful for starting fresh

#### File Naming Conventions

**Original:** `route.gpx`
**With speed:** `route_speed.gpx`
**Trimmed:** `route_trimmed.gpx`
**Both:** `route_speed_trimmed.gpx`

### Persistent Data

**Saved Settings:**
- Temporary directory path
- Selected files
- Last export date

**File:** `app_data.json`

**Auto-saved when:**
- File selections change
- App exits normally

### Logging

**Log File:** `gpx_workbench.log`

**Contents:**
- All operations performed
- Errors and warnings
- File processing details
- Timestamps for all events

**Useful for:**
- Debugging issues
- Auditing operations
- Understanding what happened

## Tips and Tricks

### Best Practices

1. **Start Small**
   - Import a few files first
   - Test processing on 1-2 routes
   - Scale up once familiar

2. **Keep Originals**
   - Never delete your `export.zip`
   - Keep a backup of workout-routes folder
   - App works with copies, not originals

3. **Process in Steps**
   - Add speed tags first
   - Visualize to check data
   - Then trim if needed
   - Finally post to Hikes Blog

4. **Check the Map**
   - Always visualize before posting
   - Look for GPS errors (straight lines, jumps)
   - Verify route makes sense

5. **Use Appropriate Speed Thresholds**
   - Walking: 5-10 mph
   - Running: 12-20 mph
   - Cycling: 20-35 mph
   - Mixed activities: 15-30 mph

### Common Issues

**Problem:** No files appear after import
- **Solution:** Click "🔄 Refresh List"

**Problem:** Map doesn't open
- **Solution:** Manually open `temp_gpx_routes/routes_map.html` in browser

**Problem:** Processing fails
- **Solution:** Check `gpx_workbench.log` for errors

**Problem:** App won't start
- **Solution:** Run `pip install -r requirements.txt` again

### Advanced Usage

#### Batch Processing

Process multiple routes efficiently:
1. Import all routes
2. Select All
3. Add Speed Tags → Creates `_speed.gpx` files
4. Deselect All
5. Select only `_speed.gpx` files (manually)
6. Trim by Speed → Creates `_trimmed.gpx` files
7. Select trimmed files
8. Post to Hikes Blog

#### Manual File Management

You can manually add GPX files to `temp_gpx_routes/`:
1. Copy `.gpx` files to the directory
2. Click "🔄 Refresh List" in the app
3. Files appear in the list

#### Customizing the Map

Edit `main.py` to customize map appearance:
- Change route colors
- Adjust zoom level
- Add markers or popups
- Change map tile provider

## Examples

### Example 1: Basic Route Visualization

```
1. Import: morning_run.gpx
2. Select: Check the checkbox
3. Click: 🗺️ Visualize Routes
4. Open: temp_gpx_routes/routes_map.html
```

### Example 2: Clean GPS Data

```
1. Import: bike_ride.gpx
2. Select: bike_ride.gpx
3. Click: ⚡ Add Speed Tags
4. Select: bike_ride_speed.gpx
5. Set max speed: 30 mph (for cycling)
6. Click: ✂️ Trim by Speed
7. Result: bike_ride_speed_trimmed.gpx (cleaned)
```

### Example 3: Batch Post to Hikes

```
1. Import: Multiple hike files
2. Click: Select All
3. Add speed tags to all
4. Click: Deselect All
5. Manually select: *_speed.gpx files
6. Click: ✂️ Trim by Speed (max: 10 mph)
7. Select: *_trimmed.gpx files
8. Click: 📤 Post to Hikes Blog
```

## Keyboard Shortcuts

No app-specific shortcuts are currently implemented. Standard controls still work:
- **Tab**: Navigate between controls
- **Space**: Toggle checkboxes
- **Enter**: Activate buttons

## Getting Help

If you encounter issues:
1. Check `gpx_workbench.log`
2. Run `python test_gpx.py` to verify installation
3. Run `python test_integration.py` for full test
4. Check GitHub issues
5. File a new issue with log details

## Next Steps

After mastering the basics:
- Explore GPX file formats
- Learn about GPS accuracy
- Understand speed calculations
- Customize the application
- Contribute improvements!
