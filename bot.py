import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from dateparser.search import search_dates
from datetime import datetime

TOKEN = "8443607513:AAHYWF7Tb9X0olHLgtPK_pmWPEOte9mM77A"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

active_replacements = {}
private_messages = {}  # для хранения сообщений в личке

FIND_WORDS = ["ищу замену", "отдам смену"]
OFFER_WORDS = ["заберу смену", "отдайте смену"]

SHIFT_KEYWORDS = {
    "утро": "с утра",
    "с утра": "с утра",
    "вечер": "с вечера",
    "вечером": "с вечера",
}

ROLE_SYNONYMS = {
    "официант": ["официант", "офик", "принимающий"],
    "раздачник": ["раздачник", "раздача", "раздаче"],
    "хостес": ["хостес", "хост", "на хосте"],
}


def highlight_dates(text: str):
    result = search_dates(
        text,
        languages=["ru"],
        settings={"PREFER_DATES_FROM": "future", "RELATIVE_BASE": datetime.now()},
    )
    if not result:
        return text, None

    new_text = text
    parsed_date = None
    for phrase, dt in result:
        parsed_date = dt.date()
        new_text = new_text.replace(phrase, f"📅 {dt.strftime('%d.%m.%Y')}")
    return new_text, parsed_date


def extract_shift(text: str):
    for k, v in SHIFT_KEYWORDS.items():
        if k in text.lower():
            return v
    return None


def extract_role(text: str):
    text_lower = text.lower()
    for role, variants in ROLE_SYNONYMS.items():
        for var in variants:
            if var in text_lower:
                return role
    return None


def cleanup_expired_replacements():
    now = datetime.now().date()
    expired = [msg_id for msg_id, r in active_replacements.items() if r["date"] and r["date"] < now]
    for msg_id in expired:
        active_replacements.pop(msg_id)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Актуальные замены", callback_data="show_active")]
    ])
    await message.answer(
        "Привет! Я бот для поиска замен.\n\n"
        "📌 В группе пиши сообщения типа:\n"
        "— 'Ищу замену завтра вечером официант'\n"
        "— 'Заменю в пятницу с утра хостес'\n\n"
        "Я сохраню их и покажу список по кнопке.",
        reply_markup=kb
    )


@dp.message()
async def handle_message(message: types.Message):
    if message.chat.type == "private":
        return

    text = message.text.lower()
    if any(word in text for word in FIND_WORDS):
        await handle_replacement(message, mode="find")
    elif any(word in text for word in OFFER_WORDS):
        await handle_replacement(message, mode="offer")


async def handle_replacement(message: types.Message, mode: str):
    user = message.from_user
    text_with_date, parsed_date = highlight_dates(message.text)
    shift = extract_shift(message.text)
    role = extract_role(message.text)

    if mode == "find":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Взять смену", callback_data="take")]
        ])
        header = "📌 Запрос на замену"
        short = f"@{user.username or user.full_name} хочет отдать смену"
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Отдать смену", callback_data="give")]
        ])
        header = "📌 Предложение замены"
        short = f"@{user.username or user.full_name} предлагает заменить"

    msg = await message.answer(
        f"{header}:\n\n"
        f"{short}\n"
        f"👤 Должность: {role or 'сотрудник'}\n"
        f"🕐 Смена: {shift or 'не указано'}\n"
        f"📅 Дата: {parsed_date.strftime('%d.%m.%Y') if parsed_date else 'не указана'}",
        reply_markup=kb
    )

    try:
        await message.delete()
    except:
        pass

    active_replacements[msg.message_id] = {
        "mode": mode,
        "author": user.username or user.full_name,
        "author_id": user.id,
        "date": parsed_date,
        "shift": shift,
        "role": role,
        "chat_id": message.chat.id,
        "msg_id": msg.message_id,
    }


