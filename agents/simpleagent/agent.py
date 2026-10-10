from google.adk.agents.llm_agent import Agent

from . import prompts
from .config import MODEL

root_agent = Agent(
    model=MODEL,
    name="root_agent",
    description=prompts.DESCRIPTION,
    instruction=prompts.INSTRUCTION,
)
