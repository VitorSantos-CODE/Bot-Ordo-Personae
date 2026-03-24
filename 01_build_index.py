"""
01_build_index.py
Roda UMA VEZ para processar o PDF e criar o banco vetorial local.
Depois disso, o banco fica salvo na pasta chroma_db/ e o bot usa ele diretamente.

Uso: python 01_build_index.py
"""

import os
import fitz  # PyMuPDF
import chromadb
from sentence_transformers import SentenceTransformer
from chromadb.utils.embedding_functions import EmbeddingFunction

# ─── Configurações ────────────────────────────────────────────────────────────

PDF_PATH = os.path.join(os.path.dirname(__file__), "..", "ordem-paranormal-rpg-v1-3-lyfxjj.pdf")
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION_NAME = "ordem_paranormal"

# Modelo multilíngue leve que roda localmente (suporta português)
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# Tamanho dos chunks (em palavras) e overlap
CHUNK_SIZE = 400
CHUNK_OVERLAP = 50


# ─── Embedding Function compatível com ChromaDB ───────────────────────────────

class LocalEmbeddingFunction(EmbeddingFunction):
    def __init__(self, model_name: str):
        print(f"[*] Carregando modelo de embedding: {model_name}")
        print("    (Pode demorar um pouco na primeira vez para baixar o modelo)")
        self.model = SentenceTransformer(model_name)

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self.model.encode(input, show_progress_bar=False).tolist()


# ─── Funções ──────────────────────────────────────────────────────────────────

def extrair_texto_pdf(pdf_path: str) -> list[dict]:
    """
    Extrai texto do PDF usando blocos posicionados.
    Trata layout multi-coluna ordenando blocos por posição (y, x)
    para evitar mistura de colunas — problema comum em livros de RPG.
    """
    print(f"\n[*] Abrindo PDF: {pdf_path}")
    doc = fitz.open(pdf_path)
    paginas = []

    for i, page in enumerate(doc):
        # Extrai blocos com posição: (x0, y0, x1, y1, texto, block_no, block_type)
        blocos = page.get_text("blocks", sort=False)

        # Filtra só blocos de texto (type=0) com conteúdo útil
        blocos_texto = [
            b for b in blocos
            if b[6] == 0 and b[4].strip() and len(b[4].strip()) > 10
        ]

        if not blocos_texto:
            continue

        # Detecta a largura da página para identificar colunas
        largura_pagina = page.rect.width
        meio = largura_pagina / 2

        # Separa blocos em coluna esquerda e direita
        coluna_esq = [b for b in blocos_texto if b[0] < meio]
        coluna_dir = [b for b in blocos_texto if b[0] >= meio]

        # Ordena cada coluna de cima para baixo (por y0)
        coluna_esq.sort(key=lambda b: b[1])
        coluna_dir.sort(key=lambda b: b[1])

        # Junta: esquerda primeiro, depois direita
        texto = "\n".join(b[4].strip() for b in coluna_esq + coluna_dir)

        if texto.strip():
            paginas.append({"pagina": i + 1, "texto": texto})

    total_paginas = len(doc)
    doc.close()
    print(f"[✓] {len(paginas)} páginas com texto extraídas de {total_paginas} total")
    return paginas



def criar_chunks(paginas: list[dict], chunk_size: int, overlap: int) -> list[dict]:
    """Divide o texto em chunks com overlap para manter contexto."""
    chunks = []
    chunk_id = 0

    for pagina in paginas:
        palavras = pagina["texto"].split()
        inicio = 0

        while inicio < len(palavras):
            fim = min(inicio + chunk_size, len(palavras))
            texto_chunk = " ".join(palavras[inicio:fim])

            chunks.append({
                "id": f"chunk_{chunk_id}",
                "texto": texto_chunk,
                "pagina": pagina["pagina"],
            })

            chunk_id += 1
            inicio += chunk_size - overlap  # avança com overlap

    print(f"[✓] {len(chunks)} chunks criados (tamanho: ~{chunk_size} palavras, overlap: {overlap})")
    return chunks


def salvar_no_chromadb(chunks: list[dict], chroma_dir: str, collection_name: str, embedding_fn):
    """Salva os chunks e seus embeddings no ChromaDB local."""
    print(f"\n[*] Iniciando indexação vetorial...")
    print(f"    Isso pode demorar 5-15 minutos dependendo do seu CPU.")
    print(f"    Número de chunks: {len(chunks)}")

    client = chromadb.PersistentClient(path=chroma_dir)

    # Remove coleção existente para recriar do zero
    try:
        client.delete_collection(collection_name)
        print(f"[*] Coleção anterior '{collection_name}' removida.")
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    # Insere em lotes para mostrar progresso
    BATCH_SIZE = 50
    total = len(chunks)

    for i in range(0, total, BATCH_SIZE):
        lote = chunks[i : i + BATCH_SIZE]
        collection.add(
            ids=[c["id"] for c in lote],
            documents=[c["texto"] for c in lote],
            metadatas=[{"pagina": c["pagina"]} for c in lote],
        )
        progresso = min(i + BATCH_SIZE, total)
        print(f"    [{progresso}/{total}] chunks indexados...", end="\r")

    print(f"\n[✓] Indexação completa! {total} chunks salvos em '{chroma_dir}'")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  ORÁCULO PARANORMAL — Construção do Índice")
    print("=" * 60)

    if not os.path.exists(PDF_PATH):
        print(f"\n[ERRO] PDF não encontrado em: {PDF_PATH}")
        print("Verifique se o arquivo está na pasta correta.")
        exit(1)

    # 1. Extrai texto do PDF
    paginas = extrair_texto_pdf(PDF_PATH)

    # 2. Divide em chunks
    chunks = criar_chunks(paginas, CHUNK_SIZE, CHUNK_OVERLAP)

    # 3. Carrega modelo de embedding
    embedding_fn = LocalEmbeddingFunction(EMBEDDING_MODEL)

    # 4. Salva no ChromaDB
    salvar_no_chromadb(chunks, CHROMA_DIR, COLLECTION_NAME, embedding_fn)

    print("\n" + "=" * 60)
    print("  ✅ Tudo pronto! Agora você pode rodar o bot com:")
    print("     python bot.py")
    print("=" * 60)
