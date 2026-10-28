from datetime import datetime, timezone
from pathlib import Path
import disnake
from disnake.ext import commands
import yaml


# ==========================================
# КОНФИГУРАЦИЯ И ПУТИ
# ==========================================
def loadMainConfig() -> dict:
    configPath = Path("config.yaml")
    if not configPath.exists():
        raise FileNotFoundError("Файл config.yaml не найден.")
    with open(configPath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

class Config:
    # Роли
    MODERATOR_ROLE_ID = loadMainConfig().get("moderator_role_id")

    # Файлы (оборачиваем в Path)
    filesConfig = loadMainConfig().get("files", {})
    TICKETS_DB_PATH = Path(filesConfig.get("tickets_db", "tickets.yaml"))
    META_DB_PATH = Path(filesConfig.get("tickets_meta", "tickets_meta.yaml"))
    CONFIG_PATH = Path(filesConfig.get("ticket_config", "tickets_config.yaml"))
    MESSAGE_ID_PATH = Path(filesConfig.get("ticket_message_id_file", "ticket_message_id.txt"))
    ASSETS_PATH = Path(filesConfig.get("assets_path", "assets"))


# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (I/O & YAML)
# ==========================================
def readYamlFile(filePath: Path) -> dict:
    if not filePath.exists():
        return {}
    try:
        with open(filePath, "r", encoding="utf-8") as fileStream:
            return yaml.safe_load(fileStream) or {}
    except Exception:
        return {}


def writeYamlFile(filePath: Path, data: dict) -> None:
    with open(filePath, "w", encoding="utf-8") as fileStream:
        yaml.dump(data, fileStream, default_flow_style=False, allow_unicode=True)

def loadConfig() -> dict:
    return readYamlFile(Config.CONFIG_PATH)


def getNextTicketNumber() -> int:
    metaData = readYamlFile(Config.META_DB_PATH)
    nextCounter = metaData.get("counter", 0) + 1
    metaData["counter"] = nextCounter
    writeYamlFile(Config.META_DB_PATH, metaData)
    return nextCounter


# ==========================================
# СОЗДАНИЕ ТИКЕТА
# ==========================================
async def createTicketFromSubmission(
    interaction: disnake.ModalInteraction,
    categoryTitle: str,
    formData: dict[str, str]
) -> None:
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    ticketAuthor = interaction.author

    if not guild:
        await interaction.followup.send("Ошибка: команда доступна только на сервере.", ephemeral=True)
        return

    ticketNumber = getNextTicketNumber()
    channelName = f"ticket-{str(ticketNumber).zfill(4)}"

    appConfig = loadConfig()
    moderatorRoleId = appConfig.get("moderator_role_id") or Config.MODERATOR_ROLE_ID
    targetCategoryId = appConfig.get("ticket_category_id")

    channelOverwrites = {
        guild.default_role: disnake.PermissionOverwrite(view_channel=False),
        ticketAuthor: disnake.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True)
    }

    moderatorRole = guild.get_role(moderatorRoleId) if moderatorRoleId else None
    if moderatorRole:
        channelOverwrites[moderatorRole] = disnake.PermissionOverwrite(
            view_channel=True, send_messages=True, read_messages=True
        )

    targetCategory = None
    if targetCategoryId:
        targetCategory = guild.get_channel(int(targetCategoryId))
    elif interaction.channel and interaction.channel.category:
        targetCategory = interaction.channel.category

    ticketChannel = await guild.create_text_channel(
        name=channelName,
        overwrites=channelOverwrites,
        category=targetCategory,
        topic=f"Тикет #{ticketNumber} | Автор: {ticketAuthor} ({ticketAuthor.id})"
    )

    ticketsDb = readYamlFile(Config.TICKETS_DB_PATH)
    ticketsDb[str(ticketChannel.id)] = {
        "ticket_number": ticketNumber,
        "creator_id": ticketAuthor.id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ticket_type": categoryTitle,
        "channel_category_id": ticketChannel.category.id if ticketChannel.category else None
    }
    writeYamlFile(Config.TICKETS_DB_PATH, ticketsDb)

    welcomeEmbed = disnake.Embed(
        description="Скоро вам ответит администрация,\nдля помощи с вашей проблемой",
        color=0x4F3D74
    )

    formattedDetails = "\n\n".join(f"{fieldKey}:\n{fieldValue}" for fieldKey, fieldValue in formData.items())
    detailsEmbed = disnake.Embed(
        title=categoryTitle,
        description=f"```\n{formattedDetails}\n```",
        color=0xA49B59
    )

    closeActionView = TicketCloseView(channelId=ticketChannel.id, creatorId=ticketAuthor.id)
    pingContent = f"{ticketAuthor.mention}, спасибо что обратились в поддержку"
    
    await ticketChannel.send(
        content=pingContent,
        embeds=[welcomeEmbed, detailsEmbed],
        view=closeActionView
    )

    normalizedCategory = categoryTitle.lower()
    if normalizedCategory == "смена ника":
        hintEmbed = disnake.Embed(
            description="Перед сменой ника, пожалуйста убедитесь,\nчто вы выложили все вещи из инвентаря на старом аккаунте",
            color=0xA45959
        )
        await ticketChannel.send(embed=hintEmbed)
    elif normalizedCategory == "создать поселение":
        hintEmbed = disnake.Embed(
            description="Вы на верном пути!\nВам осталось скинуть флаг и границы вашего поселения в данный чат",
            color=0x59A46B
        )
        await ticketChannel.send(embed=hintEmbed)

    await interaction.followup.send(f"Тикет создан: {ticketChannel.mention}", ephemeral=True)


