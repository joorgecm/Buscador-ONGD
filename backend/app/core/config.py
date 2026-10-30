from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Configuración global de la aplicación cargada desde variables de entorno o .env."""

    PROJECT_NAME: str = "Buscador de ONGD - API (IEI)"
    VERSION: str = "0.1.0"

    # Base de datos PostgreSQL (SQLAlchemy 2.0 + psycopg v3)
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/buscador_ongd"

    # Rutas a las fuentes de datos originales (por defecto la muestra representativa en data/)
    CV_CSV_PATH: Path = BACKEND_DIR / "data" / "muestra_entidades_CV_20.csv"
    WRAPPER_CV_URL: str = "http://127.0.0.1:8000/wrappers/cv"

    # Scraper y caché de geocodificación
    GEOCACHE_PATH: Path = BACKEND_DIR / "cache" / "geocache.json"
    USAR_SELENIUM: bool = True
    SELENIUM_HEADLESS: bool = True

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
