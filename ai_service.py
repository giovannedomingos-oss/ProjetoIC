import os
import json
import re
from datetime import datetime
from openai import OpenAI


def eh_chave_identificacao(texto: str) -> bool:
    if not texto:
        return False
    texto = texto.strip()
    padrao = r"^(UFSC|CATOLICA)-[A-Za-z0-9_\-]+-2025-1-[12]$"
    return bool(re.match(padrao, texto))


def _salvar_resposta_bruta(texto: str, sufixo="resposta_bruta"):
    nome = f"{sufixo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(nome, "w", encoding="utf-8") as f:
        f.write(texto)

def _extrair_json_de_texto(texto: str):
    if not texto or not isinstance(texto, str):
        raise ValueError("Texto vazio para parsear JSON")
    texto = texto.strip()
    posicoes = [p for p in (texto.find('['), texto.find('{')) if p != -1]
    if posicoes:
        inicio = min(posicoes)
        candidato = texto[inicio:]
    else:
        candidato = texto
    ultimo = max(candidato.rfind(']'), candidato.rfind('}'))
    if ultimo != -1:
        candidato = candidato[:ultimo+1]
    try:
        return json.loads(candidato)
    except Exception:
        candidato2 = candidato.replace('“', '"').replace('”', '"').replace("‘", "'").replace("’", "'")
        return json.loads(candidato2)

def get_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY não definida")
    return OpenAI(api_key=api_key)


def _gerar_resumo(client_ai, texto_base: str, prompt_sistema: str) -> str:
    texto_base = (texto_base or "").strip()
    if not texto_base:
        return ""
    resp = client_ai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": texto_base},
        ],
        temperature=0,
    )
    return resp.choices[0].message.content.strip()

def gerar_resumo_disciplina(client_ai, texto_base: str) -> str:
    prompt = (
        "Você é um analista pedagógico auxiliando uma pesquisa acadêmica. "
        "A partir das respostas dos estudantes sobre uma disciplina, elabore um resumo geral da turma que: "
        "descreva o sentimento predominante dos alunos; "
        "analise o nível de engajamento, motivação e dificuldades relatadas; "
        "identifique pontos fortes da disciplina, como metodologia, didática, materiais e atividades; "
        "identifique fragilidades ou desafios, como dificuldade inicial, ansiedade, avaliações ou adaptação; "
        "aponte possíveis riscos pedagógicos, como desmotivação ou evasão; "
        "e indique aspectos que podem ser ajustados para melhorar o processo de ensino-aprendizagem. "
        "O texto deve ser claro, analítico, equilibrado e adequado para uso em pesquisa acadêmica. "
        "Não cite respostas individuais."
    )
    return _gerar_resumo(client_ai, texto_base, prompt)

def gerar_resumo_universidade(client_ai, texto_base: str) -> str:
    prompt = (
        "Você é um analista educacional auxiliando uma pesquisa acadêmica. "
        "A partir das respostas dos estudantes sobre sua experiência na universidade, elabore um resumo geral da turma que: "
        "descreva o sentimento predominante dos alunos em relação à instituição; "
        "analise o processo de adaptação ao ambiente universitário; "
        "identifique pontos positivos da experiência acadêmica, como acolhimento, infraestrutura, apoio e ambiente; "
        "identifique dificuldades ou fragilidades percebidas pelos estudantes; "
        "aponte possíveis fatores que influenciam o bem-estar, engajamento ou risco de evasão; "
        "e forneça uma visão analítica útil para avaliação institucional. "
        "O texto deve ser claro, analítico e adequado para uso em pesquisa acadêmica. "
        "Não cite respostas individuais."
    )
    return _gerar_resumo(client_ai, texto_base, prompt)


