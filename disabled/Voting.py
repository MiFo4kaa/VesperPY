import disnake
from disnake.ext import commands

# ===== НАСТРОЙКИ =====

NOMINATIONS = {
    "player": {
        "title": "Игрок сезона",
        "description": "Бест оф зе бест игрок на веспере",
        "emoji": "<:z2_v:1460895209930887302>",
        "channel_id": 1490322181513805924
    },
    "volunteer": {
        "title": "Волонтер сезона",
        "description": "Пахает за респект и уважение",
        "emoji": "<:z1_nontilted:1373296166166466581>",
        "channel_id": 1490322228347273316
    },
    "charisma": {
        "title": "Харизма сезона",
        "description": "Главный любимец публики",
        "emoji": "<:sunglasses:1373293440443617370>",
        "channel_id": 1490322261964750939
    },
    "city": {
        "title": "Город сезона",
        "description": "Лучший город за весь сезон",
        "emoji": "🌃",
        "channel_id": 1490322405606817932
    },
    "delivery": {
        "title": "Завоз сезона",
        "description": "+ww respect moment",
        "emoji": "<:z3_upvote:1460902316520771594>",
        "channel_id": 1490322443817058355
    },
    "build": {
        "title": "Постройка сезона",
        "description": "Лучшая постройка за весь сезон",
        "emoji": "🏛️",
        "channel_id": 1490322482811375716
    },
    "event": {
        "title": "Ивент сезона",
        "description": "Самый крутой ивент за весь сезон",
        "emoji": "🎡",
        "channel_id": 1490322515900502066
    }
}

# хранение голосов
votes_storage = {key: set() for key in NOMINATIONS}


# ===== МОДАЛКА =====

class VoteModal(disnake.ui.Modal):

    def __init__(self, nomination_key: str):
        self.nomination_key = nomination_key
        nomination = NOMINATIONS[nomination_key]

        components = [
            disnake.ui.TextInput(
                label="Кто должен победить?",
                placeholder="Введите ник игрока или название",
                custom_id="vote",
                max_length=100
            )
        ]

        super().__init__(
            title=nomination["title"],
            components=components,
            custom_id=f"vote_modal_{nomination_key}"
        )

    async def callback(self, interaction: disnake.ModalInteraction):

        user_id = interaction.author.id

        if user_id in votes_storage[self.nomination_key]:
            await interaction.response.send_message(
                "❌ Вы уже голосовали в этой номинации.",
                ephemeral=True
            )
            return

        vote_text = interaction.text_values["vote"]
        nomination = NOMINATIONS[self.nomination_key]

        embed = disnake.Embed(
            title="✅ Голос отправлен",
            description=f"{interaction.author.mention}, спасибо за участие в голосовании!",
            color=0x2F3136
        )

        embed.add_field(
            name="Номинация",
            value=nomination["title"],
            inline=False
        )

        embed.add_field(
            name="Ваш голос",
            value=vote_text,
            inline=False
        )

        embed.set_thumbnail(url=interaction.author.display_avatar.url)

        await interaction.response.send_message(embed=embed, ephemeral=True)

        channel = interaction.guild.get_channel(nomination["channel_id"])

        if channel:
            await channel.send(
                f"🗳 Голос от {interaction.author.mention}\n"
                f"**{nomination['title']}**\n"
                f"{vote_text}"
            )

        votes_storage[self.nomination_key].add(user_id)


# ===== SELECT =====

class VoteSelect(disnake.ui.Select):

    def __init__(self):

        options = [
            disnake.SelectOption(
                label=data["title"],
                description=data["description"],
                emoji=data["emoji"],
                value=key
            )
            for key, data in NOMINATIONS.items()
        ]

        super().__init__(
            placeholder="Выберите номинацию...",
            options=options,
            min_values=1,
            max_values=1,
            custom_id="vote_select"
        )

    async def callback(self, interaction: disnake.MessageInteraction):
        nomination_key = self.values[0]
        await interaction.response.send_modal(VoteModal(nomination_key))


# ===== VIEW =====

class VoteView(disnake.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(VoteSelect())


# ===== COG =====

class Voting(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(description="ембед для голосования")
    async def voting(self, ctx):

        member = ctx.guild.get_member(ctx.author.id)
        if not member.guild_permissions.administrator:
            await ctx.response.send_message("У вас нет прав администратора.", ephemeral=True)
            return
        
        embed = disnake.Embed(
            title="🏆 Премия сезона Vespera",
            description="Выберите номинацию и проголосуйте",
            color=0x4f3d74
        )
        embed.set_image(url="https://i.postimg.cc/SNZ4txB4/232-20260405191048.png")

        await ctx.send(embed=embed, view=VoteView())

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(VoteView())


def setup(bot):
    bot.add_cog(Voting(bot))
    print("module: Голосование в премии загружен")