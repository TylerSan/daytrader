"""Unit tests for daytrader.core.llm — backend selection + API backend.

The Anthropic client is always mocked; no network calls.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from daytrader.core import llm
from daytrader.core.llm import (
    DEFAULT_API_MODEL,
    APIBackend,
    CLIBackend,
    LLMCallError,
    LLMConfigError,
    LLMTimeoutError,
    get_llm_backend,
    load_llm_settings,
    resolve_api_key,
)


def _root(tmp_path: Path, default_yaml: str = "{}\n", user_yaml: str | None = None,
          secrets_yaml: str | None = None) -> Path:
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "default.yaml").write_text(default_yaml)
    if user_yaml is not None:
        (cfg / "user.yaml").write_text(user_yaml)
    if secrets_yaml is not None:
        (cfg / "secrets.yaml").write_text(secrets_yaml)
    return tmp_path


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def test_default_backend_is_cli(tmp_path):
    root = _root(tmp_path)
    s = load_llm_settings(root, env={})
    assert s.backend == "cli"
    assert s.backend_source == "default" or s.backend_source == "config ai.backend"
    assert isinstance(get_llm_backend(root, env={}), CLIBackend)


def test_config_selects_api(tmp_path):
    root = _root(tmp_path, "ai:\n  backend: api\n  model: claude-sonnet-5-5\n  max_tokens: 4000\n")
    s = load_llm_settings(root, env={})
    assert (s.backend, s.backend_source) == ("api", "config ai.backend")
    assert (s.model, s.model_source) == ("claude-sonnet-5-5", "config ai.model")
    assert s.max_tokens == 4000


def test_user_yaml_overrides_default(tmp_path):
    root = _root(tmp_path, "ai:\n  backend: cli\n", user_yaml="ai:\n  backend: api\n")
    assert load_llm_settings(root, env={}).backend == "api"


def test_env_beats_config(tmp_path):
    root = _root(tmp_path, "ai:\n  backend: api\n  model: claude-sonnet-5-5\n")
    env = {"DAYTRADER_LLM_BACKEND": "CLI", "DAYTRADER_LLM_MODEL": "claude-haiku-5-5",
           "DAYTRADER_LLM_MAX_TOKENS": "1234"}
    s = load_llm_settings(root, env=env)
    assert s.backend == "cli" and s.backend_source == "env DAYTRADER_LLM_BACKEND"
    assert s.model == "claude-haiku-5-5" and s.max_tokens == 1234


def test_default_model(tmp_path):
    root = _root(tmp_path)
    s = load_llm_settings(root, env={"DAYTRADER_LLM_BACKEND": "api"})
    assert s.model == DEFAULT_API_MODEL == "claude-opus-5-5"


def test_unknown_backend_raises(tmp_path):
    root = _root(tmp_path)
    with pytest.raises(LLMConfigError):
        load_llm_settings(root, env={"DAYTRADER_LLM_BACKEND": "openai"})


def test_api_key_env_then_secrets(tmp_path):
    root = _root(tmp_path, secrets_yaml="anthropic:\n  api_key: from-file\n")
    assert resolve_api_key(root, env={"ANTHROPIC_API_KEY": "from-env"}) == (
        "from-env", "env ANTHROPIC_API_KEY")
    assert resolve_api_key(root, env={}) == ("from-file", "config/secrets.yaml")


def test_api_key_missing(tmp_path):
    root = _root(tmp_path)
    assert resolve_api_key(root, env={}) == (None, "missing")


def test_get_backend_api(tmp_path):
    root = _root(tmp_path)
    be = get_llm_backend(root, env={"DAYTRADER_LLM_BACKEND": "api", "ANTHROPIC_API_KEY": "k"})
    assert isinstance(be, APIBackend)
    assert be.model == DEFAULT_API_MODEL


def test_api_backend_without_key_errors_on_use(tmp_path):
    root = _root(tmp_path)
    be = get_llm_backend(root, env={"DAYTRADER_LLM_BACKEND": "api"})
    with pytest.raises(LLMConfigError):
        be.complete(prompt="hi", timeout=5)


# ---------------------------------------------------------------------------
# API backend with a mocked client
# ---------------------------------------------------------------------------


def _block(type_: str, text: str = "") -> SimpleNamespace:
    return SimpleNamespace(type=type_, text=text)


def _message(content, stop_reason="end_turn", model="claude-opus-5-5"):
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        model=model,
        stop_details=None,
        usage=SimpleNamespace(input_tokens=10, output_tokens=20,
                              cache_creation_input_tokens=3, cache_read_input_tokens=4),
    )


class _FakeStream:
    def __init__(self, message):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter([object(), object()])

    def get_final_message(self):
        return self._message


def _mock_client(*messages) -> MagicMock:
    client = MagicMock()
    seq = [_FakeStream(m) for m in messages]
    client.beta.messages.stream.side_effect = list(seq)
    client.messages.stream.side_effect = list(_FakeStream(m) for m in messages)
    return client


def _api(tmp_path, client, default_yaml="{}\n") -> APIBackend:
    root = _root(tmp_path, default_yaml)
    settings = load_llm_settings(root, env={"DAYTRADER_LLM_BACKEND": "api"})
    return APIBackend(settings, api_key="k", key_source="test", client=client)


def test_api_complete_maps_system_and_tools(tmp_path):
    client = _mock_client(_message([_block("text", "报告")]))
    be = _api(tmp_path, client)
    msgs = [
        {"role": "system", "content": [
            {"type": "text", "text": "SYS", "cache_control": {"type": "ephemeral"}}]},
        {"role": "user", "content": "USER"},
    ]
    resp = be.complete(messages=msgs, max_tokens=12288, timeout=30)

    assert resp.text == "报告"
    assert resp.input_tokens == 10 and resp.output_tokens == 20
    assert resp.cache_creation_tokens == 3 and resp.cache_read_tokens == 4
    kwargs = client.beta.messages.stream.call_args.kwargs
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["system"] == [
        {"type": "text", "text": "SYS", "cache_control": {"type": "ephemeral"}}]
    assert kwargs["messages"] == [{"role": "user", "content": "USER"}]
    assert kwargs["max_tokens"] == 32000  # floor beats the caller's 12288
    assert kwargs["tools"][0]["type"] == "web_search_20260209"
    assert kwargs["output_config"] == {"effort": "high"}
    assert kwargs["betas"] == ["server-side-fallback-2026-07-01"]
    assert kwargs["extra_body"] == {"fallbacks": "default"}


def test_api_fallbacks_off_uses_plain_stream(tmp_path):
    client = _mock_client(_message([_block("text", "ok")]))
    be = _api(tmp_path, client, "ai:\n  fallbacks: false\n  web_search: false\n")
    assert be.complete(prompt="p", timeout=30).text == "ok"
    client.beta.messages.stream.assert_not_called()
    kwargs = client.messages.stream.call_args.kwargs
    assert "tools" not in kwargs and "betas" not in kwargs


def test_api_final_text_drops_pre_search_narration(tmp_path):
    content = [
        _block("text", "I'll search first."),
        _block("server_tool_use"),
        _block("web_search_tool_result"),
        _block("text", "### 🌐 Macro"),
        _block("text", " Sentiment"),
    ]
    be = _api(tmp_path, _mock_client(_message(content)))
    assert be.complete(prompt="p", timeout=30).text == "### 🌐 Macro Sentiment"


def test_api_pause_turn_resumes(tmp_path):
    first = _message([_block("server_tool_use")], stop_reason="pause_turn")
    second = _message([_block("text", "done")])
    client = _mock_client(first, second)
    be = _api(tmp_path, client)
    resp = be.complete(prompt="p", timeout=30)
    assert resp.text == "done"
    assert resp.input_tokens == 20  # summed over both requests
    second_call = client.beta.messages.stream.call_args_list[1].kwargs
    assert second_call["messages"][-1]["role"] == "assistant"


def test_api_refusal_raises_call_error(tmp_path):
    be = _api(tmp_path, _mock_client(_message([], stop_reason="refusal")))
    with pytest.raises(LLMCallError):
        be.complete(prompt="p", timeout=30)


def test_api_sdk_timeout_maps_to_llm_timeout(tmp_path):
    import anthropic
    import httpx

    client = MagicMock()
    client.beta.messages.stream.side_effect = anthropic.APITimeoutError(
        request=httpx.Request("POST", "https://example.invalid"))
    be = _api(tmp_path, client)
    with pytest.raises(LLMTimeoutError):
        be.complete(prompt="p", timeout=30)


# ---------------------------------------------------------------------------
# Callers route on the selected backend
# ---------------------------------------------------------------------------


def test_ai_analyst_uses_api_backend_and_keeps_retry_contract(monkeypatch):
    from daytrader.reports.core.ai_analyst import AIAnalyst

    backend = MagicMock(spec=APIBackend)
    backend.complete.side_effect = [
        LLMCallError("api status=529 OverloadedError: busy"),
        llm.LLMResponse(text="# 报告", model="claude-opus-5-5", stop_reason="end_turn",
                        input_tokens=5, output_tokens=7),
    ]
    monkeypatch.setattr("daytrader.reports.core.ai_analyst.time.sleep", lambda _: None)
    run = MagicMock()
    monkeypatch.setattr(subprocess, "run", run)

    result = AIAnalyst(backend=backend).call(
        [{"role": "user", "content": "x"}], max_tokens=12288)

    assert result.text == "# 报告" and result.model == "claude-opus-5-5"
    assert result.input_tokens == 5
    assert backend.complete.call_count == 2
    run.assert_not_called()


def test_ai_analyst_api_raises_runtime_error_after_retries(monkeypatch):
    from daytrader.reports.core.ai_analyst import AIAnalyst

    backend = MagicMock(spec=APIBackend)
    backend.complete.side_effect = LLMTimeoutError("t")
    monkeypatch.setattr("daytrader.reports.core.ai_analyst.time.sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="AI call failed: api timeout after 300s"):
        AIAnalyst(backend=backend, max_retries=2).call([{"role": "user", "content": "x"}])
    assert backend.complete.call_count == 3


def test_ai_analyst_cli_backend_still_shells_out(monkeypatch):
    from daytrader.reports.core.ai_analyst import AIAnalyst

    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, 0, stdout="out", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = AIAnalyst(backend=CLIBackend()).call([{"role": "user", "content": "x"}])
    assert result.text == "out"
    assert calls[0][0] == ["claude", "-p"]
    assert calls[0][1]["input"] == "[USER]\nx"


def test_sentiment_collector_api_failure_is_unavailable(tmp_path):
    from daytrader.reports.sentiment.collector import SentimentCollector

    backend = MagicMock(spec=APIBackend)
    backend.complete.side_effect = LLMTimeoutError("t")
    res = SentimentCollector(["MES"], timeout_s=7, backend=backend,
                             failure_log_dir=tmp_path).collect()
    assert res.unavailable
    assert "api timeout after 7s" in (res.unavailable_reason or str(res))


def test_premarket_invoke_returns_empty_on_api_error(monkeypatch):
    from daytrader.premarket.analyzers import ai_analyst as pm

    backend = MagicMock(spec=APIBackend)
    backend.complete.side_effect = LLMCallError("boom")
    monkeypatch.setattr(pm, "get_llm_backend", lambda: backend)
    assert pm.invoke_claude_analysis("p") == ""

    backend.complete.side_effect = None
    backend.complete.return_value = llm.LLMResponse(
        text=" 分析 \n", model="m", stop_reason="end_turn")
    assert pm.invoke_claude_analysis("p") == "分析"
