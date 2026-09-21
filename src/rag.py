from langchain_core.prompts import ChatPromptTemplate
from pathlib import Path
import fitz
from src.equipment import find_equipment
from src.table_parser import parse_page_tables, table_to_text


def ask_question(
    vector_db,
    retriever,
    llm,
    question: str,
    manufacturer: str | None = None,
    outdoor_unit: str | None = None,
    system_type: str | None = None,
    indoor_unit: str | None = None,):

    equipment = find_equipment(indoor_unit)

    if equipment is None:
        return "Selected indoor unit was not found in the equipment database."

    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    catalog_path = (PROJECT_ROOT / "data" / "catalog" / "GeneralCatalog.pdf")

    # --------------------------------------------------
    # BUILD SEARCH QUERY
    # --------------------------------------------------

    search_parts = []

    if manufacturer:
        search_parts.append(manufacturer)

    if system_type:
        search_parts.append(system_type)

    if outdoor_unit:
        search_parts.append(outdoor_unit)

    if indoor_unit:
        search_parts.append(indoor_unit)

    search_parts.append(question)
    search_query = " ".join(search_parts)

    # --------------------------------------------------
    # RETRIEVE DOCUMENTS
    # --------------------------------------------------

    results = retriever.invoke(
        search_query,
        preferred_source="GeneralCatalog.pdf",
        preferred_page=equipment["pdf_page"] - 1,)

    # --------------------------------------------------
    # STRUCTURED TABLE CONTEXT
    # --------------------------------------------------

    structured_table_context = ""

    table_keywords = {
        "capacity",
        "piping",
        "pipe",
        "length",
        "height",
        "width",
        "depth",
        "dimension",
        "dimensions",
        "weight",
        "sound",
        "airflow",
        "refrigerant",
        "drain",
        "charge",
        "temperature",
        "operating range",
        "cooling",
        "heating",
    }

    question_lower = question.lower()

    is_table_question = any(
        keyword in question_lower
        for keyword in table_keywords)

    if is_table_question:
        pdf = fitz.open(catalog_path)

        try:

            page_index = equipment["pdf_page"] - 1
            page = pdf.load_page(page_index)
            parsed_tables = parse_page_tables(page)
            structured_parts = []

            for parsed_table in parsed_tables:

                table_text = table_to_text(parsed_table)

                if table_text:
                    structured_parts.append(table_text)

            structured_table_context = ("\n\n".join(structured_parts))

        finally:
            pdf.close()

    if not results:
        return "The documentation does not contain enough information to answer this question."

    # --------------------------------------------------
    # BUILD CONTEXT
    # --------------------------------------------------

    context_parts = []

    for doc in results:

        source = doc.metadata.get("source", "")
        page = doc.metadata.get("page")

        if page is not None:
            page_number = page + 1
        else:
            page_number = "unknown"

        context_parts.append(
            f"Source: {Path(source).stem}\n"
            f"Page: {page_number}\n"
            f"Content:\n{doc.page_content}"
        )

    context = "\n\n".join(context_parts)

    if structured_table_context:

        context += (
            "\n\n"
            "STRUCTURED TABLE DATA FROM SELECTED MODEL PAGE:\n"
            "This data was reconstructed from the PDF table "
            "using column geometry. Model-to-value relationships "
            "must be preserved exactly.\n\n"
            f"{structured_table_context}"
        )

    # --------------------------------------------------
    # PROMPT
    # --------------------------------------------------

    prompt = ChatPromptTemplate.from_template(
        """
You are an experienced HVAC Design Engineer and Technical AI Assistant.

Answer the user's question using ONLY the provided documentation.

GENERAL RULES

1. Never use your own knowledge.
2. Never guess.
3. If the documentation does not contain the answer, clearly say that the information is unavailable.
4. Use all relevant retrieved documents.
5. The answer may come from any document:
   - General Catalog
   - Engineering Data
   - Installation Manual
   - Service Manual
   - other technical documentation
6. Do not assume that the answer must be located in the General Catalog.
7. Preserve units exactly as stated in the documentation.
8. If the question concerns an error code, search the retrieved documentation for the error code and explain its meaning and the documented information related to it.
9. If the question concerns a selected indoor unit, use the selected model as context, but do not restrict the search to the catalog page of that model.
10. Do not reproduce the entire context.

TABLE RULES

If information comes from a table:

- Treat model names as column headers.
- Match values to the corresponding model column.
- Do not assume that the first value belongs to every model.
- If a value is shared by multiple models, preserve that relationship.
- If the table structure is ambiguous, state that the documentation is ambiguous rather than inventing a value.

RESPONSE

Give a direct technical answer.

Briefly explain the relevant information from the documentation.

Do not include a separate Sources section in the answer.
The application will display the sources separately.

CONTEXT:
{context}

QUESTION:
{question}
"""
    )

    messages = prompt.format_messages(context=context, question=question,)

    # --------------------------------------------------
    # LLM
    # --------------------------------------------------

    response = llm.invoke(messages)
    answer = response.content

    # --------------------------------------------------
    # SOURCES
    # --------------------------------------------------

    sources = []
    for doc in results:
        source = doc.metadata.get("source", "")
        page = doc.metadata.get("page")

        if page is None:
            continue

        source_name = Path(source).stem
        page_number = page + 1

        source_text = (
            f"- {source_name}, page {page_number}"
        )

        if source_text not in sources:
            sources.append(source_text)

    if sources:
        answer += "\n\nSources:\n"
        answer += "\n".join(sources)

    return answer