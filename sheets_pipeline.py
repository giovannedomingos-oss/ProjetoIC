import pandas as pd
import logging

from ai_service import (
    gerar_resumo_disciplina,
    gerar_resumo_universidade,
)
from Dicionario import construir_grupos_df


logger = logging.getLogger("sheets_pipeline")

COL_OUT = "Resumo-API-Chat"
MAX_RESPOSTAS = 50  # evita estouro de tokens



def ler_sheets_para_df(spreadsheet, aba: str) -> pd.DataFrame:
    ws = spreadsheet.worksheet(aba)
    dados = ws.get_all_values()

    if not dados:
        return pd.DataFrame()

    header = dados[0]
    linhas = dados[1:]

    df = pd.DataFrame(linhas, columns=header)
    df.columns = df.columns.str.strip()

    return df.fillna("")
def escrever_df_no_sheets(spreadsheet, aba: str, df: pd.DataFrame) -> None:
    ws = spreadsheet.worksheet(aba)

    dados = [df.columns.tolist()] + df.values.tolist()

    ws.clear()
    ws.update(dados)


def _limitar_respostas(respostas: list[str]) -> list[str]:
    """Evita excesso de tokens"""
    return respostas[:MAX_RESPOSTAS]


def _limpar_texto(texto: str) -> str:
    return texto.replace("\n", " ").replace("\r", " ").strip()


def processar_sheets_df(
    client_ai,
    df: pd.DataFrame,
    aba: str,
) -> tuple[pd.DataFrame, int]:

    if df.empty:
        return df, 0

    df.columns = df.columns.str.strip()

    if COL_OUT not in df.columns:
        df[COL_OUT] = ""

    if aba.lower() == "universidade":
        funcao_resumo = gerar_resumo_universidade
    else:
        funcao_resumo = gerar_resumo_disciplina

    grupos = construir_grupos_df(df)

    if not grupos:
        logger.warning("Nenhum grupo encontrado no dicionário")
        return df, 0

    processados = 0

    for chave, dados in grupos.items():
        respostas = dados.get("respostas", [])
        linha_chave = dados.get("linha_chave")

        if not respostas or linha_chave is None:
            continue

        linha_resumo = linha_chave + 1

        if linha_resumo >= len(df):
            nova_linha = {col: "" for col in df.columns}
            df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)

        valor_atual = str(df.loc[linha_resumo, COL_OUT]).strip()
        if valor_atual:
            continue

        respostas_validas = [
            r.strip() for r in respostas if isinstance(r, str) and r.strip()
        ]

        respostas_validas = _limitar_respostas(respostas_validas)

        if not respostas_validas:
            continue

        texto_base = "\n".join(respostas_validas)

        try:
            resumo = funcao_resumo(client_ai, texto_base)

            if resumo:
                df.loc[linha_resumo, COL_OUT] = _limpar_texto(resumo)
                processados += 1

        except Exception as e:
            logger.error(f"Erro ao gerar resumo para {chave}: {e}")
            df.loc[linha_resumo, COL_OUT] = "Erro ao gerar resumo"

    logger.info(f"{processados} turmas processadas")

    return df, processados