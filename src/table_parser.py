from collections import defaultdict

def _normalize_text(value):
    if value is None:
        return ""

    return " ".join(str(value).replace("\n", " ").split()).strip()


def _get_row_ranges(table):
    """
    Get unique Y-ranges of table rows from PyMuPDF geometry.
    """

    ranges = []

    for cell in table.cells:

        if cell is None:
            continue

        x0, y0, x1, y1 = cell
        exists = False

        for existing_y0, existing_y1 in ranges:

            if (
                abs(y0 - existing_y0) < 1
                and abs(y1 - existing_y1) < 1
            ):
                exists = True
                break

        if not exists:
            ranges.append((y0, y1))

    ranges.sort()

    return ranges

def _get_words_in_row(page, y0, y1):
    """
    Return words whose vertical center belongs to the row.
    """

    words = []

    for word in page.get_text("words"):

        x0, wy0, x1, wy1, text, *_ = word

        center_y = (wy0 + wy1) / 2

        if (
            center_y >= y0
            and center_y <= y1
        ):

            words.append(
                {
                    "text": text,
                    "x0": x0,
                    "x1": x1,
                    "y0": wy0,
                    "y1": wy1,
                }
            )

    words.sort(key=lambda word: (word["y0"], word["x0"],))

    return words

def _find_model_row(data):
    """
    Find the row containing 'Model'.
    """

    for index, row in enumerate(data):

        for value in row:

            if (
                value is not None
                and _normalize_text(value).lower()
                == "model"
            ):

                return index

    return None

def _extract_model_names(data, model_row_index):
    """
    Extract model names from the table's model row.
    """

    models = []

    for value in data[model_row_index]:

        value = _normalize_text(value)

        if not value:
            continue

        if value.lower() in {
            "model",
            "indoor unit",
            "outdoor unit",
        }:
            continue

        # Ignore obvious descriptive labels.
        if len(value) < 3:
            continue

        models.append(value)

    return models

def _find_model_positions(
    page,
    model_names,
    model_y0,
    model_y1,
):
    """
    Find the actual X position of each model name
    inside the Model row.

    Restricting the search to the Model row is important:
    the same model may occur many times elsewhere on the page.
    """

    positions = []
    words = page.get_text("words")

    for model in model_names:

        model_words = model.split()

        # Most Daikin model numbers are one PDF word.
        # We nevertheless support multiple words.
        candidates = []

        for word in words:

            x0, y0, x1, y1, text, *_ = word

            center_y = (y0 + y1) / 2

            if (
                center_y < model_y0
                or center_y > model_y1
            ):
                continue

            if text.strip() == model:
                candidates.append(
                    {
                        "model": model,
                        "x0": x0,
                        "x1": x1,
                        "center": (x0 + x1) / 2,
                    })

        if candidates:

            positions.append(candidates[0])

    positions.sort(key=lambda item: item["center"])

    return positions

def _build_model_columns(
    model_positions,
    table,
    model_y0,
    model_y1,
):
    """
    Build horizontal model regions.

    The model header cells define the broad column groups.
    """

    header_cells = []

    for cell in table.cells:

        if cell is None:
            continue

        x0, y0, x1, y1 = cell

        if (
            abs(y0 - model_y0) < 1
            and abs(y1 - model_y1) < 1
        ):

            header_cells.append((x0, x1))

    header_cells.sort()

    columns = []

    for position in model_positions:

        model = position["model"]
        center = position["center"]

        # Find the header cell containing the model name.
        matching_cell = None

        for x0, x1 in header_cells:

            if x0 <= center <= x1:

                matching_cell = (x0, x1,)
                break

        if matching_cell is None:
            continue

        columns.append(
            {
                "model": model,
                "x0": matching_cell[0],
                "x1": matching_cell[1],
                "center": center,
            })

    return columns

def _group_words(words):
    """
    Combine consecutive words belonging to the same value.

    Example:

        65-5/8
        (20)

    becomes:

        65-5/8 (20)
    """

    if not words:
        return []

    groups = []
    current = None

    for word in words:

        if current is None:

            current = {
                "text": word["text"],
                "x0": word["x0"],
                "x1": word["x1"],
                "y0": word["y0"],
                "y1": word["y1"],
            }

            continue

        gap = word["x0"] - current["x1"]

        # Normal words belonging to one value.
        if gap < 15:

            current["text"] += " " + word["text"]
            current["x1"] = word["x1"]
            current["y1"] = max(current["y1"], word["y1"],)

        else:

            groups.append(current)

            current = {
                "text": word["text"],
                "x0": word["x0"],
                "x1": word["x1"],
                "y0": word["y0"],
                "y1": word["y1"],
            }

    if current is not None:
        groups.append(current)

    return groups

