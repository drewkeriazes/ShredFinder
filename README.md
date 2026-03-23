# ShredFinder

Automatically detect highlight moments in GoPro snowboard footage and cut clips. Analyzes embedded sensor telemetry (accelerometer, gyroscope, GPS) to find jumps, spins, speed peaks, and crashes — then cut clips via FFmpeg with no re-encoding.

Includes a **web-based video editor** for assembling detected clips into polished edits with a DaVinci Resolve-style interface.

---

## Web Editor (New)

A full-featured browser-based video editor built on top of ShredFinder's detection engine.

### Features

- **Auto-Detection** — Upload GoPro footage, ShredFinder detects jumps, spins, speed peaks, and crashes automatically
- **Timeline Editor** — Multi-track timeline with drag-and-drop, trim, split, and reorder
- **Preview Player** — Real-time video playback synced to the timeline
- **Clip Library** — Browse detected clips by type, filter, sort by confidence
- **Inspector** — Adjust speed, volume, opacity per clip
- **Export** — Server-side FFmpeg rendering with transitions
- **Keyboard Shortcuts** — Space (play/pause), J/K/L (shuttle), arrows (frame step), Ctrl+Z/Y (undo/redo)
- **Multi-User** — JWT authentication, per-user storage and projects
- **Dark Theme** — DaVinci Resolve-inspired dark UI

### Quick Start

```bash
# 1. Install Python dependencies
pip install -e .
pip install "fastapi[standard]" "uvicorn[standard]" "sqlalchemy[asyncio]" \
    aiosqlite "python-jose[cryptography]" bcrypt python-multipart \
    pydantic-settings websockets aiofiles

# 2. Install frontend dependencies
cd web && npm install && cd ..

# 3. Start the backend (Terminal 1)
python -m uvicorn server.main:app --reload

# 4. Start the frontend (Terminal 2)
cd web && npm run dev
```

Open **http://localhost:5173** — register an account, upload GoPro footage, and start editing.

The API docs are at **http://localhost:8000/docs** (Swagger UI).

### Architecture

```
Browser (React + TypeScript)          Python Backend (FastAPI)
┌─────────────────────────┐           ┌──────────────────────┐
│ Clip Library             │           │ ShredFinder Pipeline │
│ Timeline Editor          │  REST +   │ FFmpeg Processing    │
│ Preview Player           │◄─────────►│ JWT Auth             │
│ Inspector Panel          │  WebSocket│ SQLite Database      │
│ Zustand State Management │           │ File Storage         │
└─────────────────────────┘           └──────────────────────┘
```

### File Storage Layout

All uploaded and processed files are organized per-user, per-media:

```
server/data/
  shredfinder.db                              # SQLite database
  users/
    {user_id}/
      media/
        {media_id}/
          original.mp4                        # Uploaded GoPro file
          proxy.mp4                           # 720p editing proxy
          thumbnail.jpg                       # Poster frame
      renders/
        {job_id}.mp4                          # Exported videos
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS v4 |
| State | Zustand (timeline, auth, media, projects) |
| UI | Radix UI, Lucide icons, react-resizable-panels, dnd-kit |
| Backend | FastAPI, SQLAlchemy (async), aiosqlite |
| Auth | JWT (python-jose), bcrypt |
| Video | FFmpeg (subprocess), ffprobe |
| Real-time | WebSocket (progress updates) |

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/login` | Get JWT token (OAuth2 form) |
| GET | `/api/auth/me` | Current user profile |
| GET | `/api/media` | List uploaded media |
| POST | `/api/media/upload` | Upload video file |
| GET | `/api/media/{id}/stream` | Stream original video |
| GET | `/api/media/{id}/thumbnail` | Serve thumbnail |
| GET | `/api/media/{id}/proxy` | Serve proxy video |
| POST | `/api/detection/run/{media_id}` | Trigger ShredFinder detection |
| GET | `/api/detection/results/{media_id}` | Get detected clips |
| GET/POST | `/api/projects` | List/create projects |
| GET/PUT/DELETE | `/api/projects/{id}` | Project CRUD |
| POST | `/api/render` | Submit timeline for export |
| GET | `/api/render/{job_id}/status` | Render progress |
| GET | `/api/render/{job_id}/download` | Download rendered video |

---

## CLI Tool

The original command-line tool for batch processing GoPro footage.

### Easy Setup (Non-Developers)

If you just want to use ShredFinder and don't have a coding background, follow these steps. You'll only need to do the setup once — after that it's just one command to process your footage.

#### Step 1: Install Python

1. Go to https://www.python.org/downloads/
2. Click the big yellow **"Download Python"** button
3. Run the installer
4. **IMPORTANT:** Check the box that says **"Add Python to PATH"** at the bottom of the installer before clicking Install

To verify it worked, open **Command Prompt** (search "cmd" in the Start menu) and type:
```
python --version
```
You should see something like `Python 3.13.7`. If you get an error, restart your computer and try again.

#### Step 2: Install FFmpeg

1. Open **Command Prompt** (search "cmd" in the Start menu)
2. Paste this command and hit Enter:
```
winget install Gyan.FFmpeg
```
3. Close and reopen Command Prompt after it finishes

#### Step 3: Download ShredFinder

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

#### Step 4: Process Your GoPro Footage

