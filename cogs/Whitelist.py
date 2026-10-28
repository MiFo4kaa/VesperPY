import asyncio
from datetime import datetime, timezone
from pathlib import Path
import re

import aiomysql
import disnake
from disnake.ext import commands
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
cogConfig = mainConfig.get("whitelist", {})


class Config:
    ADMIN_USER_ID = mainConfig.get("admin_user_id")
    GUILD_ID = mainConfig.get("guild_id")
    REVIEW_CHANNEL_ID = cogConfig.get("review_channel_id")

    # Роли
    rolesConfig = cogConfig.get("roles", {})
    ROLE_APPLICATION_SUBMITTED = rolesConfig.get("application_submitted")
    ROLE_WHITELISTED = rolesConfig.get("whitelisted")
    ROLE_UNVERIFIED = rolesConfig.get("unverified")
    MODERATOR_ROLE_ID = mainConfig.get("moderator_role_id")

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

    # Ассеты
    filesConfig = mainConfig.get("files", {})
    ASSETS_PATH = filesConfig.get("assets_path", "assets")


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

    @classmethod
    async def save_application(cls, message_id: int, user_id: int, nick: str, raw_age: str, source_info: str, join_reason: str, bio_info: str):
        async with cls.pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Сохранение/обновление в whitelist_applicants
                await cur.execute(
                    """
                    INSERT INTO whitelist_applicants (message_id, user_id, nick)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE user_id = VALUES(user_id), nick = VALUES(nick)
                    """,
                    (message_id, user_id, nick)
                )

                # Сохранение/обновление в player_info
                await cur.execute(
                    """
                    INSERT INTO player_info (player, age, join_reason, source_info, bio, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                        age = VALUES(age),
                        join_reason = VALUES(join_reason),
                        source_info = VALUES(source_info),
                        bio = VALUES(bio),
                        timestamp = VALUES(timestamp)
                    """,
                    (nick, raw_age, join_reason, source_info, bio_info, datetime.now().timestamp())
                )

    @classmethod
    async def get_application(cls, message_id: int) -> dict | None:
        async with cls.pool.acquire() as conn:
            async with conn.cursor() as cur:
                query = """
                SELECT 
                    w.message_id,
                    w.user_id,
                    w.nick,
                    p.age,
                    p.join_reason,
                    p.source_info,
                    p.bio,
                    p.timestamp
                FROM whitelist_applicants w
                LEFT JOIN player_info p ON w.nick = p.player
                WHERE w.message_id = %s
                """
                await cur.execute(query, (message_id,))
                return await cur.fetchone()


# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (RCON & UI)
# ==========================================
async def api_whitelist_add(minecraft_nick: str) -> bool:
    """Отправляет POST-запрос к VesperBridge API на добавление никнейма в вайтлист."""
    url = f"{Config.API_BASE_URL}/api/whitelist/add"
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
                    print(f"[API] {minecraft_nick} обработан плагином: {data.get('status')}")
                    return True
                else:
                    error_text = await response.text()
                    print(f"[API Error] Сервер вернул код {response.status}: {error_text}")
                    return False
    except Exception as err:
        print(f"[API Connection Error]: {err}")
        return False


def calculateAccountAge(createdAt: datetime) -> tuple[int, str]:
    delta = datetime.now(timezone.utc) - createdAt
    totalDays = delta.days
    years = totalDays // 365
    months = (totalDays % 365) // 30

    if years > 0:
        formattedAge = f"{years} г. {months} мес."
    elif months > 0:
        formattedAge = f"{months} мес."
    else:
        formattedAge = f"{totalDays} дн."

    return totalDays, formattedAge


