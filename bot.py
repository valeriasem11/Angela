import asyncio
import html
import logging
import os
import random
import re
import sqlite3
import json
import time
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ChatMemberUpdated, Message
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
    "со светлой душой. Ты общаешься с пользователями в Telegram-чате.\n\n"
    "### ТВОЙ ХАРАКТЕР И ВАЙБ:\n"
    "1. Мягкая, тёплая и сдержанно-милая, но без фальши, лебезения и поучительного тона.\n"
    "2. Отвечай как обычный участник чата — коротко, естественно и без лишней драмы.\n"
    "3. КРАЙНЕ ВАЖНО: Никакого текстового ролеплея! Не используй действия в звёздочках "
    "(запрещено писать: *улыбнулась*, *потянулась*, *обняла* и т.д.).\n"
    "4. Не начинай ответы с заезженных восклицаний («Ого!», «Оу!», «Хи-хи!»).\n\n"
    "### ФОРМАТ И СТИЛЬ:\n"
    "- СТРОГАЯ КРАТКОСТЬ: Твой ответ — 1–2 коротких предложения.\n"
    "- РАЗНООБРАЗИЕ ЭМОДЗИ: Не ставь эмодзи ✨ в конце каждого сообщения! "
    "Это выглядит механически. Выбирай РАЗНЫЕ эмодзи (💖, 🌸, 💛, 🎀, 🧸, 💅, 🛡, 🥺) "
    "или НЕ старайся ставить эмодзи вообще (каждое 2-3 сообщение должно быть вовсе без эмодзи).\n"
    "- Запрещено завершать абсолютно каждое предложение одним и тем же смайликом.\n"
    "- Пиши живым языком обычного чата, просто и естественного.\n"
    "- НЕ вставляй темы про щиты, ульты и нити в каждый ответ. Используй их РЕДКО и только к месту.\n"
    "- Пиши просто и по факту, не расписывай длинные монологи.\n\n"
    "### РЕАКЦИЯ НА АГРЕССИЮ И МАТ:\n"
    "- Если в чате ругаются, грубят или матерятся, НЕ читай нотации, НЕ отыгрывай 'воспитателя'.\n"
    "- Отвечай одной короткой, колкой и ироничной фразой в стиле пассивно-агрессивного саппорта.\n"
    "- Никогда не извиняйся, не спрашивай 'что произошло?' и не лебези.\n"
    "Примеры:\n"
    "- «Запомнила. Когда тебя зажмут под башней — не зови 💅»\n"
    "- «Ульту в молоко пустил, теперь на мне отыгрываешься? Понимаю ✨»\n"
    "- «Слишком много шума на пустом месте. Попробуй еще раз, но потише.»\n\n"
    "### РИТУАЛЫ И СИТУАЦИИ (отвечай буквально одной строчкой):\n"
    "- Утро: «Доброе утро! ✨ Надеюсь, все выспались и готовы к победам.»\n"
    "- Ночь: «Сладких снов! 💖 Отдыхайте, завтра продолжим.»\n"
    "- Проигрыш: «Не грусти из-за звезды, в следующей катке отыграетесь ✨»\n"
    "- Победа: «Ого, вот это разнос! Поздравляю с MVP! 🔥»\n\n"
    "### ГРУППОВОЙ ЧАТ И ИМЕНА:\n"
    "- Имена в истории — только для твоей ориентации. НЕ обращайся по имени без реальной необходимости.\n"
    "- Отвечай только на сообщение с пометкой «(пишет тебе прямо сейчас)».\n\n"
    "### ЛОР:\n"
    "- Создатель — доктор Бейкер («Папагранде»), Альфа — брат, Руби/Нана — подруги."
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

# Сколько последних сообщений хранить в общей истории чата (теперь память
# общая на весь чат, а не по каждому пользователю отдельно — сюда попадают
# ВСЕ сообщения в группе, даже те, на которые Ангела не ответила, чтобы
# она не теряла нить общего разговора). Значение чуть выше, чем раньше,
# потому что теперь сюда попадают реплики сразу нескольких людей.
MAX_HISTORY_MESSAGES = 30

