import time
from pathlib import Path

import aiohttp
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

cogConfig = loadMainConfig().get("radio", {})

class Config:
    # Роли
    COOLDOWN_SECONDS = cogConfig.get("cooldowntime", 3600)

    # Файлы
    filesConfig = loadMainConfig().get("files", {})
    CONFIG_PATH = Path(filesConfig.get("radio_config", "radio_config.yaml"))
    MESSAGE_ID_PATH = Path(filesConfig.get("radio_message_id_file", "radio_message_id.txt"))


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


def saveConfig(data: dict) -> None:
    writeYamlFile(Config.CONFIG_PATH, data)


def parseHexColor(hexString: str | None, defaultColor: int = 0x4F3D74) -> int:
    if not hexString:
        return defaultColor
    try:
        cleanHex = hexString.replace("#", "").strip()
        return int(cleanHex, 16)
    except ValueError:
        return defaultColor


def findRadioStationUser(
    memberUser: disnake.User | disnake.Member,
    radiosDict: dict
) -> tuple[str | None, dict | None]:
    for candidateKey in (memberUser.name, memberUser.display_name):
        if candidateKey in radiosDict:
            return candidateKey, radiosDict[candidateKey]
    return None, None


# ==========================================
# МОДАЛЬНЫЕ ОКНА
# ==========================================
class RadioBroadcastModal(disnake.ui.Modal):
    def __init__(self):
        modalComponents = [
            disnake.ui.TextInput(
                label="Заголовок",
                placeholder="Заголовок (необязательно)",
                custom_id="news_title",
                required=False,
                max_length=256
            ),
            disnake.ui.TextInput(
                label="Основной текст",
                style=disnake.TextInputStyle.paragraph,
                placeholder="Текст новости",
                custom_id="news_body",
                required=True,
                max_length=4000
            ),
            disnake.ui.TextInput(
                label="Изображение (URL)",
                placeholder="https://...",
                custom_id="news_image_url",
                required=False,
                max_length=1024
            )
        ]
        super().__init__(
            title="Отправить новость в эфир",
            components=modalComponents,
            custom_id="radio_broadcast_modal"
        )

    async def callback(self, interaction: disnake.ModalInteraction):
        appConfig = loadConfig()
        radiosDict = appConfig.get("radios", {})
        
        stationUserKey, radioEntry = findRadioStationUser(interaction.author, radiosDict)
        if not radioEntry or not radioEntry.get("settlement"):
            await interaction.response.send_message(
                "— Сигнал потерян. Пожалуйста, обратитесь к администрации.",
                ephemeral=True
            )
            return

        settlementName = radioEntry.get("settlement")
        embedColorHex = radioEntry.get("embed_col")
        flagUrl = radioEntry.get("flag_url")
        radioStationId = radioEntry.get("id")

        newsTitle = interaction.text_values.get("news_title")
        newsBody = interaction.text_values.get("news_body")
        newsImageUrl = interaction.text_values.get("news_image_url")

        embedColor = parseHexColor(embedColorHex)
        broadcastEmbed = disnake.Embed(
            title=newsTitle if newsTitle else None,
            description=newsBody,
            color=embedColor
        )

        if newsImageUrl:
            broadcastEmbed.set_image(url=newsImageUrl)

        postChannelId = appConfig.get("post_channel_id")
        webhookUrl = appConfig.get("webhook_url")
        pingRoleId = appConfig.get("ping_role_id")
        pingContent = f"<@&{pingRoleId}>" if pingRoleId else None

        if webhookUrl:
            async with aiohttp.ClientSession() as httpClientSession:
                webhookInstance = disnake.Webhook.from_url(webhookUrl, session=httpClientSession)
                try:
                    await webhookInstance.send(
                        avatar_url=flagUrl,
                        username=f"{settlementName} / st. {radioStationId}",
                        content=pingContent,
                        embeds=[broadcastEmbed],
                        wait=True
                    )
                    await interaction.response.send_message("— Сообщение отправлено в эфир!", ephemeral=True)

                    if stationUserKey:
                        radioEntry["last_post"] = time.time()
                        radiosDict[stationUserKey] = radioEntry
                        appConfig["radios"] = radiosDict
                        saveConfig(appConfig)

                except Exception as ex:
                    await interaction.response.send_message(f"— Помехи в работе webhook: {ex}", ephemeral=True)
                    return
        else:
            if not postChannelId or not interaction.guild:
                await interaction.response.send_message("— Не удалось найти нужную частоту", ephemeral=True)
                return

            targetChannel = interaction.guild.get_channel(int(postChannelId))
            if not targetChannel or not isinstance(targetChannel, disnake.TextChannel):
                await interaction.response.send_message("— Не удалось найти нужную частоту", ephemeral=True)
                return

            await targetChannel.send(content=pingContent, embed=broadcastEmbed)
            await interaction.response.send_message("— Сообщение отправлено в эфир!", ephemeral=True)


