
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama

from src.config import LLM_PROVIDER, LLM_MODEL

load_dotenv("src/API_key.env")

def create_llm():
    """
    Create and return the configured language model.
    Supports OpenAI and Ollama.
    """
    if LLM_PROVIDER == "openai":
         return ChatOpenAI( model=LLM_MODEL, temperature=0)

    elif LLM_PROVIDER == "ollama":
        return ChatOllama(model=LLM_MODEL, temperature=0)

    raise ValueError(f"Unknown provider: {LLM_PROVIDER}")
