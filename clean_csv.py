import pandas as pd
import chardet

def detectar_codificacao(arquivo: str) -> str:
    with open(arquivo, "rb") as f:
        return chardet.detect(f.read()).get("encoding") or "utf-8"

def limpar_csv(arquivo_entrada: str, arquivo_saida: str = "saida_limpa.csv") -> pd.DataFrame:
    encoding = detectar_codificacao(arquivo_entrada)

    df = pd.read_csv(
        arquivo_entrada,
        encoding=encoding,
        sep=",",
        quotechar='"',
        on_bad_lines="skip",
        dtype=str,
    )

    df = df.dropna(how="all")
    df.columns = [c.strip() for c in df.columns]
    df = df.fillna("")

    if "Resposta" in df.columns:
        df["Resposta"] = (
            df["Resposta"]
            .astype(str)
            .str.replace("\n", " ", regex=False)
            .str.replace("\r", " ", regex=False)
            .str.strip()
        )

    df = df.applymap(
        lambda x: x.encode("latin1", "ignore").decode("utf-8", "ignore")
        if isinstance(x, str) else x
    )

    df.to_csv(arquivo_saida, index=False, encoding="utf-8")
    return df

if __name__ == "__main__":
    limpar_csv("saida.csv", "saida_limpa.csv")