# ==========================================
# UI КОМПОНЕНТЫ И ВЬЮХИ
# ==========================================
class RadioControlView(disnake.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @disnake.ui.button(label="Выйти в эфир", style=disnake.ButtonStyle.gray, emoji="📢", custom_id="radio_send_button")
    async def triggerBroadcastModal(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        appConfig = loadConfig()
        radiosDict = appConfig.get("radios", {})
        
        _, radioEntry = findRadioStationUser(interaction.author, radiosDict)
        if radioEntry:
            lastPostTimestamp = radioEntry.get("last_post")
            if lastPostTimestamp:
                elapsedSeconds = time.time() - float(lastPostTimestamp)
                if elapsedSeconds < Config.COOLDOWN_SECONDS:
                    remainingSeconds = int(Config.COOLDOWN_SECONDS - elapsedSeconds)
                    remainingMinutes = remainingSeconds // 60
                    await interaction.response.send_message(
                        f"— Упс... Радиоэфир занят, ваша очередь будет через: {remainingMinutes}м",
                        ephemeral=True
                    )
                    return

        await interaction.response.send_modal(RadioBroadcastModal())


# ==========================================
# ОСНОВНОЙ COG
# ==========================================
class RadioCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.isPersistentViewRestored = False

    @commands.slash_command(name="radio", description="Создать сообщение для радио")
    async def spawnRadioPanel(self, ctx: disnake.ApplicationCommandInteraction):
        if not ctx.author.guild_permissions.administrator:
            await ctx.response.send_message("У вас нет прав администратора.", ephemeral=True)
            return

        panelEmbed = disnake.Embed(
            title="Радио",
            description="Нажмите на кнопку чтобы написать новость в эфир",
            color=0x4F3D74
        )
        panelEmbed.set_image(url="https://cdn.discordapp.com/attachments/1059799386110042153/1496732442529370112/RADIO.png?ex=69eaf436&is=69e9a2b6&hm=4d2788a669df8259e92861152f06bb7578eff2c7cfdfdf4c022ec447ced7791e&")
        
        panelView = RadioControlView()
        panelMessage = await ctx.channel.send(embed=panelEmbed, view=panelView)

        try:
            Config.MESSAGE_ID_PATH.write_text(str(panelMessage.id), encoding="utf-8")
            await ctx.response.send_message("Панель радио успешно создана и сохранена.", ephemeral=True)
        except Exception as ex:
            print(f"[RadioCog] Ошибка сохранения ID сообщения: {ex}")
            await ctx.response.send_message("Панель отправлена, но возникла ошибка сохранения ID.", ephemeral=True)

    @commands.slash_command(name="addradio", description="Добавить или обновить радиостанцию в конфиге")
    async def addRadioStation(
        self,
        ctx: disnake.ApplicationCommandInteraction,
        username: str,
        settlement: str,
        embedColor: str = commands.Param(name="embed_col", description="HEX цвет, например #4F3D74"),
        flagUrl: str = commands.Param(default=None, name="flag_url", description="Ссылка на аватар/флаг")
    ):
        if not ctx.author.guild_permissions.administrator:
            await ctx.response.send_message("У вас нет прав администратора.", ephemeral=True)
            return

        appConfig = loadConfig()
        radiosDict = appConfig.get("radios", {})

        existingStationIds = [
            stationData.get("id", 0)
            for stationData in radiosDict.values()
            if isinstance(stationData, dict) and stationData.get("id")
        ]
        nextStationId = (max(existingStationIds) + 1) if existingStationIds else 1

        stationData = radiosDict.get(username, {})
        stationData.update({
            "username": username,
            "settlement": settlement,
            "embed_col": embedColor,
            "flag_url": flagUrl,
            "id": stationData.get("id") or nextStationId
        })

        radiosDict[username] = stationData
        appConfig["radios"] = radiosDict
        saveConfig(appConfig)

        await ctx.response.send_message(f"Радиостанция `{username}` успешно сохранена (ID: {stationData['id']}).", ephemeral=True)

    @commands.slash_command(name="deleteradio", description="Удалить радиостанцию из конфига")
    async def deleteRadioStation(self, ctx: disnake.ApplicationCommandInteraction, username: str):
        if not ctx.author.guild_permissions.administrator:
            await ctx.response.send_message("У вас нет прав администратора.", ephemeral=True)
            return

        appConfig = loadConfig()
        radiosDict = appConfig.get("radios", {})

        if username in radiosDict:
            del radiosDict[username]
            appConfig["radios"] = radiosDict
            saveConfig(appConfig)
            await ctx.response.send_message(f"Радиостанция `{username}` удалена.", ephemeral=True)
        else:
            await ctx.response.send_message("Радиостанция с таким именем не найдена.", ephemeral=True)

    @commands.slash_command(name="listradio", description="Показать текущий конфиг радио")
    async def showConfig(self, ctx: disnake.ApplicationCommandInteraction):
        if not ctx.author.guild_permissions.administrator:
            await ctx.response.send_message("У вас нет прав администратора.", ephemeral=True)
            return

        appConfig = loadConfig()
        yamlFormattedText = yaml.dump(appConfig, default_flow_style=False, allow_unicode=True)
        await ctx.response.send_message(f"```yaml\n{yamlFormattedText}\n```", ephemeral=True)

    @commands.Cog.listener()
    async def on_connect(self):
        if self.isPersistentViewRestored:
            return

        if Config.MESSAGE_ID_PATH.exists():
            try:
                rawMessageId = Config.MESSAGE_ID_PATH.read_text(encoding="utf-8").strip()
                if rawMessageId.isdigit():
                    self.bot.add_view(RadioControlView(), message_id=int(rawMessageId))
                    self.isPersistentViewRestored = True
            except Exception as ex:
                print(f"[RadioCog] Ошибка восстановления persistent view: {ex}")


def setup(bot: commands.Bot):
    bot.add_cog(RadioCog(bot))
    print("cog: Radio.py загружен")