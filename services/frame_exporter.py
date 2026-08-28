import logging
import zipfile

from PIL import Image

logger = logging.getLogger(__name__)


class FrameExporter:
    """
    Packages a session's frame images into a ZIP the user can download.

    This exists so people can keep what alignment produced. Aligning rewrites
    the uploaded images in place -- warped onto the reference and cropped to
    the area every frame covers -- and until now the only way that work left
    the app was baked into an animation.
    """

    # PNG's own deflate already does the compressing, so the archive stores
    # entries verbatim rather than spending time failing to shrink them again.
    ARCHIVE_COMPRESSION = zipfile.ZIP_STORED

    # Pillow's default (6) costs roughly twice the time of 3 for about 4% less
    # data on a photograph -- a poor trade when a dozen 4096px frames are being
    # encoded in a single request. Measured on a 4096x2731 photo: 0.36s/12.5MB
    # at level 3 against 0.71s/12.0MB at level 6.
    PNG_COMPRESS_LEVEL = 3

    def export_png_zip(self, entries, destination):
        """
        Write each image to `destination` as a PNG inside a ZIP.

        Args:
            entries: (path, arcname) pairs, already validated by the caller
            destination: file path or writable binary stream for the archive

        Returns the number of images written.
        """
        written = 0

        with zipfile.ZipFile(destination, 'w', self.ARCHIVE_COMPRESSION) as archive:
            for path, arcname in entries:
                # One image is open at a time and encoded straight into the
                # archive stream, so memory stays flat no matter how many
                # frames are exported -- the same reason the aligner streams.
                with Image.open(path) as img:
                    img = self._for_png(img)
                    with archive.open(arcname, 'w') as target:
                        img.save(target, 'PNG', compress_level=self.PNG_COMPRESS_LEVEL)
                written += 1

        logger.info(f"Exported {written} frame(s) as PNG")
        return written

    @staticmethod
    def _for_png(img):
        """
        Put an image in a mode PNG can store without losing anything.

        Transparency is kept when the source has it. An image without an alpha
        band can still be transparent, carrying the index in its metadata
        instead -- which is how GIF uploads arrive, and Pillow reports the mode
        of those as L or P depending on whether the palette is grey, so the
        metadata is what has to be tested rather than the mode.
        """
        if img.mode in ('RGBA', 'LA'):
            return img
        if 'transparency' in img.info:
            return img.convert('RGBA')
        if img.mode not in ('RGB', 'L'):
            return img.convert('RGB')
        return img