def createApplicationContainer(
    applicantUser: disnake.User | disnake.Member,
    minecraftNick: str,
    rawAge: str,
    sourceInfo: str,
    joinReason: str,
    bioInfo: str,
    accountAgeFormatted: str,
    isAutoRejected: bool = False
) -> disnake.ui.Container:
    applicationDetails = (
        f"**Ваш никнейм в майнкрафте:**\n{minecraftNick}\n\n"
        f"**Сколько вам полных лет?**\n{rawAge}\n\n"
        f"**Откуда вы узнали о нашем сервере?**\n{sourceInfo}\n\n"
        f"**Чем вас заинтересовал наш сервер?**\n{joinReason}\n\n"
        f"**Расскажите о себе:**\n{bioInfo}\n"
    )

    if not isAutoRejected:
        contentMessage = f"## Заявка от {applicantUser.display_name}\nUser: {applicantUser.mention}\n||Ping: <@&{Config.MODERATOR_ROLE_ID}>||"
    else:
        contentMessage = f"## Заявка от {applicantUser.display_name}\nUser: {applicantUser.mention}"

    containerComponents = [
        disnake.ui.Section(
            disnake.ui.TextDisplay(content=contentMessage),
            accessory=disnake.ui.Thumbnail(media=applicantUser.display_avatar.url)
        ),
        disnake.ui.Separator(divider=True),
        disnake.ui.TextDisplay(content=applicationDetails),
        disnake.ui.Separator(divider=False),
        disnake.ui.TextDisplay(content=f"-# Возраст аккаунта: {accountAgeFormatted}")
    ]

    if not isAutoRejected:
        containerComponents.extend([
            disnake.ui.Separator(divider=True),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Принять",
                    style=disnake.ButtonStyle.green,
                    custom_id="accept_button"
                ),
                disnake.ui.Button(
                    label="Отклонить",
                    style=disnake.ButtonStyle.red,
                    custom_id="decline_button"
                )
            )
        ])
        accentColour = disnake.Colour(0xA49B59)
    else:
        accentColour = disnake.Colour(0xA45959)

    return disnake.ui.Container(*containerComponents, accent_colour=accentColour)


# ==========================================
# МОДАЛЬНЫЕ ОКНА И КНОПКИ
# ==========================================
class RecruitementModal(disnake.ui.Modal):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        modalComponents = [
            disnake.ui.TextInput(
                label="Ваш никнейм в майнкрафте:",
                custom_id="minecraftNick",
                required=True
            ),
            disnake.ui.TextInput(
                label="Сколько вам полных лет?",
                custom_id="userAge",
                required=True
            ),
            disnake.ui.TextInput(
                label="Откуда вы узнали о нашем сервере?",
                custom_id="sourceInfo",
                required=True
            ),
            disnake.ui.TextInput(
                label="Чем вас заинтересовал наш сервер?",
                style=disnake.TextInputStyle.long,
                custom_id="joinReason",
                required=True
            ),
            disnake.ui.TextInput(
                label="Расскажите о себе:",
                style=disnake.TextInputStyle.long,
                custom_id="bioInfo",
                required=True
            )
        ]
        super().__init__(
            title="Подать заявку в вайтлист",
            components=modalComponents,
            custom_id="recruitementModal"
        )

    async def callback(self, modalInteraction: disnake.ModalInteraction) -> None:
        applicantMember = modalInteraction.author
        minecraftNick = modalInteraction.text_values["minecraftNick"]
        rawAge = modalInteraction.text_values["userAge"]
        sourceInfo = modalInteraction.text_values["sourceInfo"]
        joinReason = modalInteraction.text_values["joinReason"]
        bioInfo = modalInteraction.text_values["bioInfo"]

        ageMatch = re.search(r"\d+", rawAge)
        parsedAge = int(ageMatch.group()) if ageMatch else None

        # Установка ника и выдача начальной роли
        try:
            await applicantMember.edit(nick=minecraftNick)
        except disnake.Forbidden:
            pass

        pendingRole = modalInteraction.guild.get_role(Config.ROLE_APPLICATION_SUBMITTED)
        if pendingRole:
            await applicantMember.add_roles(pendingRole)

        confirmEmbed = disnake.Embed(
            color=0x3474EB,
            title="Заявка успешно отправлена!",
            description=f"{applicantMember.mention}, Вы успешно подали заявку в вайтлист!\nМы рассмотрим ее в ближайшее время."
        )
        confirmEmbed.set_thumbnail(url=applicantMember.display_avatar.url)
        await modalInteraction.response.send_message(embed=confirmEmbed, ephemeral=True)

        accountDays, accountAgeFormatted = calculateAccountAge(applicantMember.created_at)
        isAutoRejected = accountDays <= 60 or (parsedAge is not None and parsedAge < 14)

        reviewContainer = createApplicationContainer(
            applicantUser=applicantMember,
            minecraftNick=minecraftNick,
            rawAge=rawAge,
            sourceInfo=sourceInfo,
            joinReason=joinReason,
            bioInfo=bioInfo,
            accountAgeFormatted=accountAgeFormatted,
            isAutoRejected=isAutoRejected
        )

        reviewChannel = modalInteraction.guild.get_channel(Config.REVIEW_CHANNEL_ID)
        reviewMessage = await reviewChannel.send(components=[reviewContainer])

        await Database.save_application(
            message_id=reviewMessage.id,
            user_id=applicantMember.id,
            nick=minecraftNick,
            raw_age=rawAge,
            source_info=sourceInfo,
            join_reason=joinReason,
            bio_info=bioInfo
        )

        if isAutoRejected:
            try:
                await applicantMember.send("Ваша заявка была отклонена")
                await applicantMember.ban(reason="Заявка в whitelist была отклонена автоматически")
            except (disnake.Forbidden, disnake.HTTPException):
                pass


