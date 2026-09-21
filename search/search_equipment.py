import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "data" / "indexes" / "equipment_database.json"


def load_database():
    """Load equipment database."""

    with open(DATABASE_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def find_model(database, model_name: str):

    model_name = model_name.upper()

    for equipment in database:
        if equipment["model"].upper() == model_name:
            return equipment

    return None


def print_equipment(equipment):
    """Print equipment information."""

    print(f"Manufacturer: {equipment['manufacturer']}")
    print(f"Family: {equipment['family']}")
    print(f"Description: {equipment['description']}")
    print(f"Type: {equipment['type']}")
    print(f"Page: {equipment['page']}")


if __name__ == "__main__":

    database = load_database()

    print(f"Database loaded successfully.")
    print(f"Records: {len(database)}")

    equipment = find_model(database, "FTX18WVJU9")

    if equipment:
        print_equipment(equipment)