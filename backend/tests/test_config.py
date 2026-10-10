from whosaid.config import load_settings


def test_defaults_and_env_override(monkeypatch, tmp_path):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("LLM_REASONING_EFFORT", "low")
    s = load_settings(env_file=tmp_path / "missing.env")
    assert s.llm_model == "qwen3.5:2b-mlx"
    assert s.llm_reasoning_effort == "low"
    assert s.llm_base_url.endswith("/v1")
