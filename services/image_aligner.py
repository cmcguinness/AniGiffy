import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class ImageAligner:
    """
    Aligns a set of photos so their backgrounds line up.

    For each frame we detect keypoints, match them against a reference frame,
    and fit a similarity transform (translation + rotation + uniform scale)
    with RANSAC. RANSAC is what makes this work on photos with a moving
    subject: the background is the consensus, so keypoints on a person who
    moved between shots fall out as outliers.

    Frames are then warped onto the reference and cropped to the rectangle
    every frame still covers, so no frame shows an empty edge.
    """

    # Feature detection runs on images scaled down to this longest side.
    # Keypoint geometry is scale-invariant, so this costs accuracy we can't
    # see while making detection several times faster on 4000px photos.
    DETECT_MAX_SIDE = 1200

    # Lowe's ratio test threshold for accepting a descriptor match.
    MATCH_RATIO = 0.75

    # A frame needs at least this many RANSAC inliers to be trusted.
    MIN_INLIERS = 12

    # Sanity bounds on a fitted transform. RANSAC can find a "consensus" among
    # a handful of spurious matches between unrelated photos, and the result is
    # usually degenerate -- scale collapsing toward zero, or the frame flung off
    # the canvas. Such a fit would drag the whole set's common crop to nothing,
    # so a transform this implausible is treated as no fit at all.
    MIN_SCALE = 0.25
    MAX_SCALE = 4.0
    MIN_OVERLAP = 0.35  # fraction of the reference canvas the frame must cover

    # The common-area search runs on a mask scaled down to this longest side.
    CROP_MASK_MAX_SIDE = 600

    def __init__(self, config):
        self.config = config

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _imread(self, path):
        """
        Read an image as BGR. cv2.imread can't handle non-ASCII paths on some
        platforms, so decode from bytes instead.
        """
        data = np.fromfile(str(path), dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, cv2.IMREAD_COLOR)

    def _imwrite(self, path, img):
        """Write an image, choosing the encoder from the file extension."""
        ext = str(path).rsplit('.', 1)[-1].lower()
        ext = '.png' if ext == 'png' else '.jpg'
        params = [cv2.IMWRITE_JPEG_QUALITY, 95] if ext == '.jpg' else []
        ok, buf = cv2.imencode(ext, img, params)
        if not ok:
            return False
        buf.tofile(str(path))
        return True

    def _detector(self):
        """
        SIFT finds better correspondences across exposure and time-of-day
        changes than ORB, and is no longer patent-encumbered. Fall back to ORB
        if this OpenCV build lacks it.
        """
        if hasattr(cv2, 'SIFT_create'):
            return cv2.SIFT_create(nfeatures=4000), cv2.NORM_L2
        return cv2.ORB_create(nfeatures=4000), cv2.NORM_HAMMING

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def _features(self, img, detector):
        """Detect keypoints on a downscaled copy, in full-resolution coords."""
        h, w = img.shape[:2]
        scale = min(1.0, self.DETECT_MAX_SIDE / max(h, w))

        small = img if scale == 1.0 else cv2.resize(
            img, (int(round(w * scale)), int(round(h * scale))),
            interpolation=cv2.INTER_AREA)

        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        # Equalising local contrast helps on photos shot in different light.
        gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)

        keypoints, descriptors = detector.detectAndCompute(gray, None)
        if descriptors is None or len(keypoints) == 0:
            return np.empty((0, 2), np.float32), None

        # Map keypoints back to full-resolution coordinates
        points = np.array([kp.pt for kp in keypoints], np.float32) / scale
        return points, descriptors

    def _estimate_transform(self, src, dst, norm):
        """
        Fit a similarity transform taking the frame onto the reference.

        Returns (2x3 matrix, inlier_count) or (None, 0) if no reliable fit.
        """
        src_pts, src_desc = src
        dst_pts, dst_desc = dst

        if src_desc is None or dst_desc is None:
            return None, 0
        if len(src_pts) < self.MIN_INLIERS or len(dst_pts) < self.MIN_INLIERS:
            return None, 0

        matcher = cv2.BFMatcher(norm)
        raw = matcher.knnMatch(src_desc, dst_desc, k=2)

        # Lowe's ratio test: keep matches that are clearly better than the
        # runner-up, which discards ambiguous repeated texture.
        good = [m for m, n in (p for p in raw if len(p) == 2)
                if m.distance < self.MATCH_RATIO * n.distance]

        if len(good) < self.MIN_INLIERS:
            return None, len(good)

        pts_src = np.array([src_pts[m.queryIdx] for m in good], np.float32)
        pts_dst = np.array([dst_pts[m.trainIdx] for m in good], np.float32)

        matrix, inliers = cv2.estimateAffinePartial2D(
            pts_src, pts_dst,
            method=cv2.RANSAC,
            ransacReprojThreshold=3.0,
            maxIters=5000,
            confidence=0.995,
        )

        if matrix is None or inliers is None:
            return None, 0

        inlier_count = int(inliers.sum())
        if inlier_count < self.MIN_INLIERS:
            return None, inlier_count

        return matrix, inlier_count

    # ------------------------------------------------------------------
    # Cropping
    # ------------------------------------------------------------------

    def _largest_rect(self, mask):
        """
        Largest axis-aligned rectangle of non-zero pixels in a binary mask.

        Standard maximal-rectangle-in-histogram scan: for each row, treat the
        run of set pixels above each column as a bar, then find the largest
        rectangle under that histogram with a monotonic stack.
        Returns (x, y, w, h).
        """
        rows, cols = mask.shape
        heights = np.zeros(cols + 1, np.int32)  # sentinel column of 0 at the end
        best = (0, 0, 0, 0)
        best_area = 0

        for y in range(rows):
            row = mask[y]
            heights[:cols] = np.where(row > 0, heights[:cols] + 1, 0)

            stack = []  # indices of increasing bar heights
            for x in range(cols + 1):
                start = x
                while stack and stack[-1][1] > heights[x]:
                    idx, height = stack.pop()
                    area = height * (x - idx)
                    if area > best_area:
                        best_area = area
                        best = (idx, y - height + 1, x - idx, height)
                    start = idx
                stack.append((start, heights[x]))

        return best

    def _quad(self, shape, matrix):
        """The frame's rectangle, put through the transform."""
        h, w = shape[:2]
        corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32).reshape(-1, 1, 2)
        return cv2.transform(corners, matrix).reshape(-1, 2)

    def _is_plausible(self, matrix, shape, size):
        """
        Reject a transform that can't be a real camera movement.

        Returns (ok: bool, reason: str).
        """
        scale = float(np.hypot(matrix[0, 0], matrix[1, 0]))
        if not (self.MIN_SCALE <= scale <= self.MAX_SCALE):
            return False, f'implausible scale ({scale:.2f}x)'

        width, height = size
        canvas = np.array([[0, 0], [width, 0], [width, height], [0, height]], np.float32)
        overlap, _ = cv2.intersectConvexConvex(
            self._quad(shape, matrix).astype(np.float32), canvas)

        fraction = overlap / float(width * height)
        if fraction < self.MIN_OVERLAP:
            return False, f'only {fraction * 100:.0f}% overlap with the reference'

        return True, ''

    def _coverage_mask(self, shape, matrix, size):
        """
        Where a frame lands on the reference canvas, as a small binary mask.

        The covered area is just the frame's rectangle put through the
        transform, so we fill that quad directly instead of warping a
        full-resolution mask -- same answer, a fraction of the memory.
        """
        width, height = size
        scale = min(1.0, self.CROP_MASK_MAX_SIDE / max(width, height))
        small = (max(1, int(round(height * scale))), max(1, int(round(width * scale))))

        quad = self._quad(shape, matrix) * scale

        mask = np.zeros(small, np.uint8)
        cv2.fillConvexPoly(mask, np.round(quad).astype(np.int32), 255)
        return mask

    def _common_crop(self, combined, size):
        """
        Largest rectangle covered by every frame.

        Runs on the downscaled intersection mask, then maps the result back
        and insets it so rounding can't leave a sliver of empty edge.
        """
        width, height = size
        scale = min(1.0, self.CROP_MASK_MAX_SIDE / max(width, height))

        # Drop partially-covered edge pixels introduced by rasterising the quad
        combined = cv2.erode(combined, np.ones((3, 3), np.uint8), iterations=1)

        x, y, w, h = self._largest_rect(combined)
        if w == 0 or h == 0:
            return None

        inv = 1.0 / scale
        x0 = int(np.ceil(x * inv)) + 1
        y0 = int(np.ceil(y * inv)) + 1
        x1 = int(np.floor((x + w) * inv)) - 1
        y1 = int(np.floor((y + h) * inv)) - 1

        if x1 - x0 < 2 or y1 - y0 < 2:
            return None
        return x0, y0, x1 - x0, y1 - y0

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def align(self, paths, reference_index=0):
        """
        Align images so their backgrounds line up, overwriting each file.

        Args:
            paths: list of Paths, in frame order
            reference_index: which frame everything else is aligned onto

        Returns a result dict:
            aligned:   how many frames were transformed
            skipped:   [{'index': i, 'reason': str}] for frames left as-is
            width/height: dimensions of the cropped output
            reference: index used as the reference
        """
        if len(paths) < 2:
            return {'error': 'Need at least two frames to align'}

        reference_index = max(0, min(reference_index, len(paths) - 1))

        reference = self._imread(paths[reference_index])
        if reference is None:
            return {'error': f'Could not read {paths[reference_index].name}'}

        ref_h, ref_w = reference.shape[:2]
        detector, norm = self._detector()

        ref_features = self._features(reference, detector)
        del reference
        if ref_features[1] is None:
            return {'error': 'No features found in the reference frame'}

        identity = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], np.float64)

        # Pass one: work out every transform, holding one image at a time.
        # Only the small coverage masks are accumulated, so peak memory stays
        # at a single frame regardless of how many frames there are.
        matrices = []
        combined = None
        skipped = []

        for i, path in enumerate(paths):
            img = self._imread(path)
            if img is None:
                return {'error': f'Could not read {path.name}'}

            if i == reference_index:
                matrix = identity
            else:
                matrix, inliers = self._estimate_transform(
                    self._features(img, detector), ref_features, norm)

                reason = f'only {inliers} matching features'
                if matrix is not None:
                    ok, why = self._is_plausible(matrix, img.shape, (ref_w, ref_h))
                    if not ok:
                        matrix, reason = None, why

                if matrix is None:
                    # Leave unmatched frames untransformed rather than
                    # dropping them, and say so in the result.
                    skipped.append({'index': i, 'reason': reason})
                    logger.info(f"Alignment skipped frame {i}: {reason}")
                    matrix = identity

            matrices.append(matrix)
            mask = self._coverage_mask(img.shape, matrix, (ref_w, ref_h))
            combined = mask if combined is None else cv2.bitwise_and(combined, mask)
            del img

        crop = self._common_crop(combined, (ref_w, ref_h))
        if crop is None:
            return {'error': 'Frames have too little overlap to crop to a common area'}

        # Pass two: warp, crop and write, again one image at a time.
        x, y, w, h = crop
        for path, matrix in zip(paths, matrices):
            img = self._imread(path)
            if img is None:
                return {'error': f'Could not read {path.name}'}

            warped = cv2.warpAffine(
                img, matrix, (ref_w, ref_h),
                flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_CONSTANT)
            del img

            if not self._imwrite(path, warped[y:y + h, x:x + w]):
                return {'error': f'Could not write {path.name}'}
            del warped

        logger.info(f"Aligned {len(paths) - len(skipped)}/{len(paths)} frames "
                    f"to {w}x{h} (reference frame {reference_index})")

        return {
            'aligned': len(paths) - len(skipped),
            'skipped': skipped,
            'width': w,
            'height': h,
            'reference': reference_index,
        }
