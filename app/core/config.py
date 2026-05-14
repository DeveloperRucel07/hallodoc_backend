from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "HalloDOC Backend"
    API_VERSION: str = "v1"

    JWT_SECRET: str = "SUPER_SECRET_CHANGE_ME"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    PRACTICE_CODE: str = "123456"

    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "llama3.2"

    CHROMA_DB_PATH: str = "/app/chroma_db"

    class Config:
        env_file = ".env"


settings = Settings()