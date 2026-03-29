"""
01_build_index.py
Roda UMA VEZ para processar o PDF e criar o banco vetorial local.
Depois disso, o banco fica salvo na pasta chroma_db/ e o bot usa ele diretamente.

Uso: python 01_build_index.py

Estratégia de chunking:
  - Cada PÁGINA do PDF é tratada como unidade base.
  - Se a página tem <= MAX_PALAVRAS_POR_CHUNK palavras, ela vira 1 chunk.
  - Se a página é grande demais, ela é dividida em sub-chunks com overlap,
    mas NUNCA atravessa fronteiras de página.
  - Isso garante que seções como "Trilhas de Especialista" ou fichas de
    rituais/criaturas não fiquem fragmentadas entre chunks de páginas diferentes.
"""

import os
import fitz  # PyMuPDF
import chromadb
from sentence_transformers import SentenceTransformer
from chromadb.utils.embedding_functions import EmbeddingFunction

# ─── Configurações ────────────────────────────────────────────────────────────

PDF_PATH = r"D:\ordem-paranormal-rpg-v1-3-lyfxjj.pdf"
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION_NAME = "ordem_paranormal"

# Modelo multilíngue leve que roda localmente (suporta português)
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# Chunking por página:
# - Páginas com até MAX palavras = 1 chunk
# - Páginas maiores são sub-divididas com overlap
MAX_PALAVRAS_POR_CHUNK = 350
OVERLAP_PALAVRAS = 60


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
    Extrai texto do PDF página por página.

    Para cada página, tenta duas estratégias:
    1. Blocos posicionados (get_text("blocks")) + separação de colunas esq/dir.
    2. Fallback para get_text("text") simples quando produz significativamente
       mais conteúdo — captura seções com títulos curtos filtrados pelos blocos.

    Retorna lista de dicts: {pagina, texto, n_palavras}
    """
    print(f"\n[*] Abrindo PDF: {pdf_path}")
    doc = fitz.open(pdf_path)
    paginas = []
    paginas_fallback = 0
    paginas_vazias = 0

    for i, page in enumerate(doc):
        largura_pagina = page.rect.width
        meio = largura_pagina / 2

        # ── Método 1: blocos posicionados (multi-coluna) ──────────────────────
        blocos = page.get_text("blocks", sort=False)
        blocos_texto = [
            b for b in blocos
            if b[6] == 0 and b[4].strip() and len(b[4].strip()) > 10
        ]
        coluna_esq = sorted([b for b in blocos_texto if b[0] < meio], key=lambda b: b[1])
        coluna_dir = sorted([b for b in blocos_texto if b[0] >= meio], key=lambda b: b[1])
        texto_blocos = "\n".join(b[4].strip() for b in coluna_esq + coluna_dir)

        # ── Método 2: fallback simples ────────────────────────────────────────
        # Ativo quando o texto simples tem ≥50% mais conteúdo que os blocos.
        # Recupera títulos e seções curtas que o filtro de 10+ chars descarta.
        texto_simples = page.get_text("text").strip()
        texto_final = texto_blocos

        if len(texto_simples) > len(texto_blocos.strip()) * 1.5:
            texto_final = texto_simples
            paginas_fallback += 1

        if not texto_final.strip():
            paginas_vazias += 1
            continue

        n_palavras = len(texto_final.split())
        paginas.append({
            "pagina": i + 1,
            "texto": texto_final,
            "n_palavras": n_palavras,
        })

    total_paginas = len(doc)
    doc.close()
    print(f"[✓] {len(paginas)} páginas com texto extraídas de {total_paginas} total")
    print(f"    {paginas_fallback} usaram fallback simples | {paginas_vazias} vazias (imagens)")
    return paginas


def criar_chunks(paginas: list[dict], max_palavras: int, overlap: int) -> list[dict]:
    """
    Cria chunks respeitando fronteiras de página.

    Cada página gera um ou mais chunks:
    - ≤ max_palavras → 1 chunk (página inteira)
    - > max_palavras → sub-chunks com overlap dentro da mesma página

    Isso mantém o conteúdo de seções coesas (ex: tabela de rituais,
    lista de trilhas, ficha de criatura) no mesmo chunk.
    """
    chunks = []
    chunk_id = 0
    paginas_multi = 0

    for pagina in paginas:
        palavras = pagina["texto"].split()
        n = len(palavras)

        if n <= max_palavras:
            # Página pequena/média: vira um único chunk
            chunks.append({
                "id": f"chunk_{chunk_id}",
                "texto": " ".join(palavras),
                "pagina": pagina["pagina"],
            })
            chunk_id += 1
        else:
            # Página grande: sub-divide com overlap dentro da mesma página
            paginas_multi += 1
            inicio = 0
            while inicio < n:
                fim = min(inicio + max_palavras, n)
                chunks.append({
                    "id": f"chunk_{chunk_id}",
                    "texto": " ".join(palavras[inicio:fim]),
                    "pagina": pagina["pagina"],
                })
                chunk_id += 1
                if fim == n:
                    break
                inicio += max_palavras - overlap

    print(f"[✓] {len(chunks)} chunks criados")
    print(f"    {paginas_multi} páginas grandes foram sub-divididas com overlap={overlap}")
    return chunks


def salvar_no_chromadb(chunks: list[dict], chroma_dir: str, collection_name: str, embedding_fn):
    """Salva os chunks e embeddings no ChromaDB local."""
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
        print(f"\n[ERRO] PDF não encontrado em: {os.path.abspath(PDF_PATH)}")
        print("Verifique se o arquivo está na pasta correta.")
        exit(1)

    # 1. Extrai texto do PDF
    paginas = extrair_texto_pdf(PDF_PATH)

    # 2. Divide em chunks (por página, com sub-divisão se necessário)
    chunks = criar_chunks(paginas, MAX_PALAVRAS_POR_CHUNK, OVERLAP_PALAVRAS)

    # 3. Carrega modelo de embedding
    embedding_fn = LocalEmbeddingFunction(EMBEDDING_MODEL)

    # 4. Salva no ChromaDB
    salvar_no_chromadb(chunks, CHROMA_DIR, COLLECTION_NAME, embedding_fn)

    print("\n" + "=" * 60)
    print("  ✅ Tudo pronto! Agora você pode rodar o bot com:")
    print("     python bot.py")
    print("=" * 60)