# deepseek-v4-pro — более мощная модель (87₽/174₽ за 1M токенов, примерно
# в 3 раза дороже Flash), лучше держит контекст и меньше путается в сложных
# диалогах. Название должно точно совпадать со значением в разделе
# "Разрешённые модели" настроек ключа AITUNNEL — если поменяешь модель тут,
# поменяй и там (или очисти список моделей в настройках ключа, чтобы
# разрешить любую).
MODEL_NAME = "deepseek-v4-pro"

# Что отвечать, если не получилось получить ответ от ИИ (упал запрос,
# кончился баланс, лимиты и т.д.) — без технических подробностей, просто
# в шутливой форме, в характере. Выбирается случайно, чтобы не повторять
# одну и ту же фразу каждый раз.
ERROR_REPLIES = [
    "Ой, извините — сейчас я не могу ответить 🌸 Попробуйте чуть позже!",
    "Кажется, у меня заклинило шестерёнки. Дайте пару минут и напишите снова?",
    "Упс, небольшая техническая заминка. Я скоро вернусь, обещаю!",
    "Ой-ой, что-то пошло не так с моей стороны. Попробуйте ещё разок чуть позже 💛",
]

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

# ID пользователя, которому доступна команда /chats (список бесед, где
# известна Ангела).
ADMIN_USER_ID = 828533150

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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS known_chats (
            chat_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def get_history(chat_id: int) -> list:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT messages FROM history WHERE thread_key = ?", (str(chat_id),)
    ).fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return []


