from fastapi import FastAPI
import gspread
import os
import logging
import json
from openai import OpenAI

app = FastAPI()

# CREDENCIAIS GOOGLE

filename = os.environ.get(
    "GOOGLE_CREDENTIALS_FILE",
    r"C:\Users\Giova\Downloads\evasao-estudantil-fb1d1292d468.json"
)

credentials_json_env = os.environ.get("GOOGLE_CREDENTIALS_JSON")

client_gspread = None
spreadsheet = None

try:
    if credentials_json_env:
        creds_dict = json.loads(credentials_json_env)
        client_gspread = gspread.service_account_from_dict(creds_dict)
    elif filename and os.path.exists(filename):
        client_gspread = gspread.service_account(filename)

    if client_gspread:
        spreadsheet = client_gspread.open_by_key("1F0TXJKwc5XkoHRQyZgBOqxERjAOKI2tnmfpOcZK9h1s")

except Exception:
    logging.exception("Erro ao inicializar gspread:")
    client_gspread = None
    spreadsheet = None


# CLIENTE OPENAI

openai_api_key = os.environ.get("OPENAI_API_KEY")
client_ai = OpenAI(api_key=openai_api_key)


# ENDPOINT STATUS

@app.get("/")
def raiz():
    return {"status": "API funcionando!"}


@app.get("/status")
def status():
    connected = spreadsheet is not None
    return {
        "status": "ok",
        "spreadsheet_connected": connected,
        "abas_disponiveis": [ws.title for ws in spreadsheet.worksheets()] if connected else []
    }


# LER CÉLULA DIRETA

@app.get("/teste_celula")
def teste_celula(aba: str, celula: str):
    ws = spreadsheet.worksheet(aba)
    valor = ws.acell(celula).value
    return {"status": "ok", "celula": celula, "conteudo": valor}


# GERAR UM ÚNICO RESUMO

@app.get("/resumo_unico")
def resumo_unico(aba: str, coluna: str, linha_inicio: int, linha_fim: int, coluna_destino: str):
    try:
        ws = spreadsheet.worksheet(aba)

        # LER INTERVALO EM UMA ÚNICA REQUISIÇÃO 

        intervalo = f"{coluna}{linha_inicio}:{coluna}{linha_fim}"
        dados = ws.get(intervalo)   

        textos = [linha[0] for linha in dados if linha and linha[0].strip()]

        if not textos:
            return {"status": "erro", "detalhes": "Nenhum texto encontrado no intervalo."}

        texto_unico = "\n".join(textos)

        # CHAMADA AO CHATGPT 
        resposta = client_ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Você é um assistente especializado em síntese de sentimentos."},
                {"role": "user", "content": f"Leia todas as respostas abaixo e produza um único resumo objetivo sobre o sentimento geral da turma:\n\n{texto_unico}"}
            ]
        )

        # ACESSO CORRETO AO TEXTO
        resumo = resposta.choices[0].message.content

        # GRAVAR RESUMO NA PLANILHA 
        cel_destino = f"{coluna_destino}{linha_inicio}"
        ws.update_acell(cel_destino, resumo)

        return {
            "status": "ok",
            "resumo": resumo,
            "gravado_em": cel_destino
        }

    except Exception as e:
        return {"status": "erro", "detalhes": str(e)}
