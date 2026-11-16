"""Cria o agente usando a configuração central do projeto."""

from google.adk.agents import Agent

from integrations.latencia_sheets import (
    finalizar_medicao_latencia,
    iniciar_medicao_latencia,
)

from .config_agent import (
    AGENT_DESCRIPTION,
    AGENT_NAME,
    GENERATION_CONFIG,
    INSTRUCTION,
    MODEL,
    TOOLS,
    responder_falha_dos_modelos,
)


root_agent = Agent(
    name=AGENT_NAME,
    model=MODEL,
    description=AGENT_DESCRIPTION,
    instruction=INSTRUCTION,
    tools=TOOLS,
    generate_content_config=GENERATION_CONFIG,
    before_agent_callback=iniciar_medicao_latencia,
    after_agent_callback=finalizar_medicao_latencia,
    on_model_error_callback=responder_falha_dos_modelos,
)

