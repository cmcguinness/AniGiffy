# AniGiffy

A web-based animated GIF creator with a Flask backend and Bootstrap 5 frontend. Upload images or import video frames, arrange them, align their backgrounds, and generate optimized GIFs (or APNGs) directly in your browser.

## Features

- **Image Upload**: PNG, JPEG (including `.jfif`/`.jpe` and camera MPO files), GIF and WebP,
  with an always-visible drag-drop target. Images larger than the maximum dimension are scaled
  down automatically rather than rejected
- **Video Import**: Pull frames out of an MP4 or MOV at a chosen frame rate (requires ffmpeg)
- **Frame Management**: Add, remove, and reorder frames with drag-and-drop
- **Auto-Align Backgrounds**: Feature-based registration (OpenCV) shifts, scales and rotates
  frames so their backgrounds line up, then crops to the area every frame covers. Frames that
  don't match the reference are reported and left untouched
- **Auto-Detect Dimensions**: Output size automatically set from the largest uploaded image
- **Auto-Detect Transparency**: Transparency mode enabled automatically if first image has alpha channel
- **Scale Control**: Scale output to a preset percentage (100/75/66/50/33/25/10%) of the
  original dimensions, or type exact width/height values
- **Output Format**: Animated GIF or animated PNG (APNG, with full alpha)
- **Transparency Support**: Create GIFs with transparent backgrounds
- **Multiple Transition Types**:
  - Cross-fade (smooth blend between images)
  - Motion Tween (fits the camera movement between two frames and steps along it, so the
    scene slides instead of dissolving)
  - Motion Morph (moves each pixel along its own optical-flow vector, so a subject that
    moved actually travels across the in-between frames)
  - Fade to White/Black (fade through intermediate color)
  - Carousel (slide in four directions: Left, Right, Up, Down)
  - Configurable timing and steps for all transitions
- **Download Frames as PNGs**: Export the current frame images as a ZIP of PNG files. Run
  Auto-Align first to get the aligned, common-area-cropped versions. Files are numbered in
  animation order and keep the name you uploaded them under (`01_IMG_1764.png`).
- **Lossless alignment**: Auto-Align writes its results as PNG rather than re-encoding to
  JPEG, so the warp isn't compounded by a second round of compression loss. A frame
  uploaded as a JPEG is replaced by a `.png`, which is roughly six times the size — hence
  the 1GB session storage quota. Alignment refuses up front if the result wouldn't fit.
- **Tabbed Settings UI**: Organized into Size, Transparency, and Transitions tabs
- **Intelligent Preview System**:
  - Single "Preview" button for projects with 10 or fewer frames
  - Separate "Quick Preview" and "Full Preview" buttons for larger projects
- **Ping-Pong Playback**: Play frames forward then backward (A, B, C, D, C, B) before looping
- **Auto-Download**: Generated GIFs download automatically
- **Multi-User Safe**: Session-based isolation with automatic cleanup
- **Rate Limiting**: Built-in protection against abuse
- **Resource Quotas**: Configurable limits on uploads, storage, and output size

## Installation

### Prerequisites

- Python 3.10+
- pip
- ffmpeg (optional — needed only for Video Import)

### Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd AniGiffy
   ```

2. Create a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the application:
   ```bash
   python app.py
   ```

5. Open your browser to `http://127.0.0.1:5173`

## Usage

1. **Upload Images**: Click the "Add Image" placeholder or drag and drop images onto it to upload one or more image files. Or use **Import Video** to extract frames from an MP4/MOV
2. **Arrange Frames**: Drag and drop frames to reorder them
3. **Align Backgrounds** (optional): Click **Auto-Align** to shift, scale and rotate every frame
   onto the first one so their backgrounds line up, then crop to the area they all cover. Built
   for a series shot from nearly the same spot; frames that don't match are reported and left
   alone. This rewrites the uploaded images, so re-running it crops further each time
4. **Adjust Timing**: Set the duration (in milliseconds) for each frame, or use **Apply All** to
   give every frame the same duration
5. **Configure Settings** (organized in tabs):
   - **Size Tab**:
     - **Format**: Animated GIF or Animated PNG
     - **Output Scale**: 100%, 75%, 66%, 50%, 33%, 25% or 10% of the original size — or set width/height directly
     - **Loop Count**: 0 for infinite loop, or specify a number of plays
     - **Ping-pong**: Play forward then backward (A, B, C, D, C, B) before looping
     - **Dithering** (GIF only): how the 256-colour palette handles smooth gradients.
       *None* is smallest but can leave stair-steps on plain walls and skies. *Ordered*
       breaks those up with a fixed Bayer pattern that stays put frame to frame, so it is
       the safe choice for animation. *Floyd–Steinberg* is smoothest on a single image but
       its noise pattern crawls during transitions and makes the largest file
   - **Transparency Tab**:
     - **Transparent GIF**: Enable for transparency support
     - **Background Color**: Fill color for non-transparent GIFs
     - **Alpha Threshold**: Pixels below this opacity become transparent
   - **Transitions Tab**:
     - **Transition Type**: Choose Cross-fade, Motion Tween, Motion Morph, Fade to
       White/Black, or Carousel (Left/Right/Up/Down)
     - **Transition Time**: Transition duration in milliseconds (0 = no transitions)
     - **Transition Steps**: Number of intermediate frames in transition. Steps are capped
       at one per 20ms of transition time for GIF (10ms for APNG), because neither format
       can hold a shorter delay. The motion transitions want at least 8 steps to look
       smooth, so give them 160ms or more.

   **About the motion transitions.** Both build genuine in-between frames rather than
   blending. *Motion Tween* fits a single similarity transform (shift, rotation, scale)
   between the two frames and moves a fraction of the way along it — it only models
   whole-frame camera movement, but it can never smear. *Motion Morph* estimates a dense
   optical flow field and moves each pixel individually, which is far more expressive but
   depends on the motion being trackable: it works best on modest movement over textured
   subjects, and degrades to a cross-fade where it can't follow what moved. Neither is
   destructive — if no reliable motion can be estimated, the transition falls back to a
   cross-fade.
