import disnake
from disnake.ext import commands


# ==========================================
# VIEW ДЛЯ ОБРАБОТКИ НАЖАТИЙ ВНУТРИ V2
# ==========================================
class TestReviewView(disnake.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @disnake.ui.button(
        label="Принять",
        style=disnake.ButtonStyle.green,
        custom_id="test_accept_button"
    )
    async def acceptApplication(
        self,
        button: disnake.ui.Button,
        interaction: disnake.MessageInteraction
    ):
        await interaction.response.defer()

        # Обновляем контейнер на зелёный статус
        acceptedContainer = disnake.ui.Container(
            disnake.ui.Section(
                disnake.ui.TextDisplay(
                    content=f"## Заявка от {interaction.author.display_name}\nUser: {interaction.author.mention}"
                ),
                accessory=disnake.ui.Thumbnail(media=interaction.author.display_avatar.url)
            ),
            disnake.ui.Separator(divider=True),
            disnake.ui.TextDisplay(
                content=(
                    "**Ваш никнейм в майнкрафте:**\nSteve_Master\n\n"
                    "**Сколько вам полных лет:**\n17\n\n"
                    "**Откуда вы узнали о нашем сервере?**\nОт друзей\n\n"
                    "**Почему вы хотите играть на нашем сервере?**\nИщу уютный ванильный сервер\n\n"
                    "**Какой у вас стиль игры?**\nСтроительство городов и ферм\n"
                )
            ),
            accent_colour=disnake.Colour(0x59A46B)
        )

        await interaction.message.edit(components=[acceptedContainer])

    @disnake.ui.button(
        label="Отклонить",
        style=disnake.ButtonStyle.red,
        custom_id="test_decline_button"
    )
    async def declineApplication(
        self,
        button: disnake.ui.Button,
        interaction: disnake.MessageInteraction
    ):
        await interaction.response.defer()

        # Обновляем контейнер на красный статус
        declinedContainer = disnake.ui.Container(
            disnake.ui.Section(
                disnake.ui.TextDisplay(
                    content=f"## Заявка от {interaction.author.display_name}\nUser: {interaction.author.mention}"
                ),
                accessory=disnake.ui.Thumbnail(media=interaction.author.display_avatar.url)
            ),
            disnake.ui.Separator(divider=True),
            disnake.ui.TextDisplay(
                content=(
                    "**Ваш никнейм в майнкрафте:**\nSteve_Master\n\n"
                    "**Сколько вам полных лет:**\n17\n\n"
                    "**Откуда вы узнали о нашем сервере?**\nОт друзей\n\n"
                    "**Почему вы хотите играть на нашем сервере?**\nИщу уютный ванильный сервер\n\n"
                    "**Какой у вас стиль игры?**\nСтроительство городов и ферм\n"
                )
            ),
            accent_colour=disnake.Colour(0xA45959)
        )

        await interaction.message.edit(components=[declinedContainer])


# ==========================================
# ОСНОВНОЙ ТЕСТОВЫЙ COG
# ==========================================
class TestComponentsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.persistentViewsRegistered = False

    @commands.slash_command(
        name="testmsg",
        description="Отправить тестовое сообщение заявки на Components V2"
    )
    async def testMsgCommand(self, ctx: disnake.ApplicationCommandInteraction):
        adminUserId = 642671410451447838
        if ctx.author.id != adminUserId:
            await ctx.send("У вас нет прав на выполнение этой команды.", ephemeral=True)
            return

        mockMember = ctx.author

        # Сборка содержимого внутри контейнера
        testContainer = disnake.ui.Container(
            # 1. Шапка: Текст слева + Аватар справа через accessory
            disnake.ui.Section(
                disnake.ui.TextDisplay(
                    content=f"## Добро пожаловать на Vespera!\n@MiFo, ваша заявка на whitelist была успешно принята - мы рады видеть вас на нашем сервере"
                ),
                accessory=disnake.ui.Thumbnail(media=mockMember.display_avatar.url)
            ),
            # 2. Разделительная черта
            disnake.ui.Separator(divider=True),
            # 3. Основной текст анкеты и статус
            disnake.ui.TextDisplay(
                content=(
                    "## Как зайти на сервер?\n"
                    "**Айпи сервера:** play.vespera.fun\n"
                    "**Версия:** 1.21.11"
                )
            ),
            # 4. Промежуточный отступ и футер
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
            # 5. Кнопки действий прямо внутри структуры
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

        # Отправляем сообщение только с компонентами
        await ctx.channel.send(components=[testContainer])
        await ctx.send("Тестовое сообщение успешно отправлено!", ephemeral=True)

    @commands.Cog.listener()
    async def on_connect(self):
        if not self.persistentViewsRegistered:
            self.bot.add_view(TestReviewView(self.bot))
            self.persistentViewsRegistered = True


def setup(bot: commands.Bot):
    bot.add_cog(TestComponentsCog(bot))
    print("cog: TestMessage.py загружен")