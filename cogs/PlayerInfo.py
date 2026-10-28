import datetime
from pathlib import Path
import aiomysql
import disnake
from disnake.ext import commands
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


class Config:
    # Роли
    MODERATOR_ROLE_ID = mainConfig.get("moderator_role_id")

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
                maxsize=5
            )

    @classmethod
    async def close(cls):
        if cls.pool:
            cls.pool.close()
            await cls.pool.wait_closed()

    @classmethod
    async def get_player_info(cls, nick: str) -> dict | None:
        async with cls.pool.acquire() as conn:
            async with conn.cursor() as cur:
                query = """
                SELECT 
                    player,
                    age,
                    join_reason,
                    source_info,
                    bio,
                    timestamp
                FROM player_info
                WHERE LOWER(player) = LOWER(%s)
                LIMIT 1
                """
                await cur.execute(query, (nick,))
                return await cur.fetchone()


# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (UI & ФОРМАТИРОВАНИЕ)
# ==========================================
def formatTimestamp(rawTimestamp: float | int | None) -> str:
    if not rawTimestamp:
        return "неизвестно"
    dateInstance = datetime.datetime.fromtimestamp(rawTimestamp)
    return dateInstance.strftime("%d/%m/%Y %H:%M")


def buildPlayerInfoContainer(applicationData: dict) -> disnake.ui.Container:
    player_nick = applicationData.get("player", "—")
    applicationDetails = (
        f"**Ваш никнейм в майнкрафте:**\n{player_nick}\n\n"
        f"**Сколько вам полных лет?**\n{applicationData.get('age') or '—'}\n\n"
        f"**Откуда вы узнали о нашем сервере?**\n{applicationData.get('source_info') or '—'}\n\n"
        f"**Чем вас заинтересовал наш сервер?**\n{applicationData.get('join_reason') or '—'}\n\n"
        f"**Расскажите о себе:**\n{applicationData.get('bio') or '—'}\n"
    )

    formattedSubmittedDate = formatTimestamp(applicationData.get("timestamp"))

    return disnake.ui.Container(
        disnake.ui.TextDisplay(content=f"## Заявка от {player_nick}\n"),
        disnake.ui.Separator(divider=True),
        disnake.ui.TextDisplay(content=applicationDetails),
        disnake.ui.Separator(divider=False),
        disnake.ui.TextDisplay(content=f"-# Дата подачи заявки: {formattedSubmittedDate}"),
        accent_colour=disnake.Colour(0x4F3D74)
    )


# ==========================================
# COG
# ==========================================
class PlayerInfoViewer(commands.Cog):
    def __init__(self, botInstance: commands.Bot) -> None:
        self.botInstance = botInstance

    async def cog_load(self):
        await Database.init()

    async def cog_unload(self):
        await Database.close()

    @commands.slash_command(
        name="info",
        description="Информация об игроке (только для администрации)"
    )
    async def getPlayerInfo(
        self,
        interaction: disnake.ApplicationCommandInteraction,
        nick: str = commands.Param(description="Никнейм игрока для поиска в базе")
    ) -> None:
        hasModeratorRole = any(role.id == Config.MODERATOR_ROLE_ID for role in interaction.author.roles)
        hasAdminAccess = interaction.author.guild_permissions.administrator

        if not (hasModeratorRole or hasAdminAccess):
            await interaction.response.send_message(
                "У вас нет необходимой роли для выполнения этой команды.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=False)

        playerRecord = await Database.get_player_info(nick)
        if not playerRecord:
            await interaction.followup.send(
                f"Ник `{nick}` не найден в базе данных.",
                ephemeral=True
            )
            return

        infoContainer = buildPlayerInfoContainer(applicationData=playerRecord)
        await interaction.followup.send(components=[infoContainer])


def setup(botInstance: commands.Bot) -> None:
    botInstance.add_cog(PlayerInfoViewer(botInstance))
    print("cog: PlayerInfo.py загружен")