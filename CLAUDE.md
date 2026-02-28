# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AniGiffy is a web-based animated GIF creator with a Flask backend and Bootstrap 5 frontend. Users upload images, arrange frames, configure transitions and transparency, and generate optimized animated GIFs in the browser.

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
- `routes/frames.py` — Upload and frame management API endpoints.
- `routes/generate.py` — Preview and full GIF generation API endpoints.
- `services/gif_builder.py` — Core GIF creation with Pillow. Handles transitions (crossfade, fade-to-color, carousel), preview generation, and frame assembly. Largest backend file (~391 lines).
- `services/image_processor.py` — Image validation, loading, resizing, transparency handling.
- `services/session_manager.py` — Per-session filesystem isolation under `user_data/{session_id}/`.
- `services/quota_manager.py` — Enforces resource limits (storage, file size, dimensions, frame count).
- `models/project.py` — Project and Frame dataclasses with serialization.

**Frontend (Vanilla JS + Bootstrap 5):**

- `templates/base.html` — Base layout with CDN-loaded Bootstrap 5.3 and Bootstrap Icons.
- `templates/index.html` — Main editor: two-panel layout with frame list (left) and preview+settings tabs (right).
- `static/js/app.js` — All frontend logic: state management, drag-and-drop, API calls via Fetch, DOM updates. Single-file client app (~400+ lines).
- `static/css/style.css` — Custom styles for drag-drop, frames, preview area.

**Data Flow:** Client-side state (frames, settings) is sent with each API call. Server is mostly stateless — session data lives on the filesystem under `user_data/`. No database.

## Key API Endpoints

- `POST /api/frames/upload` — Upload images
- `POST /api/generate/preview` — Generate preview GIF (first 10 frames or all)
- `POST /api/generate/full` — Generate full GIF
- `GET /api/frames/image/<filename>` — Serve uploaded images
- `GET /api/generate/file/<filename>` — Serve generated GIFs

## Important Conventions

- Route handlers in `routes/` should only handle request/response flow — delegate logic to `services/`.
- All image processing goes through `ImageProcessor`; all GIF assembly through `GifBuilder`.
- Session isolation: each user gets a directory under `user_data/{session_id}/` with `uploads/` and `output/` subdirectories. `SessionManager` validates paths to prevent directory traversal.
- Quotas and rate limits are configured in `config.py` — the README documents different values than the actual config; the actual `config.py` values are authoritative.
- Frontend uses no framework — vanilla JS with direct DOM manipulation.
- All dependencies are CDN-loaded (Bootstrap, Bootstrap Icons) — no npm/node build step.
