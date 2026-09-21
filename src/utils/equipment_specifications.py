from pathlib import Path
from pypdf import PdfReader
import fitz
import re

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PDF_PATH = PROJECT_ROOT / "data" / "catalog" / "GeneralCatalog.pdf"
pdf_document = fitz.open(str(PDF_PATH))
reader = PdfReader(str(PDF_PATH))

def get_page_text(page: int) -> str:
    return reader.pages[page].extract_text() or ""

def get_page_words(page: int):
    """
    Extract words with their real PDF bounding boxes.
    Returns:
        [
            {
                "text": "...",
                "x0": ...,
                "y0": ...,
                "x1": ...,
                "y1": ...,
            },
            ...
        ]
    """
    pdf_page = pdf_document[page]
    words = pdf_page.get_text("words")

    return [
        {
            "text": w[4],
            "x0": w[0],
            "y0": w[1],
            "x1": w[2],
            "y1": w[3],
        }
        for w in words
    ]

def get_vertical_lines(page: int, tolerance: float = 1.5):
    """
    Extract vertical table lines from PDF drawings.
    Returns:
        [
            {
                "x": x,
                "y0": y0,
                "y1": y1,
            },
            ...
        ]
    """

    pdf_page = pdf_document[page]
    lines = []

    for drawing in pdf_page.get_drawings():

        for item in drawing.get("items", []):

            # line
            if item[0] == "l":
                p1 = item[1]
                p2 = item[2]

                x0, y0 = p1
                x1, y1 = p2

                if abs(x1 - x0) <= tolerance:
                    lines.append({
                        "x": (x0 + x1) / 2,
                        "y0": min(y0, y1),
                        "y1": max(y0, y1),
                    })

            elif item[0] == "re":
                rect = item[1]

                lines.append({
                    "x": rect.x0,
                    "y0": rect.y0,
                    "y1": rect.y1,
                })

                lines.append({
                    "x": rect.x1,
                    "y0": rect.y0,
                    "y1": rect.y1,
                })

    return lines

def get_row_vertical_boundaries(
    page: int,
    y: float,
    tolerance: float = 2.0,
):
    """
    Return X positions of vertical table lines crossing a given Y.
    """

    lines = get_vertical_lines(page)

    xs = []

    for line in lines:
        if (line["y0"] - tolerance <= y <= line["y1"] + tolerance):
            xs.append(line["x"])

    # delete almost the same lines
    xs = sorted(xs)

    unique = []

    for x in xs:
        if not unique or abs(x - unique[-1]) > tolerance:
            unique.append(x)

    print(
        "ROW VERTICAL BOUNDARIES:",
        "PAGE:", page,
        "Y:", round(y, 2),
        "XS:", [round(x, 2) for x in unique],
    )

    return unique

def build_model_columns(
    page: int,
    models: list[str],
    target_y: float | None = None,
):
    """
    Build logical model columns from the table header.

    Supports:
    1. Tables with:
       Indoor Unit
       Outdoor Unit
       Cooling / Heating
       -> 2 logical columns per model

    2. Tables without Cooling / Heating subcolumns:
       Indoor Unit
       Outdoor Unit
       -> 1 logical column per model
    """

    words = get_page_words(page)

    # ---------------------------------------------------------
    # FIND ALL MODEL OCCURRENCES
    # ---------------------------------------------------------

    model_words = []

    for word in words:
        text = word["text"].strip()

        matched_model = None

        for model in models:
            if (
                    text == model
                    or text.startswith(model + "/")
            ):
                matched_model = model
                break

        if matched_model:
            model_words.append({
                "model": matched_model,
                "x0": word["x0"],
                "x1": word["x1"],
                "center": (word["x0"] + word["x1"]) / 2,
                "y0": word["y0"],
                "y1": word["y1"],
            })

    if not model_words:
        return []

    # ---------------------------------------------------------
    # FIND COOLING / HEATING WORDS
    # ---------------------------------------------------------

    mode_words = []

    for word in words:
        text = word["text"].strip().lower()

        if text in {"cooling", "heating"}:
            mode_words.append({
                "mode": text,
                "x0": word["x0"],
                "x1": word["x1"],
                "center": (word["x0"] + word["x1"]) / 2,
                "y0": word["y0"],
                "y1": word["y1"],
            })

    # ---------------------------------------------------------
    # TRY TO FIND A REAL COOLING / HEATING HEADER ROW
    # ---------------------------------------------------------

    header_modes = []

    for mode in mode_words:
        same_row = [
            item
            for item in mode_words
            if (
                abs(item["center"] - mode["center"]) > 1
                and abs(item["y0"] - mode["y0"]) < 3
            )
        ]

        if same_row:
            header_modes.append(mode)

    # =========================================================
    # CASE 1: COOLING / HEATING SUBCOLUMNS EXIST
    # =========================================================

    if header_modes:

        mode_rows = {}

        for mode in header_modes:
            key = round(mode["y0"] / 3) * 3
            mode_rows.setdefault(key, []).append(mode)

        if target_y is not None:
            candidate_mode_rows = []

            for row in mode_rows.values():
                mode_y = sum(
                    item["y0"]
                    for item in row
                ) / len(row)

                if mode_y < target_y:
                    candidate_mode_rows.append(
                        (target_y - mode_y, row)
                    )

            if candidate_mode_rows:
                candidate_mode_rows.sort(
                    key=lambda x: x[0]
                )
                best_mode_row = candidate_mode_rows[0][1]
            else:
                best_mode_row = max(
                    mode_rows.values(),
                    key=len
                )
        else:
            best_mode_row = max(
                mode_rows.values(),
                key=len
            )

        # Remove duplicate words at the same position
        best_mode_row.sort(key=lambda item: item["center"])

        unique_mode_row = []

        for mode in best_mode_row:
            if not unique_mode_row:
                unique_mode_row.append(mode)
                continue

            previous = unique_mode_row[-1]

            if (
                mode["mode"] == previous["mode"]
                and abs(mode["center"] - previous["center"]) < 1
            ):
                continue

            unique_mode_row.append(mode)

        best_mode_row = unique_mode_row

        if len(best_mode_row) >= 2:

            mode_y = sum(
                item["y0"]
                for item in best_mode_row
            ) / len(best_mode_row)

            # -------------------------------------------------
            # FIND MODEL ROWS JUST ABOVE MODE HEADER
            # -------------------------------------------------

            header_models = [
                item
                for item in model_words
                if 0 < mode_y - item["y0"] < 30
            ]

            if header_models:

                model_rows = {}

                for item in header_models:
                    key = round(item["y0"] / 4) * 4
                    model_rows.setdefault(key, []).append(item)

                rows = sorted(
                    model_rows.values(),
                    key=lambda row: min(
                        item["y0"] for item in row
                    )
                )

                # First row = Indoor Unit
                # Second row = Outdoor Unit
                indoor_row = sorted(
                    rows[0],
                    key=lambda item: item["center"]
                )

                outdoor_row = (
                    sorted(
                        rows[1],
                        key=lambda item: item["center"]
                    )
                    if len(rows) >= 2
                    else []
                )

                pair_count = len(indoor_row)

                if pair_count > 0:

                    logical_columns = []

                    for i, mode in enumerate(best_mode_row):

                        left = mode["x0"]
                        right = mode["x1"]

                        if i > 0:
                            left = (
                                best_mode_row[i - 1]["x1"]
                                + mode["x0"]
                            ) / 2

                        if i < len(best_mode_row) - 1:
                            right = (
                                mode["x1"]
                                + best_mode_row[i + 1]["x0"]
                            ) / 2

                        pair_index = i // 2

                        if pair_index >= pair_count:
                            continue

                        logical_columns.append({
                            "model": indoor_row[pair_index]["model"],
                            "indoor_model": indoor_row[pair_index]["model"],
                            "outdoor_model": (
                                outdoor_row[pair_index]["model"]
                                if pair_index < len(outdoor_row)
                                else None
                            ),
                            "mode": mode["mode"],
                            "x0": left,
                            "x1": right,
                        })

                    return logical_columns

    # =========================================================
    # CASE 2: NO COOLING / HEATING SUBCOLUMNS
    # =========================================================
    #
    # Example:
    #
    # Indoor Unit   FTK09  FTK12  FTK18  FTK24
    # Outdoor Unit  RK09   RK12   RK18   RK24
    #
    # One physical column per model.
    # =========================================================

    # Find words "Indoor Unit"
    indoor_unit_words = []

    for word in words:
        text = word["text"].strip().lower()

        if text == "indoor":
            # Check whether "Unit" follows on the same row
            nearby_unit = [
                other
                for other in words
                if (
                    other["text"].strip().lower() == "unit"
                    and abs(other["y0"] - word["y0"]) < 3
                    and other["x0"] >= word["x1"]
                )
            ]

            if nearby_unit:
                indoor_unit_words.append(word)

    # ---------------------------------------------------------
    # Find model occurrences belonging to Indoor Unit row
    # ---------------------------------------------------------

    indoor_model_rows = []

    for indoor_label in indoor_unit_words:

        candidates = [
            item
            for item in model_words
            if (
                abs(item["y0"] - indoor_label["y0"]) <= 25
                and item["x0"] > indoor_label["x1"]
            )
        ]

        if len(candidates) >= len(models):
            candidates.sort(key=lambda item: item["center"])
            indoor_model_rows.append(candidates)

    # ---------------------------------------------------------
    # Pick the model row belonging to the requested specification.
    # If target_y is known, use the vertically closest model row.
    # ---------------------------------------------------------

    if indoor_model_rows:

        if target_y is not None:
            indoor_row = min(
                indoor_model_rows,
                key=lambda row: abs(
                    (sum(item["y0"] for item in row) / len(row))
                    - target_y
                )
            )
        else:
            indoor_row = max(
                indoor_model_rows,
                key=len
            )

        # Keep only discovered models, in PDF order
        indoor_row = [
            item
            for item in indoor_row
            if item["model"] in models
        ]

        indoor_row.sort(
            key=lambda item: item["center"]
        )

        if len(indoor_row) == len(models):

            centers = [
                item["center"]
                for item in indoor_row
            ]

            columns = []

            for i, item in enumerate(indoor_row):

                if i == 0:
                    left = item["x0"]
                else:
                    left = (
                        centers[i - 1]
                        + item["center"]
                    ) / 2

                if i == len(indoor_row) - 1:
                    right = item["x1"]
                else:
                    right = (
                        item["center"]
                        + centers[i + 1]
                    ) / 2

                columns.append({
                    "model": item["model"],
                    "indoor_model": item["model"],
                    "outdoor_model": None,
                    "mode": None,
                    "x0": left,
                    "x1": right,
                })

            return columns

    # =========================================================
    # LAST FALLBACK
    # =========================================================
    #
    # If there is no recognizable "Indoor Unit" row,
    # use the first occurrence of each discovered model.
    # =========================================================

    model_hits = []

    for model in models:

        hits = [
            word
            for word in words
            if model in word["text"]
        ]

        if not hits:
            continue

        word = hits[0]

        model_hits.append({
            "model": model,
            "x0": word["x0"],
            "x1": word["x1"],
            "center": (
                word["x0"] + word["x1"]
            ) / 2,
        })

    model_hits.sort(
        key=lambda x: x["center"]
    )

    if not model_hits:
        return []

    centers = [
        item["center"]
        for item in model_hits
    ]

    columns = []

    for i, item in enumerate(model_hits):

        center = item["center"]

        if i == 0:
            left = item["x0"]
        else:
            left = (
                centers[i - 1]
                + center
            ) / 2

        if i == len(model_hits) - 1:
            right = item["x1"]
        else:
            right = (
                center
                + centers[i + 1]
            ) / 2

        columns.append({
            "model": item["model"],
            "indoor_model": item["model"],
            "outdoor_model": None,
            "mode": None,
            "x0": left,
            "x1": right,
        })

    return columns