# ==========================================
# МОДАЛЬНЫЕ ОКНА
# ==========================================
class GenericModal(disnake.ui.Modal):
    def __init__(self, categoryTitle: str):
        self.categoryTitle = categoryTitle
        components = [
            disnake.ui.TextInput(
                label="Описание",
                style=disnake.TextInputStyle.paragraph,
                placeholder="Подробно опишите вашу проблему/вопрос",
                custom_id="issue_description",
                required=True,
                max_length=4000
            )
        ]
        super().__init__(
            title=categoryTitle[:45],
            components=components,
            custom_id=f"ticket_modal_generic_{categoryTitle}"
        )

    async def callback(self, interaction: disnake.ModalInteraction):
        issueDescription = interaction.text_values["issue_description"]
        await createTicketFromSubmission(interaction, self.categoryTitle, {"Описание": issueDescription})


class ReportModal(disnake.ui.Modal):
    def __init__(self):
        components = [
            disnake.ui.TextInput(
                label="Ник игрока",
                placeholder="Ник нарушителя",
                custom_id="target_nickname",
                required=True,
                max_length=100
            ),
            disnake.ui.TextInput(
                label="Детали инцидента",
                style=disnake.TextInputStyle.paragraph,
                placeholder="Детальное описание происшествия",
                custom_id="incident_details",
                required=True,
                max_length=3000
            ),
            disnake.ui.TextInput(
                label="Время и доказательства",
                placeholder="<логи/видео/скрины> 18:00",
                custom_id="incident_evidence",
                required=False,
                max_length=500
            )
        ]
        super().__init__(title="Репорт на игрока", components=components, custom_id="ticket_modal_report")

    async def callback(self, interaction: disnake.ModalInteraction):
        formData = {
            "Ник игрока": interaction.text_values["target_nickname"],
            "Детали инцидента": interaction.text_values["incident_details"],
            "Время и доказательства": interaction.text_values.get("incident_evidence") or "Не указано"
        }
        await createTicketFromSubmission(interaction, "Репорт на игрока", formData)


class NicknameModal(disnake.ui.Modal):
    def __init__(self):
        components = [
            disnake.ui.TextInput(
                label="Старый никнейм",
                placeholder="Старый никнейм",
                custom_id="old_nickname",
                required=True,
                max_length=100
            ),
            disnake.ui.TextInput(
                label="Новый никнейм",
                placeholder="Новый никнейм",
                custom_id="new_nickname",
                required=True,
                max_length=100
            )
        ]
        super().__init__(title="Смена ника", components=components, custom_id="ticket_modal_nickname")

    async def callback(self, interaction: disnake.ModalInteraction):
        formData = {
            "Старый никнейм": interaction.text_values["old_nickname"],
            "Новый никнейм": interaction.text_values["new_nickname"]
        }
        await createTicketFromSubmission(interaction, "Смена ника", formData)


