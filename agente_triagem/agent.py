from google.adk.agents import Agent

from .prompt import instruction
from .rag_lexical import buscar_casos_semelhantes


root_agent = Agent(
    name="agente_triagem",
    model="gemini-3.5-flash-lite",
    description=(
        "Agente de inteligência artificial para triagem "
        "de contestações financeiras da PagFácil."
    ),
    instruction=instruction,
    tools=[buscar_casos_semelhantes],
)
