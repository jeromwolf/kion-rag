"""
KION RAG PoC - Configuration
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "KION RAG PoC"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:32b"  # 32B for better quality

    # Embedding
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-large"

    # ChromaDB
    CHROMA_PERSIST_DIR: str = "./data/chroma_db"
    CHROMA_COLLECTION_NAME: str = "kion_equipment"

    # RAG
    TOP_K: int = 5

    class Config:
        env_file = ".env"


settings = Settings()
