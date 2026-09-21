import re
from collections import defaultdict

from langchain_core.documents import Document

from src.config import TOP_K


def extract_identifiers(text: str) -> list[str]:
    """
    Extract technical identifiers such as:

    FTXB09BXVJU
    RXB09BXVJU
    U4
    E3
    R410A
    """

    return re.findall(
        r"\b[A-Z]{1,6}[-_]?\d{1,6}[A-Z0-9]*\b",
        text.upper(),
    )


def extract_keywords(text: str) -> list[str]:
    """
    Extract meaningful words from the question.
    """

    stop_words = {
        "what",
        "is",
        "the",
        "a",
        "an",
        "of",
        "for",
        "to",
        "in",
        "on",
        "and",
        "or",
        "does",
        "do",
        "mean",
        "maximum",
        "minimum",
        "how",
        "much",
        "many",
        "can",
        "be",
    }

    words = re.findall(
        r"[A-Za-z0-9]+",
        text.lower(),
    )

    return [
        word
        for word in words
        if word not in stop_words
        and len(word) > 2]


def document_key(document):
    return (
        document.metadata.get("source"),
        document.metadata.get("page"),
        document.page_content,)


def create_retriever(vector_db):

    semantic_retriever = vector_db.as_retriever(
        search_type="similarity",
        search_kwargs={"k": TOP_K,},)

    class HybridRetriever:

        def invoke(self, query: str, preferred_source: str | None = None, preferred_page: int | None = None,):

            identifiers = extract_identifiers(query)
            keywords = extract_keywords(query)

            results = []
            seen = set()

            # ==================================================
            # 1. PREFERRED PAGE
            # ==================================================

            if (
                    preferred_source is not None
                    and preferred_page is not None):

                try:

                    page_data = vector_db.get(
                        where={
                            "$and": [
                                {"source": {"$contains": preferred_source}},
                                {"page": preferred_page},]})

                except Exception:

                    page_data = {
                        "documents": [],
                        "metadatas": [],}

                for content, metadata in zip(
                        page_data.get("documents", []),
                        page_data.get("metadatas", []),):

                    document = Document( page_content=content, metadata=metadata,)

                    key = document_key(document)

                    if key in seen:
                        continue

                    seen.add(key)
                    results.append(document)

                # --------------------------------------------------
                # IF THE SELECTED MODEL PAGE EXISTS,
                # IT HAS ABSOLUTE PRIORITY.
                # --------------------------------------------------

                if results:
                    return results

            # ==================================================
            # 2. EXACT IDENTIFIER SEARCH
            # ==================================================

            exact_pages = defaultdict(list)

            for identifier in identifiers:

                try:

                    data = vector_db.get(where_document={"$contains": identifier})

                except Exception:

                    continue

                for content, metadata in zip(
                        data.get("documents", []),
                        data.get("metadatas", []),):

                    source = metadata.get("source")
                    page = metadata.get("page")

                    if source is None or page is None:
                        continue

                    exact_pages[(source, page)].append(identifier)

            # ==================================================
            # 3. OTHER PAGES CONTAINING THE MODEL / IDENTIFIER
            # ==================================================

            if exact_pages:
                scored_pages = []

                for (source, page,), matched_identifiers in exact_pages.items():

                    try:

                        page_data = vector_db.get(
                            where={
                                "$and": [
                                    {"source": source},
                                    {"page": page},]})

                    except Exception:
                        continue

                    page_documents = []

                    for content, metadata in zip(
                            page_data.get("documents", []),
                            page_data.get("metadatas", []),):
                        page_documents.append( Document(page_content=content, metadata=metadata,))

                    page_text = " ".join(
                        document.page_content
                        for document in page_documents).lower()

                    score = 0

                    # Exact identifier
                    score += (len(set(matched_identifiers)) * 1000)

                    # Question keywords
                    for keyword in keywords:

                        if keyword in page_text:
                            score += 100

                    scored_pages.append((score, source, page, page_documents,))

                scored_pages.sort(
                    key=lambda item: item[0],
                    reverse=True,)

                for (score, source, page, page_documents,) in scored_pages:

                    for document in page_documents:
                        key = document_key(document)

                        if key in seen:
                            continue

                        seen.add(key)
                        results.append(document)

                    if len(results) >= TOP_K * 2:
                        break

                if results:
                    return results

            # ==================================================
            # 4. SEMANTIC SEARCH
            # ==================================================

            return semantic_retriever.invoke(query)
    return HybridRetriever()