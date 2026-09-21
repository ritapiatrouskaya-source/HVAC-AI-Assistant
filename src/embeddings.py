# Loading Libraries
from langchain_huggingface import HuggingFaceEmbeddings

from src.config import EMBEDDING_MODEL

def create_embeddings():
    """
    Create and return the embedding model.
    """

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL
    )

    return embeddings