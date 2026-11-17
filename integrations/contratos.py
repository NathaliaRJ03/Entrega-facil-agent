"""Contratos de dados: o que cada pessoa da equipe entrega para o agente.

Cada contrato define as colunas canônicas que o agente usa e os nomes
alternativos aceitos (ex.: o título da pergunta no Google Forms). Assim a
equipe pode entregar o arquivo com o cabeçalho que for mais natural, desde
que ele bata com algum apelido. Ver docs/CONTRATOS_DE_DADOS.md.

Ordem de busca dos arquivos:
1. data/entrada/<arquivo>   -> dados reais da equipe (fora do Git, LGPD)
2. data/amostras/<arquivo>  -> amostra sintética para o agente rodar sem eles
"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

PASTA_PROJETO = Path(__file__).resolve().parent.parent
PASTA_ENTRADA = PASTA_PROJETO / "data" / "entrada"
PASTA_AMOSTRAS = PASTA_PROJETO / "data" / "amostras"
PASTA_SAIDA = PASTA_PROJETO / "data" / "saida"


def normalizar_coluna(nome: str) -> str:
    """'Número do pedido' -> 'numero_do_pedido'."""
    nome = unicodedata.normalize("NFD", str(nome).strip().lower())
    nome = "".join(c for c in nome if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", nome).strip("_")


@dataclass(frozen=True)
class Contrato:
    nome: str
    responsavel: str
    arquivo: str
    colunas: dict[str, tuple[str, ...]]
    obrigatorias: tuple[str, ...] = field(default=())

    def resolver_coluna(self, canonica: str, nomes: list[str]) -> str | None:
        """Localiza o cabeçalho original correspondente a uma coluna canônica."""
        recebidas = {normalizar_coluna(nome): nome for nome in nomes}
        for opcao in (canonica, *self.colunas.get(canonica, ())):
            original = recebidas.get(normalizar_coluna(opcao))
            if original is not None:
                return original
        return None

    def localizar_arquivo(self) -> tuple[Path | None, bool]:
        """Retorna (caminho, eh_amostra). Prefere os dados reais da equipe."""
        real = PASTA_ENTRADA / self.arquivo
        if real.exists():
            return real, False
        amostra = PASTA_AMOSTRAS / self.arquivo
        if amostra.exists():
            return amostra, True
        return None, False

    def padronizar(self, linhas: list[dict], origem: str) -> list[dict[str, str]]:
        """Renomeia as colunas para os nomes canônicos e valida as obrigatórias."""
        if not linhas:
            return []

        mapa: dict[str, str] = {}
        nomes = list(linhas[0].keys())
        for canonica in self.colunas:
            original = self.resolver_coluna(canonica, nomes)
            if original is not None:
                mapa[canonica] = original

        faltando = [c for c in self.obrigatorias if c not in mapa]
        if faltando:
            raise ValueError(
                f"{origem}: faltam as colunas {faltando} do contrato "
                f"'{self.nome}' (responsável: {self.responsavel}). "
                f"Colunas recebidas: {list(linhas[0].keys())}"
            )

        padronizadas = []
        for linha in linhas:
            registro = {c: "" for c in self.colunas}
            for canonica, original in mapa.items():
                valor = linha.get(original)
                registro[canonica] = "" if valor is None else str(valor).strip()
            padronizadas.append(registro)
        return padronizadas


def ler_csv(caminho: Path) -> list[dict[str, str]]:
    """Lê CSV com vírgula ou ponto e vírgula (Excel em português usa ';')."""
    return ler_csv_texto(caminho.read_text(encoding="utf-8-sig"))


def ler_csv_texto(texto: str) -> list[dict[str, str]]:
    """Mesmo que ler_csv, mas a partir do conteúdo (ex.: baixado de uma URL)."""
    texto = texto.lstrip("﻿")
    try:
        dialeto = csv.Sniffer().sniff(texto[:4096], delimiters=",;\t")
    except csv.Error:
        dialeto = csv.excel
    return list(csv.DictReader(io.StringIO(texto, newline=""), dialect=dialeto))


# --- Victor (NOC): respostas do Google Forms de reclamações -----------------
RECLAMACOES = Contrato(
    nome="reclamacoes_forms",
    responsavel="Victor (NOC)",
    arquivo="reclamacoes_forms.csv",
    colunas={
        "id_reclamacao": ("id", "protocolo", "numero_protocolo"),
        "id_pedido": ("id do pedido", "pedido", "número do pedido", "numero do pedido"),
        "nome_cliente": ("nome", "nome completo", "nome do cliente"),
        "data_envio": ("carimbo de data/hora", "timestamp", "data_hora", "data"),
        "tipo_contestacao": ("tipo de contestação", "tipo de contestacao",
                             "tipo de reclamação", "motivo"),
        "relato": ("descreva oque aconteceu", "descreva o que aconteceu",
                   "descreva o problema", "descrição", "descricao", "reclamação",
                   "reclamacao", "mensagem"),
        "data_compra": ("informe quando a compra foi realizada", "data da compra",
                        "quando a compra foi realizada"),
        "codigo_transacao": ("código da transação", "codigo da transacao",
                             "id da transação"),
        "valor_pedido": ("valor do pedido", "valor da compra", "valor"),
        "email_contato": ("e-mail de contato", "email de contato", "e-mail", "email"),
    },
    obrigatorias=("relato", "id_pedido", "nome_cliente"),
)

# --- Rebeca (Eng. de Dados): histórico Gold sintético de pedidos -------------
# Os cabeçalhos entregues pela engenharia de dados já devem estar traduzidos.
PEDIDOS = Contrato(
    nome="gold_pedidos",
    responsavel="Rebeca (Eng. de Dados)",
    arquivo="gold_pedidos.csv",
    colunas={
        "id_pedido": ("id do pedido", "número do pedido", "numero do pedido", "pedido"),
        "nome_cliente": ("nome", "nome completo", "nome do cliente"),
        "status_pedido": ("status do pedido", "status"),
        "data_pedido": ("data do pedido",),
        "data_prevista_entrega": (
            "previsão de entrega", "previsao de entrega", "data prevista de entrega",
            "prazo de entrega",
        ),
        "data_entrega": (
            "data de entrega", "data da entrega", "entrega realizada em",
        ),
        "dias_atraso": ("dias de atraso", "atraso em dias"),
        "status_entrega": ("status da entrega",),
        "descricao_pedido": ("descrição do pedido", "descricao do pedido", "produto"),
    },
    obrigatorias=("id_pedido", "nome_cliente"),
)