class SettlementModal(disnake.ui.Modal):
    def __init__(self):
        components = [
            disnake.ui.TextInput(
                label="Название поселения",
                placeholder="Название",
                custom_id="settlement_name",
                required=True,
                max_length=100
            ),
            disnake.ui.TextInput(
                label="Ники управляющих",
                placeholder="Ники через запятую",
                custom_id="settlement_leaders",
                required=True,
                max_length=300
            ),
            disnake.ui.TextInput(
                label="Ники жителей",
                style=disnake.TextInputStyle.paragraph,
                placeholder="Список ников жителей",
                custom_id="settlement_residents",
                required=False,
                max_length=2000
            ),
            disnake.ui.TextInput(
                label="Краткое описание",
                style=disnake.TextInputStyle.paragraph,
                placeholder="Краткое описание поселения",
                custom_id="settlement_summary",
                required=False,
                max_length=2000
            )
        ]
        super().__init__(title="Создание поселения", components=components, custom_id="ticket_modal_settlement")

    async def callback(self, interaction: disnake.ModalInteraction):
        formData = {
            "Название поселения": interaction.text_values["settlement_name"],
            "Ники управляющих": interaction.text_values["settlement_leaders"],
            "Ники жителей": interaction.text_values.get("settlement_residents") or "Не указаны",
            "Краткое описание": interaction.text_values.get("settlement_summary") or "Отсутствует"
        }
        await createTicketFromSubmission(interaction, "Создать поселение", formData)


# ==========================================
# UI КОМПОНЕНТЫ И ВЬЮХИ
# ==========================================
class TicketCategorySelect(disnake.ui.Select):
    def __init__(self):
        appConfig = loadConfig()
        categoriesDict = appConfig.get("categories", {})
        
        selectOptions = [
            disnake.SelectOption(
                label=data.get("label", key),
                value=key,
                description=data.get("description", ""),
                emoji=data.get("emoji")
            )
            for key, data in categoriesDict.items()
        ]

        if not selectOptions:
            selectOptions = [disnake.SelectOption(label="Другое", value="other")]

        super().__init__(
            placeholder="Выберите категорию вашего вопроса...",
            min_values=1,
            max_values=1,
            options=selectOptions,
            custom_id="ticket_main_select"
        )

    async def callback(self, interaction: disnake.MessageInteraction):
        selectedKey = self.values[0]
        appConfig = loadConfig()
        categoryInfo = appConfig.get("categories", {}).get(selectedKey, {})
        
        modalType = categoryInfo.get("modal", "generic")
        categoryLabel = categoryInfo.get("label", selectedKey)

        if modalType == "generic":
            await interaction.response.send_modal(GenericModal(categoryLabel))
        elif modalType == "report":
            await interaction.response.send_modal(ReportModal())
        elif modalType == "settlement":
            await interaction.response.send_modal(SettlementModal())
        elif modalType == "nickname":
            await interaction.response.send_modal(NicknameModal())
        else:
            await interaction.response.send_message("Неизвестный тип тикета.", ephemeral=True)


class TicketCreateView(disnake.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect())


