# AniGiffy

A web-based animated GIF creator with a Flask backend and Bootstrap 5 frontend. Upload images, arrange frames, and generate optimized GIFs directly in your browser.

## Features

- **Image Upload**: Support for PNG, JPEG, GIF, and WebP formats with always-visible drag-drop target
- **Frame Management**: Add, remove, and reorder frames with drag-and-drop
- **Auto-Detect Dimensions**: Output size automatically set from first uploaded image
- **Auto-Detect Transparency**: Transparency mode enabled automatically if first image has alpha channel
- **Scale Control**: Scale output from 10% to 100% of original dimensions
- **Transparency Support**: Create GIFs with transparent backgrounds
- **Multiple Transition Types**:
  - Cross-fade (smooth blend between images)
  - Fade to White/Black (fade through intermediate color)
  - Carousel (slide in four directions: Left, Right, Up, Down)
  - Configurable timing and steps for all transitions
- **Tabbed Settings UI**: Organized into Size, Transparency, and Transitions tabs
- **Intelligent Preview System**:
  - Single "Preview" button for projects with 10 or fewer frames
  - Separate "Quick Preview" and "Full Preview" buttons for larger projects
- **Auto-Download**: Generated GIFs download automatically
- **Multi-User Safe**: Session-based isolation with automatic cleanup
- **Rate Limiting**: Built-in protection against abuse
- **Resource Quotas**: Configurable limits on uploads, storage, and output size

## Installation

### Prerequisites

- Python 3.10+
- pip

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

1. **Upload Images**: Click the "Add Image" placeholder or drag and drop images onto it to upload one or more image files
2. **Arrange Frames**: Drag and drop frames to reorder them
3. **Adjust Timing**: Set the duration (in milliseconds) for each frame
4. **Configure Settings** (organized in tabs):
   - **Size Tab**:
     - **Output Scale**: Choose from 10% to 100% of original image size
     - **Loop Count**: 0 for infinite loop, or specify a number of plays
   - **Transparency Tab**:
     - **Transparent GIF**: Enable for transparency support
     - **Background Color**: Fill color for non-transparent GIFs
     - **Alpha Threshold**: Pixels below this opacity become transparent
   - **Transitions Tab**:
     - **Transition Type**: Choose Cross-fade, Fade to White/Black, or Carousel (Left/Right/Up/Down)
     - **Transition Time**: Transition duration in milliseconds (0 = no transitions)
     - **Transition Steps**: Number of intermediate frames in transition
5. **Preview**:
   - **10 or fewer frames**: Single "Preview" button generates all frames
   - **More than 10 frames**: "Quick Preview" (first 10 frames) or "Full Preview" (all frames)
6. **Stop**: Stop the preview animation
7. **Generate GIF**: Create and automatically download the final animated GIF

## Configuration

Edit `config.py` to customize:

### Resource Quotas

```python
QUOTAS = {
    'max_upload_size': 10 * 1024 * 1024,      # 10MB per image
    'max_total_storage': 50 * 1024 * 1024,    # 50MB total per session
    'max_images': 50,                          # Max images per session
    'max_frames': 200,                         # Max frames in animation
    'max_output_size': 20 * 1024 * 1024,      # 20MB max GIF
    'max_dimension': 2000,                     # Max width/height
}
```

### Rate Limits

```python
RATE_LIMITS = {
    'upload': '10 per minute, 50 per hour',
    'generate': '5 per minute, 20 per hour',
    'general_api': '100 per minute',
}
```

### Session Cleanup

```python
CLEANUP_CONFIG = {
    'session_lifetime': 168,   # Hours (1 week) before session data is deleted
    'cleanup_interval': 24,    # Hours between cleanup runs
}
```

## Project Structure

```
AniGiffy/
├── app.py                 # Flask application entry point
├── config.py              # Configuration settings
├── extensions.py          # Shared Flask extensions (rate limiter)
├── requirements.txt       # Python dependencies
├── models/
│   └── project.py         # Project and Frame data models
├── routes/
│   ├── frames.py          # Frame/upload endpoints
│   └── generate.py        # GIF generation endpoints
├── services/
│   ├── session_manager.py # Session isolation and cleanup
│   ├── quota_manager.py   # Resource limit enforcement
│   ├── image_processor.py # Image validation and transformation
│   └── gif_builder.py     # GIF creation with Pillow
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
| GET | `/api/frames/image/<filename>` | Serve uploaded image |
| GET | `/api/frames/list` | List uploaded images |
| POST | `/api/generate/preview` | Generate preview GIF |
| POST | `/api/generate/full` | Generate full GIF |
| GET | `/api/generate/file/<filename>` | Serve generated GIF |
| GET | `/api/generate/download/<filename>` | Download generated GIF |

## Dependencies

- **Flask** - Web framework
- **Pillow** - Image processing and GIF creation
- **Flask-Limiter** - Rate limiting
- **Flask-Session** - Server-side sessions
- **APScheduler** - Background cleanup tasks

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
