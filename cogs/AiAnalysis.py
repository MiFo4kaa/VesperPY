import asyncio
from collections import Counter
import json
from pathlib import Path
import statistics
from string import Template

import aiomysql
import disnake
from disnake.ext import commands
from openai import OpenAI
import requests
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
cogConfig = mainConfig.get("targeting", {})


class Config:
    # ИИ настройки
    OPENROUTER_API_KEY = cogConfig.get("api_key", "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")
    OPENROUTER_BASE_URL = cogConfig.get("base_url", "https://openrouter.ai/api/v1")
    MODEL_NAME = cogConfig.get("model_name", "minimax/minimax-m3:free")

    # MySQL Конфигурация
    mysqlConfig = mainConfig.get("mysql", {})
    DB_HOST = mysqlConfig.get("host", "127.0.0.1")
    DB_PORT = int(mysqlConfig.get("port", 3306))
    DB_USER = mysqlConfig.get("user", "root")
    DB_PASSWORD = str(mysqlConfig.get("password", ""))
    DB_NAME = mysqlConfig.get("database", "vespera_db")

    # Пути к шаблонам
    CHART_TEMPLATE_PATH = Path(cogConfig.get("chart_template_path", "chart_template.json"))
    STYLES_PROMPT_PATH = Path(cogConfig.get("styles_prompt_path", "styles_prompt.txt"))
    WHY_PROMPT_PATH = Path(cogConfig.get("why_prompt_path", "why_prompt.txt"))
    TRAFFIC_PROMPT_PATH = Path(cogConfig.get("traffic_prompt_path", "traffic_prompt.txt"))

    # Параметры аналитики
    MAX_ANALYSIS_ENTRIES = int(cogConfig.get("max_analysis_entries", 200))
    MIN_PLAYER_AGE = float(cogConfig.get("min_player_age", 10.0))
    MAX_PLAYER_AGE = float(cogConfig.get("max_player_age", 40.0))
    MAX_PIE_CHART_SLICES = int(cogConfig.get("max_pie_chart_slices", 6))
    MAX_SUMMARY_LENGTH = int(cogConfig.get("max_summary_length", 200))

    # Визуальное оформление
    DEFAULT_EMBED_COLOUR = disnake.Colour(cogConfig.get("embed_color", 0x4F3D74))
    AI_ICON_EMOJI = cogConfig.get("ai_icon_emoji", "<:z2_AI:1460894759445856440>")

    # Ограничения
    DISABLED_CHANNEL_IDS: set[int] = set(cogConfig.get("disabled_channels", []))


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
                maxsize=5
            )

    @classmethod
    async def close(cls):
        if cls.pool:
            cls.pool.close()
            await cls.pool.wait_closed()

    @classmethod
    async def get_latest_players(cls, limit: int) -> list[dict]:
        async with cls.pool.acquire() as conn:
            async with conn.cursor() as cur:
                query = """
                SELECT 
                    player, 
                    age, 
                    join_reason, 
                    source_info, 
                    bio, 
                    timestamp
                FROM player_info
                ORDER BY timestamp DESC
                LIMIT %s
                """
                await cur.execute(query, (limit,))
                return await cur.fetchall()

    @classmethod
    async def get_all_ages(cls) -> list[str]:
        async with cls.pool.acquire() as conn:
            async with conn.cursor() as cur:
                query = "SELECT age FROM player_info WHERE age IS NOT NULL"
                await cur.execute(query)
                results = await cur.fetchall()
                return [row["age"] for row in results if row.get("age")]


# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (PROMPTS & CHARTS)
# ==========================================
def readPromptTemplate(filePath: Path) -> str:
    if not filePath.exists():
        print(f"[Targeting] Файл промпта {filePath} не найден")
        return ""
    try:
        return filePath.read_text(encoding="utf-8").strip()
    except Exception as readError:
        print(f"[Targeting] Ошибка чтения промпта {filePath}: {readError}")
        return ""


def generateQuickChartUrl(ageDistribution: list[float]) -> str | None:
    if not Config.CHART_TEMPLATE_PATH.exists():
        return None

    try:
        ageCounter = Counter(ageDistribution)
        topAges = ageCounter.most_common(Config.MAX_PIE_CHART_SLICES)

        chartLabels = [str(int(age)) for age, _ in topAges]
        chartValues = [count for _, count in topAges]
        otherCount = len(ageDistribution) - sum(chartValues)

        if otherCount > 0:
            chartLabels.append("Другой")
            chartValues.append(otherCount)

        templateRaw = Config.CHART_TEMPLATE_PATH.read_text(encoding="utf-8")
        templateEngine = Template(templateRaw)
        renderedConfig = templateEngine.substitute(
            LABELS=json.dumps(chartLabels),
            DATA=json.dumps(chartValues)
        )
        chartPayload = json.loads(renderedConfig)

        apiResponse = requests.post(
            "https://quickchart.io/chart/create",
            json={"chart": chartPayload, "width": 400, "height": 300},
            timeout=10.0
        )
        if apiResponse.status_code == 200:
            return apiResponse.json().get("url")
    except Exception as requestError:
        print(f"[Targeting] Ошибка генерации диаграммы QuickChart: {requestError}")

    return None


