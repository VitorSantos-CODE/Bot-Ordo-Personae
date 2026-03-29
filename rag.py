"""
rag.py
Módulo de Retrieval-Augmented Generation.
Responsável por buscar contexto relevante no banco vetorial
e gerar respostas usando o Gemini, tudo com uso mínimo de tokens.
"""

import os
import chromadb
import google.generativeai as genai
from sentence_transformers import SentenceTransformer
from chromadb.utils.embedding_functions import EmbeddingFunction
from dotenv import load_dotenv

load_dotenv()

# ─── Configurações ────────────────────────────────────────────────────────────

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION_NAME = "ordem_paranormal"
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# Quantos trechos do livro buscar por pergunta (mais = mais contexto, mais tokens)
N_RESULTADOS = 10

# Modelo Gemini (flash = mais barato/rápido; pro = mais inteligente)
GEMINI_MODEL = "gemini-2.5-flash"

# Palavras-chave que indicam pergunta comparativa — disparam busca dupla
_PALAVRAS_COMPARACAO = [
    "compare", "comparar", "comparação", "diferença", "diferente", "vs",
    "versus", "melhor", "pior", "mais forte", "mais fraco", "entre",
    "qual é mais", "qual tem mais", "qual tem menos",
]

# Prompt do sistema — permite síntese e comparação com base nos chunks
SYSTEM_PROMPT = """Você é o Oráculo Paranormal, assistente especialista em Ordem Paranormal RPG.
Fale sempre como Agatha, personagem de Ordem Paranormal: sábia, direta e misteriosa.
Responda sempre em português.

Suas regras:
1. Use APENAS os dados presentes nos trechos do livro fornecidos no contexto.
2. Você PODE e DEVE fazer comparações, análises e sínteses a partir dos dados presentes no contexto — isso é esperado.
3. Se os dados de dois ou mais elementos estiverem no contexto, compare-os livremente.
4. Nunca invente stats, regras ou habilidades que não estejam no contexto.
5. Se uma informação realmente não estiver em nenhum dos trechos, diga claramente qual parte não encontrou — mas responda o que conseguir com o que tem.
6. Use termos do sistema corretamente: NEX, VD, Rituais, Esforço, Atributos, etc."""


# ─── Embedding Function ───────────────────────────────────────────────────────

class LocalEmbeddingFunction(EmbeddingFunction):
    _instance = None  # Singleton para não recarregar o modelo a cada chamada

    def __new__(cls, model_name: str):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.model = SentenceTransformer(model_name)
        return cls._instance

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self.model.encode(input, show_progress_bar=False).tolist()


# ─── Inicialização (feita uma vez quando o módulo é importado) ────────────────

def _inicializar():
    """Inicializa ChromaDB e Gemini. Lança erro com mensagem clara se algo falhar."""
    # Verifica se o índice existe
    if not os.path.exists(CHROMA_DIR):
        raise FileNotFoundError(
            f"Banco vetorial não encontrado em '{CHROMA_DIR}'.\n"
            "Execute primeiro: python 01_build_index.py"
        )

    # ChromaDB
    embedding_fn = LocalEmbeddingFunction(EMBEDDING_MODEL)
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
    )

    # Gemini
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY não encontrada no arquivo .env")
    genai.configure(api_key=api_key)
    modelo = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=SYSTEM_PROMPT,
    )

    return collection, modelo


# Inicializa ao importar o módulo (uma única vez)
_collection, _modelo = _inicializar()


# ─── Funções públicas ─────────────────────────────────────────────────────────

def _eh_pergunta_comparativa(pergunta: str) -> bool:
    """Detecta se a pergunta pede uma comparação entre dois ou mais elementos."""
    pergunta_lower = pergunta.lower()
    return any(palavra in pergunta_lower for palavra in _PALAVRAS_COMPARACAO)


def _extrair_keywords(pergunta: str) -> list[str]:
    """
    Extrai termos específicos da pergunta para busca direta por keyword.
    Filtra stop words e palavras muito genéricas.
    """
    import re
    stop_words = {
        "como", "quais", "qual", "quem", "onde", "quando", "quanto",
        "todos", "todas", "lista", "passe", "passa", "sobre", "sendo",
        "muito", "mais", "menos", "entre", "nessa", "nesse", "essa",
        "esse", "para", "pelo", "pela", "ritual", "rituais", "livro",
        "sistema", "regras", "personagem", "criar", "tenho", "tenha",
        "posso", "existe", "existem", "falar", "saber", "quero", "favor",
        "preciso", "passa", "passa", "passas", "manda", "mandas",
    }
    palavras = re.findall(r"[a-z\u00e0-\u00fc]{5,}", pergunta.lower())
    return [p for p in palavras if p not in stop_words][:4]  # max 4 keywords


