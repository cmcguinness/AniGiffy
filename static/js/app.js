// AniGiffy Frontend Application

// Application State
const state = {
    settings: {
        originalWidth: null,
        originalHeight: null,
        scale: 100,
        loop: 0,
        defaultDuration: 100,
        transparent: false,
        backgroundColor: '#FFFFFF',
        alphaThreshold: 128,
        transitionType: 'crossfade',
        transitionTime: 0,
        transitionSteps: 5,
        outputFormat: 'gif'
    },
    frames: [],
    currentPreview: null
};

// Calculate scaled dimensions
function getScaledDimensions() {
    const w = parseInt(document.getElementById('outputWidth').value);
    const h = parseInt(document.getElementById('outputHeight').value);
    if (!w || !h) {
        return { width: null, height: null };
    }
    return { width: w, height: h };
}

// Initialize application
document.addEventListener('DOMContentLoaded', function() {
    initializeEventListeners();
    updateUI();
});

// Event Listeners
function initializeEventListeners() {
    // Image upload handler
    document.getElementById('imageUpload').addEventListener('change', handleImageUpload);

    // Drag and drop handlers
    const dropZone = document.getElementById('dropZone');

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove('drag-over');

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleImageUpload({ target: { files: files } });
        }
    });

    // Generate buttons
    document.getElementById('generatePreview').addEventListener('click', () => generatePreview(null));
    document.getElementById('generateQuickPreview').addEventListener('click', () => generatePreview(10));
    document.getElementById('generateFullPreview').addEventListener('click', () => generatePreview(null));
    document.getElementById('generateFull').addEventListener('click', generateFullGIF);
    document.getElementById('stopPreview').addEventListener('click', stopPreview);

    // Settings inputs
    document.getElementById('outputFormat').addEventListener('change', updateSettings);
    document.getElementById('scale').addEventListener('change', updateSettings);
    document.getElementById('loop').addEventListener('change', updateSettings);
    document.getElementById('outputWidth').addEventListener('change', updateSettings);
    document.getElementById('outputHeight').addEventListener('change', updateSettings);

    // Transparency settings
    document.getElementById('transparent').addEventListener('change', updateTransparencySettings);
    document.getElementById('backgroundColor').addEventListener('change', updateSettings);
    document.getElementById('alphaThreshold').addEventListener('input', updateAlphaThreshold);

    // Transition settings
    document.getElementById('transitionType').addEventListener('change', updateSettings);
    document.getElementById('transitionTime').addEventListener('change', updateSettings);
    document.getElementById('transitionSteps').addEventListener('change', updateSettings);

    // Video import
    document.getElementById('importVideoBtn').addEventListener('click', () => {
        document.getElementById('videoUpload').click();
    });
    document.getElementById('videoUpload').addEventListener('change', handleVideoSelect);
    document.getElementById('extractFps').addEventListener('change', updateEstimatedFrames);
    document.getElementById('extractFramesBtn').addEventListener('click', handleVideoExtract);
}

