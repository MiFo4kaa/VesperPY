import asyncio
from datetime import datetime, time, timezone
from pathlib import Path

import aiomysql
import disnake
from disnake.ext import commands, tasks
import aiohttp
import yaml


# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================
def loadMainConfig() -> dict:
    configPath = Path("config.yaml")
    if not configPath.exists():
        raise FileNotFoundError("Файл config.yaml не найден.")
    with open(configPath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


mainConfig = loadMainConfig()
cogConfig = mainConfig.get("uwatch", {})


class Config:
    GUILD_ID = mainConfig.get("guild_id")
    LOG_CHANNEL_ID = cogConfig.get("log_channel_id")

    # HTTP API VesperBridge
    apiConfig = mainConfig.get("api", {})
    API_HOST = apiConfig.get("host", "127.0.0.1")
    API_PORT = int(apiConfig.get("port", 8080))
    API_TOKEN = apiConfig.get("token", "")
    API_BASE_URL = f"http://{API_HOST}:{API_PORT}"

    # MySQL Конфигурация
    mysqlConfig = mainConfig.get("mysql", {})
    DB_HOST = mysqlConfig.get("host", "127.0.0.1")
    DB_PORT = int(mysqlConfig.get("port", 3306))
    DB_USER = mysqlConfig.get("user", "root")
    DB_PASSWORD = str(mysqlConfig.get("password", ""))
    DB_NAME = mysqlConfig.get("database", "vespera_db")


# ==========================================
# МЕНЕДЖЕР БАЗЫ ДАННЫХ (MySQL)
# ==========================================
class Database:
    pool: aiomysql.Pool = None

    @classmethod
    async def init(cls):
        if cls.pool is None:
            cls.pool = await aiomysql.create_pool(
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                db=Config.DB_NAME,
                autocommit=True,
                cursorclass=aiomysql.DictCursor,
                minsize=1,
                maxsize=10
            )

    @classmethod
    async def close(cls):
        if cls.pool:
            cls.pool.close()
            await cls.pool.wait_closed()
            cls.pool = None

    @classmethod
    async def get_all_applicants(cls) -> list[dict]:
        """Получает всех пользователей из таблицы whitelist_applicants."""
        async with cls.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT user_id, nick FROM whitelist_applicants")
                return await cur.fetchall()

    @classmethod
    async def remove_applicant(cls, user_id: int) -> int:
        """Удаляет пользователя по user_id из таблицы whitelist_applicants."""
        async with cls.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM whitelist_applicants WHERE user_id = %s", (user_id,))
                return cur.rowcount


# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (API & UI)
# ==========================================
async def api_whitelist_remove(minecraft_nick: str) -> str:
    """Отправляет POST-запрос к VesperBridge API на удаление никнейма из вайтлиста."""
    url = f"{Config.API_BASE_URL}/api/whitelist/remove"
    headers = {
        "Authorization": f"Bearer {Config.API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"username": minecraft_nick}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as response:
                if response.status == 200:
                    data = await response.json()
                    return f"API Success: status={data.get('status')}"
                error_text = await response.text()
                return f"API Error {response.status}: {error_text}"
    except Exception as err:
        return f"API Connection Error: {err}"


def buildAutoPurgeEmbed(discordUserId: int, minecraftNick: str, apiStatus: str | None = None) -> disnake.Embed:
    embed = disnake.Embed(
        title="Автоматическая очистка вайтлиста",
        description=(
            f"Пользователь покинул Discord-сервер и был автоматически исключен.\n\n"
            f"**Discord ID:** `{discordUserId}`\n"
            f"**Minecraft Ник:** `{minecraftNick}`"
        ),
        color=0xE06C75,
        timestamp=datetime.now(timezone.utc)
    )
    if apiStatus:
        embed.add_field(name="API Ответ", value=f"```{apiStatus}```", inline=False)
    embed.set_footer(text="Uwatch")
    return embed


# ==========================================
# COG
# ==========================================
class UserWatchdog(commands.Cog):
    def __init__(self, botInstance: commands.Bot) -> None:
        self.botInstance = botInstance
        self.dailyAuditTask.start()

    async def cog_load(self) -> None:
        await Database.init()

    async def cog_unload(self) -> None:
        self.dailyAuditTask.cancel()
        await Database.close()

    # Запуск ровно в полночь по МСК (21:00 UTC)
    @tasks.loop(time=time(hour=21, minute=0, second=0, tzinfo=timezone.utc))
    async def dailyAuditTask(self) -> None:
        await self.botInstance.wait_until_ready()
        targetChannel = self.botInstance.get_channel(Config.LOG_CHANNEL_ID)
        if not targetChannel:
            return

        await self.performWhitelistAudit(targetChannel)

    async def performWhitelistAudit(self, feedbackChannel: disnake.TextChannel | None = None) -> int:
        targetGuild = self.botInstance.get_guild(Config.GUILD_ID)
        if not targetGuild:
            return 0

        applicants = await Database.get_all_applicants()
        if not applicants:
            return 0

        purgedCount = 0

        for record in applicants:
            discordUserId = record.get("user_id")
            minecraftNick = record.get("nick")

            if not discordUserId or not minecraftNick:
                continue

            try:
                # Проверяем наличие участника на сервере Discord
                await targetGuild.fetch_member(discordUserId)
            except disnake.NotFound:
                # Пользователь покинул сервер — удаляем запись из БД
                await Database.remove_applicant(discordUserId)

                # Отправляем POST-запрос на /api/whitelist/remove к плагину
                apiResult = await api_whitelist_remove(minecraftNick)

                purgedCount += 1

                if feedbackChannel:
                    logEmbed = buildAutoPurgeEmbed(discordUserId, minecraftNick, apiResult)
                    await feedbackChannel.send(embed=logEmbed)

                # Небольшая пауза между запросами для снижения нагрузки на Discord API и HTTP-сервер плагина
                await asyncio.sleep(0.5)
            except disnake.HTTPException:
                continue

        return purgedCount

    @commands.slash_command(
        name="checkusers",
        description="Проверить вайтлист и автоматически удалить покинувших сервер игроков"
    )
    async def manualAuditCommand(self, interaction: disnake.ApplicationCommandInteraction) -> None:
        if not interaction.author.guild_permissions.administrator:
            await interaction.response.send_message(
                "У вас нет прав администратора для выполнения этой команды.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        targetChannel = self.botInstance.get_channel(Config.LOG_CHANNEL_ID) or interaction.channel
        purgedTotal = await self.performWhitelistAudit(feedbackChannel=targetChannel)

        if purgedTotal > 0:
            await interaction.followup.send(
                f"Проверка завершена. Автоматически удалено пользователей: **{purgedTotal}**.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Все игроки из вайтлиста присутствуют на сервере.",
                ephemeral=True
            )


def setup(botInstance: commands.Bot) -> None:
    botInstance.add_cog(UserWatchdog(botInstance))
    print("cog: Uwatch.py загружен")