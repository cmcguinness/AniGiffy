// AniGiffy crop: one rectangle trimmed from every frame before it is resized.
//
// The crop lives in state.settings.crop as the share of each edge to trim
// ({left, top, right, bottom}, fractions 0-1) rather than pixels, so one crop
// fits frames of differing sizes and survives the server downscaling an
// oversized upload. The pixel values shown are for the frame being edited.
// It travels to the server with the rest of the settings and is applied in
// ImageProcessor.prepare_frame, so the stored images are never touched.

const CROP_EDGES = ['left', 'top', 'right', 'bottom'];

let cropper = null;
let cropFrameSize = null;      // natural size of the frame shown in the modal
let syncingCropInputs = false; // true while typed values are pushed into the cropper

document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('openCropBtn').addEventListener('click', openCropModal);
    document.getElementById('clearCropBtn').addEventListener('click', clearCrop);
    document.getElementById('applyCropBtn').addEventListener('click', applyCrop);
    document.getElementById('resetCropBtn').addEventListener('click', () => cropper && cropper.reset());
    document.getElementById('cropAspect').addEventListener('change', function() {
        if (cropper) cropper.setAspectRatio(parseFloat(this.value));
    });

    CROP_EDGES.forEach(edge => {
        const input = document.getElementById(`crop-${edge}`);
        input.addEventListener('input', pushCropInputsToCropper);
        // Once the user is done typing, show what the cropper actually
        // accepted (it clamps to the image and honours the aspect lock).
        input.addEventListener('change', pullCropFromCropper);
    });

    const modalEl = document.getElementById('cropModal');
    modalEl.addEventListener('shown.bs.modal', function() {
        const img = document.getElementById('cropImage');
        if (img.complete && img.naturalWidth) {
            initCropper(img);
        } else {
            img.addEventListener('load', () => initCropper(img), { once: true });
        }
    });
    modalEl.addEventListener('hidden.bs.modal', function() {
        if (cropper) {
            cropper.destroy();
            cropper = null;
        }
    });

    updateCropSummary();
});

function hasCrop() {
    const c = state.settings.crop;
    return !!c && CROP_EDGES.some(edge => c[edge] > 0);
}

// Size of the original frames once the crop is trimmed off
function getCroppedSourceDimensions() {
    const w = state.settings.originalWidth;
    const h = state.settings.originalHeight;
    if (!w || !h) return { width: null, height: null };
    const c = state.settings.crop || { left: 0, top: 0, right: 0, bottom: 0 };
    return {
        width: Math.max(1, Math.round(w * (1 - c.left - c.right))),
        height: Math.max(1, Math.round(h * (1 - c.top - c.bottom)))
    };
}

function openCropModal() {
    if (state.frames.length === 0) {
        showToast('Add some frames before cropping', 'warning');
        return;
    }

    const img = document.getElementById('cropImage');
    img.src = `/api/frames/image/${state.frames[0].file.split('/').pop()}?v=${state.imageVersion}`;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('cropModal')).show();
}

function initCropper(img) {
    if (cropper) cropper.destroy();

    cropper = new Cropper(img, {
        viewMode: 1,          // keep the box inside the image
        autoCropArea: 1,      // with no crop yet, start from the whole frame
        zoomable: false,
        movable: false,
        rotatable: false,
        scalable: false,
        aspectRatio: parseFloat(document.getElementById('cropAspect').value),
        ready() {
            const data = cropper.getImageData();
            cropFrameSize = { width: data.naturalWidth, height: data.naturalHeight };
            if (hasCrop()) {
                const c = state.settings.crop;
                cropper.setData({
                    x: c.left * cropFrameSize.width,
                    y: c.top * cropFrameSize.height,
                    width: (1 - c.left - c.right) * cropFrameSize.width,
                    height: (1 - c.top - c.bottom) * cropFrameSize.height
                });
            }
            pullCropFromCropper();
        },
        crop(event) {
            if (!syncingCropInputs) setCropInputs(event.detail);
        }
    });
}

