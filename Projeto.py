from fastapi import FastAPI, Query
import pandas as pd
import os
import logging
from datetime import datetime

from ai_service import get_client
from conf import conectar_google_sheets

from csv_pipeline import (
    gerar_csv_disciplina,
    gerar_csv_universidade,
)

from sheets_pipeline import (
    ler_sheets_para_df,
    escrever_df_no_sheets,
    processar_sheets_df,
)

from Sentimento_pipeline import executar_pipeline_sentimentos

from pipeline_completo import executar_pipeline_completo


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Projeto")

app = FastAPI(title="Resumo Geral e Sentimentos por Turma")

try:
    client_ai = get_client()
except Exception as e:
    logger.exception("Erro ao inicializar cliente de IA: %s", e)
    client_ai = None

try:
    spreadsheet = conectar_google_sheets()
except Exception as e:
    logger.exception("Erro ao conectar ao Google Sheets: %s", e)
    spreadsheet = None


def _validar_arquivo(caminho: str):
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")


def _timestamp_nome(nome_base: str) -> str:
    agora = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{nome_base}_{agora}.csv"

@app.post("/sheets/resumo_disciplina")
def sheets_resumo_disciplina(aba: str = Query(...)):
    if not spreadsheet:
        return {"status": "erro", "detalhe": "Planilha não conectada"}

    df = ler_sheets_para_df(spreadsheet, aba)
    if df.empty:
        return {"status": "erro", "detalhe": "Aba vazia ou inválida"}

    df, processados = processar_sheets_df(
        client_ai=client_ai,
        df=df,
        aba="disciplina",
    )

    escrever_df_no_sheets(spreadsheet, aba, df)

    return {
        "status": "ok",
        "turmas_processadas": processados,
        "origem": "sheets",
        "tipo": "disciplina",
    }


@app.post("/sheets/resumo_universidade")
def sheets_resumo_universidade(aba: str = Query(...)):
    if not spreadsheet:
        return {"status": "erro", "detalhe": "Planilha não conectada"}

    df = ler_sheets_para_df(spreadsheet, aba)
    if df.empty:
        return {"status": "erro", "detalhe": "Aba vazia ou inválida"}

    df, processados = processar_sheets_df(
        client_ai=client_ai,
        df=df,
        aba="universidade",
    )

    escrever_df_no_sheets(spreadsheet, aba, df)

    return {
        "status": "ok",
        "turmas_processadas": processados,
        "origem": "sheets",
        "tipo": "universidade",
    }

@app.post("/csv/resumo_disciplina")
def csv_resumo_disciplina(
    caminho_entrada: str = Query(...),
    caminho_saida: str = Query("resumo_disciplina.csv"),
):
    try:
        _validar_arquivo(caminho_entrada)

        gerar_csv_disciplina(client_ai, caminho_entrada, caminho_saida)

        return {
            "status": "ok",
            "arquivo_saida": caminho_saida,
            "tipo": "disciplina",
        }

    except Exception as e:
        logger.exception("Erro resumo disciplina CSV: %s", e)
        return {"status": "erro", "detalhe": str(e)}


@app.post("/csv/resumo_universidade")
def csv_resumo_universidade(
    caminho_entrada: str = Query(...),
    caminho_saida: str = Query("resumo_universidade.csv"),
):
    try:
        _validar_arquivo(caminho_entrada)

        gerar_csv_universidade(client_ai, caminho_entrada, caminho_saida)

        return {
            "status": "ok",
            "arquivo_saida": caminho_saida,
            "tipo": "universidade",
        }

    except Exception as e:
        logger.exception("Erro resumo universidade CSV: %s", e)
        return {"status": "erro", "detalhe": str(e)}
    
@app.post("/csv/sentimentos")
def csv_sentimentos(
    caminho_entrada: str = Query(...),
    tipo: str = Query(..., regex="^(disciplina|universidade)$"),
    caminho_saida_individual: str = Query("sentimentos_individuais.csv"),
):
    if client_ai is None:
        return {"status": "erro", "detalhe": "Cliente de IA não inicializado"}

    try:
        _validar_arquivo(caminho_entrada)

        df_final, df_stats = executar_pipeline_sentimentos(
            caminho_entrada=caminho_entrada,
            tipo=tipo,
            caminho_saida_individual=caminho_saida_individual,
            client_ai=client_ai,
        )

        total_respostas = int(
            pd.to_numeric(df_stats["total_respostas"], errors="coerce")
            .fillna(0)
            .sum()
        ) if not df_stats.empty else 0

        return {
            "status": "ok",
            "arquivo_saida": caminho_saida_individual,
            "total_respostas": total_respostas,
            "turmas": df_stats["turma"].tolist() if not df_stats.empty else [],
        }

    except Exception as e:
        logger.exception("Erro sentimentos CSV: %s", e)
        return {"status": "erro", "detalhe": str(e)}


@app.post("/csv/pipeline_completo")
def csv_pipeline_completo(
    caminho_entrada: str = Query(...),
    caminho_saida_detalhado: str = Query("detalhado.csv"),
    caminho_saida_stats: str = Query("estatisticas.csv"),
):
    if client_ai is None:
        return {"status": "erro", "detalhe": "Cliente de IA não inicializado"}

    try:
        _validar_arquivo(caminho_entrada)

        caminho_saida_detalhado = _timestamp_nome("detalhado")
        caminho_saida_stats = _timestamp_nome("estatisticas")

        df_classificado, df_stats = executar_pipeline_completo(
            caminho_entrada=caminho_entrada,
            caminho_saida_detalhado=caminho_saida_detalhado,
            caminho_saida_stats=caminho_saida_stats,
            client=client_ai,
        )

        total = int(df_stats["total"].sum()) if not df_stats.empty else 0

        return {
            "status": "ok",
            "arquivos": {
                "detalhado": caminho_saida_detalhado,
                "estatisticas": caminho_saida_stats,
            },
            "total_respostas": total,
            "turmas_processadas": df_stats["turma"].tolist() if not df_stats.empty else [],
        }

    except Exception as e:
        logger.exception("Erro pipeline completo: %s", e)
        return {"status": "erro", "detalhe": str(e)}