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
N_RESULTADOS = 4          # chunks buscados por pergunta
GEMINI_MODEL = "gemini-2.5-flash"
max_output_tokens = 3000
temperature = 0.3
```

## Problemas resolvidos durante o desenvolvimento
1. **`ValueError: document closed`** no `01_build_index.py` — `len(doc)` chamado após `doc.close()`. Fix: salvar `total_paginas = len(doc)` antes de fechar.
2. **Modelo não encontrado** — `gemini-1.5-flash` não mais disponível na API v1beta. Trocado para `gemini-2.5-flash`.
3. **Quota 0 no plano gratuito** — `gemini-2.0-flash` e `gemini-2.0-flash-lite` têm limit=0 na free tier para esta conta. `gemini-2.5-flash` funcionou.
4. **Texto extraído do PDF misturado** — PDF tem layout multi-coluna. Fix: extração por blocos (`page.get_text("blocks")`), separando e ordenando colunas esquerda/direita por posição Y.
5. **Respostas cortadas no Discord** — `max_output_tokens=600` era muito baixo + campo do Embed limitado a 1024 chars. Fix: aumentar tokens + dividir resposta em múltiplos campos `📖 Resposta` / `📖 Continuação`.

## Status atual
- ✅ Bot online e respondendo
- ✅ Comando `!op` (prefix) e `/op` (slash) funcionando
- ⚠️ `01_build_index.py` foi corrigido para multi-coluna — **reindexar** para melhorar qualidade das respostas
- ⚠️ `Message Content Intent` deve estar ativo no Discord Developer Portal

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
