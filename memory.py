# memory.py
import json
import os

FILE = "purchase_history.json"

def load_history():
    if not os.path.exists(FILE):
        return []
    with open(FILE, "r") as f:
        return json.load(f)

def save_history(data):
    with open(FILE, "w") as f:
        json.dump(data, f)

def clear_history():
    if os.path.exists(FILE):
        os.remove(FILE)
