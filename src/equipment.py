import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATABASE = PROJECT_ROOT / "data" / "indexes" / "equipment_database.json"


with open(DATABASE, encoding="utf-8") as f:
    equipment = json.load(f)


def find_equipment(model: str):

    for item in equipment:

        if item["model"] == model:
            return item

    return None