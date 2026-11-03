"""Configuration is part of the contract.

Two things must hold:

* the right key wins - a key rotated in ``backend/.env`` has to take effect,
  and a key set in the process environment has to win over every file;
* no key ever reaches a log line - not through ``repr(settings)``, not
  through the diagnostics that say where the key came from.
"""

from __future__ import annotations

from pathlib import Path

from app.config import ENV_FILES, ENV_FILES_BY_PRIORITY, ROOT_DIR, Settings


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_the_last_env_file_in_the_list_wins(monkeypatch, tmp_path):
    """pydantic-settings merges the env files in order and the last one wins.

    That is why the file list in config.py is written lowest priority first.
    """
    low = _write(tmp_path / "root.env", "TOP_K=3\n")
    high = _write(tmp_path / "backend.env", "TOP_K=9\n")
    monkeypatch.delenv("TOP_K", raising=False)

    assert Settings(_env_file=(str(low), str(high))).top_k == 9
    assert Settings(_env_file=(str(high), str(low))).top_k == 3


def test_the_process_environment_wins_over_every_file(monkeypatch, tmp_path):
    low = _write(tmp_path / "root.env", "TOP_K=3\n")
    high = _write(tmp_path / "backend.env", "TOP_K=9\n")
    monkeypatch.setenv("TOP_K", "11")

    assert Settings(_env_file=(str(low), str(high))).top_k == 11


def test_the_real_env_files_are_ordered_lowest_priority_first():
    assert Path(ENV_FILES[0]) == ROOT_DIR / ".env"
    assert Path(ENV_FILES[1]) == ROOT_DIR / "backend" / ".env"
    # the diagnostics list them the other way round: highest priority first
    assert ENV_FILES_BY_PRIORITY[0] == ENV_FILES[1]
    assert ENV_FILES_BY_PRIORITY[1] == ENV_FILES[0]


def test_a_missing_key_is_not_a_key():
    settings = Settings(_env_file=None, gemini_api_key="")
    assert settings.has_api_key is False
    assert settings.api_key_source == "not set"


def test_the_placeholder_key_is_not_a_key():
    settings = Settings(_env_file=None, gemini_api_key="YOUR_GEMINI_API_KEY")
    assert settings.has_api_key is False


def test_the_api_key_never_appears_in_the_settings_repr(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-value")
    settings = Settings(_env_file=None)
    assert settings.has_api_key is True
    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings)


def test_the_api_key_source_names_the_file_and_not_the_key(monkeypatch, tmp_path):
    key_file = _write(tmp_path / "backend.env", "GEMINI_API_KEY=abc123secret\n")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("app.config.ENV_FILES_BY_PRIORITY", (str(key_file),))

    settings = Settings(_env_file=(str(key_file),))
    assert settings.has_api_key is True
    assert settings.api_key_source == str(key_file)
    assert "abc123secret" not in settings.api_key_source


def test_the_api_key_source_reports_the_process_environment(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "abc123secret")
    settings = Settings(_env_file=None)
    assert settings.api_key_source == "process environment"
    assert "abc123secret" not in settings.api_key_source


def test_the_tunables_are_configurable(monkeypatch):
    """Everything the audit asked to be configurable really is."""
    monkeypatch.setenv("TOP_K", "4")
    monkeypatch.setenv("MIN_SIMILARITY", "0.5")
    monkeypatch.setenv("CANDIDATE_K", "20")
    monkeypatch.setenv("LLM_MODEL", "some-other-model")
    monkeypatch.setenv("CHUNK_MAX_TOKENS", "300")
    monkeypatch.setenv("RETRIEVAL_HYBRID", "false")

    settings = Settings(_env_file=None)
    assert settings.top_k == 4
    assert settings.min_similarity == 0.5
    assert settings.candidate_k == 20
    assert settings.llm_model == "some-other-model"
    assert settings.chunk_max_tokens == 300
    assert settings.retrieval_hybrid is False


def test_the_chunking_settings_are_part_of_the_index_version():
    """Changing the chunking must invalidate the index, not silently keep it."""
    base = Settings(_env_file=None)
    other = Settings(_env_file=None, chunk_max_tokens=999)
    assert base.chunking_signature != other.chunking_signature