6. **Preview**:
   - **10 or fewer frames**: Single "Preview" button generates all frames
   - **More than 10 frames**: "Quick Preview" (first 10 frames) or "Full Preview" (all frames)
7. **Stop**: Stop the preview animation
8. **Generate GIF**: Create and automatically download the final animation

## Configuration

Edit `config.py` to customize:

### Resource Quotas

```python
QUOTAS = {
    'max_upload_size': 25 * 1024 * 1024,      # 25MB per image
    'max_total_storage': 1024 * 1024 * 1024,  # 1GB total per session
    'max_images': 200,                         # Max images per project
    'max_frames': 200,                         # Max frames in animation
    'max_output_size': 200 * 1024 * 1024,     # 200MB max output
    'max_dimension': 4096,                     # Max width/height (4K).
                                               # Larger uploads are scaled down
                                               # to fit, not rejected.
    'max_projects': 10,                        # Max projects per session
    'max_video_size': 100 * 1024 * 1024,      # 100MB per video upload
    'max_video_duration': 120,                 # seconds
}
```

### Rate Limits

These are applied by the route decorators, which read this dict directly, so
`config.py` is the only place to change them.

```python
RATE_LIMITS = {
    'upload': '120 per minute, 600 per hour',
    'generate': '5 per minute, 20 per hour',
    'save_project': '30 per minute',
    'general_api': '100 per minute',
    'video_upload': '3 per minute, 10 per hour',
    'align': '3 per minute, 20 per hour',
    'export': '6 per minute, 30 per hour',
}
```

### Session Cleanup

```python
CLEANUP_CONFIG = {
    'session_lifetime': 168,   # Hours (1 week) before session data is deleted
    'cleanup_interval': 24,    # Hours between cleanup runs
    'orphan_file_age': 24,     # Hours before unreferenced files are removed
}
```

### Alignment

```python
ALIGN_MAX_FRAMES = 60          # Most frames one align request may process
```

## Project Structure

```
AniGiffy/
├── app.py                 # Flask application entry point
├── config.py              # Configuration settings
├── extensions.py          # Shared Flask extensions (rate limiter)
├── requirements.txt       # Python dependencies
├── Dockerfile             # Container build (installs ffmpeg)
├── Procfile               # Process definition for gunicorn
├── models/
│   └── project.py         # Project and Frame data models
├── routes/
│   ├── frames.py          # Frame/upload/align endpoints
│   ├── generate.py        # GIF generation endpoints
│   └── video.py           # Video upload and frame extraction endpoints
├── services/
│   ├── session_manager.py # Session isolation and cleanup
│   ├── quota_manager.py   # Resource limit enforcement
│   ├── image_processor.py # Image validation and transformation
│   ├── image_aligner.py   # OpenCV background alignment
│   ├── video_processor.py # ffmpeg probing and frame extraction
│   └── gif_builder.py     # GIF/APNG creation with Pillow
├── static/
│   ├── css/style.css      # Custom styles
│   └── js/app.js          # Frontend JavaScript
├── user_data/             # Per-session storage (auto-created)
└── templates/
    ├── base.html          # Base template with Bootstrap 5
    └── index.html         # Main editor interface
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Main editor interface |
| POST | `/api/frames/upload` | Upload an image |
| POST | `/api/frames/align` | Align frame backgrounds (rewrites the image files) |
| POST | `/api/frames/add` | Add a frame to the project |
| PUT | `/api/frames/<frame_id>` | Update a frame's properties |
| DELETE | `/api/frames/<frame_id>` | Delete a frame |
| PUT | `/api/frames/reorder` | Reorder frames |
| GET | `/api/frames/image/<filename>` | Serve uploaded image |
| GET | `/api/frames/list` | List uploaded images |
| POST | `/api/video/upload` | Upload a video for frame extraction |
| POST | `/api/video/extract` | Extract frames from an uploaded video |
| POST | `/api/generate/preview` | Generate preview animation |
| POST | `/api/generate/full` | Generate full animation |
| GET | `/api/generate/file/<filename>` | Serve generated animation |
| GET | `/api/generate/download/<filename>` | Download generated animation |
| GET | `/api/generate/list` | List generated animations |

## Dependencies

- **Flask** - Web framework
- **Pillow** - Image processing and GIF/APNG creation
- **OpenCV** (`opencv-python-headless`) + **NumPy** - Feature detection and warping for Auto-Align
- **Flask-Limiter** - Rate limiting
- **Flask-Session** - Server-side sessions
- **APScheduler** - Background cleanup tasks
- **gunicorn** - Production WSGI server

External tools:

- **ffmpeg** / **ffprobe** - Required for Video Import only. The rest of the app works without it

## Production Deployment

For production use:

1. Set a secure `SECRET_KEY` environment variable
2. Use a production WSGI server (gunicorn, uWSGI)
3. Configure a reverse proxy (nginx, Apache)
4. Consider using Redis for session storage and rate limiting
5. Set `DEBUG = False` in config

Example with gunicorn:
```bash
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

## License

MIT License
