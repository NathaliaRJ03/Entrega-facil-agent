"""Chat web do cliente: conversa com o agente sem mostrar ferramentas.

Rodar na raiz do projeto:  python -m uvicorn chat_web.app:app --port 8080
Abrir:                     http://localhost:8080

Só o texto que o agente escreve para o cliente chega ao navegador; as chamadas
de ferramenta ficam no servidor.

Fluxo do formulário: o agente envia o link e encerra a resposta (o link aparece
na hora). O navegador então chama /api/aguardar, que confere a planilha de
respostas até chegar uma reclamação nova e, só então, aciona o agente com uma
mensagem interna "[Sistema] ..." para ele responder com a solução.
"""

import asyncio
import json
import os
import re
import time
import unicodedata
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from agente_triagem.agent import root_agent  # noqa: E402
from integrations.contratos import PEDIDOS  # noqa: E402
from integrations.databricks import aquecer_conexao  # noqa: E402
from tools.formulario import CHAVE_BASE, ids_novos  # noqa: E402

PAGINA = Path(__file__).with_name("index.html")
APP_NAME = "entrega_facil_chat"
PREFIXO_SISTEMA = "[Sistema]"

# Desistência: encerra a espera do formulário no servidor, sem depender de o modelo
# chamar a ferramenta. Compara sem acento e sem maiúsculas ("nao quero mais...").
_DESISTENCIA = re.compile(
    r"(nao quero mais|nao vou mais|nao vou (fazer|preencher|enviar)|desisti|desistir|"
    r"desisto|deixa pra la|deixa para la|esquece|cancela(r)? (a )?reclamacao)"
)


def _desistiu(texto: str) -> bool:
    limpo = unicodedata.normalize("NFD", texto.lower())
    limpo = "".join(c for c in limpo if unicodedata.category(c) != "Mn")
    return bool(_DESISTENCIA.search(limpo))


ESPERA_MAXIMA_S = float(os.getenv("FORMS_ESPERA_SEGUNDOS", "900"))
# Cada conferência da planilha já leva ~2 s para baixar; esperar mais 3 s entre
# elas atrasava a resposta ao cliente em até 6 s depois do envio do formulário.
INTERVALO_S = float(os.getenv("FORMS_INTERVALO_SEGUNDOS", "0.5"))

app = FastAPI(title="Chat Entrega Fácil")


@app.on_event("startup")
async def aquecer() -> None:
    """Abre a conexão com a Gold antes do primeiro cliente (poupa 2 a 5 s)."""
    asyncio.create_task(asyncio.to_thread(aquecer_conexao, PEDIDOS))
sessoes = InMemorySessionService()
runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=sessoes)


class Mensagem(BaseModel):
    sessao: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    texto: str = Field(min_length=1, max_length=2000)


class Sessao(BaseModel):
    sessao: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


# Conversas encerradas pelo cliente ao iniciar outra: nada mais roda nelas.
canceladas: set[str] = set()


def _linha(dados: dict) -> str:
    return json.dumps(dados, ensure_ascii=False) + "\n"


async def _garantir_sessao(sessao: str):
    existente = await sessoes.get_session(app_name=APP_NAME, user_id=sessao, session_id=sessao)
    return existente or await sessoes.create_session(
        app_name=APP_NAME, user_id=sessao, session_id=sessao
    )


_PADRAO_CUPOM = re.compile(
    r"Cupom aprovado:\s*(?P<codigo>[A-Z0-9-]+);\s*benefício:\s*(?P<beneficio>.+?);\s*"
    r"validade:\s*(?P<dias>\d+)\s*dias"
)


def _cupom_da_ferramenta(evento) -> dict | None:
    """Lê o cupom aprovado direto da resposta da ferramenta (fonte única, não do texto do modelo)."""
    try:
        respostas = evento.get_function_responses()
    except Exception:  # noqa: BLE001 - evento sem respostas de ferramenta
        return None
    for resposta in respostas or []:
        if resposta.name != "oferecer_cupom_atraso":
            continue
        dados = resposta.response
        texto = dados.get("result", "") if isinstance(dados, dict) else str(dados)
        achado = _PADRAO_CUPOM.search(str(texto))
        if achado:
            return {
                "codigo": achado["codigo"],
                "beneficio": achado["beneficio"].strip(),
                "validade_dias": int(achado["dias"]),
            }
    return None


