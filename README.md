# ShredFinder

Automatically detect highlight moments in GoPro snowboard footage and cut clips. Analyzes embedded sensor telemetry (accelerometer, gyroscope, GPS) to find jumps, spins, speed peaks, and crashes — then cuts clips via FFmpeg with no re-encoding.

---

## Easy Setup (Non-Developers)

If you just want to use ShredFinder and don't have a coding background, follow these steps. You'll only need to do the setup once — after that it's just one command to process your footage.

### Step 1: Install Python

1. Go to https://www.python.org/downloads/
2. Click the big yellow **"Download Python"** button
3. Run the installer
4. **IMPORTANT:** Check the box that says **"Add Python to PATH"** at the bottom of the installer before clicking Install

To verify it worked, open **Command Prompt** (search "cmd" in the Start menu) and type:
```
python --version
```
You should see something like `Python 3.13.7`. If you get an error, restart your computer and try again.

### Step 2: Install FFmpeg

1. Open **Command Prompt** (search "cmd" in the Start menu)
2. Paste this command and hit Enter:
```
winget install Gyan.FFmpeg
```
3. Close and reopen Command Prompt after it finishes

### Step 3: Download ShredFinder

1. Go to https://github.com/drewkeriazes/ShredFinder
2. Click the green **"Code"** button, then click **"Download ZIP"**
3. Unzip the folder somewhere easy to find (like your Desktop or Downloads)
4. Open **Command Prompt** and navigate to the folder:
```
cd Desktop\ShredFinder-master
```
5. Install ShredFinder:
```
pip install -e .
```

### Step 4: Process Your GoPro Footage

1. Plug in your GoPro SD card or copy your `.MP4` files to a folder on your computer
2. Open **Command Prompt** and run:
```
shredfinder "D:\DCIM\100GOPRO"
```
Replace the path in quotes with wherever your GoPro files are. Right-click the folder in File Explorer and click "Copy as path" to get the exact path.

That's it! ShredFinder will:
- Scan all your GoPro files
- Find your best jumps, spins, speed runs, and crashes
- Cut clips into a `clips/` folder organized by type (jumps, spins, etc.)
- Generate a summary report

### Common Options

```
shredfinder "D:\DCIM\100GOPRO" --dry-run
```
Preview what it finds without cutting any clips (good for testing).

```
shredfinder "D:\DCIM\100GOPRO" --trail-map
```
Generate an interactive map of your GPS tracks you can open in a browser.

```
shredfinder "D:\DCIM\100GOPRO" --reel --top-n 10
```
Automatically create a highlight reel of your 10 best moments.

```
shredfinder "D:\DCIM\100GOPRO" --stats
```
See your season stats — top speed, biggest air, vertical feet, etc.

### Troubleshooting

- **"shredfinder is not recognized"** — Close and reopen Command Prompt, or try `python -m shredfinder.cli` instead
- **"python is not recognized"** — You need to reinstall Python and make sure to check "Add Python to PATH"
- **"ffmpeg not found"** — Close and reopen Command Prompt after installing FFmpeg
- **"No events detected"** — Try relaxing the detection: `shredfinder "your/path" --g-threshold 6 --min-landing-g 10`
- **Files not found** — Make sure the path points to the folder with `.MP4` files, not individual files

---

## Developer Setup

Everything below is the full technical documentation.

## Requirements

- **Python** 3.10+
- **FFmpeg** installed and on PATH (or via WinGet/Chocolatey on Windows)

## Install

```bash
# Clone and install in editable mode
git clone <repo-url>
cd ShredFinder
pip install -e .

# Verify
shredfinder --help
```

Or without installing:

```bash
pip install click pandas numpy
python -m shredfinder.cli --help
```

### Installing FFmpeg

```bash
# Windows (pick one)
winget install Gyan.FFmpeg
choco install ffmpeg

# macOS
brew install ffmpeg

# Linux
sudo apt install ffmpeg
```

## Quick Start

```bash
# Basic: detect events and cut clips
shredfinder ./footage

# Dry run first to see what it finds
shredfinder ./footage --dry-run

# Full run with all features
shredfinder ./footage --export-edl --export-gpx --trail-map --stats --reel
```

## Commands & Options

### Basic Usage

```bash
shredfinder INPUT_DIR [OPTIONS]
```

`INPUT_DIR` is a folder containing raw GoPro `.MP4` files.

### Output Options

| Flag | Description |
|------|-------------|
| `-o, --output-dir DIR` | Output directory (default: `./clips`) |
| `--no-organize` | Flat output instead of subfolders by type |
| `--dry-run` | Detect events but don't cut clips |
| `-v, --verbose` | Debug logging |

### Detection Tuning

| Flag | Default | Description |
|------|---------|-------------|
| `--g-threshold` | `4.0` | Freefall threshold (m/s²). Lower = stricter |
| `--min-airtime-sec` | `0.3` | Minimum airtime to count as a jump |
| `--min-landing-g` | `15.0` | Landing spike required to confirm a jump |
| `--min-speed-mph` | `20.0` | Speed threshold for speed events |
| `--min-spin-degrees` | `180` | Minimum rotation to detect a spin |
| `--spin-axis` | `z` | Gyro axis for spin detection (`x`, `y`, or `z`) |
| `--crash-g-threshold` | `25.0` | G-force threshold for crash detection |
| `--clip-pad-sec` | `3.0` | Seconds of padding before/after events |
| `--clip-max-sec` | `12.0` | Maximum clip duration |
| `--max-workers` | `4` | Parallel FFmpeg processes |
| `--no-chairlift-filter` | off | Disable automatic chairlift segment filtering |

