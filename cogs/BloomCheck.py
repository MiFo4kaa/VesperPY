import asyncio
from datetime import time, timezone
from pathlib import Path

import aiohttp
import aiomysql
import disnake
from disnake.ext import commands, tasks
import yaml


# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================
def loadMainConfig() -> dict:
    configPath = Path("config.yaml")
    if not configPath.exists():
        raise FileNotFoundError("Файл config.yaml не найден.")
    with open(configPath, "r", encoding="utf-8") as fileStream:
        return yaml.safe_load(fileStream) or {}


mainConfig = loadMainConfig()
cogConfig = mainConfig.get("bloom", {})


class Config:
    GUILD_ID = mainConfig.get("guild_id")
    BLOOM_ROLE_ID = cogConfig.get("role_id")

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
    connectionPool: aiomysql.Pool = None

    @classmethod
    async def init(cls):
        if cls.connectionPool is None:
            cls.connectionPool = await aiomysql.create_pool(
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
        if cls.connectionPool:
            cls.connectionPool.close()
            await cls.connectionPool.wait_closed()
            cls.connectionPool = None

    @classmethod
    async def getUsersByNicks(cls, targetNicks: list[str]) -> dict[str, int]:
        """Возвращает маппинг {lowercase_nick: user_id} для найденных игроков."""
        if not targetNicks:
            return {}

        queryPlaceholders = ", ".join(["%s"] * len(targetNicks))
        queryString = f"SELECT user_id, nick FROM whitelist_applicants WHERE LOWER(nick) IN ({queryPlaceholders})"

        async with cls.connectionPool.acquire() as dbConnection:
            async with dbConnection.cursor() as dbCursor:
                await dbCursor.execute(queryString, tuple(nickItem.lower() for nickItem in targetNicks))
                resultRows = await dbCursor.fetchall()
                return {rowItem["nick"].lower(): int(rowItem["user_id"]) for rowItem in resultRows if rowItem.get("user_id")}


# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (API)
# ==========================================
async def fetchBloomNicks() -> list[str] | None:
    """Запрашивает список игроков группы bloom у VesperBridge API."""
    requestUrl = f"{Config.API_BASE_URL}/api/groups/bloom"
    requestHeaders = {
        "Authorization": f"Bearer {Config.API_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as httpClientSession:
            async with httpClientSession.get(requestUrl, headers=requestHeaders, timeout=aiohttp.ClientTimeout(total=10.0)) as httpResponse:
                if httpResponse.status == 200:
                    responseData = await httpResponse.json()
                    return responseData.get("players", [])
                return None
    except Exception:
        return None


# ==========================================
# COG
# ==========================================
class BloomSync(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await Database.init()
        self.dailyBloomSyncTask.start()

    async def cog_unload(self) -> None:
        self.dailyBloomSyncTask.cancel()
        await Database.close()

    # 02:00 по МСК (UTC+3) соответствует 23:00 UTC предыдущего дня
    @tasks.loop(time=time(hour=23, minute=0, second=0, tzinfo=timezone.utc))
    async def dailyBloomSyncTask(self) -> None:
        await self.bot.wait_until_ready()
        await self.syncBloomRoles()

    async def syncBloomRoles(self) -> tuple[int, int]:
        """Синхронизирует роли участников Discord со списком из LuckPerms."""
        targetGuild = self.bot.get_guild(Config.GUILD_ID)
        if not targetGuild:
            return 0, 0

        bloomRole = targetGuild.get_role(Config.BLOOM_ROLE_ID)
        if not bloomRole:
            return 0, 0

        apiNicks = await fetchBloomNicks()
        if apiNicks is None:
            return 0, 0

        nickToUserId = await Database.getUsersByNicks(apiNicks)

        targetBloomUserIds: set[int] = set(nickToUserId.values())
        currentRoleMembers = {guildMember.id: guildMember for guildMember in bloomRole.members}
        currentRoleUserIds: set[int] = set(currentRoleMembers.keys())

        userIdsToAdd = targetBloomUserIds - currentRoleUserIds
        userIdsToRemove = currentRoleUserIds - targetBloomUserIds

        addedCount = 0
        removedCount = 0

        for targetUserId in userIdsToAdd:
            targetMember = targetGuild.get_member(targetUserId)
            if not targetMember:
                try:
                    targetMember = await targetGuild.fetch_member(targetUserId)
                except (disnake.NotFound, disnake.HTTPException):
                    continue

            try:
                await targetMember.add_roles(bloomRole, reason="Bloom sync: active subscription")
                addedCount += 1
                await asyncio.sleep(0.3)
            except (disnake.Forbidden, disnake.HTTPException):
                continue

        for targetUserId in userIdsToRemove:
            targetMember = currentRoleMembers.get(targetUserId)
            if not targetMember:
                targetMember = targetGuild.get_member(targetUserId)
                if not targetMember:
                    try:
                        targetMember = await targetGuild.fetch_member(targetUserId)
                    except (disnake.NotFound, disnake.HTTPException):
                        continue

            try:
                await targetMember.remove_roles(bloomRole, reason="Bloom sync: subscription expired")
                removedCount += 1
                await asyncio.sleep(0.3)
            except (disnake.Forbidden, disnake.HTTPException):
                continue

        return addedCount, removedCount

    @commands.slash_command(
        name="syncbloom",
        description="Принудительно синхронизировать роли Bloom с сервером"
    )
    async def manualBloomSync(self, commandInteraction: disnake.ApplicationCommandInteraction) -> None:
        if not commandInteraction.author.guild_permissions.administrator:
            await commandInteraction.response.send_message(
                "У вас нет прав администратора для выполнения этой команды.",
                ephemeral=True
            )
            return

        await commandInteraction.response.defer(ephemeral=True)

        addedTotal, removedTotal = await self.syncBloomRoles()

        await commandInteraction.followup.send(
            f"Синхронизация завершена.\n"
            f"• Выдано ролей: **{addedTotal}**\n"
            f"• Снято ролей: **{removedTotal}**",
            ephemeral=True
        )


def setup(bot: commands.Bot):
    bot.add_cog(BloomSync(bot))
    print("cog: BloomCheck.py загружен")