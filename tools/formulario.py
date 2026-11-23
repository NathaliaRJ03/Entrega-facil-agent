"""Envio do link do Forms e detecção automática de que o cliente o enviou.

O agente só envia o link e encerra a resposta. Quem espera o envio é o servidor
do chat (chat_web/app.py), que confere a planilha e, ao achar uma reclamação
nova, aciona o agente de novo. Assim o link aparece na hora para o cliente.
"""

import os
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlsplit

from google.adk.tools import ToolContext

from integrations.workspace import carregar_reclamacoes

from .salvar_atendimento import ids_ja_atendidos

# Códigos internos das perguntas do Forms (para o link pré-preenchido).
_ENTRY_NOME = os.getenv("FORMS_ENTRY_NOME", "entry.1246677129")
_ENTRY_PEDIDO = os.getenv("FORMS_ENTRY_PEDIDO", "entry.1295866107")


def _limpar(texto: str, limite: int) -> str:
    """Tira caracteres de controle e corta; o valor vem do chat (não confiável)."""
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(texto or "")).strip()[:limite]


def _link_preenchido(base: str, nome: str, id_pedido: str) -> str:
    partes = urlsplit(base)
    url = f"{partes.scheme}://{partes.netloc}{partes.path}?usp=pp_url"
    # Abre o formulário já com a conta da Entrega Fácil (se estiver logada no navegador),
    # em vez da conta pessoal que estiver ativa.
    conta = os.getenv("FORMS_AUTHUSER", "entregafacil08@gmail.com").strip()
    if conta:
        url += f"&authuser={quote(conta)}"
    if nome:
        url += f"&{_ENTRY_NOME}={quote(nome)}"
    if id_pedido:
        url += f"&{_ENTRY_PEDIDO}={quote(id_pedido)}"
    return url


CHAVE_BASE = "formulario_ids_anteriores"


MAX_TENTATIVAS_IDENTIDADE = 3
_CHAVE_TENTATIVAS = "tentativas_identidade"


def enviar_link_formulario(
    tool_context: ToolContext,
    nome_cliente: str = "",
    id_pedido: str = "",
) -> str:
    """Confere nome e ID do pedido na Gold e, só se baterem, devolve o link do Forms.

    Antes de chamar, peça ao cliente o nome completo e o ID do pedido no chat.
    Se os dados não conferirem, nenhum link é enviado. Depois de mostrar o link,
    termine a resposta: o sistema detecta sozinho o envio do formulário.

    Args:
        nome_cliente: Nome que o cliente informou no chat.
        id_pedido: ID do pedido que o cliente informou no chat.
    """
    link = os.getenv("FORMS_URL", "").strip()
    if not link:
        return "Link do formulário não configurado. Avise o cliente que um atendente enviará o link."
    nome = _limpar(nome_cliente, 80)
    pedido = _limpar(id_pedido, 40)
    if not (nome and pedido):
        return (
            "Faltam dados. Peça ao cliente, no chat, o nome completo e o ID do "
            "pedido (o que ainda não foi informado) e só então chame de novo. "
            "Sem os dois dados, não envie o link."
        )

    tentativas = int(tool_context.state.get(_CHAVE_TENTATIVAS, 0) or 0)
    if tentativas >= MAX_TENTATIVAS_IDENTIDADE:
        return (
            "Limite de tentativas atingido. NÃO envie o link. Diga ao cliente que "
            "não foi possível confirmar os dados do pedido e que um atendente "
            "entrará em contato. Não tente de novo."
        )
    from .consultar_dados import confirmar_cliente_na_gold  # evita import circular

    # A leitura da planilha (~2 s) não depende da conferência na Gold: roda junto.
    with ThreadPoolExecutor(max_workers=1) as pool:
        leitura_forms = pool.submit(carregar_reclamacoes, True)
        confere = confirmar_cliente_na_gold(nome, pedido)
        if confere:
            try:
                reclamacoes, _ = leitura_forms.result()
            except (OSError, ValueError, KeyError):
                reclamacoes = []
    if not confere:
        tool_context.state[_CHAVE_TENTATIVAS] = tentativas + 1
        return (
            "Não foi possível confirmar o nome e o ID do pedido juntos. NÃO envie o "
            "link. Diga ao cliente, sem revelar qual dado está errado nem o que "
            "consta nos registros, que não conseguiu confirmar essas informações e "
            "peça que confira o nome completo e o ID do pedido (como aparecem na "
            "compra) e envie de novo."
        )

    tool_context.state[_CHAVE_TENTATIVAS] = 0
    tool_context.state[CHAVE_BASE] = [r["id_reclamacao"] for r in reclamacoes]
    return (
        f"Dados confirmados. Link do formulário: {_link_preenchido(link, nome, pedido)}. "
        "Mostre o link ao cliente e termine a resposta; o envio será detectado "
        "automaticamente."
    )


def cancelar_espera_formulario(tool_context: ToolContext) -> str:
    """Encerra a espera do formulário quando o cliente desiste da reclamação.

    Chame quando o cliente disser que não quer mais reclamar ou não vai
    preencher o formulário. Depois, despeça-se com cordialidade.
    """
    tool_context.state[CHAVE_BASE] = None
    return (
        "Espera do formulário encerrada. Confirme ao cliente que tudo bem, que o "
        "atendimento foi encerrado sem abrir reclamação e que ele pode voltar quando "
        "quiser. Não envie outro link."
    )


def ids_novos(base: list[str]) -> list[str]:
    """IDs de reclamações que não estavam na planilha quando o link foi enviado."""
    conhecidos = set(base)
    try:
        reclamacoes, _ = carregar_reclamacoes(forcar=True)
    except (OSError, ValueError, KeyError):
        return []
    atendidos = ids_ja_atendidos()
    return [
        r["id_reclamacao"]
        for r in reclamacoes
        if r["id_reclamacao"] not in conhecidos and r["id_reclamacao"] not in atendidos
    ]
