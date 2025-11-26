import logging
from PIL import Image
from pathlib import Path

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Handles image loading, validation, and transformations"""

    def __init__(self, config):
        self.config = config
        self.allowed_extensions = config.ALLOWED_EXTENSIONS
        self.allowed_mimetypes = config.ALLOWED_MIMETYPES

    def validate_file_extension(self, filename):
        """Check if file has an allowed extension"""
        ext = Path(filename).suffix.lower().lstrip('.')
        return ext in self.allowed_extensions

    def load_and_validate_image(self, file_path):
        """
        Load an image and validate it
        Returns (Image, error_message)
        """
        try:
            # Open image
            img = Image.open(file_path)

            # Verify it's actually an image
            img.verify()

            # Reopen after verify (verify() closes the file)
            img = Image.open(file_path)

            # Check format
            if img.format.lower() not in ['png', 'jpeg', 'gif', 'webp']:
                return None, f"Unsupported image format: {img.format}"

            # Check dimensions
            width, height = img.size
            if not self.check_dimensions(width, height):
                return None, f"Image dimensions {width}x{height} exceed maximum {self.config.QUOTAS['max_dimension']}"

            return img, None

        except Exception as e:
            logger.error(f"Image validation failed: {e}")
            return None, f"Invalid image file: {str(e)}"

    def check_dimensions(self, width, height):
        """Check if dimensions are within limits"""
        max_dim = self.config.QUOTAS['max_dimension']
        return width <= max_dim and height <= max_dim

    def resize_image(self, img, target_width, target_height, fit_mode='contain'):
        """
        Resize image to target dimensions

        fit_mode options:
        - 'contain': Fit inside dimensions, maintain aspect ratio, add padding
        - 'cover': Fill dimensions, maintain aspect ratio, crop if needed
        - 'fill': Exact dimensions, maintain aspect ratio, pad if needed
        - 'stretch': Exact dimensions, ignore aspect ratio
        """
        try:
            if fit_mode == 'stretch':
                # Simply resize to exact dimensions
                return img.resize((target_width, target_height), Image.Resampling.LANCZOS)

            elif fit_mode == 'contain':
                # Fit inside while maintaining aspect ratio
                img.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)

                # Create new image with padding if needed
                new_img = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))

                # Calculate position to center the image
                x = (target_width - img.width) // 2
                y = (target_height - img.height) // 2

                new_img.paste(img, (x, y))
                return new_img

            elif fit_mode == 'cover':
                # Calculate scale to cover the target dimensions
                img_aspect = img.width / img.height
                target_aspect = target_width / target_height

                if img_aspect > target_aspect:
                    # Image is wider, scale by height
                    new_height = target_height
                    new_width = int(target_height * img_aspect)
                else:
                    # Image is taller, scale by width
                    new_width = target_width
                    new_height = int(target_width / img_aspect)

                # Resize
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # Crop to target dimensions
                left = (new_width - target_width) // 2
                top = (new_height - target_height) // 2
                right = left + target_width
                bottom = top + target_height

                return img.crop((left, top, right, bottom))

            else:  # 'fill' is default
                # Same as contain for now
                return self.resize_image(img, target_width, target_height, 'contain')

        except Exception as e:
            logger.error(f"Image resize failed: {e}")
            return None

    def hex_to_rgb(self, hex_color):
        """Convert hex color string to RGB tuple"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def prepare_frame(self, file_path, target_width, target_height,
                      transparent=False, background_color='#FFFFFF', alpha_threshold=128):
        """
        Load and prepare a frame for GIF creation

        Args:
            file_path: Path to the image file
            target_width: Target width
            target_height: Target height
            transparent: If True, preserve transparency in GIF
            background_color: Hex color for background when not transparent
            alpha_threshold: Threshold (0-255) for converting semi-transparent to opaque/transparent

        Returns prepared image or None on error
        """
        img, error = self.load_and_validate_image(file_path)
        if error:
            logger.error(f"Failed to prepare frame: {error}")
            return None

        # Convert to RGBA for consistent processing
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        # Resize to target dimensions (keeping RGBA)
        img = self.resize_image(img, target_width, target_height, 'contain')

        if img is None:
            return None

        # Ensure we're in RGBA mode after resize
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        if transparent:
            # Convert semi-transparent pixels based on threshold
            # GIF only supports 1-bit transparency (fully transparent or fully opaque)
            pixels = img.load()
            width, height = img.size

            for y in range(height):
                for x in range(width):
                    r, g, b, a = pixels[x, y]
                    if a < alpha_threshold:
                        # Make fully transparent
                        pixels[x, y] = (0, 0, 0, 0)
                    else:
                        # Make fully opaque
                        pixels[x, y] = (r, g, b, 255)

            return img
        else:
            # Flatten to background color
            bg_rgb = self.hex_to_rgb(background_color)
            background = Image.new('RGB', img.size, bg_rgb)
            background.paste(img, mask=img.split()[3])  # Use alpha channel as mask
            return background