def get_page_text_positions(page: int):
    """
    Extract words from PDF together with their real bounding boxes.
    Returns:
        [
            {
                "text": str,
                "x0": float,
                "y0": float,
                "x1": float,
                "y1": float,
            },
            ...
        ]
    """
    pdf_page = pdf_document[page]
    words = pdf_page.get_text("words")
    items = []

    for word in words:
        x0, y0, x1, y1, text = word[:5]

        text = text.strip()

        if not text:
            continue

        items.append({
            "text": text,
            "x0": x0,
            "y0": y0,
            "x1": x1,
            "y1": y1,
        })

    items.sort(
        key=lambda item: (
            item["y0"],
            item["x0"],
        )
    )
    return items

def reconstruct_pdf_fragments(items):
    """
    Reconstruct values that PDF splits into separate text fragments.

    Examples:
        281 / 265 / 230 -> 281/265/230
        33 / 30 / 28 -> 33/30/28
        77 (35) -> 77 (35)
    """

    if not items:
        return []

    items = sorted(
        items,
        key=lambda item: (
            item["y0"],
            item["x0"],
        ),
    )

    result = []
    i = 0

    while i < len(items):

        current = items[i]

        # --------------------------------------------------------
        # FRACTION / SLASH VALUES
        #
        # 281 / 265 / 230
        # --------------------------------------------------------

        if re.fullmatch(r"\d+(?:\.\d+)?", current["text"]):

            parts = [current["text"]]
            start_x = current["x0"]
            end_x = current["x1"]
            y0 = current["y0"]
            y1 = current["y1"]

            j = i + 1

            while j < len(items):

                slash = items[j]

                # Must be on approximately the same line
                if abs(
                    ((slash["y0"] + slash["y1"]) / 2)
                    - ((current["y0"] + current["y1"]) / 2)
                ) > 2:
                    break

                # Slash
                if slash["text"] != "/":
                    break

                # Need a number after slash
                if j + 1 >= len(items):
                    break

                number = items[j + 1]

                if not re.fullmatch(
                        r"\d+(?:\.\d+)?",
                        number["text"]
                ):
                    break

                # Make sure the fragment is physically close
                if number["x0"] - slash["x1"] > 10:
                    break

                # PDF may split a two-digit value into two separate
                # single-digit fragments, e.g. "3" + "0" -> "30".
                if (
                        re.fullmatch(r"\d", number["text"])
                        and j + 2 < len(items)
                ):
                    next_digit = items[j + 2]

                    same_line = abs(
                        (
                                (number["y0"] + number["y1"]) / 2
                                - (next_digit["y0"] + next_digit["y1"]) / 2
                        )
                    ) <= 2

                    close_x = (
                                      next_digit["x0"] - number["x1"]
                              ) <= 3

                    if (
                            same_line
                            and close_x
                            and re.fullmatch(r"\d", next_digit["text"])
                    ):
                        number = {
                            "text": number["text"] + next_digit["text"],
                            "x0": number["x0"],
                            "y0": min(number["y0"], next_digit["y0"]),
                            "x1": next_digit["x1"],
                            "y1": max(number["y1"], next_digit["y1"]),
                        }
                        j += 1

                parts.append(number["text"])

                end_x = number["x1"]
                y1 = max(y1, number["y1"])

                current = number
                j += 2

            if len(parts) >= 2:

                result.append({
                    "text": "/".join(parts),
                    "x0": start_x,
                    "y0": y0,
                    "x1": end_x,
                    "y1": y1,
                })

                i = j
                continue
        # --------------------------------------------------------
        # FRACTIONAL DIMENSIONS
        #
        # PDF may split:
        #   37 3/8
        #
        # into:
        #   37
        #   3/8
        # --------------------------------------------------------

        if re.fullmatch(r"\d+(?:\.\d+)?", current["text"]):
            if i + 1 < len(items):

                next_item = items[i + 1]

                same_line = abs(
                    (
                        (current["y0"] + current["y1"]) / 2
                        - (next_item["y0"] + next_item["y1"]) / 2
                    )
                ) <= 2

                close_x = (
                    next_item["x0"] - current["x1"]
                ) <= 10

                if (
                    same_line
                    and close_x
                    and re.fullmatch(
                        r"\d+/\d+",
                        next_item["text"]
                    )
                ):
                    result.append({
                        "text": (
                            current["text"]
                            + "-"
                            + next_item["text"]
                        ),
                        "x0": current["x0"],
                        "y0": min(
                            current["y0"],
                            next_item["y0"]
                        ),
                        "x1": next_item["x1"],
                        "y1": max(
                            current["y1"],
                            next_item["y1"]
                        ),
                    })

                    i += 2
                    continue
        # --------------------------------------------------------
        # WEIGHT / VALUE WITH PARENTHESES
        #
        # 77 (35)
        # --------------------------------------------------------

        if re.fullmatch(
            r"\d+(?:\.\d+)?",
            current["text"]
        ):

            if i + 1 < len(items):

                next_item = items[i + 1]

                combined = (
                    current["text"]
                    + " "
                    + next_item["text"]
                )

                if re.fullmatch(
                    r"\d+(?:\.\d+)?\s*\(\d+(?:\.\d+)?\)",
                    combined
                ):

                    result.append({
                        "text": combined,
                        "x0": current["x0"],
                        "y0": min(
                            current["y0"],
                            next_item["y0"]
                        ),
                        "x1": next_item["x1"],
                        "y1": max(
                            current["y1"],
                            next_item["y1"]
                        ),
                    })

                    i += 2
                    continue

        # --------------------------------------------------------
        # NORMAL ITEM
        # --------------------------------------------------------

        result.append(current)
        i += 1

    return result

def ranges_overlap(a0, a1, b0, b1, tolerance=2.0):
    """
    Return True when two horizontal ranges overlap.
    """
    return min(a1, b1) - max(a0, b0) >= -tolerance


def build_model_cells(model_positions):
    """
    Convert model center positions into horizontal model-column cells.

    Each model receives:
        x0 = left boundary
        x1 = right boundary
    """

    valid = [
        item
        for item in model_positions
        if item["x"] is not None
    ]

    if not valid:
        return []

    valid.sort(key=lambda item: item["x"])

    cells = []

    for i, item in enumerate(valid):

        center = item["x"]

        if i == 0:
            left = center - (valid[i + 1]["x"] - center) / 2
        else:
            left = (valid[i - 1]["x"] + center) / 2

        if i == len(valid) - 1:
            right = center + (center - valid[i - 1]["x"]) / 2
        else:
            right = (center + valid[i + 1]["x"]) / 2

        cells.append({
            "model": item["model"],
            "x0": left,
            "x1": right,
        })

    return cells


def find_specification_row(
    items,
    specification_names,
):
    """
    Find a specification label in a PDF row.

    Handles labels that PDF extracts as separate words.

    Examples:
        Air + Flow + Rate
        Sound + Pressure + Level
        Sound + Level
    """

    if not items or not specification_names:
        return None

    # ------------------------------------------------------------
    # NORMALIZE SPECIFICATION NAMES
    # ------------------------------------------------------------

    names = [
        " ".join(name.lower().split())
        for name in specification_names
    ]

    # Special PDF wording:
    # "Airflow" in our database corresponds to
    # "Air Flow Rate" in the PDF.
    expanded_names = []

    for name in names:
        expanded_names.append(name)

        if name == "airflow":
            expanded_names.append("air flow rate")
            expanded_names.append("air flow")

        if "capacity" in name:
            expanded_names.append("capacity rated")

    names = expanded_names

    # Longest first
    names.sort(
        key=lambda name: len(name.split()),
        reverse=True,
    )

    max_words = max(
        len(name.split())
        for name in names
    )

    # ------------------------------------------------------------
    # GROUP PDF WORDS INTO HORIZONTAL ROWS
    # ------------------------------------------------------------

    rows = []

    sorted_items = sorted(
        items,
        key=lambda item: (
            (item["y0"] + item["y1"]) / 2,
            item["x0"],
        ),)

    for item in sorted_items:

        item_y = (item["y0"] + item["y1"]) / 2

        row = None

        for existing_row in rows:
            if abs(existing_row["y"] - item_y) <= 1.5:
                row = existing_row
                break

        if row is None:
            row = {
                "y": item_y,
                "items": [],
            }
            rows.append(row)

        row["items"].append(item)

    # ------------------------------------------------------------
    # SEARCH ROWS
    # ------------------------------------------------------------

    for row in rows:

        row_items = sorted(
            row["items"],
            key=lambda item: item["x0"],
        )

        # --------------------------------------------------------
        # Try every consecutive group of words.
        #
        # Example:
        #
        # Air | Flow | Rate | CFM
        #
        # becomes:
        #
        # "air flow rate"
        # --------------------------------------------------------

        for start in range(len(row_items)):

            words = []

            for end in range(start, min(len(row_items),start + max_words,),):
                words.append(row_items[end]["text"])

                candidate = " ".join(words)
                candidate = " ".join(candidate.lower().split())

                if candidate in names:

                    return {
                        "y": row["y"],
                        "start_item": row_items[start],
                        "end_item": row_items[end],
                    }

    return None

