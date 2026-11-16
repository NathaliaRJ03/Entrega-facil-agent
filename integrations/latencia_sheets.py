"""Mede a execução completa do agente e envia os dados ao Google Sheets."""

import logging
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import gspread
from google.adk.agents import Context
from gspread.exceptions import WorksheetNotFound


logger = logging.getLogger(__name__)

CHAVE_INICIO_NS = "temp:latencia_inicio_ns"
CHAVE_INICIO_UTC = "temp:latencia_inicio_utc"
CABECALHOS = (
    "id_invocacao",
    "agente",
    "inicio_utc",
    "fim_utc",
    "horario_resposta",
    "latencia_ms",
    "status",
)

# Um único worker mantém a ordem das linhas e evita bloquear a resposta do agente.
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sheets-latencia")


def iniciar_medicao_latencia(contexto: Context) -> None:
    """Marca o início do processamento desta invocação do agente."""
    contexto.state[CHAVE_INICIO_NS] = time.perf_counter_ns()
    contexto.state[CHAVE_INICIO_UTC] = datetime.now(timezone.utc).isoformat(
        timespec="milliseconds"
    )


def finalizar_medicao_latencia(contexto: Context) -> None:
    """Calcula a duração e agenda a gravação sem esperar pela rede do Sheets."""
    inicio_ns = contexto.state.get(CHAVE_INICIO_NS)
    inicio_utc = contexto.state.get(CHAVE_INICIO_UTC)
    if not isinstance(inicio_ns, int) or not isinstance(inicio_utc, str):
        logger.warning(
            "Não encontrei o início da medição da invocação %s.",
            contexto.invocation_id,
        )
        return

    instante_fim = datetime.now(timezone.utc)
    fim_utc = instante_fim.isoformat(timespec="milliseconds")
    horario_resposta = instante_fim.astimezone(
        ZoneInfo("America/Sao_Paulo")
    ).isoformat(timespec="seconds")
    latencia_ms = round((time.perf_counter_ns() - inicio_ns) / 1_000_000, 2)
    linha = (
        contexto.invocation_id,
        contexto.agent_name,
        inicio_utc,
        fim_utc,
        horario_resposta,
        latencia_ms,
        "sucesso",
    )

    if not os.getenv("LATENCIA_SHEETS_ID", "").strip():
        logger.debug("LATENCIA_SHEETS_ID não configurado; latência não enviada ao Sheets.")
        return

    try:
        futuro = _EXECUTOR.submit(_anexar_linha, linha)
        futuro.add_done_callback(_registrar_falha_de_gravacao)
    except RuntimeError:
        logger.exception("Não foi possível agendar a gravação da latência no Sheets.")


def _anexar_linha(linha: tuple[object, ...]) -> None:
    """Cria a aba se necessário e acrescenta uma linha de métricas."""
    id_planilha = os.getenv("LATENCIA_SHEETS_ID", "").strip()
    nome_aba = os.getenv("LATENCIA_SHEETS_ABA", "latencia_agente").strip()
    arquivo_credenciais = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")

    caminho_credenciais = Path(arquivo_credenciais)
    if not caminho_credenciais.is_absolute():
        caminho_credenciais = Path(__file__).resolve().parents[1] / caminho_credenciais

    cliente = gspread.service_account(filename=str(caminho_credenciais))
    planilha = cliente.open_by_key(id_planilha)
    try:
        aba = planilha.worksheet(nome_aba)
    except WorksheetNotFound:
        aba = planilha.add_worksheet(
            title=nome_aba,
            rows=1000,
            cols=len(CABECALHOS),
        )

    cabecalhos_existentes = aba.row_values(1)
    if not cabecalhos_existentes:
        aba.append_row(list(CABECALHOS), value_input_option="RAW")
    elif tuple(cabecalhos_existentes) != CABECALHOS:
        raise ValueError(
            f"A aba '{nome_aba}' precisa ter estes cabeçalhos: {list(CABECALHOS)}"
        )

    aba.append_row(list(linha), value_input_option="RAW")


def _registrar_falha_de_gravacao(futuro: Future) -> None:
    try:
        futuro.result()
    except Exception:  # noqa: BLE001 - falha no dashboard não deve parar o agente
        logger.exception("Falha ao enviar a latência para o Google Sheets.")
