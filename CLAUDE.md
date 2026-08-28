# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AniGiffy is a web-based animated GIF creator with a Flask backend and Bootstrap 5 frontend. Users upload images (or extract frames from video), arrange frames, optionally auto-align their backgrounds, configure transitions and transparency, and generate optimized animated GIFs or APNGs in the browser.

## Running the Application

```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run development server (serves on http://127.0.0.1:5173)
python app.py
```

There is no automated test suite. Test changes manually via the browser UI and Chrome DevTools.

## Architecture

**Backend (Flask):** Layered architecture with strict separation between routing and business logic.

- `app.py` — Entry point. Initializes Flask, registers blueprints, starts APScheduler for session cleanup.
- `config.py` — All configuration: quotas, rate limits, cleanup intervals, allowed file types.
- `extensions.py` — Shared Flask extensions (rate limiter singleton).
- `routes/frames.py` — Upload, frame management and alignment API endpoints.
- `routes/generate.py` — Preview and full GIF/APNG generation API endpoints.
- `routes/video.py` — Video upload and frame extraction API endpoints.
- `services/gif_builder.py` — Core GIF/APNG creation with Pillow. Handles transitions (crossfade, fade-to-color, carousel, motion tween/morph via `FrameInterpolator`), ping-pong sequencing, preview generation, and frame assembly. Largest backend file (~460 lines).
- `services/image_processor.py` — Image validation, loading, resizing, transparency handling. Accepts MPO (camera multi-picture JPEG) and scales oversized uploads down instead of rejecting them.
- `services/frame_interpolator.py` — Motion transitions. Fits a similarity transform
  between two frames (reusing `ImageAligner`'s feature matching) for the "tween" mode, and
  computes dense optical flow with per-pixel trust maps for the "morph" mode. Both return
  `None` when no reliable motion can be estimated so `GifBuilder` falls back to a
  cross-fade.
- `services/image_aligner.py` — OpenCV background alignment: SIFT/ORB features, RANSAC similarity
  transform against a reference frame, then a common-area crop. Streams one image at a time so
  memory stays flat regardless of frame count.
- `services/session_manager.py` — Per-session filesystem isolation under `user_data/{session_id}/`.
- `services/quota_manager.py` — Enforces resource limits (storage, file size, dimensions, frame count).
- `services/video_processor.py` — ffmpeg/ffprobe video probing and frame extraction. ffmpeg is
  required only for video import; the rest of the app runs without it.
- `models/project.py` — Project and Frame dataclasses with serialization.

**Frontend (Vanilla JS + Bootstrap 5):**

- `templates/base.html` — Base layout with CDN-loaded Bootstrap 5.3 and Bootstrap Icons.
- `templates/index.html` — Main editor: two-panel layout with frame list (left) and preview+settings tabs (right).
- `static/js/app.js` — All frontend logic: state management, drag-and-drop, API calls via Fetch, DOM updates. Single-file client app (~900 lines — approaching the 1000-line guideline).
- `static/css/style.css` — Custom styles for drag-drop, frames, preview area.

**Data Flow:** Client-side state (frames, settings) is sent with each API call. Server is mostly stateless — session data lives on the filesystem under `user_data/`. No database.

## Key API Endpoints

- `POST /api/frames/upload` — Upload images
- `POST /api/frames/align` — Align frame backgrounds (rewrites the image files in place)
- `POST /api/generate/preview` — Generate preview GIF (first 10 frames or all)
- `POST /api/generate/full` — Generate full GIF
- `GET /api/frames/image/<filename>` — Serve uploaded images
- `GET /api/generate/file/<filename>` — Serve generated GIFs
- `POST /api/video/upload` / `POST /api/video/extract` — Import frames from a video

## Important Conventions

- Route handlers in `routes/` should only handle request/response flow — delegate logic to `services/`.
- GIF palette reduction goes through `GifBuilder._quantize` (octree, not Pillow's default median cut — see its docstring). The transparent path must use `_quantize_reserving_zero`, since index 0 is declared transparent on save and no quantiser reserves it for you.
- All image processing goes through `ImageProcessor`; all GIF assembly through `GifBuilder`; all alignment through `ImageAligner`; all motion in-betweening through `FrameInterpolator`.
- The minimum frame delay is format-dependent (`GIF_MIN_FRAME_MS` / `APNG_MIN_FRAME_MS` in
  `gif_builder.py`), and transition steps are capped so no frame falls below it. GIF's 20ms
  floor is a hard format limit; APNG stores delays as a rational fraction of a second and so
  allows far more steps, which is what the motion transitions want.
- Session isolation: each user gets a directory under `user_data/{session_id}/` with `uploads/` and `output/` subdirectories. `SessionManager` validates paths to prevent directory traversal.
- Quotas and rate limits are configured in `config.py`, which is authoritative; the README mirrors those values and should be updated alongside them. The `@limiter.limit(...)` decorators in `routes/` read `config.RATE_LIMITS` — never inline a limit string there, or the config silently stops being the source of truth.
- Frontend uses no framework — vanilla JS with direct DOM manipulation.
- All frontend dependencies are CDN-loaded (Bootstrap, Bootstrap Icons) — no npm/node build step.
- Alignment rewrites the uploaded image files in place, so the frontend bumps `state.imageVersion`
  to bust cached thumbnails whenever it runs.