1. Plug in your GoPro SD card or copy your `.MP4` files to a folder on your computer
2. Open **Command Prompt** and run:
```
shredfinder "D:\DCIM\100GOPRO"
```
Replace the path in quotes with wherever your GoPro files are. Right-click the folder in File Explorer and click "Copy as path" to get the exact path.

That's it! ShredFinder will:
- Scan all your GoPro files
- Find your best jumps, spins, speed runs, and crashes
- Cut clips into a `clips/run_<timestamp>_<id>/` folder organized by type
- Generate a summary report

Each run gets its own folder with a unique ID so you can compare different runs and settings without overwriting previous results.

### Common Options

```bash
shredfinder "D:\DCIM\100GOPRO" --dry-run          # Preview without cutting
shredfinder "D:\DCIM\100GOPRO" --trail-map         # Interactive GPS map
shredfinder "D:\DCIM\100GOPRO" --reel --top-n 10   # Highlight reel of top 10
shredfinder "D:\DCIM\100GOPRO" --stats              # Season statistics
```

### Troubleshooting

- **"shredfinder is not recognized"** — Close and reopen Command Prompt, or try `python -m shredfinder` instead
- **"python is not recognized"** — You need to reinstall Python and make sure to check "Add Python to PATH"
- **"ffmpeg not found"** — Close and reopen Command Prompt after installing FFmpeg
- **"No events detected"** — Try relaxing the detection: `shredfinder "your/path" --g-threshold 6 --min-landing-g 10`
- **Files not found** — Make sure the path points to the folder with `.MP4` files, not individual files

---

## Developer Setup

### Requirements

- **Python** 3.10+
- **FFmpeg** installed and on PATH
- **Node.js** 18+ (for web editor)

### Install

```bash
# Clone and install
git clone <repo-url>
cd ShredFinder
pip install -e .

# Verify CLI
shredfinder --help

# Install web editor dependencies
cd web && npm install && cd ..
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

## CLI Usage

```bash
# Basic: detect events and cut clips
shredfinder ./footage

# Dry run first to see what it finds
shredfinder ./footage --dry-run

# Full run with all features
shredfinder ./footage --export-edl --export-gpx --trail-map --stats --reel
```

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

Each run creates a unique folder with a timestamp and ID:

```
clips/
  run_20260321_143000_a3f8c1b2/
    run.json           Run metadata (ID, settings, results)
    manifest.csv       Full manifest of all clips with metadata
    summary.txt        Human-readable report
    jumps/             Jump clips (filenames include landing quality)
    speed/             Speed peak clips
    spins/             Spin clips (filenames include degree count)
    crashes/           Crash/bail clips
    by_source/         Symlinks grouped by source MP4 file
    timeline.edl       DaVinci Resolve timeline (with --export-edl)
    tracks.gpx         GPS tracks + waypoints (with --export-gpx)
    trail_map.html     Interactive map (with --trail-map)
    stats.txt          Season stats text (with --stats)
    stats.json         Season stats JSON (with --stats)
    highlight_reel.mp4 Top clips concatenated (with --reel)
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
```

Config is loaded from (first found):
1. `./shredfinder.toml`
2. `~/.config/shredfinder/config.toml`
3. `~/shredfinder.toml`

CLI flags override config values.

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

## Project Structure

```
ShredFinder/
  shredfinder/              # CLI detection pipeline
    cli.py                  Click CLI entry point
    scanner.py              MP4 file discovery
    telemetry.py            GPMF extraction, DataFrame building
    gpmf_parser.py          Binary GPMF (KLV) format parser
    detector.py             Jump/spin/speed/crash detection
    clipper.py              Parallel FFmpeg clip cutting
    report.py               CSV manifest + text summary
    config.py               TOML config management
    session.py              Session grouping by date/location
    reel.py                 Highlight reel generation
    stats.py                Season stats aggregation
    trail_map.py            Interactive HTML trail map
    edl_export.py           DaVinci Resolve EDL export
    gpx_export.py           GPX track + waypoint export
  server/                   # Web editor backend
    main.py                 FastAPI app, WebSocket, CORS
    config.py               Settings (pydantic-settings)
    api/                    REST endpoints
      auth.py               Register, login, JWT
      media.py              Upload, stream, thumbnail, proxy
      detection.py          Trigger ShredFinder, get results
      projects.py           Project CRUD
      render.py             Export/render jobs
    models/                 SQLAlchemy ORM
      user.py               User accounts
      media.py              Uploaded media files
      project.py            Projects, clips
    services/               Business logic
      ffmpeg.py             FFmpeg command runner
      proxy.py              Proxy/thumbnail generation
      renderer.py           Timeline rendering
      storage.py            File storage abstraction
    tasks/                  Background tasks
      detection.py          ShredFinder pipeline runner
      proxy.py              Proxy/thumbnail tasks
      render.py             Render tasks
  web/                      # Web editor frontend
    src/
      components/           React UI components
        Auth/               Login/register page
        Layout/             App shell, toolbar
        Library/            Clip browser, upload
        Timeline/           Tracks, clips, playhead
        Preview/            Video player
        Inspector/          Clip properties
      stores/               Zustand state management
      services/             API client, WebSocket
      hooks/                Keyboard shortcuts, timeline helpers
      types/                TypeScript interfaces
  tests/                    CLI detection tests
```

## Development

```bash
# Run CLI tests
python -m pytest tests/ -v

# Start web editor (dev mode)
python -m uvicorn server.main:app --reload   # backend
cd web && npm run dev                         # frontend

# Build frontend for production
cd web && npm run build
```