async def _rodar_agente(sessao: str, texto: str, state_delta: dict | None = None):
    """Roda o agente e devolve só o texto escrito ao cliente (sem ferramentas)."""
    entrada = types.Content(role="user", parts=[types.Part(text=texto)])
    cupom: dict | None = None
    try:
        async for evento in runner.run_async(
            user_id=sessao, session_id=sessao, new_message=entrada, state_delta=state_delta
        ):
            if sessao in canceladas:
                return
            cupom = _cupom_da_ferramenta(evento) or cupom
            if evento.partial or not evento.content or evento.author == "user":
                continue
            resposta = "".join(
                p.text for p in (evento.content.parts or []) if p.text and not p.thought
            ).strip()
            if resposta:
                yield _linha({"texto": resposta})
        if cupom:
            # Depois do texto: a página troca o código da mensagem por um cartão completo.
            yield _linha({"cupom": cupom})
    except Exception:  # noqa: BLE001 - nunca vazar detalhes internos ao cliente
        yield _linha({"texto": "Desculpe, tive um problema por aqui. Pode tentar de novo?"})


async def _base_pendente(sessao: str) -> list[str] | None:
    atual = await sessoes.get_session(app_name=APP_NAME, user_id=sessao, session_id=sessao)
    base = atual.state.get(CHAVE_BASE) if atual else None
    return base if isinstance(base, list) else None


@app.get("/")
def pagina() -> FileResponse:
    return FileResponse(PAGINA)


@app.get("/logo.png")
def logo() -> FileResponse:
    return FileResponse(PAGINA.with_name("logo.png"))


@app.post("/api/cancelar")
async def cancelar(corpo: Sessao) -> dict:
    """Encerra a conversa anterior quando o cliente inicia outra na interface."""
    canceladas.add(corpo.sessao)
    await sessoes.delete_session(
        app_name=APP_NAME, user_id=corpo.sessao, session_id=corpo.sessao
    )
    return {"cancelada": True}


@app.post("/api/mensagem")
async def mensagem(corpo: Mensagem) -> StreamingResponse:
    if corpo.sessao in canceladas:
        return StreamingResponse(iter([_linha({"fim": True})]), media_type="application/x-ndjson")
    await _garantir_sessao(corpo.sessao)
    texto = corpo.texto.strip()

    async def fluxo():
        if texto.startswith(PREFIXO_SISTEMA):
            yield _linha({"texto": "Não entendi. Pode me contar o que aconteceu com o seu pedido?"})
        else:
            delta = {CHAVE_BASE: None} if _desistiu(texto) else None
            async for linha in _rodar_agente(corpo.sessao, texto, delta):
                yield linha
            if await _base_pendente(corpo.sessao) is not None:
                yield _linha({"aguardando": True})
        yield _linha({"fim": True})

    return StreamingResponse(fluxo(), media_type="application/x-ndjson")


@app.post("/api/aguardar")
async def aguardar(corpo: Sessao) -> StreamingResponse:
    """Espera o cliente enviar o formulário e aciona o agente com a reclamação nova."""
    if corpo.sessao in canceladas:
        return StreamingResponse(iter([_linha({"fim": True})]), media_type="application/x-ndjson")
    await _garantir_sessao(corpo.sessao)

    async def fluxo():
        base = await _base_pendente(corpo.sessao)
        if base is None:
            yield _linha({"fim": True})
            return
        fim = time.monotonic() + ESPERA_MAXIMA_S
        novas: list[str] = []
        while time.monotonic() < fim and corpo.sessao not in canceladas:
            novas = await asyncio.to_thread(ids_novos, base)
            if novas:
                break
            await asyncio.sleep(INTERVALO_S)
        if corpo.sessao in canceladas:
            yield _linha({"fim": True})
            return
        if not novas:
            yield _linha({"fim": True, "expirou": True})
            return
        yield _linha({"recebido": True})
        aviso = (
            f"{PREFIXO_SISTEMA} Formulário recebido. id_reclamacao: {novas[-1]}. "
            "Siga o fluxo de atendimento a partir do passo 2 e responda ao cliente."
        )
        async for linha in _rodar_agente(corpo.sessao, aviso, {CHAVE_BASE: None}):
            yield linha
        yield _linha({"fim": True})

    return StreamingResponse(fluxo(), media_type="application/x-ndjson")
