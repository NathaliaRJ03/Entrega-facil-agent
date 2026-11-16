from google.genai import types


# Para o Gemini 3.5 Flash-Lite, mantenha a temperatura padrão recomendada.
TEMPERATURE = 1.0

# LOW mantém o agente ágil para o fluxo de consulta e uso de ferramentas.
# Troque para MEDIUM se a avaliação mostrar que ele precisa de mais raciocínio.
THINKING_LEVEL = types.ThinkingLevel.LOW

MAX_OUTPUT_TOKENS = 1024

# A OpenAI não aceita thinking_level; a reserva usa o `effort` do próprio
# provedor, no mesmo nível do Gemini.
ESFORCO_RESERVAS = "low"

GENERATION_CONFIG = types.GenerateContentConfig(
    temperature=TEMPERATURE,
    max_output_tokens=MAX_OUTPUT_TOKENS,
    thinking_config=types.ThinkingConfig(
        thinking_level=THINKING_LEVEL,
        include_thoughts=False,
    ),
)
