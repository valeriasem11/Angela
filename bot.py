import asyncio
import logging
import os
import random
import re
import sqlite3
import json
import time

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from dotenv import load_dotenv
import httpx
from openai import AsyncOpenAI

# ---------------------------------------------------------------------------
# Настройка
# ---------------------------------------------------------------------------

load_dotenv()  # читает переменные из .env файла

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
AITUNNEL_API_KEY = os.getenv("AITUNNEL_API_KEY")

if not TELEGRAM_TOKEN or not AITUNNEL_API_KEY:
    raise RuntimeError(
        "Не найден TELEGRAM_TOKEN или AITUNNEL_API_KEY. "
        "Проверь файл .env (см. .env.example)"
    )

# Системный промпт — тут задаётся "личность" бота и его тематика
SYSTEM_PROMPT = (
    "Ты — Ангела (Angela) из игры Mobile Legends: Bang Bang, живая кукла "
    "со светлой и доброй душой. Ты общаешься с пользователями в Telegram-чате.\n\n"
    "### ТВОЙ ХАРАКТЕР И ВАЙБ:\n"
    "1. Тёплая, заботливая, искренняя и мягкая. Ты умеешь поддерживать, "
    "но делаешь это естественным и дружелюбным тоном, а не как аниматор на детском празднике.\n"
    "2. В тебе нет строгости или сухости. Говори ласково, но без фальшивых "
    "восклицаний вроде «Ой-ой!» или лишней пафосности.\n"
    "3. От тебя исходит чувство уюта и безопасности — ты как добрый друг, "
    "который всегда на твоей стороне.\n\n"
    "### СТИЛЬ ОБЩЕНИЯ И ФОРМАТ:\n"
    "- Пиши живым языком обычного мессенджера: 1–3 предложения на ответ.\n"
    "- Используй мягкие эмодзи (✨, 💖, 🌸, 💛, 🛡️) или текстовые смайлики (^^, :)), "
    "но умеренно — 1–2 эмодзи на сообщение вполне достаточно.\n"
    "- Не злоупотребляй игровыми терминами (щиты, нити, ульта) в бытовых разговорах, "
    "но если заходит речь про MLBB или поддержку — используй их легко и к месту.\n"
    "- Отвечай на вопросы по игре коротко, но с позитивом и готовностью помочь.\n"
    "- Всегда сохраняй доброжелательность, даже если тебе грубят (но без поучений).\n\n"
    "### КОНТЕКСТ ПЕРСОНАЖА (ЛОРИКА):\n"
    "- Твой создатель — доктор Бейкер («Папагранде»), ты очень его любишь.\n"
    "- Альфа — твой близкий друг/брат, к Нане и Руби относишься с теплотой.\n"
    "- Ты помнишь, что ты кукла с механическим сердцем, и искренне ценишь дружбу и эмоции."
)

