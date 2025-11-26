import json
import uuid
from datetime import datetime
from pathlib import Path


class Frame:
    """Represents a single frame in an animation"""

    def __init__(self, file_path, duration=100, frame_id=None):
        self.id = frame_id or f"frame-{uuid.uuid4().hex[:8]}"
        self.file = file_path
        self.duration = duration

    def to_dict(self):
        return {
            'id': self.id,
            'file': self.file,
            'duration': self.duration
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            file_path=data['file'],
            duration=data.get('duration', 100),
            frame_id=data.get('id')
        )


class Project:
    """Represents an animation project"""

    def __init__(self, name, width=800, height=600, loop=0, default_duration=100,
                 transparent=False, background_color='#FFFFFF', alpha_threshold=128):
        self.name = name
        self.created = datetime.utcnow().isoformat()
        self.modified = datetime.utcnow().isoformat()
        self.settings = {
            'width': width,
            'height': height,
            'loop': loop,
            'defaultDuration': default_duration,
            'transparent': transparent,
            'backgroundColor': background_color,
            'alphaThreshold': alpha_threshold
        }
        self.frames = []

    def add_frame(self, file_path, duration=None):
        """Add a frame to the project"""
        if duration is None:
            duration = self.settings['defaultDuration']

        frame = Frame(file_path, duration)
        self.frames.append(frame)
        self.update_modified()
        return frame

    def remove_frame(self, frame_id):
        """Remove a frame by ID"""
        self.frames = [f for f in self.frames if f.id != frame_id]
        self.update_modified()

    def reorder_frames(self, frame_ids):
        """Reorder frames based on a list of frame IDs"""
        # Create a mapping of frame ID to frame object
        frame_map = {f.id: f for f in self.frames}

        # Reorder based on provided IDs
        new_order = []
        for frame_id in frame_ids:
            if frame_id in frame_map:
                new_order.append(frame_map[frame_id])

        self.frames = new_order
        self.update_modified()

    def update_frame(self, frame_id, **kwargs):
        """Update frame properties"""
        for frame in self.frames:
            if frame.id == frame_id:
                if 'duration' in kwargs:
                    frame.duration = kwargs['duration']
                if 'file' in kwargs:
                    frame.file = kwargs['file']
                self.update_modified()
                return frame
        return None

    def update_settings(self, **kwargs):
        """Update project settings"""
        if 'width' in kwargs:
            self.settings['width'] = int(kwargs['width'])
        if 'height' in kwargs:
            self.settings['height'] = int(kwargs['height'])
        if 'loop' in kwargs:
            self.settings['loop'] = int(kwargs['loop'])
        if 'defaultDuration' in kwargs:
            self.settings['defaultDuration'] = int(kwargs['defaultDuration'])
        if 'transparent' in kwargs:
            self.settings['transparent'] = bool(kwargs['transparent'])
        if 'backgroundColor' in kwargs:
            self.settings['backgroundColor'] = str(kwargs['backgroundColor'])
        if 'alphaThreshold' in kwargs:
            self.settings['alphaThreshold'] = int(kwargs['alphaThreshold'])

        self.update_modified()

    def update_modified(self):
        """Update the modified timestamp"""
        self.modified = datetime.utcnow().isoformat()

    def to_dict(self):
        """Convert project to dictionary"""
        return {
            'name': self.name,
            'created': self.created,
            'modified': self.modified,
            'settings': self.settings,
            'frames': [f.to_dict() for f in self.frames]
        }

    def to_json(self):
        """Convert project to JSON string"""
        return json.dumps(self.to_dict(), indent=2)

    def save(self, file_path):
        """Save project to a JSON file"""
        with open(file_path, 'w') as f:
            f.write(self.to_json())

    @classmethod
    def from_dict(cls, data):
        """Create a project from a dictionary"""
        settings = data.get('settings', {})
        project = cls(
            name=data['name'],
            width=settings.get('width', 800),
            height=settings.get('height', 600),
            loop=settings.get('loop', 0),
            default_duration=settings.get('defaultDuration', 100),
            transparent=settings.get('transparent', False),
            background_color=settings.get('backgroundColor', '#FFFFFF'),
            alpha_threshold=settings.get('alphaThreshold', 128)
        )

        project.created = data.get('created', datetime.utcnow().isoformat())
        project.modified = data.get('modified', datetime.utcnow().isoformat())

        # Load frames
        for frame_data in data.get('frames', []):
            frame = Frame.from_dict(frame_data)
            project.frames.append(frame)

        return project

    @classmethod
    def from_json(cls, json_str):
        """Create a project from a JSON string"""
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def load(cls, file_path):
        """Load a project from a JSON file"""
        with open(file_path, 'r') as f:
            return cls.from_json(f.read())

    def validate(self, config):
        """Validate project against configuration limits"""
        errors = []

        # Check dimensions
        if self.settings['width'] > config.QUOTAS['max_dimension']:
            errors.append(f"Width exceeds maximum: {config.QUOTAS['max_dimension']}")

        if self.settings['height'] > config.QUOTAS['max_dimension']:
            errors.append(f"Height exceeds maximum: {config.QUOTAS['max_dimension']}")

        # Check frame count
        if len(self.frames) > config.QUOTAS['max_frames']:
            errors.append(f"Frame count exceeds maximum: {config.QUOTAS['max_frames']}")

        # Check frame durations
        for frame in self.frames:
            if frame.duration < 1:
                errors.append(f"Frame {frame.id} has invalid duration: {frame.duration}")

        return len(errors) == 0, errors