// Image Upload
async function handleImageUpload(event) {
    const files = event.target.files;
    if (files.length === 0) return;

    for (let file of files) {
        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/frames/upload', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (response.ok) {
                // Track largest dimensions across all uploads
                if (data.width > (state.settings.originalWidth || 0) ||
                    data.height > (state.settings.originalHeight || 0)) {
                    state.settings.originalWidth = Math.max(data.width, state.settings.originalWidth || 0);
                    state.settings.originalHeight = Math.max(data.height, state.settings.originalHeight || 0);
                    recalcDimensionsFromScale();
                }

                // Auto-enable transparency if first image has it
                if (state.frames.length === 0 && data.hasTransparency) {
                    state.settings.transparent = true;
                    document.getElementById('transparent').checked = true;
                    updateTransparencyUI();
                }

                // Add frame to state
                const frame = {
                    id: `frame-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
                    file: data.path,
                    duration: state.settings.defaultDuration
                };

                state.frames.push(frame);
                updateUI();
            } else {
                showToast(`Failed to upload ${file.name}: ${data.message}`, 'danger');
            }
        } catch (error) {
            console.error('Upload error:', error);
            showToast(`Error uploading ${file.name}`, 'danger');
        }
    }

    // Reset input
    event.target.value = '';
}

// Frame Management
function renderFrames() {
    const frameList = document.getElementById('frameList');
    frameList.innerHTML = '';

    // Render existing frames
    state.frames.forEach((frame, index) => {
        const frameElement = createFrameElement(frame, index);
        frameList.appendChild(frameElement);
    });

    // Always add "Add Image" placeholder at the end
    const addImagePlaceholder = createAddImagePlaceholder();
    frameList.appendChild(addImagePlaceholder);
}

function createAddImagePlaceholder() {
    const div = document.createElement('div');
    div.className = 'add-image-placeholder';
    div.innerHTML = `
        <i class="bi bi-plus-circle"></i>
        <p class="mb-0">Drop image here<br>or click to upload</p>
    `;

    // Make it clickable to trigger file upload
    div.addEventListener('click', function() {
        document.getElementById('imageUpload').click();
    });

    // Drag and drop handlers
    div.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.stopPropagation();
        div.classList.add('drag-over');
    });

    div.addEventListener('dragleave', (e) => {
        e.preventDefault();
        e.stopPropagation();
        div.classList.remove('drag-over');
    });

    div.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        div.classList.remove('drag-over');

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleImageUpload({ target: { files: files } });
        }
    });

    return div;
}

function createFrameElement(frame, index) {
    const div = document.createElement('div');
    div.className = 'frame-item';
    div.draggable = true;
    div.dataset.frameId = frame.id;
    div.dataset.index = index;

    div.innerHTML = `
        <img src="/api/frames/image/${frame.file.split('/').pop()}"
             class="frame-thumbnail"
             alt="Frame ${index + 1}">
        <div class="frame-controls">
            <div>
                <small class="text-muted">Duration:</small>
                <input type="number" class="form-control form-control-sm frame-duration"
                       value="${frame.duration}" min="1" data-frame-id="${frame.id}">
            </div>
            <i class="bi bi-trash frame-delete" data-frame-id="${frame.id}"></i>
        </div>
    `;

    // Handle image load error
    const img = div.querySelector('img');
    img.addEventListener('error', function() {
        this.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="%23ddd"/></svg>';
    });

    // Duration change handler
    const durationInput = div.querySelector('.frame-duration');
    durationInput.addEventListener('change', function() {
        updateFrameDuration(this.dataset.frameId, this.value);
    });

    // Delete handler
    const deleteBtn = div.querySelector('.frame-delete');
    deleteBtn.addEventListener('click', function() {
        deleteFrame(this.dataset.frameId);
    });

    // Drag and drop events
    div.addEventListener('dragstart', handleDragStart);
    div.addEventListener('dragover', handleDragOver);
    div.addEventListener('drop', handleDrop);
    div.addEventListener('dragend', handleDragEnd);

    return div;
}

function updateFrameDuration(frameId, duration) {
    const frame = state.frames.find(f => f.id === frameId);
    if (frame) {
        frame.duration = parseInt(duration);
    }
}

function deleteFrame(frameId) {
    if (confirm('Remove this frame?')) {
        state.frames = state.frames.filter(f => f.id !== frameId);
        updateUI();
        showToast('Frame removed', 'info');
    }
}

// Drag and Drop
let draggedElement = null;

function handleDragStart(e) {
    draggedElement = this;
    this.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
}

function handleDragOver(e) {
    if (e.preventDefault) {
        e.preventDefault();
    }
    e.dataTransfer.dropEffect = 'move';
    return false;
}

function handleDrop(e) {
    if (e.stopPropagation) {
        e.stopPropagation();
    }

    if (draggedElement !== this) {
        const draggedIndex = parseInt(draggedElement.dataset.index);
        const targetIndex = parseInt(this.dataset.index);

        // Reorder frames
        const frame = state.frames.splice(draggedIndex, 1)[0];
        state.frames.splice(targetIndex, 0, frame);

        updateUI();
    }

    return false;
}

function handleDragEnd(e) {
    this.classList.remove('dragging');
}

// GIF Generation
async function generatePreview(maxFrames = 10) {
    if (state.frames.length === 0) {
        showToast('Add frames before generating', 'warning');
        return;
    }

    // Stop current preview if one is showing
    if (state.currentPreview) {
        stopPreview();
    }

    const isQuick = maxFrames !== null;
    const previewButton = document.getElementById('generatePreview');
    const quickButton = document.getElementById('generateQuickPreview');
    const fullButton = document.getElementById('generateFullPreview');
    const statusDiv = document.getElementById('generationStatus');

    // Disable all preview buttons
    previewButton.disabled = true;
    quickButton.disabled = true;
    fullButton.disabled = true;

    // Determine which button was clicked
    let button;
    let statusMessage;

    if (state.frames.length <= 10) {
        // Single preview button mode
        button = previewButton;
        statusMessage = 'Generating preview...';
    } else {
        // Dual button mode
        button = isQuick ? quickButton : fullButton;
        statusMessage = isQuick
            ? `Generating quick preview (up to ${maxFrames} frames)...`
            : 'Generating full preview (all frames)...';
    }

    const originalHTML = button.innerHTML;
    button.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Generating...';
    statusDiv.innerHTML = `<small class="text-muted">${statusMessage}</small>`;

    try {
        const dims = getScaledDimensions();
        const requestBody = {
            project: {
                name: 'Animation',
                settings: {
                    ...state.settings,
                    width: dims.width,
                    height: dims.height
                },
                frames: state.frames
            }
        };

        // Add maxFrames to request if it's a quick preview
        if (isQuick) {
            requestBody.maxFrames = maxFrames;
        }

        const response = await fetch('/api/generate/preview', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });

        const data = await response.json();

        if (response.ok) {
            displayPreview(data.path);
            statusDiv.innerHTML = `<small class="text-success">${data.message} (${formatFileSize(data.size)})</small>`;
        } else {
            showToast(`Preview failed: ${data.message}`, 'danger');
            statusDiv.innerHTML = `<small class="text-danger">Error: ${data.message}</small>`;
        }
    } catch (error) {
        console.error('Preview generation error:', error);
        showToast('Preview generation failed', 'danger');
        statusDiv.innerHTML = '<small class="text-danger">Generation failed</small>';
    } finally {
        button.innerHTML = originalHTML;

        // Re-enable buttons based on current frame count
        const hasFrames = state.frames.length > 0;
        const dims = getScaledDimensions();
        const hasDimensions = dims.width && dims.height;
        const canGenerate = hasFrames && hasDimensions;

        previewButton.disabled = !canGenerate;
        quickButton.disabled = !canGenerate;
        fullButton.disabled = !canGenerate;
    }
}

async function generateFullGIF() {
    if (state.frames.length === 0) {
        showToast('Add frames before generating', 'warning');
        return;
    }

    const button = document.getElementById('generateFull');
    const statusDiv = document.getElementById('generationStatus');

    button.disabled = true;
    const fmtLabel = state.settings.outputFormat === 'apng' ? 'APNG' : 'GIF';
    button.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Generating...';
    statusDiv.innerHTML = `<small class="text-muted">Generating full ${fmtLabel}...</small>`;

    try {
        const dims = getScaledDimensions();
        const response = await fetch('/api/generate/full', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                project: {
                    name: 'Animation',
                    settings: {
                        ...state.settings,
                        width: dims.width,
                        height: dims.height
                    },
                    frames: state.frames
                }
            })
        });

        const data = await response.json();

        if (response.ok) {
            displayPreview(data.path);
            showToast('GIF generated! Downloading...', 'success');
            statusDiv.innerHTML = `<small class="text-success">Generated: ${data.filename} (${formatFileSize(data.size)})</small>`;

            // Trigger download automatically
            const link = document.createElement('a');
            link.href = `/api/generate/download/${data.filename}`;
            link.download = data.filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        } else {
            showToast(`Generation failed: ${data.message}`, 'danger');
            statusDiv.innerHTML = `<small class="text-danger">Error: ${data.message}</small>`;
        }
    } catch (error) {
        console.error('GIF generation error:', error);
        showToast('GIF generation failed', 'danger');
        statusDiv.innerHTML = '<small class="text-danger">Generation failed</small>';
    } finally {
        button.disabled = false;
        const fmt = state.settings.outputFormat === 'apng' ? 'APNG' : 'GIF';
        button.innerHTML = `<i class="bi bi-download"></i> Generate ${fmt}`;
    }
}

function displayPreview(path) {
    const placeholder = document.getElementById('previewPlaceholder');
    const image = document.getElementById('previewImage');
    const stopBtn = document.getElementById('stopPreview');

    placeholder.classList.add('d-none');
    image.classList.remove('d-none');
    stopBtn.classList.remove('d-none');

    // Add cache buster to force reload
    image.src = path + '?t=' + Date.now();
    state.currentPreview = path;
}

function stopPreview() {
    const placeholder = document.getElementById('previewPlaceholder');
    const image = document.getElementById('previewImage');
    const stopBtn = document.getElementById('stopPreview');
    const statusDiv = document.getElementById('generationStatus');

    // Hide preview, show placeholder
    image.classList.add('d-none');
    image.src = '';
    placeholder.classList.remove('d-none');
    stopBtn.classList.add('d-none');
    statusDiv.innerHTML = '';
    state.currentPreview = null;
}

// Settings Updates
function updateSettings(event) {
    const oldScale = state.settings.scale;
    state.settings.outputFormat = document.getElementById('outputFormat').value;
    state.settings.scale = parseInt(document.getElementById('scale').value);
    state.settings.loop = parseInt(document.getElementById('loop').value);
    state.settings.transparent = document.getElementById('transparent').checked;
    state.settings.backgroundColor = document.getElementById('backgroundColor').value;
    state.settings.alphaThreshold = parseInt(document.getElementById('alphaThreshold').value);
    state.settings.transitionType = document.getElementById('transitionType').value;
    state.settings.transitionTime = parseInt(document.getElementById('transitionTime').value);
    state.settings.transitionSteps = parseInt(document.getElementById('transitionSteps').value);

    // Only recalc dimensions from scale when scale actually changed
    if (state.settings.scale !== oldScale) {
        recalcDimensionsFromScale();
    }
    updateGenerateButtonLabel();
}

function updateGenerateButtonLabel() {
    const fmt = state.settings.outputFormat === 'apng' ? 'APNG' : 'GIF';
    const btn = document.getElementById('generateFull');
    if (!btn.querySelector('.spinner-border')) {
        btn.innerHTML = `<i class="bi bi-download"></i> Generate ${fmt}`;
    }
}

function recalcDimensionsFromScale() {
    if (!state.settings.originalWidth || !state.settings.originalHeight) return;
    const scale = state.settings.scale;
    document.getElementById('outputWidth').value = Math.round(state.settings.originalWidth * scale / 100);
    document.getElementById('outputHeight').value = Math.round(state.settings.originalHeight * scale / 100);
}

function updateOutputSizeDisplay() {
    recalcDimensionsFromScale();
}

function updateTransparencySettings() {
    const isTransparent = document.getElementById('transparent').checked;
    state.settings.transparent = isTransparent;
    updateTransparencyUI();
}

function updateAlphaThreshold() {
    const value = parseInt(document.getElementById('alphaThreshold').value);
    state.settings.alphaThreshold = value;
    document.getElementById('alphaThresholdValue').textContent = value;
}

function updateTransparencyUI() {
    const isTransparent = state.settings.transparent;
    const backgroundColorGroup = document.getElementById('backgroundColorGroup');
    const alphaThresholdGroup = document.getElementById('alphaThresholdGroup');

    if (isTransparent) {
        backgroundColorGroup.classList.add('d-none');
        alphaThresholdGroup.classList.remove('d-none');
    } else {
        backgroundColorGroup.classList.remove('d-none');
        alphaThresholdGroup.classList.add('d-none');
    }
}

// UI Updates
function updateUI() {
    // Update form inputs
    document.getElementById('outputFormat').value = state.settings.outputFormat;
    document.getElementById('scale').value = state.settings.scale;
    document.getElementById('loop').value = state.settings.loop;
    updateGenerateButtonLabel();

    // Update transparency settings
    document.getElementById('transparent').checked = state.settings.transparent;
    document.getElementById('backgroundColor').value = state.settings.backgroundColor;
    document.getElementById('alphaThreshold').value = state.settings.alphaThreshold;
    document.getElementById('alphaThresholdValue').textContent = state.settings.alphaThreshold;
    updateTransparencyUI();

    // Update transition settings
    document.getElementById('transitionType').value = state.settings.transitionType;

    // Render frames
    renderFrames();

    // Enable/disable generate buttons (need frames and dimensions)
    const hasFrames = state.frames.length > 0;
    const dims = getScaledDimensions();
    const hasDimensions = dims.width && dims.height;
    const canGenerate = hasFrames && hasDimensions;

    // Show single preview button if 10 or fewer frames, otherwise show both
    const previewButton = document.getElementById('generatePreview');
    const quickButton = document.getElementById('generateQuickPreview');
    const fullButton = document.getElementById('generateFullPreview');

    if (state.frames.length <= 10) {
        // Show single preview button
        previewButton.classList.remove('d-none');
        quickButton.classList.add('d-none');
        fullButton.classList.add('d-none');
        previewButton.disabled = !canGenerate;
    } else {
        // Show quick and full preview buttons
        previewButton.classList.add('d-none');
        quickButton.classList.remove('d-none');
        fullButton.classList.remove('d-none');
        quickButton.disabled = !canGenerate;
        fullButton.disabled = !canGenerate;
    }

    document.getElementById('generateFull').disabled = !canGenerate;
}

// Utility Functions
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer');

    const toastId = 'toast-' + Date.now();
    const toastHTML = `
        <div id="${toastId}" class="toast" role="alert">
            <div class="toast-header bg-${type} text-white">
                <strong class="me-auto">AniGiffy</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        </div>
    `;

    toastContainer.insertAdjacentHTML('beforeend', toastHTML);

    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, { delay: 3000 });
    toast.show();

    toastElement.addEventListener('hidden.bs.toast', function() {
        toastElement.remove();
    });
}

// ── Video Import ──

// Temporary state for the video import modal
let videoImportState = {
    filename: null,
    duration: 0,
    width: 0,
    height: 0,
    fps: 0,
    remainingSlots: 50,
};

async function handleVideoSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    event.target.value = '';

    const modal = new bootstrap.Modal(document.getElementById('videoImportModal'));
    const errorEl = document.getElementById('videoError');
    const infoEl = document.getElementById('videoInfo');
    const progressEl = document.getElementById('videoUploadProgress');
    const progressLabel = document.getElementById('videoProgressLabel');
    const extractBtn = document.getElementById('extractFramesBtn');

    // Reset modal state
    errorEl.classList.add('d-none');
    infoEl.classList.add('d-none');
    extractBtn.classList.add('d-none');
    extractBtn.disabled = true;
    progressEl.classList.remove('d-none');
    progressLabel.textContent = 'Uploading video...';
    modal.show();

    try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('/api/video/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        progressEl.classList.add('d-none');

        if (!response.ok) {
            errorEl.textContent = data.message || data.error || 'Upload failed';
            errorEl.classList.remove('d-none');
            return;
        }

        // Populate modal info
        videoImportState.filename = data.filename;
        videoImportState.duration = data.duration;
        videoImportState.width = data.width;
        videoImportState.height = data.height;
        videoImportState.fps = data.fps;
        videoImportState.remainingSlots = data.remainingSlots;

        document.getElementById('videoFilename').textContent = file.name;
        document.getElementById('videoDuration').textContent = data.duration.toFixed(1) + 's';
        document.getElementById('videoResolution').textContent = `${data.width} x ${data.height}`;
        document.getElementById('videoFps').textContent = data.fps.toFixed(1);
        document.getElementById('videoCodec').textContent = data.codec;

        infoEl.classList.remove('d-none');
        extractBtn.classList.remove('d-none');
        updateEstimatedFrames();

    } catch (err) {
        progressEl.classList.add('d-none');
        errorEl.textContent = 'Network error uploading video';
        errorEl.classList.remove('d-none');
        console.error('Video upload error:', err);
    }
}

function updateEstimatedFrames() {
    const fps = parseFloat(document.getElementById('extractFps').value);
    const count = Math.ceil(videoImportState.duration * fps);
    document.getElementById('estimatedFrames').textContent = count;

    // Check quota using server-provided remaining slots
    const remaining = videoImportState.remainingSlots;
    const warning = document.getElementById('frameQuotaWarning');
    const extractBtn = document.getElementById('extractFramesBtn');

    if (count > remaining) {
        warning.classList.remove('d-none');
        extractBtn.disabled = true;
    } else {
        warning.classList.add('d-none');
        extractBtn.disabled = false;
    }
}

async function handleVideoExtract() {
    const extractBtn = document.getElementById('extractFramesBtn');
    const progressEl = document.getElementById('videoUploadProgress');
    const progressLabel = document.getElementById('videoProgressLabel');
    const errorEl = document.getElementById('videoError');

    extractBtn.disabled = true;
    const originalHTML = extractBtn.innerHTML;
    extractBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Extracting...';
    progressEl.classList.remove('d-none');
    progressLabel.textContent = 'Extracting frames (this may take a moment)...';
    errorEl.classList.add('d-none');

    try {
        const fps = parseFloat(document.getElementById('extractFps').value);
        const response = await fetch('/api/video/extract', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filename: videoImportState.filename,
                fps: fps
            })
        });

        const data = await response.json();
        progressEl.classList.add('d-none');

        if (!response.ok) {
            errorEl.textContent = data.message || data.error || 'Extraction failed';
            errorEl.classList.remove('d-none');
            extractBtn.innerHTML = originalHTML;
            extractBtn.disabled = false;
            return;
        }

        // Track largest dimensions from extracted frames
        if (data.frames.length > 0) {
            const fw = data.frames[0].width;
            const fh = data.frames[0].height;
            if (fw > (state.settings.originalWidth || 0) ||
                fh > (state.settings.originalHeight || 0)) {
                state.settings.originalWidth = Math.max(fw, state.settings.originalWidth || 0);
                state.settings.originalHeight = Math.max(fh, state.settings.originalHeight || 0);
                recalcDimensionsFromScale();
            }
        }

        // Add each extracted frame to state
        // Duration per frame = 1000ms / fps so total playback matches video length
        const frameDuration = Math.round(1000 / fps);
        for (const f of data.frames) {
            state.frames.push({
                id: `frame-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
                file: f.path,
                duration: frameDuration
            });
        }

        updateUI();

        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('videoImportModal'));
        if (modal) modal.hide();

        showToast(`Imported ${data.count} frames from video`, 'success');

    } catch (err) {
        progressEl.classList.add('d-none');
        errorEl.textContent = 'Network error during extraction';
        errorEl.classList.remove('d-none');
        extractBtn.innerHTML = originalHTML;
        extractBtn.disabled = false;
        console.error('Video extract error:', err);
    }
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}
