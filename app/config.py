import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self):
        self.app_env = os.getenv("APP_ENV", "development").strip().lower()
        if self.app_env not in {"development", "test", "staging", "production"}:
            raise ValueError("APP_ENV must be development, test, staging, or production")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.6")
        self.openrouter_referer = os.getenv("OPENROUTER_SITE_URL", "http://localhost:8000")
        self.openrouter_title = os.getenv("OPENROUTER_APP_NAME", "Draftroom")
        self.openrouter_visibility = os.getenv("OPENROUTER_APP_VISIBILITY", "hidden")
        self.tavily_api_key = os.getenv("TAVILY_API_KEY", "")
        self.enable_web = os.getenv("ENABLE_WEB", "true").strip().lower() in {"1", "true", "yes", "on"}
        self.pinecone_api_key = os.getenv("PINECONE_API_KEY", "")
        self.pinecone_index = os.getenv("PINECONE_INDEX", "docgen-kb")
        self.pinecone_cloud = os.getenv("PINECONE_CLOUD", "aws")
        self.pinecone_region = os.getenv("PINECONE_REGION", "us-east-1")
        self.pinecone_embed_model = os.getenv("PINECONE_EMBED_MODEL", "")
        self.api_key = os.getenv("API_KEY", "")
        self.data_dir = Path(os.getenv("DATA_DIR", "data")).expanduser()
        self._database_url = os.getenv("DATABASE_URL", "").strip()
        self.max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "25"))
        self.max_upload_total_mb = int(os.getenv("MAX_UPLOAD_TOTAL_MB", "100"))
        self.max_upload_files = int(os.getenv("MAX_UPLOAD_FILES", "10"))
        self.allowed_ext = {".docx", ".pdf", ".ppt", ".pptx", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".txt", ".md"}
        if self.max_upload_mb < 1:
            raise ValueError("MAX_UPLOAD_MB must be at least 1")
        if self.max_upload_files < 1:
            raise ValueError("MAX_UPLOAD_FILES must be at least 1")
        if self.max_upload_total_mb < self.max_upload_mb:
            raise ValueError("MAX_UPLOAD_TOTAL_MB must be at least MAX_UPLOAD_MB")
        if self.app_env == "production" and len(self.api_key) < 32:
            raise ValueError("API_KEY must contain at least 32 characters when APP_ENV=production")
        if self.app_env == "production" and not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is required when APP_ENV=production")
        if self.app_env == "production" and not self.database_url.startswith("postgresql+"):
            raise ValueError("DATABASE_URL must point to PostgreSQL when APP_ENV=production")
        if self.app_env == "production" and not self.pinecone_api_key:
            raise ValueError("PINECONE_API_KEY is required when APP_ENV=production")

    @property
    def database_url(self) -> str:
        if self._database_url:
            return self._database_url
        path = (self.data_dir / "draftroom.db").resolve()
        return f"sqlite:///{path}"


settings = Settings()
