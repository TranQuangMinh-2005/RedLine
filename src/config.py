"""Settings tập trung — đọc từ .env (W1 task 1.3).

Mọi tham số cấu hình đều đi qua Settings để:
- Không hard-code secret (rubric 5.4): API key chỉ nằm trong .env
- Ghi target_config_hash được (W3): cùng config -> cùng hash -> tái lập
- Bật/tắt guardrail bằng DEFENSE_PROFILE (W5) mà không đổi code
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ExecutionMode = Literal["agent", "llm"]


class Settings(BaseSettings):
    """Cấu hình toàn hệ thống. Đọc từ .env, override bằng biến môi trường."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM: endpoint "env" (Docker environment) khởi tạo từ các biến này ---
    # Model mặc định Groq nằm trong code (model_catalog); .env chỉ cần override.
    LLM_PROVIDER: str = "groq"
    LLM_MODEL: str = "openai/gpt-oss-20b"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.groq.com/openai/v1"
    LLM_TEMPERATURE: float = 0.0
    LLM_TIMEOUT_SECONDS: float = 120.0
    # Reasoning model (gpt-oss): "low" | "medium" | "high". Rỗng = không gửi tham số.
    # Đặt "low" để suy luận không ăn hết max_tokens khiến câu trả lời rỗng.
    LLM_REASONING_EFFORT: str = ""
    # Endpoint khởi động: env (biến LLM_* ở trên) | groq | custom (REMOTE_LLM_*)
    LLM_ENDPOINT: Literal["env", "groq", "openrouter", "custom"] = "env"
    # Key Groq riêng; bỏ trống thì dùng LLM_API_KEY khi LLM_BASE_URL là Groq.
    GROQ_API_KEY: str = ""
    # Key OpenRouter riêng; bỏ trống thì dùng LLM_API_KEY khi LLM_BASE_URL là OpenRouter.
    OPENROUTER_API_KEY: str = ""
    # Endpoint ngoài điền sẵn cho UI, ví dụ Kaggle gateway: https://xxxx.ngrok-free.app/v1
    REMOTE_LLM_BASE_URL: str = ""
    REMOTE_LLM_API_KEY: str = ""
    # primary: only primary; round_robin: alternate; failover: primary then secondary.
    LLM_ROUTING_MODE: Literal["primary", "round_robin", "failover"] = "primary"
    LLM_SECONDARY_PROVIDER: str = ""
    LLM_SECONDARY_MODEL: str = ""
    LLM_SECONDARY_API_KEY: str = ""
    LLM_SECONDARY_BASE_URL: str = ""

    # --- TARGET ---
    TARGET_HOST: str = "0.0.0.0"
    TARGET_PORT: int = 8000
    CANARY_TOKEN: str = "CANARY-REDLINE-REPLACE-ME"
    # Một actor mock cố định cho toàn bộ benchmark. Đây là danh tính scenario,
    # không phải dữ liệu do prompt của attacker cung cấp.
    SCENARIO_CUSTOMER_ID: str = "CUS-001"
    # Phiên bản system prompt của target. Tăng giá trị này mỗi khi prompt đổi để
    # target_config_hash tách được kết quả của các phiên bản prompt khác nhau.
    SYSTEM_PROMPT_VERSION: str = "weak-none-2026-09-17"
    # Chỉ bật trong sandbox benchmark để harness tạo fixture có kiểm soát.
    ENABLE_TEST_FIXTURES: bool = False
    # Tắt để chạy target như chatbot thuần (model unrestricted không hỗ trợ tool calling).
    # Mặc định true để giữ nguyên hành vi agent đầy đủ.
    ENABLE_TOOLS: bool = True

    # --- RAG ---
    RAG_COLLECTION: str = "redline_docs"
    RAG_CHUNK_SIZE: int = 500
    RAG_CHUNK_OVERLAP: int = 50

    # --- DB ---
    DATABASE_URL: str = "sqlite:///./data/redline.db"

    # --- GUARDRAIL (W5: bật/tắt để đo bypass rate) ---
    DEFENSE_PROFILE: Literal["none", "basic", "strict"] = "none"

    # --- LLAMA GUARD (chốt riêng, model phân loại chạy local: llama.cpp server hoặc Ollama) ---
    LLAMA_GUARD_ENABLED: bool = False
    LLAMA_GUARD_BASE_URL: str = "http://localhost:8088/v1"
    LLAMA_GUARD_MODEL: str = "Llama-Guard-3-1B-Q4_K_M"
    LLAMA_GUARD_API_KEY: str = ""
    LLAMA_GUARD_CHECK_OUTPUT: bool = True
    LLAMA_GUARD_FAIL_MODE: Literal["closed", "open"] = "closed"
    LLAMA_GUARD_TIMEOUT_SECONDS: float = 30.0

    # --- PROMPT GUARD 2 (chốt riêng: prompt injection / jailbreak, model local CPU) ---
    PROMPT_GUARD_ENABLED: bool = False
    PROMPT_GUARD_URL: str = "http://localhost:8089"
    PROMPT_GUARD_MODEL: str = "Llama-Prompt-Guard-2-86M"
    PROMPT_GUARD_THRESHOLD: float = 0.5
    PROMPT_GUARD_CHECK_RAG: bool = True
    PROMPT_GUARD_FAIL_MODE: Literal["closed", "open"] = "closed"
    PROMPT_GUARD_TIMEOUT_SECONDS: float = 15.0

    # --- TRACE: trả pipeline guardrail cho UI khi request có include_trace ---
    # Tắt khi chạy benchmark nếu không muốn caller thấy luật guardrail.
    GUARDRAIL_TRACE_ENABLED: bool = True

    # --- ROE LIMITS ---
    ROE_MAX_REQUESTS_PER_MIN: int = 30
    ROE_MAX_TOKENS_TOTAL: int = 500_000
    ROE_MAX_ATTEMPTS: int = 5
    ROE_KILL_SWITCH: bool = False

    # --- LOGGING ---
    LOG_LEVEL: str = "INFO"
    REDACT_SECRETS: bool = True
    # Đường dẫn ghi audit JSONL để harness đọc evidence (audit_log/retrieval_log).
    # Rỗng nghĩa là chỉ ghi ra stdout như trước.
    AUDIT_LOG_PATH: str = ""

    # --- NGROK (cho Kaggle / remote tunnel) ---
    NGROK_AUTHTOKEN: str = ""

    @property
    def target_config_hash(self) -> str:
        """Hash cấu hình mục tiêu — W3 ghi kèm mỗi kết quả để tái lập.

        Cùng (model, temperature, system prompt, defense profile, canary)
        -> cùng hash. Phải ổn định trong một phiên.
        """
        return self.target_config_hash_for(self.DEFENSE_PROFILE)

    def target_config_hash_for(self, defense_profile: str) -> str:
        """Hash cấu hình theo profile thực sự đang chạy (kể cả runtime override)."""
        import hashlib

        from src.guardrails import llama_guard, prompt_guard
        from src.services import llm_runtime

        endpoint = llm_runtime.get_active()
        guard = llama_guard.get_config()
        injection_guard = prompt_guard.get_config()
        parts = [
            endpoint.provider,
            endpoint.model,
            endpoint.base_url,
            self.LLM_ROUTING_MODE,
            self.LLM_SECONDARY_PROVIDER,
            self.LLM_SECONDARY_MODEL,
            self.LLM_SECONDARY_BASE_URL,
            str(self.LLM_TEMPERATURE),
            defense_profile,
            self.CANARY_TOKEN,
            self.SCENARIO_CUSTOMER_ID,
            self.SYSTEM_PROMPT_VERSION,
            str(self.ENABLE_TOOLS),
        ]
        if guard.enabled:
            parts.append(
                f"llama_guard={guard.model}{'+output' if guard.check_output else ''}"
                f"@{guard.fail_mode}"
            )
        if injection_guard.enabled:
            parts.append(
                f"prompt_guard={injection_guard.model}@{injection_guard.threshold}"
                f"{'+rag' if injection_guard.check_rag else ''}"
                f"@{injection_guard.fail_mode}"
            )
        payload = "|".join(parts)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@lru_cache
def get_settings() -> Settings:
    """Singleton settings — các module gọi get_settings() thay vì tạo mới."""
    return Settings()
