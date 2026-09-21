from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader


def load_document(data_path: str):
    """
    Load all PDF documents from the data directory.

    Every PDF page becomes one LangChain Document.
    Page numbers remain zero-based in metadata.
    """

    data_path = Path(data_path)

    documents = []

    pdf_files = list(data_path.rglob("*.pdf"))

    for pdf_path in pdf_files:

        print("=" * 80)
        print(f"Loading: {pdf_path.name}")
        print("=" * 80)

        loader = PyPDFLoader(str(pdf_path))

        pages = loader.load()

        for page in pages:

            page.metadata["source"] = str(pdf_path)

            documents.append(page)

        print(f"Pages loaded: {len(pages)}")

    print("=" * 80)
    print(f"TOTAL DOCUMENTS: {len(documents)}")
    print("=" * 80)

    return documents