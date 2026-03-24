# 🔮 Oráculo Paranormal

Bot para Discord que responde perguntas sobre **Ordem Paranormal RPG** usando o livro de regras como fonte.

---

## Como funciona

Usa **RAG (Retrieval-Augmented Generation)**:
1. O texto do PDF é indexado localmente em um banco vetorial
2. Para cada pergunta, os trechos mais relevantes do livro são buscados
3. Apenas esses trechos (não o livro todo!) são enviados ao Gemini para gerar a resposta

Isso reduz o uso de tokens em ~99% comparado a enviar o livro inteiro.

---

## Pré-requisitos

- Python 3.10+
- Token de Bot do Discord
- Chave de API do Google Gemini (gratuita)

---

## Configuração (passo a passo)

### 1. Instale as dependências
```bash
cd d:\Ordem\bot
pip install -r requirements.txt
```

### 2. Configure as chaves de API

Copie o arquivo de exemplo e preencha:
```bash
copy .env.example .env
```
Edite o arquivo `.env` com suas chaves:
- **DISCORD_TOKEN**: obtenha em [discord.com/developers/applications](https://discord.com/developers/applications)
- **GEMINI_API_KEY**: obtenha gratuitamente em [aistudio.google.com](https://aistudio.google.com/app/apikey)

### 3. Como obter o Token do Discord

1. Acesse [discord.com/developers/applications](https://discord.com/developers/applications)
2. Clique em **New Application**, dê um nome (ex: "Oráculo Paranormal")
3. Vá em **Bot** → clique em **Reset Token** → copie o token
4. Em **Bot**, ative **Message Content Intent** (necessário para prefix commands)
5. Vá em **OAuth2 → URL Generator**:
   - Scopes: `bot` + `applications.commands`
   - Bot Permissions: `Send Messages`, `Read Messages/View Channels`, `Embed Links`
6. Copie a URL gerada e abra no navegador para convidar o bot ao seu servidor

### 4. Processe o PDF (roda UMA única vez)
```bash
python 01_build_index.py
```
⏳ Isso pode demorar 5-15 minutos. Após isso, o banco vetorial fica salvo em `chroma_db/`.

### 5. Inicie o bot
```bash
python bot.py
```

---

## Comandos

| Comando | Tipo | Descrição |
|---|---|---|
| `!op <pergunta>` | Prefix | Consulta o livro de regras |
| `/op <pergunta>` | Slash | Mesmo que acima (interface moderna) |
| `!op_ajuda` | Prefix | Exibe a ajuda |

**Exemplos:**
```
!op O que é NEX?
!op Quais são os atributos do personagem?
!op Como funcionam os rituais?
!op Quais são as origens disponíveis?
```

---

## Estrutura de arquivos

```
bot/
├── .env                  ← Suas chaves (NÃO compartilhe!)
├── .env.example          ← Template das chaves
├── requirements.txt      ← Dependências Python
├── 01_build_index.py     ← Processa o PDF (roda uma vez)
├── rag.py                ← Lógica de busca e geração de resposta
├── bot.py                ← Bot do Discord
└── chroma_db/            ← Banco vetorial (gerado automaticamente)
```

---

## Limites do plano gratuito do Gemini

O modelo **gemini-1.5-flash** no plano gratuito tem (aproximadamente):
- 15 requisições por minuto
- 1.000.000 tokens por dia

Com o RAG, cada pergunta usa ~1.000-3.000 tokens, ou seja, você tem margem para centenas de perguntas por dia sem custo.