class TicketCloseView(disnake.ui.View):
    def __init__(self, channelId: int, creatorId: int):
        super().__init__(timeout=None)
        self.channelId = channelId
        self.creatorId = creatorId

    @disnake.ui.button(label="Закрыть", style=disnake.ButtonStyle.gray, emoji="🔒", custom_id="ticket_close_button")
    async def closeTicket(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        ticketChannel = interaction.guild.get_channel(self.channelId) if interaction.guild else None
        if not ticketChannel:
            await interaction.response.send_message("Канал тикета не найден.", ephemeral=True)
            return

        creatorMember = interaction.guild.get_member(self.creatorId)
        if creatorMember:
            try:
                await ticketChannel.set_permissions(creatorMember, overwrite=disnake.PermissionOverwrite(view_channel=False))
            except Exception:
                pass

        actionView = ReopenDeleteView(channelId=self.channelId, creatorId=self.creatorId)
        closeNoticeMessage = await ticketChannel.send("Тикет закрыт. Выберите действие ниже:", view=actionView)
        actionView.closeMessageId = closeNoticeMessage.id
        await interaction.response.defer()


class ReopenDeleteView(disnake.ui.View):
    def __init__(self, channelId: int, creatorId: int, closeMessageId: int | None = None):
        super().__init__(timeout=None)
        self.channelId = channelId
        self.creatorId = creatorId
        self.closeMessageId = closeMessageId

    @disnake.ui.button(label="Открыть", style=disnake.ButtonStyle.gray, emoji="🔓", custom_id="ticket_reopen")
    async def reopenTicket(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        ticketChannel = interaction.guild.get_channel(self.channelId) if interaction.guild else None
        if not ticketChannel:
            await interaction.response.send_message("Канал тикета не найден.", ephemeral=True)
            return

        creatorMember = interaction.guild.get_member(self.creatorId)
        if creatorMember:
            try:
                await ticketChannel.set_permissions(
                    creatorMember,
                    overwrite=disnake.PermissionOverwrite(view_channel=True, send_messages=True)
                )
            except Exception as ex:
                await interaction.response.send_message(f"Не удалось обновить права: {ex}", ephemeral=True)
                return

        if self.closeMessageId:
            try:
                msg = await ticketChannel.fetch_message(self.closeMessageId)
                await msg.delete()
            except Exception:
                pass

        await ticketChannel.send(f"<@{self.creatorId}>, тикет снова открыт.")
        await interaction.response.defer()

    @disnake.ui.button(label="Удалить", style=disnake.ButtonStyle.red, emoji="🗑️", custom_id="ticket_delete")
    async def deleteTicket(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        ticketChannel = interaction.guild.get_channel(self.channelId) if interaction.guild else None
        if not ticketChannel:
            await interaction.response.send_message("Канал уже удален.", ephemeral=True)
            return

        await interaction.response.defer()
        
        ticketsDb = readYamlFile(Config.TICKETS_DB_PATH)
        ticketsDb.pop(str(self.channelId), None)
        writeYamlFile(Config.TICKETS_DB_PATH, ticketsDb)
        
        try:
            await ticketChannel.delete()
        except Exception:
            pass


# ==========================================
# ОСНОВНОЙ COG
# ==========================================
class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.isPersistentViewRestored = False

    @commands.slash_command(name="tickets", description="Создать сообщение для открытия тикетов")
    async def spawnTicketsPanel(self, ctx: disnake.ApplicationCommandInteraction):
        if not ctx.author.guild_permissions.administrator:
            await ctx.response.send_message("У вас нет прав администратора.", ephemeral=True)
            return

        assetsPath = Config.ASSETS_PATH
        ticketsThumbnail = disnake.File(f"{assetsPath}/TICKETS.png", filename="TICKETS.png")

        categorySelect = TicketCategorySelect()

        ticketContainer = disnake.ui.Container(
            disnake.ui.TextDisplay(
                content=f"## Нужна помощь?\nВыберите категорию вашего вопроса и подробно опишите вашу проблему"
            ),
            disnake.ui.Separator(divider=True),
            disnake.ui.MediaGallery(
                disnake.MediaGalleryItem(
                    media="attachment://TICKETS.png",
                    description="Нужна помощь?"
                )
            ),
            disnake.ui.Separator(divider=True),
            disnake.ui.ActionRow(categorySelect),
            accent_colour = disnake.Colour(0x4F3D74)
        )
        
        panelMessage = await ctx.channel.send(file=ticketsThumbnail,components=[ticketContainer])
        Config.MESSAGE_ID_PATH.write_text(str(panelMessage.id), encoding="utf-8")
        self.bot.add_view(TicketCreateView(), message_id=panelMessage.id)


    @commands.Cog.listener()
    async def on_connect(self):
        if self.isPersistentViewRestored:
            return

        if Config.MESSAGE_ID_PATH.exists():
            try:
                rawMessageId = Config.MESSAGE_ID_PATH.read_text(encoding="utf-8").strip()
                if rawMessageId.isdigit():
                    self.bot.add_view(TicketCreateView(), message_id=int(rawMessageId))
                    self.isPersistentViewRestored = True
            except Exception as ex:
                print(f"[TicketsCog] Ошибка восстановления persistent view: {ex}")


def setup(bot: commands.Bot):
    bot.add_cog(TicketsCog(bot))
    print("cog: Tickets.py загружен")