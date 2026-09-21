import json
from pathlib import Path
import re

from src.utils.indoor_units_extractor import extract_family_models, extract_models
from src.utils.equipment_specifications import (
    extract_specification,
    extract_specification_from_text,
    get_page_text, normalize_pdf_text, get_page_text_positions,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INDEX_PATH = PROJECT_ROOT / "data" / "indexes" / "catalog_index.json"

with open(INDEX_PATH, encoding="utf-8") as f:
    catalog_index = json.load(f)

COOLING_NAMES = [
    "Rated Cooling Capacity",
    "Nominal Cooling Capacity",
    "Cooling capacity"
]

HEATING_NAMES = [
    "Rated Heating Capacity",
    "Nominal Heating Capacity",
    "Heating capacity",
]


def value_or_none(values, index):
    if index < len(values):
        return values[index]
    return None

def discover_models(
    page: int,
    family_key: str,
    page_end: int
) -> tuple[list[str], int | None]:
    """
    Universal model discovery from the specification page.

    Returns:
        (
            models,
            page_number_where_models_were_found
        )
    """

    # Families without "_" are discovered from "Indoor Unit" rows.
    if "_" not in family_key:

        def find_indoor_models(
                start_page: int,
                end_page: int
        ) -> tuple[list[str], int | None]:

            indoor_models = []
            found_page = None

            for page_number in range(start_page, end_page + 1):
                page_text = get_page_text(page_number)

                if not page_text:
                    continue

                for line in page_text.splitlines():
                    normalized = " ".join(line.split())

                    if not normalized.lower().startswith("indoor unit"):
                        continue

                    matches = re.findall(
                        r"\b[A-Z]{2,}[A-Z0-9-]*\d[A-Z0-9-]*\b",
                        normalized
                    )

                    if not matches:
                        continue

                    # Используем только первую найденную строку Indoor Unit.
                    # Не объединяем модели из последующих таблиц.
                    indoor_models = [model.upper() for model in matches]
                    found_page = page_number

                    return indoor_models, found_page

            return indoor_models, found_page

        # First: search inside the indexed section.
        indoor_models, found_page = find_indoor_models(
            page,
            page_end
        )

        # Fallback: only when nothing was found.
        if not indoor_models and page > 1:
            indoor_models, found_page = find_indoor_models(
                page - 1,
                page - 1
            )

        return indoor_models, found_page

    text = get_page_text(page)

    if not text:
        return [], None

    family_prefix, family_suffix = family_key.split("_", 1)

    suffixes = [family_suffix]

    # FXTQ_TAVJUA(D) means that both A and D models belong
    # to the same family.
    if family_suffix.endswith("(D)"):
        base_suffix = family_suffix[:-3]

        suffixes = [
            base_suffix,
            base_suffix[:-1] + "D"
        ]

    models = []

    for suffix in suffixes:
        pattern = (
            rf"\b{re.escape(family_prefix)}"
            rf"\d+"
            rf"{re.escape(suffix)}\b"
        )

        candidates = re.findall(
            pattern,
            text,
            re.IGNORECASE
        )

        for model in candidates:
            model = model.upper()

            if model not in models:
                models.append(model)

    if models:
        return models, page

    return [], None

def verify_discovered_models(page: int, family_prefix: str, models: list[str]) -> None:
    """
    Debug verification for universal model discovery.

    Prints the models discovered on the specification page and
    checks whether they actually occur in the page text.
    """

    if not models:
        print("NO MODELS FOUND")
        return

    text = get_page_text(page)

    if not text:
        print("NO PAGE TEXT")
        return

    for model in models:
        found = model.upper() in text.upper()

        print(
            f"{'OK  ' if found else 'MISS'} "
            f"{model}"
        )

    print("-" * 60)
    print(f"Discovered: {len(models)}")

equipment = []

for item in catalog_index:

    title = item["title"]

    if title == "Multi-Zone Systems":
        continue

    if title == "Single Zone Systems":
        continue

    if not title.startswith("Daikin "):
        continue

    if any(x in title for x in [
        "Multi-Zone",
        "VRV",
        "VRF",
    ]):
        continue

    print(f"Processing {title}...")
    spec_page = item["page"]

    models, discovered_page = discover_models(
        spec_page,
        title.split(" - ")[0],
        item["page_end"]
    )

    if discovered_page is not None:
        spec_page = discovered_page

    page_text = normalize_pdf_text(get_page_text(spec_page))



    verify_discovered_models(
        spec_page,
        title,
        models
    )

    # ============================================================
    # ALL OTHER FAMILIES
    # ============================================================

    print("FILTERED MODELS:", models)
   # models = sorted(models)

    if not models:
        print(f"⚠ No models found for {title}")
        continue

    # ============================================================
    # FAMILY / SYSTEM TYPE
    # ============================================================

    parts = title.split(" - ", 1)

    family = parts[0]
    description = parts[1] if len(parts) > 1 else ""

    if "OTERRA" in family and "Cooling" in family:
        family = family.replace("Cooling", "Cooling Only")

    cooling_only = "Cooling Only" in family

    print("COOLING: ", cooling_only)

    system_type = "single_zone"
    unit_type = "indoor"

    # ============================================================
    # EXTRACT SPECIFICATIONS
    # ============================================================

    cooling_capacity = extract_specification(
        spec_page,
        COOLING_NAMES,
        len(models),
        spec_type="capacity",
        models=models
    )

    if cooling_only:
        heating_capacity = []
    else:
        heating_capacity = extract_specification(
            spec_page,
            HEATING_NAMES,
            len(models),
            spec_type="capacity",
            models=models
        )

    height = extract_specification(
        spec_page,
        ["Height"],
        len(models),
        spec_type="dimension",
        models=models
    )

    width = extract_specification(
        spec_page,
        ["Width"],
        len(models),
        spec_type="dimension",
        models=models
    )

    depth = extract_specification(
        spec_page,
        ["Depth"],
        len(models),
        spec_type="dimension",
        models=models
    )

    sound = extract_specification(
        spec_page,
        ["Sound Pressure", "Sound Level"],
        len(models),
        spec_type="sound",
        models=models
    )

    liquid_pipe = extract_specification(
        spec_page,
        ["Liquid"],
        len(models),
        spec_type="pipe",
        models=models
    )

    gas_pipe = extract_specification(
        spec_page,
        ["Gas"],
        len(models),
        spec_type="pipe",
        models=models
    )
    cooling_outdoor_temperature = extract_specification(
        spec_page,
        ["Operating Range - Cooling"],
        len(models),
        spec_type="cooling_outdoor_temperature",
        models=models
    )

    if cooling_only:
        heating_outdoor_temperature = []
    else:
        heating_outdoor_temperature = extract_specification(
            spec_page,
            ["Operating Range - Heating"],
            len(models),
            spec_type="heating_outdoor_temperature",
            models=models
        )

    condensate_drain = extract_specification(
        spec_page,
        ["Condensate Pipe Connection", "Condensate Drain"],
        len(models),
        spec_type="pipe",
        models=models
    )
    # ============================================================
    # DEBUG OUTPUT
    # ============================================================

    print(f"\n{family}")
    print(f"Models found: {len(models)}")
    print(f"Cooling values found: {len(cooling_capacity)}")
    print(f"Heating values found: {len(heating_capacity)}")
    print(f"Cooling:      {cooling_capacity}")
    print(f"Heating:      {heating_capacity}")
    print(f"Height:       {height}")
    print(f"Width:        {width}")
    print(f"Depth:        {depth}")
    print(f"Sound:        {sound}")
    print(f"gas:          {gas_pipe}")
    print(f"liquid:       {liquid_pipe}")
    print(f"drain:        {condensate_drain}")
    print(f"out_cool:    {cooling_outdoor_temperature}")
    print(f"out_heat:    {heating_outdoor_temperature}")

    print(f"Models found: {len(models)}")
    for i, model in enumerate(models):

        equipment.append({
            "manufacturer": "Daikin",
            "system_type": system_type,
            "unit_type": unit_type,
            "family": family,
            "model": model,

            "indoor_model": (
                None
                if unit_type == "outdoor"
                else model
            ),

            "outdoor_model": (
                model
                if unit_type == "outdoor"
                else None
            ),

            "cooling_capacity": value_or_none(cooling_capacity, i),
            "heating_capacity": value_or_none(heating_capacity, i),

            "liquid_pipe": value_or_none(liquid_pipe, i),
            "gas_pipe": value_or_none(gas_pipe, i),
            "drain_pipe": value_or_none(condensate_drain, i),

            "cooling_outdoor_temperature": value_or_none(
                cooling_outdoor_temperature, i
            ),
            "heating_outdoor_temperature": value_or_none(
                heating_outdoor_temperature, i
),

            "height": value_or_none(height, i),
            "width": value_or_none(width, i),
            "depth": value_or_none(depth, i),

            "sound_level": value_or_none(sound, i),

            "pdf_page": spec_page,
        })

# Summary
print()
print(f"\nFound {len(equipment)} equipment models.")

# Save JSON
OUTPUT_PATH = PROJECT_ROOT / "data" / "indexes" /  "equipment_database.json"

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(equipment, f, indent=4, ensure_ascii=False)

print(f"\nEquipment database saved to:")
print(OUTPUT_PATH)

# Verification
print("\nVerification")
print("=" * 50)


for item in equipment:
    print(
        f"{item['system_type']} | "
        f"{item['family']} | "
        f"{item['model']}"
    )