def build_cells_from_row(page: int, y: float, model_columns: list[dict],):
    """
    Reconstruct table cells on a specific row
    using actual vertical PDF lines.
    Each physical cell is assigned to the model
    whose column contains the cell center.
    """
    boundaries = get_row_vertical_boundaries(page, y,)

    if len(boundaries) < 2:
        return []

    cells = []

    for i in range(len(boundaries) - 1):

        x0 = boundaries[i]
        x1 = boundaries[i + 1]

        cell_center = (x0 + x1) / 2

        covered_models = []

        for column in model_columns:

            if column["x0"] <= cell_center <= column["x1"]:
                covered_models.append(column["model"])

        if covered_models:
            cells.append({
                "x0": x0,
                "x1": x1,
                "models": covered_models,
            })

    return cells

def group_values_by_model_x(
    page: int,
    specification_names: list[str],
    models: list[str],
    spec_type: str = "number"
) -> list[str | None]:

    print("DEBUG spec_type =", spec_type)

    if not models:
        return []

    items = get_page_text_positions(page)

    if not items:
        return [None] * len(models)

    items = reconstruct_pdf_fragments(items)

    # ============================================================
    # 1. BUILD MODEL COLUMNS
    # ============================================================

    model_columns = build_model_columns(page, models)

    if not model_columns:
        return [None] * len(models)

    # ============================================================
    # 2. FIND SPECIFICATION LABEL
    # ============================================================

    # ------------------------------------------------------------
    # PIPE:
    # Do NOT search for "Pipe Connections".
    #
    # In the PDF "Pipe Connections" is a merged table header and
    # may not exist as a standalone PDF text item.
    #
    # Instead we find the actual physical row:
    #   Gas
    #   Liquid
    #   Condensate Pipe Connection
    #
    # and use its Y position.
    # ------------------------------------------------------------

    if spec_type == "pipe":

        target_name = specification_names[0].strip().lower()

        # --------------------------------------------------------
        # Find all possible pipe-row labels
        # --------------------------------------------------------

        pipe_rows = []

        for item in items:

            text = item["text"].strip().lower()
            item_y = (item["y0"] + item["y1"]) / 2

            # Gas / Liquid
            if text in ("gas", "liquid"):
                pipe_rows.append({
                    "name": text,
                    "item": item,
                    "y": item_y,
                })

            # Condensate rows may be split into separate PDF words:
            # "Condensate" + "Pipe" + "Connection"
            # or:
            # "Condensate" + "Drain"
            # They share the same Y position.
            elif text == "condensate":

                same_row = [
                    other
                    for other in items
                    if abs(((other["y0"] + other["y1"]) / 2) - item_y) < 1.0
                ]

                row_text = " ".join(
                    other["text"].strip().lower()
                    for other in same_row
                )

                if (
                        "condensate" in row_text
                        and "drain" in row_text
                ):
                    pipe_rows.append({
                        "name": "condensate drain",
                        "item": item,
                        "y": item_y,
                    })

                elif (
                        "condensate" in row_text
                        and "pipe" in row_text
                        and "connection" in row_text
                ):
                    pipe_rows.append({
                        "name": "condensate pipe connection",
                        "item": item,
                        "y": item_y,
                    })

            # Some PDFs use just "Drain" without the word
            # "Condensate". This is still the condensate drain row.
            elif text == "drain":
                pipe_rows.append({
                    "name": "condensate drain",
                    "item": item,
                    "y": item_y,
                })
        # --------------------------------------------------------
        # Normalize Condensate Drain
        # --------------------------------------------------------

        if "condensate" in target_name:
            target_names = {
                "condensate drain",
                "condensate pipe connection",
                "drain",
            }

            # If the PDF has only "Drain", use it directly.
            available_names = {
                row["name"]
                for row in pipe_rows
            }

            if "condensate pipe connection" not in available_names:
                target_names.discard("condensate pipe connection")

        else:
            target_names = {
                target_name,
            }


        # --------------------------------------------------------
        # Find candidates for requested row
        # --------------------------------------------------------

        target_candidates = [
            row
            for row in pipe_rows
            if row["name"] in target_names
        ]

        # --------------------------------------------------------
        # Gas / Liquid:
        #
        # The correct row should be close to another pipe row.
        # This prevents random "Gas" or "Liquid" text elsewhere
        # on the page from being selected.
        # --------------------------------------------------------

        if target_name in ("gas", "liquid"):

            scored_candidates = []

            for candidate in target_candidates:
                candidate_y = candidate["y"]

                nearby_pipe_rows = [
                    row
                    for row in pipe_rows
                    if row is not candidate
                       and abs(row["y"] - candidate_y) <= 30
                ]

                score = len(nearby_pipe_rows)
                scored_candidates.append((score, candidate))

            if scored_candidates:

                scored_candidates.sort(key=lambda x: (-x[0], x[1]["y"],))

                target_item = scored_candidates[0][1]

            else:
                target_item = None

        else:

            # ----------------------------------------------------
            # Condensate:
            # Just use the first matching physical row.
            # ----------------------------------------------------

            target_item = (
                target_candidates[0]
                if target_candidates
                else None
            )


        # --------------------------------------------------------
        # Nothing found
        # --------------------------------------------------------

        if target_item is None:
            print(
                f"PIPE: row '{target_name}' not found "
                f"for {specification_names}"
            )

            return [None] * len(models)

        # --------------------------------------------------------
        # Build specification match exactly as the normal logic
        # expects it.
        # --------------------------------------------------------

        target_pdf_item = target_item["item"]

        specification_match = {
            "y": target_item["y"],
            "start_item": target_pdf_item,
            "end_item": target_pdf_item,
        }

        spec_y = target_item["y"]

        print(
            "PIPE TARGET:",
            specification_names,
            "Y:",
            round(spec_y, 2),
            "TEXT:",
            repr(target_pdf_item["text"]),
        )

    else:

        # --------------------------------------------------------
        # OLD WORKING LOGIC
        # --------------------------------------------------------

        if spec_type == "pipe":
            target_name = specification_names[0].strip().lower()

        if spec_type == "sound":
            # ----------------------------------------------------
            # Sound may occur more than once on the same PDF page.
            #
            # IMPORTANT:
            # Select the model group first.
            # Do NOT average all occurrences of the models on the page.
            # ----------------------------------------------------

            specification_match = None

            # Find all Y positions where the requested models occur.
            model_occurrences = []

            for model in models:
                occurrences = []

                for item in items:
                    if item["text"].strip() == model:
                        occurrences.append(
                            (item["y0"] + item["y1"]) / 2
                        )

                model_occurrences.append(
                    {
                        "model": model,
                        "ys": occurrences,
                    }
                )

            # ----------------------------------------------------
            # Find a common model row/group.
            #
            # We need one Y position where all requested models
            # belong to the same table.
            # ----------------------------------------------------

            candidate_model_groups = []

            first_model_ys = (
                model_occurrences[0]["ys"]
                if model_occurrences
                else []
            )

            for base_y in first_model_ys:

                group_ys = [base_y]
                valid_group = True

                for occurrence in model_occurrences[1:]:

                    nearby = [
                        y
                        for y in occurrence["ys"]
                        if abs(y - base_y) <= 30
                    ]

                    if not nearby:
                        valid_group = False
                        break

                    nearest_y = min(
                        nearby,
                        key=lambda y: abs(y - base_y)
                    )

                    group_ys.append(nearest_y)

                if valid_group:
                    candidate_model_groups.append(
                        {
                            "y": sum(group_ys) / len(group_ys),
                            "ys": group_ys,
                        }
                    )

            # ----------------------------------------------------
            # If several groups exist, use the one with the
            # smallest vertical spread.
            # This keeps models from different tables apart.
            # ----------------------------------------------------

            if candidate_model_groups:

                candidate_model_groups.sort(
                    key=lambda group: (
                        max(group["ys"]) - min(group["ys"]),
                        group["y"],
                    )
                )

                target_model_y = candidate_model_groups[0]["y"]

                print(
                    "SOUND MODEL GROUP:",
                    models,
                    "Y:",
                    round(target_model_y, 2),
                    "MODEL_YS:",
                    [
                        round(y, 2)
                        for y in candidate_model_groups[0]["ys"]
                    ],
                )

                # ------------------------------------------------
                # Find all rows containing Sound / Pressure / Level
                # ------------------------------------------------

                candidate_matches = []

                processed_y = []

                for item in items:

                    row_y0 = (
                                     item["y0"] + item["y1"]
                             ) / 2

                    if any(
                            abs(row_y0 - y) <= 1.5
                            for y in processed_y
                    ):
                        continue

                    row_items = [
                        other
                        for other in items
                        if abs(
                            (
                                    other["y0"] + other["y1"]
                            ) / 2
                            - row_y0
                        ) <= 1.5
                    ]

                    processed_y.append(row_y0)

                    row_items.sort(
                        key=lambda item: item["x0"]
                    )

                    row_text = " ".join(
                        item["text"].strip()
                        for item in row_items
                    ).lower()

                    if (
                            "sound" in row_text
                            and "pressure" in row_text
                            and "level" in row_text
                    ):
                        candidate_matches.append(
                            {
                                "y": row_y0,
                                "start_item": row_items[0],
                                "end_item": row_items[-1],
                            }
                        )

                # ------------------------------------------------
                # Select Sound row belonging to THIS model group.
                # ------------------------------------------------

                if candidate_matches:
                    specification_match = min(
                        candidate_matches,
                        key=lambda match: abs(
                            match["y"] - target_model_y
                        )
                    )

                    print(
                        "SOUND SELECTED ROW:",
                        round(
                            specification_match["y"],
                            2
                        ),
                        "TARGET MODEL Y:",
                        round(
                            target_model_y,
                            2
                        ),
                    )

        else:
            if spec_type == "sound":
                search_names = specification_names + [
                    "Sound Pressure Level"
                ]
            else:
                search_names = specification_names
            specification_match = find_specification_row(
                items,
                search_names,
            )

        if specification_match is None and spec_type == "sound":
            sound_item = next(
                (
                    item for item in items
                    if item["text"].strip().lower() == "sound"
                ),
                None,
            )

            if sound_item is not None:
                sound_y = (
                                  sound_item["y0"] + sound_item["y1"]
                          ) / 2

                pressure_level_items = [
                    item
                    for item in items
                    if abs(
                        (
                                (item["y0"] + item["y1"]) / 2
                        ) - sound_y
                    ) <= 10
                       and item["text"].strip().lower()
                       in {"pressure", "level"}
                ]

                if pressure_level_items:
                    end_item = max(
                        pressure_level_items,
                        key=lambda item: item["x1"],
                    )

                    specification_match = {
                        "y": sound_y,
                        "start_item": sound_item,
                        "end_item": end_item,
                    }

        if spec_type == "sound":
            print("FVXS SOUND SPEC MATCH =", specification_match)

        if spec_type == "capacity":
            print("CAPACITY specification_match =", specification_match)

        if specification_match is None:
            if spec_type != "pipe":
                return [None] * len(models)

            spec_y = None
        else:
            spec_y = specification_match["y"]

    # ============================================================
    # REBUILD MODEL COLUMNS FOR THIS SPECIFICATION ROW
    # ============================================================
    # A page may contain several tables with the same model names.
    # Use the specification row Y to select the corresponding model
    # group before assigning values by X.
    # ============================================================
    if spec_y is not None:
        contextual_model_columns = build_model_columns(
            page,
            models,
            target_y=spec_y,
        )

        if contextual_model_columns:
            model_columns = contextual_model_columns

        print(
            "CONTEXTUAL MODEL COLUMNS:",
            model_columns,
            "SPEC_Y:",
            round(spec_y, 2),
        )

    # ============================================================
    # 3. FIND SPECIFICATION VALUE ROW
    # ============================================================
    #
    # Sound is special:
    # in some PDF tables the "Sound Level" label is on one
    # visual line, while the actual numeric values are on the
    # next line.
    #
    # Example:
    #
    # Sound Level (Reference)
    # Pressure             33 / 30 / 28 ...
    #
    # For sound, look slightly below the label for the row
    # containing numeric values.
    # ============================================================

    if spec_type == "sound":
        candidate_rows = {}

        sound_source_items = list(items)

        # PDF may split a two-digit sound value into two adjacent
        # single-digit fragments, e.g. "3" + "0" instead of "30".
        sound_tokens = []

        for item in items:
            item_y = (item["y0"] + item["y1"]) / 2

            if item_y < spec_y - 5:
                continue

            if item_y > spec_y + 12:
                continue

            if item["x0"] < specification_match["start_item"]["x0"]:
                continue

            if re.fullmatch(r"\d", item["text"].strip()):
                sound_tokens.append(item)

        sound_tokens.sort(key=lambda item: item["x0"])

        merged_tokens = []
        i = 0

        while i < len(sound_tokens):
            current = sound_tokens[i]

            if i + 1 < len(sound_tokens):
                next_item = sound_tokens[i + 1]

                same_row = abs(
                    ((current["y0"] + current["y1"]) / 2)
                    - ((next_item["y0"] + next_item["y1"]) / 2)
                ) <= 2

                close_x = (
                                  next_item["x0"] - current["x1"]
                          ) <= 3

                if same_row and close_x:
                    merged_tokens.append({
                        "text": (
                                current["text"]
                                + next_item["text"]
                        ),
                        "x0": current["x0"],
                        "y0": min(
                            current["y0"],
                            next_item["y0"]
                        ),
                        "x1": next_item["x1"],
                        "y1": max(
                            current["y1"],
                            next_item["y1"]
                        ),
                    })

                    i += 2
                    continue

            merged_tokens.append(current)
            i += 1

        sound_source_items.extend(merged_tokens)

        sound_merge_items = []

        for item in sound_source_items:
            text = item["text"].strip()

            if text == "/":
                slash_y = (item["y0"] + item["y1"]) / 2

                previous_items = [
                    prev
                    for prev in sound_source_items
                    if prev["x1"] < item["x0"]
                    and abs(
                        ((prev["y0"] + prev["y1"]) / 2) - slash_y
                    ) <= 8
                    and re.fullmatch(
                        r"\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?){2,}",
                        prev["text"].strip(),
                    )
                ]

                if previous_items:
                    previous = max(
                        previous_items,
                        key=lambda x: x["x1"],
                    )

                    next_items = [
                        nxt
                        for nxt in sound_source_items
                        if nxt["x0"] > item["x1"]
                        and abs(
                            ((nxt["y0"] + nxt["y1"]) / 2) - slash_y
                        ) <= 8
                        and re.fullmatch(
                            r"\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)+",
                            nxt["text"].strip(),
                        )
                    ]

                    if next_items:
                        next_item = min(
                            next_items,
                            key=lambda x: x["x0"],
                        )

                        sound_merge_items.append({
                            "text": (
                                previous["text"].strip()
                                + "/"
                                + next_item["text"].strip().lstrip("/")
                            ),
                            "x0": previous["x0"],
                            "x1": next_item["x1"],
                            "y0": min(
                                previous["y0"],
                                next_item["y0"],
                            ),
                            "y1": max(
                                previous["y1"],
                                next_item["y1"],
                            ),
                        })

        sound_source_items.extend(sound_merge_items)

        for item in sound_source_items:
            item_y = (item["y0"] + item["y1"]) / 2

            if item_y < spec_y - 5:
                continue

            if item_y > spec_y + 12:
                continue

            if item["x0"] < specification_match["start_item"]["x0"]:
                continue

            text = item["text"].strip()

            sound_match = re.fullmatch(
                r"\d+(?:\.\d+)?"
                r"(?:\s*/\s*\d+(?:\.\d+)?){0,4}",
                text
            )

            if not sound_match:
                continue

            parts = [
                float(x)
                for x in re.split(
                    r"\s*/\s*",
                    text
                )
            ]

            if all(value >= 19 for value in parts):
                row_key = round(item_y, 1)

                candidate_rows.setdefault(
                    row_key,
                    []
                ).append(item)

        best_row = None
        best_score = 0

        for row_y, row in candidate_rows.items():
            score = 0

            for item in row:
                text = item["text"].strip()

                if re.fullmatch(
                        r"\d+(?:\.\d+)?"
                        r"(?:\s*/\s*\d+(?:\.\d+)?){0,4}",
                        text
                ):
                    parts = [
                        float(x)
                        for x in re.split(
                            r"\s*/\s*",
                            text
                        )
                    ]

                    if all(value >= 20 for value in parts):
                        score += 4

            if score > best_score:
                best_score = score
                best_row = row_y

        if best_row is not None and best_score >= 4:
            spec_y = best_row

    # ============================================================
    # BUILD ROW ITEMS
    # ============================================================

    row_items = []

    for item in items:

        item_y = (item["y0"] + item["y1"]) / 2
        # ------------------------------------------------------------
        # SOUND:
        # The PDF may place "Sound Level (Reference)"
        # on one row and the actual values on the next row.
        # Therefore allow a larger vertical range.
        # ------------------------------------------------------------

        if spec_type == "sound":
            if item_y < spec_y - 4:
                continue
            if item_y > spec_y + 18:
                continue
        else:
            if spec_type == "airflow":
                if abs(item_y - spec_y) > 7:
                    continue
            else:
                if abs(item_y - spec_y) > 4:
                    continue

        if item["x0"] < specification_match["start_item"]["x0"]:
            continue

        row_items.append(item)

    row_items.sort(key=lambda item: item["x0"])

    if spec_type == "sound":
        # ---------------------------------------------------------
        # SOUND:
        # Keep every numeric sound value found on the selected row.
        #
        # Do NOT filter the row again by sound_rows here.
        # The PDF may contain several sound values in the same row,
        # e.g.:
        #
        # CDXS15 + CDXS18 -> 37/35/33/31
        # CDXS24           -> 38/36/34/32
        # ---------------------------------------------------------

        sound_value_items = []

        for item in row_items:
            text = item["text"].strip()

            if re.fullmatch(
                    r"\d+(?:\.\d+)?"
                    r"(?:\s*/\s*\d+(?:\.\d+)?){1,4}",
                    text
            ):
                parts = [
                    float(x)
                    for x in re.split(r"\s*/\s*", text)
                ]

                if all(value >= 19 for value in parts):
                    sound_value_items.append(item)

        if sound_value_items:
            row_items = sound_value_items

    # ============================================================
    # 4. EXTRACT VALUES FROM NORMAL ROW
    # ============================================================


    value_items = []

    for item in row_items:

        values = parse_values(
            item["text"],
            expected_count=len(models),
            spec_type=spec_type,
        )

        if not values:
            continue

        if spec_type == "sound":
            text = item["text"].strip()

            # Ignore compressor motor output values
            # such as 790 and 1100.
            if text in {"790", "1100", "1,100"}:
                continue

        # --------------------------------------------------------
        # One value in one PDF word
        # --------------------------------------------------------

        if len(values) == 1:

            value_items.append({
                "value": values[0],
                "x0": item["x0"],
                "x1": item["x1"],
                "y": (
                    item["y0"] + item["y1"]
                ) / 2,
            })

        # --------------------------------------------------------
        # Several values in one PDF word
        # --------------------------------------------------------
        else:
            total_width = (item["x1"] - item["x0"])
            step = (total_width / len(values))

            for i, value in enumerate(values):

                value_items.append({
                    "value": value,
                    "x0": (item["x0"] + i * step),
                    "x1": (item["x0"] + (i + 1) * step),
                    "y": (item["y0"] + item["y1"]) / 2,})

    # ============================================================
    # SPECIAL CAPACITY HANDLING
    #
    # Some Daikin tables use:
    #
    # Capacity Rated (Min. ~ Max.)
    #
    # Example:
    # 9,100 (4,600 ~ 11,000)
    # 10,000 (4,600 ~ 14,000)
    #
    # We need the Rated value, not the Max value.
    # ============================================================

    if spec_type == "capacity":

        page_text = normalize_pdf_text(
            get_page_text(page)
        )

        capacity_marker = re.search(
            r"Capacity\s+Rated",
            page_text,
            re.IGNORECASE,
        )

        moisture_marker = re.search(
            r"Moisture\s+Removal",
            page_text,
            re.IGNORECASE,
        )

        if capacity_marker and moisture_marker:

            capacity_block = page_text[
                capacity_marker.end():
                moisture_marker.start()
            ]

            rated_values = re.findall(
                r"(\d[\d,]*)\s*"
                r"\(\s*"
                r"\d[\d,]*\s*"
                r"(?:~|–|-)"
                r"\s*\d[\d,]*\s*\)",
                capacity_block,
            )

            if len(rated_values) >= len(models) * 2:

                name_text = " ".join(
                    specification_names
                ).lower()

                if "cooling" in name_text:
                    selected_values = rated_values[0::2]

                elif "heating" in name_text:
                    selected_values = rated_values[1::2]

                else:
                    selected_values = []

                if len(selected_values) >= len(models):

                    return selected_values[:len(models)]

    # ============================================================
    # 5. AIRFLOW SPECIAL FALLBACK
    # PDF may split:
    #   281 / 265 / 230
    # into separate PDF words.
    # First reconstruct airflow directly from the SAME physical
    # row. Only if that fails, try the SCFM row.
    # ============================================================

    if spec_type == "airflow" and not value_items:

        # --------------------------------------------------------
        # A. Reconstruct split airflow values on the normal row
        # --------------------------------------------------------
        airflow_tokens = []

        for item in row_items:
            text = item["text"].strip()
            if (
                    re.fullmatch(r"\d+(?:\.\d+)?", text)
                    or text == "/"
            ):
                airflow_tokens.append(item)

        airflow_tokens.sort(key=lambda item: item["x0"])
        i = 0

        while i < len(airflow_tokens):

            # ----------------------------------------------------
            # 3-part airflow:
            #
            # 281 / 265 / 230
            # ----------------------------------------------------

            if (
                    i + 4 < len(airflow_tokens)
                    and airflow_tokens[i]["text"] != "/"
                    and airflow_tokens[i + 1]["text"] == "/"
                    and airflow_tokens[i + 2]["text"] != "/"
                    and airflow_tokens[i + 3]["text"] == "/"
                    and airflow_tokens[i + 4]["text"] != "/"
            ):

                first = airflow_tokens[i]
                second = airflow_tokens[i + 2]
                third = airflow_tokens[i + 4]

                # Make sure this is one local group, not values
                # from different model columns.
                if (
                        first["x1"] <= second["x0"] + 25
                        and second["x1"] <= third["x0"] + 25
                ):
                    value_items.append({
                        "value": (first["text"] + "/" + second["text"] + "/" + third["text"]),
                        "x0": first["x0"],
                        "x1": third["x1"],
                        "y": (first["y0"] + first["y1"]) / 2,})

                    i += 5
                    continue

            # ----------------------------------------------------
            # 2-part airflow:
            # 280 / 226
            # ----------------------------------------------------

            if (
                    i + 2 < len(airflow_tokens)
                    and airflow_tokens[i]["text"] != "/"
                    and airflow_tokens[i + 1]["text"] == "/"
                    and airflow_tokens[i + 2]["text"] != "/"
            ):

                first = airflow_tokens[i]
                second = airflow_tokens[i + 2]

                if first["x1"] <= second["x0"] + 25:
                    value_items.append({
                        "value": (first["text"] + "/" + second["text"]),
                        "x0": first["x0"],
                        "x1": second["x1"],
                        "y": (first["y0"] + first["y1"]) / 2,})

                    i += 3
                    continue

            i += 1

        # --------------------------------------------------------
        # B. If still nothing found, look specifically at SCFM row
        # --------------------------------------------------------

        if not value_items:

            scfm_items = [
                item
                for item in items
                if item["text"].strip().upper() == "SCFM"]

            if scfm_items:

                scfm_item = scfm_items[0]
                scfm_y = (scfm_item["y0"] + scfm_item["y1"]) / 2
                scfm_row = []

                for item in items:

                    item_y = (item["y0"] + item["y1"]) / 2

                    if abs(item_y - scfm_y) > 2.0:
                        continue

                    if item["x0"] < specification_match["start_item"]["x0"]:
                        continue

                    scfm_row.append(item)

                scfm_row.sort(key=lambda item: item["x0"])

                # ------------------------------------------------
                # Try complete airflow strings first
                # ------------------------------------------------

                for item in scfm_row:

                    values = parse_values(
                        item["text"],
                        expected_count=len(models),
                        spec_type="airflow",)

                    if not values:
                        continue

                    if len(values) == 1:

                        value_items.append({
                            "value": values[0],
                            "x0": item["x0"],
                            "x1": item["x1"],
                            "y": (item["y0"] + item["y1"]) / 2,})

                    else:

                        total_width = (item["x1"] - item["x0"])
                        step = (total_width / len(values))

                        for j, value in enumerate(values):
                            value_items.append({
                                "value": value,
                                "x0": (item["x0"] + j * step),
                                "x1": (item["x0"] + (j + 1) * step),
                                "y": (item["y0"] + item["y1"]) / 2,})

                # ------------------------------------------------
                # Split numeric tokens on SCFM row
                # ------------------------------------------------

                if not value_items:

                    numeric_tokens = [
                        item
                        for item in scfm_row
                        if re.fullmatch(
                            r"\d+(?:\.\d+)?",
                            item["text"].strip())]

                    i = 0

                    while i + 2 < len(numeric_tokens):
                        first = numeric_tokens[i]
                        second = numeric_tokens[i + 1]
                        third = numeric_tokens[i + 2]

                        value_items.append({
                            "value": (first["text"] + "/" + second["text"] + "/" + third["text"]),
                            "x0": first["x0"],
                            "x1": third["x1"],
                            "y": (first["y0"] + first["y1"]) / 2,})

                        i += 3
    # ============================================================
    # 5B. PIPE SPECIAL FALLBACK
    #
    # Liquid / Gas values may be placed on TWO visual rows:
    #        ø3/8 - ø1/4   liquid
    #        ø5/8 -  ø1/2   gas
    # The upper value belongs to the last model column.
    # The lower value belongs to the first model group.
    # ============================================================

    if (
            spec_type == "pipe"
            and target_name in (
            "gas",
            "liquid",
            "condensate pipe connection",
            "condensate drain",)
    ):
        pipe_values = []

        # --------------------------------------------------------
        # CONDENSATE DRAIN / CONNECTION
        # Read the value directly from the page text.
        # Example:
        #   Drain Ø 3/4 (Ø 19.0)
        #   Drain Ø 13/16 (Ø 20.0)
        # --------------------------------------------------------
        if target_name in (
                "condensate pipe connection",
                "condensate drain",
        ):
            page_text = get_page_text(page)

            drain_match = re.search(
                r"\bDrain\b\s*(?:Ø\s*)?(\d+(?:-\d+)?/\d+|\d+)",
                page_text,
                re.IGNORECASE,
            )

            if drain_match:
                pipe_values.append({
                    "value": drain_match.group(1),
                    "x0": 0,
                    "x1": 0,
                    "y": spec_y,
                })

        # Search in a wider vertical area around the target row.
        for index, item in enumerate(items):
            item_y = (item["y0"] + item["y1"]) / 2

            if abs(item_y - spec_y) > 6.0:
                continue

            text = item["text"].strip()
            normalized = text.replace("∕", "/")

            # Normal pipe value:
            # 1/4, 3/8, 1/2, 5/8
            if re.fullmatch(
                    r"(?:ø\s*)?\d+(?:-\d+)?/\d+",
                    normalized,
                    re.IGNORECASE,
            ):
                value_match = re.search(
                    r"\d+(?:-\d+)?/\d+",
                    normalized,
                )

                if value_match:
                    pipe_values.append({
                        "value": value_match.group(0),
                        "x0": item["x0"],
                        "x1": item["x1"],
                        "y": item_y,
                    })

            # PDF may split "Ø 5/8" into two separate items:
            # "Ø" + "5/8"
            elif normalized.lower() in ("ø",):
                if index + 1 < len(items):
                    next_item = items[index + 1]

                    next_y = (
                                     next_item["y0"] + next_item["y1"]
                             ) / 2

                    next_text = next_item["text"].strip()
                    next_normalized = next_text.replace("∕", "/")

                    same_row = abs(next_y - item_y) <= 1.5
                    close_x = (
                                      next_item["x0"] - item["x1"]
                              ) <= 10

                    fraction_match = re.fullmatch(
                        r"\d+(?:-\d+)?/\d+",
                        next_normalized,
                    )

                    if (
                            same_row
                            and close_x
                            and fraction_match
                    ):
                        pipe_values.append({
                            "value": fraction_match.group(0),
                            "x0": item["x0"],
                            "x1": next_item["x1"],
                            "y": item_y,
                        })

            # Unicode single-character fractions
            elif text in ("¼", "⅜", "½", "⅝"):
                fraction_map = {
                    "¼": "1/4",
                    "⅜": "3/8",
                    "½": "1/2",
                    "⅝": "5/8",
                }

                pipe_values.append({
                    "value": fraction_map[text],
                    "x0": item["x0"],
                    "x1": item["x1"],
                    "y": item_y,
                })

        # Sort from left to right.
        pipe_values.sort(key=lambda item: (item["x0"] + item["x1"]) / 2)

        # Remove duplicate values at almost the same position.
        unique_values = []

        for item in pipe_values:
            center = (item["x0"] + item["x1"]) / 2

            duplicate = any(
                item["value"] == existing["value"]
                and abs(
                    center - (existing["x0"] + existing["x1"]) / 2) < 5
                for existing in unique_values
            )

            if not duplicate:
                unique_values.append(item)

        value_items = unique_values
    # ============================================================
    # 6. NOTHING FOUND
    # ============================================================

    if not value_items:
        return [None] * len(models)

    # ============================================================
    # 7. BUILD REAL CELLS FOR THIS SPECIFICATION ROW
    # ============================================================


    row_cells = build_cells_from_row(page, spec_y, model_columns,)

    if spec_type == "pipe" and target_name in (
            "gas",
            "liquid",
            "condensate pipe connection",
            "condensate drain",
    ):
        if value_items:
            sorted_values = sorted(value_items, key=lambda item: (item["x0"] + item["x1"]) / 2)

            sorted_columns = sorted(model_columns, key=lambda column: (column["x0"] + column["x1"]) / 2)
            result = {model: None for model in models}

            # ---------------------------------------------------------
            # PIPE RULE:
            # Values are ordered from left to right on the PDF.
            # If there are fewer physical pipe values than models,
            # the values represent groups of models.
            # Example:
            #   1 value  -> all models get this value
            #   2 values -> split models into 2 left/right groups
            #   3 values -> one value per model/group
            # ---------------------------------------------------------

            value_count = len(sorted_values)
            model_count = len(sorted_columns)

            if value_count == 1:
                for column in sorted_columns:
                    result[column["model"]] = sorted_values[0]["value"]

            elif value_count == model_count:
                for column, value_item in zip(sorted_columns, sorted_values):
                    result[column["model"]] = value_item["value"]

            else:
                # Split the model columns into consecutive groups
                # corresponding to the physical pipe values.
                #
                # Example:
                # 7 models / 2 values
                # -> first group gets value #1
                # -> second group gets value #2
                #
                for index, column in enumerate(sorted_columns):
                    group_index = min(
                        value_count - 1,
                        int(index * value_count / model_count)
                    )

                    result[column["model"]] = (
                        sorted_values[group_index]["value"]
                    )

            # A/D models:
            # D-models receive the value of the corresponding A-model.
            for model in models:
                if model.endswith("D"):
                    a_model = model[:-1] + "A"

                    if a_model in result:
                        result[model] = result[a_model]

            return [
                result.get(model)
                for model in models
            ]

    # ============================================================
    # 8. ASSIGN VALUES TO REAL CELLS
    # ============================================================

    result = {model: None for model in models}

    if spec_type == "sound":
        sound_result = {model: None for model in models}

        # ---------------------------------------------------------
        # SOUND:
        # Use the REAL physical table cells from the PDF.
        #
        # The model_columns may describe header/mode areas,
        # but the actual Sound row has its own vertical cell borders.
        # We therefore determine the model from the physical cell
        # in which the Sound value is located.
        # ---------------------------------------------------------

        boundaries = get_row_vertical_boundaries(
            page,
            spec_y,
        )

        # Use the complete physical table area.
        # The first/last physical cells may extend outside
        # the logical model header columns.

        sound_boundaries = [
            x for x in boundaries
            if x >= 200
               and x <= 520
        ]

        sound_boundaries = sorted(sound_boundaries)

        # ---------------------------------------------------------
        # Build physical cells.
        # Each physical cell belongs to one model.
        #
        # For example:
        #
        # 210 -> 259  = model 1
        # 259 -> 309  = model 2
        # 309 -> 358  = model 3
        # ...
        #
        # When there are two Sound values inside one model cell,
        # the FIRST value is retained.
        # ---------------------------------------------------------

        physical_cells = []

        for i in range(len(sound_boundaries) - 1):
            cell_x0 = sound_boundaries[i]
            cell_x1 = sound_boundaries[i + 1]

            # Determine which logical model owns this physical cell
            # by the actual horizontal overlap.
            owning_model = None
            best_overlap = 0.0

            for model in models:
                model_columns_for_model = [
                    column
                    for column in model_columns
                    if column["model"] == model
                ]

                if not model_columns_for_model:
                    continue

                model_left = min(
                    column["x0"]
                    for column in model_columns_for_model
                )

                model_right = max(
                    column["x1"]
                    for column in model_columns_for_model
                )

                overlap = (
                        min(cell_x1, model_right)
                        - max(cell_x0, model_left)
                )

                if overlap > best_overlap:
                    best_overlap = overlap
                    owning_model = model

            if owning_model is not None:
                physical_cells.append({
                    "x0": cell_x0,
                    "x1": cell_x1,
                    "model": owning_model,
                })

        # ---------------------------------------------------------
        # Assign Sound values to physical cells.
        # ---------------------------------------------------------

        print(
            "SOUND VALUE ITEMS:",
            [
                {
                    "value": item["value"],
                    "x0": round(item["x0"], 1),
                    "x1": round(item["x1"], 1),
                    "y": round(item["y"], 1),
                }
                for item in value_items
            ]
        )

        sorted_values = sorted(
            value_items,
            key=lambda item: (item["x0"] + item["x1"]) / 2
        )

        sorted_models = sorted(
            models,
            key=lambda model: min(
                column["x0"]
                for column in model_columns
                if column["model"] == model
            )
        )

        if len(sorted_values) == len(sorted_models) * 2:
            # PDF contains Cooling + Heating sound values
            # for each model:
            #
            # Model 1: Cooling, Heating
            # Model 2: Cooling, Heating
            # ...
            #
            # Keep the first value for each model (Cooling).

            cooling_values = sorted_values[::2]

            for model, value_item in zip(
                    sorted_models,
                    cooling_values
            ):
                sound_result[model] = value_item["value"]

        elif len(sorted_values) >= len(sorted_models):
            # One sound value per model.
            for model, value_item in zip(
                    sorted_models,
                    sorted_values[:len(sorted_models)]
            ):
                sound_result[model] = value_item["value"]

        return [
            sound_result.get(model)
            for model in models
        ]

    requested_mode = None

    if spec_type == "capacity":
        name_text = " ".join(
            specification_names
        ).lower()

        if "cooling" in name_text:
            requested_mode = "cooling"
        elif "heating" in name_text:
            requested_mode = "heating"

    if (
            spec_type == "capacity"
            and requested_mode == "heating"
            and not any(
        column.get("mode") == "heating"
        for column in model_columns
    )
    ):
        return [None] * len(models)

    for value_item in value_items:

        value_x0 = value_item["x0"]
        value_x1 = value_item["x1"]

        value_center = (
                               value_x0 + value_x1
                       ) / 2

        best_column = None
        best_distance = float("inf")

        for column in model_columns:

            if (
                    requested_mode is not None
                    and column.get("mode") is not None
                    and column.get("mode") != requested_mode
            ):
                continue

            # Значение должно находиться ВНУТРИ
            # горизонтальной области модели.
            if not (
                    column["x0"] <= value_center <= column["x1"]
            ):
                continue

            # Расстояние от центра значения
            # до центра модели.
            column_center = (
                                    column["x0"] + column["x1"]
                            ) / 2

            distance = abs(
                value_center - column_center
            )

            if distance < best_distance:
                best_distance = distance
                best_column = column

        if best_column is None:
            continue

        model = best_column["model"]

        if model in result:
            result[model] = value_item["value"]

    # ---------------------------------------------------------
    # A/D models:
    # D-models have exactly the same specifications as A-models.
    # Copy all values from the corresponding A-model automatically.
    # ---------------------------------------------------------
    for model in models:
        if model.endswith("D"):
            a_model = model[:-1] + "A"

            if a_model in result:
                result[model] = result[a_model]

    return [result.get(model) for model in models]

