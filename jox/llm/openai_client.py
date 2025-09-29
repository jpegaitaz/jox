from __future__ import annotations
import os
from typing import Any, Dict

from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage

def make_client(model: str, temperature: float = 0.1) -> ChatOpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY missing")
    return ChatOpenAI(model=model, temperature=temperature, api_key=api_key)

async def simple_json_chat(llm: ChatOpenAI, system: str, user: str) -> Dict[str, Any]:
    msgs = [SystemMessage(content=system), HumanMessage(content=user)]
    resp = await llm.ainvoke(msgs)
    import json
    try:
        return json.loads(resp.content)
    except Exception:
        return {"raw": resp.content}
