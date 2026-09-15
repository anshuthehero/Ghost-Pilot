"""
Centralized Application Settings & Configuration.
"""

import os
from typing import List
from pydantic import Field

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:
    from pydantic import BaseModel as BaseSettings  # type: ignore
    SettingsConfigDict = None  # type: ignore


class Settings(BaseSettings):
    APP_ENV: str = "development"
    DEBUG: bool = False
    
    HOST: str = "127.0.0.1"
    PORT: int = 9471
    
    # Security & Tokens
    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production-1234567890"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    DEV_AUTH_TOKEN: str = "ghost-dev-token-local"
    
    # AI Credentials
    # AI Provider Credentials & Configuration (Supports Server-Side, Alternate Providers, and BYOK)
    AI_PROVIDER: str = "groq"
    AI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    BYOK_ENABLED: bool = False
    GROQ_MODEL: str = "qwen/qwen3.8-27b"
    GROQ_WHISPER_MODEL: str = "whisper-large-v3-turbo"
    
    # Database & Storage
    DATABASE_URL: str = "sqlite:///./ghost_copilot.db"
    REDIS_URL: str = ""

    @property
    def resolved_database_url(self) -> str:
        """Resolves relative SQLite database path to a guaranteed user-writable location."""
        url = self.DATABASE_URL
        if url.startswith("sqlite:///./") or url == "sqlite:///ghost_copilot.db":
            try:
                data_dir = os.path.expanduser("~/.ghost_copilot")
                os.makedirs(data_dir, exist_ok=True)
                db_path = os.path.join(data_dir, "ghost_copilot.db")
                # Test writability (handle sandbox/read-only home)
                with open(db_path, "a") as f:
                    pass
                return f"sqlite:///{db_path}"
            except Exception:
                repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                return f"sqlite:///{os.path.join(repo_root, 'ghost_copilot.db')}"
        return url
    
    # Strict CORS Origins (No wildcards in production)
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:9471", "http://127.0.0.1:9471", "http://localhost:3000"
    ]
    
    # Rate Limiting
    RATE_LIMIT_SOLVE_RPM: int = 30
    RATE_LIMIT_TRANSCRIBE_RPM: int = 60
    
    # Versioning & Updates
    LATEST_CLIENT_VERSION: str = "3.0.0"
    MIN_REQUIRED_CLIENT_VERSION: str = "3.0.0"

    def validate_production_environment(self):
        """
        Enforces production fail-closed security invariant:
        - APP_ENV must be explicitly recognized (development, production, test, staging).
        - Hosted production/staging MUST use PostgreSQL (not SQLite). Local desktop may use SQLite.
        - Production must have a strong, non-default JWT secret key.
        - Production must fail closed if no valid AI-provider credential/configuration exists.
        - Production must not include development-only CORS origins (M-5 fix).
        """
        VALID_ENVIRONMENTS = {"development", "production", "test", "staging"}
        if self.APP_ENV not in VALID_ENVIRONMENTS:
            raise RuntimeError(
                f"Configuration error: APP_ENV must be one of {sorted(list(VALID_ENVIRONMENTS))}, got '{self.APP_ENV}'."
            )

        if self.APP_ENV in ("production", "staging"):
            if self.JWT_SECRET_KEY == "dev-secret-key-change-in-production-1234567890" or len(self.JWT_SECRET_KEY) < 32:
                raise RuntimeError(
                    "Production configuration error: JWT_SECRET_KEY must be a secure, random secret of at least 32 characters."
                )
            if self.DATABASE_URL.startswith("sqlite"):
                raise RuntimeError(
                    "Production hosted deployment MUST use PostgreSQL. Local/standalone desktop operation may continue using SQLite."
                )
            # M-5 fix: Reject development-only origins in production
            dev_origins = {"http://localhost:3000", "http://127.0.0.1:3000"}
            exposed = dev_origins & set(self.ALLOWED_ORIGINS)
            if exposed:
                raise RuntimeError(
                    f"Production CORS configuration error: development-only origins present: {exposed}. "
                    "Remove them from ALLOWED_ORIGINS in your production .env file."
                )
            # Fail closed if no AI-provider configuration/credentials exist
            has_ai_credential = (
                bool(self.AI_API_KEY)
                or bool(self.GROQ_API_KEY)
                or bool(self.OPENAI_API_KEY)
                or bool(self.BYOK_ENABLED)
                or bool(os.environ.get("AI_API_KEY"))
                or bool(os.environ.get("OPENAI_API_KEY"))
                or bool(os.environ.get("BYOK_ENABLED"))
            )
            if not has_ai_credential:
                raise RuntimeError(
                    "Production configuration error: No valid AI-provider credential or BYOK configuration exists."
                )

    if SettingsConfigDict:
        model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    else:
        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
            extra = "ignore"


# Helper to load settings from .env manually if pydantic-settings isn't doing it
def get_settings() -> Settings:
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env_path = os.path.join(base_dir, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    if k not in os.environ:
                        os.environ[k] = v.strip()

    # Parse allowed origins if present in environ as comma-separated string
    allowed = os.environ.get("ALLOWED_ORIGINS")
    origins = [o.strip() for o in allowed.split(",")] if allowed else [
        "http://localhost:9471", "http://127.0.0.1:9471", "http://localhost:3000"
    ]
    
    s = Settings(
        APP_ENV=os.environ.get("APP_ENV", "development"),
        DEBUG=os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes"),
        HOST=os.environ.get("HOST", "127.0.0.1"),
        PORT=int(os.environ.get("PORT", "9471")),
        JWT_SECRET_KEY=os.environ.get("JWT_SECRET_KEY", "dev-secret-key-change-in-production-1234567890"),
        JWT_ALGORITHM=os.environ.get("JWT_ALGORITHM", "HS256"),
        ACCESS_TOKEN_EXPIRE_MINUTES=int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")),
        DEV_AUTH_TOKEN=os.environ.get("DEV_AUTH_TOKEN", "ghost-dev-token-local"),
        AI_PROVIDER=os.environ.get("AI_PROVIDER", "groq"),
        AI_API_KEY=os.environ.get("AI_API_KEY", ""),
        GROQ_API_KEY=os.environ.get("GROQ_API_KEY", "") or os.environ.get("AI_API_KEY", ""),
        OPENAI_API_KEY=os.environ.get("OPENAI_API_KEY", ""),
        BYOK_ENABLED=os.environ.get("BYOK_ENABLED", "false").lower() in ("true", "1", "yes"),
        GROQ_MODEL=os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b"),
        GROQ_WHISPER_MODEL=os.environ.get("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo"),
        DATABASE_URL=os.environ.get("DATABASE_URL", "sqlite:///./ghost_copilot.db"),
        REDIS_URL=os.environ.get("REDIS_URL", ""),
        ALLOWED_ORIGINS=origins,
        RATE_LIMIT_SOLVE_RPM=int(os.environ.get("RATE_LIMIT_SOLVE_RPM", "30")),
        RATE_LIMIT_TRANSCRIBE_RPM=int(os.environ.get("RATE_LIMIT_TRANSCRIBE_RPM", "60")),
        LATEST_CLIENT_VERSION=os.environ.get("LATEST_CLIENT_VERSION", "3.0.0"),
        MIN_REQUIRED_CLIENT_VERSION=os.environ.get("MIN_REQUIRED_CLIENT_VERSION", "3.0.0")
    )
    s.validate_production_environment()
    return s


settings = get_settings()
