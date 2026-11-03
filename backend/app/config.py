from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]

# Env files are read by pydantic-settings, so the precedence is deterministic
# and identical from every working directory:
#
#   1. the real process environment  (always wins; never overwritten by a file)
#   2. backend/.env                   (the canonical file for this service)
#   3. .env at the repository root    (a convenience fallback)
#
# The previous implementation called load_dotenv() at import time, which put the
# ROOT .env into os.environ *before* pydantic-settings ran. Because
# python-dotenv does not override an existing variable, the root .env then won
# over backend/.env -- so rotating the key in backend/.env could silently keep
# using a stale key from the root .env. Do not add load_dotenv() calls here.
#
# pydantic-settings reads a list of env files in order and lets the LAST one
# win, so the list below is written lowest priority first: the root .env is
# read first and backend/.env overrides it.
ENV_FILES = (str(ROOT_DIR / ".env"), str(ROOT_DIR / "backend" / ".env"))

# The files in the order they take effect, highest priority first. Used for
# diagnostics ("where did this value come from?").
ENV_FILES_BY_PRIORITY = tuple(reversed(ENV_FILES))


class Settings(BaseSettings):
    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # ---- provider ------------------------------------------------------- #
    # repr=False keeps the key out of repr(settings): a stray log line must
    # never be able to print it.
    gemini_api_key: str = Field(default="", repr=False)
    llm_provider: str = "gemini"
    llm_model: str = "gemini-3.5-flash-lite"
    llm_api_version: str = "v1beta"
    llm_timeout_seconds: float = 20.0
    llm_max_retries: int = 3
    llm_retry_base_delay_seconds: float = 0.5
    llm_retry_max_delay_seconds: float = 8.0
    llm_temperature: float = 0.2
    llm_max_output_tokens: int = 400
    llm_safety_block_threshold: str = "BLOCK_ONLY_HIGH"
    llm_history_turns: int = 6

    # ---- embeddings ----------------------------------------------------- #
    embedding_provider: str = "huggingface"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384

    # ---- chunking ------------------------------------------------------- #
    chunk_max_tokens: int = 400
    chunk_min_tokens: int = 200
    chunk_overlap_tokens: int = 0

    # ---- retrieval ------------------------------------------------------ #
    chroma_persist_dir: str = "./chroma_db"
    top_k: int = 6
    min_similarity: float = 0.35
    candidate_k: int = 12
    retrieval_script_boost: float = 0.05
    retrieval_hybrid: bool = True
    retrieval_hybrid_rrf_k: int = 60
    retrieval_dedupe: bool = True
    retrieval_answer_min_similarity: float = 0.35

    # ---- fallback (used when the provider cannot answer) --------------- #
    fallback_max_chunks: int = 1
    fallback_max_chars: int = 700

    # ---- behaviour ------------------------------------------------------ #
    query_rewrite: bool = True
    auto_rebuild_index: bool = False
    health_check_on_startup: bool = True
    health_check_fail_fast: bool = False
    # Call the provider during the startup check. Off by default: booting the
    # service must not spend quota or wait on a slow provider. The
    # command-line health check always probes.
    health_check_probe_provider: bool = False
    max_message_chars: int = 500
    handoff_email: str = "hotelaapp@gmail.com"
    handoff_whatsapp: str = ""
    rate_limit_per_minute: int = 60
    turnstile_enabled: bool = False
    turnstile_secret: str = Field(default="", repr=False)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = Field(default="", repr=False)
    smtp_from: str = ""

    # ---- observability -------------------------------------------------- #
    log_level: str = "INFO"
    log_json: bool = True

    model_config = SettingsConfigDict(env_file=ENV_FILES, extra="ignore", case_sensitive=False)

    # ------------------------------------------------------------------ #
    # derived values
    # ------------------------------------------------------------------ #
    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def rate_limit(self) -> str:
        return f"{self.rate_limit_per_minute}/minute"

    @property
    def data_dir(self) -> Path:
        return ROOT_DIR / "data"

    @property
    def chroma_dir(self) -> Path:
        path = Path(self.chroma_persist_dir)
        return path if path.is_absolute() else ROOT_DIR / "backend" / path

    @property
    def kb_dir(self) -> Path:
        return ROOT_DIR / "kb"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'hotela.db'}"

    @property
    def chunking_signature(self) -> str:
        """Part of the index version: the chunking settings change the chunks."""
        return f"{self.chunk_max_tokens}:{self.chunk_min_tokens}:{self.chunk_overlap_tokens}"

    @property
    def has_api_key(self) -> bool:
        return bool(self.gemini_api_key) and self.gemini_api_key != "YOUR_GEMINI_API_KEY"

    @property
    def api_key_source(self) -> str:
        """Where *this* key came from, for diagnostics. Never returns the key."""
        if not self.has_api_key:
            return "not set"
        if os.environ.get("GEMINI_API_KEY") == self.gemini_api_key:
            return "process environment"
        for path in ENV_FILES_BY_PRIORITY:
            candidate = Path(path)
            if not candidate.exists():
                continue
            for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip().startswith("GEMINI_API_KEY") and "=" in line:
                    value = line.split("=", 1)[1].strip().strip("\"'")
                    if value and value == self.gemini_api_key:
                        try:
                            return candidate.relative_to(ROOT_DIR).as_posix()
                        except ValueError:  # a file outside the repository
                            return str(candidate)
        return "settings"


settings = Settings()
