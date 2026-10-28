import disnake
from disnake.ext import commands
import datetime

intents = disnake.Intents.default()
intents.members = True 

class QAModal(disnake.ui.Modal):
    def __init__(self, bot):
        self.bot = bot
        components = [
            disnake.ui.TextInput(label="Ваш вопрос:", placeholder="", custom_id="question")
        ]
        super().__init__(title="Задать вопрос", components=components, custom_id="QAModal")

    async def callback(self, interaction: disnake.ModalInteraction) -> None:
        question = interaction.text_values["question"]
        now = datetime.datetime.utcnow()
        cooldowns = getattr(self.bot, 'qa_last_question', {})
        last = cooldowns.get(interaction.author.id)
        COOLDOWN_SECONDS = 8 * 60 * 60
        if last:
            elapsed = (now - last).total_seconds()
            if elapsed < COOLDOWN_SECONDS:
                rem = int(COOLDOWN_SECONDS - elapsed)
                hours, rem = divmod(rem, 3600)
                minutes, seconds = divmod(rem, 60)
                if hours:
                    fmt = f"{hours}ч {minutes}м"
                else:
                    fmt = f"{minutes}м {seconds}с"
                embed = disnake.Embed(color=0xff0000, title="Не торопитесь!")
                embed.description = f"""{interaction.author.mention}, Вы сможете зaдать следующий вопрос через: 
{fmt}."""
                embed.set_thumbnail(url=interaction.author.display_avatar.url)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

        # record the time of this successful submission
        if not hasattr(self.bot, 'qa_last_question'):
            self.bot.qa_last_question = {}
        self.bot.qa_last_question[interaction.author.id] = now

        embed = disnake.Embed(color=0x3474eb, title="Вопрос успешно отправлен")
        embed.description = f"""{interaction.author.mention}, Вы успешно задали свой вопрос!
осталось только дождаться рубрики Q&A."""
        embed.set_thumbnail(url=interaction.author.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        channel = interaction.guild.get_channel(1460143735307239575)
        msg = await channel.send(f"""**Вопрос от игрока:** 
{question}
""", view=None)

class QuestionSelect(disnake.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    @disnake.ui.button(label="Задать Вопрос", row=0, style=disnake.ButtonStyle.gray, emoji='❔', custom_id="QA_button")
    async def RQA_button(self, button: disnake.ui.Button, interactionA: disnake.Interaction):
            await interactionA.response.send_modal(QAModal(self.bot))


class Question(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.persistents_views_added = False
    @commands.slash_command(description="создать ембед для Q&A")
    async def qa(self, ctx):
        if ctx.author.id==642671410451447838:
            view = QuestionSelect(self.bot)
            wlembed = disnake.Embed(color=0x4F3D74, title="Задать вопрос MiFo4ka_")
            wlembed.description = f"""Нажмите на кнопку, что бы задать вопрос MiFo4ka_ для рубрики Q&A"""
            wlembed.set_image(url="https://i.postimg.cc/6qByWJBg/QNA.png")
            await ctx.send(embed=wlembed, view=view)        

    @commands.Cog.listener()
    async def on_connect(self):
        if self.persistents_views_added:
            return
        self.bot.add_view(QuestionSelect(self.bot), message_id=...)


def setup(bot):
    bot.add_cog(Question(bot))
    print("module: QA загружен")