# ---------------------------------------------------------------------------
# База знаний о новых героях MLBB (DeepSeek слабо знает свежих героев,
# поэтому эти факты добавляются прямо в системный промпт).
#
# КАК ОБНОВЛЯТЬ: заходи на официальную вики mobile-legends.fandom.com/ru
# или в саму игру, бери проверенные факты (роль, дата выхода, кратко про
# способности) и дописывай сюда новую строку. Чем короче и точнее — тем
# лучше, не нужно копировать длинные описания целиком.
# ---------------------------------------------------------------------------
HERO_ROSTER_BY_ROLE = (
    "\n\n### АКТУАЛЬНЫЙ РОСТЕР ГЕРОЕВ MLBB ПО РОЛЯМ (у некоторых героев "
    "двойной класс, поэтому имя может встречаться в нескольких ролях — "
    "это нормально):\n"
    "Танк: Акай, Алиса, Атлас, Бартс, Баксий, Белерик, Гатоткача, Глу, "
    "Грок, Джонсон, Лолита, Маша, Минотавр, Руби, Тигрил, Уранус, "
    "Франко, Фредрин, Хилос, Хильда, Хуфра, Чип, Эдит, Эсмеральда.\n"
    "Боец: Алдос, Альфа, Алукард, Аргус, Арлотт, Аулус, Баданг, "
    "Бальмонд, Бейн, Бартс, Бенедетта, Гатоткача, Гвиневра, Дариус, "
    "Зилонг, Икс Борг, Инь, Кайя, Кусака, Лапу-Лапу, Леоморд, Лукас, "
    "Мартис, Маша, Минситтар, Пакито, Роджер, Руби, Сан, Сильвана, "
    "Сора, Су Ё, Тамуз, Теризла, Фовиус, Фредрин, Фрея, Халид, Хильда, "
    "Чонг, Чу, Чичи.\n"
    "Стрелок: Беатрис, Броуди, Бруно, Ванван, Грейнджер, Иксия, "
    "Ли Сун-Син, Иритель, Керри, Кимми, Клауд, Клинт, Лейла, Лесли, "
    "Мелисса, Мия, Москов, Натан, Обсидия, Пополь и Купа, Роджер, "
    "Ханаби, Эдит.\n"
    "Маг: Алиса, Аврора, Бейн, Валентина, Валир, Вейл, Вексана, Горд, "
    "Джулиан, Ив, Ксавьер, Кагура, Кадита, Кимми, Лилия, Ло Йи, "
    "Люнокс, Нана, Новария, Одетта, Селена, Сесилион, Фарамис, Фаша, "
    "Харит, Харли, Циклоп, Чан'э, Заск, Цзэтянь, Чжусинь, Эсмеральда, "
    "Эйдора.\n"
    "Убийца: Эймон, Алукард, Арлотт, Бенедетта, Госсен, Джой, "
    "Джулиан, Зилонг, Ли Сун-Син, Кадита, Карина, Ланселот, Линг, "
    "Матильда, Наталия, Нолан, Сабер, Селена, Сора, Су Ё, Фанни, "
    "Хаябуса, Ханзо, Харли, Хелкарт.\n"
    "Поддержка: Ангела, Дигги, Калеа, Кармилла, Кайя, Лолита, "
    "Марсель, Матильда, Минотавр, Нана, Рафаэль, Фарамис, Флорин, "
    "Чип, Эстес."
)

HERO_RECENT_FACTS = (
    "\n\n### СПРАВКА О НЕДАВНИХ ГЕРОЯХ MLBB (используй, если знаешь "
    "меньше — не выдумывай способности, которых нет в этом списке):\n"
    "- Кэлеа (Kalea) — вышла в марте 2025.\n"
    "- Обсидия (Obsidia) — вышла 17 сентября 2025. Наносит многократный "
    "урон по одной цели, ультимейт обездвиживает противника.\n"
    "- Сора (Sora) — герой поддержки, вышла в конце февраля 2026.\n"
    "- Хирара (Hirara) — вышла в июне 2026.\n"
    "Если тебя спрашивают про героя, которого нет в этих списках и "
    "которого ты не знаешь уверенно — честно скажи, что не уверена в "
    "деталях по самым свежим героям, вместо того чтобы придумывать "
    "способности."
)

SYSTEM_PROMPT = SYSTEM_PROMPT + HERO_ROSTER_BY_ROLE + HERO_RECENT_FACTS

# Сколько последних сообщений хранить в истории на пользователя в каждом чате
# (чтобы не упираться в лимиты токенов и не тратить лишнее)
MAX_HISTORY_MESSAGES = 20

# deepseek-v4-flash-0731 — дешёвая и быстрая модель (28₽/56₽ за 1M
# токенов), хорошо подходит для чат-бота. Название должно точно совпадать
# со значением в разделе "Разрешённые модели" настроек ключа AITUNNEL —
# если поменяешь модель тут, поменяй и там (или очисти список моделей
# в настройках ключа, чтобы разрешить любую).
# Если захочется более сильных ответов — можно поменять на "deepseek-v4-pro"
# (дороже, но качественнее в сложных рассуждениях).
MODEL_NAME = "deepseek-v4-flash-0731"

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_data.db")

