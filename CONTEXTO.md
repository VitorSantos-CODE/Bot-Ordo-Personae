# Contexto do Projeto — Oráculo Paranormal Bot

## O que é
Bot para Discord que responde perguntas sobre **Ordem Paranormal RPG v1.3** usando RAG (Retrieval-Augmented Generation). O livro base está em `d:\Ordem\ordem-paranormal-rpg-v1-3-lyfxjj.pdf`.

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
N_RESULTADOS = 8          # chunks buscados por pergunta (era 4)
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
   - Injeta os chunks encontrados **no início do contexto** (prioridade máxima)
   - Necessária porque o embedding semântico às vezes não rankeia bem termos específicos (ex: nomes de rituais em chunks mistos de multi-coluna)

## Estrutura da extração do PDF (01_build_index.py)
O PDF (`ordem-paranormal-rpg-v1-3-lyfxjj.pdf`) tem **332 páginas** e layout multi-coluna.

A extração usa **duas tentativas por página**:
1. **Blocos posicionados** (`get_text("blocks")`) — separa colunas esq/dir por posição X
2. **Fallback para `get_text("text")` simples** — ativado quando `get_text("text")` retorna **50% mais conteúdo** que os blocos filtrados
   - Crítico: algumas páginas (ex: pág. 136 com ritual Cicatrização) têm seus títulos de seção perdidos pelo filtro de blocos mas recuperados pelo fallback

Configurações de chunking:
```python
CHUNK_SIZE = 400    # palavras por chunk
CHUNK_OVERLAP = 50  # overlap entre chunks
# Resultado atual: ~518 chunks gerados
```

## Problemas resolvidos durante o desenvolvimento
1. **`ValueError: document closed`** no `01_build_index.py` — `len(doc)` chamado após `doc.close()`. Fix: salvar `total_paginas = len(doc)` antes de fechar.
2. **Modelo não encontrado** — `gemini-1.5-flash` não mais disponível na API v1beta. Trocado para `gemini-2.5-flash`.
3. **Quota 0 no plano gratuito** — `gemini-2.0-flash` e `gemini-2.0-flash-lite` têm limit=0 na free tier para esta conta. `gemini-2.5-flash` funcionou.
4. **Texto extraído do PDF misturado** — PDF tem layout multi-coluna. Fix: extração por blocos, separando e ordenando colunas esquerda/direita por posição Y.
5. **Respostas cortadas no Discord** — `max_output_tokens=600` era muito baixo + campo do Embed limitado a 1024 chars. Fix: aumentar tokens + dividir resposta em múltiplos campos `📖 Resposta` / `📖 Continuação`.
6. **`ValueError: Expected include item... got ids in query`** — ChromaDB não aceita `"ids"` no parâmetro `include` da query (IDs são retornados automaticamente). Fix: remover `"ids"` do `include`.
7. **Respostas genéricas / rituais não encontrados** — `N_RESULTADOS=4` era insuficiente e o `SYSTEM_PROMPT` impedia síntese e comparação. Fix: aumentar para 8, reformular prompt e adicionar busca comparativa.
8. **Ritual de Cicatrização não encontrado (problema complexo)** — Cadeia de causas:
   - O índice inicial foi gerado antes da correção multi-coluna → necessário reindexar
   - Após reindexar, `get_text("blocks")` filtrava títulos curtos de seção → adicionado fallback `get_text("text")` quando retorna 50% mais conteúdo
   - Mesmo com o texto indexado (pág. 136 do PDF), o embedding semântico do chunk misturado de multi-coluna não rankeava bem → implementada busca híbrida com keyword search via `where_document`

## Diagnóstico do PDF
- O PDF tem **332 páginas** no arquivo (não confundir com numeração impressa do livro, que tem offset de ~10 páginas)
  - Ex: "página 126" do livro = **página 136 do arquivo PDF**
- Páginas de rituais e criaturas frequentemente têm pouco texto via `get_text("blocks")` mas muito mais via `get_text("text")` (3000+ chars)
- **~37 páginas** têm texto mínimo com imagens (suspeita de conteúdo parcialmente image-based)

## Status atual
- ✅ Bot online e respondendo
- ✅ Comando `!op` (prefix) e `/op` (slash) funcionando
- ✅ Índice reindexado com fallback de extração — **518 chunks**
- ✅ Busca híbrida implementada e **testada** (semântica + keyword) — ritual Cicatrização encontrado corretamente
- ✅ SYSTEM_PROMPT permite comparações e síntese
- ✅ Comparação entre criaturas funcionando
- ⚠️ `Message Content Intent` deve estar ativo no Discord Developer Portal
- 📋 Resultados completos dos testes serão revisados na próxima sessão

## Como rodar
```powershell
# Reindexar PDF (após mudanças no 01_build_index.py):
cd d:\Ordem\bot
python 01_build_index.py

# Iniciar o bot:
python bot.py
```

## Próximas melhorias possíveis
- Adicionar histórico de conversa por canal (memória curta)
- Comando `!op_regra <termo>` para busca direta sem LLM (zero tokens)
- Logging de perguntas para análise de uso
- Deploy em servidor sempre ligado (ex: Railway, Fly.io, VPS)
- Investigar OCR para páginas 100% image-based (se existirem)
