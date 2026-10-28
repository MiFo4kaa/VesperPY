import disnake
from disnake.ext import commands
from rcon.source import Client
import yaml
from datetime import datetime, timezone
from pathlib import Path
import re

intents = disnake.Intents.default()
intents.members = True 

class RecruitementModal(disnake.ui.Modal):
    def __init__(self, bot):
        self.bot = bot
        components = [
            disnake.ui.TextInput(label="Ваш никнейм в майнкрафте:", placeholder="", custom_id="nick"),
            disnake.ui.TextInput(label="Сколько вам полных лет:", placeholder="", custom_id="age"),
            disnake.ui.TextInput(label="Откуда вы узнали о нашем сервере?", style=disnake.TextInputStyle.long, placeholder="", custom_id="known"),
            disnake.ui.TextInput(label="Почему вы хотите играть на нашем сервере?", placeholder="", custom_id="irlname"),
            disnake.ui.TextInput(label="Какой у вас стиль игры?", style=disnake.TextInputStyle.long, placeholder="", custom_id="ideas")
        ]
        super().__init__(title="Подать заявку в вайтлист", components=components, custom_id="recruitementModal")

    async def callback(self, interaction: disnake.ModalInteraction) -> None:
        global nick
        dview=decide(self.bot)
        nick = interaction.text_values["nick"]
        irlname = interaction.text_values["irlname"]
        age = interaction.text_values["age"]
        known = interaction.text_values["known"]
        ideas = interaction.text_values["ideas"]

        match = re.search(r"\d+", age)
        if match:
            int_age = int(match.group())
        else:
            int_age = None

        global idA
        idA=interaction.author.id
        ourGuild = self.bot.get_guild(947609711845462116)
        guildMember = await ourGuild.fetch_member(idA)
        await disnake.Member.edit(interaction.author, nick=nick)
        await interaction.author.add_roles(interaction.guild.get_role(1373000908790829086))
        embed = disnake.Embed(color=0x3474eb, title="Заявка успешно отправлена!")
        embed.description = f"""{interaction.author.mention}, Вы успешно подали заявку в вайтлист!
мы рассмотрим ее в ближайшее время."""
        embed.set_thumbnail(url=interaction.author.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        created = interaction.author.created_at
        now = datetime.now(timezone.utc)

        delta = now - created
        days = delta.days

        years = days // 365
        months = (days % 365) // 30

        if years > 0:
            account_age = f"{years} г. {months} мес."
        elif months > 0:
            account_age = f"{months} мес."
        else:
            account_age = f"{days} дн."

        if days<=30:
            status = "❌ Отклонена (авто)"

            embed = disnake.Embed(
                title=None,
                color=0xA45959
            )

            msgContent=f"""**Статус:** {status}"""

            dview=None

            await guildMember.send("Ваша заявка была отклонена")
            await guildMember.ban(reason="Заявка в whitelist была отклонена")
        elif int_age is not None and int_age < 14:
            status = "❌ Отклонена (авто)"

            embed = disnake.Embed(
                title=None,
                color=0xA45959
            )
            msgContent=f"""**Статус:** {status}"""

            dview=None

            await guildMember.send("Ваша заявка была отклонена")
            await guildMember.ban(reason="Заявка в whitelist была отклонена")
        else:
            status = "⏳ На рассмотрении"

            embed = disnake.Embed(
                title=None,
                color=0xA49B59
            )

            msgContent=f"""||<@&1480621091679506594>||

**Статус:** {status}"""


        embed.description = f"""
**Ваш никнейм в майнкрафте:**
{nick}

**Сколько вам полных лет:**
{age}

**Откуда вы узнали о нашем сервере?**
{known}

**Почему вы хотите играть на нашем сервере?**
{irlname}

**Какой у вас стиль игры?**
{ideas}
"""
        embed.set_author(
            name=f"Заявка от {interaction.author}",
            icon_url=interaction.author.display_avatar.url
        )

        embed.set_footer(text=f"Возраст аккаунта: {account_age}")

        channel = interaction.guild.get_channel(1373232826920472586)

        msg = await channel.send(
            content=msgContent,
            embed=embed,
            view=dview
        )
        
        msgid=msg.id
        try:
            # Открыть файл для чтения существующих данных
            with open('whitelisters.yaml', 'r') as f:
                data = yaml.safe_load(f) or {}  # Если файл пустой, создать пустой словарь
        except FileNotFoundError:
            # Если файл не существует, создать пустой словарь
            data = {}
        #докс дата для отображения заявок
        try:
            with open('doxbin.yaml', 'r', encoding='utf-8') as f:
                dox_data = yaml.safe_load(f) or {}  
        except FileNotFoundError:
            dox_data = {}


        # Добавление новых данных в словарь
        data[msgid] = {'idA': idA, 'nick': nick}
        dox_data[nick] = {'irlname': irlname, 'age': age, 'known': known, 'ideas': ideas, 'timestamp': datetime.now().timestamp()}

        # Открыть файл для записи обновленных данных
        with open('whitelisters.yaml', 'w') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        with open('doxbin.yaml', 'w', encoding='utf-8') as f:
            yaml.dump(dox_data, f, default_flow_style=False, allow_unicode=True)

class RecruitementSelect(disnake.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    @disnake.ui.button(label="Подать заявку", row=0, style=disnake.ButtonStyle.gray, emoji='📩', custom_id="WL_button")
    async def RWL_button(self, button: disnake.ui.Button, interactionA: disnake.Interaction):
        banned_role1=interactionA.guild.get_role(1373000908790829086)
        banned_role2=interactionA.guild.get_role(1372998328366927964)
        if banned_role1 in interactionA.author.roles:
            embed = disnake.Embed(color=0xff0000, title="Заявка не была отправлена")
            embed.description = f"""{interactionA.author.mention}, вы уже подали заявку в whitelist
*Если вы хотите что-то дополнить или изменить в заявке, напишите в ЛС модерации или администрации*"""
            embed.set_thumbnail(url=interactionA.author.display_avatar.url)
            await interactionA.response.send_message(embed=embed, ephemeral=True)
        elif banned_role2 in interactionA.author.roles:
            embed = disnake.Embed(color=0xff0000, title="Заявка не была отправлена")
            embed.description = f"""{interactionA.author.mention}, вы уже находитесь в вайтлисте"""
            embed.set_thumbnail(url=interactionA.author.display_avatar.url)
            await interactionA.response.send_message(embed=embed, ephemeral=True)
        else:
            await interactionA.response.send_modal(RecruitementModal(self.bot))

class decide(disnake.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    @disnake.ui.button(label="Принять", row=0, style=disnake.ButtonStyle.green, custom_id="accept_button")
    async def da_button(self, button: disnake.ui.Button, interaction: disnake.Interaction):
        check_id = interaction.message.id

        with open('whitelisters.yaml', 'r') as f:
            data = yaml.safe_load(f)

        if check_id not in data:
            return

        d_idA = data[check_id]['idA']
        d_nick = data[check_id]['nick']

        guild = interaction.guild
        user = await self.bot.fetch_user(d_idA)
        mem = guild.get_member(d_idA)

        embed = interaction.message.embeds[0]

    # если пользователь вышел
        if mem is None:

            embed.color = 0xA45959
            await interaction.message.edit(
                content=f"""Заявка whitelist от <@{d_idA}>

**Статус:** ❌ Пользователь вышел с сервера""",
                embed=embed,
                view=None
            )
            return
        
        await user.send(
            f"""
# :hyacinth: Добро пожаловать на Vespera!
<@{d_idA}>, ваша заявка на **whitelist** была успешно **принята** - мы рады видеть вас на нашем сервере :herb:

> **IP сервера:** play.vespera.fun
> **Версия Minecraft:** 1.21.11

В этом канале вы найдёте **важную информацию** о сервере:
https://discord.com/channels/947609711845462116/1372992050777292910

## Основные команды сервера:

> **!<сообщение>** - написать в глобальный чат
> **/m <ник> <сообщение>** - личное сообщение игроку
> **/sit** - присесть на поверхность
> **/menu** - главное меню сервера
> **/bank** - меню банка
> **/vpass** - пропуск с наградами

Полный **список команд** и **все нововведения** доступны на нашей вики:
https://wiki.vespera.fun

## Нужна помощь?

Если у вас **возникли вопросы или проблемы** на сервере - обратитесь в:
https://discord.com/channels/947609711845462116/1372989355970265270

:four_leaf_clover: *Приятной игры на сервере!*
    """
        )
        await mem.add_roles(interaction.guild.get_role(1372998328366927964))
        await mem.remove_roles(interaction.guild.get_role(1373008541362819092))
        await mem.remove_roles(interaction.guild.get_role(1373000908790829086))
        with Client('213.152.43.22', 25680, passwd='MiFo134@!!2') as client:
            response = client.run('comfywl', 'add', d_nick)

        embed.color = 0x59A46B
        await interaction.message.edit(
            content=f"""Заявка whitelist от <@{d_idA}>

**Статус:** ✅ Принята""",
            embed=embed,
            view=None
        )

    @disnake.ui.button(label="Отклонить", row=0, style=disnake.ButtonStyle.red, custom_id="decline_button")
    async def dd_button(self, button: disnake.ui.Button, interaction1: disnake.Interaction):
        check_id1 = interaction1.message.id
        with open('whitelisters.yaml', 'r') as f:
            data = yaml.safe_load(f)
        if check_id1 in data:
            d_idA1 = data[check_id1]['idA']

        guild1 = self.bot.get_guild(947609711845462116)
        user1 = await self.bot.fetch_user(d_idA1)
        mem1 = await guild1.fetch_member(d_idA1)
        embed = interaction1.message.embeds[0]

        if mem1 is None:
            embed.color = 0xA45959
            await interaction.message.edit(
                content=f"""Заявка whitelist от <@{d_idA}>

**Статус:** ❌ Пользователь вышел с сервера""",
                embed=embed,
                view=None
            )
            return

        embed.color = 0xA45959
        await interaction1.message.edit(
            content=f"""Заявка whitelist от <@{d_idA1}>

**Статус:** ❌ Отклонена""",
            embed=embed,
            view=None
        )

        await mem1.send("Ваша заявка была отклонена")
        await mem1.ban(reason="Заявка в whitelist была отклонена")
        channel1 = interaction1.guild.get_channel(1373232826920472586)
        bmsg1 = await channel1.fetch_message(check_id1)


class Recruitement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.persistents_views_added = False
        # path where the last /whitelist message id will be stored
        self._storage_file = Path(__file__).parent / 'whitelist_message_id.txt'
    @commands.slash_command(description="создать ембед для вайтлистов")
    async def whitelist(self, ctx):
        if ctx.author.id==642671410451447838:
            view = RecruitementSelect(self.bot)
            wlembed = disnake.Embed(color=0x4F3D74, title="Подать заявку в Whitelist")
            wlembed.description = f"""При нажатии на кнопку вы откроете форму для заполнения заявки"""
            wlembed.set_image(url="https://i.postimg.cc/8CkK6stJ/JOIN.png")
            msg = await ctx.send(embed=wlembed, view=view)
            # persist the message id so the view can be restored after bot restart
            try:
                # If for some reason `ctx.send` returned None, try to find
                # the message we just sent by scanning recent messages.
                if msg is None:
                    channel = ctx.channel
                    async for m in channel.history(limit=10):
                        if m.author.id == self.bot.user.id and m.embeds:
                            em = m.embeds[0]
                            if em.title == "Подать заявку в Whitelist":
                                msg = m
                                break

                if msg is None:
                    print("Failed to capture whitelist message object after send; not saving id.")
                else:
                    self._storage_file.write_text(str(msg.id))
            except Exception as e:
                print(f"Failed to write whitelist message id: {e}")

    @commands.Cog.listener()
    async def on_connect(self):
        if self.persistents_views_added:
            return
        try:
            if self._storage_file.exists():
                raw = self._storage_file.read_text().strip()
                if raw:
                    msg_id = int(raw)
                    self.bot.add_view(RecruitementSelect(self.bot), message_id=msg_id)
                    self.persistents_views_added = True
        except Exception as e:
            print(f"Failed to restore persistent view for whitelist: {e}")


def setup(bot):
    bot.add_cog(Recruitement(bot))
    print("module: Whitelist загружен")