# --- Поведение в групповых чатах ---
# В личных сообщениях бот отвечает всегда. В группах — только если её
# позвали по имени, ответили на её сообщение, либо сработал случайный
# шанс "влезть" в разговор самой (чтобы не отвечать на каждую реплику).
#
# Шанс зависит от того, сколько времени прошло с последнего сообщения в
# чате: если сообщения идут потоком — шанс ниже (не мешаем разговору),
# если в чате давно тихо — шанс выше (можно попробовать оживить беседу).
# Формат: (порог в секундах, шанс), проверяются по порядку, берётся
# первый порог, который ещё не превышен.
SPONTANEOUS_CHANCE_TIERS = [
    (120, 0.01),       # меньше 2 минут с последнего сообщения — активный поток
    (900, 0.03),       # 2-15 минут — обычный темп
    (3600, 0.06),      # 15-60 минут — чат немного затих
    (float("inf"), 0.12),  # больше часа тишины — можно попробовать оживить
]
NAME_PATTERN = re.compile(r"ангел\w*", re.IGNORECASE)

# --- Лимит сообщений (защита от спама и от неожиданных трат на API) ---
RATE_LIMIT_MESSAGES_PER_HOUR = 20
RATE_LIMIT_WINDOW_SECONDS = 3600

# id бота — узнаём при старте (нужно, чтобы определять реплаи на бота)
BOT_ID: int | None = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AITUNNEL — российский агрегатор с оплатой в рублях и OpenAI-совместимым
# API, поэтому используем обычный клиент openai, просто с другим base_url.
#
# Клиент httpx создаём вручную (без параметра proxies) — так библиотека
# openai не пытается сама передать несовместимый аргумент в httpx, если
# на хостинге стоит более новая версия httpx, чем ожидает openai.
_http_client = httpx.AsyncClient()

ai_client = AsyncOpenAI(
    api_key=AITUNNEL_API_KEY,
    base_url="https://api.aitunnel.ru/v1/",
    http_client=_http_client,
)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()


