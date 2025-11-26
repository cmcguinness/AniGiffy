import logging
from PIL import Image
from pathlib import Path

logger = logging.getLogger(__name__)


class GifBuilder:
    """Handles GIF creation from project specifications"""

    def __init__(self, config, image_processor):
        self.config = config
        self.image_processor = image_processor

    def build_gif(self, project, output_path, session_manager, session_id):
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
                    img = self.image_processor.prepare_frame(
                        frame_path,
                        target_width,
                        target_height,
                        transparent=transparent,
                        background_color=background_color,
                        alpha_threshold=alpha_threshold
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

            # Convert frames for GIF format
            gif_frames = []
            for img in prepared_frames:
                if transparent and img.mode == 'RGBA':
                    # Convert RGBA to P mode with transparency
                    # Use a palette that reserves index 0 for transparency
                    gif_frame = img.convert('P', palette=Image.Palette.ADAPTIVE, colors=255)
                    # Find the transparent color and set it
                    mask = Image.eval(img.split()[3], lambda a: 255 if a == 0 else 0)
                    gif_frame.paste(0, mask=mask)
                    gif_frames.append(gif_frame)
                else:
                    # No transparency - just convert to P mode
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    gif_frames.append(img.convert('P', palette=Image.Palette.ADAPTIVE, colors=256))

            # Create GIF
            first_frame = gif_frames[0]
            remaining_frames = gif_frames[1:] if len(gif_frames) > 1 else []

            # Build save parameters
            save_params = {
                'save_all': True,
                'append_images': remaining_frames,
                'duration': durations,
                'loop': loop_count,
                'optimize': False,  # Disable for transparency support
                'disposal': 2  # Clear to background color
            }

            # Add transparency if enabled
            if transparent:
                save_params['transparency'] = 0  # Index 0 is transparent

            # Save as GIF
            first_frame.save(output_path, **save_params)

            # Get file size
            file_size = Path(output_path).stat().st_size

            # Check if output size is within limits
            if file_size > self.config.QUOTAS['max_output_size']:
                Path(output_path).unlink()  # Delete the file
                return False, f"Generated GIF exceeds size limit ({file_size} bytes)", 0

            logger.info(f"Successfully created GIF: {output_path} ({file_size} bytes)")
            return True, "GIF created successfully", file_size

        except Exception as e:
            logger.error(f"GIF creation failed: {e}")
            return False, f"GIF creation failed: {str(e)}", 0

    def create_preview_gif(self, project, output_path, session_manager, session_id, max_frames=10):
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

            # Create temporary project with limited frames (including transparency settings)
            preview_project = type(project)(
                name=project.name,
                width=project.settings['width'],
                height=project.settings['height'],
                loop=project.settings['loop'],
                default_duration=project.settings['defaultDuration'],
                transparent=project.settings.get('transparent', False),
                background_color=project.settings.get('backgroundColor', '#FFFFFF'),
                alpha_threshold=project.settings.get('alphaThreshold', 128)
            )

            preview_project.frames = frames_to_use

            # Build the preview
            success, message, file_size = self.build_gif(
                preview_project,
                output_path,
                session_manager,
                session_id
            )

            if success and len(project.frames) > max_frames:
                message = f"Preview created with {max_frames} of {len(project.frames)} frames"

            return success, message

        except Exception as e:
            logger.error(f"Preview creation failed: {e}")
            return False, f"Preview creation failed: {str(e)}"