SPECIFICATION_HEADERS = [
    "SPECIFICATIONS",
    "Model Name",
    "Capacity Index",

    "Rated Cooling Capacity",
    "Nominal Cooling Capacity",
    "Cooling capacity",

    "Rated Heating Capacity",
    "Nominal Heating Capacity",
    "Heating capacity",

    "Airflow Rate",
    "Airflow",

    "Height",
    "Width",
    "Depth",

    "Sound Level",
    "Sound Pressure",
    "Sound Pressure Level",

    "Weight",

    "Power Supply",
    "Electrical",

    "Condensate Pump Lift",
    "Condensate Pipe Connection",
    "Condensate Drain",

    "Pipe Connections",
    "Liquid",
    "Gas",

    "Refrigerant Control",
    "Refrigerant",

    "Maximum Overcurrent Protective Device",
    "Minimum Circuit Amps",
    "Minimum Circuit Ampacity",

    "Protection Devices",
    "External Finish",
    "External Static Pressure",

    "Fan",
    "Motor Output",
    "Drive Type",
    "Static Pressure",
    "External Static Pressure",
    "Nominal Conditions",
    "Note",
]


def get_row_positions(
    items: list[dict],
    text_contains: str,
    tolerance: float = 1.5
) -> list[dict]:
    """Return PDF text fragments belonging to a specification row."""

    matches = []

    for item in items:
        if text_contains.lower() in item["text"].lower():
            matches.append(item)

    if not matches:
        return []

    # Обычно нужная строка одна.
    # Берём первую найденную.
    target_y = matches[0]["y"]

    return [
        item
        for item in items
        if abs(item["y"] - target_y) <= tolerance
    ]


