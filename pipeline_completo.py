import re
import pandas as pd
import logging
from typing import Tuple, Optional, List

from ai_service import (
    get_client,
    classificar_sentimento_individual,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pipeline")

COL_ID = "Identificação"
COL_RESP = "Resposta"

EXTRA_ID_COLS: List[str] = ["Column4"]

ROTULOS = ["Positiva", "Negativa", "Neutra", "Misto"]


def carregar_csv(caminho: str) -> pd.DataFrame:
    """
    Carrega CSV garantindo que colunas sejam strings e sem NaNs.
    """
    df = pd.read_csv(caminho, dtype=str, encoding="utf-8").fillna("")
    df.columns = df.columns.str.strip()
    return df


def _auto_detect_extra_id_columns(df: pd.DataFrame) -> List[str]:
    """
    Detecta automaticamente colunas que provavelmente contêm chaves de identificação.
    Regras simples:
      - nomes que contenham 'column' (Column4, Column5, ...)
      - nomes que contenham 'id' ou 'ident' (exceto a coluna principal COL_ID)
      - nomes que contenham 'class' (às vezes a classificação aparece com a chave)
    """
    candidates = []
    for col in df.columns:
        low = col.lower()
        if col == COL_ID:
            continue
        if low.startswith("column") or "ident" in low or low == "id" or "class" in low:
            candidates.append(col)
    return candidates


def preparar_dados(df: pd.DataFrame) -> pd.DataFrame:
    """
    - Normaliza colunas de identificação e resposta.
    - Preenche a coluna 'turma' por forward-fill a partir de Identificação.
    - Remove linhas vazias de resposta.
    - Remove linhas onde a resposta é idêntica à identificação/turma (caso de cabeçalho repetido).
    - Remove linhas onde a resposta ou qualquer coluna extra detectada contém (substring) qualquer identificação presente no arquivo (case-insensitive).
    - Cria coluna 'resposta' usada pelo pipeline.
    """
    df = df.copy()

    if COL_ID not in df.columns or COL_RESP not in df.columns:
        raise ValueError(f"CSV deve conter as colunas '{COL_ID}' e '{COL_RESP}'")

    # Normaliza e remove espaços
    df[COL_ID] = df[COL_ID].astype(str).str.strip()
    df[COL_RESP] = df[COL_RESP].astype(str).str.strip()

    extra_cols = [c for c in EXTRA_ID_COLS if c in df.columns]
    if not extra_cols:
        extra_cols = _auto_detect_extra_id_columns(df)

    for col in extra_cols:
        df[col] = df[col].astype(str).str.strip()

    ids_from_id_col = {str(x).strip() for x in df[COL_ID].unique() if str(x).strip() != ""}
    ids_from_extras = set()
    for col in extra_cols:
        ids_from_extras.update({str(x).strip() for x in df[col].unique() if str(x).strip() != ""})
    ids_set_original = {s.lower() for s in (ids_from_id_col | ids_from_extras) if s != ""}

    df["turma"] = df[COL_ID].replace("", pd.NA).ffill()

    before_count = len(df)
    df = df[df[COL_RESP] != ""]
    removed_empty = before_count - len(df)
    if removed_empty:
        logger.info("Removidas %d linhas com 'Resposta' vazia.", removed_empty)

    before_count = len(df)
    df = df[df[COL_RESP] != df[COL_ID]]
    removed_same_colid = before_count - len(df)
    if removed_same_colid:
        logger.info("Removidas %d linhas onde 'Resposta' == coluna '%s'.", removed_same_colid, COL_ID)

    before_count = len(df)
    df = df[df[COL_RESP] != df["turma"]]
    removed_same_turma = before_count - len(df)
    if removed_same_turma:
        logger.info("Removidas %d linhas onde 'Resposta' == 'turma' (ffill).", removed_same_turma)

    if ids_set_original:
        ids_sorted = sorted(ids_set_original, key=lambda s: -len(s))
        escaped = [re.escape(s) for s in ids_sorted]
        pattern = "(" + "|".join(escaped) + ")"
        regex = re.compile(pattern, flags=re.IGNORECASE)

        mask_resp_no_id = ~df[COL_RESP].astype(str).str.contains(regex, regex=True)

        if extra_cols:
            mask_extras_no_id = pd.Series(True, index=df.index)
            for col in extra_cols:
                mask_extras_no_id = mask_extras_no_id & (~df[col].astype(str).str.contains(regex, regex=True))
        else:
            mask_extras_no_id = pd.Series(True, index=df.index)

        mask_keep = mask_resp_no_id & mask_extras_no_id

        removed = df[~mask_keep].copy()
        if not removed.empty:
            logger.info(
                "Removendo %d linhas onde 'Resposta' ou colunas extras contêm (substring) uma identificação de turma.",
                len(removed),
            )
            logger.debug("Exemplos removidos por coincidência com ID (substring):\n%s", removed.head(10).to_dict(orient="records"))

        df = df[mask_keep]

    df = df.reset_index(drop=True)

    df["resposta"] = df[COL_RESP]

    return df


def normalizar_sentimento(valor: str) -> str:
    """
    Normaliza o texto retornado pelo serviço de sentimento para os rótulos definidos.
    """
    if not isinstance(valor, str):
        return "Neutra"

    v = valor.strip().lower()

    if v.startswith("posit"):
        return "Positiva"
    if v.startswith("negat"):
        return "Negativa"
    if v.startswith("mist"):
        return "Misto"

    return "Neutra"


def classificar(df: pd.DataFrame, client) -> pd.DataFrame:
    """
    Classifica cada resposta usando a função externa classificar_sentimento_individual.
    Em caso de erro, marca como 'Neutra' e registra justificativa com o erro.
    """
    registros = []

    for idx, row in df.iterrows():
        resposta_texto = row.get("resposta", "")
        try:
            resultado = classificar_sentimento_individual(
                client,
                resposta_texto
            )

            sentimento = normalizar_sentimento(
                resultado.get("sentimento_final", "Neutra")
            )
            justificativa = resultado.get("justificativa", "")

        except Exception as e:
            logger.exception("Erro ao classificar resposta na linha %s", idx)
            sentimento = "Neutra"
            justificativa = f"Erro: {e}"

        registros.append({
            "turma": row["turma"],
            "resposta": resposta_texto,
            "sentimento": sentimento,
            "justificativa": justificativa
        })

    return pd.DataFrame(registros)


def calcular_estatisticas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula contagens e porcentagens por turma com base nas linhas já filtradas.
    Garante que porcentagens somem corretamente com base no total real de respostas.
    """
    linhas = []

    if "turma" not in df.columns or df.empty:
        return pd.DataFrame(columns=["turma", "total"] + [f"count_{r.lower()}" for r in ROTULOS] + [f"pct_{r.lower()}" for r in ROTULOS])

    for turma, grupo in df.groupby("turma"):
        total = len(grupo)
        cont = grupo["sentimento"].value_counts()

        linha = {
            "turma": turma,
            "total": total
        }

        for r in ROTULOS:
            qtd = int(cont.get(r, 0))
            pct = round((qtd / total) * 100, 2) if total > 0 else 0.0

            linha[f"count_{r.lower()}"] = qtd
            linha[f"pct_{r.lower()}"] = pct

        linhas.append(linha)

    stats_df = pd.DataFrame(linhas)

    stats_df = stats_df.sort_values("turma").reset_index(drop=True)

    return stats_df


def salvar_csv(df: pd.DataFrame, caminho: str):
    """
    Salva CSV com separador ponto-e-vírgula e decimal vírgula (compatível com Excel PT-BR).
    """
    df.to_csv(
        caminho,
        index=False,
        sep=";",
        encoding="utf-8",
        decimal=","
    )


def executar_pipeline_completo(
    caminho_entrada: str,
    caminho_saida_detalhado: str = "detalhado.csv",
    caminho_saida_stats: str = "estatisticas.csv",
    client: Optional[object] = None
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Orquestra todo o pipeline: carregar, preparar, classificar, calcular estatísticas e salvar.
    Retorna (df_classificado, df_stats).
    """
    logger.info("Iniciando pipeline...")

    if client is None:
        client = get_client()

    df_raw = carregar_csv(caminho_entrada)

    df_clean = preparar_dados(df_raw)

    logger.info("Distribuição de turmas (top 10) após limpeza:")
    logger.info(df_clean["turma"].value_counts().head(10))

    if df_clean.empty:
        logger.warning("Nenhuma resposta válida encontrada após a limpeza. Encerrando pipeline.")
        df_classificado = pd.DataFrame(columns=["turma", "resposta", "sentimento", "justificativa"])
        df_stats = pd.DataFrame(columns=["turma", "total"] + [f"count_{r.lower()}" for r in ROTULOS] + [f"pct_{r.lower()}" for r in ROTULOS])
        salvar_csv(df_classificado, caminho_saida_detalhado)
        salvar_csv(df_stats, caminho_saida_stats)
        return df_classificado, df_stats

    df_classificado = classificar(df_clean, client)

    df_stats = calcular_estatisticas(df_classificado)

    salvar_csv(df_classificado, caminho_saida_detalhado)
    salvar_csv(df_stats, caminho_saida_stats)

    logger.info("Pipeline concluído com sucesso!")

    return df_classificado, df_stats
