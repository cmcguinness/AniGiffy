import logging

import numpy as np
from PIL import Image
from pathlib import Path

from services.frame_interpolator import FrameInterpolator

logger = logging.getLogger(__name__)

# Shortest delay each output format can actually hold. GIF delays are whole
# centiseconds and browsers render anything under 2cs as ~100ms, so 20ms is a
# hard floor. APNG delays are a rational fraction of a second, so it can go
# far finer -- 10ms (100fps) is past the point of visible benefit.
GIF_MIN_FRAME_MS = 20
APNG_MIN_FRAME_MS = 10

# Dithering modes for GIF palette reduction. 'none' is the default; see
# GifBuilder._quantize for what each trades.
DITHER_MODES = ('none', 'ordered', 'floyd-steinberg')

# 8x8 Bayer threshold matrix, as a signed offset in the range -0.5..0.5.
# Each cell is a fixed threshold for that pixel position, so the pattern is a
# pure function of (x, y) and repeats identically frame after frame.
_BAYER8 = np.array([
    [0, 32, 8, 40, 2, 34, 10, 42],
    [48, 16, 56, 24, 50, 18, 58, 26],
    [12, 44, 4, 36, 14, 46, 6, 38],
    [60, 28, 52, 20, 62, 30, 54, 22],
    [3, 35, 11, 43, 1, 33, 9, 41],
    [51, 19, 59, 27, 49, 17, 57, 25],
    [15, 47, 7, 39, 13, 45, 5, 37],
    [63, 31, 55, 23, 61, 29, 53, 21],
], dtype=np.float32) / 64.0 - 0.5

# How far the Bayer pattern pushes a pixel's value, in 0..255 units. Roughly
# one palette step for a 256-colour photo: enough to break up banding without
# making the pattern itself obvious at viewing size.
_ORDERED_DITHER_AMPLITUDE = 6.0