def classificar_sentimento(client_ai, texto_resumo: str) -> str:
    texto_resumo = (texto_resumo or "").strip()
    if not texto_resumo:
        return "Neutra"
    prompt = (
        "Classifique o sentimento predominante do texto abaixo em exatamente uma das três categorias: "
        "Positivo, Negativo ou Neutro. "
        "Responda apenas com uma única palavra: Positivo, Negativo ou Neutro."
    )
    resp = client_ai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": texto_resumo},
        ],
        temperature=0,
    )
    conteudo = resp.choices[0].message.content.strip()
    m = re.search(r"\b(Positivo|Negativo|Neutro|Positiva|Negativa|Neutra)\b", conteudo, flags=re.IGNORECASE)
    if m:
        token = m.group(1).lower()
        if token.startswith("posit"):
            return "Positiva"
        if token.startswith("negat"):
            return "Negativa"
        return "Neutra"
    return "Neutra"


def classificar_sentimento_individual(client_ai, texto: str) -> dict:
    texto = (texto or "").strip()

    if eh_chave_identificacao(texto):
        return {
            "sentimento_final": "Neutra",
            "componentes": {"positivo": [], "negativo": [], "neutro": []},
            "justificativa": "Linha de identificação da turma — não é resposta de estudante."
        }

    if not texto:
        return {
            "sentimento_final": "Neutra",
            "componentes": {"positivo": [], "negativo": [], "neutro": []},
            "justificativa": "Texto vazio."
        }

    prompt = """
Você é um classificador de sentimento especializado em respostas curtas de estudantes.

Classifique o texto abaixo considerando três categorias:
- Positiva: elogios, satisfação, aspectos favoráveis.
- Negativa: críticas, frustração, aspectos desfavoráveis.
- Neutra: informação, descrição ou opinião sem carga emocional clara.

IMPORTANTE:
- Se houver sentimentos mistos (ex.: “A disciplina é difícil mas a aula é boa”), identifique ambos.
- Porém, escolha um sentimento final seguindo esta regra:
    1. Se houver sentimentos positivos E negativos → classifique como "Misto".
    2. Se houver apenas um tipo → use Positiva, Negativa ou Neutra normalmente.
- Sempre retorne JSON válido.

TEXTO:
"{{TEXTO_DO_ALUNO}}"

RETORNO (somente JSON):
{
  "sentimento_final": "Positiva | Negativa | Neutra | Misto",
  "componentes": {
      "positivo": ["trechos positivos encontrados"],
      "negativo": ["trechos negativos encontrados"],
      "neutro": ["trechos neutros encontrados"]
  },
  "justificativa": "Explique em 1 frase por que o sentimento_final foi escolhido."
}
"""
    prompt = prompt.replace("{{TEXTO_DO_ALUNO}}", texto)

    try:
        resp = client_ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": texto},
            ],
            temperature=0,
        )
        conteudo = resp.choices[0].message.content.strip()
    except Exception as e:
       
        _salvar_resposta_bruta(f"Erro API: {e}\nTexto:{texto}", sufixo="erro_api")
        return {
            "sentimento_final": "Neutra",
            "componentes": {"positivo": [], "negativo": [], "neutro": []},
            "justificativa": f"Erro na chamada à API: {e}"
        }

    try:
        dados = _extrair_json_de_texto(conteudo)
        if isinstance(dados, dict) and "sentimento_final" in dados:
           
            sf = dados.get("sentimento_final", "").strip().lower()
            if sf.startswith("posit"):
                dados["sentimento_final"] = "Positiva"
            elif sf.startswith("negat"):
                dados["sentimento_final"] = "Negativa"
            elif sf.startswith("mist"):
                dados["sentimento_final"] = "Misto"
            else:
                dados["sentimento_final"] = "Neutra"
            return dados
        if isinstance(dados, list) and len(dados) > 0 and isinstance(dados[0], dict):
            return dados[0]
        _salvar_resposta_bruta(conteudo, sufixo="resposta_bruta_invalida")
    except Exception as e:
        _salvar_resposta_bruta(conteudo, sufixo="resposta_bruta_erro")
        return {
            "sentimento_final": "Neutra",
            "componentes": {"positivo": [], "negativo": [], "neutro": []},
            "justificativa": f"Falha ao interpretar JSON retornado: {e}"
        }

    return {
        "sentimento_final": "Neutra",
        "componentes": {"positivo": [], "negativo": [], "neutro": []},
        "justificativa": "Resposta em formato inesperado."
    }
