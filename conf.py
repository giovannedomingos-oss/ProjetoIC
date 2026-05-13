import os
import json
import logging
import gspread

SPREADSHEET_KEY = "1F0TXJKwc5XkoHRQyZgBOqxERjAOKI2tnmfpOcZK9h1s"

def conectar_google_sheets():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    filename = os.path.join(BASE_DIR, "config", "credenciais.json")

    credentials_json_env = os.environ.get("GOOGLE_CREDENTIALS_JSON")

    try:
        if credentials_json_env:
            creds_dict = json.loads(credentials_json_env)
            client = gspread.service_account_from_dict(creds_dict)

        elif os.path.exists(filename):
            client = gspread.service_account(filename)

        else:
            raise FileNotFoundError(
                f"Arquivo não encontrado em: {filename}"
            )

        return client.open_by_key(SPREADSHEET_KEY)

    except Exception:
        logging.exception("Erro ao conectar Google Sheets:")
        return None