from pathlib import Path
import re
from pypdf import PdfReader

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PDF_PATH = PROJECT_ROOT / "data" / "catalog" / "GeneralCatalog.pdf"

reader = PdfReader(str(PDF_PATH))


def extract_models(text: str) -> list[str]:
    pattern = r"\bFX[A-Z]{2}\d{2}[A-Z0-9]+\b"
    return list(dict.fromkeys(re.findall(pattern, text)))


def extract_family_models(start_page: int, end_page: int):
    models = []

    inside_specifications = False

    for page in range(start_page - 1, end_page):

        text = reader.pages[page].extract_text() or ""

        # Начало блока specifications
        if re.search(r"\bSPECIFICATIONS\b", text, re.IGNORECASE):
            inside_specifications = True

        if inside_specifications:

            # Если начался новый раздел — прекращаем искать модели
            if re.search(r"\bACCESSORIES\b", text, re.IGNORECASE):
                text = re.split(
                    r"\bACCESSORIES\b",
                    text,
                    maxsplit=1,
                    flags=re.IGNORECASE
                )[0]

                inside_specifications = False

            models.extend(extract_models(text))

    return list(dict.fromkeys(models))

