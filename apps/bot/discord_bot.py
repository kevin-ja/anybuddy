import os
import logging
import discord
import aiohttp
from config import settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("AnyBuddyBot")

DISCORD_BOT_TOKEN = settings.discord_bot_token
FASTAPI_URL = settings.fastapi_url
ALLOWED_CHANNELS = [
    canal.strip() for canal in settings.allowed_channels.split(",") if canal.strip()
]


if not DISCORD_BOT_TOKEN:
    logger.critical("DISCORD_BOT_TOKEN no configurado en las variables de entorno.")

# =====================================================================
# CONFIGURACIÓN DE INTENTS DE DISCORD
# =====================================================================
intents = discord.Intents.default()
intents.messages = True
# message_content es un intent PRIVILEGIADO: activarlo aca no alcanza, tambien
# hay que habilitarlo en el Developer Portal de Discord. Si falta de ese lado el
# bot se conecta igual y aparece online, pero todos los mensajes le llegan con
# content vacio, asi que contesta cualquier cosa sin dar un solo error.
intents.message_content = True

client = discord.Client(intents=intents)


# =====================================================================
# EVENTOS DEL BOT
# =====================================================================
@client.event
async def on_ready():
    logger.info(f"¡Bot conectado exitosamente como {client.user}!")
    logger.info(f"Canales autorizados para responder: {ALLOWED_CHANNELS}")
    logger.info(f"Apuntando al backend en: {FASTAPI_URL}")


@client.event
async def on_message(message: discord.Message):
    logger.info(f"¡Discord envió un evento! Canal detectado: '{message.channel.name}'")
    # 1. Filtro de Seguridad: Evitar que el bot se responda a sí mismo e ingrese en bucle
    if message.author == client.user:
        return

    # 2. Filtro de Canales (Allow-list): Solo procesar si el canal actual está en la lista
    #
    # La lista es de NOMBRES, no de ids. Renombrar el canal en Discord deja al
    # bot mudo sin tocar nada del deploy: sigue online, lee los mensajes y los
    # descarta aca. Los ids no cambian nunca, pero se eligio el nombre porque
    # ALLOWED_CHANNELS lo escribe una persona en el .env.prod.
    if message.channel.name not in ALLOWED_CHANNELS:
        return

    logger.info(
        f"Mensaje recibido de {message.author} en #{message.channel.name}: '{message.content}'"
    )

    # Indicar visualmente en Discord que el bot está "escribiendo" mientras procesa el RAG
    async with message.channel.typing():

        # Preparar el payload bajo el contrato estricto de la API
        payload = {"message": message.content, "user_id": str(message.author.id)}

        # 3. Conexión asíncrona hacia el contenedor de FastAPI
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    FASTAPI_URL, json=payload, timeout=60
                ) as response:

                    if response.status == 200:
                        data = await response.json()
                        bot_response = data.get(
                            "response",
                            "Lo siento, recibí una respuesta vacía del servidor.",
                        )
                    else:
                        error_detail = await response.text()
                        logger.error(
                            f"Error de FastAPI (Status {response.status}): {error_detail}"
                        )
                        bot_response = "❌ Hubo un problema técnico al procesar tu consulta con el agente. Inténtalo de nuevo más tarde."

        except aiohttp.ClientConnectorError:
            logger.error(
                f"No se pudo conectar al servidor de FastAPI en {FASTAPI_URL}. ¿Está el contenedor encendido?"
            )
            bot_response = "🔌 El servicio de asistencia de AnyBuddy está temporalmente fuera de línea. Por favor, avisa a un administrador."

        except Exception as e:
            logger.error(f"Error inesperado en la comunicación: {str(e)}")
            bot_response = "⚠️ Ocurrió un error inesperado al procesar tu mensaje."

        # 4. Responder directamente al alumno en el canal de Discord
        try:
            await message.reply(bot_response)
        except discord.Forbidden:
            logger.error(
                f"No tengo permisos para enviar mensajes en el canal #{message.channel.name}"
            )
        except Exception as e:
            logger.error(f"Error al enviar respuesta a Discord: {str(e)}")


if __name__ == "__main__":
    if DISCORD_BOT_TOKEN:
        client.run(DISCORD_BOT_TOKEN)
