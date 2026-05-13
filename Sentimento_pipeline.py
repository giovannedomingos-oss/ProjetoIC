import re
import logging
from typing import Tuple, Optional

import pandas as pd
from ai_service import get_client, classificar_sentimento_individual


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sentimento_pipeline")

COL_ID = "Identificação"
COL_RESP = "Resposta"

ROTULOS_VALIDOS = ["Positiva", "Negativa", "Neutra", "Misto"]


def eh_identificacao_turma(texto: str) -> bool:
    if not texto:
        return False
    texto = texto.strip()
    padrao = r"^(UFSC|CATOLICA)-[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*-\d{4}-\d-\d$"
    return bool(re.match(padrao, texto))


def normalizar_sentimento(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        return "Neutra"

    r = raw.strip().lower()

    if r.startswith("posit"):
        return "Positiva"
    if r.startswith("negat"):
        return "Negativa"
    if r.startswith("mist"):
        return "Misto"

    return "Neutra"


def calcular_percentual(valor: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round((valor / total) * 100, 2)


def carregar_csv(caminho: str) -> pd.DataFrame:
    logger.info(f"Lendo CSV: {caminho}")
    df = pd.read_csv(caminho, dtype=str, encoding="utf-8").fillna("")
    df.columns = df.columns.str.strip()
    return df


def preparar_respostas(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Preparando dados...")

    df = df.copy()

    df["turma"] = df[COL_ID].astype(str).str.strip()
    df["resposta"] = df[COL_RESP].astype(str).str.strip()

    df = df[
        (~df["resposta"].eq("")) &
        (~df["turma"].apply(eh_identificacao_turma))
    ]

    logger.info(f"{len(df)} respostas válidas encontradas")
    return df


def classificar_respostas(
    df: pd.DataFrame,
    tipo: str,
    client_ai: Optional[object] = None
) -> pd.DataFrame:

    logger.info("Classificando sentimentos...")

    if client_ai is None:
        client_ai = get_client()

    registros = []

    for _, row in df.iterrows():
        try:
            resultado = classificar_sentimento_individual(
                client_ai,
                row["resposta"]
            )

            if isinstance(resultado, dict):
                sentimento = resultado.get("sentimento_final", "")
                justificativa = resultado.get("justificativa", "")
            else:
                sentimento = str(resultado)
                justificativa = ""

        except Exception as e:
            sentimento = "Neutra"
            justificativa = f"Erro: {e}"

        registros.append({
            "turma": row["turma"],
            "tipo": tipo,
            "resposta": row["resposta"],
            "sentimento": normalizar_sentimento(sentimento),
            "justificativa": justificativa,
        })

    return pd.DataFrame(registros)


def gerar_estatisticas(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Gerando estatísticas...")

    linhas = []

    for (turma, tipo), grupo in df.groupby(["turma", "tipo"]):
        total = len(grupo)
        contagem = grupo["sentimento"].value_counts()

        dados = {
            "turma": turma,
            "tipo": tipo,
            "total_respostas": total,
        }

        for r in ROTULOS_VALIDOS:
            qtd = contagem.get(r, 0)
            dados[f"count_{r.lower()}"] = qtd
            dados[f"pct_{r.lower()}"] = calcular_percentual(qtd, total)

        linhas.append(dados)

    return pd.DataFrame(linhas)

def anexar_resumo(df_detalhado: pd.DataFrame, df_stats: pd.DataFrame) -> pd.DataFrame:
    logger.info("Anexando resumo ao detalhado...")

    df = df_detalhado.merge(df_stats, on=["turma", "tipo"], how="left")

    df["_ordem"] = df.groupby("turma").cumcount()

    cols_resumo = [
        c for c in df.columns
        if c.startswith("count_") or c.startswith("pct_") or c == "total_respostas"
    ]

    for col in cols_resumo:
        df.loc[df["_ordem"] > 0, col] = pd.NA

    return df.drop(columns="_ordem")



def salvar_csv(df: pd.DataFrame, caminho: str):
    logger.info(f"Salvando CSV: {caminho}")

    df.to_csv(
        caminho,
        index=False,
        sep=";",
        encoding="utf-8",
        decimal=",",
        na_rep=""
    )


def executar_pipeline(
    caminho_entrada: str,
    tipo: str,
    caminho_saida_detalhado: str = "detalhado.csv",
    caminho_saida_resumo: str = "estatisticas.csv",
    client_ai=None
) -> Tuple[pd.DataFrame, pd.DataFrame]:

    df_raw = carregar_csv(caminho_entrada)

    df_clean = preparar_respostas(df_raw)

    df_classificado = classificar_respostas(df_clean, tipo, client_ai)

    df_stats = gerar_estatisticas(df_classificado)

    df_final = anexar_resumo(df_classificado, df_stats)

    salvar_csv(df_final, caminho_saida_detalhado)
    salvar_csv(df_stats, caminho_saida_resumo)

    logger.info("Pipeline finalizado com sucesso")

    return df_final, df_stats


def executar_pipeline_sentimentos(
    caminho_entrada: str,
    tipo: str,
    caminho_saida_individual: str = "sentimentos_individuais.csv",
    client_ai=None,
):
    return executar_pipeline(
        caminho_entrada=caminho_entrada,
        tipo=tipo,
        caminho_saida_detalhado=caminho_saida_individual,
        caminho_saida_resumo=f"estatisticas_{tipo}.csv",
        client_ai=client_ai,
    )