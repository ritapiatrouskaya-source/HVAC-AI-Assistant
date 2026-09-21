# loading functions

from src.loader import load_document
from src.chunking import splitting
from src.vector_store import load_or_create_vector_store
from src.llm import create_llm
from src.retriever import create_retriever
from src.rag import ask_question
from src.config import VECTOR_DB_PATH

from src.config import DATA_PATH

REBUILD_VECTOR_DB = False

if REBUILD_VECTOR_DB or not VECTOR_DB_PATH.exists() or not any(VECTOR_DB_PATH.iterdir()):
    documents = load_document(str(DATA_PATH))
    print(f"Documents: {len(documents)}")

    chunks = splitting(documents)
    print(f"Chunks: {len(chunks)}")

    vector_db = load_or_create_vector_store(chunks)
else:
    vector_db = load_or_create_vector_store()

retriever = create_retriever(vector_db)
llm = create_llm()

question = "What is the maximum piping length for RXSQ48?"

answer = ask_question(
    retriever,
    llm,
    question
)

print(answer)