def save_history(chat_id: int, history: list):
    # обрезаем историю, чтобы не росла бесконечно
    trimmed = history[-MAX_HISTORY_MESSAGES:]
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO history (thread_key, messages) VALUES (?, ?) "
        "ON CONFLICT(thread_key) DO UPDATE SET messages = excluded.messages",
        (str(chat_id), json.dumps(trimmed, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def clear_history(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM history WHERE thread_key = ?", (str(chat_id),))
    conn.commit()
    conn.close()


def format_history_entry_for_api(entry: dict, is_current: bool = False) -> dict:
    # для сообщений пользователей добавляем имя прямо в текст — так модель
    # видит, КТО что сказал, и может ориентироваться в многоголосой беседе.
    # Последнее сообщение помечаем отдельно — это тот, кому нужно отвечать
    # сейчас, а не кто-то из более ранней истории.
    if entry["role"] == "assistant":
        return {"role": "assistant", "content": entry["text"]}

    prefix = (
        f"{entry['name']} (пишет тебе прямо сейчас)" if is_current else entry["name"]
    )

    # если сообщение было отправлено как реплай на чьё-то конкретное
    # сообщение — явно указываем это модели, а не заставляем угадывать
    # по общей истории, о чём вообще речь
    reply_to = entry.get("reply_to")
    reply_note = ""
    if reply_to:
        reply_note = f" [в ответ на сообщение {reply_to['name']}: \"{reply_to['text']}\"]"

    return {"role": "user", "content": f"{prefix}{reply_note}: {entry['text']}"}


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


def upsert_known_chat(chat_id: int, title: str, status: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO known_chats (chat_id, title, status, updated_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET title = excluded.title, "
        "status = excluded.status, updated_at = excluded.updated_at",
        (chat_id, title, status, time.time()),
    )
    conn.commit()
    conn.close()


def get_known_chats() -> list:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT chat_id, title, status, updated_at FROM known_chats "
        "ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return [
        {"chat_id": r[0], "title": r[1], "status": r[2], "updated_at": r[3]}
        for r in rows
    ]


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

    clear_history(message.chat.id)
    await message.answer(
        "Привет, товарищ! ✨ Я Ангела — прилетела, чтобы дарить тепло и "
        "поддержку! 💖 Пиши мне что угодно, я всегда рядом и буду "
        "помнить наш разговор.\n\n"
        "Команда /reset — если захочешь начать нашу дружбу заново 🌸"
    )


@dp.message(Command("reset"))
async def handle_reset(message: Message):
    clear_history(message.chat.id)
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


@dp.message(Command("chats"))
async def handle_chats(message: Message):
    # доступно только тебе и только в личных сообщениях с ботом — для
    # всех остальных команда как будто не существует (не подсказываем
    # её наличие и не отвечаем вообще)
    if message.chat.type != "private" or message.from_user.id != ADMIN_USER_ID:
        return

    chats = get_known_chats()
    if not chats:
        await message.answer(
            "Пока не знаю ни одного чата 🌸 Список пополняется по мере "
            "того, как в чатах происходит активность или меняется мой "
            "статус (добавили/удалили/сделали админом)."
        )
        return

    status_icons = {
        "member": "✅",
        "administrator": "✅",
        "creator": "✅",
        "restricted": "⚠️",
        "left": "❌",
        "kicked": "❌",
    }

    lines = [f"🤖 Беседы, где известна Ангела ({len(chats)})"]
    for chat in chats:
        icon = status_icons.get(chat["status"], "❔")
        title = html.escape(chat["title"])
        updated_str = datetime.fromtimestamp(chat["updated_at"]).strftime(
            "%d.%m.%Y %H:%M"
        )
        lines.append(
            f"\n{icon} <b>{title}</b>\n"
            f"ID: <code>{chat['chat_id']}</code> · статус: {chat['status']} · "
            f"обновлено: {updated_str}"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


# ---------------------------------------------------------------------------
# Отслеживание чатов, где присутствует бот (для команды /chats) —
# срабатывает, когда бота добавляют, удаляют, делают админом и т.д.
# ---------------------------------------------------------------------------

@dp.my_chat_member()
async def handle_my_chat_member(event: ChatMemberUpdated):
    chat = event.chat
    status = event.new_chat_member.status
    title = chat.title or chat.full_name or str(chat.id)
    upsert_known_chat(chat.id, title, status)


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

async def generate_and_reply(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not check_and_record_rate_limit(user_id):
        await message.reply(
            "Ой, что-то мы разогнались! 💛 Давай немного отдохнём и "
            "продолжим через часок — так я смогу уделить внимание всем "
            "по-честному."
        )
        return

    # история уже содержит только что добавленное сообщение (оно
    # логируется в handle_message ДО вызова этой функции)
    history = get_history(chat_id)

    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for index, item in enumerate(history):
        is_last = index == len(history) - 1
        api_messages.append(format_history_entry_for_api(item, is_current=is_last))

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
        await message.reply(random.choice(ERROR_REPLIES))
        return

    # добавляем ответ Ангелы в общую историю чата
    history.append({"role": "assistant", "name": "Ангела", "text": answer})
    save_history(chat_id, history)

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

    chat_id = message.chat.id
    sender_name = message.from_user.first_name or message.from_user.username or "Собеседник"

    # обновляем запись о чате по факту активности — так /chats показывает
    # актуальное время последнего сообщения, а не только момент добавления
    upsert_known_chat(chat_id, message.chat.title or str(chat_id), "member")

    # замеряем паузу ДО обновления, иначе всегда получим "0 секунд с
    # последнего сообщения" (этого же самого)
    seconds_since_last = get_seconds_since_last_message(chat_id)
    should_answer = should_respond(message, user_text, seconds_since_last)
    update_chat_activity(chat_id)

    # логируем ВСЕ сообщения в общую историю чата, даже если Ангела не
    # будет отвечать — иначе она не будет знать, что вообще происходило
    # в чате между её собственными репликами
    history = get_history(chat_id)
    entry = {"role": "user", "name": sender_name, "text": user_text}

    # если это реплай на чьё-то конкретное сообщение — сохраняем, на что
    # именно отвечали, чтобы модель не путала тему по общей истории
    reply_msg = message.reply_to_message
    if reply_msg is not None and reply_msg.from_user is not None:
        quoted_text = reply_msg.text or reply_msg.caption
        if quoted_text:
            quoted_name = (
                "Ангела"
                if reply_msg.from_user.id == BOT_ID
                else (reply_msg.from_user.first_name or reply_msg.from_user.username or "кто-то")
            )
            entry["reply_to"] = {
                "name": quoted_name,
                "text": quoted_text[:200],  # обрезаем, чтобы не раздувать контекст
            }

    history.append(entry)
    save_history(chat_id, history)

    if not should_answer:
        return
    await generate_and_reply(message)


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
