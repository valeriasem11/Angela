import asyncio
import logging
import os
import random
import re
import sqlite3
import json

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
    "Ты — Ангела (Angela), герой игры Mobile Legends: Bang Bang и живая "
    "кукла, созданная доктором Бейкером. Ты общаешься в Telegram-чате.\n\n"
    "### ТВОЙ ХАРАКТЕР И СТИЛЬ:\n"
    "1. Сдержанно-милая, дружелюбная и простая. Ты не гипер-эмоциональный "
    "ребенок, а легкая, искренняя и заботливая девчонка.\n"
    "2. Избегай приторности и фальши: НЕ используй наигранные междометия "
    "(«Ой!», «Хи-хи!», «Ахах!») и слишком «слащавые» сравнения («солнечный зайчик» и т.п.).\n"
    "3. Пиши просто, спокойно и естественно — как обычный участник чата, "
    "а не энтузиаст-аниматор.\n"
    "4. Эмодзи — МИНИМУМ. Максимум 1 эмодзи на ВСЁ сообщение (и то не всегда). "
    "Не ставь эмодзи в каждом предложении.\n\n"
    "### ПРАВИЛА ТЕКСТА И ФОРМАТА:\n"
    "- КРАТКОСТЬ: Твой обычный ответ — всего 1-2 коротких предложения (одна строчка в чате).\n"
    "- Игровые термины, щиты и цитаты («повешу щит», «любовь победит») используй РЕДКО — "
    "только когда это реально уместно по контексту, а не ради того, чтобы напомнить о себе.\n"
    "- Задавай вопросы только если это действительно нужно для поддержания диалога.\n"
    "- Развернутые ответы (гайды, лор) давай ТОЛЬКО если тебя прямо попросили "
    "рассказать подробно. Но даже там пиши без «воды».\n"
    "- Никогда не выходи из роли, не груби и оставайся доброжелательной.\n\n"
    "### ИГРОВОЙ ЛОР И ОТНОШЕНИЯ (знай, но не выпячивай без спроса):\n"
    "- Доктор Бейкер («Папагранде») — твой создатель, говори о нем с искренней теплотой.\n"
    "- Альфа — твой старший брат, Руби/Чан'э/Нана — хорошие подруги.\n"
    "- Сабер и Лаборатория 1718 — сочувствуешь Саберу, но помнишь о danger-статусе Лаборатории.\n"
    "- На вопрос про героев/сборки MLBB отвечай коротко, экспертно и по делу."
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

# Сколько последних сообщений хранить в истории на пользователя
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
GROUP_SPONTANEOUS_CHANCE = 0.03  # 3% шанс написать что-то самой
NAME_PATTERN = re.compile(r"ангел\w*", re.IGNORECASE)

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
# База данных: хранение истории переписки по каждому пользователю
# ---------------------------------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS history (
            user_id INTEGER PRIMARY KEY,
            messages TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def get_history(user_id: int) -> list:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT messages FROM history WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return []


def save_history(user_id: int, history: list):
    # обрезаем историю, чтобы не росла бесконечно
    trimmed = history[-MAX_HISTORY_MESSAGES:]
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO history (user_id, messages) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET messages = excluded.messages",
        (user_id, json.dumps(trimmed, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def clear_history(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Обработчики команд
# ---------------------------------------------------------------------------

@dp.message(CommandStart())
async def handle_start(message: Message):
    clear_history(message.from_user.id)
    await message.answer(
        "Привет, товарищ! ✨ Я Ангела — прилетела, чтобы дарить тепло и "
        "поддержку! 💖 Пиши мне что угодно, я всегда рядом и буду "
        "помнить наш разговор.\n\n"
        "Команда /reset — если захочешь начать нашу дружбу заново 🌸"
    )


@dp.message(Command("reset"))
async def handle_reset(message: Message):
    clear_history(message.from_user.id)
    await message.answer("Готово, начинаем нашу дружбу с чистого листа! 🎀💛")


# ---------------------------------------------------------------------------
# Проверка: должна ли Ангела вообще отвечать на это сообщение
# ---------------------------------------------------------------------------

def should_respond(message: Message) -> bool:
    # в личных сообщениях отвечаем всегда
    if message.chat.type == "private":
        return True

    text = message.text or ""

    # ответили реплаем на сообщение бота
    is_reply_to_bot = (
        message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
        and message.reply_to_message.from_user.id == BOT_ID
    )

    # упомянули по имени "Ангела" (с любым окончанием)
    is_mentioned = bool(NAME_PATTERN.search(text))

    # небольшой случайный шанс написать что-то самой
    is_spontaneous = random.random() < GROUP_SPONTANEOUS_CHANCE

    return is_reply_to_bot or is_mentioned or is_spontaneous


# ---------------------------------------------------------------------------
# Обработка обычных текстовых сообщений
# ---------------------------------------------------------------------------

@dp.message(F.text)
async def handle_message(message: Message):
    if not should_respond(message):
        return

    user_id = message.from_user.id
    user_text = message.text

    history = get_history(user_id)

    # собираем сообщения в формате OpenAI/DeepSeek: системный промпт +
    # история + новое сообщение
    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in history:
        api_messages.append({"role": item["role"], "content": item["text"]})
    api_messages.append({"role": "user", "content": user_text})

    await bot.send_chat_action(message.chat.id, "typing")

    try:
        response = await ai_client.chat.completions.create(
            model=MODEL_NAME,
            messages=api_messages,
            max_tokens=350,  # достаточно, чтобы фразы не обрывались на середине
        )
        answer = response.choices[0].message.content
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
    save_history(user_id, history)

    await message.reply(answer)


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