def find_specification_lines(
    text: str,
    names: list[str]
) -> list[str]:
    """Return text blocks belonging to requested specifications."""

    text = re.sub(r"\s+", " ", text).strip()
    text_lower = text.lower()

    blocks = []

    headers = sorted(
        SPECIFICATION_HEADERS,
        key=len,
        reverse=True)

    for name in names:

        name_lower = name.lower()
        search_start = 0

        while True:

            start = text_lower.find(name_lower, search_start)

            if start == -1:
                break

            content_start = start + len(name_lower)

            end = len(text)

            # Find the nearest NEXT specification header
            for header in headers:

                header_lower = header.lower()

                # Never use the current specification
                if header_lower == name_lower:
                    continue

                pos = text_lower.find(header_lower, content_start)

                if pos != -1 and pos < end:
                    end = pos

            block = text[content_start:end].strip()

            if block:
                blocks.append(block)

            search_start = content_start

    return blocks

def normalize_pdf_text(text: str) -> str:
    """Fix common number breaks caused by PDF text extraction."""

    # 17 ,000 -> 17,000
    text = re.sub(
        r"(\d)\s+,(\d{3})",
        r"\1,\2",
        text)

    # 7,20 0 -> 7,200
    text = re.sub(
        r"(\d+,\d{1,2})\s+(\d)(?=\s|$|\()",
        r"\1\2",
        text)

    # 54,0009 (15.8) -> 54,000 (15.8)
    text = re.sub(
        r"(\d{2},\d{3})9(?=\s*\()",
        r"\1",
        text)

    return text

