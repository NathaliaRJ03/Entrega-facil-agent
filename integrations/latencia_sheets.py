"""Envia métricas do agente ao Google Sheets: latência e tickets encerrados."""

import json
import logging
import os
import time
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from functools import partial
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
CABECALHOS_TICKET = (
    "ID_TICKET",
    "TIMESTAMP_ABERTURA",
    "TIMESTAMP_RESOLUCAO",
    "STATUS_TICKET",
)
FUSO_LOCAL = "America/Sao_Paulo"

# A gravação nunca bloqueia a resposta do agente. Com o Apps Script (que tem
# trava própria) as linhas saem em paralelo, para uma não esperar a outra e a
# planilha refletir cada atendimento na hora. Pela API do Sheets, o cabeçalho
# é criado sem trava, então fica um único worker.
_EXECUTOR = ThreadPoolExecutor(
    max_workers=4 if os.getenv("SHEETS_WEBHOOK_URL", "").strip() else 1,
    thread_name_prefix="sheets-latencia",
)
_ABAS_PRONTAS: dict[str, object] = {}  # aba -> worksheet com cabeçalho já conferido
_TENTATIVAS_ENVIO = 3


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

    if not sheets_configurado():
        logger.debug("Sheets não configurado; latência não enviada.")
        return

    try:
        futuro = _EXECUTOR.submit(_anexar_linha, linha)
        futuro.add_done_callback(_registrar_falha_de_gravacao)
    except RuntimeError:
        logger.exception("Não foi possível agendar a gravação da latência no Sheets.")


def horario_local(valor: str | datetime) -> str:
    """Normaliza um horário para São Paulo com fuso explícito.

    O Forms grava a data/hora local sem fuso ("2026-11-12 15:05:00"); o registro
    do atendimento é UTC. Converter os dois para o mesmo fuso evita que o tempo
    de resolução calculado no dashboard fique 3 horas errado.
    """
    fuso = ZoneInfo(FUSO_LOCAL)
    if isinstance(valor, datetime):
        instante = valor
    else:
        texto = str(valor or "").strip()
        if not texto:
            return ""
        try:
            instante = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        except ValueError:
            return texto
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=fuso)
    return instante.astimezone(fuso).isoformat(timespec="seconds")


def agendar_ticket(
    id_ticket: str,
    abertura: str,
    resolucao: str | datetime,
    status: str,
) -> None:
    """Envia em segundo plano uma linha do ticket encerrado para o Sheets.

    Usa a mesma planilha da latência, em outra aba. Só metadados: nenhum nome,
    contato ou texto da reclamação.
    """
    if not sheets_configurado():
        logger.debug("Sheets não configurado; ticket não enviado.")
        return

    linha = (id_ticket, horario_local(abertura), horario_local(resolucao), status)
    gravar = partial(
        _anexar_linha,
        nome_aba=os.getenv("TICKETS_SHEETS_ABA", "tickets_atendimento").strip(),
        cabecalhos=CABECALHOS_TICKET,
    )
    try:
        futuro = _EXECUTOR.submit(gravar, linha)
        futuro.add_done_callback(_registrar_falha_de_gravacao)
    except RuntimeError:
        logger.exception("Não foi possível agendar a gravação do ticket no Sheets.")


