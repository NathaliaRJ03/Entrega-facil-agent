"""Registra que uma reclamação real foi atendida, sem guardar o texto do cliente."""

import csv
import os
from datetime import datetime, timezone

from integrations.contratos import PASTA_SAIDA
from integrations.workspace import carregar_reclamacoes

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


def carregar_reclamacoes_pendentes() -> tuple[list[dict[str, str]], str, str]:
    """Lê apenas em memória e retorna pendências, origem e uma mensagem de erro."""
    try:
        reclamacoes, origem = carregar_reclamacoes()
    except (OSError, ValueError, KeyError):
        return [], "", "Não consegui carregar as reclamações. Solicite revisão manual."

    triados = ids_ja_atendidos()
    pendentes = [r for r in reclamacoes if r["id_reclamacao"] not in triados]
    return pendentes, origem, ""


def obter_proxima_reclamacao() -> tuple[dict[str, str] | None, str, str]:
    """Obtém a primeira pendência, sem expor as demais ao modelo."""
    pendentes, origem, erro = carregar_reclamacoes_pendentes()
    if erro:
        return None, origem, erro
    if not pendentes:
        return None, origem, ""
    return pendentes[0], origem, ""


def registrar_atendimento(
    id_reclamacao: str,
    cupom_oferecido: str = "",
) -> str:
    """Marca uma reclamação do Forms como atendida para não reaparecer na fila.

    Reconsulta os dados no backend; não confia em status, atraso ou pedido enviados
    pelo modelo. Registra somente metadados operacionais, sem relato ou contato.
    """
    reclamacao = str(id_reclamacao or "").strip()
    if not reclamacao:
        return "Informe o ID da reclamação para registrar o atendimento."

    proxima, _, erro = obter_proxima_reclamacao()
    if erro:
        return erro
    if proxima is None:
        return "Nenhuma reclamação pendente para registrar."
    if reclamacao != proxima["id_reclamacao"]:
        return "Só é possível registrar a reclamação pendente atualmente selecionada."

    # Importação local evita ciclo: consultar_dados também usa ids_ja_atendidos.
    from tools.consultar_dados import _avaliar_atraso, _consultar_pedido_verificado

    pedido, _, erro = _consultar_pedido_verificado(reclamacao)
    if erro:
        return f"O pedido não foi confirmado; atendimento não registrado. {erro}"

    atraso_calculado, _ = _avaliar_atraso(pedido)
    atraso = "nao" if atraso_calculado == "não" else atraso_calculado
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
        "id_pedido": (pedido.get("id_pedido") or "").strip(),
        "status_pedido": (pedido.get("status_pedido") or "").strip(),
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