def _extrair_termos_comparacao(pergunta: str) -> list[str]:
    """
    Tenta extrair os termos sendo comparados na pergunta.
    Retorna uma lista de sub-queries para busca individual.
    Estratégia simples: busca pela pergunta original + busca por cada
    segmento separado por 'e', 'ou', 'vs', 'versus'.
    """
    import re
    # Divide nos separadores mais comuns em comparações
    partes = re.split(r'\b(e|ou|vs\.?|versus|com)\b', pergunta, flags=re.IGNORECASE)
    # Filtra partes muito curtas (os próprios separadores)
    termos = [p.strip() for p in partes if len(p.strip()) > 5]
    # Sempre inclui a pergunta completa como primeira query (máx 4 queries)
    queries: list[str] = [pergunta] + termos
    resultado: list[str] = []
    for i, q in enumerate(queries):
        if i >= 4:
            break
        resultado.append(q)
    return resultado



def buscar_contexto(pergunta: str) -> tuple[str, list[int]]:
    """
    Busca os trechos mais relevantes do livro para a pergunta.
    Usa busca híbrida: semântica + keyword direto (via where_document).
    Para perguntas comparativas, faz buscas múltiplas.
    Retorna o contexto concatenado e as páginas de origem.
    """
    if _eh_pergunta_comparativa(pergunta):
        queries = _extrair_termos_comparacao(pergunta)
    else:
        queries = [pergunta]

    todos_docs: list[str] = []
    todas_paginas: set[int] = set()
    ids_vistos: set[str] = set()

    # ── Busca semântica ───────────────────────────────────────────────────
    for query in queries:
        resultados = _collection.query(
            query_texts=[query],
            n_results=N_RESULTADOS,
            include=["documents", "metadatas"],
        )
        docs_batch = list(resultados["documents"][0])  # type: ignore[index]
        metas_batch = list(resultados["metadatas"][0])  # type: ignore[index]
        ids_batch = list(resultados["ids"][0])  # type: ignore[index]
        for doc, meta, doc_id in zip(docs_batch, metas_batch, ids_batch):
            if str(doc_id) not in ids_vistos:
                ids_vistos.add(str(doc_id))
                todos_docs.append(str(doc))
                todas_paginas.add(int(meta["pagina"]))

    # ── Busca por keyword (garante termos específicos que o embedding perde) ─
    keywords = _extrair_keywords(pergunta)
    for keyword in keywords:
        for variante in [keyword, keyword.capitalize(), keyword.title()]:
            try:
                r_kw = _collection.get(
                    where_document={"$contains": variante},
                    include=["documents", "metadatas"],
                    limit=6,  # max 6 chunks por keyword
                )
                kw_docs = list(r_kw["documents"])   # type: ignore[index]
                kw_metas = list(r_kw["metadatas"])  # type: ignore[index]
                kw_ids = list(r_kw["ids"])           # type: ignore[index]
                for doc, meta, doc_id in zip(kw_docs, kw_metas, kw_ids):
                    if str(doc_id) not in ids_vistos:
                        ids_vistos.add(str(doc_id))
                        todos_docs.insert(0, str(doc))  # prioridade no contexto
                        todas_paginas.add(int(meta["pagina"]))
                if kw_docs:  # se encontrou com esta variante, não tenta as outras
                    break
            except Exception:
                pass  # where_document pode não ser suportado em versões antigas

    paginas = sorted(todas_paginas)
    contexto = "\n\n---\n\n".join(todos_docs)
    return contexto, paginas


def gerar_resposta(pergunta: str, contexto: str) -> str:
    """
    Gera uma resposta usando o Gemini com o contexto recuperado.
    O prompt é formatado de forma enxuta para minimizar tokens.
    """
    prompt = f"Contexto do livro:\n{contexto}\n\nPergunta: {pergunta}"

    resposta = _modelo.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            max_output_tokens=3000,  # limite de tokens da resposta
            temperature=0.3,         # mais determinístico = menos alucinação
        ),
    )
    return resposta.text


def responder(pergunta: str) -> tuple[str, list[int]]:
    """
    Função principal: busca contexto e gera resposta.
    Retorna (texto_da_resposta, lista_de_páginas).
    """
    contexto, paginas = buscar_contexto(pergunta)
    resposta = gerar_resposta(pergunta, contexto)
    return resposta, paginas