def _anexar_linha(
    linha: tuple[object, ...],
    nome_aba: str | None = None,
    cabecalhos: tuple[str, ...] = CABECALHOS,
) -> None:
    """Cria a aba se necessário e acrescenta uma linha de métricas."""
    nome_aba = nome_aba or os.getenv("LATENCIA_SHEETS_ABA", "latencia_agente").strip()
    webhook = os.getenv("SHEETS_WEBHOOK_URL", "").strip()
    if webhook:
        _enviar_para_apps_script(webhook, nome_aba, cabecalhos, linha)
        return

    id_planilha = os.getenv("LATENCIA_SHEETS_ID", "").strip()
    arquivo_credenciais = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")

    caminho_credenciais = Path(arquivo_credenciais)
    if not caminho_credenciais.is_absolute():
        caminho_credenciais = Path(__file__).resolve().parents[1] / caminho_credenciais

    # Abrir a planilha e conferir o cabeçalho custa várias chamadas; só a
    # primeira linha de cada aba paga isso, as seguintes fazem uma só (append).
    aba = _ABAS_PRONTAS.get(nome_aba)
    if aba is None:
        cliente = gspread.service_account(filename=str(caminho_credenciais))
        planilha = cliente.open_by_key(id_planilha)
        try:
            aba = planilha.worksheet(nome_aba)
        except WorksheetNotFound:
            aba = planilha.add_worksheet(
                title=nome_aba,
                rows=1000,
                cols=len(cabecalhos),
            )

        cabecalhos_existentes = aba.row_values(1)
        if not cabecalhos_existentes:
            aba.append_row(list(cabecalhos), value_input_option="RAW")
        elif tuple(cabecalhos_existentes) != cabecalhos:
            raise ValueError(
                f"A aba '{nome_aba}' precisa ter estes cabeçalhos: {list(cabecalhos)}"
            )
        _ABAS_PRONTAS[nome_aba] = aba

    try:
        aba.append_row(list(linha), value_input_option="RAW")
    except Exception:
        _ABAS_PRONTAS.pop(nome_aba, None)  # sessão expirada: a próxima linha reabre
        raise


def sheets_configurado() -> bool:
    """Há um destino: o Apps Script da planilha ou a planilha via conta de serviço."""
    return bool(
        os.getenv("SHEETS_WEBHOOK_URL", "").strip()
        or os.getenv("LATENCIA_SHEETS_ID", "").strip()
    )


def _enviar_para_apps_script(
    url: str,
    nome_aba: str,
    cabecalhos: tuple[str, ...],
    linha: tuple[object, ...],
) -> None:
    """Envia a linha ao app da web do Apps Script publicado na planilha.

    Alternativa à conta de serviço: o script roda com a conta dona da planilha,
    então não precisa do Google Cloud. O token impede que outra pessoa com o
    link grave na planilha.
    """
    if not url.startswith("https://script.google.com/"):
        raise ValueError("SHEETS_WEBHOOK_URL precisa ser o link /exec do Apps Script.")
    corpo = json.dumps(
        {
            "token": os.getenv("SHEETS_WEBHOOK_TOKEN", "").strip(),
            "aba": nome_aba,
            "cabecalhos": list(cabecalhos),
            "linha": list(linha),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    pedido = urllib.request.Request(
        url, data=corpo, headers={"Content-Type": "application/json"}, method="POST"
    )
    # O Apps Script responde com um redirecionamento; o urllib o segue. Uma
    # lentidão ou queda passageira é repetida, para a linha não se perder.
    for tentativa in range(1, _TENTATIVAS_ENVIO + 1):
        try:
            with urllib.request.urlopen(pedido, timeout=15) as resposta:
                texto = resposta.read().decode("utf-8", errors="replace")
            break
        except urllib.error.HTTPError as erro:
            if erro.code in (401, 403):
                raise ValueError(
                    f"O Apps Script pediu login (HTTP {erro.code}). Reimplante o App da "
                    "Web com 'Quem pode acessar: Qualquer pessoa' (não 'Qualquer pessoa "
                    "em <domínio>') e use o novo link /exec."
                ) from None
            if erro.code < 500 or tentativa == _TENTATIVAS_ENVIO:
                raise
        except (urllib.error.URLError, TimeoutError):
            if tentativa == _TENTATIVAS_ENVIO:
                raise
        time.sleep(0.5 * tentativa)
    try:
        resultado = json.loads(texto)
    except json.JSONDecodeError:
        raise ValueError(
            "O Apps Script não devolveu JSON. Confira se foi implantado como "
            "'App da Web' com acesso para 'Qualquer pessoa'."
        ) from None
    if not resultado.get("ok"):
        raise ValueError(f"O Apps Script recusou a linha: {resultado.get('erro')}")


def _registrar_falha_de_gravacao(futuro: Future) -> None:
    try:
        futuro.result()
    except Exception:  # noqa: BLE001 - falha no dashboard não deve parar o agente
        logger.exception("Falha ao enviar métricas para o Google Sheets.")
