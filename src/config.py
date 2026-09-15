"""Settings tập trung — đọc từ .env (W1 task 1.3).

Mọi tham số cấu hình đều đi qua Settings để:
- Không hard-code secret (rubric 5.4): API key chỉ nằm trong .env
- Ghi target_config_hash được (W3): cùng config -> cùng hash -> tái lập
- Bật/tắt guardrail bằng DEFENSE_PROFILE (W5) mà không đổi code
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Cấu hình toàn hệ thống. Đọc từ .env, override bằng biến môi trường."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM (target dùng llama-3.3-70b-versatile trên Groq LPU) ---
    LLM_PROVIDER: str = "groq"
    LLM_MODEL: str = "qwen/qwen3.8-27b"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.groq.com/openai/v1"
    LLM_TEMPERATURE: float = 0.0

    # --- TARGET ---
    TARGET_HOST: str = "0.0.0.0"
    TARGET_PORT: int = 8000
    CANARY_TOKEN: str = "CANARY-REDLINE-REPLACE-ME"

    # --- RAG ---
    RAG_COLLECTION: str = "redline_docs"
    RAG_CHUNK_SIZE: int = 500
    RAG_CHUNK_OVERLAP: int = 50

    # --- DB ---
    DATABASE_URL: str = "sqlite:///./data/redline.db"

    # --- GUARDRAIL (W5: bật/tắt để đo bypass rate) ---
    DEFENSE_PROFILE: Literal["none", "basic", "strict"] = "none"

    # --- ROE LIMITS ---
    ROE_MAX_REQUESTS_PER_MIN: int = 30
    ROE_MAX_TOKENS_TOTAL: int = 500_000
    ROE_MAX_ATTEMPTS: int = 5
    ROE_KILL_SWITCH: bool = False

    # --- LOGGING ---
    LOG_LEVEL: str = "INFO"
    REDACT_SECRETS: bool = True

    # --- NGROK (cho Kaggle / remote tunnel) ---
    NGROK_AUTHTOKEN: str = ""

    @property
    def target_config_hash(self) -> str:
        """Hash cấu hình mục tiêu — W3 ghi kèm mỗi kết quả để tái lập.

        Cùng (model, temperature, system prompt, defense profile, canary)
        -> cùng hash. Phải ổn định trong một phiên.
        """
        import hashlib

        payload = "|".join(
            [
                self.LLM_PROVIDER,
                self.LLM_MODEL,
                str(self.LLM_TEMPERATURE),
                str(self.DEFENSE_PROFILE),
                self.CANARY_TOKEN,
            ]
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@lru_cache
def get_settings() -> Settings:
    """Singleton settings — các module gọi get_settings() thay vì tạo mới."""
    return Settings()
