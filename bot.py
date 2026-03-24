"""
bot.py
Bot do Discord — Oráculo Paranormal 🔮
Suporta tanto prefix commands (!op) quanto slash commands (/op).

Uso:
    python bot.py
"""

import os
import time
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# ─── Configurações ────────────────────────────────────────────────────────────

PREFIX = "!"
COOLDOWN_SEGUNDOS = 10  # Tempo mínimo entre perguntas do mesmo usuário
MAX_CACHE = 100          # Máximo de respostas em cache (evita uso excessivo de memória)

# ─── Setup do Bot ─────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True  # Necessário para ler mensagens com prefix

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)
tree = bot.tree  # Para slash commands

# Cache de respostas: {pergunta_normalizada: (resposta, paginas)}
_cache: dict[str, tuple[str, list[int]]] = {}
# Cooldown por usuário: {user_id: timestamp_ultima_pergunta}
_cooldowns: dict[int, float] = {}


# ─── Lazy import do RAG (só carrega quando o bot está pronto) ─────────────────

_rag = None

def _get_rag():
    global _rag
    if _rag is None:
        import rag
        _rag = rag
    return _rag


# ─── Funções auxiliares ───────────────────────────────────────────────────────

def _normalizar(texto: str) -> str:
    """Normaliza a pergunta para usar como chave de cache."""
    return texto.strip().lower()


def _verificar_cooldown(user_id: int) -> float:
    """Retorna 0 se pode responder, ou quantos segundos faltam."""
    agora = time.time()
    ultima = _cooldowns.get(user_id, 0)
    tempo_passado = agora - ultima
    if tempo_passado < COOLDOWN_SEGUNDOS:
        return COOLDOWN_SEGUNDOS - tempo_passado
    return 0


def _registrar_uso(user_id: int):
    """Registra que o usuário fez uma pergunta agora."""
    _cooldowns[user_id] = time.time()


def _buscar_cache(pergunta: str):
    """Busca no cache. Retorna None se não encontrado."""
    chave = _normalizar(pergunta)
    return _cache.get(chave)


def _salvar_cache(pergunta: str, resposta: str, paginas: list[int]):
    """Salva no cache, respeitando o limite máximo."""
    if len(_cache) >= MAX_CACHE:
        # Remove a entrada mais antiga
        primeira_chave = next(iter(_cache))
        del _cache[primeira_chave]
    _cache[_normalizar(pergunta)] = (resposta, paginas)


async def _processar_pergunta(pergunta: str, user_id: int) -> discord.Embed:
    """
    Lógica central: verifica cooldown, cache, chama RAG e retorna um Embed.
    Usada por ambos os tipos de comando.
    """
    # 1. Cooldown
    faltam = _verificar_cooldown(user_id)
    if faltam > 0:
        embed = discord.Embed(
            title="⏳ Aguarde um momento...",
            description=f"Você poderá fazer outra pergunta em **{faltam:.0f} segundos**.",
            color=discord.Color.orange(),
        )
        return embed

    # 2. Validação mínima
    pergunta = pergunta.strip()
    if len(pergunta) < 3:
        return discord.Embed(
            title="❓ Pergunta muito curta",
            description="Por favor, escreva uma pergunta mais detalhada.",
            color=discord.Color.red(),
        )
    if len(pergunta) > 500:
        return discord.Embed(
            title="📝 Pergunta muito longa",
            description="Por favor, limite sua pergunta a 500 caracteres.",
            color=discord.Color.red(),
        )

    # 3. Cache
    em_cache = _buscar_cache(pergunta)
    if em_cache:
        resposta, paginas = em_cache
        embed = _montar_embed(pergunta, resposta, paginas, do_cache=True)
        return embed

    # 4. Processa via RAG (operação pesada — roda em thread separada)
    _registrar_uso(user_id)

    try:
        rag = _get_rag()
        loop = asyncio.get_running_loop()
        resposta, paginas = await loop.run_in_executor(None, rag.responder, pergunta)
        _salvar_cache(pergunta, resposta, paginas)
        return _montar_embed(pergunta, resposta, paginas, do_cache=False)

    except FileNotFoundError as e:
        return discord.Embed(
            title="⚠️ Índice não encontrado",
            description=f"```{e}```",
            color=discord.Color.red(),
        )
    except Exception as e:
        return discord.Embed(
            title="💥 Erro ao consultar o Oráculo",
            description=f"Algo deu errado: `{type(e).__name__}: {e}`",
            color=discord.Color.red(),
        )