@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery):
    user = callback.from_user
    data = callback.data

    if data == "show_active":
        cleanup_expired_replacements()

        if user.id in private_messages:
            for msg_id in private_messages[user.id]:
                try:
                    await bot.delete_message(user.id, msg_id)
                except:
                    pass
            private_messages[user.id] = []

        if not active_replacements:
            sent = await callback.message.answer("Сейчас нет активных замен ✅")
            private_messages.setdefault(user.id, []).append(sent.message_id)
            return

        text = "📋 <b>Актуальные замены:</b>\n\n"
        for r in active_replacements.values():
            link = f"https://t.me/c/{str(r['chat_id'])[4:]}/{r['msg_id']}"
            text += (
                f"— @{r['author']} "
                f"👤 {r['role'] or 'сотрудник'} "
                f"🕐 {r['shift'] or 'не указано'} "
                f"{'📅 ' + r['date'].strftime('%d.%m.%Y') if r['date'] else ''}\n"
                f"<a href='{link}'>🔗 Открыть в чате</a>\n\n"
            )

        sent = await callback.message.answer(text)
        private_messages.setdefault(user.id, []).append(sent.message_id)
        return

    if data == "make_hvanch":
        try:
            await callback.message.delete()
        except:
            pass

        parts = callback.message.text.split("\n")
        role_line = [p for p in parts if p.startswith("👤")]
        shift_line = [p for p in parts if p.startswith("🕐")]
        date_line = [p for p in parts if p.startswith("📅")]
        user_line = parts[0]

        role = role_line[0].replace("👤 Должность: ", "") if role_line else "сотрудник"
        shift = shift_line[0].replace("🕐 Смена: ", "") if shift_line else "не указано"
        date = date_line[0].replace("📅 ", "") if date_line else "не указана"

        if "забрал" in user_line or "заменит" in user_line:
            target_user = user_line.split()[1]
        else:
            target_user = "@user"

        new_text = (
            f"✨ <b>Замена</b> ✨\n\n"
            f"Дорогие менеджеридзе,\n"
            f"можно выйду за {target_user}\n\n"
            f"📅 Дата: {date}\n"
            f"🕐 Смена: {shift}\n"
            f"👤 Должность: {role}\n\n"
            f"Одобряете? @sshev07 @sssdinara"
        )

        await callback.message.answer(new_text)
        return

    msg_id = callback.message.message_id
    if msg_id not in active_replacements:
        await callback.answer("Эта замена уже закрыта ❌", show_alert=True)
        return

    r = active_replacements.pop(msg_id)

    hvanch_btn = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Сделать макет для ХВАНЧ", callback_data="make_hvanch")]]
    )

    if r["mode"] == "find" and data == "take":
        new_text = (
            f"✅ @{user.username or user.full_name} заменит @{r['author']}\n"
            f"👤 Должность: {r['role'] or 'сотрудник'}\n"
            f"🕐 Смена: {r['shift'] or 'не указано'}\n"
            f"📅 {r['date'].strftime('%d.%m.%Y') if r['date'] else 'не указана'}"
        )
        await bot.send_message(r["author_id"], new_text, reply_markup=hvanch_btn)
        await bot.send_message(user.id, new_text.replace("заменит", "вы замените"), reply_markup=hvanch_btn)

    elif r["mode"] == "offer" and data == "give":
        new_text = (
            f"✅ @{r['author']} заменит @{user.username or user.full_name}\n"
            f"👤 Должность: {r['role'] or 'сотрудник'}\n"
            f"🕐 Смена: {r['shift'] or 'не указано'}\n"
            f"📅 {r['date'].strftime('%d.%m.%Y') if r['date'] else 'не указана'}"
        )
        await bot.send_message(r["author_id"], new_text, reply_markup=hvanch_btn)
        await bot.send_message(user.id, new_text.replace("заменит", "вы приняли смену у"), reply_markup=hvanch_btn)

    await callback.message.edit_text(new_text)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
