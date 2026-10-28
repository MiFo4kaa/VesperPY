import os
import disnake
from disnake.ext import commands
import traceback

intents = disnake.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

for file in os.listdir("./cogs"):
    if file.endswith(".py"):
        extensionName = f"cogs.{file[:-3]}"
        try:
            bot.load_extension(extensionName)
        except Exception as e:
            print(f"[ERROR] Не удалось загрузить {extensionName}:")
            traceback.print_exc()

bot.run("MTM4OTkzMDQ3ODA2ODU2NDI1MA.G4vrPK.W2f8E4awleIGWwR56zY9kYeQ8bqmZxyY8feer8")