def _montar_embed(
    pergunta: str,
    resposta: str,
    paginas: list[int],
    do_cache: bool,
) -> discord.Embed:
    """Monta o Embed formatado com a resposta, dividindo em múltiplos campos se necessário."""
    embed = discord.Embed(
        title="🔮 Oráculo Paranormal",
        color=discord.Color.purple(),
    )
    embed.add_field(name="❓ Pergunta", value=pergunta, inline=False)

    # Discord limita cada campo a 1024 chars — divide a resposta se necessário
    LIMITE = 1024
    if len(resposta) <= LIMITE:
        embed.add_field(name="📖 Resposta", value=resposta, inline=False)
    else:
        # Divide em partes respeitando o limite, quebrando em espaços
        partes = []
        while len(resposta) > LIMITE:
            corte = resposta.rfind(" ", 0, LIMITE)  # quebra na última palavra
            if corte == -1:
                corte = LIMITE
            partes.append(resposta[:corte])
            resposta = resposta[corte:].lstrip()
        if resposta:
            partes.append(resposta)

        for i, parte in enumerate(partes):
            nome = "📖 Resposta" if i == 0 else "📖 Continuação"
            embed.add_field(name=nome, value=parte, inline=False)

    rodape_partes = []
    if paginas:
        rodape_partes.append(f"📄 Pág. {', '.join(str(p) for p in paginas)}")
    if do_cache:
        rodape_partes.append("⚡ Cache")
    embed.set_footer(text=" • ".join(rodape_partes) if rodape_partes else "Ordem Paranormal RPG")

    return embed



# ─── Eventos ──────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"\n{'='*50}")
    print(f"  🔮 Oráculo Paranormal está online!")
    print(f"  Bot: {bot.user} (ID: {bot.user.id})")
    print(f"  Prefix: {PREFIX}op <pergunta>")
    print(f"  Slash:  /op <pergunta>")
    print(f"{'='*50}\n")

    # Sincroniza slash commands com o Discord
    try:
        synced = await tree.sync()
        print(f"[✓] {len(synced)} slash command(s) sincronizado(s)")
    except Exception as e:
        print(f"[!] Erro ao sincronizar slash commands: {e}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return  # Ignora comandos desconhecidos silenciosamente


# ─── Prefix Command: !op ──────────────────────────────────────────────────────

@bot.command(name="op", help="Faz uma pergunta sobre Ordem Paranormal RPG")
async def op_prefix(ctx: commands.Context, *, pergunta: str = ""):
    """!op <pergunta>"""
    if not pergunta:
        await ctx.send(
            embed=discord.Embed(
                title="🔮 Oráculo Paranormal",
                description=(
                    "Use `!op <sua pergunta>` para consultar o livro de regras.\n\n"
                    "**Exemplos:**\n"
                    "`!op O que é NEX?`\n"
                    "`!op Quais são os atributos do personagem?`\n"
                    "`!op Como funcionam os rituais?`"
                ),
                color=discord.Color.purple(),
            )
        )
        return

    async with ctx.typing():  # Mostra "digitando..." enquanto processa
        embed = await _processar_pergunta(pergunta, ctx.author.id)
    await ctx.reply(embed=embed)


# ─── Slash Command: /op ───────────────────────────────────────────────────────

@tree.command(name="op", description="Faz uma pergunta sobre Ordem Paranormal RPG")
@app_commands.describe(pergunta="O que você quer saber sobre Ordem Paranormal?")
async def op_slash(interaction: discord.Interaction, pergunta: str):
    """/op <pergunta>"""
    # Slash commands precisam de resposta em até 3s; usamos defer para mais tempo
    await interaction.response.defer(thinking=True)
    embed = await _processar_pergunta(pergunta, interaction.user.id)
    await interaction.followup.send(embed=embed)


# ─── Comando de ajuda: !op_ajuda ─────────────────────────────────────────────

@bot.command(name="op_ajuda", aliases=["op_help"])
async def ajuda(ctx: commands.Context):
    embed = discord.Embed(
        title="🔮 Oráculo Paranormal — Ajuda",
        color=discord.Color.purple(),
    )
    embed.add_field(
        name="Como usar",
        value=(
            "`!op <pergunta>` — Comando de texto\n"
            "`/op <pergunta>` — Slash command\n\n"
            "**Exemplos:**\n"
            "`!op O que é NEX?`\n"
            "`!op Como criar um personagem?`\n"
            "`!op Quais são as origens disponíveis?`\n"
            "`!op Como funciona o sistema de rituais?`"
        ),
        inline=False,
    )
    embed.add_field(
        name="⏱️ Cooldown",
        value=f"Aguarde {COOLDOWN_SEGUNDOS}s entre perguntas.",
        inline=False,
    )
    embed.set_footer(text="Respostas baseadas no livro de regras Ordem Paranormal v1.3")
    await ctx.send(embed=embed)


# ─── Inicialização ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("[ERRO] DISCORD_TOKEN não encontrado no arquivo .env")
        print("Copie o arquivo .env.example para .env e preencha o token.")
        exit(1)

    print("[*] Iniciando o Oráculo Paranormal...")
    bot.run(token)
