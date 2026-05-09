import json
import os

FILE = "purchase_history.json"


def load_history():
    if not os.path.exists(FILE):
        return []

    with open(FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_history(data):
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def clear_history():
    if os.path.exists(FILE):
        os.remove(FILE)


def get_preferred_brand(item_name):
    history = load_history()

    item_name = item_name.lower().strip()

    for entry in history:
        if entry["item"].lower() == item_name:
            return entry["preferred_brand"]

    return None