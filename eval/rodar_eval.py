"""Executa avaliações locais com casos sintéticos, sem chamar o modelo.

Uso, a partir da raiz do projeto:
    python eval/rodar_eval.py
"""

import csv
import json
import os
import sys
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_PROJETO))

from agente_triagem import rag_lexical  # noqa: E402
from agente_triagem.rag_lexical import carregar_documentos  # noqa: E402
from integrations import latencia_sheets  # noqa: E402
from retriever.bm25 import BuscaBM25  # noqa: E402
from tools import consultar_dados, salvar_atendimento  # noqa: E402


PASTA_EVAL = Path(__file__).resolve().parent


def carregar_json(nome: str) -> dict:
    caminho = PASTA_EVAL / nome
    return json.loads(caminho.read_text(encoding="utf-8"))


def faltantes(texto: str, termos: list[str]) -> list[str]:
    texto_normalizado = texto.casefold()
    return [termo for termo in termos if termo.casefold() not in texto_normalizado]


def inesperados(texto: str, termos: list[str]) -> list[str]:
    texto_normalizado = texto.casefold()
    return [termo for termo in termos if termo.casefold() in texto_normalizado]


def avaliar_atendimento() -> tuple[int, int]:
    dados = carregar_json("casos_atendimento.json")
    casos = dados["casos"]
    aprovados = 0

    for caso in casos:
        reclamacao = caso["reclamacao"]
        chamadas_pedido = 0

        def obter_proxima(r=reclamacao):
            return r, "Forms sintético de avaliação", ""

        def carregar_pendentes(r=reclamacao):
            outra = {
                "id_reclamacao": "EVAL-OCULTO",
                "id_pedido": "PED-EVAL-OCULTO",
                "nome_cliente": "Segredo Oculto",
                "relato": "Conteúdo da próxima reclamação não deve ser exibido.",
            }
            return [r, outra], "Forms sintético de avaliação", ""

        def carregar_pedido(_contrato, _id, c=caso):
            nonlocal chamadas_pedido
            chamadas_pedido += 1
            return c["pedidos"], "Gold sintética de avaliação"

        with (
            patch.object(
                consultar_dados,
                "obter_proxima_reclamacao",
                side_effect=obter_proxima,
            ),
            patch.object(
                consultar_dados,
                "carregar_reclamacoes_pendentes",
                side_effect=carregar_pendentes,
            ),
            patch.object(
                consultar_dados,
                "carregar_pedido",
                side_effect=carregar_pedido,
            ),
            patch.dict(
                os.environ,
                {
                    "CUPOM_ATRASO_CODIGO": caso["cupom"]["codigo"],
                    "CUPOM_ATRASO_DESCONTO": caso["cupom"]["desconto"],
                },
            ),
        ):
            resultado_fila = consultar_dados.listar_reclamacoes_pendentes()
            resultado_relato = consultar_dados.obter_reclamacao_pendente(
                reclamacao["id_reclamacao"]
            )
            resultado_fora_fila = consultar_dados.obter_reclamacao_pendente(
                "EVAL-OCULTO"
            )
            resultado_id_invalido = consultar_dados.obter_reclamacao_pendente(
                "../EVAL"
            )
            resultado_consulta = consultar_dados.consultar_pedido(
                reclamacao["id_reclamacao"]
            )
            resultado_cupom = consultar_dados.oferecer_cupom_atraso(
                reclamacao["id_reclamacao"]
            )

        nome = reclamacao.get("nome_cliente", "")
        id_pedido = reclamacao.get("id_pedido", "")
        erros = []
        if "Total pendente: 2" not in resultado_fila:
            erros.append("fila não informa corretamente a quantidade pendente")
        erros += [
            f"fila não mostra o ID da reclamação: {reclamacao['id_reclamacao']}"
        ] if reclamacao["id_reclamacao"].casefold() not in resultado_fila.casefold() else []
        erros += [
            f"fila expôs dado que deveria permanecer oculto: {termo}"
            for termo in (
                nome,
                id_pedido,
                reclamacao.get("relato", ""),
                "EVAL-OCULTO",
                "PED-EVAL-OCULTO",
                "Segredo Oculto",
                "Conteúdo da próxima reclamação",
            )
            if termo and termo.casefold() in resultado_fila.casefold()
        ]
        if "Só é possível consultar a próxima reclamação pendente" not in resultado_fora_fila:
            erros.append("a ferramenta permitiu consultar outra reclamação da fila")
        if "identificador da reclamação é inválido" not in resultado_id_invalido:
            erros.append("a ferramenta não rejeitou um ID de reclamação inválido")
        erros += [
            f"relato redigido não contém: {termo}"
            for termo in faltantes(resultado_relato, caso.get("relato_contem", []))
        ]
        erros += [
            f"relato redigido expôs: {termo}"
            for termo in inesperados(resultado_relato, caso.get("relato_nao_contem", []))
        ]
        erros += [
            f"consulta não contém: {termo}"
            for termo in faltantes(resultado_consulta, caso.get("consulta_contem", []))
        ]
        erros += [
            f"consulta expôs conteúdo que deveria faltar: {termo}"
            for termo in inesperados(
                resultado_consulta,
                [nome, id_pedido, *caso.get("consulta_nao_contem", [])],
            )
            if termo
        ]
        erros += [
            f"resposta do cupom não contém: {termo}"
            for termo in faltantes(resultado_cupom, caso.get("cupom_contem", []))
        ]
        erros += [
            f"resposta do cupom contém conteúdo proibido: {termo}"
            for termo in inesperados(
                resultado_cupom,
                [nome, id_pedido, *caso.get("cupom_nao_contem", [])],
            )
            if termo
        ]

        chamadas_esperadas = caso.get("carregamentos_pedido_esperados")
        if chamadas_esperadas is not None and chamadas_pedido != chamadas_esperadas:
            erros.append(
                "número de consultas à Gold diferente do esperado: "
                f"{chamadas_pedido} != {chamadas_esperadas}"
            )

        passou = not erros
        aprovados += int(passou)
        print(f"[{'APROVADO' if passou else 'REPROVADO'}] atendimento / {caso['id']}")
        for erro in erros:
            print(f"  {erro}")

    return aprovados, len(casos)