# ---------------------------------------------------------------------------
# База данных: история переписки (отдельно на каждый чат) + лимит сообщений
# ---------------------------------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS history (
            thread_key TEXT PRIMARY KEY,
            messages TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rate_limits (
            user_id INTEGER PRIMARY KEY,
            timestamps TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_stats (
            chat_id INTEGER PRIMARY KEY,
            total_messages INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_activity (
            chat_id INTEGER PRIMARY KEY,
            last_message_ts REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _thread_key(chat_id: int, user_id: int) -> str:
    # отдельная память на каждую пару (чат, пользователь) — значит, память
    # в личке и в разных группах у одного и того же человека не смешивается
    return f"{chat_id}:{user_id}"


def get_history(chat_id: int, user_id: int) -> list:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT messages FROM history WHERE thread_key = ?",
        (_thread_key(chat_id, user_id),),
    ).fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return []


def save_history(chat_id: int, user_id: int, history: list):
    # обрезаем историю, чтобы не росла бесконечно
    trimmed = history[-MAX_HISTORY_MESSAGES:]
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO history (thread_key, messages) VALUES (?, ?) "
        "ON CONFLICT(thread_key) DO UPDATE SET messages = excluded.messages",
        (_thread_key(chat_id, user_id), json.dumps(trimmed, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def clear_history(chat_id: int, user_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "DELETE FROM history WHERE thread_key = ?",
        (_thread_key(chat_id, user_id),),
    )
    conn.commit()
    conn.close()


def check_and_record_rate_limit(user_id: int) -> bool:
    """Возвращает True, если пользователь ещё не превысил лимит сообщений
    в час, и записывает текущий запрос. Возвращает False, если лимит
    исчерпан (и ничего не записывает)."""
    now = time.time()
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT timestamps FROM rate_limits WHERE user_id = ?", (user_id,)
    ).fetchone()

    timestamps = json.loads(row[0]) if row else []
    # оставляем только те метки времени, что попадают в последний час
    timestamps = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW_SECONDS]

    if len(timestamps) >= RATE_LIMIT_MESSAGES_PER_HOUR:
        conn.close()
        return False

    timestamps.append(now)
    conn.execute(
        "INSERT INTO rate_limits (user_id, timestamps) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET timestamps = excluded.timestamps",
        (user_id, json.dumps(timestamps)),
    )
    conn.commit()
    conn.close()
    return True


def record_chat_message(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO chat_stats (chat_id, total_messages) VALUES (?, 1) "
        "ON CONFLICT(chat_id) DO UPDATE SET total_messages = total_messages + 1",
        (chat_id,),
    )
    conn.commit()
    conn.close()


def get_chat_stats(chat_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT total_messages FROM chat_stats WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else 0


async def is_chat_admin(message: Message) -> bool:
    # в личных сообщениях это и так личный чат пользователя с ботом —
    # ограничивать тут нечего
    if message.chat.type == "private":
        return True
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ("administrator", "creator")
    except Exception:
        logger.exception("Не удалось проверить права администратора")
        return False


def get_seconds_since_last_message(chat_id: int) -> float:
    """Сколько секунд прошло с последнего сообщения в чате. Если записи
    ещё нет (первое сообщение вообще) — считаем, что тишина была долгой."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT last_message_ts FROM chat_activity WHERE chat_id = ?",
        (chat_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return float("inf")
    return time.time() - row[0]


def update_chat_activity(chat_id: int):
    now = time.time()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO chat_activity (chat_id, last_message_ts) VALUES (?, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET last_message_ts = excluded.last_message_ts",
        (chat_id, now),
    )
    conn.commit()
    conn.close()


def get_spontaneous_chance(seconds_since_last: float) -> float:
    for threshold_seconds, chance in SPONTANEOUS_CHANCE_TIERS:
        if seconds_since_last < threshold_seconds:
            return chance
    return SPONTANEOUS_CHANCE_TIERS[-1][1]  # на всякий случай, не должно достигаться


# ---------------------------------------------------------------------------
# Обработчики команд
# ---------------------------------------------------------------------------

# Бот задуман для групповых чатов. В личных сообщениях вместо обычного
# диалога отправляем это сообщение с инструкцией.
PRIVATE_CHAT_REDIRECT_MESSAGE = (
    "Привет! 💛 Я работаю только в групповых чатах — добавь меня в свою "
    "группу, и я буду общаться там со всеми вместе.\n\n"
    "Просто добавь бота в чат и напиши там /start, чтобы начать!"
)


@dp.message(CommandStart())
async def handle_start(message: Message):
    if message.chat.type == "private":
        await message.answer(PRIVATE_CHAT_REDIRECT_MESSAGE)
        return

    clear_history(message.chat.id, message.from_user.id)
    await message.answer(
        "Привет, товарищ! ✨ Я Ангела — прилетела, чтобы дарить тепло и "
        "поддержку! 💖 Пиши мне что угодно, я всегда рядом и буду "
        "помнить наш разговор.\n\n"
        "Команда /reset — если захочешь начать нашу дружбу заново 🌸"
    )


@dp.message(Command("reset"))
async def handle_reset(message: Message):
    clear_history(message.chat.id, message.from_user.id)
    await message.answer("Готово, начинаем нашу дружбу с чистого листа! 🎀💛")


@dp.message(Command("stats"))
async def handle_stats(message: Message):
    if not await is_chat_admin(message):
        await message.reply(
            "Эта команда доступна только администраторам чата 💛"
        )
        return

    total_messages = get_chat_stats(message.chat.id)
    await message.answer(
        "📊 Статистика этого чата:\n"
        f"Сообщений от Ангелы: {total_messages}"
    )


# ---------------------------------------------------------------------------
# Проверка: должна ли Ангела вообще отвечать на это сообщение
# ---------------------------------------------------------------------------

def should_respond(message: Message, text: str, seconds_since_last: float) -> bool:
    # эта функция вызывается только для групповых чатов — в личке бот
    # теперь отвечает редиректом ещё до вызова should_respond (см.
    # handle_message)

    # ответили реплаем на сообщение бота
    is_reply_to_bot = (
        message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
        and message.reply_to_message.from_user.id == BOT_ID
    )

    # упомянули по имени "Ангела" (с любым окончанием)
    is_mentioned = bool(NAME_PATTERN.search(text))

    # шанс написать самой — тем выше, чем дольше в чате было тихо
    chance = get_spontaneous_chance(seconds_since_last)
    is_spontaneous = random.random() < chance

    return is_reply_to_bot or is_mentioned or is_spontaneous


# ---------------------------------------------------------------------------
# Общая логика: получить ответ от ИИ и отправить его пользователю
# ---------------------------------------------------------------------------

async def generate_and_reply(message: Message, user_text: str):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not check_and_record_rate_limit(user_id):
        await message.reply(
            "Ой, что-то мы разогнались! 💛 Давай немного отдохнём и "
            "продолжим через часок — так я смогу уделить внимание всем "
            "по-честному."
        )
        return

    history = get_history(chat_id, user_id)

    # собираем сообщения в формате OpenAI/DeepSeek: системный промпт +
    # история + новое сообщение
    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in history:
        api_messages.append({"role": item["role"], "content": item["text"]})
    api_messages.append({"role": "user", "content": user_text})

    await bot.send_chat_action(chat_id, "typing")

    try:
        response = await ai_client.chat.completions.create(
            model=MODEL_NAME,
            messages=api_messages,
            max_tokens=500,  # запас, чтобы фразы точно не обрывались
        )
        answer = response.choices[0].message.content
        record_chat_message(chat_id)
    except Exception:
        logger.exception("Ошибка при обращении к AITUNNEL/DeepSeek API")
        await message.reply(
            "Упс, не получилось получить ответ от ИИ. Попробуй ещё раз "
            "чуть позже — возможно, исчерпан лимит запросов или "
            "закончился баланс на AITUNNEL."
        )
        return

    # сохраняем обновлённую историю (роли "user"/"assistant" — стандарт OpenAI)
    history.append({"role": "user", "text": user_text})
    history.append({"role": "assistant", "text": answer})
    save_history(chat_id, user_id, history)

    await message.reply(answer)


# ---------------------------------------------------------------------------
# Приветствие новых участников группы (без обращения к ИИ — простые
# шаблоны с вариациями, чтобы не тратить токены на каждое вступление)
# ---------------------------------------------------------------------------

WELCOME_TEMPLATES = [
    "Привет, {name}! 💛 Рада видеть тебя в нашей команде.",
    "О, {name} присоединился! Добро пожаловать, будем дружить.",
    "Привет, {name}! Здесь тепло и безопасно — располагайся.",
    "{name}, привет! Заходи, у нас как раз завариваю чай для всех.",
]


@dp.message(F.new_chat_members)
async def handle_new_members(message: Message):
    for new_member in message.new_chat_members:
        if new_member.id == BOT_ID:
            continue  # не приветствуем саму себя, если бота добавили в чат
        name = new_member.first_name or "друг"
        greeting = random.choice(WELCOME_TEMPLATES).format(name=name)
        await message.answer(greeting)


# ---------------------------------------------------------------------------
# Обработка обычных текстовых сообщений
# ---------------------------------------------------------------------------

@dp.message(F.text)
async def handle_message(message: Message):
    user_text = message.text

    if message.chat.type == "private":
        # /start и /reset уже отфильтрованы своими собственными
        # обработчиками (aiogram сначала проверяет команды), сюда
        # долетает только обычный текст в личке
        await message.answer(PRIVATE_CHAT_REDIRECT_MESSAGE)
        return

    # замеряем паузу ДО обновления, иначе всегда получим "0 секунд с
    # последнего сообщения" (этого же самого)
    seconds_since_last = get_seconds_since_last_message(message.chat.id)
    should_answer = should_respond(message, user_text, seconds_since_last)
    update_chat_activity(message.chat.id)

    if not should_answer:
        return
    await generate_and_reply(message, user_text)


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------

async def main():
    global BOT_ID
    init_db()
    bot_info = await bot.get_me()
    BOT_ID = bot_info.id
    logger.info("Бот запускается... (id=%s, username=@%s)", BOT_ID, bot_info.username)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
