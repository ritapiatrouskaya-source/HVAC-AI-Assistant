
from langchain_chroma import Chroma

from src.embeddings import create_embeddings
from src.config import VECTOR_DB_PATH


def create_vector_store(documents):
    """
    Create a new Chroma vector store from documents.
    """

    embeddings = create_embeddings()

    vector_db = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=str(VECTOR_DB_PATH),
    )

    return vector_db


def load_or_create_vector_store(documents):
    """
    Load existing Chroma database if it exists.
    Otherwise create a new one.
    """

    VECTOR_DB_PATH.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Chroma stores files inside this directory.
    existing_files = list(
        VECTOR_DB_PATH.iterdir()
    )

    if existing_files:

        print("Loading existing Chroma vector database...")

        embeddings = create_embeddings()

        vector_db = Chroma(
            persist_directory=str(VECTOR_DB_PATH),
            embedding_function=embeddings,
        )

        return vector_db

    print("Creating new Chroma vector database...")

    return create_vector_store(documents)