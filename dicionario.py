def construir_grupos_df(df):
    if df.empty:
        return {}

    if "Identificação" not in df.columns or "Resposta" not in df.columns:
        return {}

    grupos = {}
    chave_atual = None
    linha_chave = None

    for idx, row in df.iterrows():
        identificacao = str(row["Identificação"]).strip()
        resposta = str(row["Resposta"]).strip()

        if identificacao:
            chave_atual = identificacao
            linha_chave = idx

            grupos[chave_atual] = {
                "respostas": [],
                "linha_chave": linha_chave
            }

            if resposta:
                grupos[chave_atual]["respostas"].append(resposta)

            continue

        if not chave_atual:
            continue

        if resposta:
            grupos[chave_atual]["respostas"].append(resposta)

    # Remove grupos sem respostas
    return {
        k: v for k, v in grupos.items()
        if v["respostas"]
    }
