# Contexto do Projeto — Oráculo Paranormal Bot

## O que é
Bot para Discord que responde perguntas sobre **Ordem Paranormal RPG v1.3** usando RAG (Retrieval-Augmented Generation). O livro base está em `D:\ordem-paranormal-rpg-v1-3-lyfxjj.pdf`.

## Arquitetura
- **Embeddings locais**: `sentence-transformers` com modelo `paraphrase-multilingual-MiniLM-L12-v2` (roda no CPU, sem custo de API)
- **Banco vetorial**: ChromaDB persistente em `d:\Ordem\bot\chroma_db\`
- **LLM**: Google Gemini `gemini-2.5-flash` via `google-generativeai`
- **Bot**: `discord.py` com prefix command `!op` e slash command `/op`

## Personalidade do Bot
O bot se chama **Oráculo Paranormal** e fala **como a personagem Agatha** de Ordem Paranormal. Definido no `SYSTEM_PROMPT` em `rag.py`.

## Arquivos e responsabilidades
| Arquivo | Função |
|---|---|
| `01_build_index.py` | Processa o PDF e cria o índice vetorial (roda uma vez) |
| `rag.py` | Busca contexto no ChromaDB + chama Gemini |
| `bot.py` | Bot do Discord (prefix + slash commands, cache, cooldown) |
| `diagnostico.py` | Script de debug para inspecionar chunks do ChromaDB |
| `.env` | Tokens secretos (DISCORD_TOKEN, GEMINI_API_KEY) |
| `chroma_db/` | Banco vetorial gerado (não commitar no git) |

## Configurações atuais (rag.py)
```python
N_RESULTADOS = 10         # chunks buscados por pergunta
GEMINI_MODEL = "gemini-2.5-flash"
max_output_tokens = 3000
temperature = 0.3
```

## Estrutura da busca (rag.py) — Busca Híbrida
A função `buscar_contexto()` usa **duas camadas** de busca:

1. **Busca semântica** — via embedding no ChromaDB, retorna `N_RESULTADOS` chunks mais próximos
   - Para perguntas comparativas (detectadas por palavras-chave como "compare", "vs", "diferença"), faz **múltiplas queries** (uma por entidade) e une os chunks

2. **Busca por keyword** — via `where_document={"$contains": termo}` do ChromaDB
   - Extrai palavras específicas da pergunta (≥5 chars, sem stop words)
   - Busca direta no banco por essas palavras (case-insensitive com variantes)
   - Injeta os chunks encontrados **no início do contexto** (prioridade máxima, limit=6)

## Estrutura da extração do PDF (01_build_index.py)
O PDF (`D:\ordem-paranormal-rpg-v1-3-lyfxjj.pdf`) tem **332 páginas** e layout multi-coluna.

A extração usa **duas tentativas por página**:
1. **Blocos posicionados** (`get_text("blocks")`) — separa colunas esq/dir por posição X
2. **Fallback para `get_text("text")` simples** — ativado quando `get_text("text")` retorna **50% mais conteúdo** que os blocos filtrados

Estratégia de chunking — **por página** (implementada em 2026-03-28):
```python
MAX_PALAVRAS_POR_CHUNK = 350  # páginas com ≤350 palavras = 1 chunk único
OVERLAP_PALAVRAS = 60         # overlap só para páginas grandes que precisam sub-dividir
# Resultado: 543 chunks gerados
# Vantagem: seções como 'Trilhas de Especialista' e fichas de criaturas ficam
# em chunks únicos, sem fragmentação entre páginas.
```

## Problemas resolvidos durante o desenvolvimento
1. **`ValueError: document closed`** — `len(doc)` chamado após `doc.close()`. Fix: salvar `total_paginas` antes de fechar.
2. **Modelo não encontrado** — `gemini-1.5-flash` descontinuado. Trocado para `gemini-2.5-flash`.
3. **Quota 0 no plano gratuito** — `gemini-2.0-flash` e `gemini-2.0-flash-lite` com limit=0. `gemini-2.5-flash` funciona.
4. **Texto do PDF misturado** — layout multi-coluna. Fix: extração por blocos com separação esq/dir.
5. **Respostas cortadas no Discord** — `max_output_tokens=600` insuficiente + campo Embed limitado a 1024 chars. Fix: mais tokens + dividir em múltiplos campos `📖 Resposta` / `📖 Continuação`.
6. **`ValueError: Expected include item... got ids`** — ChromaDB retorna IDs automaticamente. Fix: remover `"ids"` do `include`.
7. **Respostas genéricas** — `N_RESULTADOS=4` insuficiente. Fix: aumentar, reformular SYSTEM_PROMPT, adicionar busca comparativa.
8. **Ritual de Cicatrização fragmentado** — Cadeia: reindexação + fallback `get_text("text")` + busca híbrida keyword/semântica.
9. **Trilhas de Especialista incompletas** — Página 40 tinha 728 palavras, gerava 3 chunks quebrando o contexto. Fix: **chunking por página**.

## Diagnóstico do PDF (2026-03-28)
- Offset: numeração impressa ≠ página do arquivo (~10 pág. de diferença)
- **"Empap"**: **NÃO existe como texto extraível** — conteúdo image-based. Para suportar precisaria OCR.
- **Trilhas restantes** (Investigador, Ocultista, Combatente, Atirador): suspeita de também serem image-based — não investigado completamente.
- OCR grátis: Tesseract (qualidade baixa em PDFs estilizados de RPG). OCR pago: Gemini Vision API (boa qualidade, consome tokens).

## Resultados de testes (2026-03-28)
| Pergunta | Resultado |
|---|---|
| `ritual de cicatrização` | ✅ Completo com todas as formas (Básico, Discente, Verdadeiro) |
| `top 3 criaturas de sangue` | ✅ Detalhado — Kerberos VD340, Minotauro VD280, Titã de Sangue |
| `trilhas de especialista` | ⚠️ Só 2/5 (Médico de Campo e Negociador) — restantes suspeitas de image-based |
| `kerberos vs empap` | ⚠️ Empap não existe no texto do PDF |

## Status atual (pausado em 2026-03-28)
- ✅ Bot funcional — `!op` (prefix) e `/op` (slash)
- ✅ Índice: **543 chunks** com chunking por página
- ✅ Busca híbrida: semântica (N=10) + keyword (limit=6)
- ✅ Respostas de rituais e criaturas melhoradas
- ⚠️ Trilhas de Especialista: só 2/5 encontradas
- ⚠️ `Message Content Intent` deve estar ativo no Discord Developer Portal

## Como rodar
```powershell
# Reindexar PDF (após mudanças no 01_build_index.py):
cd d:\Ordem\bot
python 01_build_index.py

# Iniciar o bot:
python bot.py
```

## Próximas melhorias mapeadas

### Fáceis (sem custo)
- Verificar se trilhas Investigador/Ocultista/Combatente/Atirador existem no texto do PDF
- Comando `!op_regra <termo>` para busca direta sem LLM (zero tokens)
- Logging de perguntas para análise de uso
- Histórico de conversa por canal (memória curta)

### Médias (decisão necessária)
- Deploy em servidor sempre ligado (Railway, Fly.io, VPS)
- OCR com Tesseract (grátis, local, mas qualidade baixa em livros RPG estilizados)

### Caras (escolha consciente)
- OCR via Gemini Vision API (ótima qualidade, mas consome tokens por página de imagem)