### Export & Features

| Flag | Description |
|------|-------------|
| `--export-edl` | Export CMX 3600 EDL timeline for DaVinci Resolve |
| `--export-gpx` | Export GPS tracks + event waypoints as GPX |
| `--trail-map` | Generate interactive HTML map with Leaflet.js |
| `--stats` | Generate season stats (vertical feet, top speed, etc.) |
| `--reel` | Auto-generate highlight reel from top-ranked clips |
| `--top-n N` | Number of clips in highlight reel (default: 10) |

## Output Structure

```
clips/
  jumps/           Jump clips (filenames include landing quality)
  speed/           Speed peak clips
  spins/           Spin clips (filenames include degree count)
  crashes/         Crash/bail clips
  by_source/       Symlinks grouped by source MP4 file
    GX010185/
    GX010207/
  manifest.csv     Full manifest of all clips with metadata
  summary.txt      Human-readable report
  timeline.edl     DaVinci Resolve timeline (with --export-edl)
  tracks.gpx       GPS tracks + waypoints (with --export-gpx)
  trail_map.html   Interactive map (with --trail-map)
  stats.txt        Season stats text (with --stats)
  stats.json       Season stats JSON (with --stats)
  highlight_reel.mp4  Top clips concatenated (with --reel)
```

## Config File

Create `shredfinder.toml` in the project directory to set defaults:

```toml
[detection]
g_threshold = 4.0
min_airtime_sec = 0.3
min_landing_g = 15.0
min_speed_mph = 20.0
clip_pad_sec = 3.0
clip_max_sec = 12.0
min_spin_degrees = 180.0
spin_axis = "z"
crash_g_threshold = 25.0
filter_chairlift = true

[output]
output_dir = "./clips"
max_workers = 4
organize = true

[[footage]]
path = "/path/to/gopro/day1"
label = "Day 1"

[[footage]]
path = "/path/to/gopro/day2"
label = "Day 2"
```

Config is loaded from (first found):
1. `./shredfinder.toml`
2. `~/.config/shredfinder/config.toml`
3. `~/shredfinder.toml`

CLI flags override config values.

## Batch Processing

Process all directories listed in your config:

```bash
python run_all.py
```

## Event Detection

### Jumps
Detected via accelerometer freefall (magnitude < `g_threshold`) followed by a landing spike (> `min_landing_g`). GPS speed is checked to reject stationary false positives. Each jump gets a confidence score (0-1) and landing quality label (`stomped`, `sketchy`, or `crash`).

### Spins
Detected via gyroscope angular velocity integration. Requires co-occurrence with freefall to filter out ground pivots. Labels spins as 180, 360, 540, 720+ degrees.

### Speed Peaks
Sustained GPS speed above `min_speed_mph` for 2+ seconds. Filters GPS noise (rejects > 80 mph and invalid coordinates).

### Crashes
High-G spike (> `crash_g_threshold`) combined with GPS deceleration to zero and optional GYRO tumble detection. Scored by severity (0-1).

### Chairlift Filtering
GPS altitude + speed analysis automatically classifies segments as riding, chairlift, or stationary. Events during non-riding segments are filtered out. Disable with `--no-chairlift-filter`.

## Development

```bash
# Install dev dependencies
pip install -e .
pip install pytest

# Run tests
python -m pytest tests/ -v

# Run tests with coverage
python -m pytest tests/ -v --tb=short

# Run a specific test class
python -m pytest tests/test_detector.py::TestDetectSpins -v

# Quick import check
python -c "import shredfinder; print(shredfinder.__version__)"
```

## Project Structure

```
shredfinder/
  cli.py            Click CLI entry point
  scanner.py        MP4 file discovery
  telemetry.py      GPMF extraction, DataFrame building, segment classification
  gpmf_parser.py    Binary GPMF (KLV) format parser
  detector.py       Jump/spin/speed/crash detection + landing quality
  clipper.py        Parallel FFmpeg clip cutting with organized output
  report.py         CSV manifest + text summary
  config.py         TOML config file management
  session.py        Session grouping by date/location
  reel.py           Event ranking + highlight reel generation
  stats.py          Season stats aggregation
  trail_map.py      Interactive HTML trail map (Leaflet.js)
  edl_export.py     DaVinci Resolve EDL export
  gpx_export.py     GPX track + waypoint export
  footage_dirs.py   Footage directory helpers (configure via shredfinder.toml)
tests/
  test_detector.py  Detection tests (jumps, spins, crashes, landing quality)
  test_gpmf_parser.py  GPMF binary parsing tests
  test_scanner.py   File discovery tests
  test_telemetry.py DataFrame building tests (ACCL, GPS, GYRO)
```

## Examples

```bash
# Detect with relaxed thresholds (find more events)
shredfinder ./footage --g-threshold 6.0 --min-landing-g 10 --min-speed-mph 10

# Strict detection (fewer, higher quality clips)
shredfinder ./footage --g-threshold 3.0 --min-landing-g 20 --min-airtime-sec 0.5

# Just spins and jumps, no speed events
shredfinder ./footage --min-speed-mph 100

# Generate everything for a full day
shredfinder ./footage \
  --export-edl --export-gpx --trail-map --stats --reel --top-n 15

# Process with verbose debug logging
shredfinder ./footage --dry-run -v 2>debug.log
```