def avaliar_registro() -> tuple[int, int]:
    casos = carregar_json("casos_atendimento.json").get("casos_registro", [])
    aprovados = 0

    for caso in casos:
        reclamacao = caso["reclamacao"]
        id_registrar = caso.get("id_registrar", reclamacao["id_reclamacao"])

        def obter_proxima(r=reclamacao):
            return r, "Forms sintético de avaliação", ""

        def carregar_pedido(_contrato, _id, c=caso):
            return c["pedidos"], "Gold sintética de avaliação"

        with TemporaryDirectory(prefix="pagfacil-eval-") as pasta_temporaria:
            arquivo = Path(pasta_temporaria) / "atendimentos.csv"
            with (
                patch.object(salvar_atendimento, "ARQUIVO_ATENDIMENTOS", arquivo),
                patch.object(
                    salvar_atendimento,
                    "obter_proxima_reclamacao",
                    side_effect=obter_proxima,
                ),
                patch.object(
                    consultar_dados,
                    "obter_proxima_reclamacao",
                    side_effect=obter_proxima,
                ),
                patch.object(
                    consultar_dados,
                    "carregar_pedido",
                    side_effect=carregar_pedido,
                ),
                patch.dict(
                    os.environ,
                    {
                        "CUPOM_ATRASO_CODIGO": caso["cupom"]["codigo"],
                        "CUPOM_ATRASO_DESCONTO": caso["cupom"]["desconto"],
                    },
                ),
            ):
                resultado = salvar_atendimento.registrar_atendimento(
                    id_registrar,
                    caso.get("cupom_oferecido", ""),
                )

            conteudo_arquivo = (
                arquivo.read_text(encoding="utf-8-sig") if arquivo.exists() else ""
            )
            erros = [
                f"resposta não contém: {termo}"
                for termo in faltantes(resultado, caso.get("resultado_contem", []))
            ]
            erros += [
                f"resposta contém conteúdo proibido: {termo}"
                for termo in inesperados(resultado, caso.get("resultado_nao_contem", []))
            ]
            erros += [
                f"arquivo de registro não contém: {termo}"
                for termo in faltantes(conteudo_arquivo, caso.get("arquivo_contem", []))
            ]
            erros += [
                f"arquivo de registro contém conteúdo proibido: {termo}"
                for termo in inesperados(conteudo_arquivo, caso.get("arquivo_nao_contem", []))
            ]

            if caso.get("arquivo_contem") and arquivo.exists():
                with arquivo.open(encoding="utf-8-sig", newline="") as entrada:
                    linhas = list(csv.DictReader(entrada))
                if len(linhas) != 1:
                    erros.append(f"esperava uma linha no CSV, encontrei {len(linhas)}")

        passou = not erros
        aprovados += int(passou)
        print(f"[{'APROVADO' if passou else 'REPROVADO'}] registro / {caso['id']}")
        for erro in erros:
            print(f"  {erro}")

    return aprovados, len(casos)


