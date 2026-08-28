import hashlib
import logging

import cv2
import numpy as np
from PIL import Image

from services.image_aligner import ImageAligner

logger = logging.getLogger(__name__)


class FrameInterpolator:
    """
    Builds in-between frames that show motion, not just a dissolve.

    Two strategies, both producing a list of intermediate images for a pair
    of frames:

    "tween" fits one similarity transform (translation + rotation + uniform
    scale) between the two frames and steps a fraction of the way along it.
    It only models whole-frame movement -- camera drift -- but it can never
    smear, because every intermediate is a rigid resampling of a real photo.

    "morph" computes a dense optical flow field and moves each pixel along
    its own vector, so a subject that moved within the frame actually
    travels. Far more expressive and far more fragile: large motion,
    occlusion and flat texture all show up as smearing.

    Both warp from *both* ends and cross-dissolve the results. Each side
    fills the holes the other opens up, which is what keeps edges and
    occlusion boundaries from tearing.
    """

    # Optical flow runs on images scaled down to this longest side. Flow is a
    # smooth field, so estimating it small and scaling the vectors up costs
    # very little and is several times faster on full-size photos.
    FLOW_MAX_SIDE = 960

    # If any coherent region of the frame moved a larger fraction of the
    # frame than this, flow can't track it: the search never finds the match,
    # and morphing along the field it does return produces a smeared mess.
    # Fall back to a cross-fade instead.
    MAX_FLOW_FRACTION = 0.12

    # Forward and backward flow should cancel: follow a pixel to the next
    # frame and back, and you should land where you started. How far it can
    # miss before that pixel is called untrustworthy -- a constant slack in
    # pixels, plus a fraction of the distance travelled, since long
    # displacements earn proportionally more error honestly.
    CONSISTENCY_SLACK_PX = 1.5
    CONSISTENCY_SLACK_FRACTION = 0.08

    # Grey-level slack when scoring how well the flow actually explains the
    # next frame. Keeps a region that barely changed between frames -- where
    # both the warped and unwarped errors are near zero, and their ratio is
    # therefore meaningless -- from being judged on sensor noise.
    PHOTOMETRIC_SLACK = 8.0

    def __init__(self, config):
        self.config = config
        self.aligner = ImageAligner(config)
        # Transitions are built pair by pair down the timeline, so every frame
        # but the first and last gets its features asked for twice -- once as
        # the outgoing frame, once as the incoming one. Remembering the last
        # frame's features halves the detection work over a whole animation.
        self._feature_cache = (None, None)

    # ------------------------------------------------------------------
    # PIL <-> OpenCV
    # ------------------------------------------------------------------

    @staticmethod
    def _to_array(img):
        """PIL image -> RGBA uint8 array. Alpha rides along through warping."""
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        return np.asarray(img, dtype=np.uint8)

    @staticmethod
    def _to_image(arr):
        return Image.fromarray(arr, 'RGBA')

    @staticmethod
    def _gray(arr):
        return cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)

    # ------------------------------------------------------------------
    # Similarity tween
    # ------------------------------------------------------------------

    @staticmethod
    def _digest(arr):
        """
        Content hash of a frame, used to key the feature cache.

        Hashing the pixels rather than comparing object identity means the
        cache stays correct no matter how the caller obtained the frame --
        arrays are rebuilt on every call, so identity would never match --
        and a genuinely repeated frame gets a hit for free. blake2b over a
        few megabytes costs a small fraction of what feature detection does.
        """
        return hashlib.blake2b(np.ascontiguousarray(arr), digest_size=16).digest()

    def _features(self, arr, detector):
        """Keypoints and descriptors for a frame, reusing the last result."""
        digest = self._digest(arr)
        cached_digest, cached = self._feature_cache
        if cached_digest == digest:
            return cached

        features = self.aligner._features(
            cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2BGR), detector)
        self._feature_cache = (digest, features)
        return features

    def _fit_similarity(self, arr1, arr2):
        """
        Fit the similarity transform taking frame 1 onto frame 2.

        Reuses the aligner's feature matching, so this behaves the same way
        Auto-Align does: RANSAC treats the background as the consensus and
        discards keypoints on a subject that moved.

        Returns a 2x3 matrix, or None if there's no trustworthy fit.
        """
        detector, norm = self.aligner._detector()
        f1 = self._features(arr1, detector)
        f2 = self._features(arr2, detector)

        matrix, inliers = self.aligner._estimate_transform(f1, f2, norm)
        if matrix is None:
            logger.info(f"Motion tween: no reliable transform ({inliers} matches)")
            return None

        height, width = arr1.shape[:2]
        ok, reason = self.aligner._is_plausible(matrix, arr1.shape, (width, height))
        if not ok:
            logger.info(f"Motion tween: rejected transform -- {reason}")
            return None

        return matrix

    @staticmethod
    def _partial_transform(matrix, t):
        """
        The similarity transform t of the way from identity to `matrix`.

        A similarity is a rotation and scale about some fixed point plus, in
        the general case, nothing else -- so the honest way to take a
        fraction of one is to find that fixed point and rotate/scale about it
        by a fraction of the angle and the t-th root of the scale.
        Interpolating the matrix entries directly would instead swing the
        image through an arc that the camera never travelled.

        A pure translation has no fixed point (the system is singular); there
        the fraction of the motion is just the fraction of the offset.
        """
        linear = matrix[:, :2]
        offset = matrix[:, 2]

        scale = float(np.hypot(linear[0, 0], linear[1, 0]))
        angle = float(np.arctan2(linear[1, 0], linear[0, 0]))

        scale_t = scale ** t
        angle_t = angle * t
        cos_t, sin_t = np.cos(angle_t), np.sin(angle_t)
        linear_t = scale_t * np.array([[cos_t, -sin_t], [sin_t, cos_t]], np.float64)

        residual = np.eye(2) - linear
        if abs(np.linalg.det(residual)) < 1e-8:
            # No fixed point: translation only, which interpolates linearly.
            offset_t = offset * t
        else:
            fixed = np.linalg.solve(residual, offset)
            offset_t = fixed - linear_t @ fixed

        return np.hstack([linear_t, offset_t.reshape(2, 1)])

    def create_tween_frames(self, img1, img2, steps):
        """
        In-betweens that slide the whole frame along the camera's movement.

        Returns None if no transform could be fitted, so the caller can fall
        back to a cross-fade.
        """
        arr1, arr2 = self._to_array(img1), self._to_array(img2)
        if arr1.shape != arr2.shape:
            return None

        matrix = self._fit_similarity(arr1, arr2)
        if matrix is None:
            return None

        height, width = arr1.shape[:2]
        square = np.vstack([matrix, [0, 0, 1]])
        inverse = np.linalg.inv(square)

        frames = []
        for i in range(1, steps + 1):
            t = i / (steps + 1)
            partial = self._partial_transform(matrix, t)

            # Frame 1 moves t of the way forward; frame 2 moves the remaining
            # (1 - t) back, by composing the partial with the full inverse.
            # Both land on the same intermediate geometry, so the dissolve
            # between them has nothing left to slide.
            back = (np.vstack([partial, [0, 0, 1]]) @ inverse)[:2]

            # Replicating the edge pixels keeps the few pixels uncovered by
            # the warp from flashing as a black border.
            warp1 = cv2.warpAffine(arr1, partial, (width, height),
                                   flags=cv2.INTER_LANCZOS4,
                                   borderMode=cv2.BORDER_REPLICATE)
            warp2 = cv2.warpAffine(arr2, back, (width, height),
                                   flags=cv2.INTER_LANCZOS4,
                                   borderMode=cv2.BORDER_REPLICATE)

            frames.append(self._to_image(self._blend(warp1, warp2, t)))

        return frames

    # ------------------------------------------------------------------
    # Optical flow morph
    # ------------------------------------------------------------------

    def _flow(self, gray1, gray2):
        """Dense flow from gray1 to gray2, estimated on downscaled copies."""
        height, width = gray1.shape[:2]
        scale = min(1.0, self.FLOW_MAX_SIDE / max(height, width))

        if scale < 1.0:
            size = (int(round(width * scale)), int(round(height * scale)))
            small1 = cv2.resize(gray1, size, interpolation=cv2.INTER_AREA)
            small2 = cv2.resize(gray2, size, interpolation=cv2.INTER_AREA)
        else:
            small1, small2 = gray1, gray2

        if hasattr(cv2, 'DISOpticalFlow_create'):
            flow = cv2.DISOpticalFlow_create(
                cv2.DISOPTICAL_FLOW_PRESET_MEDIUM).calc(small1, small2, None)
        else:
            flow = cv2.calcOpticalFlowFarneback(
                small1, small2, None,
                pyr_scale=0.5, levels=4, winsize=21,
                iterations=3, poly_n=7, poly_sigma=1.5, flags=0)

        if scale < 1.0:
            # Scaling the field back up has to scale the vectors too: a
            # 5px displacement measured at half size is 10px at full size.
            flow = cv2.resize(flow, (width, height), interpolation=cv2.INTER_LINEAR) / scale

        return flow

    @staticmethod
    def _largest_motion(flow):
        """
        The largest *coherent* displacement in a flow field, in pixels.

        A plain maximum would fire on single-pixel noise, and a percentile
        misses the case this needs to catch -- one subject crossing the frame
        while the background sits still, which is only a few percent of the
        pixels no matter how far it travelled. Median-blurring the magnitudes
        first drops isolated outliers but leaves any region large enough to
        actually see, so the maximum then means what it should.
        """
        magnitude = np.hypot(flow[:, :, 0], flow[:, :, 1]).astype(np.float32)
        return float(cv2.medianBlur(magnitude, 5).max())

    def _photometric(self, source, target, flow):
        """
        Per-pixel confidence that `flow` really explains `target`, as a 0..1
        map on `target`'s grid.

        The forward/backward check catches flow that contradicts itself, but
        not flow that fails the same way in both directions -- when motion
        outruns the search, both fields agree the pixel barely moved, and
        both are wrong. That only shows up by carrying the frame all the way
        across and seeing whether it lands on the next one.

        Scored against how wrong doing nothing would have been, rather than
        against an absolute threshold, so an exposure change between two
        photos -- which lifts both errors together -- doesn't read as failed
        tracking.
        """
        warped = self._warp_along(source, flow, 1.0).astype(np.float32)
        target = target.astype(np.float32)

        moved_error = cv2.GaussianBlur(np.abs(warped - target), (0, 0), 3.0)
        static_error = cv2.GaussianBlur(np.abs(source.astype(np.float32) - target), (0, 0), 3.0)

        # Full trust where the warp removes the error, none where it does no
        # better than leaving the pixel alone.
        ratio = moved_error / (static_error + self.PHOTOMETRIC_SLACK)
        return np.clip(2.0 * (1.0 - ratio), 0.0, 1.0).astype(np.float32)

    def _consistency(self, flow, reverse):
        """
        Per-pixel confidence in `flow`, as a 0..1 map.

        Follows each pixel along `flow` and back along `reverse`; the distance
        it lands from where it started is the error. Occlusions and untracked
        regions -- exactly the places a warp would smear -- fail this, because
        there is nothing on the other side to come back from.
        """
        height, width = flow.shape[:2]
        grid_x, grid_y = np.meshgrid(np.arange(width, dtype=np.float32),
                                     np.arange(height, dtype=np.float32))
        landed = cv2.remap(reverse, grid_x + flow[:, :, 0], grid_y + flow[:, :, 1],
                           cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

        residual = flow + landed
        error = np.hypot(residual[:, :, 0], residual[:, :, 1])
        travelled = np.hypot(flow[:, :, 0], flow[:, :, 1])
        allowed = self.CONSISTENCY_SLACK_PX + self.CONSISTENCY_SLACK_FRACTION * travelled

        # Ramp from full trust at the allowed error to none at twice it, so
        # the transition between moved and cross-faded pixels is gradual
        # rather than a visible hard edge.
        trust = np.clip(2.0 - error / np.maximum(allowed, 1e-6), 0.0, 1.0)
        return cv2.GaussianBlur(trust.astype(np.float32), (0, 0), 3.0)

    @staticmethod
    def _warp_along(arr, flow, amount):
        """
        Pull each output pixel from wherever it came from, `amount` of the
        way along the flow field. Backward sampling, so every output pixel
        gets a value -- no scatter, no holes.
        """
        height, width = arr.shape[:2]
        grid_x, grid_y = np.meshgrid(np.arange(width, dtype=np.float32),
                                     np.arange(height, dtype=np.float32))
        map_x = grid_x + amount * flow[:, :, 0]
        map_y = grid_y + amount * flow[:, :, 1]
        return cv2.remap(arr, map_x, map_y, cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_REPLICATE)

    @staticmethod
    def _blend(a, b, t):
        return cv2.addWeighted(a, 1.0 - t, b, t, 0.0)

    def create_morph_frames(self, img1, img2, steps):
        """
        In-betweens that move each pixel along its own motion vector.

        Returns None if the motion looks too large to interpolate honestly,
        so the caller can fall back to a cross-fade.
        """
        arr1, arr2 = self._to_array(img1), self._to_array(img2)
        if arr1.shape != arr2.shape:
            return None

        gray1, gray2 = self._gray(arr1), self._gray(arr2)
        forward = self._flow(gray1, gray2)
        backward = self._flow(gray2, gray1)


        height, width = arr1.shape[:2]
        limit = self.MAX_FLOW_FRACTION * max(height, width)
        if self._largest_motion(forward) > limit or self._largest_motion(backward) > limit:
            logger.info(f"Motion morph: motion exceeds {limit:.0f}px, too far for flow "
                        f"to track -- falling back to cross-fade")
            return None

        # Where the two flow fields disagree, the pixel is occluded or simply
        # wasn't tracked, and warping it invents motion that isn't there.
        # Those pixels cross-fade instead of moving.
        # Each trust map lives on the grid of the frame it describes, so the
        # photometric warp has to be the one that lands on that same grid:
        # the forward field is indexed by frame 1's pixels, the backward
        # field by frame 2's.
        trust1 = np.minimum(self._consistency(forward, backward),
                            self._photometric(gray2, gray1, forward))
        trust2 = np.minimum(self._consistency(backward, forward),
                            self._photometric(gray1, gray2, backward))

        frames = []
        for i in range(1, steps + 1):
            t = i / (steps + 1)
            # Each source is dragged toward the other frame's time, then the
            # two are mixed by how far along we are -- so whichever frame the
            # intermediate is closer to contributes the least-warped pixels.
            warp1 = self._warp_along(arr1, backward, t)
            warp2 = self._warp_along(arr2, forward, 1.0 - t)
            moved = self._blend(warp1, warp2, t)

            # Trust has to travel with the pixels it describes, so it is
            # warped by the same maps as the frames it came from. A pixel is
            # only moved if both ends agree it can be.
            trust = np.minimum(self._warp_along(trust1, backward, t),
                               self._warp_along(trust2, forward, 1.0 - t))

            plain = self._blend(arr1, arr2, t)
            trust = trust[:, :, None]
            frames.append(self._to_image(
                (moved * trust + plain * (1.0 - trust)).astype(np.uint8)))

        return frames