def parse_values(
    text: str,
    expected_count: int,
    spec_type: str = "number"
) -> list[str]:
    """Extract specification values from a text block."""
    # ------------------------------------------------------------
    # Capacity
    #
    # Example:
    # 14,200 (4.2)
    # 18,000 (5.3)
    # ------------------------------------------------------------

    if spec_type == "capacity":

        # Capacity with kW:
        # 14,200 (4.2)
        # 18,000 (5.3)

        matches = re.findall(
            r"\d[\d,]*\s*\(\d+(?:\.\d+)?\)",
            text
        )

        if matches:
            return matches[:expected_count]

        # Capacity without kW:
        # 7,500
        # 9,500
        # 12,000
        # 18,000
        # 24,000

        matches = re.findall(
            r"\b\d[\d,]{3,}\b",
            text)

        return [
            f"{int(value.replace(',', '')):,}"
            for value in matches[:expected_count]]


    elif spec_type in (
        "cooling_outdoor_temperature",
        "heating_outdoor_temperature",
    ):
        matches = re.findall(
            r"(-?\d+(?:\.\d+)?)\s*[–-]\s*(-?\d+(?:\.\d+)?)\s*°?\s*F",
            text,
            re.IGNORECASE,
        )

        result = []

        for lower_f, upper_f in matches:
            lower_c = round((float(lower_f) - 32) * 5 / 9, 1)
            upper_c = round((float(upper_f) - 32) * 5 / 9, 1)

            result.append(
                f"{lower_c}–{upper_c} °C"
            )

        return result[:expected_count]
    # ------------------------------------------------------------
    # Number
    #
    # Example:
    # 7500 9500 12000
    # ------------------------------------------------------------

    elif spec_type == "number":

        matches = re.findall(
            r"\b\d[\d,]{3,}\b",
            text
        )

        return matches[:expected_count]

    # ------------------------------------------------------------
    # Airflow
    #
    # Example:
    # 560/447/406
    # 635/565/512
    # ------------------------------------------------------------

    elif spec_type == "airflow":

        matches = re.findall(

            # 5-part airflow: 212/191/173/155/141

            r"\d+(?:\.\d+)?\s*/\s*"
            r"\d+(?:\.\d+)?\s*/\s*"
            r"\d+(?:\.\d+)?\s*/\s*"
            r"\d+(?:\.\d+)?\s*/\s*"
            r"\d+(?:\.\d+)?"
            r"|"
            # 3-part airflow: 281/265/230
            r"\d+(?:\.\d+)?\s*/\s*"
            r"\d+(?:\.\d+)?\s*/\s*"
            r"\d+(?:\.\d+)?"
            r"|"
            # 2-part airflow: 280/226
            r"\d+(?:\.\d+)?\s*/\s*"
            r"\d+(?:\.\d+)?"
            r"|"
            # single airflow: 635
            r"\b\d[\d,]*\b",
            text
        )

        return matches[:expected_count]

    # ------------------------------------------------------------
    # Weight
    # Example:
    # 77 (35)
    # 82 (37)
    # ------------------------------------------------------------

    elif spec_type == "weight":
        matches = re.findall(
            r"\d+(?:\.\d+)?\s*\(\d+(?:\.\d+)?\)",
            text
        )
        if matches:
            return matches[:expected_count]
        matches = re.findall(
            r"\b\d+(?:\.\d+)?\b",
            text
        )

        return matches[:expected_count]

    # ------------------------------------------------------------
    # Sound
    #
    # Example:
    # 37/34/31
    # 36/34/32
    # ------------------------------------------------------------

    elif spec_type == "sound":

        matches = re.findall(

            r"\b\d+(?:\.\d+)?"

            r"(?:\s*/\s*\d+(?:\.\d+)?){0,4}\b",

            text

        )

        return matches[:expected_count]

    # ------------------------------------------------------------
    # Pipe
    # ------------------------------------------------------------

    elif spec_type == "pipe":

        # Remove values in parentheses first.
        # Example:
        # ø1/4 (ø6.4) (Flare)
        # -> ø1/4

        clean_text = re.sub(
            r"\([^)]*\)",
            "",
            text
        )

        # Pipe sizes:
        # 1/4
        # 3/8
        # 1/2
        # 5/8
        # 3/4
        # 1-1/8
        # VP25
        #
        # IMPORTANT:
        # Fraction must be matched BEFORE simple numbers,
        # otherwise 1/2 becomes 1 and 2.

        matches = re.findall(
            r"\b\d+(?:-\d+)?/\d+\b"
            r"|"
            r"\bVP\d+\b",
            clean_text,
            re.IGNORECASE
        )
        return matches[:expected_count]

    # ------------------------------------------------------------
    # Refrigerant
    # Example:
    # R-410A
    # ------------------------------------------------------------

    elif spec_type == "refrigerant":

        matches = re.findall(
            r"R-\d+[A-Z]?",
            text,
            re.IGNORECASE
        )

        return matches[:expected_count]

    # ------------------------------------------------------------
    # Dimensions
    #
    # Example:
    # 39-3/8
    # 31-1/2
    # 9-11/16
    # ------------------------------------------------------------

    elif spec_type == "dimension":
        # PDF can split fractional dimensions:
        # 37 3/8 -> 37-3/8
        text = re.sub(
            r"(\d+)\s+(\d+/\d+)",
            r"\1-\2",
            text
        )


        # --------------------------------------------------------
        # Special case:
        # Dimensions - Unit Body (H x W x D)
        # Example:
        # 10-1/4 x 22-5/8 x 22-5/8
        # We extract the three dimensions in H/W/D order.
        # --------------------------------------------------------

        unit_body_match = re.search(
            r"Dimensions\s*-\s*Unit Body\s*\(H\s*x\s*W\s*x\s*D\)"
            r".*?"
            r"(\d+(?:-\d+/\d+)?(?:\.\d+)?)\s*x\s*"
            r"(\d+(?:-\d+/\d+)?(?:\.\d+)?)\s*x\s*"
            r"(\d+(?:-\d+/\d+)?(?:\.\d+)?)",
            text,
            re.IGNORECASE
        )

        if unit_body_match:

            h, w, d = unit_body_match.groups()

            if expected_count == 1:
                return [h]

            if expected_count == 2:
                return [h, w]

            return [h, w, d]

        # --------------------------------------------------------
        # Normal dimensions
        # --------------------------------------------------------

        matches = re.findall(

            r"\b\d+(?:-\d+/\d+)?(?:\.\d+)?\b",
            text)

        return matches[:expected_count]
    return []