def avaliar_latencia() -> tuple[int, int]:
    casos = carregar_json("casos_latencia.json")["casos"]
    aprovados = 0

    class ExecutorCaptura:
        def __init__(self):
            self.envios = []

        def submit(self, funcao, linha):
            self.envios.append((funcao, linha))
            futuro = Future()
            futuro.set_result(None)
            return futuro

    for caso in casos:
        contexto = SimpleNamespace(
            state={},
            invocation_id=caso["id_invocacao"],
            agent_name=caso["agente"],
        )
        executor = ExecutorCaptura()
        with (
            patch.object(latencia_sheets, "_EXECUTOR", executor),
            patch.dict(
                os.environ,
                {
                    "LATENCIA_SHEETS_ID": (
                        "planilha-sintetica"
                        if caso["status"] == "sucesso"
                        else ""
                    )
                },
            ),
        ):
            latencia_sheets.iniciar_medicao_latencia(contexto)
            latencia_sheets.finalizar_medicao_latencia(contexto)

        erros = []
        if not isinstance(contexto.state.get(latencia_sheets.CHAVE_INICIO_NS), int):
            erros.append("a hora monotônica de início não foi registrada")
        if not isinstance(contexto.state.get(latencia_sheets.CHAVE_INICIO_UTC), str):
            erros.append("o início em UTC não foi registrado")

        if caso["status"] == "sucesso":
            if len(executor.envios) != 1:
                erros.append(f"esperava um envio agendado; encontrei {len(executor.envios)}")
            else:
                linha = executor.envios[0][1]
                if len(linha) != len(latencia_sheets.CABECALHOS):
                    erros.append("a linha não corresponde aos cabeçalhos configurados")
                else:
                    registro = dict(zip(latencia_sheets.CABECALHOS, linha))
                    if registro.get("id_invocacao") != caso["id_invocacao"]:
                        erros.append("ID da invocação incorreto")
                    if registro.get("agente") != caso["agente"]:
                        erros.append("nome do agente incorreto")
                    if registro.get("status") != "sucesso":
                        erros.append("status da medição incorreto")
                    try:
                        inicio = datetime.fromisoformat(registro["inicio_utc"])
                        fim = datetime.fromisoformat(registro["fim_utc"])
                        resposta = datetime.fromisoformat(registro["horario_resposta"])
                        latencia_ms = float(registro["latencia_ms"])
                        if not all(
                            instante.tzinfo is not None
                            for instante in (inicio, fim, resposta)
                        ):
                            erros.append("um horário não inclui fuso horário")
                        resposta_local_esperada = fim.astimezone(
                            ZoneInfo("America/Sao_Paulo")
                        ).replace(microsecond=0)
                        if (
                            resposta.utcoffset() != resposta_local_esperada.utcoffset()
                            or resposta.replace(tzinfo=None)
                            != resposta_local_esperada.replace(tzinfo=None)
                        ):
                            erros.append(
                                "horário da resposta não está convertido para São Paulo"
                            )
                        if latencia_ms < 0:
                            erros.append("a latência não pode ser negativa")
                    except (KeyError, TypeError, ValueError):
                        erros.append("horários ou latência têm formato inválido")
        elif executor.envios:
            erros.append("houve tentativa de envio sem planilha configurada")

        passou = not erros
        aprovados += int(passou)
        print(f"[{'APROVADO' if passou else 'REPROVADO'}] latência / {caso['id']}")
        for erro in erros:
            print(f"  {erro}")

    return aprovados, len(casos)


