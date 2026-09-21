from langchain_community.document_loaders import PyPDFLoader
from pathlib import Path

import re

from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parents[2]

PDF_PATH = PROJECT_ROOT / "data" / "catalog" / "GeneralCatalog.pdf"

print(PDF_PATH)
print(PDF_PATH.exists())

loader = PyPDFLoader(str(PDF_PATH))
documents = loader.load()

print(f"Pages: {len(documents)}")

def normalize_lines(text: str) -> list[str]:
    """
    Clean PDF text and merge broken words and page numbers.
    """

    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]

    lines = []

    i = 0

    while i < len(raw_lines):

        line = raw_lines[i]

        # ----------------------------
        # Merge broken words
        # F + XSQ...
        # D + aikin...
        # ----------------------------
        if (
            len(line) == 1
            and i + 1 < len(raw_lines)
            and raw_lines[i + 1][0].isalpha()
        ):
            line += raw_lines[i + 1]
            i += 1

        # ----------------------------
        # Merge page numbers
        # 2
        # 46
        # ->
        # 246
        # ----------------------------
        if (
            i + 2 < len(raw_lines)
            and raw_lines[i + 1].isdigit()
            and raw_lines[i + 2].isdigit()
            and len(raw_lines[i + 1]) == 1
            and len(raw_lines[i + 2]) == 2
        ):
            line += f" {raw_lines[i + 1]}{raw_lines[i + 2]}"
            i += 2

        lines.append(line)

        i += 1

    return lines

def extract_page(line: str):

    # 280, 300, 314, 330
    match = re.search(r"(\d{3})$", line)
    if match:
        return match.group(1)

    # 2 80 -> 280
    match = re.search(r"(\d)\s+(\d{2})$", line)
    if match:
        return match.group(1) + match.group(2)

    # 21, 22, 49, 52, 76, 79, 82
    match = re.search(r"(\d{2})$", line)
    if match:
        return match.group(1)

    return None

toc = documents[2:5]

print("=" * 60)
print("VRV Table of Contents")

lines = normalize_lines("\n".join(doc.page_content for doc in toc))

print("\n===== TOC LINES 0-40 =====")
for i, line in enumerate(lines[:40]):
    print(i, repr(line))
print("===== END TOC LINES =====\n")
print("===== END TOC LINES =====\n")

catalog_index = []

for line in lines:

    page = extract_page(line)

    if page is None:
        continue

    title = line.replace(page, "").strip()
    title = re.sub(r"\d\s+\d{2}$", "", title).strip()

    # missing rows
    if not title:
        continue

    # VRV + Single-Zone + Multi-Zone
    if not (
            title.startswith("FX")
            or title.startswith("VRV")
            or title.startswith("Daikin VRV")
            or "Indoor Units Overview" in title
            or (
                    21 <= int(page) < 79
                    and (
                            title.startswith("Daikin ")
                            or title in {
                                "Single Zone Systems",
                                "Multi-Zone Systems",
                                "Multi-Zone Indoor Units",
                                "Multi-Zone Combinations",
                            }
                    )
            )
    ):
        continue

    catalog_index.append({
        "type": None,
        "title": title,
        "page": int(page),
        "page_end": None,
    })

    if "Ventilation" in line:
        break
# ------------------------------------------------------------
# Determine end page for each catalog section
# ------------------------------------------------------------

for i, item in enumerate(catalog_index):
    if i < len(catalog_index) - 1:
        item["page_end"] = catalog_index[i + 1]["page"] - 1
    else:
        item["page_end"] = item["page"]

expanded_index = []

for item in catalog_index:
    base_title = item["title"]
    page_start = item["page"]
    page_end = item["page_end"]

    detected = []

    base_words = base_title.split()

    # ------------------------------------------------------------
    # Special case for TOC titles that combine multiple variants
    # Example:
    # Daikin POLARA Heat Pump or Cooling Systems
    #
    # The real PDF contains separate headings:
    # Daikin POLARA Wall-Mounted Cooling Only
    # Daikin POLARA Wall-Mounted Heat Pump
    # ------------------------------------------------------------
    combined_variants = (
        "Heat Pump or Cooling Systems" in base_title
    )

    if combined_variants:
        base_name = base_title.split(
            " Heat Pump or Cooling Systems"
        )[0].strip()

        for pdf_page in range(page_start, page_end + 1):
            page_text = documents[pdf_page - 1].page_content

            if (
                "Model" not in page_text
                or "Indoor Unit" not in page_text
                or "Outdoor Unit" not in page_text
            ):
                continue

            lines = [
                " ".join(line.split())
                for line in page_text.splitlines()
                if line.strip()
            ]

            for i in range(len(lines) - 1):
                combined = f"{lines[i]} {lines[i + 1]}"

                pattern = (
                    r"^"
                    + re.escape(base_name)
                    + r"\s+(.+?\b(?:Cooling Only|Heat Pump)\b)"
                    r"$"
                )

                match = re.search(
                    pattern,
                    combined,
                    re.IGNORECASE,
                )

                if not match:
                    continue

                full_title = f"{base_name} {match.group(1)}"

                if full_title not in [
                    x["title"] for x in detected
                ]:
                    detected.append({
                        "title": full_title,
                        "page": pdf_page-1
                    })

                break

        # Do not run the normal base-title detection below.
        # This special case has already identified the variants.
        if detected:
            for i, detected_item in enumerate(detected):
                if i < len(detected) - 1:
                    detected_end = (
                        detected[i + 1]["page"] - 1
                    )
                else:
                    detected_end = page_end-1

                expanded_index.append({
                    "type": None,
                    "title": detected_item["title"],
                    "page": detected_item["page"],
                    "page_end": detected_end,
                })

            continue

    for pdf_page in range(page_start, page_end + 1):
        page_text = documents[pdf_page - 1].page_content

        # Нас интересуют только страницы с таблицей
        # Indoor Unit / Outdoor Unit.
        if (
                "Model" not in page_text
                or "Indoor Unit" not in page_text
                or "Outdoor Unit" not in page_text
        ):
            continue

        lines = [
            " ".join(line.split())
            for line in page_text.splitlines()
            if line.strip()
        ]

        # Ищем название, разбитое на две строки:
        # Daikin OTERRA
        # Wall-Mounted Cooling
        for i in range(len(lines) - 1):
            combined = f"{lines[i]} {lines[i + 1]}"

            pattern = (
                r"^"
                + r"\s+".join(re.escape(word) for word in base_words)
                + r"\s+([A-Za-z-]+)"
            )

            match = re.search(
                pattern,
                combined,
                re.IGNORECASE,
            )

            if not match:
                continue

            extra_word = match.group(1)
            full_title = f"{base_title} {extra_word}"

            if full_title not in [x["title"] for x in detected]:
                detected.append({
                    "title": full_title,
                    "page": pdf_page,
                })

            break

    if detected:
        for i, detected_item in enumerate(detected):
            if i < len(detected) - 1:
                detected_end = detected[i + 1]["page"] - 1
            else:
                detected_end = page_end

            expanded_index.append({
                "type": None,
                "title": detected_item["title"],
                "page": detected_item["page"],
                "page_end": detected_end,
            })
    else:
        expanded_index.append(item)

catalog_index = expanded_index

print(f"\nFound sections: {len(catalog_index)}")
pprint(catalog_index)

import json

OUTPUT_PATH = PROJECT_ROOT / "data" / "indexes" / "catalog_index.json"

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(catalog_index, f, indent=4, ensure_ascii=False)

print(f"\nCatalog index saved to:")
print(OUTPUT_PATH)