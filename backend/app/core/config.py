from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración global de la aplicación cargada desde variables de entorno o .env."""

    PROJECT_NAME: str = "Buscador de ONGD - API (IEI)"
    VERSION: str = "0.1.0"

    # Base de datos PostgreSQL (SQLAlchemy 2.0 + psycopg v3)
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/buscador_ongd"

    # LLM (Groq) para clasificar el ámbito de las entidades de Catalunya
    GROQ_API_KEY: str = ""

    # Orígenes permitidos para CORS (por si front-end y back-end se sirven por separado)
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
