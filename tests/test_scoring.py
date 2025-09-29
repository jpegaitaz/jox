import asyncio
import os
import pytest
from jox.orchestrator.scoring import score_match

@pytest.mark.asyncio
async def test_score_shape(monkeypatch):
    # Avoid real OpenAI calls by monkeypatching the LLM helper
    from jox import llm as llm_mod
    async def fake_json_chat(llm, system, user):
        return {"score": 7.5, "rationale": "test"}
    monkeypatch.setattr("jox.llm.openai_client.simple_json_chat", fake_json_chat)
    cv = {"raw":"python aws nlp"}
    job = {"description":"We need python and aws skills"}
    s = await score_match(cv, job)
    assert "score" in s
