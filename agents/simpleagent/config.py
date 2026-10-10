"""Runtime configuration for simpleagent, read from environment variables."""

import os

MODEL = os.getenv("AGENT_MODEL", "gemini-2.5-flash")
