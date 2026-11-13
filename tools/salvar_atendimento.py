"""Registra que uma reclamação real foi atendida, sem guardar o texto do cliente."""

import csv
import os
from datetime import datetime, timezone

from integrations.contratos import PASTA_SAIDA, normalizar_coluna

ARQUIVO_ATENDIMENTOS = PASTA_SAIDA / "atendimentos.csv"
COLUNAS = (
    "id_reclamacao", "data_atendimento", "id_pedido", "status_pedido",
    "atraso_confirmado", "cupom_oferecido",
)


def ids_ja_atendidos() -> set[str]:
    if not ARQUIVO_ATENDIMENTOS.exists():
        return set()
    with ARQUIVO_ATENDIMENTOS.open(encoding="utf-8-sig", newline="") as arquivo:
        return {
            linha.get("id_reclamacao", "").strip()
            for linha in csv.DictReader(arquivo)
            if linha.get("id_reclamacao", "").strip()
        }


def registrar_atendimento(
    id_reclamacao: str,
    id_pedido: str,
    status_pedido: str,
    atraso_confirmado: str,
    cupom_oferecido: str = "",
) -> str:
    """Marca uma reclamação do Forms como atendida para não reaparecer na fila.

    Registra somente metadados operacionais; não armazena relato, nome ou e-mail.
    """
    reclamacao = (id_reclamacao or "").strip()
    if not reclamacao:
        return "Informe o ID da reclamação para registrar o atendimento."
    if reclamacao in ids_ja_atendidos():
        return f"A reclamação {reclamacao} já consta como atendida."

    atraso = normalizar_coluna(atraso_confirmado)
    if atraso not in {"sim", "nao", "indeterminado"}:
        return "Use sim, não ou indeterminado em atraso_confirmado."
    cupom = (cupom_oferecido or "").strip()
    if cupom and (
        atraso != "sim"
        or cupom != os.getenv("CUPOM_ATRASO_CODIGO", "").strip()
        or not os.getenv("CUPOM_ATRASO_DESCONTO", "").strip()
    ):
        return "O cupom não corresponde à campanha configurada ou o atraso não foi confirmado."

    registro = {
        "id_reclamacao": reclamacao,
        "data_atendimento": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "id_pedido": (id_pedido or "").strip(),
        "status_pedido": (status_pedido or "").strip(),
        "atraso_confirmado": atraso,
        "cupom_oferecido": cupom,
    }

    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    novo = not ARQUIVO_ATENDIMENTOS.exists()
    with ARQUIVO_ATENDIMENTOS.open(
        "a", encoding="utf-8-sig" if novo else "utf-8", newline=""
    ) as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS)
        if novo:
            escritor.writeheader()
        escritor.writerow(registro)
    return f"Atendimento registrado para {reclamacao}."
