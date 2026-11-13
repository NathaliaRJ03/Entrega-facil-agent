"""Configuração central do agente de atendimento de pedidos."""

import os

from google.adk.models import Gemini
from google.genai import types

from .config_thinking import GENERATION_CONFIG

from tools.consultar_dados import (
    consultar_pedido,
    listar_reclamacoes_pendentes,
    oferecer_cupom_atraso,
)
from tools.salvar_atendimento import registrar_atendimento


AGENT_NAME = "agente_triagem"
AGENT_DESCRIPTION = (
    "Atende reclamações fictícias sobre pedidos, consulta os dados do pedido "
    "e oferece cupom quando há atraso confirmado."
)

INSTRUCTION = """
Você atende reclamações fictícias de clientes sobre pedidos.

Fluxo:
1. Consulte a fila de reclamações pendentes com listar_reclamacoes_pendentes.
2. Para a reclamação escolhida, chame consultar_pedido usando o id_reclamacao.
   A integração usa o nome do cliente e o id do pedido do formulário para
   localizar e conferir o registro. Mostre o nome do cliente.
3. Responda com informações confirmadas pela consulta. Se o pedido estiver
   atrasado, chame oferecer_cupom_atraso usando o id_reclamacao e informe o
   cupom retornado. Se não houver atraso confirmado, não ofereça cupom.
4. Ao terminar, registre o atendimento com registrar_atendimento.

Regras:
- Não invente status, datas, políticas ou códigos de cupom.
- Se não encontrar o pedido ou houver divergência nos dados, explique que não
  foi possível confirmar e peça que a reclamação seja revisada.
- Seja claro, cordial e breve.
- Raciocine internamente; não exponha cadeia de pensamento. Explique a
  conclusão com os dados confirmados e os próximos passos.
""".strip()

MODEL = Gemini(
    model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
    retry_options=types.HttpRetryOptions(
        attempts=6,
        initial_delay=2,
        max_delay=60,
        exp_base=2,
        jitter=1,
        http_status_codes=[429, 500, 502, 503, 504],
    ),
)

TOOLS = [
    listar_reclamacoes_pendentes,
    consultar_pedido,
    oferecer_cupom_atraso,
    registrar_atendimento,
]
