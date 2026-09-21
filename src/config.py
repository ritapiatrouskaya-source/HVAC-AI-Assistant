# Models
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


LLM_PROVIDER = "ollama"
LLM_MODEL = "llama3.1"

# Chunking
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# Retrieval
TOP_K = 5

# Paths

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_PATH = PROJECT_ROOT / "data"
VECTOR_DB_PATH = PROJECT_ROOT / "data" / "vector_db"