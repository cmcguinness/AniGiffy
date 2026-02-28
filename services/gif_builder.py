import logging
from PIL import Image
from pathlib import Path

logger = logging.getLogger(__name__)


class GifBuilder:
    """Handles GIF creation from project specifications"""

    def __init__(self, config, image_processor):
        self.config = config
        self.image_processor = image_processor

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
                           'carousel-left', 'carousel-right', 'carousel-up', 'carousel-down')

        Returns:
            List of transition frame images
        """
        if transition_type == 'crossfade':
            return self.create_crossfade_frames(img1, img2, steps)
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

            # Validate transition settings
            if transition_time > 0:
                for frame in project.frames:
                    if frame.duration < transition_time:
                        return False, f"Frame duration ({frame.duration}ms) must be >= transition time ({transition_time}ms)", 0
                if transition_steps < 1:
                    return False, "Transition steps must be at least 1", 0

            is_apng = output_format == 'apng'

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

            # Helper function to convert image to GIF palette format
            def to_gif_format(img):
                if transparent and img.mode == 'RGBA':
                    # Convert RGBA to P mode with transparency
                    gif_frame = img.convert('P', palette=Image.Palette.ADAPTIVE, colors=255)
                    mask = Image.eval(img.split()[3], lambda a: 255 if a == 0 else 0)
                    gif_frame.paste(0, mask=mask)
                    return gif_frame
                else:
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    return img.convert('P', palette=Image.Palette.ADAPTIVE, colors=256)

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
                transition_steps=project.settings.get('transitionSteps', 5)
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
