"""Lê as reclamações do Google Forms (via planilha de respostas no Sheets).

Somente as respostas reais do Forms, em dois modos (nesta ordem):
- Link CSV em FORMS_CSV_URL. Preferido (tempo real), com a planilha
  compartilhada como "qualquer pessoa com o link: Leitor":
    https://docs.google.com/spreadsheets/d/<ID>/export?format=csv&gid=<GID>
  O link de "Publicar na Web" (.../pub?output=csv) também funciona, mas o
  Google só o atualiza a cada ~5 min.
- Planilha (Google Sheets API): defina FORMS_SHEET_ID e
  GOOGLE_SERVICE_ACCOUNT_FILE no .env e compartilhe a planilha com o e-mail
  da service account (somente leitura).
Não há reserva em arquivo local nem amostra sintética.
"""

import os
import re
import time
import urllib.request

from .contratos import RECLAMACOES, ler_csv_texto


def _ler_url_csv(url: str) -> list[dict]:
    """Baixa a planilha publicada na Web (Arquivo > Compartilhar > Publicar na Web)."""
    if not url.startswith("https://docs.google.com/"):
        raise ValueError("FORMS_CSV_URL precisa ser um link https://docs.google.com/...")
    with urllib.request.urlopen(url, timeout=15) as resposta:
        texto = resposta.read().decode("utf-8")
    if texto.lstrip().startswith("<"):
        raise ValueError("o link devolveu uma página, não CSV. Publique em formato CSV.")
    return ler_csv_texto(texto)


def _ler_planilha(sheet_id: str) -> list[dict]:
    import gspread  # dependência opcional: pip install gspread

    credenciais = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
    cliente = gspread.service_account(filename=credenciais)
    planilha = cliente.open_by_key(sheet_id)
    aba = os.getenv("FORMS_SHEET_ABA")
    folha = planilha.worksheet(aba) if aba else planilha.sheet1
    return folha.get_all_records()


_CACHE: dict = {"quando": 0.0, "valor": None}
_VALIDADE_CACHE_S = 20.0


def carregar_reclamacoes(forcar: bool = False) -> tuple[list[dict[str, str]], str]:
    """Retorna (reclamações, origem), reaproveitando a leitura por poucos segundos.

    Cada ferramenta do agente consulta a fila; sem cache, cada uma baixaria a
    planilha de novo. Use forcar=True quando precisar enxergar envios novos.
    """
    agora = time.monotonic()
    if not forcar and _CACHE["valor"] is not None and agora - _CACHE["quando"] < _VALIDADE_CACHE_S:
        return _CACHE["valor"]
    resultado = _carregar_reclamacoes()
    if resultado[0]:
        _CACHE["quando"], _CACHE["valor"] = agora, resultado
    return resultado


def _carregar_reclamacoes() -> tuple[list[dict[str, str]], str]:
    """Lê a planilha (sem cache)."""
    aviso = ""
    url_csv = os.getenv("FORMS_CSV_URL", "").strip()
    if url_csv:
        try:
            linhas = _ler_url_csv(url_csv)
            registros = RECLAMACOES.padronizar(linhas, "planilha publicada (CSV)")
            return _completar_ids(registros), "Google Sheets em tempo real (respostas do Forms)"
        except Exception as erro:  # noqa: BLE001 - mostrar o motivo na demo
            aviso = f" [falha ao ler a planilha publicada: {erro}]"

    sheet_id = os.getenv("FORMS_SHEET_ID", "").strip()
    if sheet_id:
        try:
            linhas = _ler_planilha(sheet_id)
            registros = RECLAMACOES.padronizar(linhas, "Google Sheets (Forms)")
            return _completar_ids(registros), "Google Sheets (respostas do Forms)"
        except Exception as erro:  # noqa: BLE001 - mostrar o motivo na demo
            aviso += f" [falha ao ler o Google Sheets: {erro}]"

    # Sem reserva: o agente nunca lê CSV local nem amostra sintética.
    return [], "Forms indisponível (configure FORMS_CSV_URL ou FORMS_SHEET_ID)" + aviso


def _data_iso(valor: str) -> str:
    """'12/11/2026 15:05:00' (Sheets em PT-BR) -> '2026-11-12 15:05:00'."""
    achado = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})(.*)", valor.strip())
    if not achado:
        return valor
    dia, mes, ano, resto = achado.groups()
    return f"{ano}-{int(mes):02d}-{int(dia):02d}{resto}"


def _completar_ids(registros: list[dict[str, str]]) -> list[dict[str, str]]:
    """O Forms não gera ID: usa o carimbo de data/hora da resposta.

    Como as respostas são apagadas depois do atendimento, a posição na planilha
    não serve de ID (ela se repetiria). O carimbo é único por envio.
    """
    usados: set[str] = set()
    for numero, registro in enumerate(registros, start=1):
        if not registro["id_reclamacao"]:
            digitos = re.sub(r"\D", "", registro["data_envio"])
            base = f"FORM-{digitos}" if digitos else f"FORM-{numero:04d}"
            novo, sufixo = base, 1
            while novo in usados:
                sufixo += 1
                novo = f"{base}-{sufixo}"
            registro["id_reclamacao"] = novo
        usados.add(registro["id_reclamacao"])
        registro["data_envio"] = _data_iso(registro["data_envio"])
        registro["data_compra"] = _data_iso(registro["data_compra"])
    return registros


def _aba_das_respostas(planilha):
    aba = os.getenv("FORMS_SHEET_ABA")
    if aba:
        return planilha.worksheet(aba)
    gid = re.search(r"gid=(\d+)", os.getenv("FORMS_CSV_URL", ""))
    return planilha.get_worksheet_by_id(int(gid.group(1))) if gid else planilha.sheet1


def excluir_resposta(data_envio: str) -> str:
    """Apaga da planilha a resposta do Forms enviada em `data_envio` (ISO).

    Exige a service account com permissão de Editor na planilha. Só apaga se
    houver exatamente uma linha com esse carimbo. Retorna "" se apagou, ou o
    motivo de não ter apagado.
    """
    sheet_id = os.getenv("FORMS_SHEET_ID", "").strip()
    if not sheet_id or not data_envio:
        return "FORMS_SHEET_ID ou carimbo da resposta ausente."
    try:
        import gspread

        credenciais = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
        folha = _aba_das_respostas(gspread.service_account(filename=credenciais).open_by_key(sheet_id))
        carimbos = folha.col_values(1)
        linhas = [n for n, valor in enumerate(carimbos, start=1) if n > 1 and _data_iso(valor) == data_envio]
        if len(linhas) != 1:
            return f"esperava 1 linha com o carimbo {data_envio}, achei {len(linhas)}."
        folha.delete_rows(linhas[0])
        return ""
    except Exception as erro:  # noqa: BLE001 - não derrubar o atendimento
        return f"falha ao apagar a resposta: {type(erro).__name__}"