def extract_specification_from_text(
    text: str,
    specification_names: list[str],
    expected_count: int,
    spec_type: str = "number"
) -> list[str]:

    blocks = find_specification_lines(
        text,
        specification_names
    )

    if not blocks:
        return []

    all_values = []

    for block in blocks:

        values = parse_values(
            block,
            expected_count - len(all_values),
            spec_type=spec_type
        )

        all_values.extend(values)

        if len(all_values) >= expected_count:
            break

    return all_values[:expected_count]

def extract_composite_dimensions_by_model(
    page: int,
    specification_names: list[str],
    models: list[str],
) -> list[str | None]:

    if not models:
        return []

    items = get_page_text_positions(page)

    if not items:
        return [None] * len(models)

    items = reconstruct_pdf_fragments(items)

    # ------------------------------------------------------------
    # Find the MAIN equipment Dimensions row.
    #
    # Important:
    # FXEQ page has another "Dimensions" row later for the
    # decoration panel. The main equipment row is written as:
    #
    #     Dimensions:
    #
    # while the decoration panel row is:
    #
    #     Dimensions (H x W x D)
    #
    # Therefore we specifically require "Dimensions:".
    # ------------------------------------------------------------

    specification_match = None

    # ------------------------------------------------------------
    # Find the H x W x D header row directly.
    #
    # The PDF may have:
    #   Dimensions
    #   H x W x D
    #
    # So "Dimensions" itself is not required.
    # ------------------------------------------------------------

    for item in items:
        text = item["text"].strip().lower()

        normalized = (
            text
            .replace("×", "x")
            .replace("(", "")
            .replace(")", "")
            .replace(",", "")
        )

        # Header may be extracted as one text fragment:
        # "Dimensions (H x W x D)"
        # or simply "H x W x D"
        if re.search(r"\bh\s*x\s*w\s*x\s*d\b", normalized):
            specification_match = {
                "y": (item["y0"] + item["y1"]) / 2,
                "start_item": item,
                "end_item": item,
            }
            break

        if normalized != "h":
            continue

        y = (
                (item["y0"] + item["y1"]) / 2
        )

        same_line = [
            x
            for x in items
            if abs(
                (
                        (x["y0"] + x["y1"]) / 2
                ) - y
            ) <= 1.5
        ]

        same_line.sort(
            key=lambda x: x["x0"]
        )

        texts = [
            x["text"]
            .strip()
            .lower()
            .replace("×", "x")
            .replace("(", "")
            .replace(")", "")
            .replace(",", "")
            for x in same_line
        ]

        for j in range(len(texts) - 4):
            if texts[j:j + 5] == [
                "h",
                "x",
                "w",
                "x",
                "d",
            ]:
                specification_match = {
                    "y": y,
                    "start_item": same_line[j],
                    "end_item": same_line[j + 4],
                }
                break

        if specification_match:
            break

    if specification_match is None:
        return [None] * len(models)
    print(
        "DIMENSION HEADER MATCH:",
        specification_match
    )
    spec_y = specification_match["y"]
    row_items = []

    for item in items:
        item_y = (
                         item["y0"] + item["y1"]
                 ) / 2

        if page == 70 and models and models[0].startswith("FDMQ"):
            if item_y < spec_y:
                continue

            if item_y - spec_y > 5:
                continue
        else:
            if abs(item_y - spec_y) > 3:
                continue

        if item["x0"] < specification_match["end_item"]["x1"]:
            continue

        row_items.append(item)

    row_items.sort(
        key=lambda item: item["x0"]
    )

    # ------------------------------------------------------------
    # Normalize PDF fraction characters
    # ------------------------------------------------------------

    fraction_map = {
        "½": "1/2",
        "⅓": "1/3",
        "⅔": "2/3",
        "¼": "1/4",
        "¾": "3/4",
        "⅕": "1/5",
        "⅖": "2/5",
        "⅗": "3/5",
        "⅘": "4/5",
        "⅙": "1/6",
        "⅚": "5/6",
        "⅛": "1/8",
        "⅜": "3/8",
        "⅝": "5/8",
        "⅞": "7/8",
        "∕": "/",
    }

    def normalize_dimension_text(text):
        for old, new in fraction_map.items():
            text = text.replace(old, new)

        text = (
            text
            .replace("×", "x")
            .replace("X", "x")
            .replace("(", "")
            .replace(")", "")
            .replace(",", "")
        )

        return text.strip()

    # ------------------------------------------------------------
    # Dimension token
    #
    # Supports:
    #
    # 7-7/8
    # 10-1/4
    # 22-5/8
    # 33-1-1/16
    # 45
    # 53.43
    # ------------------------------------------------------------

    dimension_pattern = re.compile(
        r"^\d+(?:-\d+)*(?:/\d+)?(?:\.\d+)?$"
    )

    # ------------------------------------------------------------
    # Find H x W x D groups
    # ------------------------------------------------------------
    print(
        "DIMENSION ROW ITEMS:",
        [
            (
                item["text"],
                round(item["x0"], 2),
                round(item["x1"], 2),
                round(item["y0"], 2),
                round(item["y1"], 2),
            )
            for item in row_items
        ],
    )


    dimension_pattern = re.compile(
        r"\(?\s*"
        r"(\d+(?:-\d+)*(?:/\d+)?(?:\.\d+)?)"
        r"\s*x\s*"
        r"(\d+(?:-\d+)*(?:/\d+)?(?:\.\d+)?)"
        r"\s*x\s*"
        r"(\d+(?:-\d+)*(?:/\d+)?(?:\.\d+)?)"
        r"\s*\)?",
        re.IGNORECASE
    )

    dimension_groups = []
    current = ""

    for item in row_items:
        text = normalize_dimension_text(item["text"])

        if text == "x":
            current += " x "
        else:
            current += text

        if current.count("x") == 2 and re.search(
                r"\d+\s*x\s*\d+\s*x\s*\d+",
                current
        ):
            match = re.search(
                r"(\d+(?:,\d+)?)\s*x\s*(\d+(?:,\d+)?)\s*x\s*(\d+(?:,\d+)?)",
                current
            )

            if match:
                dimension_groups.append({
                    "height": match.group(1),
                    "width": match.group(2),
                    "depth": match.group(3),
                    "x0": item["x0"],
                    "x1": item["x1"],
                })

            current = ""

    print("DIMENSION GROUPS:", dimension_groups)

    if not dimension_groups:
        return [None] * len(models)

    # ------------------------------------------------------------
    # Which dimension do we need?
    # ------------------------------------------------------------

    if "Height" in specification_names:
        dimension_key = "height"

    elif "Width" in specification_names:
        dimension_key = "width"

    elif "Depth" in specification_names:
        dimension_key = "depth"

    else:
        return [None] * len(models)

    # ------------------------------------------------------------
    # One merged dimension cell = same value for all models
    #
    # Example FXZQ:
    #
    # 10-1/4 x 22-5/8 x 22-5/8
    # ------------------------------------------------------------

    if len(dimension_groups) == 1:

        value = dimension_groups[0][dimension_key]

        return [value] * len(models)

    # ------------------------------------------------------------
    # Several merged cells.
    #
    # Example FXEQ:
    #
    # 07-15 -> 7-7/8 x 18-1/2 x 33-1-1/16
    # 18-24 -> 7-7/8 x 18-1/2 x 48-13/16
    #
    # Determine which model columns each group belongs to
    # using the horizontal center of the dimension cell.
    # ------------------------------------------------------------

    # ------------------------------------------------------------
    # FDMQ: page 70 contains two separate tables.
    #
    # Top table:
    #   FDMQ09, FDMQ12 -> 700 mm width
    #   FDMQ15         -> 1000 mm width
    #
    # Bottom table:
    #   FDMQ18, FDMQ24 -> 1000 mm width
    # ------------------------------------------------------------
    if (
            page == 70
            and models
            and models[0].startswith("FDMQ")
            and len(dimension_groups) == 2
    ):
        if len(models) == 3:
            return [
                dimension_groups[0][dimension_key],
                dimension_groups[0][dimension_key],
                dimension_groups[1][dimension_key],
            ]

        if len(models) == 2:
            return [
                dimension_groups[1][dimension_key],
                dimension_groups[1][dimension_key],
            ]

    model_columns = build_model_columns(
        page,
        models,
        target_y=spec_y,
    )

    if not model_columns:
        return [None] * len(models)

    model_centers = [
        (model_columns[i]["x0"] + model_columns[i + 1]["x1"]) / 2
        for i in range(0, len(model_columns), 2)]

    group_centers = [
        (group["x0"] + group["x1"]) / 2
        for group in dimension_groups
    ]

    # ------------------------------------------------------------
    # Find the best contiguous split of model columns between
    # dimension groups.
    #
    # Example FXEQ:
    #
    # group 1 -> models 0..3
    # group 2 -> models 4..5
    #
    # The groups are merged cells, so nearest-model matching
    # is not sufficient.
    # ------------------------------------------------------------

    memo = {}


    def best_partition(group_index, model_start):
        key = (group_index, model_start)

        if key in memo:
            return memo[key]

        if group_index == len(group_centers):
            if model_start == len(model_centers):
                return (0.0, [])
            return (float("inf"), [])

        groups_left = (len(group_centers) - group_index)
        models_left = (len(model_centers) - model_start)

        if models_left < groups_left:
            return (float("inf"), [])

        best_cost = float("inf")
        best_parts = None

        max_end = (len(model_centers) - (groups_left - 1))

        for model_end in range(model_start + 1, max_end + 1):

            span = model_centers[model_start:model_end]
            span_center = (sum(span) / len(span))
            cost = abs(span_center - group_centers[group_index])
            rest_cost, rest_parts = (best_partition(group_index + 1, model_end))
            total_cost = cost + rest_cost

            if total_cost < best_cost:
                best_cost = total_cost
                best_parts = [(model_start, model_end)] + rest_parts

        memo[key] = (best_cost, best_parts)

        return memo[key]

    _, partitions = best_partition(0, 0)

    # ------------------------------------------------------------
    # Build result according to model order.
    # ------------------------------------------------------------

    result = [None] * len(models)

    if partitions:

        for group_index, (
                start_model,
                end_model
        ) in enumerate(partitions):

            value = dimension_groups[
                group_index
            ][dimension_key]

            for model_index in range(
                    start_model,
                    end_model
            ):
                result[model_index] = value

    return result