def _assign_value_to_models(
    value,
    model_columns,
):
    """
    Assign a value to the model group based on its
    horizontal position.

    Model columns are divided into groups using the
    midpoint between neighbouring model positions.

    If a value belongs to a merged pair of model columns,
    the value is assigned to both models in that group.
    """

    if not model_columns:
        return []

    value_center = (
        value["x0"] + value["x1"]
    ) / 2

    # --------------------------------------------------
    # MODEL CENTERS
    # --------------------------------------------------

    centers = [
        column["center"]
        for column in model_columns
    ]

    # --------------------------------------------------
    # BUILD GROUP BOUNDARIES
    # --------------------------------------------------

    boundaries = []

    for index in range(
        len(centers) - 1
    ):

        midpoint = (centers[index] + centers[index + 1]) / 2

        boundaries.append(midpoint)

    # --------------------------------------------------
    # FIND THE MODEL GROUP
    # --------------------------------------------------

    group_index = 0

    for boundary in boundaries:

        if value_center > boundary:
            group_index += 1
        else:
            break

    # --------------------------------------------------
    # MERGED MODEL GROUPS
    # --------------------------------------------------

    # The catalog uses pairs of models for some
    # merged cells. The value is located approximately
    # between the two model columns.
    #
    # Example:
    #
    # FTXB09 + FTXB12 -> 20 m
    # FTXB18 + FTXB24 -> 30 m
    #
    # Detect which half of the model groups the value
    # belongs to.

    if len(model_columns) == 4:

        if value_center < (centers[1] + centers[2]) / 2:

            return [model_columns[0]["model"], model_columns[1]["model"],]

        return [model_columns[2]["model"], model_columns[3]["model"],]

    # --------------------------------------------------
    # GENERAL CASE
    # --------------------------------------------------

    return [model_columns[group_index]["model"]]

def parse_table(page, table,):
    """
    Parse a PyMuPDF table while preserving
    the relationship between values and model columns.

    Returns:

    {
        "models": [...],
        "rows": [
            {
                "parameter": "...",
                "values": {
                    "MODEL": "VALUE"
                }
            }
        ]
    }
    """

    data = table.extract()

    if not data:
        return None

    model_row_index = _find_model_row(data)

    if model_row_index is None:
        return None

    row_ranges = _get_row_ranges(table)

    if (model_row_index >= len(row_ranges)):
        return None

    model_y0, model_y1 = row_ranges[model_row_index]

    model_names = _extract_model_names(data, model_row_index,)

    if not model_names:
        return None

    model_positions = _find_model_positions(page, model_names, model_y0, model_y1,)

    if not model_positions:
        return None

    model_columns = _build_model_columns(model_positions, table, model_y0, model_y1,)

    if not model_columns:
        return None

    rows = []

    for row_index, row in enumerate(data):

        if row_index == model_row_index:
            continue

        if row_index >= len(row_ranges):
            continue

        y0, y1 = row_ranges[row_index]

        words = _get_words_in_row(page, y0, y1,)

        if not words:
            continue

        # Find the left-side parameter text.
        parameter_parts = []

        table_x0 = min(cell[0] for cell in table.cells if cell is not None)

        first_model_x = min(
            column["x0"]
            for column in model_columns
        )

        for word in words:

            if word["x1"] <= first_model_x:

                parameter_parts.append(
                    word["text"]
                )

        parameter = _normalize_text(" ".join(parameter_parts))

        if not parameter:
            continue

        # Extract value groups from the model area.
        value_words = [
            word
            for word in words
            if word["x0"] >= first_model_x
        ]

        value_groups = _group_words(value_words)

        if not value_groups:
            continue

        values = defaultdict(list)

        for value in value_groups:

            text = _normalize_text(value["text"])

            if not text:
                continue

            assigned_models = (_assign_value_to_models(value, model_columns,))

            for model in assigned_models:

                if text not in values[model]:

                    values[model].append(text)

        if not values:
            continue

        normalized_values = {}

        for model, model_values in values.items():

            if len(model_values) == 1:
                normalized_values[model] = (model_values[0])

            else:
                normalized_values[model] = ( " | ".join(model_values))

        rows.append(
            {
                "parameter": parameter,
                "values": normalized_values,
            })

    return {
        "models": [
            column["model"]
            for column in model_columns
        ],
        "rows": rows,
    }


def table_to_text(parsed_table):
    """
    Convert the structured table into text suitable
    for the LLM.

    The important difference from PyPDFLoader is that
    the model-to-value relationship is explicitly written.
    """

    if not parsed_table:
        return ""

    lines = []

    for row in parsed_table["rows"]:

        parameter = row["parameter"]

        for model, value in row["values"].items():

            lines.append(
                f"{model} | "
                f"{parameter} | "
                f"{value}"
            )

    return "\n".join(lines)


def parse_page_tables(page):
    """
    Parse all detectable tables on a PDF page.
    """

    tables = page.find_tables()
    parsed_tables = []

    for table in tables.tables:

        parsed = parse_table(page, table,)

        if parsed is not None:

            parsed_tables.append(parsed)

    return parsed_tables