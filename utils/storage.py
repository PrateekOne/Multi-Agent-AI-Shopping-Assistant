# storage.py
import json

def load_file(path):
    if path.endswith(".json"):
        return json.load(open(path))
    if path.endswith(".csv"):
        import csv
        with open(path) as f:
            return list(csv.DictReader(f))
    return []