def extract_specification(
    page: int,
    specification_names: list[str],
    expected_count: int,
    spec_type: str = "number",
    models: list[str] | None = None
) -> list[str | None]:
    """Extract a specification from a catalog page."""

    # ============================================================
    # POSITION-BASED EXTRACTION
    # ============================================================
    print(
        "EXTRACT SPEC:",
        specification_names,
        "MODELS:",
        models
    )
    # ============================================================
    # OUTDOOR OPERATING TEMPERATURE
    # ============================================================

    if spec_type in (
        "cooling_outdoor_temperature",
        "heating_outdoor_temperature",
    ):
        text = normalize_pdf_text(get_page_text(page))

        print(
            "TEMPERATURE PAGE TEXT:",
            repr(text)
        )

        def fahrenheit_to_celsius(value):
            return round((float(value) - 32) * 5 / 9, 1)

        if spec_type == "cooling_outdoor_temperature":
            match = re.search(
                r"Cooling.*?"
                r"(-?\d+(?:\.\d+)?)\s*°?\s*[–-]\s*"
                r"(-?\d+(?:\.\d+)?)\s*°?\s*F",
                text,
                re.IGNORECASE | re.DOTALL,
            )

        else:
            match = re.search(
                r"Operating Range\s*-\s*Heating.*?"
                r"(-?\d+(?:\.\d+)?)\s*°?\s*[–-]\s*"
                r"(-?\d+(?:\.\d+)?)\s*°?\s*F?",
                text,
                re.IGNORECASE | re.DOTALL,
            )

        if not match:
            return [None] * expected_count

        lower_f = float(match.group(1))
        upper_f = float(match.group(2))

        value = (
            f"{fahrenheit_to_celsius(lower_f)}–"
            f"{fahrenheit_to_celsius(upper_f)} °C"
        )

        return [value] * expected_count

    # ============================================================
    # COMPOSITE DIMENSIONS: H x W x D
    #
    # Some PDF tables do not have separate Height / Width / Depth
    # rows. Instead they use:
    #
    # Dimensions (H x W x D)
    #
    # Handle those tables generically.
    # ============================================================

    if models and spec_type == "dimension":

        print("ENTER COMPOSITE DIMENSIONS")

        dimension_values = extract_composite_dimensions_by_model(
            page=page,
            specification_names=specification_names,
            models=models,
        )

        if (
            dimension_values
            and any(value is not None for value in dimension_values)
        ):
            print(
                "COMPOSITE DIMENSION RESULT:",
                dimension_values
            )

            return dimension_values[:expected_count]



    if models :
        values = group_values_by_model_x(
            page=page,
            specification_names=specification_names,
            models=models,
            spec_type=spec_type
        )

        return values[:expected_count]

    # ============================================================
    # FALLBACK: OLD TEXT EXTRACTION
    # ============================================================

    text = get_page_text(page)

    # Fix PDF extraction problems
    text = normalize_pdf_text(text)

    # Find specification blocks
    blocks = find_specification_lines(
        text,
        specification_names
    )

    if not blocks:
        return []

    all_values = []

    for block in blocks:

        remaining = expected_count - len(all_values)

        if remaining <= 0:
            break

        values = parse_values(
            block,
            remaining,
            spec_type=spec_type
        )

        if values:
            all_values.extend(values)


    return all_values[:expected_count]