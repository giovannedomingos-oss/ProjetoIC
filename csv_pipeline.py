import pandas as pd
from ai_service import (
    gerar_resumo_disciplina,
    gerar_resumo_universidade,
    classificar_sentimento,
)

COL_ID = "Identificação"
COL_RESP = "Resposta"


def _gerar_csv_agregado(
    client_ai,
    caminho_entrada: str,
    caminho_saida: str,
    nome_coluna_resumo: str,
    funcao_resumo,
):

    df = pd.read_csv(
        caminho_entrada,
        encoding="utf-8",
        dtype=str,
    ).fillna("")

    df.columns = df.columns.str.strip()

    for col in [COL_ID, COL_RESP]:
        if col not in df.columns:
            raise ValueError(f"Coluna obrigatória ausente: {col}")


    df[COL_ID] = (
        df[COL_ID]
        .replace("", pd.NA)
        .ffill()
    )

    df = df[df[COL_ID].notna()]

    resultado = []

    for turma, grupo in df.groupby(COL_ID):

        respostas = [
            r.strip()
            for r in grupo[COL_RESP].tolist()
            if isinstance(r, str) and r.strip()
        ]

        if not respostas:
            continue

        texto_base = "\n".join(respostas)


        resumo = funcao_resumo(client_ai, texto_base)

        if resumo:
            resumo = (
                resumo
                .replace("\n", " ")
                .replace("\r", " ")
                .strip()
            )

        sentimento = classificar_sentimento(client_ai, resumo)

        resultado.append({
            "turma-codigo": turma,
            nome_coluna_resumo: resumo,
            "sentimento": sentimento,
        })

    df_saida = pd.DataFrame(resultado)

    df_saida.to_csv(
        caminho_saida,
        index=False,
        sep=";",
        encoding="utf-8",
    )

    return df_saida


def gerar_csv_disciplina(
    client_ai,
    caminho_entrada: str,
    caminho_saida: str = "resumo_disciplina.csv",
):
    return _gerar_csv_agregado(
        client_ai=client_ai,
        caminho_entrada=caminho_entrada,
        caminho_saida=caminho_saida,
        nome_coluna_resumo="resumo-disciplina",
        funcao_resumo=gerar_resumo_disciplina,
    )


def gerar_csv_universidade(
    client_ai,
    caminho_entrada: str,
    caminho_saida: str = "resumo_universidade.csv",
):
    return _gerar_csv_agregado(
        client_ai=client_ai,
        caminho_entrada=caminho_entrada,
        caminho_saida=caminho_saida,
        nome_coluna_resumo="resumo-universidade",
        funcao_resumo=gerar_resumo_universidade,
    )