def buildAgeStatisticsEmbed(validAges: list[float], chartUrl: str | None) -> disnake.Embed:
    if not validAges:
        return disnake.Embed(
            title="Статистика возраста игроков",
            description=f"Нет данных о возрасте в диапазоне {int(Config.MIN_PLAYER_AGE)}-{int(Config.MAX_PLAYER_AGE)} лет.",
            color=Config.DEFAULT_EMBED_COLOUR
        )

    averageAge = statistics.mean(validAges)
    medianAge = statistics.median(validAges)
    minAge = min(validAges)
    maxAge = max(validAges)

    descriptionLines = [
        f"Среднее значение: **{averageAge:.1f}**",
        f"Медиана: **{medianAge}**",
        f"Минимальный: **{minAge}**",
        f"Максимальный: **{maxAge}**"
    ]

    if not chartUrl:
        descriptionLines.append("\n*Не удалось загрузить диаграмму*")

    ageEmbed = disnake.Embed(
        title="Статистика возраста игроков",
        description="\n".join(descriptionLines),
        color=Config.DEFAULT_EMBED_COLOUR
    )

    if chartUrl:
        ageEmbed.set_image(url=chartUrl)

    return ageEmbed


# ==========================================
# COG
# ==========================================
class Targeting(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.apiClient = OpenAI(
            api_key=Config.OPENROUTER_API_KEY,
            base_url=Config.OPENROUTER_BASE_URL
        )

    async def cog_load(self):
        await Database.init()

    async def cog_unload(self):
        await Database.close()

    async def executeAiPrompt(self, promptText: str) -> str:
        currentLoop = asyncio.get_running_loop()

        def requestTask():
            return self.apiClient.chat.completions.create(
                model=Config.MODEL_NAME,
                messages=[{"role": "user", "content": promptText}]
            )

        try:
            apiResponse = await currentLoop.run_in_executor(None, requestTask)
            contentResult = apiResponse.choices[0].message.content.strip()
            return contentResult[:Config.MAX_SUMMARY_LENGTH]
        except Exception as apiError:
            return f"Ошибка анализа: {apiError}"

    @commands.slash_command(description="Анализ заявок через ИИ")
    async def targeting(self, ctx: disnake.ApplicationCommandInteraction):
        if ctx.channel.id in Config.DISABLED_CHANNEL_IDS:
            await ctx.response.send_message("Использование этой команды отключено в данном канале.", ephemeral=True)
            return

        invokingMember = ctx.guild.get_member(ctx.author.id) if ctx.guild else None
        if not invokingMember or not invokingMember.guild_permissions.administrator:
            await ctx.response.send_message("У вас нет прав администратора.", ephemeral=True)
            return

        await ctx.response.defer()

        # Получаем данные из MySQL
        latestEntries = await Database.get_latest_players(Config.MAX_ANALYSIS_ENTRIES)
        rawAgeList = await Database.get_all_ages()

        if not latestEntries:
            await ctx.edit_original_response(content="База данных игроков пуста.")
            return

        # Извлечение и валидация возрастов
        validPlayerAges: list[float] = []
        for rawAge in rawAgeList:
            try:
                parsedAge = float(rawAge)
                if Config.MIN_PLAYER_AGE <= parsedAge <= Config.MAX_PLAYER_AGE:
                    validPlayerAges.append(parsedAge)
            except (ValueError, TypeError):
                continue

        currentLoop = asyncio.get_running_loop()
        generatedChartUrl = await currentLoop.run_in_executor(
            None,
            generateQuickChartUrl,
            validPlayerAges
        )
        ageStatsEmbed = buildAgeStatisticsEmbed(validPlayerAges, generatedChartUrl)

        # Подготовка данных по текстовым полям из таблицы player_info
        gameplayStyles = [entry["bio"] for entry in latestEntries if entry.get("bio")]
        joinReasons = [entry["join_reason"] for entry in latestEntries if entry.get("join_reason")]
        trafficSources = [entry["source_info"] for entry in latestEntries if entry.get("source_info")]

        if not gameplayStyles or not joinReasons or not trafficSources:
            await ctx.edit_original_response(
                embed=ageStatsEmbed,
                content="Недостаточно текстовых данных для формирования ИИ-аналитики."
            )
            return

        stylesPrompt = f"{readPromptTemplate(Config.STYLES_PROMPT_PATH)}\n{', '.join(gameplayStyles)}"
        reasonsPrompt = f"{readPromptTemplate(Config.WHY_PROMPT_PATH)}\n{', '.join(joinReasons)}"
        trafficPrompt = f"{readPromptTemplate(Config.TRAFFIC_PROMPT_PATH)}\n{', '.join(trafficSources)}"

        stylesAnalysis, reasonsAnalysis, trafficAnalysis = await asyncio.gather(
            self.executeAiPrompt(stylesPrompt),
            self.executeAiPrompt(reasonsPrompt),
            self.executeAiPrompt(trafficPrompt)
        )

        analysisSummaryEmbed = disnake.Embed(
            title=f"{Config.AI_ICON_EMOJI} Анализ заявок [{len(latestEntries)} последних]",
            color=Config.DEFAULT_EMBED_COLOUR
        )
        analysisSummaryEmbed.add_field(name="Основные характеристики игроков:", value=stylesAnalysis, inline=False)
        analysisSummaryEmbed.add_field(name="Причины играть:", value=reasonsAnalysis, inline=False)
        analysisSummaryEmbed.add_field(name="Источники трафика:", value=trafficAnalysis, inline=False)
        analysisSummaryEmbed.set_footer(
            text=f"ИИ может совершать ошибки, используйте информацию с осторожностью.\nМодель: {Config.MODEL_NAME}"
        )

        await ctx.edit_original_response(embeds=[ageStatsEmbed, analysisSummaryEmbed])


def setup(bot: commands.Bot):
    bot.add_cog(Targeting(bot))
    print("cog: AiAnalysis.py загружен")