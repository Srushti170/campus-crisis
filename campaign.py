"""Persistent three-sector campaign progression for Campus Crisis."""
import json
from pathlib import Path

PROGRESS = Path(__file__).parent / 'logs' / 'campaign_progress.json'
MAX_SECTOR = 3


def load_progress():
    try:
        data = json.loads(PROGRESS.read_text()) if PROGRESS.exists() else {}
    except (json.JSONDecodeError, OSError):
        data = {}
    return {'completed': max(0, int(data.get('completed', 0))),
            'unlocked_sector': min(MAX_SECTOR, max(1, int(data.get('unlocked_sector', 1))))}


def record_completion(progress):
    """Unlock one sector after a successful rescue and persist the result."""
    completed = progress['completed'] + 1
    updated = {'completed': completed,
               'unlocked_sector': min(MAX_SECTOR, max(progress['unlocked_sector'], min(MAX_SECTOR, completed + 1)))}
    try:
        PROGRESS.parent.mkdir(exist_ok=True)
        PROGRESS.write_text(json.dumps(updated, indent=2))
    except OSError:
        pass
    return updated


def reset_progress():
    """Start a new campaign from Sector 1."""
    fresh = {'completed': 0, 'unlocked_sector': 1}
    try:
        PROGRESS.parent.mkdir(exist_ok=True)
        PROGRESS.write_text(json.dumps(fresh, indent=2))
    except OSError:
        pass
    return fresh
