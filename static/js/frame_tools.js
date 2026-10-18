// AniGiffy per-frame tools: download one frame's image, or swap in a
// replacement for it (e.g. after retouching a still pulled from a video).
//
// A replacement is uploaded like any other image, then the existing frame is
// pointed at the new file. Its id, position and duration are kept, so the
// rest of the sequence and every setting (crop included) are untouched.

let replaceTargetFrameId = null;

document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('replaceUpload').addEventListener('change', handleReplaceSelect);
});

// The stored file as-is, so a JPEG pulled from a video isn't re-encoded
// before it is edited. Named by position so it's clear which frame it was.
function downloadFrame(frameId) {
    const index = state.frames.findIndex(f => f.id === frameId);
    if (index === -1) return;
    const frame = state.frames[index];

    const stored = frame.file.split('/').pop();
    const ext = stored.includes('.') ? stored.split('.').pop() : 'png';
    const number = String(index + 1).padStart(3, '0');
    const base = frame.name ? frame.name.replace(/\.[^.]+$/, '') + '-' : '';

    const link = document.createElement('a');
    link.href = `/api/frames/image/${stored}?v=${state.imageVersion}`;
    link.download = `${base}frame-${number}.${ext}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function startReplaceFrame(frameId) {
    replaceTargetFrameId = frameId;
    document.getElementById('replaceUpload').click();
}

async function handleReplaceSelect(event) {
    const file = event.target.files[0];
    const frameId = replaceTargetFrameId;
    event.target.value = '';
    replaceTargetFrameId = null;
    if (!file || !frameId) return;

    // Size of the image being replaced, read from its thumbnail
    const thumb = document.querySelector(`.frame-item[data-frame-id="${frameId}"] .frame-thumbnail`);
    const oldSize = thumb && thumb.naturalWidth ? { width: thumb.naturalWidth, height: thumb.naturalHeight } : null;

    try {
        const formData = new FormData();
        formData.append('file', file);
        const response = await fetch('/api/frames/upload', { method: 'POST', body: formData });
        const data = await response.json();

        if (!response.ok) {
            showToast(`Failed to upload ${file.name}: ${data.message}`, 'danger');
            return;
        }

        // The frame may have been deleted while the file was uploading
        const frame = state.frames.find(f => f.id === frameId);
        if (!frame) {
            showToast('That frame was removed before the replacement finished uploading', 'warning');
            return;
        }

        const previous = { file: frame.file, name: frame.name };
        frame.file = data.path;
        frame.name = file.name;

        // Keep the output size covering the largest frame, as uploads do
        if (data.width > (state.settings.originalWidth || 0) ||
            data.height > (state.settings.originalHeight || 0)) {
            state.settings.originalWidth = Math.max(data.width, state.settings.originalWidth || 0);
            state.settings.originalHeight = Math.max(data.height, state.settings.originalHeight || 0);
            recalcDimensionsFromScale();
        }

        stopPreview();
        updateUI();

        const number = state.frames.indexOf(frame) + 1;
        const sizeChanged = oldSize && (oldSize.width !== data.width || oldSize.height !== data.height);
        const message = sizeChanged
            ? `Frame ${number} replaced, but it is ${data.width} × ${data.height} where the original was `
              + `${oldSize.width} × ${oldSize.height}, so it won't line up with the other frames`
            : `Frame ${number} replaced`;

        showToast(message, sizeChanged ? 'warning' : 'success', {
            label: 'Undo',
            onClick: () => {
                const target = state.frames.find(f => f.id === frameId);
                if (!target) return;
                target.file = previous.file;
                target.name = previous.name;
                stopPreview();
                updateUI();
            }
        });
    } catch (error) {
        console.error('Replace error:', error);
        showToast(`Error uploading ${file.name}`, 'danger');
    }
}
