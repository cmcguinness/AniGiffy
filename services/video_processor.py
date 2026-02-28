import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class VideoProcessor:
    """Handles video probing and frame extraction via ffmpeg"""

    PROBE_TIMEOUT = 15   # seconds
    EXTRACT_TIMEOUT = 300  # seconds

    def __init__(self, config):
        self.config = config
        self.allowed_extensions = config.ALLOWED_VIDEO_EXTENSIONS
        self.ffmpeg = shutil.which('ffmpeg')
        self.ffprobe = shutil.which('ffprobe')

        if not self.ffmpeg or not self.ffprobe:
            logger.warning("ffmpeg/ffprobe not found on PATH; video import disabled")

    @property
    def available(self):
        return self.ffmpeg is not None and self.ffprobe is not None

    def validate_video_extension(self, filename):
        """Check if file has an allowed video extension"""
        ext = Path(filename).suffix.lower().lstrip('.')
        return ext in self.allowed_extensions

    def probe_video(self, path):
        """
        Run ffprobe on a video file.
        Returns dict with duration, width, height, fps, codec or (None, error).
        """
        try:
            cmd = [
                self.ffprobe,
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                str(path),
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.PROBE_TIMEOUT,
            )

            if result.returncode != 0:
                return None, f"ffprobe failed: {result.stderr[:200]}"

            raw = result.stdout
            # Handle potential markdown fences or extraneous text
            if '```' in raw:
                raw = raw.split('```')[1] if raw.count('```') >= 2 else raw
                raw = raw.strip().lstrip('json').strip()
            data = json.loads(raw)

            # Find the video stream
            video_stream = None
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break

            if not video_stream:
                return None, "No video stream found"

            # Parse frame rate (e.g. "30/1" or "29.97")
            fps_str = video_stream.get('r_frame_rate', '0/1')
            if '/' in fps_str:
                num, den = fps_str.split('/')
                fps = float(num) / float(den) if float(den) != 0 else 0
            else:
                fps = float(fps_str)

            duration = float(data.get('format', {}).get('duration', 0))
            width = int(video_stream.get('width', 0))
            height = int(video_stream.get('height', 0))
            codec = video_stream.get('codec_name', 'unknown')

            return {
                'duration': round(duration, 2),
                'width': width,
                'height': height,
                'fps': round(fps, 2),
                'codec': codec,
            }, None

        except subprocess.TimeoutExpired:
            return None, "Video probe timed out"
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            return None, f"Failed to parse video metadata: {e}"
        except Exception as e:
            logger.error(f"probe_video error: {e}")
            return None, f"Unexpected error probing video: {e}"

    def extract_frames(self, video_path, output_dir, fps):
        """
        Extract frames from video at the given FPS.
        Outputs PNG files named frame_000001.png, frame_000002.png, etc.
        Returns (list_of_paths, error).
        """
        try:
            output_pattern = str(Path(output_dir) / 'vframe_%06d.png')
            cmd = [
                self.ffmpeg,
                '-i', str(video_path),
                '-vf', f'fps={fps}',
                '-y',
                output_pattern,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.EXTRACT_TIMEOUT,
            )

            if result.returncode != 0:
                return None, f"ffmpeg extraction failed: {result.stderr[:300]}"

            # Collect extracted files in sorted order
            output_dir = Path(output_dir)
            extracted = sorted(output_dir.glob('vframe_*.png'))

            if not extracted:
                return None, "No frames were extracted"

            return extracted, None

        except subprocess.TimeoutExpired:
            return None, "Frame extraction timed out (video may be too long)"
        except Exception as e:
            logger.error(f"extract_frames error: {e}")
            return None, f"Unexpected error extracting frames: {e}"
