import asyncio
from collections import deque
from pathlib import Path
import re

import disnake
from disnake.ext import commands
from openai import OpenAI
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

cogConfig = loadMainConfig().get("chating", {})

class Config:
    OPENROUTER_API_KEY = cogConfig.get("api_key", "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")
    OPENROUTER_BASE_URL = cogConfig.get("base_url", "https://openrouter.ai/api/v1")
    MODEL_NAME = cogConfig.get("model_name", "minimax/minimax-m3:free")
    MEMORY_LIMIT = cogConfig.get("memory_limit", 5)
    SYSTEM_PROMPT_PATH = Path(cogConfig.get("system_prompt_path", "system_prompt.txt"))
    DISABLED_CHANNEL_IDS: set[int] = set(cogConfig.get("disabled_channels", []))


# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def loadSystemPrompt(filePath: Path) -> str:
    try:
        if filePath.exists():
            return filePath.read_text(encoding="utf-8").strip()
    except Exception as readError:
        print(f"[Chating] Ошибка чтения системного промпта: {readError}")
    return ""


# ==========================================
# COG
# ==========================================
class Chating(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.apiClient = OpenAI(
            api_key=Config.OPENROUTER_API_KEY,
            base_url=Config.OPENROUTER_BASE_URL,
        )
        self.systemPrompt = loadSystemPrompt(Config.SYSTEM_PROMPT_PATH)
        self.userMemoryMap: dict[str | int, deque[dict[str, str]]] = {}

    def extractUserPrompt(self, messageContent: str, botId: int) -> str | None:
        mentionPatterns = (f"<@{botId}>", f"<@!{botId}>")
        for mention in mentionPatterns:
            if messageContent.startswith(mention):
                return messageContent[len(mention):].strip()

        nameMatch = re.match(r"^\s*веспер\b[\s,.:!?-]*(.*)$", messageContent, flags=re.IGNORECASE | re.DOTALL)
        if nameMatch:
            return nameMatch.group(1).strip()

        return None

    async def checkIsReplyToBot(self, message: disnake.Message, botId: int) -> bool:
        if not message.reference or not message.reference.message_id:
            return False

        try:
            referencedMessage = await message.channel.fetch_message(message.reference.message_id)
            return (
                referencedMessage.author.id == botId
                and message.author.id != botId
            )
        except Exception:
            return False

    async def generateAiResponse(self, messageHistory: list[dict[str, str]]) -> str:
        currentLoop = asyncio.get_running_loop()
        apiResponse = await currentLoop.run_in_executor(
            None,
            lambda: self.apiClient.chat.completions.create(
                model=Config.MODEL_NAME,
                messages=messageHistory,
            ),
        )

        try:
            generatedText = apiResponse.choices[0].message.content.strip()
        except Exception:
            generatedText = str(apiResponse)

        return generatedText or "Извините, я не смог ничего сгенерировать."

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message):
        if not message.guild or message.channel.id in Config.DISABLED_CHANNEL_IDS:
            return

        botUser = getattr(self.bot, "user", None)
        rawContent = (message.content or "").strip()
        if not botUser or not rawContent:
            return

        # Игнорируем сторонних ботов, но обрабатываем обычных игроков и Minecraft-вебхуки
        if message.author.bot and not message.webhook_id:
            return

        extractedPrompt = self.extractUserPrompt(rawContent, botUser.id)

        # Если прямого обращения нет, проверяем ответ на сообщение бота
        if not extractedPrompt and await self.checkIsReplyToBot(message, botUser.id):
            extractedPrompt = rawContent

        if not extractedPrompt:
            return

        sessionIdentifier = f"webhook_{message.webhook_id}" if message.webhook_id else message.author.id
        if sessionIdentifier not in self.userMemoryMap:
            self.userMemoryMap[sessionIdentifier] = deque(maxlen=Config.MEMORY_LIMIT)

        activeUserMemory = self.userMemoryMap[sessionIdentifier]
        activeUserMemory.append({"role": "user", "content": extractedPrompt})

        conversationPayload: list[dict[str, str]] = []
        if self.systemPrompt:
            conversationPayload.append({"role": "system", "content": self.systemPrompt})
        conversationPayload.extend(list(activeUserMemory))

        try:
            async with message.channel.typing():
                assistantReply = await self.generateAiResponse(conversationPayload)
                activeUserMemory.append({"role": "assistant", "content": assistantReply})
                await message.reply(assistantReply, mention_author=False)
        except Exception as executionError:
            await message.reply(f"Ошибка при обращении к ИИ: {executionError}", mention_author=False)


def setup(bot: commands.Bot):
    bot.add_cog(Chating(bot))
    print("cog: AiChating.py загружен")