"""Cria o agente usando a configuração central do projeto."""

from google.adk.agents import Agent

from .config_agent import (
    AGENT_DESCRIPTION,
    AGENT_NAME,
    GENERATION_CONFIG,
    INSTRUCTION,
    MODEL,
    TOOLS,
)


root_agent = Agent(
    name=AGENT_NAME,
    model=MODEL,
    description=AGENT_DESCRIPTION,
    instruction=INSTRUCTION,
    tools=TOOLS,
    generate_content_config=GENERATION_CONFIG,
)

