"""Lê as reclamações do Google Forms (via planilha de respostas no Sheets).

Três modos (o primeiro configurado vence):
- Link CSV em FORMS_CSV_URL. Preferido (tempo real), com a planilha
  compartilhada como "qualquer pessoa com o link: Leitor":
    https://docs.google.com/spreadsheets/d/<ID>/export?format=csv&gid=<GID>
  O link de "Publicar na Web" (.../pub?output=csv) também funciona, mas o
  Google só o atualiza a cada ~5 min.
- Planilha (Google Sheets API): defina FORMS_SHEET_ID e
  GOOGLE_SERVICE_ACCOUNT_FILE no .env e compartilhe a planilha com o e-mail
  da service account (somente leitura).
- Arquivo: o Victor exporta as respostas para data/entrada/reclamacoes_forms.csv.
  Sem nenhum dos dois, usa data/amostras/reclamacoes_forms.csv.
"""

import os
import re
import urllib.request

from .contratos import RECLAMACOES, ler_csv, ler_csv_texto


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


def carregar_reclamacoes() -> tuple[list[dict[str, str]], str]:
    """Retorna (reclamações padronizadas, descrição da origem)."""
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
    if sheet_id and not aviso:
        try:
            linhas = _ler_planilha(sheet_id)
            registros = RECLAMACOES.padronizar(linhas, "Google Sheets (Forms)")
            return _completar_ids(registros), "Google Sheets (respostas do Forms)"
        except Exception as erro:  # noqa: BLE001 - mostrar o motivo na demo
            aviso = f" [falha ao ler o Google Sheets: {erro}]"

    caminho, eh_amostra = RECLAMACOES.localizar_arquivo()
    if caminho is None:
        return [], "nenhuma fonte de reclamações encontrada" + aviso

    registros = RECLAMACOES.padronizar(ler_csv(caminho), caminho.name)
    origem = ("AMOSTRA SINTÉTICA " if eh_amostra else "") + f"arquivo {caminho.name}"
    return _completar_ids(registros), origem + aviso


def _data_iso(valor: str) -> str:
    """'12/11/2026 15:05:00' (Sheets em PT-BR) -> '2026-11-12 15:05:00'."""
    achado = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})(.*)", valor.strip())
    if not achado:
        return valor
    dia, mes, ano, resto = achado.groups()
    return f"{ano}-{int(mes):02d}-{int(dia):02d}{resto}"


def _completar_ids(registros: list[dict[str, str]]) -> list[dict[str, str]]:
    """O Forms não gera ID: usa a posição da resposta (estável, só cresce)."""
    for numero, registro in enumerate(registros, start=1):
        if not registro["id_reclamacao"]:
            registro["id_reclamacao"] = f"FORM-{numero:04d}"
        registro["data_envio"] = _data_iso(registro["data_envio"])
        registro["data_compra"] = _data_iso(registro["data_compra"])
    return registros