def avaliar_busca() -> tuple[int, int]:
    dados = carregar_json("casos_busca.json")
    busca = BuscaBM25(carregar_documentos())
    limite = int(dados.get("top_k", 3))
    casos = dados["casos"]
    aprovados = 0

    for caso in casos:
        resultados = busca.buscar(caso["consulta"], limite=limite)
        fontes = [
            str(resultado["fonte"]).replace("\\", "/")
            for resultado in resultados
        ]
        correcoes = resultados[0].get("termos_corrigidos", {}) if resultados else {}
        fonte_esperada = caso["fonte_esperada"].replace("\\", "/")
        posicao_obtida = (
            fontes.index(fonte_esperada) + 1 if fonte_esperada in fontes else None
        )
        posicao_esperada = int(caso.get("posicao_esperada", 1))
        fonte_correta = posicao_obtida == posicao_esperada
        correcoes_corretas = all(
            correcoes.get(original) == corrigido
            for original, corrigido in caso.get("correcoes_esperadas", {}).items()
        )
        resultado_esperado = next(
            (
                resultado
                for resultado in resultados
                if str(resultado["fonte"]).replace("\\", "/") == fonte_esperada
            ),
            None,
        )
        texto_esperado = str(resultado_esperado["texto"]) if resultado_esperado else ""
        trechos_presentes = not faltantes(
            texto_esperado, caso.get("texto_contem", [])
        )
        trechos_ausentes = not inesperados(
            texto_esperado, caso.get("texto_nao_contem", [])
        )
        passou = (
            fonte_correta
            and correcoes_corretas
            and trechos_presentes
            and trechos_ausentes
        )
        aprovados += int(passou)
        status = "APROVADO" if passou else "REPROVADO"
        print(
            f"[{status}] busca / {caso['id']} "
            f"(posição {posicao_obtida or 'sem resultado'}, esperada {posicao_esperada})"
        )
        if not fonte_correta:
            print(f"  Fonte esperada: {fonte_esperada}")
            print(f"  Fontes encontradas: {fontes or 'nenhuma'}")
        if not correcoes_corretas:
            print(f"  Correções encontradas: {correcoes}")
        if not trechos_presentes:
            print(
                "  Trechos ausentes na seção esperada: "
                f"{faltantes(texto_esperado, caso.get('texto_contem', []))}"
            )
        if not trechos_ausentes:
            print(
                "  Trechos proibidos na seção esperada: "
                f"{inesperados(texto_esperado, caso.get('texto_nao_contem', []))}"
            )

    caso_privacidade = dados["caso_privacidade"]
    consultas_capturadas = []

    class BuscaCaptura:
        documentos = [{"texto": "Orientação sintética para o eval."}]

        def buscar(self, consulta, limite=3):
            consultas_capturadas.append(consulta)
            return [
                {
                    "fonte": "eval sintético",
                    "texto": self.documentos[0]["texto"],
                    "termos_corrigidos": {},
                }
            ][:limite]

    with patch.object(rag_lexical, "criar_busca", return_value=BuscaCaptura()):
        resultado = rag_lexical.buscar_documentos_apoio(caso_privacidade["consulta"])

    consulta_segura = consultas_capturadas[0] if consultas_capturadas else ""
    erros_privacidade = [
        f"consulta segura não contém marcador: {termo}"
        for termo in faltantes(consulta_segura, caso_privacidade.get("contem", []))
    ]
    erros_privacidade += [
        f"consulta segura preservou dado sensível: {termo}"
        for termo in inesperados(consulta_segura, caso_privacidade.get("nao_contem", []))
    ]
    if "Orientação sintética" not in resultado:
        erros_privacidade.append("a busca não devolveu o resultado sintético esperado")
    passou_privacidade = not erros_privacidade
    aprovados += int(passou_privacidade)
    print(
        f"[{'APROVADO' if passou_privacidade else 'REPROVADO'}] "
        f"busca / {caso_privacidade['id']}"
    )
    for erro in erros_privacidade:
        print(f"  {erro}")

    return aprovados, len(casos) + 1


def main() -> int:
    total_aprovados = 0
    total_casos = 0
    print("Avaliação local do projeto (dados sintéticos; sem chamada ao modelo)\n")

    for nome, avaliador in (
        ("Fila, privacidade, segurança e regras de atendimento", avaliar_atendimento),
        ("Registro recalculado e minimizado", avaliar_registro),
        ("Medição de latência sem serviço externo", avaliar_latencia),
        ("Busca BM25 e correção de digitação", avaliar_busca),
    ):
        print(f"\n{nome}")
        aprovados, total = avaliador()
        total_aprovados += aprovados
        total_casos += total
        print(f"Resultado: {aprovados}/{total} casos aprovados")

    print(f"\nTotal: {total_aprovados}/{total_casos} casos aprovados")
    return 0 if total_aprovados == total_casos else 1


if __name__ == "__main__":
    raise SystemExit(main())