class GifBuilder:
    """Handles GIF creation from project specifications"""

    def __init__(self, config, image_processor):
        self.config = config
        self.image_processor = image_processor
        self.interpolator = FrameInterpolator(config)

    @staticmethod
    def _quantize(img, colors, dither='none'):
        """
        Reduce an image to a GIF palette.

        `dither` selects how pixels that fall between palette entries are
        handled. 'none' snaps each to its nearest colour, which is smallest
        and fastest but turns a smooth gradient (a plain wall, a sky) into
        visible stair-steps. 'ordered' offsets each pixel by a fixed Bayer
        threshold for its position before snapping, trading the steps for a
        fine regular pattern -- and because the pattern depends only on
        position, a pixel that doesn't change between frames dithers
        identically every frame, so nothing shimmers during playback.
        'floyd-steinberg' is error diffusion: smoothest on a single still,
        but the error carried along each row means any small change
        re-scatters the noise pattern, which crawls visibly across static
        areas during transitions, and it compresses worst (measured +25-70%
        on file size). Pillow doesn't ship an ordered dither, and only
        dithers against a supplied palette, so both modes build the palette
        with octree first and then map against it.

        Uses the octree quantiser rather than Pillow's default median cut.
        Median cut sorts every pixel in the image to find its palette, which
        costs ~44ms on a single 403x268 frame -- and an animation quantises
        one frame per transition step, so that was the largest single cost in
        building a GIF, larger than decoding the source photos. Octree builds
        the same size palette by accumulating colours into a tree, ~100x
        faster, and because it doesn't dither, the flat runs it leaves
        compress substantially better: measured over a real 12-photo
        animation, 576ms -> 6ms and 795KB -> 625KB.

        The trade is slightly coarser colour (mean error 2.86 -> 3.60 out of
        255). It shows as faint blotching in large smooth areas, visible when
        a photo's flattest region is magnified several times, and not at
        viewing size.
        """
        if img.mode != 'RGB':
            # Quantise from RGB even when the source has alpha: octree would
            # otherwise treat alpha as a fourth dimension and spend palette
            # entries on it, and the caller handles transparency itself.
            img = img.convert('RGB')
        palette = img.quantize(colors=colors, method=Image.Quantize.FASTOCTREE)

        if dither == 'floyd-steinberg':
            return img.quantize(palette=palette, dither=Image.Dither.FLOYDSTEINBERG)
        if dither == 'ordered':
            pixels = np.asarray(img, dtype=np.float32)
            h, w = pixels.shape[:2]
            reps = (h // 8 + 1, w // 8 + 1)
            threshold = np.tile(_BAYER8, reps)[:h, :w, None] * _ORDERED_DITHER_AMPLITUDE
            offset = np.clip(pixels + threshold, 0, 255).astype(np.uint8)
            return Image.fromarray(offset).quantize(palette=palette, dither=Image.Dither.NONE)
        return palette

    @classmethod
    def _quantize_reserving_zero(cls, img, dither='none'):
        """
        Quantise to a palette whose index 0 is left free for transparency.

        The frame is saved with index 0 declared transparent, so any opaque
        pixel that lands on index 0 is punched out as a hole. Asking the
        quantiser for 255 colours does not prevent that -- it just numbers its
        255 colours from zero -- so the indices are shifted up by one and the
        palette given a spare entry at the front. Whether index 0 happened to
        go unused was previously left to the quantiser's ordering.
        """
        quantised = cls._quantize(img, colors=255, dither=dither)

        shifted = np.asarray(quantised, dtype=np.uint8) + 1
        out = Image.fromarray(shifted, mode='P')

        # Pad the palette back to 255 real colours in case the quantiser
        # returned fewer, so every shifted index still addresses an entry.
        palette = quantised.getpalette()[:255 * 3]
        palette += [0] * (255 * 3 - len(palette))
        out.putpalette([0, 0, 0] + palette)
        return out

    def create_crossfade_frames(self, img1, img2, steps):
        """
        Create transition frames between two images using linear cross-fade

        Args:
            img1: First image (current frame)
            img2: Second image (next frame)
            steps: Number of transition frames to create

        Returns:
            List of transition frame images
        """
        transition_frames = []

        # Ensure both images are in RGBA mode for blending
        if img1.mode != 'RGBA':
            img1 = img1.convert('RGBA')
        if img2.mode != 'RGBA':
            img2 = img2.convert('RGBA')

        for i in range(1, steps + 1):
            # Calculate blend ratio: step i goes from mostly img1 to mostly img2
            # For step i of N steps: alpha2 = i/(N+1), alpha1 = 1 - alpha2
            alpha = i / (steps + 1)

            # Blend the two images
            blended = Image.blend(img1, img2, alpha)
            transition_frames.append(blended)

        return transition_frames

    def create_fade_to_color_frames(self, img1, img2, steps, color):
        """
        Create transition frames that fade current image to a color, then fade in next image

        Args:
            img1: First image (current frame)
            img2: Second image (next frame)
            steps: Number of transition frames to create
            color: RGB tuple for intermediate color (e.g., (255, 255, 255) for white)

        Returns:
            List of transition frame images
        """
        transition_frames = []

        # Ensure both images are in RGBA mode
        if img1.mode != 'RGBA':
            img1 = img1.convert('RGBA')
        if img2.mode != 'RGBA':
            img2 = img2.convert('RGBA')

        # Create solid color image
        color_img = Image.new('RGBA', img1.size, color + (255,))

        # First half: fade from img1 to color
        half_steps = steps // 2
        for i in range(1, half_steps + 1):
            alpha = i / (half_steps + 1)
            blended = Image.blend(img1, color_img, alpha)
            transition_frames.append(blended)

        # Second half: fade from color to img2
        remaining_steps = steps - half_steps
        for i in range(1, remaining_steps + 1):
            alpha = i / (remaining_steps + 1)
            blended = Image.blend(color_img, img2, alpha)
            transition_frames.append(blended)

        return transition_frames

    def create_carousel_frames(self, img1, img2, steps, direction):
        """
        Create carousel transition frames where images slide in a direction

        Args:
            img1: First image (current frame)
            img2: Second image (next frame)
            steps: Number of transition frames to create
            direction: 'left', 'right', 'up', or 'down'

        Returns:
            List of transition frame images
        """
        transition_frames = []

        # Ensure both images are in RGBA mode
        if img1.mode != 'RGBA':
            img1 = img1.convert('RGBA')
        if img2.mode != 'RGBA':
            img2 = img2.convert('RGBA')

        width, height = img1.size

        for i in range(1, steps + 1):
            # Calculate offset ratio
            ratio = i / (steps + 1)

            # Create new frame
            frame = Image.new('RGBA', (width, height), (0, 0, 0, 0))

            if direction == 'left':
                # img1 moves left (off screen), img2 comes from right
                offset1 = int(-width * ratio)
                offset2 = int(width * (1 - ratio))
                frame.paste(img1, (offset1, 0))
                frame.paste(img2, (offset2, 0))
            elif direction == 'right':
                # img1 moves right (off screen), img2 comes from left
                offset1 = int(width * ratio)
                offset2 = int(-width * (1 - ratio))
                frame.paste(img1, (offset1, 0))
                frame.paste(img2, (offset2, 0))
            elif direction == 'up':
                # img1 moves up (off screen), img2 comes from bottom
                offset1 = int(-height * ratio)
                offset2 = int(height * (1 - ratio))
                frame.paste(img1, (0, offset1))
                frame.paste(img2, (0, offset2))
            elif direction == 'down':
                # img1 moves down (off screen), img2 comes from top
                offset1 = int(height * ratio)
                offset2 = int(-height * (1 - ratio))
                frame.paste(img1, (0, offset1))
                frame.paste(img2, (0, offset2))

            transition_frames.append(frame)

        return transition_frames

    def create_transition_frames(self, img1, img2, steps, transition_type):
        """
        Create transition frames between two images based on transition type

        Args:
            img1: First image (current frame)
            img2: Second image (next frame)
            steps: Number of transition frames to create
            transition_type: Type of transition ('crossfade', 'fade-to-white', 'fade-to-black',
                           'carousel-left', 'carousel-right', 'carousel-up', 'carousel-down',
                           'motion-tween', 'motion-morph')

        Returns:
            List of transition frame images
        """
        if transition_type == 'crossfade':
            return self.create_crossfade_frames(img1, img2, steps)
        elif transition_type == 'motion-tween':
            # Falls back to a cross-fade when no camera movement can be
            # fitted -- a dissolve is a poor transition, but a warp built on
            # a transform we don't trust is a broken one.
            frames = self.interpolator.create_tween_frames(img1, img2, steps)
            return frames if frames is not None else self.create_crossfade_frames(img1, img2, steps)
        elif transition_type == 'motion-morph':
            frames = self.interpolator.create_morph_frames(img1, img2, steps)
            return frames if frames is not None else self.create_crossfade_frames(img1, img2, steps)
        elif transition_type == 'fade-to-white':
            return self.create_fade_to_color_frames(img1, img2, steps, (255, 255, 255))
        elif transition_type == 'fade-to-black':
            return self.create_fade_to_color_frames(img1, img2, steps, (0, 0, 0))
        elif transition_type.startswith('carousel-'):
            direction = transition_type.split('-')[1]
            return self.create_carousel_frames(img1, img2, steps, direction)
        else:
            # Default to crossfade for unknown types
            logger.warning(f"Unknown transition type '{transition_type}', defaulting to crossfade")
            return self.create_crossfade_frames(img1, img2, steps)

    def build_gif(self, project, output_path, session_manager, session_id, output_format='gif'):
        """
        Build a GIF from a project

        Args:
            project: Project object
            output_path: Path to save the GIF
            session_manager: SessionManager instance
            session_id: Session ID for path validation

        Returns:
            (success: bool, message: str, file_size: int)
        """
        try:
            if len(project.frames) == 0:
                return False, "Project has no frames", 0

            # Validate project
            is_valid, errors = project.validate(self.config)
            if not is_valid:
                return False, f"Project validation failed: {', '.join(errors)}", 0

            # Get target dimensions and settings
            target_width = project.settings['width']
            target_height = project.settings['height']
            loop_count = project.settings['loop']
            transparent = project.settings.get('transparent', False)
            background_color = project.settings.get('backgroundColor', '#FFFFFF')
            alpha_threshold = project.settings.get('alphaThreshold', 128)
            transition_type = project.settings.get('transitionType', 'crossfade')
            transition_time = project.settings.get('transitionTime', 0)
            transition_steps = project.settings.get('transitionSteps', 5)
            dither = project.settings.get('dither', 'none')
            if dither not in DITHER_MODES:
                dither = 'none'

            is_apng = output_format == 'apng'

            # Validate and adjust transition settings.
            # GIF stores delays in centiseconds and browsers treat 0cs as
            # ~100ms, so a GIF frame can't go below 20ms (2cs). APNG stores
            # delays as a rational number of seconds and has no such floor,
            # so motion transitions can use many more steps there -- which is
            # exactly where they look best.
            MIN_FRAME_MS = APNG_MIN_FRAME_MS if is_apng else GIF_MIN_FRAME_MS
            if transition_time > 0:
                for frame in project.frames:
                    if frame.duration < transition_time:
                        return False, f"Frame duration ({frame.duration}ms) must be >= transition time ({transition_time}ms)", 0
                if transition_steps < 1:
                    return False, "Transition steps must be at least 1", 0
                # Auto-reduce steps so each transition frame stays >= MIN_FRAME_MS
                max_steps = transition_time // MIN_FRAME_MS
                if max_steps < 1:
                    # Transition time itself is below minimum; clamp to one frame at MIN_FRAME_MS
                    transition_steps = 1
                    transition_time = MIN_FRAME_MS
                    logger.info(f"Transition time too short, clamped to {MIN_FRAME_MS}ms / 1 step")
                elif transition_steps > max_steps:
                    logger.info(f"Reduced transition steps from {transition_steps} to {max_steps} "
                                f"to maintain minimum {MIN_FRAME_MS}ms per frame")
                    transition_steps = max_steps

            # Load and prepare all frames
            prepared_frames = []
            durations = []

            for frame in project.frames:
                # Construct safe file path
                try:
                    frame_path = session_manager.safe_path(session_id, frame.file)

                    if not frame_path.exists():
                        logger.error(f"Frame file not found: {frame.file}")
                        continue

                    # Prepare the frame with transparency settings
                    # APNG supports full alpha, so skip binarization
                    img = self.image_processor.prepare_frame(
                        frame_path,
                        target_width,
                        target_height,
                        transparent=transparent,
                        background_color=background_color,
                        alpha_threshold=alpha_threshold,
                        binarize_alpha=not is_apng
                    )

                    if img is None:
                        logger.error(f"Failed to prepare frame: {frame.file}")
                        continue

                    prepared_frames.append(img)
                    durations.append(frame.duration)

                except Exception as e:
                    logger.error(f"Error processing frame {frame.file}: {e}")
                    continue

            if len(prepared_frames) == 0:
                return False, "No valid frames to create GIF", 0

            # Ping-pong: play forward, then back through the middle frames, so
            # A,B,C,D becomes A,B,C,D,C,B and loops seamlessly back to A. The
            # endpoints are held once so they don't stutter at the turnaround.
            # Prepared images are reused, so this costs no extra decoding.
            if project.settings.get('pingPong', False) and len(prepared_frames) > 2:
                prepared_frames = prepared_frames + prepared_frames[-2:0:-1]
                durations = durations + durations[-2:0:-1]

            # Helper function to convert image to GIF palette format
            def to_gif_format(img):
                if transparent and img.mode == 'RGBA':
                    alpha = img.split()[3]
                    gif_frame = self._quantize_reserving_zero(img, dither)
                    mask = Image.eval(alpha, lambda a: 255 if a == 0 else 0)
                    gif_frame.paste(0, mask=mask)
                    return gif_frame
                else:
                    return self._quantize(img, colors=256, dither=dither)

            # Helper to ensure RGBA for APNG
            def to_apng_format(img):
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                return img

            convert_frame = to_apng_format if is_apng else to_gif_format

            # Convert frames and add transitions
            output_frames = []
            output_durations = []

            for i in range(len(prepared_frames)):
                current_frame = prepared_frames[i]
                current_duration = durations[i]
                next_frame = prepared_frames[(i + 1) % len(prepared_frames)]

                if transition_time > 0:
                    # Add main frame with reduced duration
                    main_duration = current_duration - transition_time
                    output_frames.append(convert_frame(current_frame))
                    output_durations.append(main_duration)

                    # Create and add transition frames
                    transition_frames = self.create_transition_frames(
                        current_frame,
                        next_frame,
                        transition_steps,
                        transition_type
                    )

                    # Duration per transition frame
                    transition_frame_duration = transition_time // transition_steps
                    remainder = transition_time % transition_steps

                    for j, trans_frame in enumerate(transition_frames):
                        output_frames.append(convert_frame(trans_frame))
                        # Add remainder to last transition frame to maintain exact timing
                        dur = transition_frame_duration + (remainder if j == len(transition_frames) - 1 else 0)
                        output_durations.append(dur)
                else:
                    # No transitions - just add the frame as-is
                    output_frames.append(convert_frame(current_frame))
                    output_durations.append(current_duration)

            # Save animation
            first_frame = output_frames[0]
            remaining_frames = output_frames[1:] if len(output_frames) > 1 else []

            if is_apng:
                # Save as APNG
                save_params = {
                    'format': 'PNG',
                    'save_all': True,
                    'append_images': remaining_frames,
                    'duration': output_durations,
                    'loop': loop_count,
                }
            else:
                # Save as GIF
                save_params = {
                    'save_all': True,
                    'append_images': remaining_frames,
                    'duration': output_durations,
                    'loop': loop_count,
                    'optimize': False,  # Disable for transparency support
                    'disposal': 2  # Clear to background color
                }
                if transparent:
                    save_params['transparency'] = 0  # Index 0 is transparent

            first_frame.save(output_path, **save_params)

            # Get file size
            file_size = Path(output_path).stat().st_size

            # Check if output size is within limits
            if file_size > self.config.QUOTAS['max_output_size']:
                Path(output_path).unlink()  # Delete the file
                fmt_label = 'APNG' if is_apng else 'GIF'
                return False, f"Generated {fmt_label} exceeds size limit ({file_size} bytes)", 0

            fmt_label = 'APNG' if is_apng else 'GIF'
            logger.info(f"Successfully created {fmt_label}: {output_path} ({file_size} bytes)")
            return True, f"{fmt_label} created successfully", file_size

        except Exception as e:
            logger.error(f"GIF creation failed: {e}")
            return False, f"GIF creation failed: {str(e)}", 0

    def create_preview_gif(self, project, output_path, session_manager, session_id, max_frames=10, output_format='gif'):
        """
        Create a preview GIF with limited frames for faster generation

        Args:
            project: Project object
            output_path: Path to save preview GIF
            session_manager: SessionManager instance
            session_id: Session ID
            max_frames: Maximum number of frames to include in preview

        Returns:
            (success: bool, message: str)
        """
        try:
            if len(project.frames) == 0:
                return False, "Project has no frames"

            # Limit frames for preview
            frames_to_use = project.frames[:max_frames]

            # Create temporary project with limited frames (including transparency and transition settings)
            preview_project = type(project)(
                name=project.name,
                width=project.settings['width'],
                height=project.settings['height'],
                loop=project.settings['loop'],
                default_duration=project.settings['defaultDuration'],
                transparent=project.settings.get('transparent', False),
                background_color=project.settings.get('backgroundColor', '#FFFFFF'),
                alpha_threshold=project.settings.get('alphaThreshold', 128),
                transition_type=project.settings.get('transitionType', 'crossfade'),
                transition_time=project.settings.get('transitionTime', 0),
                transition_steps=project.settings.get('transitionSteps', 5),
                ping_pong=project.settings.get('pingPong', False),
                dither=project.settings.get('dither', 'none')
            )

            preview_project.frames = frames_to_use

            # Build the preview
            success, message, file_size = self.build_gif(
                preview_project,
                output_path,
                session_manager,
                session_id,
                output_format=output_format
            )

            if success and len(project.frames) > max_frames:
                message = f"Preview created with {max_frames} of {len(project.frames)} frames"

            return success, message

        except Exception as e:
            logger.error(f"Preview creation failed: {e}")
            return False, f"Preview creation failed: {str(e)}"
