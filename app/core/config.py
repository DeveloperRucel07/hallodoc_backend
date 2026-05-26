import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "HalloDOC Backend"
    API_VERSION: str = "v1"

    JWT_SECRET: str = os.getenv("JWT_SECRET")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    COOKIE_SECURE: bool = False 
    COOKIE_SAMESITE: str = "lax" 
    PRACTICE_CODE: str = "123456"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "hallodoc:latest"

    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8000
    CHROMA_DB_PATH: str = "./data/chroma_db"
    CHROMA_TOKEN: str = ""

    COLLECTION_NAME: str = "medical_rag_de"
    EMBEDDING_MODEL: str = "nomic-embed-text"

    CHUNK_SIZE: int = 200
    CHUNK_OVERLAP: int = 25

    PDF_DIR: str = "./data/medicines"
    DB_URL: str = "sqlite:///./data/hallodoc.db"
    SCRAPE_DELAY: float = 1.5
    WEB_SOURCES: list[str] = []

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


config = Settings()