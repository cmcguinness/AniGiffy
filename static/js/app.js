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
        alphaThreshold: 128
    },
    frames: [],
    currentPreview: null
};

// Calculate scaled dimensions
function getScaledDimensions() {
    if (!state.settings.originalWidth || !state.settings.originalHeight) {
        return { width: null, height: null };
    }
    return {
        width: Math.round(state.settings.originalWidth * state.settings.scale / 100),
        height: Math.round(state.settings.originalHeight * state.settings.scale / 100)
    };
}

// Initialize application
document.addEventListener('DOMContentLoaded', function() {
    initializeEventListeners();
    updateUI();
});

// Event Listeners
function initializeEventListeners() {
    // Image upload button triggers file input
    document.getElementById('uploadButton').addEventListener('click', function() {
        document.getElementById('imageUpload').click();
    });

    // Image upload handler
    document.getElementById('imageUpload').addEventListener('change', handleImageUpload);

    // Generate buttons
    document.getElementById('generatePreview').addEventListener('click', generatePreview);
    document.getElementById('generateFull').addEventListener('click', generateFullGIF);
    document.getElementById('stopPreview').addEventListener('click', stopPreview);

    // Settings inputs
    document.getElementById('scale').addEventListener('change', updateSettings);
    document.getElementById('loop').addEventListener('change', updateSettings);

    // Transparency settings
    document.getElementById('transparent').addEventListener('change', updateTransparencySettings);
    document.getElementById('backgroundColor').addEventListener('change', updateSettings);
    document.getElementById('alphaThreshold').addEventListener('input', updateAlphaThreshold);
}

// Image Upload
async function handleImageUpload(event) {
    const files = event.target.files;
    if (files.length === 0) return;

    showToast('Uploading images...', 'info');

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
                // Set original dimensions from first image
                if (state.settings.originalWidth === null || state.settings.originalHeight === null) {
                    state.settings.originalWidth = data.width;
                    state.settings.originalHeight = data.height;

                    // Auto-enable transparency if first image has it
                    if (data.hasTransparency) {
                        state.settings.transparent = true;
                        document.getElementById('transparent').checked = true;
                        updateTransparencyUI();
                    }
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

    if (state.frames.length > 0) {
        showToast('Images uploaded successfully', 'success');
    }
}

// Frame Management
function renderFrames() {
    const frameList = document.getElementById('frameList');

    if (state.frames.length === 0) {
        frameList.innerHTML = `
            <div class="text-center text-muted py-5">
                <i class="bi bi-card-image" style="font-size: 3rem;"></i>
                <p class="mt-2">No frames yet.<br>Upload images to get started.</p>
            </div>
        `;
        return;
    }

    frameList.innerHTML = '';

    state.frames.forEach((frame, index) => {
        const frameElement = createFrameElement(frame, index);
        frameList.appendChild(frameElement);
    });
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
async function generatePreview() {
    if (state.frames.length === 0) {
        showToast('Add frames before generating', 'warning');
        return;
    }

    const button = document.getElementById('generatePreview');
    const statusDiv = document.getElementById('generationStatus');

    button.disabled = true;
    button.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Generating...';
    statusDiv.innerHTML = '<small class="text-muted">Generating preview (up to 10 frames)...</small>';

    try {
        const dims = getScaledDimensions();
        const response = await fetch('/api/generate/preview', {
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
        button.disabled = false;
        button.innerHTML = '<i class="bi bi-lightning"></i> Preview';
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
    button.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Generating...';
    statusDiv.innerHTML = '<small class="text-muted">Generating full GIF...</small>';

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
        button.innerHTML = '<i class="bi bi-download"></i> Generate GIF';
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
function updateSettings() {
    state.settings.scale = parseInt(document.getElementById('scale').value);
    state.settings.loop = parseInt(document.getElementById('loop').value);
    state.settings.transparent = document.getElementById('transparent').checked;
    state.settings.backgroundColor = document.getElementById('backgroundColor').value;
    state.settings.alphaThreshold = parseInt(document.getElementById('alphaThreshold').value);
    updateOutputSizeDisplay();
}

function updateOutputSizeDisplay() {
    const dims = getScaledDimensions();
    const outputSizeEl = document.getElementById('outputSize');
    if (dims.width && dims.height) {
        outputSizeEl.textContent = `${dims.width} × ${dims.height}`;
    } else {
        outputSizeEl.textContent = '-';
    }
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
    document.getElementById('scale').value = state.settings.scale;
    document.getElementById('loop').value = state.settings.loop;
    updateOutputSizeDisplay();

    // Update transparency settings
    document.getElementById('transparent').checked = state.settings.transparent;
    document.getElementById('backgroundColor').value = state.settings.backgroundColor;
    document.getElementById('alphaThreshold').value = state.settings.alphaThreshold;
    document.getElementById('alphaThresholdValue').textContent = state.settings.alphaThreshold;
    updateTransparencyUI();

    // Render frames
    renderFrames();

    // Enable/disable generate buttons (need frames and dimensions)
    const hasFrames = state.frames.length > 0;
    const dims = getScaledDimensions();
    const hasDimensions = dims.width && dims.height;
    document.getElementById('generatePreview').disabled = !(hasFrames && hasDimensions);
    document.getElementById('generateFull').disabled = !(hasFrames && hasDimensions);
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

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}
