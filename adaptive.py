"""Trained, explainable adaptive-difficulty model for Campus Crisis."""
import json
import math
from pathlib import Path

HISTORY = Path(__file__).parent / 'logs' / 'mission_history.json'
MODEL = Path(__file__).parent / 'logs' / 'adaptive_model.json'
FEATURES = ('students_rescued', 'time_remaining', 'fuel', 'ammo', 'zombies_neutralized', 'medkits_used')
MINIMUM_SAMPLES = 15


def _history():
    try:
        return json.loads(HISTORY.read_text()) if HISTORY.exists() else []
    except (json.JSONDecodeError, OSError):
        return []


def _rows(history):
    outcomes = ('Mission complete', 'Rescue team lost', 'Student lost', 'Time expired')
    return [item for item in history if item.get('outcome') in outcomes]


def _vector(record):
    return [float(record.get(name, 0)) for name in FEATURES]


def _sigmoid(value):
    return 1 / (1 + math.exp(-max(-35, min(35, value))))


def train(history=None):
    """Train and save logistic regression without adding a third-party package."""
    rows = _rows(_history() if history is None else history)
    if len(rows) < MINIMUM_SAMPLES:
        return None
    values = [_vector(row) for row in rows]
    means = [sum(row[i] for row in values) / len(values) for i in range(len(FEATURES))]
    scales = [max(.001, (sum((row[i]-means[i])**2 for row in values) / len(values))**.5) for i in range(len(FEATURES))]
    inputs = [[(row[i]-means[i])/scales[i] for i in range(len(FEATURES))] for row in values]
    targets = [1.0 if row.get('outcome') == 'Mission complete' else 0.0 for row in rows]
    weights, bias = [0.0] * len(FEATURES), 0.0
    for _ in range(900):
        errors = [_sigmoid(bias + sum(weight*value for weight, value in zip(weights, row))) - target for row, target in zip(inputs, targets)]
        bias -= .11 * sum(errors) / len(inputs)
        for i in range(len(weights)):
            gradient = sum(error*row[i] for error, row in zip(errors, inputs)) / len(inputs)
            weights[i] -= .11 * (gradient + .012*weights[i])
    correct = sum((_sigmoid(bias + sum(weight*value for weight, value in zip(weights, row))) >= .5) == bool(target) for row, target in zip(inputs, targets))
    model = {'version': 1, 'samples': len(rows), 'features': FEATURES, 'means': means, 'scales': scales, 'weights': weights, 'bias': bias, 'training_accuracy': round(correct/len(rows), 3)}
    try:
        MODEL.write_text(json.dumps(model, indent=2))
    except OSError:
        pass
    return model


def _prediction(model, profile):
    normalized = [(value-mean)/scale for value, mean, scale in zip(_vector(profile), model['means'], model['scales'])]
    return _sigmoid(model['bias'] + sum(weight*value for weight, value in zip(model['weights'], normalized)))


def _profile(rows):
    recent = rows[-5:]
    return {name: sum(float(row.get(name, 0)) for row in recent)/len(recent) for name in FEATURES}


def _fallback(rows):
    if len(rows) < 2:
        return {'time': 0, 'medkits': 0, 'zombie_hp': 0, 'label': 'Baseline', 'reason': 'Collecting mission data.', 'ml_probability': None}
    wins = sum(row.get('outcome') == 'Mission complete' for row in rows[-5:])
    if wins <= 1:
        return {'time': 45, 'medkits': 1, 'zombie_hp': -18, 'label': 'Support mode', 'reason': 'Fallback support while ML collects data.', 'ml_probability': None}
    return {'time': 0, 'medkits': 0, 'zombie_hp': 0, 'label': 'Balanced mode', 'reason': 'Fallback balance while ML collects data.', 'ml_probability': None}


def recommend():
    """Use the trained model's predicted success chance for bounded changes."""
    rows = _rows(_history())
    model = train(rows)
    if not model:
        return _fallback(rows)
    probability = _prediction(model, _profile(rows))
    percent = round(probability*100)
    if probability < .48:
        return {'time': 45, 'medkits': 1, 'zombie_hp': -18, 'label': 'ML Support mode', 'reason': f'ML predicts {percent}% chance of success from recent play.', 'ml_probability': probability}
    if probability > .78:
        return {'time': -25, 'medkits': -1, 'zombie_hp': 18, 'label': 'ML Escalation mode', 'reason': f'ML predicts {percent}% chance of success from recent play.', 'ml_probability': probability}
    return {'time': 0, 'medkits': 0, 'zombie_hp': 0, 'label': 'ML Balanced mode', 'reason': f'ML predicts {percent}% chance of success from recent play.', 'ml_probability': probability}


def report():
    """Player-facing evidence that a learned model is active."""
    rows = _rows(_history())
    model = train(rows)
    return {'missions': len(rows), 'wins': sum(row.get('outcome') == 'Mission complete' for row in rows), 'rescued': (sum(row.get('students_rescued', 0) for row in rows)/len(rows) if rows else 0.0), 'trained': model is not None, 'accuracy': model['training_accuracy'] if model else None}