// Box from the cropper ({x, y, width, height}) -> pixel insets per edge
function boxToInsets(box) {
    const left = Math.max(0, Math.round(box.x));
    const top = Math.max(0, Math.round(box.y));
    return {
        left,
        top,
        right: Math.max(0, cropFrameSize.width - left - Math.round(box.width)),
        bottom: Math.max(0, cropFrameSize.height - top - Math.round(box.height))
    };
}

function setCropInputs(box) {
    if (!cropFrameSize) return;
    const insets = boxToInsets(box);
    CROP_EDGES.forEach(edge => {
        document.getElementById(`crop-${edge}`).value = insets[edge];
    });
    updateCropResultLabel(insets);
}

function readCropInputs() {
    const insets = {};
    CROP_EDGES.forEach(edge => {
        insets[edge] = Math.max(0, parseInt(document.getElementById(`crop-${edge}`).value) || 0);
    });
    return insets;
}

function pullCropFromCropper() {
    if (cropper && cropFrameSize) setCropInputs(cropper.getData(true));
}

function pushCropInputsToCropper() {
    if (!cropper || !cropFrameSize) return;
    const i = readCropInputs();
    const width = cropFrameSize.width - i.left - i.right;
    const height = cropFrameSize.height - i.top - i.bottom;
    if (width < 1 || height < 1) return;

    syncingCropInputs = true;
    try {
        cropper.setData({ x: i.left, y: i.top, width, height });
    } finally {
        syncingCropInputs = false;
    }
    updateCropResultLabel(i);
}

function updateCropResultLabel(insets) {
    const w = cropFrameSize.width - insets.left - insets.right;
    const h = cropFrameSize.height - insets.top - insets.bottom;
    document.getElementById('cropResultSize').textContent =
        `${w} × ${h} px (from ${cropFrameSize.width} × ${cropFrameSize.height})`;
}

function applyCrop() {
    if (!cropper || !cropFrameSize) return;

    const insets = boxToInsets(cropper.getData(true));
    const crop = {
        left: insets.left / cropFrameSize.width,
        top: insets.top / cropFrameSize.height,
        right: insets.right / cropFrameSize.width,
        bottom: insets.bottom / cropFrameSize.height
    };
    state.settings.crop = CROP_EDGES.some(edge => crop[edge] > 0) ? crop : null;

    // Bootstrap warns if the modal is hidden while one of its buttons has focus
    document.activeElement.blur();
    bootstrap.Modal.getInstance(document.getElementById('cropModal')).hide();
    onCropChanged();
    showToast(hasCrop() ? 'Crop applied to all frames' : 'Crop cleared', 'info');
}

function clearCrop() {
    state.settings.crop = null;
    onCropChanged();
    showToast('Crop cleared', 'info');
}

function onCropChanged() {
    // Output size follows the cropped image, at the current scale
    recalcDimensionsFromScale();
    stopPreview();
    updateCropSummary();
    updateUI();
}

// Rotating the frames carries the crop round with them
function rotateCrop(direction) {
    const c = state.settings.crop;
    if (!c) return;
    state.settings.crop = direction === 'right'
        ? { left: c.bottom, top: c.left, right: c.top, bottom: c.right }   // clockwise
        : { left: c.top, top: c.right, right: c.bottom, bottom: c.left };  // counter-clockwise
    updateCropSummary();
}

function updateCropSummary() {
    const summary = document.getElementById('cropSummary');
    const clearBtn = document.getElementById('clearCropBtn');
    if (!summary) return;

    if (!hasCrop()) {
        summary.textContent = 'None — full frame';
        clearBtn.classList.add('d-none');
        return;
    }

    const dims = getCroppedSourceDimensions();
    summary.textContent = dims.width
        ? `${dims.width} × ${dims.height} from ${state.settings.originalWidth} × ${state.settings.originalHeight}`
        : 'Cropped';
    clearBtn.classList.remove('d-none');
}