class RecruitementSelectView(disnake.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @disnake.ui.button(label="Подать заявку", row=0, style=disnake.ButtonStyle.gray, emoji='📩', custom_id="WL_button")
    async def openApplicationModal(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        submittedRole = interaction.guild.get_role(Config.ROLE_APPLICATION_SUBMITTED)
        whitelistedRole = interaction.guild.get_role(Config.ROLE_WHITELISTED)

        if submittedRole in interaction.author.roles:
            errorEmbed = disnake.Embed(
                color=0xFF0000,
                title="Заявка не была отправлена",
                description=f"{interaction.author.mention}, вы уже подали заявку в whitelist\n*Если вы хотите что-то дополнить или изменить в заявке, напишите в* <#1372989355970265270>"
            )
            errorEmbed.set_thumbnail(url=interaction.author.display_avatar.url)
            await interaction.response.send_message(embed=errorEmbed, ephemeral=True)
            return

        if whitelistedRole in interaction.author.roles:
            errorEmbed = disnake.Embed(
                color=0xFF0000,
                title="Заявка не была отправлена",
                description=f"{interaction.author.mention}, вы уже находитесь в вайтлисте"
            )
            errorEmbed.set_thumbnail(url=interaction.author.display_avatar.url)
            await interaction.response.send_message(embed=errorEmbed, ephemeral=True)
            return

        await interaction.response.send_modal(RecruitementModal(self.bot))


class DecideView(disnake.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @disnake.ui.button(label="Принять", row=0, style=disnake.ButtonStyle.green, custom_id="accept_button")
    async def acceptApplication(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        await interaction.response.defer()

        # Получаем данные заявки из MySQL
        app_data = await Database.get_application(interaction.message.id)

        if not app_data:
            await interaction.followup.send("Заявка не найдена в базе данных.", ephemeral=True)
            return

        applicantId = app_data["user_id"]
        minecraftNick = app_data["nick"]

        guild = interaction.guild
        targetGuildMember = guild.get_member(applicantId)
        targetUser = await self.bot.fetch_user(applicantId)

        applicationDetails = (
            f"**Ваш никнейм в майнкрафте:**\n{minecraftNick}\n\n"
            f"**Сколько вам полных лет?**\n{app_data.get('age') or 'Не указан'}\n\n"
            f"**Откуда вы узнали о нашем сервере?**\n{app_data.get('source_info') or 'Не указано'}\n\n"
            f"**Чем вас заинтересовал наш сервер?**\n{app_data.get('join_reason') or 'Не указано'}\n\n"
            f"**Расскажите о себе:**\n{app_data.get('bio') or 'Не указан'}\n"
        )

        if targetGuildMember is None:
            leftContainer = disnake.ui.Container(
                disnake.ui.Section(
                    disnake.ui.TextDisplay(
                        content=f"## Заявка от {targetUser.display_name}\nUser: {targetUser.mention}"
                    ),
                    accessory=disnake.ui.Thumbnail(media=targetUser.display_avatar.url)
                ),
                disnake.ui.Separator(divider=True),
                disnake.ui.TextDisplay(content=applicationDetails),
                accent_colour=disnake.Colour(0xA45959)
            )
            await interaction.message.edit(components=[leftContainer])
            return

        # API запрос
        apiSuccess = await api_whitelist_add(minecraftNick)

        assetsPath = Config.ASSETS_PATH
        serverLogo = disnake.File(f"{assetsPath}/LOGO.gif", filename="logo.gif")

        welcomeContainer = disnake.ui.Container(
            disnake.ui.Section(
                disnake.ui.TextDisplay(
                    content=f"## Добро пожаловать на Vespera!\n<@{applicantId}>, ваша заявка на whitelist была успешно принята - мы рады видеть вас на нашем сервере"
                ),
                accessory=disnake.ui.Thumbnail(media="attachment://logo.gif")
            ),
            disnake.ui.Separator(divider=True),
            disnake.ui.TextDisplay(
                content=(
                    "## Как зайти на сервер?\n"
                    "**Айпи сервера:** play.vespera.fun\n"
                    "**Версия:** 1.21.11"
                )
            ),
            disnake.ui.Separator(divider=True),
            disnake.ui.TextDisplay(
                content=(
                    "## Основные команды на сервере:\n\n"
                    "> **!<сообщение>** - написать в глобальный чат\n"
                    "> **/m <ник> <сообщение>** - личное сообщение игроку\n"
                    "> **/sit** - присесть на поверхность\n\n"
                    "Команды, фишки и нововведения сервера:\n"
                )
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Вики",
                    style=disnake.ButtonStyle.url,
                    url="https://wiki.vespera.fun/"
                )
            ),
            disnake.ui.Separator(divider=True),
            disnake.ui.TextDisplay(
                content=(
                    "## Нужна помощь?\n\n"
                    "Если у вас возникли вопросы или проблемы на сервере\n"
                    "нажмите на кнопку ниже:\n"
                )
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Помощь",
                    style=disnake.ButtonStyle.red,
                    emoji="🆘",
                    url="https://discord.com/channels/947609711845462116/1372989355970265270"
                )
            ),
            accent_colour=disnake.Colour(0x59A46B)
        )

        try:
            await targetUser.send(file=serverLogo, components=[welcomeContainer])
        except (disnake.Forbidden, disnake.HTTPException):
            pass

        # Роли
        rolesToAdd = [guild.get_role(Config.ROLE_WHITELISTED)]
        rolesToRemove = [
            guild.get_role(Config.ROLE_UNVERIFIED),
            guild.get_role(Config.ROLE_APPLICATION_SUBMITTED)
        ]
        await targetGuildMember.add_roles(*[r for r in rolesToAdd if r])
        await targetGuildMember.remove_roles(*[r for r in rolesToRemove if r])

        accentColour = disnake.Colour(0x59A46B) if apiSuccess else disnake.Colour(0xE09F3E)

        acceptedContainer = disnake.ui.Container(
            disnake.ui.Section(
                disnake.ui.TextDisplay(
                    content=f"## Заявка от {targetGuildMember.display_name}\nUser: {targetGuildMember.mention}"
                ),
                accessory=disnake.ui.Thumbnail(media=targetGuildMember.display_avatar.url)
            ),
            disnake.ui.Separator(divider=True),
            disnake.ui.TextDisplay(content=applicationDetails),
            accent_colour=accentColour
        )

        await interaction.message.edit(components=[acceptedContainer])

    @disnake.ui.button(label="Отклонить", row=0, style=disnake.ButtonStyle.red, custom_id="decline_button")
    async def declineApplication(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        await interaction.response.defer()

        # Получаем данные заявки из MySQL
        app_data = await Database.get_application(interaction.message.id)

        if not app_data:
            await interaction.followup.send("Заявка не найдена в базе данных.", ephemeral=True)
            return

        applicantId = app_data["user_id"]
        minecraftNick = app_data["nick"]

        guild = interaction.guild
        targetGuildMember = guild.get_member(applicantId)
        targetUser = await self.bot.fetch_user(applicantId)

        applicationDetails = (
            f"**Ваш никнейм в майнкрафте:**\n{minecraftNick}\n\n"
            f"**Сколько вам полных лет?**\n{app_data.get('age') or 'Не указан'}\n\n"
            f"**Откуда вы узнали о нашем сервере?**\n{app_data.get('source_info') or 'Не указано'}\n\n"
            f"**Чем вас заинтересовал наш сервер?**\n{app_data.get('join_reason') or 'Не указано'}\n\n"
            f"**Расскажите о себе:**\n{app_data.get('bio') or 'Не указан'}\n"
        )

        declinedContainer = disnake.ui.Container(
            disnake.ui.Section(
                disnake.ui.TextDisplay(
                    content=f"## Заявка от {targetUser.display_name}\nUser: {targetUser.mention}"
                ),
                accessory=disnake.ui.Thumbnail(media=targetUser.display_avatar.url)
            ),
            disnake.ui.Separator(divider=True),
            disnake.ui.TextDisplay(content=applicationDetails),
            accent_colour=disnake.Colour(0xA45959)
        )

        await interaction.message.edit(components=[declinedContainer])

        if targetGuildMember is not None:
            try:
                await targetGuildMember.send("Ваша заявка была отклонена")
                await targetGuildMember.ban(reason="Заявка в whitelist была отклонена")
            except (disnake.Forbidden, disnake.HTTPException):
                pass


# ==========================================
# ОСНОВНОЙ COG
# ==========================================
class Recruitement(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.persistentViewsRegistered = False

    async def cog_load(self):
        # Инициализация пула соединений с БД при загрузке cog
        await Database.init()

    async def cog_unload(self):
        # Закрытие пула при выгрузке cog
        await Database.close()

    @commands.slash_command(description="Создать форму для подачи заявок в вайтлист")
    async def whitelist(self, ctx: disnake.ApplicationCommandInteraction):
        if ctx.author.id != Config.ADMIN_USER_ID:
            await ctx.send("У вас нет прав для выполнения этой команды.", ephemeral=True)
            return

        assetsPath = Config.ASSETS_PATH
        serverLogo = disnake.File(f"{assetsPath}/LOGO.gif", filename="logo.gif")

        whitelistContainer = disnake.ui.Container(
            disnake.ui.Section(
                disnake.ui.TextDisplay(
                    content=f"## Подать заявку в Whitelist\nПри нажатии на кнопку в конце сообщения,\nвы откроете форму для вашей заявки"
                ),
                accessory=disnake.ui.Thumbnail(media="attachment://logo.gif")
            ),
            disnake.ui.Separator(divider=True),
            disnake.ui.TextDisplay(
                content=(
                    "### Правила подачи заявки\n\n"
                    "1. Вам должно быть не менее 14 лет\n"
                    "2. Ваш Discord аккаунт должен быть создан не менее 2 месяцев назад\n"
                    "3. Заявка должна быть заполнена полностью и адекватно, без шуток\n"
                    "4. Ваш профиль, аватарка, содержание заявки не должны нарушать правила сервера\n"
                    "5. Заявка подается только 1 раз и одним аккаунтом, создание твинков, альт аккаунтов запрещено и может привести к блокировке вашего основного аккаунта"
                )
            ),
            disnake.ui.Separator(divider=False),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Подать заявку",
                    style=disnake.ButtonStyle.green,
                    custom_id="WL_button",
                    emoji="📩"
                )
            ),
            accent_colour=disnake.Colour(0x4F3D74)
        )

        await ctx.send(file=serverLogo, components=[whitelistContainer])

    @commands.Cog.listener()
    async def on_connect(self):
        if not self.persistentViewsRegistered:
            self.bot.add_view(RecruitementSelectView(self.bot))
            self.bot.add_view(DecideView(self.bot))
            self.persistentViewsRegistered = True


def setup(bot: commands.Bot):
    bot.add_cog(Recruitement(bot))
    print("cog: Whitelist.py загружен")