import importlib


def test_openai_compatible_proxy_uses_chat_completions(monkeypatch):
    import tradingagents.llm_clients.openai_client as openai_client

    mod = importlib.reload(openai_client)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(mod, "NormalizedChatOpenAI", FakeChatOpenAI)

    mod.OpenAIClient(
        model="gpt-5.2",
        provider="openai",
        base_url="https://right.codes/codex/v1",
    ).get_llm()

    assert captured["base_url"] == "https://right.codes/codex/v1"
    assert "use_responses_api" not in captured


def test_native_openai_uses_responses_api(monkeypatch):
    import tradingagents.llm_clients.openai_client as openai_client

    mod = importlib.reload(openai_client)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(mod, "NormalizedChatOpenAI", FakeChatOpenAI)

    mod.OpenAIClient(model="gpt-5.2", provider="openai").get_llm()

    assert captured["use_responses_api"] is True
