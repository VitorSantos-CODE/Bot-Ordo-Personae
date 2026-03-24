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
N_RESULTADOS = 4

# Modelo Gemini (flash = mais barato/rápido; pro = mais inteligente)
GEMINI_MODEL = "gemini-2.5-flash"

# Prompt do sistema — enxuto por design para economizar tokens
SYSTEM_PROMPT = """Você é o Oráculo Paranormal, assistente especialista em Ordem Paranormal RPG.
Responda de forma clara e direta, APENAS com base no contexto fornecido.
Se a informação não estiver no contexto, diga: "Não encontrei essa informação no livro de regras."
Não invente regras. Use termos do sistema (NEX, Rituais, Esforço, etc.) corretamente.
Responda sempre em português. Fala como a Agatha, personagem de Ordem Paranormal"""


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

def buscar_contexto(pergunta: str) -> tuple[str, list[int]]:
    """
    Busca os trechos mais relevantes do livro para a pergunta.
    Retorna o contexto concatenado e as páginas de origem.
    """
    resultados = _collection.query(
        query_texts=[pergunta],
        n_results=N_RESULTADOS,
    )

    documentos = resultados["documents"][0]
    metadados = resultados["metadatas"][0]
    paginas = sorted(set(m["pagina"] for m in metadados))

    # Junta os trechos com separador
    contexto = "\n\n---\n\n".join(documentos)
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
