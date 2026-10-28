import os
from pathlib import Path


import yaml
import disnake
from disnake.ext import commands
import traceback

intents = disnake.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

def loadMainConfig() -> dict:
    configPath = Path("config.yaml")
    if not configPath.exists():
        raise FileNotFoundError("Файл config.yaml не найден.")
    with open(configPath, "r", encoding="utf-8") as fileStream:
        return yaml.safe_load(fileStream) or {}

mainConfig = loadMainConfig()

class Config:
    BOT_TOKEN = mainConfig.get("bot_token")

for file in os.listdir("./cogs"):
    if file.endswith(".py"):
        extensionName = f"cogs.{file[:-3]}"
        try:
            bot.load_extension(extensionName)
        except Exception as e:
            print(f"[ERROR] Не удалось загрузить {extensionName}:")
            traceback.print_exc()

bot.run(Config.BOT_TOKEN)
