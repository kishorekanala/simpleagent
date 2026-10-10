"""Offline checks of the agent definition (no model calls)."""

import importlib

from google.adk.agents.llm_agent import Agent


def test_root_agent_is_configured():
    from agents.simpleagent import agent, prompts

    assert isinstance(agent.root_agent, Agent)
    assert agent.root_agent.name == "root_agent"
    assert agent.root_agent.model == "gemini-2.5-flash"
    assert agent.root_agent.instruction == prompts.INSTRUCTION
    assert agent.root_agent.tools == []


def test_model_is_overridable_by_env(monkeypatch):
    from agents.simpleagent import config

    monkeypatch.setenv("AGENT_MODEL", "gemini-2.5-pro")
    try:
        assert importlib.reload(config).MODEL == "gemini-2.5-pro"
    finally:
        monkeypatch.delenv("AGENT_MODEL")
        importlib.reload(config)
