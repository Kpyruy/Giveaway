from datetime import datetime
import asyncio
import aiogram
import random
import re
import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ParseMode
from aiogram.types.message import ContentType
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from configparser import ConfigParser
from pymongo import MongoClient
import motor.motor_asyncio
import json

import logging
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher.handler import CancelHandler, current_handler

cluster = motor.motor_asyncio.AsyncIOMotorClient("mongodb+srv://Admin:T8Lylcpso9jNs5Yw@cluster0.1t9opzs.mongodb.net/RandomBot?retryWrites=true&w=majority")
user_collections = cluster.RandomBot.user
key_collection = cluster.RandomBot.key
contests_collection = cluster.RandomBot.contests
promo_collection = cluster.RandomBot.promo

timezone = pytz.timezone('Europe/Kiev')
current_time = datetime.now(timezone)
current_date_time = current_time.strftime('%Y-%m-%d %H:%M:%S')

config = ConfigParser()
config.read('private/.env')

BOT_TOKEN = config.get('BOT', 'TOKEN')
PAYMENTS_TOKEN = config.get('PAYMENTS', 'PAYMENTS_TOKEN')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

class MenuCategories(StatesGroup):
    main_menu = State()
    key = State()
    uses = State()
    waiting_for_key = State()
    search = State()
    id_check = State()
    search_check = State()
    contest_search_profile = State()

class CreateContestState(StatesGroup):
    name = State()
    description = State()
    winners = State()
    end_date = State()

class ChangeContestState(StatesGroup):
    name_change = State()
    description_change = State()
    winners_change = State()
    date_change = State()

def format_participants(members):
    if members % 10 == 1 and members % 100 != 11:
        return "участник"
    elif 2 <= members % 10 <= 4 and (members % 100 < 10 or members % 100 >= 20):
        return "участника"
    else:
        return "участников"

async def add_user(user_id):
    current_date = datetime.now(timezone).strftime("%Y-%m-%d")
    user_data = {
        "_id": user_id,
        "creation_date": current_date,
        "participation": 0,
        "wins": 0,
        "status": "Новичок 🆕",
        "keys": 0,
        "ban_members": []
    }
    user_collections.insert_one(user_data)

async def update_status(user_id):
    user_data = await user_collections.find_one({"_id": user_id})
    status = user_data.get("status")
    if status == "Создатель 🎭" or status == "Тестер ✨" or status == "Админ 🚗":
        return  # Не менять статус для пользователя с айди

    wins = user_data.get("wins", 0)
    participation = user_data.get("participation", 0)

    if wins == 1:
        status = "Начинающий 🍥"
    elif wins == 5:
        status = "Юный победитель 🥮"
    elif wins == 10:
        status = "Молодчик 🧋"
    elif wins == 15:
        status = "Удачливый 🤞"
    elif wins == 25:
        status = "Лакер 🍀"
    elif wins == 50:
        status = "Уникум ♾️"
    elif participation == 5:
        status = "Начало положено 🍤"
    elif participation == 15:
        status = "Активный 🦈"
    elif participation == 25:
        status = "Батарейка 🔋"
    elif participation == 50:
        status = "Смотрящий 👀"
    elif participation == 100:
        status = "Невероятный 🧭"
    else:
        return  # Не менять статус, если не подходит ни одно условие

    await user_collections.update_one({"_id": user_id}, {"$set": {"status": status}})

# Get the bot's username from the bot instance
async def get_bot_username() -> str:
    bot_info = await bot.get_me()
    return bot_info.username

# Now you can generate the start link using the bot's username
async def generate_start_link(contest_id):
    bot_username = await get_bot_username()
    start_link = f"t.me/{bot_username}?start={contest_id}"
    return start_link

async def create_contest(contest_id, user_id, contest_name, contest_description, winners, end_date, start_link):
    await contests_collection.insert_one({
        "_id": int(contest_id),
        "owner_id": user_id,
        "contest_name": contest_name,
        "contest_description": contest_description,
        "winners": int(winners),
        "end_date": str(end_date),
        "members": [],
        "contest_winners": [],
        "ban_members": [],
        "join_date": [],
        "start_link": start_link,
        "ended": "False"
    })

async def update_contest_members(contest_id, user_id):
    await contests_collection.update_one(
        {"_id": int(contest_id)},
        {"$addToSet": {"members": user_id}}
    )

async def update_contest_date(contest_id):
    current_date = datetime.now(timezone).strftime("%Y-%m-%d")

    await contests_collection.update_one(
        {"_id": int(contest_id)},
        {"$addToSet": {"join_date": current_date}}
    )

async def update_contest_ban_members(contest_id, user_id):
    await contests_collection.update_one(
        {"_id": int(contest_id)},
        {"$addToSet": {"ban_members": user_id}}
    )

async def update_profile_ban_members(profile_user_id, user_id):
    await user_collections.update_one(
        {"_id": int(profile_user_id)},
        {"$addToSet": {"ban_members": user_id}}
    )

async def update_win_contest_members(contest_id, user_id):
    await contests_collection.update_one(
        {"_id": int(contest_id)},
        {"$addToSet": {"contest_winners": user_id}}
    )

async def del_profile_ban_members(profile_user_id, user_id):
    await user_collections.update_one(
        {"_id": int(profile_user_id)},
        {"$pull": {"ban_members": user_id}}
    )

def generate_key(length=16):
    characters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    key = ''.join(random.choice(characters) for _ in range(length))
    return key

async def add_key(key, uses):
    key_data = {
        "key": key,
        "uses": uses,
    }
    await key_collection.insert_one(key_data)

async def buy_key(key, uses, email, user_id):
    key_data = {
        "key": key,
        "uses": int(uses),
        "email": email,
        "user_id": int(user_id),
        "buy": "True"
    }
    await key_collection.insert_one(key_data)

async def get_username(user_id):
    # Use the get_chat method to get the user's information
    user = await bot.get_chat(user_id)

    # Access the username property of the User object
    username = user.username

    return username

async def get_ban_username(user_id):
    # Use the get_chat method to get the user's information
    user = await bot.get_chat(user_id)

    # Access the username property of the User object
    username = user.username

    return username

async def get_username_winners(user):
    # Use the get_chat method to get the user's information
    user_name = await bot.get_chat(user)

    # Access the username property of the User object
    username = user_name.username

    return username

async def show_members(callback_query, contest_id, current_page):
    # Поиск конкурса по айди
    contest = await contests_collection.find_one({"_id": int(contest_id)})
    message_id = change_message_id[-1]

    members = contest.get("members")
    participants_word = format_participants(len(members))
    result_message = f"<b>🏯 Всего</b> <code>{len(members)}</code> <b>{participants_word}</b> — <b>Страница {current_page}</b>\n\n"

    keyboard = types.InlineKeyboardMarkup()

    # Количество участников на одной странице
    per_page = 25
    start_index = (current_page - 1) * per_page
    end_index = current_page * per_page
    page_members = members[start_index:end_index] if start_index < len(members) else []
    for idx, user_id in enumerate(page_members, start=start_index + 1):
        username = await get_username(user_id)
        if username:
            username = username.replace("_", "&#95;")
        result_message += f"{idx}. @{username} (<code>{user_id}</code>)\n"

    # Кнопки перелистывания
    prev_button = types.InlineKeyboardButton(text='◀️ Назад', callback_data=f'members_{contest_id}_prev_{current_page}')
    next_button = types.InlineKeyboardButton(text='Вперед ▶️', callback_data=f'members_{contest_id}_next_{current_page}')
    contest_profile = types.InlineKeyboardButton(text='Детальнее 🧶', callback_data=f'contest_search_profile_{contest_id}')
    banned_members = types.InlineKeyboardButton(text='Заблок. участники ‼️', callback_data=f'ban_members_{contest_id}_None_1')
    back = types.InlineKeyboardButton(text='Назад 🧿', callback_data='change')

    # Add both buttons if there are both previous and next pages
    if current_page > 1 and end_index < len(members):
        keyboard.row(prev_button, next_button)
    # Add only the previous button if there are no more pages
    elif current_page > 1:
        keyboard.row(prev_button)
    # Add only the next button if this is the first page
    elif end_index < len(members):
        keyboard.row(next_button)

    if len(members) >= 1:
        keyboard.row(banned_members, contest_profile)
    keyboard.row(back)

    reply = await bot.edit_message_text(result_message, callback_query.message.chat.id, message_id,
                                        parse_mode="HTML",
                                        reply_markup=keyboard)

    # Сохранение ID сообщения в глобальную переменную
    change_message_id.append(reply.message_id)

async def show_ban_members(callback_query, contest_id, current_page):
    # Поиск конкурса по айди
    contest = await contests_collection.find_one({"_id": int(contest_id)})
    message_id = change_message_id[-1]

    ban_members = contest.get("ban_members")
    result_message = f"<b>‼️Заблокированные участники — Страница {current_page}</b>\n\n"

    keyboard = types.InlineKeyboardMarkup()

    # Количество участников на одной странице
    per_page = 25
    start_index = (current_page - 1) * per_page
    end_index = current_page * per_page
    page_members = ban_members[start_index:end_index] if start_index < len(ban_members) else []
    for idx, user_id in enumerate(page_members, start=start_index + 1):
        username = await get_username(user_id)
        if username:
            username = username.replace("_", "&#95;")
        result_message += f"{idx}. @{username} (<code>{user_id}</code>)\n"

    # Кнопки перелистывания
    prev_button = types.InlineKeyboardButton(text='◀️ Назад', callback_data=f'members_{contest_id}_prev_{current_page}')
    next_button = types.InlineKeyboardButton(text='Вперед ▶️', callback_data=f'members_{contest_id}_next_{current_page}')
    contest_profile = types.InlineKeyboardButton(text='Детальнее 🧶', callback_data=f'contest_search_profile_{contest_id}')
    back = types.InlineKeyboardButton(text='Назад 🧿', callback_data='change')

    # Add both buttons if there are both previous and next pages
    if current_page > 1 and end_index < len(ban_members):
        keyboard.row(prev_button, next_button)
    # Add only the previous button if there are no more pages
    elif current_page > 1:
        keyboard.row(prev_button)
    # Add only the next button if this is the first page
    elif end_index < len(ban_members):
        keyboard.row(next_button)

    if len(ban_members) < 1:
        result_message += "<code>Заблокированных пользователей не обнаружено‼️</code>"
    else:
        keyboard.row(contest_profile)
    keyboard.row(back)

    reply = await bot.edit_message_text(result_message, callback_query.message.chat.id, message_id,
                                        parse_mode="HTML",
                                        reply_markup=keyboard)

    # Сохранение ID сообщения в глобальную переменную
    change_message_id.append(reply.message_id)

async def show_user_history(callback_query, user_id, current_page):
    # Retrieve contests where the user with the specified user_id was a member
    user_history = await contests_collection.find({"members": user_id}).to_list(length=None)

    if user_history:
        # Your logic to display user history based on the current_page
        per_page = 5
        start_index = (current_page - 1) * per_page
        end_index = current_page * per_page
        page_history = user_history[start_index:end_index] if start_index < len(user_history) else []
        all_pages = len(user_history) // per_page

        if all_pages == 0:
            all_pages = 1
        else:
            pass
        # Create the message containing the user history for the current page
        result_message = f"*📒 История участий - Страница* `{current_page}` из `{all_pages}`:\n\n"
        for idx, contest in enumerate(page_history, start=start_index + 1):
            # Extract relevant information about the contest, e.g., its title, end date, etc.
            contest_name = contest.get("contest_name")
            contest_id = contest.get("_id")
            contest_end_date = contest.get("end_date")
            contest_members = contest.get("members")
            if contest_name == str(contest_id):
                # Format the contest information as needed
                result_message += f"                            *= {idx} =*\n" \
                                  f"*🪁 Имя:* `{contest_name}`\n" \
                                  f"*👤 Количество участников:* `{len(contest_members)}`\n" \
                                  f"*🗓️ Дата окончания:* `{contest_end_date}`\n\n"
            else:
                # Format the contest information as needed
                result_message += f"                            *= {idx} =*\n" \
                                  f"*🪁 Имя:* `{contest_name}`\n" \
                                  f"*🧊 Идентификатор:* `{contest_id}`\n" \
                                  f"*👤 Количество участников:* `{len(contest_members)}`\n" \
                                  f"*🗓️ Дата окончания:* `{contest_end_date}`\n\n"

        # Calculate the total number of pages
        total_pages = (len(user_history) + per_page - 1) // per_page

        # Create the inline keyboard with pagination buttons
        keyboard = types.InlineKeyboardMarkup()
        prev_button = types.InlineKeyboardButton(text='◀️ Предыдущая', callback_data=f'history_{user_id}_prev_{current_page}')
        next_button = types.InlineKeyboardButton(text='Следущая ▶️', callback_data=f'history_{user_id}_next_{current_page}')

        if current_page > 1 and end_index < total_pages:
            keyboard.row(prev_button, next_button)
        elif current_page > 1:
            keyboard.row(prev_button)
        elif current_page < total_pages:
            keyboard.row(next_button)
        back = types.InlineKeyboardButton(text='Назад 🥏', callback_data='profile_edit')
        keyboard.row(back)

        # Send or edit the message with pagination
        reply = await bot.edit_message_text(result_message, callback_query.message.chat.id,
                                            callback_query.message.message_id, parse_mode="Markdown", reply_markup=keyboard)
        profile_messages.append(reply.message_id)
    else:
        result_message = "*📒 У вас не была обнаружена история участий!*"
        keyboard = types.InlineKeyboardMarkup()
        back = types.InlineKeyboardButton(text='Назад 🥏', callback_data='profile_edit')
        keyboard.row(back)

        # Send or edit the message with pagination
        reply = await bot.edit_message_text(result_message, callback_query.message.chat.id,
                                            callback_query.message.message_id, parse_mode="Markdown", reply_markup=keyboard)
        profile_messages.append(reply.message_id)

async def promo_members(chat_id, promo, current_page):
    # Поиск конкурса по айди
    promo_code = await promo_collection.find_one({"_id": promo})

    members = promo_code.get("active_members")
    result_message = f"<b>📋 Список пользователей для промокода</b> <code>{promo}</code>:\n\n" \
                     f"                                   <b>Страница {current_page}</b>\n\n"

    keyboard = types.InlineKeyboardMarkup()

    # Количество участников на одной странице
    per_page = 25
    start_index = (current_page - 1) * per_page
    end_index = current_page * per_page
    page_members = members[start_index:end_index] if start_index < len(members) else []
    for idx, user_id in enumerate(page_members, start=start_index + 1):
        username = await get_username(user_id)
        if username:
            username = username.replace("_", "&#95;")
        result_message += f"<b>{idx}.</b> @{username} <b>(</b><code>{user_id}</code><b>)</b>\n"

    # Кнопки перелистывания
    prev_button = types.InlineKeyboardButton(text='◀️ Назад', callback_data=f'promo_{promo}_prev_{current_page}')
    next_button = types.InlineKeyboardButton(text='Вперед ▶️', callback_data=f'promo_{promo}_next_{current_page}')
    back = types.InlineKeyboardButton(text='Выполенено ✅', callback_data='done')

    # Add both buttons if there are both previous and next pages
    if current_page > 1 and end_index < len(members):
        keyboard.row(prev_button, next_button)
    # Add only the previous button if there are no more pages
    elif current_page > 1:
        keyboard.row(prev_button)
    # Add only the next button if this is the first page
    elif end_index < len(members):
        keyboard.row(next_button)
    keyboard.row(back)
    uses = promo_code.get("uses")
    result_message += f"\n\n<b>🧪 Осталось активаций:</b> <code>{uses}</code>"
    # Send the formatted message with the keyboard
    reply = await bot.send_message(chat_id, result_message,
                                   parse_mode="HTML",
                                   reply_markup=keyboard)

    # Сохранение ID сообщения в глобальную переменную
    promo_message_id.append(reply.message_id)

async def handle_promo_code(promo_code: str, user_id: int):
    promo = await promo_collection.find_one({"_id": promo_code})

    if promo:
        active_members = promo.get("active_members", [])

        if user_id in active_members:
            await bot.send_message(user_id, "*❌ Вы уже активировали данный промокод.*", parse_mode="Markdown")
        else:
            uses = promo.get("uses", 0)
            if uses > 0:
                await activate_promo_code(promo_code, user_id)
            else:
                await bot.send_message(user_id, "*❌ Промокод больше не действителен.*", parse_mode="Markdown")
    else:
        await bot.send_message(user_id, "*Промокод не найден. ❌*", parse_mode="Markdown")

async def create_promo_codes(promo_name: str, quantity: int, visible: str, prize: str, user_id: int):
    promo_code = generate_promo_code()

    existing_promo = await promo_collection.find_one({"_id": promo_name})
    if existing_promo:
        await bot.send_message(user_id, f"*❌ Промокод* `{promo_name}` *уже существует!*", parse_mode="Markdown")
        return

    if promo_name == "random":
        promo = {
            "_id": promo_code,
            "user_id": user_id,
            "uses": quantity,
            "prize": prize,
            "active_members": [],
            "visible": visible
        }
        if visible == "False":
            message = f"*🧪 Промокод* `{promo_code}` *был успешно создан!*\n" \
                      f"*🎬 Количество активаций:* `{quantity}`\n"\
                      f"*🤫 Статус:* `скрыт`\n"
            if prize == "key":
                message = f"*🧪 Промокод* `{promo_code}` *был успешно создан!*\n" \
                       f"*🎬 Количество активаций:* `{quantity}`\n" \
                       f"*🤫 Статус:* `скрыт`\n" \
                       f"*🎁 Награда:* `+1 ключ`"
            else:
                message = f"*🧪 Промокод* `{promo_code}` *был успешно создан!*\n" \
                       f"*🎬 Количество активаций:* `{quantity}`\n"
        else:
            if prize == "key":
                message = f"*🧪 Промокод* `{promo_code}` *был успешно создан!*\n" \
                       f"*🎬 Количество активаций:* `{quantity}`\n" \
                       f"*🤫 Статус:* `скрыт`\n" \
                       f"*🎁 Награда:* `+1 ключ`"
            else:
                message = f"*🧪 Промокод* `{promo_code}` *был успешно создан!*\n" \
                       f"*🎬 Количество активаций:* `{quantity}`\n"
    else:
        promo = {
            "_id": promo_name,
            "user_id": user_id,
            "uses": quantity,
            "prize": prize,
            "active_members": [],
            "visible": visible
        }
        if visible == "False":
            message = f"*🧪 Промокод* `{promo_name}` *был успешно создан!*\n" \
                      f"*🎬 Количество активаций:* `{quantity}`\n"\
                      f"*🤫 Статус:* `скрыт`\n"
            if prize == "key":
                message = f"*🧪 Промокод* `{promo_name}` *был успешно создан!*\n" \
                       f"*🎬 Количество активаций:* `{quantity}`\n" \
                       f"*🤫 Статус:* `скрыт`\n" \
                       f"*🎁 Награда:* `+1 ключ`"
            else:
                message = f"*🧪 Промокод* `{promo_name}` *был успешно создан!*\n" \
                       f"*🎬 Количество активаций:* `{quantity}`\n"
        else:
            if prize == "key":
                message = f"*🧪 Промокод* `{promo_name}` *был успешно создан!*\n" \
                       f"*🎬 Количество активаций:* `{quantity}`\n" \
                       f"*🤫 Статус:* `скрыт`\n" \
                       f"*🎁 Награда:* `+1 ключ`"
            else:
                message = f"*🧪 Промокод* `{promo_name}` *был успешно создан!*\n" \
                       f"*🎬 Количество активаций:* `{quantity}`\n"


    await promo_collection.insert_one(promo)

    await bot.send_message(user_id, text=message, parse_mode="Markdown")

async def get_active_promo_codes():
    active_promos = await promo_collection.find({"visible": "True"}).to_list(length=None)

    if active_promos:
        promo_ids = [f"*{idx + 1}.* `{promo['_id']}`" for idx, promo in enumerate(active_promos)]
        promo_list = "\n".join(promo_ids)
        return promo_list
    else:
        return None

async def activate_promo_code(promo_code: str, user_id: int):
    await promo_collection.update_one({"_id": promo_code}, {"$push": {"active_members": user_id}})
    await promo_collection.update_one({"_id": promo_code}, {"$inc": {"uses": -1}})

    promo = await promo_collection.find_one({"_id": promo_code})
    prize = promo.get("prize")
    if prize == "None":
        pass
    elif prize == "key":
        await user_collections.update_one({"_id": user_id}, {"$inc": {"keys": 1}})
    else:
        pass
    await bot.send_message(user_id, f"*Промокод* `{promo_code}` *активирован. ✅*", parse_mode="Markdown")

def generate_promo_code():
    promo_length = 8  # Длина промокода
    allowed_characters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return ''.join(random.choices(allowed_characters, k=promo_length))

# Объявление глобальных переменных
contest_name = None
contest_id = None
contest_description = None
winners = None
end_date = None

# Глобальная переменная для хранения ID сообщений
profile_messages = []
generate_message = []
contest_messages = []
change_message_id = []
permanent_message_id = []
promo_message_id = []

@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    if message.chat.type != 'private':
        await bot.send_message(message.chat.id, "*❌ Команда /start доступна только в личных сообщениях.*", parse_mode="Markdown")
        return

    user_id = message.from_user.id
    existing_user = await user_collections.find_one({"_id": user_id})

    if existing_user:
        # Код для существующего пользователя
        contest_id = message.get_args()
        if contest_id:
            contest = await contests_collection.find_one({"_id": int(contest_id)})
            if contest:
                owner_id = contest.get("owner_id")
                owner_data = await user_collections.find_one({"_id": int(owner_id)})

            if contest:
                ended = contest.get("ended")  # Проверяем значение параметра "ended", по умолчанию False

                if ended == "True":
                    # Код, если конкурс завершен
                    end_message = await message.reply("*Упс... Конкурс завершен❗️*", parse_mode="Markdown")
                    await asyncio.sleep(3.5)
                    await bot.delete_message(chat_id=message.chat.id, message_id=end_message.message_id)
                else:
                    if user_id in contest['members']:
                        # Пользователь уже зарегистрирован в конкурсе
                        registered = await message.reply("*‼️ Вы уже зарегистрированы в этом конкурсе.*",
                                                         parse_mode="Markdown")
                        await asyncio.sleep(3.5)
                        await bot.delete_message(chat_id=message.chat.id, message_id=registered.message_id)
                        keyboard = types.InlineKeyboardMarkup()
                        active_drawings = types.InlineKeyboardButton(text='🔋 Активные розыгрыши',
                                                                     callback_data='active_drawings')
                        profile = types.InlineKeyboardButton(text='🥂 Профиль', callback_data='profile')
                        support = types.InlineKeyboardButton(text='🆘 Поддержка', callback_data='support')
                        keyboard.row(active_drawings, support)
                        keyboard.row(profile)

                        await message.reply(
                            "*🎭 Рады вас снова видеть!*\n\n*🪶 Как всегда, воспользуйтесь кнопками для дальнейшего взаимодействия:*",
                            parse_mode="Markdown", reply_markup=keyboard)
                    elif user_id in contest['ban_members']:
                        # Пользователь заблокирован в конкурсе
                        await message.reply("*❌ Вы заблокированы в этом конкурсе.*",
                                                    parse_mode="Markdown")
                    elif user_id in owner_data['ban_members']:
                        # Пользователь заблокирован в конкурсе
                        await message.reply("*❌ Вы не можете принимать участие в конкурсах этого пользователя.*",
                                                    parse_mode="Markdown")
                    else:
                        # Добавление пользователя в участники конкретного конкурса
                        await update_contest_members(contest_id, user_id)
                        # Обновление значения participation пользователя
                        await user_collections.update_one({"_id": user_id}, {"$inc": {"participation": 1}})
                        # Код для успешного добавления пользователя в конкурс
                        keyboard = types.InlineKeyboardMarkup()
                        active_drawings = types.InlineKeyboardButton(text='🔋 Активные розыгрыши', callback_data='active_drawings')
                        profile = types.InlineKeyboardButton(text='🥂 Профиль', callback_data='profile')
                        support = types.InlineKeyboardButton(text='🆘 Поддержка', callback_data='support')
                        keyboard.row(active_drawings, support)
                        keyboard.row(profile)

                        # Обновление статуса пользователя
                        await update_status(user_id)
                        await update_contest_date(contest_id)
                        await message.reply(
                            f"*🎭 Вы успешно добавлены в конкурс* `{contest_id}`*!*\n\n"
                            "*🪶 Воспользуйтесь кнопками для дальнейшего взаимодействия:*",
                            parse_mode="Markdown", reply_markup=keyboard
                        )
                    return
            else:
                # Код, если конкурс с указанной ссылкой не найден
                true_contest = await message.reply("*К сожалению, такого конкурса не существует. ❌*",
                                                   parse_mode="Markdown")
                await asyncio.sleep(3)
                await bot.delete_message(chat_id=message.chat.id, message_id=true_contest.message_id)

        keyboard = types.InlineKeyboardMarkup()
        active_drawings = types.InlineKeyboardButton(text='🔋 Активные розыгрыши', callback_data='active_drawings')
        profile = types.InlineKeyboardButton(text='🥂 Профиль', callback_data='profile')
        support = types.InlineKeyboardButton(text='🆘 Поддержка', callback_data='support')
        keyboard.row(active_drawings, support)
        keyboard.row(profile)

        await message.reply(
            "*🎭 Рады вас снова видеть!*\n\n*🪶 Как всегда, воспользуйтесь кнопками для дальнейшего взаимодействия:*",
            parse_mode="Markdown", reply_markup=keyboard)
    else:
        await add_user(user_id)
        # Код для нового пользователя
        contest_id = message.get_args()
        if contest_id:
            contest = await contests_collection.find_one({"_id": contest_id})
            if contest:
                if user_id in contest['members']:
                    # Пользователь уже зарегистрирован в конкурсе
                    registered = await message.reply("*‼️ Вы уже зарегистрированы в этом конкурсе.*", parse_mode="Markdown")
                    await asyncio.sleep(3.5)
                    await bot.delete_message(chat_id=message.chat.id, message_id=registered.message_id)
                elif user_id in contest['ban_members']:
                    # Пользователь заблокирован в конкурсе
                    await message.reply("*❌ Вы заблокированы в этом конкурсе.*",
                                                parse_mode="Markdown")
                else:
                    # Добавление пользователя в участники конкретного конкурса
                    await update_contest_members(contest_id, user_id)
                    # Обновление значения participation пользователя
                    await user_collections.update_one({"_id": user_id}, {"$inc": {"participation": 1}})
                    # Код для успешного добавления пользователя в конкурс
                    keyboard = types.InlineKeyboardMarkup()
                    active_drawings = types.InlineKeyboardButton(text='🔋 Активные розыгрыши', callback_data='active_drawings')
                    profile = types.InlineKeyboardButton(text='🥂 Профиль', callback_data='profile')
                    support = types.InlineKeyboardButton(text='🆘 Поддержка', callback_data='support')
                    keyboard.row(active_drawings, support)
                    keyboard.row(profile)

                    await message.reply(
                        f"*🎭 Вы успешно добавлены в конкурс* `{contest_id}`*!*\n\n"
                        "*🪶 Воспользуйтесь кнопками для дальнейшего взаимодействия:*",
                        parse_mode="Markdown", reply_markup=keyboard
                    )
                    await update_status(user_id)
                    await update_contest_date(contest_id)
                    return
            else:
                # Код, если конкурс с указанной ссылкой не найден
                true_contest = await message.reply("*К сожалению, такого конкурса не существует. ❌*", parse_mode="Markdown")
                await asyncio.sleep(3.5)
                await bot.delete_message(chat_id=message.chat.id, message_id=true_contest.message_id)

        keyboard = types.InlineKeyboardMarkup()
        active_drawings = types.InlineKeyboardButton(text='🔋 Активные розыгрыши', callback_data='active_drawings')
        profile = types.InlineKeyboardButton(text='🥂 Профиль', callback_data='profile')
        support = types.InlineKeyboardButton(text='🆘 Поддержка', callback_data='support')
        keyboard.row(active_drawings, support)
        keyboard.row(profile)

        await message.reply(
            "*🎭 Добро пожаловать в конкурс бота!*\n\n*🪶 Воспользуйтесь кнопками для дальнейшего взаимодействия:*",
            parse_mode="Markdown", reply_markup=keyboard)

# Ветка генерации ключа
@dp.message_handler(commands=['generate'])
async def generate_command(message: types.Message):

    if message.chat.type != 'private':
        await bot.send_message(message.chat.id, "*❌ Команда /generate доступна только в личных сообщениях.*", parse_mode="Markdown")
        return

    user_id = message.from_user.id
    user_data = await user_collections.find_one({"_id": user_id})

    if user_data and ("status" in user_data and user_data["status"] in ["Админ 🚗", "Создатель 🎭"]):
        # Если пользователь ввел команду с аргументом (числом)
        if len(message.get_args()) > 0:
            arg = message.get_args()
            if re.match("^[0-9]+$", arg):
                uses = int(arg)
                if uses >= 0 and uses <= 100:
                    key = generate_key()

                    await add_key(key, uses)

                    await message.reply(f"*🔑 Сгенерирован ключ:* `{key}`\n*🧦 Количество использований:* `{uses}`",
                                        parse_mode="Markdown")
                else:
                    int_digit = await bot.send_message(message.chat.id,
                                                       "*❌ Некорректное количество использований. Пожалуйста, введите число от 0 до 100.*",
                                                       parse_mode="Markdown")
                    await asyncio.sleep(3)
                    await bot.delete_message(chat_id=message.chat.id, message_id=int_digit.message_id)
                    return
            else:
                int_digit = await bot.send_message(message.chat.id,
                                                   "*❌ Некорректное количество использований. Пожалуйста, введите целое число.*",
                                                   parse_mode="Markdown")
                await asyncio.sleep(3)
                await bot.delete_message(chat_id=message.chat.id, message_id=int_digit.message_id)
                return
        else:
            reply = await message.reply("*Для отмены напишите:* `Отмена`\n\n*🦴 Введите количество использований ключа:*", parse_mode="Markdown")

            # Сохранение ID сообщения в глобальную переменную
            generate_message.append(reply.message_id)

            await MenuCategories.uses.set()
    else:
        # # Код для существующего пользователя
        # keyboard = types.InlineKeyboardMarkup()
        # buy_key = types.InlineKeyboardButton(text='Купить ключ 🔑', callback_data='buy_key')
        # keyboard.row(buy_key)

        await message.reply("*У вас нет доступа для генерации ключей. 🚫*", parse_mode="Markdown", reply_markup=keyboard)

@dp.message_handler(state=MenuCategories.uses)
async def process_uses(message: types.Message, state: FSMContext):
    if message.text.lower() == "отмена" or message.text == "Отмена":
        await state.finish()
        await bot.send_message(message.chat.id, "*⚠️ Генерация ключа отменена.*", parse_mode="Markdown")
        return
    global generate_message

    arg = message.text

    # Удаление сообщения пользователя
    await bot.delete_message(message.chat.id, message.message_id)

    if re.match("^[0-9]+$", arg):
        uses = int(arg)
        if uses >= 0 and uses <= 100:
            key = generate_key()

            await state.finish()

            await add_key(key, uses)

            # Get the message ID from the contest_messages list
            message_id = generate_message[-1]
            text = f"*🔑 Сгенерирован ключ:* `{key}`\n*🧦 Количество использований:* `{uses}`"

            await bot.edit_message_text(text, message.chat.id, message_id, parse_mode="Markdown")
        else:
            int_digit = await bot.send_message(message.chat.id,
                                               "*❌ Некорректное количество использований. Пожалуйста, введите число от 0 до 100.*",
                                               parse_mode="Markdown")
            await asyncio.sleep(3)
            await bot.delete_message(chat_id=message.chat.id, message_id=int_digit.message_id)
            return
    else:
        int_digit = await bot.send_message(message.chat.id,
                                           "*❌ Некорректное количество использований. Пожалуйста, введите целое число.*",
                                           parse_mode="Markdown")
        await asyncio.sleep(3)
        await bot.delete_message(chat_id=message.chat.id, message_id=int_digit.message_id)
        return

# Ветка конкурсов
@dp.message_handler(commands=['contest'])
async def start_contest_command(message: types.Message):
    if message.chat.type != 'private':
        await bot.send_message(message.chat.id, "*❌ Команда /contest доступна только в личных сообщениях.*", parse_mode="Markdown")
        return

    global contest_messages

    user_id = message.from_user.id
    user_data = await user_collections.find_one({"_id": user_id})

    if user_data and (("status" in user_data and user_data["status"] in ["Тестер ✨", "Админ 🚗", "Создатель 🎭"]) or int(user_data.get("keys", 0)) > 0):

        # Код для существующего пользователя
        keyboard = types.InlineKeyboardMarkup()
        search = types.InlineKeyboardButton(text='🔎 Проверить', callback_data='search')
        create = types.InlineKeyboardButton(text='🎫 Создать', callback_data='create')
        change = types.InlineKeyboardButton(text='🍭 Редактировать', callback_data='change')
        keyboard.row(change, search)
        keyboard.row(create)

        reply = await message.reply(
            "*🍡 Рады вас видеть в панели управления конкурсами!*\n\n*✨ Воспользуйтесь кнопками для управления конкурсом или его создания:*",
            parse_mode="Markdown", reply_markup=keyboard)

        # Сохранение ID сообщения в глобальную переменную
        contest_messages.append(reply.message_id)
    else:
        # Код для существующего пользователя
        keyboard = types.InlineKeyboardMarkup()
        input_key = types.InlineKeyboardButton(text='🔑 Ввести ключ', callback_data='input_key')
        keyboard.row(input_key)

        reply = await message.reply(
            "*👀 Воспользуйтесь кнопкой и введите уникальный ключ для доступа к созданию конкурсов:*",
            parse_mode="Markdown", reply_markup=keyboard)

        # Сохранение ID сообщения в глобальную переменную
        contest_messages.append(reply.message_id)

@dp.callback_query_handler(lambda callback_query: callback_query.data == 'input_key')
async def input_key_callback(callback_query: types.CallbackQuery, state: FSMContext):
    keyboard = types.InlineKeyboardMarkup()
    input_key_decline = types.InlineKeyboardButton(text='Отмена ❌', callback_data='input_key_decline')
    keyboard.row(input_key_decline)

    # Get the message ID from the contest_messages list
    message_id = contest_messages[-1]
    text = "*🔑 Введите уникальный ключ для доступа к созданию конкурсов:*"

    reply = await bot.edit_message_text(text, callback_query.message.chat.id, message_id, parse_mode="Markdown",
                                reply_markup=keyboard)

    # Store the message ID in the contest_messages list
    contest_messages.append(reply.message_id)

    # Set the state to waiting_for_key
    await MenuCategories.waiting_for_key.set()

@dp.callback_query_handler(lambda callback_query: callback_query.data == 'input_key_decline', state=MenuCategories.waiting_for_key)
async def input_key_decline_callback(callback_query: types.CallbackQuery, state: FSMContext):
    global contest_messages

    # Clear the waiting state
    await state.finish()

    user_id = callback_query.from_user.id
    user_data = await user_collections.find_one({"_id": user_id})

    if user_data and (("status" in user_data and user_data["status"] in ["Тестер ✨", "Админ 🚗", "Создатель 🎭"]) or int(
            user_data.get("keys", 0)) > 0):
        # Code for existing user
        keyboard = types.InlineKeyboardMarkup()
        search = types.InlineKeyboardButton(text='🔎 Проверить', callback_data='search')
        create = types.InlineKeyboardButton(text='🎫 Создать', callback_data='create')
        change = types.InlineKeyboardButton(text='🍭 Редактировать', callback_data='change')
        keyboard.row(change, search)
        keyboard.row(create)

        # Get the message ID from the contest_messages list
        message_id = contest_messages[-1]
        text = "*🍡 Рады вас видеть в панели управления конкурсами!*\n\n*✨ Воспользуйтесь кнопками для управления конкурсом или его создания:*"

        reply = await bot.edit_message_text(text, callback_query.message.chat.id, message_id, parse_mode="Markdown",
                                            reply_markup=keyboard)

        # Update the message ID in the contest_messages list
        contest_messages[-1] = reply.message_id
    else:
        # Code for existing user
        keyboard = types.InlineKeyboardMarkup()
        input_key = types.InlineKeyboardButton(text='🔑 Ввести ключ', callback_data='input_key')
        keyboard.row(input_key)

        # Get the message ID from the contest_messages list
        message_id = contest_messages[-1]
        text = "*👀 Воспользуйтесь кнопкой и введите уникальный ключ для доступа к созданию конкурсов:*"

        reply = await bot.edit_message_text(text, callback_query.message.chat.id, message_id, parse_mode="Markdown",
                                            reply_markup=keyboard)

        # Update the message ID in the contest_messages list
        contest_messages[-1] = reply.message_id

@dp.message_handler(state=MenuCategories.waiting_for_key)
async def process_key(message: types.Message, state: FSMContext):
    # Получение ввода ключа от пользователя
    key = message.text

    user_id = message.from_user.id  # Obtain the user ID from the message object

    # Удаление сообщения пользователя
    await bot.delete_message(message.chat.id, message.message_id)

    # Проверка существования ключа в базе данных
    key_data = await key_collection.find_one({"key": key})

    if key_data:
        uses = key_data.get("uses", 0)
        if uses > 0:
            # Уменьшение значения uses на 1
            await key_collection.update_one({"key": key}, {"$inc": {"uses": -1}})

            # Увеличение значения keys на 1 в коллекции user_collections
            user = await user_collections.find_one({"_id": user_id})
            if user and isinstance(user.get("keys"), int):
                await user_collections.update_one({"_id": user_id}, {"$inc": {"keys": 1}})
            else:
                await user_collections.update_one({"_id": user_id}, {"$set": {"keys": 1}})

            # Получение ID сообщения из глобальной переменной
            message_id = contest_messages[-1]

            # Обновление сообщения с новыми кнопками
            keyboard = types.InlineKeyboardMarkup()
            search = types.InlineKeyboardButton(text='🔎 Проверить', callback_data='search')
            create = types.InlineKeyboardButton(text='🎫 Создать', callback_data='create')
            change = types.InlineKeyboardButton(text='🍭 Редактировать', callback_data='change')
            keyboard.row(change, search)
            keyboard.row(create)
            text = "*🍡 Рады вас видеть в панели управления конкурсами!*\n\n*✨ Воспользуйтесь кнопками для управления конкурсом или его создания:*"

            await bot.edit_message_text(text, message.chat.id, message_id, parse_mode="Markdown", reply_markup=keyboard)
        else:
            wrong_key = await bot.send_message(message.chat.id, "*❌ Количество использований этого ключа закончилось. Попробуйте другой ключ.*", parse_mode="Markdown")
            await asyncio.sleep(5)
            await bot.delete_message(chat_id=message.chat.id, message_id=wrong_key.message_id)
    else:
        wrong_key = await bot.send_message(message.chat.id, "*❌ Неверный ключ. Попробуйте снова.*", parse_mode="Markdown")
        await asyncio.sleep(3)
        await bot.delete_message(chat_id=message.chat.id, message_id=wrong_key.message_id)

    # Сброс состояния ожидания ввода ключа
    await state.finish()

@dp.callback_query_handler(lambda query: query.data == 'continue_create')
async def continue_create_callback(query: types.CallbackQuery, state: FSMContext):
    # Обновление сообщения с новым текстом
    create_text = "*🪁 Введите имя конкурса:*"

    keyboard = types.InlineKeyboardMarkup()
    skip_name = types.InlineKeyboardButton(text=' Пропустить 🚩', callback_data='skip_name')
    keyboard.row(skip_name)

    # Получение идентификатора сообщения из списка contest_messages
    message_id = contest_messages[-1]

    await bot.edit_message_text(create_text, query.message.chat.id, message_id, parse_mode="Markdown", reply_markup=keyboard)

    # Установка состояния ожидания ввода имени конкурса
    await CreateContestState.name.set()

@dp.message_handler(state=CreateContestState.name)
async def process_name(message: types.Message, state: FSMContext):
    # Получение введенного пользователем имени конкурса
    contest_name = message.text

    # Удаление сообщения пользователя
    await bot.delete_message(message.chat.id, message.message_id)

    if not contest_name:
        # Если имя конкурса не было введено, генерируем случайное имя
        contest_name = str(random.randint(100000000, 999999999))

    # Генерация случайного идентификатора конкурса
    contest_id = str(random.randint(100000000, 999999999))

    # Сохранение имени и идентификатора конкурса (например, в базе данных или переменных)
    await state.update_data(contest_name=contest_name)
    await state.update_data(contest_id=contest_id)

    # Обновление сообщения с новыми кнопками и текстом
    skip_name_text = f"*🎗️ Введите описание для конкурса:*"

    keyboard = types.InlineKeyboardMarkup()
    skip_description = types.InlineKeyboardButton(text=' Пропустить 🚩', callback_data='skip_description')
    keyboard.add(skip_description)

    # Получение идентификатора сообщения из списка contest_messages
    message_id = contest_messages[-1]

    await bot.edit_message_text(skip_name_text, message.chat.id, message_id, parse_mode="Markdown", reply_markup=keyboard)

    # Установка состояния ожидания ввода описания конкурса
    await CreateContestState.description.set()

@dp.callback_query_handler(lambda query: query.data == 'skip_name', state=CreateContestState.name)
async def skip_name_callback(query: types.CallbackQuery, state: FSMContext):
    # Генерация случайного имени и идентификатора конкурса
    contest_name = str(random.randint(100000000, 999999999))
    contest_id = contest_name

    # Сохранение имени и идентификатора конкурса (например, в базе данных или переменных)
    await state.update_data(contest_name=contest_name)
    await state.update_data(contest_id=contest_id)
    # Обновление сообщения с новыми кнопками и текстом
    skip_name_text = f"*🎗️ Введите описание для конкурса:*"

    keyboard = types.InlineKeyboardMarkup()
    skip_description = types.InlineKeyboardButton(text=' Пропустить 🚩', callback_data='skip_description')
    keyboard.add(skip_description)

    # Получение идентификатора сообщения из списка contest_messages
    message_id = contest_messages[-1]

    await bot.edit_message_text(skip_name_text, query.message.chat.id, message_id, parse_mode="Markdown", reply_markup=keyboard)

    # Установка состояния ожидания ввода описания конкурса
    await CreateContestState.description.set()

@dp.message_handler(state=CreateContestState.description)
async def process_description(message: types.Message, state: FSMContext):
    # Получение введенного пользователем описания конкурса
    contest_description = message.text

    # Удаление сообщения пользователя
    await bot.delete_message(message.chat.id, message.message_id)

    if not contest_description:
        contest_description = "Описание отсутсвует 🚫"
    # Сохранение описания конкурса (например, в базе данных или переменной)
    await state.update_data(description=contest_description)

    # Обновление сообщения с новыми кнопками и текстом
    skip_winners_text = f"*🎖️ Введите количество победителей в конкурсе:*"

    keyboard = types.InlineKeyboardMarkup()
    skip_winners = types.InlineKeyboardButton(text=' Пропустить 🚩', callback_data='skip_winners')
    keyboard.add(skip_winners)

    # Получение идентификатора сообщения из списка contest_messages
    message_id = contest_messages[-1]

    await bot.edit_message_text(skip_winners_text, message.chat.id, message_id, parse_mode="Markdown", reply_markup=keyboard)

    # Установка состояния ожидания ввода описания конкурса
    await CreateContestState.winners.set()

@dp.callback_query_handler(lambda query: query.data == 'skip_description', state=CreateContestState.description)
async def skip_name_callback(query: types.CallbackQuery, state: FSMContext):
    # Генерация случайного имени для конкурса
    contest_description = "Описание отсутсвует 🚫"

    # Сохранение имени конкурса (например, в базе данных или переменной)
    await state.update_data(description=contest_description)

    # Обновление сообщения с новыми кнопками и текстом
    skip_winners_text = f"*🎖️ Введите количество победителей в конкурсе:*"

    keyboard = types.InlineKeyboardMarkup()
    skip_winners = types.InlineKeyboardButton(text=' Пропустить 🚩', callback_data='skip_winners')
    keyboard.add(skip_winners)

    # Получение идентификатора сообщения из списка contest_messages
    message_id = contest_messages[-1]

    await bot.edit_message_text(skip_winners_text, query.message.chat.id, message_id, parse_mode="Markdown", reply_markup=keyboard)

    # Установка состояния ожидания ввода описания конкурса
    await CreateContestState.winners.set()

@dp.message_handler(state=CreateContestState.winners)
async def process_description(message: types.Message, state: FSMContext):
    winners = message.text

    await bot.delete_message(message.chat.id, message.message_id)

    if not winners.isdigit():
        int_digit = await bot.send_message(message.chat.id, "*Нужно вводить только числовое значение! ❌*", parse_mode="Markdown")
        await asyncio.sleep(3)
        await bot.delete_message(chat_id=message.chat.id, message_id=int_digit.message_id)
        return

    winners = int(winners)
    if winners <= 0 or winners > 25:
        invalid_value = await bot.send_message(message.chat.id, "*Некорректное количество победителей. Пожалуйста, введите число от 1 до 25. ❌*", parse_mode="Markdown")
        await asyncio.sleep(3)
        await bot.delete_message(chat_id=message.chat.id, message_id=invalid_value.message_id)
        return

    if not winners:
        winners = 1

    await state.update_data(winners=winners)
    message_id = contest_messages[-1]

    date_text = f"*📆 Введите дату окончания конкурса (в формате ДД.ММ.ГГГГ):*"
    keyboard = types.InlineKeyboardMarkup()
    skip_date = types.InlineKeyboardButton(text=' Пропустить 🚩', callback_data='skip_date')
    keyboard.add(skip_date)

    await bot.edit_message_text(date_text, message.chat.id, message_id, parse_mode="Markdown", reply_markup=keyboard)

    await CreateContestState.end_date.set()

@dp.callback_query_handler(lambda query: query.data == 'skip_winners', state=CreateContestState.winners)
async def skip_name_callback(query: types.CallbackQuery, state: FSMContext):
    winners = 1

    await state.update_data(winners=winners)
    message_id = contest_messages[-1]

    date_text = f"*📆 Введите дату окончания конкурса (в формате ДД.ММ.ГГГГ):*"
    keyboard = types.InlineKeyboardMarkup()
    skip_date = types.InlineKeyboardButton(text=' Пропустить 🚩', callback_data='skip_date')
    keyboard.add(skip_date)

    await bot.edit_message_text(date_text, query.message.chat.id, message_id, parse_mode="Markdown", reply_markup=keyboard)

    await CreateContestState.end_date.set()

@dp.message_handler(state=CreateContestState.end_date)
async def process_description(message: types.Message, state: FSMContext):
    global contest_name, contest_id, contest_description, winners, end_date

    end_date_str = message.text

    await bot.delete_message(message.chat.id, message.message_id)
    message_id = contest_messages[-1]

    # Получаем текущую дату и время (offset-aware)
    today = datetime.now(timezone)

    try:
        # Преобразуем введенную дату и время в формате ДД.ММ.ГГГГ ЧАС:МИНУТЫ (offset-aware)
        end_date = datetime.strptime(end_date_str, "%d.%m.%Y %H:%M")
    except ValueError:
        try:
            # If the above parsing fails, try parsing the date without time
            end_date = datetime.strptime(end_date_str, "%d.%m.%Y")
            # Set the time to midnight (00:00)
            end_date = end_date.replace(hour=0, minute=0)
        except ValueError:
            # If both parsing attempts fail, it means the date format is incorrect
            wrong_date_format = await bot.send_message(message.chat.id, "*Неверный формат даты! Введите дату в формате* `ДД.ММ.ГГГГ.` *или* `ДД.ММ.ГГГГ. ЧАС:МИНУТЫ` ❌", parse_mode="Markdown")
            await asyncio.sleep(3)
            await bot.delete_message(chat_id=message.chat.id, message_id=wrong_date_format.message_id)
            return

    # Making end_date offset-aware using the same timezone
    end_date = timezone.localize(end_date)

    # Проверяем, что введенная дата и время больше текущей даты и времени
    if end_date <= today:
        old_date = await bot.send_message(message.chat.id, "*Дата и время должны быть больше текущей даты и времени.* 😶", parse_mode="Markdown")
        await asyncio.sleep(3)
        await bot.delete_message(chat_id=message.chat.id, message_id=old_date.message_id)
        return

    if not end_date_str:
        end_date_str = "Дата не указана. 🚫"
    else:
        # Преобразуем объект datetime в строку в формате ДД.ММ.ГГГГ ЧАС:МИНУТЫ
        end_date_str = end_date.strftime("%d.%m.%Y %H:%M")

    await state.update_data(end_date=end_date_str)

    data = await state.get_data()

    end_date = data.get('end_date')
    contest_name = data.get('contest_name')
    contest_id = data.get('contest_id')
    contest_description = data.get('description')
    winners = data.get('winners')

    confirmation_text = f"*💠 Данные зарегистрированы!*\n\n*🪁 Имя:* `{contest_name}`\n*🧊 Идентификатор:* `{contest_id}`\n*🎗️ Описание:* _{contest_description}_\n*🎖️ Количество победителей:* `{winners}`\n*📆 Дата окончания:* `{end_date}`"

    keyboard = types.InlineKeyboardMarkup()
    confirm_create = types.InlineKeyboardButton(text='Подтвердить ✅', callback_data='confirm_create')
    decline_create = types.InlineKeyboardButton(text='Отменить ❌', callback_data='decline_create')
    keyboard.add(decline_create, confirm_create)

    await bot.edit_message_text(confirmation_text, message.chat.id, message_id, parse_mode="Markdown", reply_markup=keyboard)

    # Сброс состояния ожидания ввода ключа
    await state.finish()

@dp.callback_query_handler(lambda query: query.data == 'skip_date', state=CreateContestState.end_date)
async def skip_date_callback(query: types.CallbackQuery, state: FSMContext):
    global contest_name, contest_id, contest_description, winners, end_date

    end_date = "Дата не указана. 🚫"

    await state.update_data(end_date=end_date)

    data = await state.get_data()
    message_id = contest_messages[-1]

    contest_name = data.get('contest_name')
    contest_id = data.get('contest_id')
    contest_description = data.get('description')
    winners = data.get('winners')
    end_date = data.get('end_date')

    confirmation_text = f"*💠 Данные зарегистрированы!*\n\n" \
                        f"*🪁 Имя:* `{contest_name}`\n" \
                        f"*🧊 Идентификатор:* `{contest_id}`\n" \
                        f"*🎗️ Описание:* _{contest_description}_\n" \
                        f"*🎖️ Количество победителей:* `{winners}`\n" \
                        f"*📆 Дата окончания:* `{end_date}`"

    keyboard = types.InlineKeyboardMarkup()
    confirm_create = types.InlineKeyboardButton(text='Подтвердить ✅', callback_data='confirm_create')
    decline_create = types.InlineKeyboardButton(text='Отменить ❌', callback_data='decline_create')

    keyboard.add(decline_create, confirm_create)

    await bot.edit_message_text(confirmation_text, query.message.chat.id, message_id, parse_mode="Markdown", reply_markup=keyboard)

    # Сброс состояния ожидания ввода ключа
    await state.finish()

@dp.callback_query_handler(lambda query: query.data == 'confirm_create', state='*')
async def confirm_create_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await button_click(callback_query, state)

# Ветка поиска конкурса
@dp.callback_query_handler(text='decline_search', state=MenuCategories.search)
async def decline_search_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    prev_message_id = (await state.get_data()).get('prev_message_id')
    if prev_message_id:
        await bot.delete_message(callback_query.message.chat.id, prev_message_id)
    await state.finish()

    global contest_messages

    message_id = contest_messages[-1]

    user_id = callback_query.from_user.id
    user_data = await user_collections.find_one({"_id": user_id})

    if user_data and (("status" in user_data and user_data["status"] in ["Тестер ✨", "Админ 🚗", "Создатель 🎭"]) or int(user_data.get("keys", 0)) > 0):

        # Код для существующего пользователя
        keyboard = types.InlineKeyboardMarkup()
        search = types.InlineKeyboardButton(text='🔎 Проверить', callback_data='search')
        create = types.InlineKeyboardButton(text='🎫 Создать', callback_data='create')
        change = types.InlineKeyboardButton(text='🍭 Редактировать', callback_data='change')
        keyboard.row(change, search)
        keyboard.row(create)

        confirmation_text = "*🍡 Рады вас видеть в панели управления конкурсами!*\n\n*✨ Воспользуйтесь кнопками для управления конкурсом или его создания:*"

        reply = await bot.edit_message_text(confirmation_text, callback_query.message.chat.id, message_id, parse_mode="Markdown",
                                    reply_markup=keyboard)

        # Сохранение ID сообщения в глобальную переменную
        contest_messages.append(reply.message_id)

    else:
        # Код для существующего пользователя
        keyboard = types.InlineKeyboardMarkup()
        input_key = types.InlineKeyboardButton(text='🔑 Ввести ключ', callback_data='input_key')
        keyboard.row(input_key)

        confirmation_text = "*👀 Воспользуйтесь кнопкой и введите уникальный ключ для доступа к созданию конкурсов:*"

        reply = await bot.edit_message_text(confirmation_text, callback_query.message.chat.id, message_id, parse_mode="Markdown",
                                    reply_markup=keyboard)

        # Сохранение ID сообщения в глобальную переменную
        contest_messages.append(reply.message_id)

@dp.message_handler(state=MenuCategories.search)
async def process_search(message: types.Message, state: FSMContext):
    await bot.delete_message(message.chat.id, message.message_id)

    if not message.text.isdigit():
        int_digit = await bot.send_message(message.chat.id, "*❌ Введите пожалуйста целочисленный идентификатор конкурса.*", parse_mode="Markdown")
        await asyncio.sleep(3)
        await bot.delete_message(chat_id=message.chat.id, message_id=int_digit.message_id)
        return

    global contest_messages

    search_id = int(message.text)

    # Поиск конкурса по айди
    contest = await contests_collection.find_one({"_id": search_id})

    # Отправьте результаты поиска
    result = await bot.send_message(message.chat.id, "*🕌 Результаты поиска конкурса...*", parse_mode="Markdown")
    await asyncio.sleep(2)
    await bot.delete_message(chat_id=message.chat.id, message_id=result.message_id)
    message_id = contest_messages[-1]

    if contest:
        contest_id = contest.get("_id")
        contest_name = contest.get("contest_name")
        owner_id = contest.get("owner_id")
        contest_description = contest.get("contest_description")
        members = contest.get("members")
        end_date = contest.get("end_date")
        members_message = len(members)
        winners = contest.get("winners", 0)
        contest_winners = contest.get("contest_winners")
        ended = contest.get("ended")
        if ended == "True":
            contest_status = "<b>❌ Статус:</b> Завершён."
        else:
            contest_status = "<b>✅ Статус:</b> Активен."

        if contest_winners:

            contest_winners_list = "\n".join(
                [f"<b>{idx}.</b> @{await get_username_winners(user)} — <code>{user}</code>" for idx, user in
                 enumerate(contest_winners, start=1)])
            result_message = f"<b>🔎 Результаты поиска конкурса </b> <code>{contest_id}</code><b>:</b>\n\n" \
                             f"<b>🍙 Автор:</b> <code>{owner_id}</code>\n" \
                             f"<b>🧊 Идентификатор:</b> <code>{contest_id}</code>\n" \
                             f"<b>🪁 Имя:</b> <code>{contest_name}</code>\n" \
                             f"<b>🎗️ Описание:</b> <i>{contest_description}</i>\n" \
                             f"<b>🎖️ Количество победителей:</b> <code>{winners}</code>\n" \
                             f"<b>👤 Количество участников:</b> <code>{members_message}</code>\n" \
                             f"<b>🏆 Победители:</b> \n{contest_winners_list}\n" \
                             f"<b>📆 Дата окончания:</b> <code>{end_date}</code>\n\n" \
                             f"{contest_status}"
        else:
            result_message = f"<b>🔎 Результаты поиска конкурса </b> <code>{contest_id}</code><b>:</b>\n\n" \
                             f"<b>🍙 Автор:</b> <code>{owner_id}</code>\n" \
                             f"<b>🧊 Идентификатор:</b> <code>{contest_id}</code>\n" \
                             f"<b>🪁 Имя:</b> <code>{contest_name}</code>\n" \
                             f"<b>🎗️ Описание:</b> <i>{contest_description}</i>\n" \
                             f"<b>🎖️ Количество победителей:</b> <code>{winners}</code>\n" \
                             f"<b>👤 Количество участников:</b> <code>{members_message}</code>\n" \
                             f"<b>📆 Дата окончания:</b> <code>{end_date}</code>\n\n" \
                             f"{contest_status}"

        keyboard = types.InlineKeyboardMarkup()
        input_id = types.InlineKeyboardButton(text='НАЗАД ❌', callback_data='decline_search')
        search = types.InlineKeyboardButton(text='Проверить 🔎', callback_data='search')
        keyboard.row(search)
        keyboard.row(input_id)

        reply = await bot.edit_message_text(result_message, message.chat.id, message_id, parse_mode="HTML", reply_markup=keyboard)
        await state.finish()

        # Сохранение ID сообщения в глобальную переменную
        contest_messages.append(reply.message_id)
    else:
        int_digit = await bot.send_message(message.chat.id, "*❌ Конкурс с указанным айди не найден.*", parse_mode="Markdown")
        await asyncio.sleep(4)
        await bot.delete_message(chat_id=message.chat.id, message_id=int_digit.message_id)

@dp.callback_query_handler(text='search')
async def search_callback(callback_query: types.CallbackQuery, state: FSMContext):
    search_text = "*🔎 Чтобы найти конкурс, введите его айди:*"
    keyboard = types.InlineKeyboardMarkup()
    input_id = types.InlineKeyboardButton(text='Отмена ❌', callback_data='decline_search')
    keyboard.row(input_id)

    await bot.edit_message_text(search_text, callback_query.message.chat.id, callback_query.message.message_id,
                                parse_mode="Markdown", reply_markup=keyboard)
    await MenuCategories.search.set()
    await state.update_data(prev_message_id=callback_query.message.message_id)

# Ветка поиска пользователя
@dp.callback_query_handler(text='decline_id_check', state=MenuCategories.id_check)
async def decline_search_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await state.finish()

    user_id = callback_query.from_user.id
    user_data = await user_collections.find_one({"_id": user_id})

    if user_data:
        username = callback_query.from_user.username
        wins = user_data.get("wins", 0)
        participation = user_data.get("participation", 0)
        creation_date = user_data.get("creation_date", "")
        status = user_data.get("status", "")

        # Создание и отправка сообщения с кнопками
        profile = f'*🍹 Профиль пользователя* `{username}`:\n\n*🍧 Статус:* `{status}`\n\n*🏅 Победы в конкурсах:* `{wins}`\n*🍀 Участие в конкурсах:* `{participation}`\n*📅 Дата регистрации:* `{creation_date}`'
        keyboard = types.InlineKeyboardMarkup()
        history = types.InlineKeyboardButton(text='История участий 📔', callback_data='history')
        id_check = types.InlineKeyboardButton(text='Поиск пользователя 🥏', callback_data='id_check')
        done = types.InlineKeyboardButton(text='Готово ✅', callback_data='done')
        keyboard.add(history, id_check)
        keyboard.add(done)

        reply = await bot.edit_message_text(profile, callback_query.message.chat.id,
                                            callback_query.message.message_id, parse_mode="Markdown",
                                            reply_markup=keyboard)
    else:
        # Обработка случая, когда данные о пользователе не найдены
        reply = await message.reply("☠️ Профиль пользователя не найден.")
    # Сохранение ID сообщения в глобальную переменную
    profile_messages.append(reply.message_id)

@dp.message_handler(state=MenuCategories.id_check)
async def process_search(message: types.Message, state: FSMContext):
    await bot.delete_message(message.chat.id, message.message_id)

    if not message.text.isdigit():
        int_digit = await bot.send_message(message.chat.id, "*❌ Введите пожалуйста целочисленный идентификатор пользователя.*", parse_mode="Markdown")
        await asyncio.sleep(3)
        await bot.delete_message(chat_id=message.chat.id, message_id=int_digit.message_id)
        return

    global profile_messages

    user_id = int(message.text)

    # Поиск конкурса по айди
    user = await user_collections.find_one({"_id": user_id})

    # Отправьте результаты поиска
    result = await bot.send_message(message.chat.id, "*🏯 Результаты поиска пользователя...*", parse_mode="Markdown")
    await asyncio.sleep(2)
    await bot.delete_message(chat_id=message.chat.id, message_id=result.message_id)
    message_id = profile_messages[-1]

    if user:
        wins = user.get("wins", 0)
        participation = user.get("participation", 0)
        creation_date = user.get("creation_date", "")
        status = user.get("status", "")

        # Создание и отправка сообщения с кнопками
        profile = f'*🍹 Профиль пользователя* `{user_id}`:\n\n*🍧 Статус:* `{status}`\n\n*🏅 Победы в конкурсах:* `{wins}`\n*🍀 Участие в конкурсах:* `{participation}`\n*📅 Дата регистрации:* `{creation_date}`'
        keyboard = types.InlineKeyboardMarkup()
        id_check = types.InlineKeyboardButton(text='Поиск пользователя 🥏', callback_data='id_check')
        done = types.InlineKeyboardButton(text='Готово ✅', callback_data='done')
        keyboard.add(id_check)
        keyboard.add(done)

        reply = await bot.edit_message_text(profile, message.chat.id, message_id, parse_mode="Markdown",
                                    reply_markup=keyboard)
        await state.finish()

        # Сохранение ID сообщения в глобальную переменную
        profile_messages.append(reply.message_id)
    else:
        int_digit = await bot.send_message(message.chat.id, "*❌ Пользователь с указанным айди не найден.*", parse_mode="Markdown")
        await asyncio.sleep(4)
        await bot.delete_message(chat_id=message.chat.id, message_id=int_digit.message_id)

@dp.callback_query_handler(text='id_check')
async def search_callback(callback_query: types.CallbackQuery, state: FSMContext):
    search_text = "*🔎 Чтобы найти пользователя, введите его айди:*"
    keyboard = types.InlineKeyboardMarkup()
    input_id = types.InlineKeyboardButton(text='Отмена ❌', callback_data='decline_id_check')
    keyboard.row(input_id)

    await bot.edit_message_text(search_text, callback_query.message.chat.id, callback_query.message.message_id,
                                parse_mode="Markdown", reply_markup=keyboard)
    await MenuCategories.id_check.set()
    await state.update_data(prev_message_id=callback_query.message.message_id)

## Ветка поиска профиля пользователя в конкурсе
@dp.callback_query_handler(text='decline_contest_profile_search', state=MenuCategories.contest_search_profile)
async def decline_search_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await state.finish()
    prev_message_id = (await state.get_data()).get('prev_message_id')
    if prev_message_id:
        await bot.delete_message(callback_query.message.chat.id, prev_message_id)

    global contest_messages

    user_id = callback_query.from_user.id

    # Поиск конкурса по айди
    contests = await contests_collection.find({"owner_id": user_id}).to_list(length=None)
    message_id = contest_messages[-1]
    if contests:
        # Создаем переменную для хранения сообщения с активными конкурсами
        result_message = "*🎯 Ваши активные конкурсы:*\n\n"

        # Итерация по каждому конкурсу
        for contest in contests:
            # Извлечение необходимых данных из найденного конкурса
            contest_id = contest.get("_id")
            contest_name = contest.get("contest_name")
            members = contest.get("members")
            ended = contest.get("ended")
            if ended == "True":
                pass
            else:
                if members:
                    members_count = len(members)
                else:
                    members_count = 0

                if members_count > 0:
                    members_message = f"{members_count}"
                else:
                    members_message = "0"

                # Формирование сообщения с данными конкурса
                result_message += f"*🪁 Имя:* `{contest_name}`\n" \
                                  f"*🧊 Айди конкурса* `{contest_id}`*:*\n" \
                                  f"*🏯 Количество участников:* `{members_message}`" \
                                  f"*·*\n"

        keyboard = types.InlineKeyboardMarkup()
        decline_create = types.InlineKeyboardButton(text='Назад 🧿', callback_data='decline_create')
        contest_check = types.InlineKeyboardButton(text='Управление 🧧', callback_data='contest_check')
        keyboard.row(contest_check)
        keyboard.row(decline_create)

        reply = await bot.edit_message_text(result_message, callback_query.message.chat.id, message_id,
                                            parse_mode="Markdown",
                                            reply_markup=keyboard)

        # Сохранение ID сообщения в глобальную переменную
        change_message_id.append(reply.message_id)
    else:
        keyboard = types.InlineKeyboardMarkup()
        decline_create = types.InlineKeyboardButton(text='Назад 🧿', callback_data='decline_create')
        keyboard.row(decline_create)

        int_digit = await bot.edit_message_text("*У вас не обнаружено активных конкурсов‼️*",
                                                callback_query.message.chat.id, message_id,
                                                parse_mode="Markdown",
                                                reply_markup=keyboard)
        change_message_id.append(int_digit.message_id)

@dp.message_handler(state=MenuCategories.contest_search_profile)
async def process_search(message: types.Message, state: FSMContext):
    await bot.delete_message(message.chat.id, message.message_id)

    if not message.text.isdigit():
        int_digit = await bot.send_message(message.chat.id, "*❌ Введите пожалуйста целочисленный идентификатор.*", parse_mode="Markdown")
        await asyncio.sleep(3)
        await bot.delete_message(chat_id=message.chat.id, message_id=int_digit.message_id)
        return

    global change_message_id
    contest_id = (await state.get_data()).get('contest_id')

    search_user_id = int(message.text)

    # Поиск конкурса по айди
    contest = await contests_collection.find_one({"_id": int(contest_id)})

    if contest:
        members = contest.get("members")
        ban_members = contest.get("ban_members")
        join_date = contest.get("join_date")

        if int(search_user_id) in members:
            user_index = members.index(search_user_id)
            blocked = "Заблокирован!" if search_user_id in ban_members else "Душевное!"

            # Отправьте результаты поиска
            result = await bot.send_message(message.chat.id, "*🕌 Результаты поиска...*", parse_mode="Markdown")
            await asyncio.sleep(2)
            await bot.delete_message(chat_id=message.chat.id, message_id=result.message_id)
            message_id = change_message_id[-1]

            username = await get_username(search_user_id)
            if username:
                username = username.replace("_", "&#95;")
            if search_user_id in ban_members:
                # Формирование сообщения с данными пользователя
                result_message = f"<b>🧶Пользователь:</b> <code>{search_user_id}</code>\n" \
                                 f"<b>🪐 Юзернейм:</b> @{username}\n" \
                                 f"<b>‼️ Состояние:</b> <code>{blocked}</code>"
                block = types.InlineKeyboardButton(text='Разблокировать ❎',
                                                   callback_data=f'unblock_profile_{search_user_id}_{contest_id}')
            else:
                # Формирование сообщения с данными пользователя
                result_message = f"<b>🧶Пользователь:</b> <code>{search_user_id}</code>\n" \
                                 f"<b>🪐 Юзернейм:</b> @{username}\n" \
                                 f"<b>📅 Дата присоединения:</b> <code>{join_date[user_index]}</code>\n\n" \
                                 f"<b>❎ Состояние:</b> <code>{blocked}</code>"
                block = types.InlineKeyboardButton(text='Заблокировать 🚫',
                                                   callback_data=f'block_profile_{search_user_id}_{contest_id}')

            keyboard = types.InlineKeyboardMarkup()
            kick = types.InlineKeyboardButton(text='Исключить 🎇',
                                               callback_data=f'kick_profile_{search_user_id}_{contest_id}')
            back_search = types.InlineKeyboardButton(text='Назад 🧿', callback_data='contest_check')
            input_id = types.InlineKeyboardButton(text='Искать ещё 🔎', callback_data=f'contest_search_profile_{contest_id}')
            keyboard.row(input_id)
            keyboard.row(kick, block)
            keyboard.row(back_search)
            reply = await bot.edit_message_text(result_message, message.chat.id, message_id, parse_mode="HTML",
                                                reply_markup=keyboard)
            await state.finish()

            # Сохранение ID сообщения в глобальную переменную
            change_message_id.append(reply.message_id)
        elif int(search_user_id) in ban_members:
            message_id = change_message_id[-1]

            username = await get_username(search_user_id)
            if username:
                username = username.replace("_", "&#95;")

            # Формирование сообщения с данными пользователя
            result_message = f"<b>🧶Пользователь:</b> <code>{search_user_id}</code>\n" \
                             f"<b>🪐 Юзернейм:</b> @{username}\n" \
                             f"<b>‼️ Заблокирован:</b> <code>Да 🔨</code>"
            unblock = types.InlineKeyboardButton(text='Разблокировать ❎',
                                                 callback_data=f'unblock_profile_{search_user_id}_{contest_id}')

            keyboard = types.InlineKeyboardMarkup()
            back_search = types.InlineKeyboardButton(text='Назад 🧿', callback_data='contest_check')
            input_id = types.InlineKeyboardButton(text='Искать ещё 🔎',
                                                  callback_data=f'contest_search_profile_{contest_id}')
            keyboard.row(input_id)
            keyboard.row(unblock)
            keyboard.row(back_search)
            await state.finish()

            reply = await bot.edit_message_text(result_message, message.chat.id, message_id, parse_mode="HTML",
                                                reply_markup=keyboard)
            # Сохранение ID сообщения в глобальную переменную
            change_message_id.append(reply.message_id)
        else:
            int_digit = await bot.send_message(message.chat.id, "*❌ Пользователь не обнаружен.*", parse_mode="Markdown")
            await asyncio.sleep(4)
            await bot.delete_message(chat_id=message.chat.id, message_id=int_digit.message_id)
    else:
        int_digit = await bot.send_message(message.chat.id, "*❌ Конкурс не найден.*", parse_mode="Markdown")
        await asyncio.sleep(4)
        await bot.delete_message(chat_id=message.chat.id, message_id=int_digit.message_id)

@dp.callback_query_handler(lambda c: c.data.startswith('contest_search_profile'))
async def search_callback(callback_query: types.CallbackQuery, state: FSMContext):

    button_text = callback_query.data
    contest_id = button_text.split('_')[3]

    search_text = "*🧶 Введите айди пользователя:*"
    keyboard = types.InlineKeyboardMarkup()
    input_id = types.InlineKeyboardButton(text='Отмена ❌', callback_data='decline_contest_profile_search')
    keyboard.row(input_id)

    await bot.edit_message_text(search_text, callback_query.message.chat.id, callback_query.message.message_id,
                                parse_mode="Markdown", reply_markup=keyboard)
    await MenuCategories.contest_search_profile.set()
    await state.update_data(contest_id=contest_id)
    await state.update_data(prev_message_id=callback_query.message.message_id)

## Ветка ввода изменений в конкурсе
# Изменение имени
@dp.callback_query_handler(text='decline_name_change', state=ChangeContestState.name_change)
async def decline_search_callback(callback_query: types.CallbackQuery, state: FSMContext):
    contest_id = (await state.get_data()).get('contest_id')

    await callback_query.answer()
    await state.finish()
    prev_message_id = (await state.get_data()).get('prev_message_id')
    if prev_message_id:
        await bot.delete_message(callback_query.message.chat.id, prev_message_id)

    global contest_messages

    # Поиск конкурса по айди
    contest = await contests_collection.find_one({"_id": int(contest_id)})

    if contest:
        message_id = change_message_id[-1]

        # Извлечение необходимых данных из найденного конкурса
        contest_id = contest.get("_id")
        contest_name = contest.get("contest_name")
        contest_description = contest.get("contest_description")
        winners = contest.get("winners")
        members = contest.get("members")
        end_date = contest.get("end_date")

        if members:
            members_count = len(members)
        else:
            members_count = 0

        if members_count > 0:
            members_message = f"{members_count}"
        else:
            members_message = "0"

        result_message = f"*🏆 Редакция конкурса* `{contest_id}`*:*\n\n" \
                         f"*🪁 Имя:* `{contest_name}`\n" \
                         f"*🧊 Идентификатор:* `{contest_id}`\n" \
                         f"*🎗️ Описание:* _{contest_description}_\n" \
                         f"*🎖️ Количество победителей:* `{winners}`\n" \
                         f"*🏯 Количество участников:* `{members_message}`\n" \
                         f"*📆 Дата окончания:* `{end_date}`"

        keyboard = types.InlineKeyboardMarkup()
        name_change = types.InlineKeyboardButton(text='Имя  ️🪁', callback_data=f'name_change_{contest_id}')
        description_change = types.InlineKeyboardButton(text='Описание 🎗️️',
                                                        callback_data=f'description_change_{contest_id}')
        winners_change = types.InlineKeyboardButton(text='Победители 🎖️', callback_data=f'winners_change_{contest_id}')
        date_change = types.InlineKeyboardButton(text='Дата  ️📆', callback_data=f'date_change_{contest_id}')
        back = types.InlineKeyboardButton(text='Назад 🧿', callback_data=f'change')
        keyboard.row(name_change)
        keyboard.row(description_change)
        keyboard.row(winners_change)
        keyboard.row(date_change)
        keyboard.row(back)

        reply = await bot.edit_message_text(result_message, callback_query.message.chat.id, message_id,
                                            parse_mode="Markdown",
                                            reply_markup=keyboard)

        # Сохранение ID сообщения в глобальную переменную
        change_message_id.append(reply.message_id)
    else:
        int_digit = await bot.edit_message_text("*У вас не обнаружено активных конкурсов‼️*",
                                                callback_query.message.chat.id, message_id,
                                                parse_mode="Markdown",
                                                reply_markup=keyboard)
        change_message_id.append(int_digit.message_id)

@dp.message_handler(state=ChangeContestState.name_change)
async def process_search(message: types.Message, state: FSMContext):
    await bot.delete_message(message.chat.id, message.message_id)

    global change_message_id
    contest_id = (await state.get_data()).get('contest_id')

    new_name = message.text
    await contests_collection.update_one({"_id": int(contest_id)},
                                      {"$set": {"contest_name": new_name}})
    # Поиск конкурса по айди
    contest = await contests_collection.find_one({"_id": int(contest_id)})

    if contest:
        message_id = change_message_id[-1]

        # Извлечение необходимых данных из найденного конкурса
        contest_id = contest.get("_id")
        contest_name = contest.get("contest_name")
        contest_description = contest.get("contest_description")
        winners = contest.get("winners")
        members = contest.get("members")
        end_date = contest.get("end_date")

        if members:
            members_count = len(members)
        else:
            members_count = 0

        if members_count > 0:
            members_message = f"{members_count}"
        else:
            members_message = "0"

        result_message = f"*🏆 Редакция конкурса* `{contest_id}`*:*\n\n" \
                         f"*🪁 Имя:* `{contest_name}`\n" \
                         f"*🧊 Идентификатор:* `{contest_id}`\n" \
                         f"*🎗️ Описание:* _{contest_description}_\n" \
                         f"*🎖️ Количество победителей:* `{winners}`\n" \
                         f"*🏯 Количество участников:* `{members_message}`\n" \
                         f"*📆 Дата окончания:* `{end_date}`"

        keyboard = types.InlineKeyboardMarkup()
        name_change = types.InlineKeyboardButton(text='Имя  ️🪁', callback_data=f'name_change_{contest_id}')
        description_change = types.InlineKeyboardButton(text='Описание 🎗️️',
                                                        callback_data=f'description_change_{contest_id}')
        winners_change = types.InlineKeyboardButton(text='Победители 🎖️', callback_data=f'winners_change_{contest_id}')
        date_change = types.InlineKeyboardButton(text='Дата  ️📆', callback_data=f'date_change_{contest_id}')
        back = types.InlineKeyboardButton(text='Назад 🧿', callback_data=f'change')
        keyboard.row(name_change)
        keyboard.row(description_change)
        keyboard.row(winners_change)
        keyboard.row(date_change)
        keyboard.row(back)

        reply = await bot.edit_message_text(result_message, message.chat.id, message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)
        await state.finish()
    else:
        int_digit = await bot.send_message(message.chat.id, "*❌ Конкурс не найден.*", parse_mode="Markdown")
        await asyncio.sleep(4)
        await bot.delete_message(chat_id=message.chat.id, message_id=int_digit.message_id)

@dp.callback_query_handler(lambda c: c.data.startswith('name_change'))
async def search_callback(callback_query: types.CallbackQuery, state: FSMContext):

    button_text = callback_query.data
    contest_id = button_text.split('_')[2]

    search_text = "*🪁 Введите новое имя конкурса:*"
    keyboard = types.InlineKeyboardMarkup()
    input_id = types.InlineKeyboardButton(text='Отмена ❌', callback_data='decline_name_change')
    keyboard.row(input_id)

    await bot.edit_message_text(search_text, callback_query.message.chat.id, callback_query.message.message_id,
                                parse_mode="Markdown", reply_markup=keyboard)
    await ChangeContestState.name_change.set()
    await state.update_data(contest_id=contest_id)
    await state.update_data(prev_message_id=callback_query.message.message_id)

# Изменение описания
@dp.callback_query_handler(text='decline_description_change', state=ChangeContestState.description_change)
async def decline_search_callback(callback_query: types.CallbackQuery, state: FSMContext):
    contest_id = (await state.get_data()).get('contest_id')

    await callback_query.answer()
    await state.finish()
    prev_message_id = (await state.get_data()).get('prev_message_id')
    if prev_message_id:
        await bot.delete_message(callback_query.message.chat.id, prev_message_id)

    global contest_messages

    # Поиск конкурса по айди
    contest = await contests_collection.find_one({"_id": int(contest_id)})

    if contest:
        message_id = change_message_id[-1]

        # Извлечение необходимых данных из найденного конкурса
        contest_id = contest.get("_id")
        contest_name = contest.get("contest_name")
        contest_description = contest.get("contest_description")
        winners = contest.get("winners")
        members = contest.get("members")
        end_date = contest.get("end_date")

        if members:
            members_count = len(members)
        else:
            members_count = 0

        if members_count > 0:
            members_message = f"{members_count}"
        else:
            members_message = "0"

        result_message = f"*🏆 Редакция конкурса* `{contest_id}`*:*\n\n" \
                         f"*🪁 Имя:* `{contest_name}`\n" \
                         f"*🧊 Идентификатор:* `{contest_id}`\n" \
                         f"*🎗️ Описание:* _{contest_description}_\n" \
                         f"*🎖️ Количество победителей:* `{winners}`\n" \
                         f"*🏯 Количество участников:* `{members_message}`\n" \
                         f"*📆 Дата окончания:* `{end_date}`"

        keyboard = types.InlineKeyboardMarkup()
        name_change = types.InlineKeyboardButton(text='Имя  ️🪁', callback_data=f'name_change_{contest_id}')
        description_change = types.InlineKeyboardButton(text='Описание 🎗️️',
                                                        callback_data=f'description_change_{contest_id}')
        winners_change = types.InlineKeyboardButton(text='Победители 🎖️', callback_data=f'winners_change_{contest_id}')
        date_change = types.InlineKeyboardButton(text='Дата  ️📆', callback_data=f'date_change_{contest_id}')
        back = types.InlineKeyboardButton(text='Назад 🧿', callback_data=f'change')
        keyboard.row(name_change)
        keyboard.row(description_change)
        keyboard.row(winners_change)
        keyboard.row(date_change)
        keyboard.row(back)

        reply = await bot.edit_message_text(result_message, callback_query.message.chat.id, message_id,
                                            parse_mode="Markdown",
                                            reply_markup=keyboard)

        # Сохранение ID сообщения в глобальную переменную
        change_message_id.append(reply.message_id)
    else:
        int_digit = await bot.edit_message_text("*У вас не обнаружено активных конкурсов‼️*",
                                                callback_query.message.chat.id, message_id,
                                                parse_mode="Markdown",
                                                reply_markup=keyboard)
        change_message_id.append(int_digit.message_id)

@dp.message_handler(state=ChangeContestState.description_change)
async def process_search(message: types.Message, state: FSMContext):
    await bot.delete_message(message.chat.id, message.message_id)

    global change_message_id
    contest_id = (await state.get_data()).get('contest_id')

    new_description = message.text
    await contests_collection.update_one({"_id": int(contest_id)},
                                      {"$set": {"contest_description": new_description}})
    # Поиск конкурса по айди
    contest = await contests_collection.find_one({"_id": int(contest_id)})

    if contest:
        message_id = change_message_id[-1]

        # Извлечение необходимых данных из найденного конкурса
        contest_id = contest.get("_id")
        contest_name = contest.get("contest_name")
        contest_description = contest.get("contest_description")
        winners = contest.get("winners")
        members = contest.get("members")
        end_date = contest.get("end_date")

        if members:
            members_count = len(members)
        else:
            members_count = 0

        if members_count > 0:
            members_message = f"{members_count}"
        else:
            members_message = "0"

        result_message = f"*🏆 Редакция конкурса* `{contest_id}`*:*\n\n" \
                         f"*🪁 Имя:* `{contest_name}`\n" \
                         f"*🧊 Идентификатор:* `{contest_id}`\n" \
                         f"*🎗️ Описание:* _{contest_description}_\n" \
                         f"*🎖️ Количество победителей:* `{winners}`\n" \
                         f"*🏯 Количество участников:* `{members_message}`\n" \
                         f"*📆 Дата окончания:* `{end_date}`"

        keyboard = types.InlineKeyboardMarkup()
        name_change = types.InlineKeyboardButton(text='Имя  ️🪁', callback_data=f'name_change_{contest_id}')
        description_change = types.InlineKeyboardButton(text='Описание 🎗️️',
                                                        callback_data=f'description_change_{contest_id}')
        winners_change = types.InlineKeyboardButton(text='Победители 🎖️', callback_data=f'winners_change_{contest_id}')
        date_change = types.InlineKeyboardButton(text='Дата  ️📆', callback_data=f'date_change_{contest_id}')
        back = types.InlineKeyboardButton(text='Назад 🧿', callback_data=f'change')
        keyboard.row(name_change)
        keyboard.row(description_change)
        keyboard.row(winners_change)
        keyboard.row(date_change)
        keyboard.row(back)

        reply = await bot.edit_message_text(result_message, message.chat.id, message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)
        await state.finish()
    else:
        int_digit = await bot.send_message(message.chat.id, "*❌ Конкурс не найден.*", parse_mode="Markdown")
        await asyncio.sleep(4)
        await bot.delete_message(chat_id=message.chat.id, message_id=int_digit.message_id)

@dp.callback_query_handler(lambda c: c.data.startswith('description_change'))
async def search_callback(callback_query: types.CallbackQuery, state: FSMContext):

    button_text = callback_query.data
    contest_id = button_text.split('_')[2]

    search_text = "*🎗️ Введите описание конкурса:*"
    keyboard = types.InlineKeyboardMarkup()
    input_id = types.InlineKeyboardButton(text='Отмена ❌', callback_data='decline_description_change')
    keyboard.row(input_id)

    await bot.edit_message_text(search_text, callback_query.message.chat.id, callback_query.message.message_id,
                                parse_mode="Markdown", reply_markup=keyboard)
    await ChangeContestState.description_change.set()
    await state.update_data(contest_id=contest_id)
    await state.update_data(prev_message_id=callback_query.message.message_id)

# Изменение количества победителей
@dp.callback_query_handler(text='decline_winners_change', state=ChangeContestState.winners_change)
async def decline_search_callback(callback_query: types.CallbackQuery, state: FSMContext):
    contest_id = (await state.get_data()).get('contest_id')

    await callback_query.answer()
    await state.finish()
    prev_message_id = (await state.get_data()).get('prev_message_id')
    if prev_message_id:
        await bot.delete_message(callback_query.message.chat.id, prev_message_id)

    global contest_messages

    # Поиск конкурса по айди
    contest = await contests_collection.find_one({"_id": int(contest_id)})

    if contest:
        message_id = change_message_id[-1]

        # Извлечение необходимых данных из найденного конкурса
        contest_id = contest.get("_id")
        contest_name = contest.get("contest_name")
        contest_description = contest.get("contest_description")
        winners = contest.get("winners")
        members = contest.get("members")
        end_date = contest.get("end_date")

        if members:
            members_count = len(members)
        else:
            members_count = 0

        if members_count > 0:
            members_message = f"{members_count}"
        else:
            members_message = "0"

        result_message = f"*🏆 Редакция конкурса* `{contest_id}`*:*\n\n" \
                         f"*🪁 Имя:* `{contest_name}`\n" \
                         f"*🧊 Идентификатор:* `{contest_id}`\n" \
                         f"*🎗️ Описание:* _{contest_description}_\n" \
                         f"*🎖️ Количество победителей:* `{winners}`\n" \
                         f"*🏯 Количество участников:* `{members_message}`\n" \
                         f"*📆 Дата окончания:* `{end_date}`"

        keyboard = types.InlineKeyboardMarkup()
        name_change = types.InlineKeyboardButton(text='Имя  ️🪁', callback_data=f'name_change_{contest_id}')
        description_change = types.InlineKeyboardButton(text='Описание 🎗️️',
                                                        callback_data=f'description_change_{contest_id}')
        winners_change = types.InlineKeyboardButton(text='Победители 🎖️', callback_data=f'winners_change_{contest_id}')
        date_change = types.InlineKeyboardButton(text='Дата  ️📆', callback_data=f'date_change_{contest_id}')
        back = types.InlineKeyboardButton(text='Назад 🧿', callback_data=f'change')
        keyboard.row(name_change)
        keyboard.row(description_change)
        keyboard.row(winners_change)
        keyboard.row(date_change)
        keyboard.row(back)

        reply = await bot.edit_message_text(result_message, callback_query.message.chat.id, message_id,
                                            parse_mode="Markdown",
                                            reply_markup=keyboard)

        # Сохранение ID сообщения в глобальную переменную
        change_message_id.append(reply.message_id)
    else:
        int_digit = await bot.edit_message_text("*У вас не обнаружено активных конкурсов‼️*",
                                                callback_query.message.chat.id, message_id,
                                                parse_mode="Markdown",
                                                reply_markup=keyboard)
        change_message_id.append(int_digit.message_id)

@dp.message_handler(state=ChangeContestState.winners_change)
async def process_search(message: types.Message, state: FSMContext):
    await bot.delete_message(message.chat.id, message.message_id)

    global change_message_id
    contest_id = (await state.get_data()).get('contest_id')

    new_winners = message.text
    if not new_winners.isdigit():
        int_digit = await bot.send_message(message.chat.id, "*Нужно вводить только числовое значение! ❌*", parse_mode="Markdown")
        await asyncio.sleep(3)
        await bot.delete_message(chat_id=message.chat.id, message_id=int_digit.message_id)
        return

    winners = int(new_winners)
    if winners <= 0 or winners > 25:
        invalid_value = await bot.send_message(message.chat.id, "*Некорректное количество победителей. Пожалуйста, введите число от 1 до 25. ❌*", parse_mode="Markdown")
        await asyncio.sleep(3)
        await bot.delete_message(chat_id=message.chat.id, message_id=invalid_value.message_id)
        return

    await contests_collection.update_one({"_id": int(contest_id)},
                                      {"$set": {"winners": int(new_winners)}})
    # Поиск конкурса по айди
    contest = await contests_collection.find_one({"_id": int(contest_id)})

    if contest:
        message_id = change_message_id[-1]

        # Извлечение необходимых данных из найденного конкурса
        contest_id = contest.get("_id")
        contest_name = contest.get("contest_name")
        contest_description = contest.get("contest_description")
        winners = contest.get("winners")
        members = contest.get("members")
        end_date = contest.get("end_date")

        if members:
            members_count = len(members)
        else:
            members_count = 0

        if members_count > 0:
            members_message = f"{members_count}"
        else:
            members_message = "0"

        result_message = f"*🏆 Редакция конкурса* `{contest_id}`*:*\n\n" \
                         f"*🪁 Имя:* `{contest_name}`\n" \
                         f"*🧊 Идентификатор:* `{contest_id}`\n" \
                         f"*🎗️ Описание:* _{contest_description}_\n" \
                         f"*🎖️ Количество победителей:* `{winners}`\n" \
                         f"*🏯 Количество участников:* `{members_message}`\n" \
                         f"*📆 Дата окончания:* `{end_date}`"

        keyboard = types.InlineKeyboardMarkup()
        name_change = types.InlineKeyboardButton(text='Имя  ️🪁', callback_data=f'name_change_{contest_id}')
        description_change = types.InlineKeyboardButton(text='Описание 🎗️️',
                                                        callback_data=f'description_change_{contest_id}')
        winners_change = types.InlineKeyboardButton(text='Победители 🎖️', callback_data=f'winners_change_{contest_id}')
        date_change = types.InlineKeyboardButton(text='Дата  ️📆', callback_data=f'date_change_{contest_id}')
        back = types.InlineKeyboardButton(text='Назад 🧿', callback_data=f'change')
        keyboard.row(name_change)
        keyboard.row(description_change)
        keyboard.row(winners_change)
        keyboard.row(date_change)
        keyboard.row(back)

        reply = await bot.edit_message_text(result_message, message.chat.id, message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)
        await state.finish()
    else:
        int_digit = await bot.send_message(message.chat.id, "*❌ Конкурс не найден.*", parse_mode="Markdown")
        await asyncio.sleep(4)
        await bot.delete_message(chat_id=message.chat.id, message_id=int_digit.message_id)

@dp.callback_query_handler(lambda c: c.data.startswith('winners_change'))
async def search_callback(callback_query: types.CallbackQuery, state: FSMContext):

    button_text = callback_query.data
    contest_id = button_text.split('_')[2]

    search_text = "*🥇 Введите количество победетелей:*"
    keyboard = types.InlineKeyboardMarkup()
    input_id = types.InlineKeyboardButton(text='Отмена ❌', callback_data='decline_winners_change')
    keyboard.row(input_id)

    await bot.edit_message_text(search_text, callback_query.message.chat.id, callback_query.message.message_id,
                                parse_mode="Markdown", reply_markup=keyboard)
    await ChangeContestState.winners_change.set()
    await state.update_data(contest_id=contest_id)
    await state.update_data(prev_message_id=callback_query.message.message_id)

# Изменение даты
@dp.callback_query_handler(text='decline_date_change', state=ChangeContestState.date_change)
async def decline_search_callback(callback_query: types.CallbackQuery, state: FSMContext):
    contest_id = (await state.get_data()).get('contest_id')

    await callback_query.answer()
    await state.finish()
    prev_message_id = (await state.get_data()).get('prev_message_id')
    if prev_message_id:
        await bot.delete_message(callback_query.message.chat.id, prev_message_id)

    global contest_messages

    # Поиск конкурса по айди
    contest = await contests_collection.find_one({"_id": int(contest_id)})

    if contest:
        message_id = change_message_id[-1]

        # Извлечение необходимых данных из найденного конкурса
        contest_id = contest.get("_id")
        contest_name = contest.get("contest_name")
        contest_description = contest.get("contest_description")
        winners = contest.get("winners")
        members = contest.get("members")
        end_date = contest.get("end_date")

        if members:
            members_count = len(members)
        else:
            members_count = 0

        if members_count > 0:
            members_message = f"{members_count}"
        else:
            members_message = "0"

        result_message = f"*🏆 Редакция конкурса* `{contest_id}`*:*\n\n" \
                         f"*🪁 Имя:* `{contest_name}`\n" \
                         f"*🧊 Идентификатор:* `{contest_id}`\n" \
                         f"*🎗️ Описание:* _{contest_description}_\n" \
                         f"*🎖️ Количество победителей:* `{winners}`\n" \
                         f"*🏯 Количество участников:* `{members_message}`\n" \
                         f"*📆 Дата окончания:* `{end_date}`"

        keyboard = types.InlineKeyboardMarkup()
        name_change = types.InlineKeyboardButton(text='Имя  ️🪁', callback_data=f'name_change_{contest_id}')
        description_change = types.InlineKeyboardButton(text='Описание 🎗️️',
                                                        callback_data=f'description_change_{contest_id}')
        winners_change = types.InlineKeyboardButton(text='Победители 🎖️', callback_data=f'winners_change_{contest_id}')
        date_change = types.InlineKeyboardButton(text='Дата  ️📆', callback_data=f'date_change_{contest_id}')
        back = types.InlineKeyboardButton(text='Назад 🧿', callback_data=f'change')
        keyboard.row(name_change)
        keyboard.row(description_change)
        keyboard.row(winners_change)
        keyboard.row(date_change)
        keyboard.row(back)

        reply = await bot.edit_message_text(result_message, callback_query.message.chat.id, message_id,
                                            parse_mode="Markdown",
                                            reply_markup=keyboard)

        # Сохранение ID сообщения в глобальную переменную
        change_message_id.append(reply.message_id)
    else:
        int_digit = await bot.edit_message_text("*У вас не обнаружено активных конкурсов‼️*",
                                                callback_query.message.chat.id, message_id,
                                                parse_mode="Markdown",
                                                reply_markup=keyboard)
        change_message_id.append(int_digit.message_id)

@dp.message_handler(state=ChangeContestState.date_change)
async def process_search(message: types.Message, state: FSMContext):
    await bot.delete_message(message.chat.id, message.message_id)

    global change_message_id
    contest_id = (await state.get_data()).get('contest_id')

    new_date_str = message.text

    # Получаем текущую дату и время
    today = datetime.now(timezone)

    try:
        # Преобразуем введенную дату и время в формате ДД.ММ.ГГГГ ЧАС:МИНУТЫ (offset-aware)
        new_date = datetime.strptime(new_date_str, "%d.%m.%Y %H:%M")
    except ValueError:
        try:
            # If the above parsing fails, try parsing the date without time
            new_date = datetime.strptime(new_date_str, "%d.%m.%Y")
            # Set the time to midnight (00:00)
            new_date = new_date.replace(hour=0, minute=0)
        except ValueError:
            # If both parsing attempts fail, it means the date format is incorrect
            wrong_date_format = await bot.send_message(message.chat.id, "*Неверный формат даты! Введите дату в формате* `ДД.ММ.ГГГГ.` *или* `ДД.ММ.ГГГГ. ЧАС:МИНУТЫ` ❌", parse_mode="Markdown")
            await asyncio.sleep(3)
            await bot.delete_message(chat_id=message.chat.id, message_id=wrong_date_format.message_id)
            return

    # Making end_date offset-aware using the same timezone
    new_date = timezone.localize(new_date)

    # Проверяем, что введенная дата и время больше текущей даты и времени
    if new_date <= today:
        old_date = await bot.send_message(message.chat.id, "*Дата и время должны быть больше текущей даты и времени.* 😶", parse_mode="Markdown")
        await asyncio.sleep(3)
        await bot.delete_message(chat_id=message.chat.id, message_id=old_date.message_id)
        return

    if not new_date_str:
        new_date_str = "Дата не указана. 🚫"
    else:
        # Преобразуем объект datetime в строку в формате ДД.ММ.ГГГГ ЧАС:МИНУТЫ
        new_date_str = new_date.strftime("%d.%m.%Y %H:%M")

    await contests_collection.update_one({"_id": int(contest_id)},
                                      {"$set": {"end_date": new_date_str}})
    # Поиск конкурса по айди
    contest = await contests_collection.find_one({"_id": int(contest_id)})

    if contest:
        message_id = change_message_id[-1]

        # Извлечение необходимых данных из найденного конкурса
        contest_id = contest.get("_id")
        contest_name = contest.get("contest_name")
        contest_description = contest.get("contest_description")
        winners = contest.get("winners")
        members = contest.get("members")
        end_date = contest.get("end_date")

        if members:
            members_count = len(members)
        else:
            members_count = 0

        if members_count > 0:
            members_message = f"{members_count}"
        else:
            members_message = "0"

        result_message = f"*🏆 Редакция конкурса* `{contest_id}`*:*\n\n" \
                         f"*🪁 Имя:* `{contest_name}`\n" \
                         f"*🧊 Идентификатор:* `{contest_id}`\n" \
                         f"*🎗️ Описание:* _{contest_description}_\n" \
                         f"*🎖️ Количество победителей:* `{winners}`\n" \
                         f"*🏯 Количество участников:* `{members_message}`\n" \
                         f"*📆 Дата окончания:* `{end_date}`"

        keyboard = types.InlineKeyboardMarkup()
        name_change = types.InlineKeyboardButton(text='Имя  ️🪁', callback_data=f'name_change_{contest_id}')
        description_change = types.InlineKeyboardButton(text='Описание 🎗️️',
                                                        callback_data=f'description_change_{contest_id}')
        winners_change = types.InlineKeyboardButton(text='Победители 🎖️', callback_data=f'winners_change_{contest_id}')
        date_change = types.InlineKeyboardButton(text='Дата  ️📆', callback_data=f'date_change_{contest_id}')
        back = types.InlineKeyboardButton(text='Назад 🧿', callback_data=f'change')
        keyboard.row(name_change)
        keyboard.row(description_change)
        keyboard.row(winners_change)
        keyboard.row(date_change)
        keyboard.row(back)

        reply = await bot.edit_message_text(result_message, message.chat.id, message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)
        await state.finish()
    else:
        int_digit = await bot.send_message(message.chat.id, "*❌ Конкурс не найден.*", parse_mode="Markdown")
        await asyncio.sleep(4)
        await bot.delete_message(chat_id=message.chat.id, message_id=int_digit.message_id)

@dp.callback_query_handler(lambda c: c.data.startswith('date_change'))
async def search_callback(callback_query: types.CallbackQuery, state: FSMContext):

    button_text = callback_query.data
    contest_id = button_text.split('_')[2]

    search_text = "*📅 Введите новую дату:*"
    keyboard = types.InlineKeyboardMarkup()
    input_id = types.InlineKeyboardButton(text='Отмена ❌', callback_data='decline_date_change')
    keyboard.row(input_id)

    await bot.edit_message_text(search_text, callback_query.message.chat.id, callback_query.message.message_id,
                                parse_mode="Markdown", reply_markup=keyboard)
    await ChangeContestState.date_change.set()
    await state.update_data(contest_id=contest_id)
    await state.update_data(prev_message_id=callback_query.message.message_id)

# Поиск через команду
@dp.message_handler(commands=['search'])
async def process_search_command(message: types.Message, state: FSMContext):
    args = message.get_args()

    if message.reply_to_message:
        replied_user = message.reply_to_message.from_user
        user_id = replied_user.id
    elif args:
        user_id = args
    else:
        await bot.send_message(message.chat.id, "*❌ Необходимо указать айди пользователя или ответить на его сообщение.*", parse_mode="Markdown")
        return

    try:
        user_id = int(user_id)
    except ValueError:
        await bot.send_message(message.chat.id, "*❌ Введенный айди должен быть числом в правильном формате.*", parse_mode="Markdown")
        return

    user_data = await user_collections.find_one({"_id": user_id})

    if user_data:
        wins = user_data.get("wins", 0)
        participation = user_data.get("participation", 0)
        creation_date = user_data.get("creation_date", "")
        status = user_data.get("status", "")

        profile = f'*🍹 Профиль пользователя* `{user_id}`:\n\n*🍧 Статус:* `{status}`\n\n*🏅 Победы в конкурсах:* `{wins}`\n*🍀 Участие в конкурсах:* `{participation}`\n*📅 Дата регистрации:* `{creation_date}`'
        await bot.send_chat_action(user_id, action="typing")
        await asyncio.sleep(0.5)
        await bot.send_message(message.chat.id, profile, parse_mode="Markdown")
        await state.finish()
    else:
        if args:
            search_id = int(message.text.split(' ')[1])  # Получение айди конкурса из сообщения
            contest = await contests_collection.find_one({"_id": search_id})

            if contest:
                contest_id = contest.get("_id")
                contest_name = contest.get("contest_name")
                owner_id = contest.get("owner_id")
                contest_description = contest.get("contest_description")
                members = contest.get("members")
                end_date = contest.get("end_date")
                members_message = len(members)
                winners = contest.get("winners", 0)
                contest_winners = contest.get("contest_winners")

                if contest_winners:

                    contest_winners_list = "\n".join(
                        [f"<b>{idx}.</b> @{await get_username_winners(user)} — <code>{user}</code>" for idx, user in
                         enumerate(contest_winners, start=1)])
                    result_message = f"<b>🔎 Результаты поиска конкурса </b> <code>{contest_id}</code><b>:</b>\n\n" \
                                     f"<b>🍙 Автор:</b> <code>{owner_id}</code>\n" \
                                     f"<b>🧊 Идентификатор:</b> <code>{contest_id}</code>\n" \
                                     f"<b>🪁 Имя:</b> <code>{contest_name}</code>\n" \
                                     f"<b>🎗️ Описание:</b> <i>{contest_description}</i>\n" \
                                     f"<b>🎖️ Количество победителей:</b> <code>{winners}</code>\n" \
                                     f"<b>👤 Количество участников:</b> <code>{members_message}</code>\n" \
                                     f"<b>🏆 Победители:</b> \n{contest_winners_list}\n" \
                                     f"<b>📆 Дата окончания:</b> <code>{end_date}</code>"
                else:
                    result_message = f"<b>🔎 Результаты поиска конкурса </b> <code>{contest_id}</code><b>:</b>\n\n" \
                                     f"<b>🍙 Автор:</b> <code>{owner_id}</code>\n" \
                                     f"<b>🧊 Идентификатор:</b> <code>{contest_id}</code>\n" \
                                     f"<b>🪁 Имя:</b> <code>{contest_name}</code>\n" \
                                     f"<b>🎗️ Описание:</b> <i>{contest_description}</i>\n" \
                                     f"<b>🎖️ Количество победителей:</b> <code>{winners}</code>\n" \
                                     f"<b>👤 Количество участников:</b> <code>{members_message}</code>\n" \
                                     f"<b>📆 Дата окончания:</b> <code>{end_date}</code>"
                user_id = message.from_user.id
                await bot.send_chat_action(user_id, action="typing")
                await asyncio.sleep(0.5)
                await bot.send_message(message.chat.id, result_message, parse_mode="HTML")
            else:
                await bot.send_message(message.chat.id,
                                       "*❌ Ответьте на сообщение пользователя или укажите айди после команды* /search `{айди}`",
                                       parse_mode="Markdown")
        else:
            await bot.send_message(message.chat.id,
                                    "*❌ Ответьте на сообщение пользователя или укажите айди после команды* /search `{айди}`",
                                    parse_mode="Markdown")

# Профиль через команду
@dp.message_handler(commands=['profile'])
async def start_contest_command(message: types.Message):
        global profile_messages

        user_id = message.from_user.id

        # Поиск данных о пользователе в базе данных
        user_data = await user_collections.find_one({"_id": user_id})

        if user_data:
            username = message.from_user.username  # Получение имени пользователя
            wins = user_data.get("wins", 0)
            participation = user_data.get("participation", 0)
            creation_date = user_data.get("creation_date", "")
            status = user_data.get("status", "")

            # Создание и отправка сообщения с кнопками
            profile = f'*🍹 Профиль пользователя* `{username}`:\n\n*🍧 Статус:* `{status}`\n\n*🏅 Победы в конкурсах:* `{wins}`\n*🍀 Участие в конкурсах:* `{participation}`\n*📅 Дата регистрации:* `{creation_date}`'
            await bot.send_chat_action(user_id, action="typing")
            await asyncio.sleep(0.5)
            reply = await message.reply(profile, parse_mode="Markdown")
        else:
            # Обработка случая, когда данные о пользователе не найдены
            reply = await message.reply("☠️ Профиль пользователя не найден.")
        # Сохранение ID сообщения в глобальную переменную
        profile_messages.append(reply.message_id)

# # Перманнентная блокировака через команду
# @dp.message_handler(commands=['permanent'])
# async def process_search_command(message: types.Message, state: FSMContext):
#     args = message.get_args()
#
#     global permanent_message_id
#
#     profile_user_id = message.from_user.id
#     user_data = await user_collections.find_one({"_id": profile_user_id})
#     ban_members = user_data.get("ban_members")
#
#     if not args and not message.reply_to_message:
#         if ban_members:
#             result_message = "<b>♾️ Черный список:</b>\n\n"
#             for idx, banned_user_id in enumerate(ban_members, start=1):
#                 username = await get_ban_username(banned_user_id)
#                 if username:
#                     username = username.replace("_", "&#95;")
#                 result_message += f"{idx}. @{username} (<code>{banned_user_id}</code>)\n"
#         else:
#             result_message = "<b>Заблокированных пользователей нет. 🚫</b>\n"
#
#         result_message += "\n<b>📛 Чтобы добавить/удалить пользователя</b>\n" \
#                           "/permanent <code>{id}</code>"
#
#         await bot.send_message(message.chat.id, result_message, parse_mode="HTML")
#         return
#
#     if args:
#         user_id = args
#     elif message.reply_to_message:
#         replied_user = message.reply_to_message.from_user
#         user_id = replied_user.id
#     else:
#         user_id = profile_user_id
#
#     if isinstance(user_id, int):
#         user_id = str(user_id)
#
#     try:
#         user_id = int(user_id)
#     except ValueError:
#         await bot.send_message(message.chat.id, "*❌ Введенный айди пользователя должен быть числом.*", parse_mode="Markdown")
#         return
#
#     if args and user_data and user_id == profile_user_id:
#         await bot.send_message(message.chat.id, "*❌ Нельзя добавить самого себя в черный список.*", parse_mode="Markdown")
#         return
#
#     # Проверка на существование пользователя
#     try:
#         await bot.get_chat_member(message.chat.id, user_id)
#     except Exception:
#         await bot.send_message(message.chat.id, "*❌ Такого пользователя не существует.*", parse_mode="Markdown")
#         return
#
#     if not args:
#         if ban_members:
#             result_message = "<b>♾️ Черный список:</b>\n\n"
#             for idx, banned_user_id in enumerate(ban_members, start=1):
#                 username = await get_ban_username(banned_user_id)
#                 if username:
#                     username = username.replace("_", "&#95;")
#                 result_message += f"{idx}. @{username} (<code>{banned_user_id}</code>)\n"
#         else:
#             result_message = "<b>Заблокированных пользователей нет. 🚫</b>\n"
#
#         result_message += "\n<b>📛 Чтобы добавить/удалить пользователя</b>\n" \
#                           "/permanent <code>{id}</code>"
#
#         await bot.send_message(message.chat.id, result_message, parse_mode="HTML")
#         return
#
#     if user_id in ban_members:
#         await del_profile_ban_members(profile_user_id, user_id)
#
            # username = await get_username(user_id)
            # if username:
            #     username = username.replace("_", "&#95;")
#
#         profile = f'<b>🍁 Пользователь</b> @{username} (<code>{user_id}</code>) <b>был удален из черного списка вашего профиля!</b>\n\n' \
#                   f'<b>♾️ Для просмотра всех заблокированных пользователей напишите /permanent</b>'
#         await bot.send_message(message.chat.id, profile, parse_mode="HTML")
#         await state.finish()
#     else:
#         await update_profile_ban_members(profile_user_id, user_id)
#
        # username = await get_username(user_id)
        # if username:
        #     username = username.replace("_", "&#95;")
#
#         profile = f'<b>🍁 Пользователь</b> @{username} (<code>{user_id}</code>) <b>был внесен в черный список вашего профиля!</b>\n\n' \
#                   f'<b>♾️ Для просмотра всех заблокированных пользователей напишите /permanent</b>'
#         await bot.send_message(message.chat.id, profile, parse_mode="HTML")
#         await state.finish()

# Команда промокод

@dp.message_handler(commands=['promo'])
async def process_promo_command(message: types.Message):
    args = message.get_args()

    parts = args.split(' ')
    if args:
        user_data = await user_collections.find_one({"_id": message.from_user.id})
        status = user_data.get("status")
        if status == "Создатель 🎭" or status == "Админ 🚗":
            if len(parts) == 1:
                # Обработка команды /promo (сам промокод)
                promo_code = args
                await handle_promo_code(promo_code, message.from_user.id)
            if len(parts) == 2:
                # Обработка команды /promo (название) (количество)
                promo_name = parts[0]
                quantity = int(parts[1])
                visible = "True"
                prize = "None"
                await create_promo_codes(promo_name, quantity, visible, prize, message.from_user.id)
            elif len(parts) == 3:
                # Обработка команды /promo (название) (количество) (видимость)
                promo_name = parts[0]
                quantity = int(parts[1])
                visible = parts[2]
                if visible == "False":
                    visible = "False"
                else:
                    visible = "True"
                prize = "None"
                await create_promo_codes(promo_name, quantity, visible, prize, message.from_user.id)
            if status == "Создатель 🎭":
                if len(parts) == 4:
                    # Обработка команды /promo (название) (количество) (видимость) (награда)
                    promo_name = parts[0]
                    quantity = int(parts[1])
                    visible = parts[2]
                    if visible == "False":
                        visible = "False"
                    else:
                        visible = "True"
                    prize = parts[3]
                    await create_promo_codes(promo_name, quantity, visible, prize, message.from_user.id)
            else:
                pass
        else:
            if len(parts) == 1:
                # Обработка команды /promo (сам промокод)
                promo_code = args
                await handle_promo_code(promo_code, message.from_user.id)
    else:
        active_promos = await get_active_promo_codes()
        if active_promos:
            await message.reply(f"*📽️ Активные промокоды:*\n{active_promos}\n\n"
                                "*🧪 Для активации промокода* /promo `{промокод}`", parse_mode="Markdown")
        else:
            await message.reply("*🤫 Активных промокодов не обнаружено!*\n\n"
                                "*🧪 Для активации промокода* /promo `{промокод}`", parse_mode="Markdown")

# Команда для просмотра всех кто активировал промокод
@dp.message_handler(commands=['promo_list'])
async def process_promo_list_command(message: types.Message):
    promo_id = message.get_args()
    user_data = await user_collections.find_one({"_id": message.from_user.id})
    status = user_data.get("status")
    current_page = 1
    if status == "Создатель 🎭" or status == "Админ 🚗":
        if promo_id:
            promo = await promo_collection.find_one({"_id": promo_id})
            if promo:
                active_members = promo.get("active_members", [])
                uses = promo.get("uses")
                if active_members:
                    await promo_members(message.chat.id, promo_id, current_page)
                else:
                    await message.reply(f"*📋 Промокод* `{promo_id}` *не был активирован ни одним пользователем.*",
                                        parse_mode="Markdown")
            else:
                await message.reply("*❌ Промокод не найден.*", parse_mode="Markdown")
        else:
            await message.reply("*❌ Пожалуйста, укажите идентификатор промокода.*", parse_mode="Markdown")

@dp.message_handler(commands=['help'])
async def start_contest_command(message: types.Message):
    user_id = message.from_user.id

    await bot.send_chat_action(user_id, action="typing")
    await asyncio.sleep(0.7)
    # Создание и отправка сообщения с кнопками
    profile = f'*Навигация по боту 💤*\n\n' \
              f'/start - 🎭 Основное меню, помогает посмотреть свой профиль и активные конкурсы на данный момент, также использовать кнопку `Поддержка 🆘`.\n' \
              f'/search - 🔎 Поиск конкурса/пользователя, используя его айди.\n' \
              f'/profile - 👤 Чат-команда для показа своего профиля.\n' \
              f'/promo - 🧪 Просмотр активных промокодов, также их активация!\n' \
              f'/contest - 🎖 Меню для создания ваших конкурсов и управлениями ими, доступ к меню получается только через `ключ 🔑`.\n' \
              f'/generate - 🗝️ Создание/покупка (в будущем) ключа для формирования конкурсов!\n\n'

    # Создание кнопки-ссылки "Детальнее"
    inline_keyboard = types.InlineKeyboardMarkup()
    inline_keyboard.add(types.InlineKeyboardButton(text="Детальнее ❔", url="https://teletype.in/@kpyr/Flame"))

    await message.reply(profile, parse_mode="Markdown", reply_markup=inline_keyboard)

# Обработчик команды для очистки личных чатов с пользователями
@dp.message_handler(commands=['clear_all_chats'])
async def clear_all_user_chats(message: types.Message):
    # Get all _id users from the database
    all_user_data = await user_collections.find(projection={"_id": 1}).to_list(length=None)

    if all_user_data:
        chat_id_list = [user_data["_id"] for user_data in all_user_data]

        for chat_id in chat_id_list:
            # Wait a while before deleting the next chat (about 1 second)
            await asyncio.sleep(0.1)

            try:
                # You need to keep track of the message_id when the bot sends a message
                # Here messages is a list or other data structure that holds all the stored message IDs
                messages = get_list_of_message_ids_for_this_chat_id(chat_id)
                for msg_id in messages:
                    await bot.delete_message(chat_id, msg_id)
            except Exception as e:
                print(f"Failed to delete messages in chat {chat_id}: {e}")

@dp.message_handler(commands=['id'])
async def get_user_profile(message: types.Message):
    # Get the user ID from the command arguments
    args = message.get_args()
    if not args:
        await message.reply("Пожалуйста укажите айди. Пример: /id <айди>")
        return

    try:
        user_id = int(args)
    except ValueError:
        await message.reply("Инвалид. Пожалуйста, укажите правильный айди.")
        return

    try:
        # Get the user information using the provided user ID
        user = await bot.get_chat(user_id)
        username = user.username
        first_name = user.first_name
        last_name = user.last_name

        # Create the message showing the user profile
        if username:
            result_message = f"Профиль 📒\n" \
                             f"Тэг: @{username}\n"
        else:
            result_message = "Юзернейм отсутствует ❌\n\n"

        # Add first name and last name if available
        if first_name:
            result_message += f"Имя: {first_name}"
        if last_name:
            result_message += f" {last_name}"

        await message.reply(result_message)
    except Exception as e:
        await message.reply("Ошибка при получении профиля пользователя. Пожалуйста, убедитесь, что вы указали правильный айди.")

# Кнопки
@dp.callback_query_handler(lambda callback_query: True)
async def button_click(callback_query: types.CallbackQuery, state: FSMContext):
    global contest_name, contest_id, contest_description, winners, end_date
    global profile_messages
    global change_message_id
    global promo_message_id

    # Получение данных о нажатой кнопке
    button_text = callback_query.data
    user_id = callback_query.from_user.id

    emojis = ["🎉", "🎈", "🎁", "🏆", "🎖️", "🏅", "🍙", "🎫", "🎗️", "🍿", "🎀", "🎟️", "🧣", "🎒", "📣", "📢", "🌟", "✨", "🔥", "🎵",
              "🎶", "💃", "🕺", "🎯", "📚", "💡", "🖌️", "📸", "🎥", "🖼️", "🎨", "💎", "🌹", "🌼", "🌺", "🌷", "🌸", "🌕", "🌙", "⭐", "🌈", "☀️"]

    keyboard = None  # Объявление переменной keyboard

    if button_text == 'active_drawings':
        active_drawings = ["*🫧 Активные конкурсы на данный момент:*\n"]

        all_contests = contests_collection.find()

        active_contests_found = False  # Флаг, указывающий на то, были ли найдены активные конкурсы

        async for contest in all_contests:
            contest_id = contest["_id"]
            members_count = len(contest.get("members", []))
            ended = contest.get("ended")  # Проверяем значение параметра "ended", по умолчанию False

            if ended == "False":
                message_text = f"*🍭 Конкурс:* `{contest_id}`\n*🏯 Количество участников:* `{members_count}`\n"
                active_drawings.append(message_text)
                active_contests_found = True

        if active_contests_found:
            active_drawings_text = "\n".join(active_drawings)

            # Создание и отправка сообщения с кнопками
            keyboard = types.InlineKeyboardMarkup()
            # statistic = types.InlineKeyboardButton(text='🪡 Посмотреть статистику', callback_data='statistic')
            # history = types.InlineKeyboardButton(text='📜 Посмотреть историю', callback_data='drawings_history')
            done = types.InlineKeyboardButton(text='Выполнено ✅', callback_data='done')
            # keyboard.add(history, statistic)
            keyboard.add(done)

            await bot.send_message(callback_query.message.chat.id, text=active_drawings_text, parse_mode="Markdown",
                                   reply_markup=keyboard)
        else:
            # Создание и отправка сообщения с кнопками
            keyboard = types.InlineKeyboardMarkup()
            # statistic = types.InlineKeyboardButton(text='🪡 Посмотреть статистику', callback_data='statistic')
            # history = types.InlineKeyboardButton(text='📜 Посмотреть историю', callback_data='drawings_history')
            done = types.InlineKeyboardButton(text='Выполнено ✅', callback_data='done')
            # keyboard.add(history, statistic)
            keyboard.add(done)

            await bot.send_message(callback_query.message.chat.id, "*🫧 Упс... Сейчас активных конкурсов не обнаружено!*",
                                   parse_mode="Markdown", reply_markup=keyboard)

    elif button_text == 'profile':
        global profile_messages

        user_id = callback_query.from_user.id

        # Поиск данных о пользователе в базе данных
        user_data = await user_collections.find_one({"_id": user_id})

        if user_data:
            username = callback_query.from_user.username
            wins = user_data.get("wins", 0)
            participation = user_data.get("participation", 0)
            creation_date = user_data.get("creation_date", "")
            status = user_data.get("status", "")

            # Создание и отправка сообщения с кнопками
            profile = f'*🍹 Профиль пользователя* `{username}`:\n\n*🍧 Статус:* `{status}`\n\n*🏅 Победы в конкурсах:* `{wins}`\n*🍀 Участие в конкурсах:* `{participation}`\n*📅 Дата регистрации:* `{creation_date}`'
            keyboard = types.InlineKeyboardMarkup()
            history = types.InlineKeyboardButton(text='История участий 📔', callback_data=f'history_{user_id}_None_1')
            id_check = types.InlineKeyboardButton(text='Поиск пользователя 🥏', callback_data='id_check')
            done = types.InlineKeyboardButton(text='Готово ✅', callback_data='done')
            keyboard.add(history, id_check)
            keyboard.add(done)

            reply = await bot.send_message(callback_query.message.chat.id, text=profile, parse_mode="Markdown",
                                           reply_markup=keyboard)
        else:
            # Обработка случая, когда данные о пользователе не найдены
            reply = await bot.send_message(callback_query.message.chat.id, "☠️ Профиль пользователя не найден.")

        # Сохранение ID сообщения в глобальную переменную
        profile_messages.append(reply.message_id)

    elif button_text == 'profile_edit':

        user_id = callback_query.from_user.id

        # Поиск данных о пользователе в базе данных
        user_data = await user_collections.find_one({"_id": user_id})

        username = callback_query.from_user.username
        wins = user_data.get("wins", 0)
        participation = user_data.get("participation", 0)
        creation_date = user_data.get("creation_date", "")
        status = user_data.get("status", "")

        # Создание и отправка сообщения с кнопками
        profile = f'*🍹 Профиль пользователя* `{username}`:\n\n*🍧 Статус:* `{status}`\n\n*🏅 Победы в конкурсах:* `{wins}`\n*🍀 Участие в конкурсах:* `{participation}`\n*📅 Дата регистрации:* `{creation_date}`'
        keyboard = types.InlineKeyboardMarkup()
        history = types.InlineKeyboardButton(text='История участий 📔', callback_data=f'history_{user_id}_None_1')
        id_check = types.InlineKeyboardButton(text='Поиск пользователя 🥏', callback_data='id_check')
        done = types.InlineKeyboardButton(text='Готово ✅', callback_data='done')
        keyboard.add(history, id_check)
        keyboard.add(done)

        # Send or edit the message with pagination
        await bot.edit_message_text(profile, callback_query.message.chat.id,
                                                callback_query.message.message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)

    elif button_text == 'support':

        creator_username = "[@Kpyr](https://t.me/Kpyr_uy)"
        support = f"🆔 Ваш id: `{user_id}`\n\n/help - Помощь в боте. 💾\n\n*📱 Контакты для обратной связи:*\n\n*🎭 Создатель бота:* {creator_username}"

        await callback_query.message.answer(text=support, parse_mode="Markdown")

    elif button_text == 'create':

        # Update the message with new buttons
        keyboard = types.InlineKeyboardMarkup()
        continue_create = types.InlineKeyboardButton(text='Продолжить ✅', callback_data='continue_create')
        decline_create = types.InlineKeyboardButton(text='Отмена ❌', callback_data='decline_create')
        keyboard.add(decline_create, continue_create)
        create_text = f"*💠 Если вы создадите конкурс ваш ранее активированный ключ потратится и вы потеряете возможность создавать новые конкурсы до момента активации нового ключа, вы уверены что хотите продолжить?*"

        # Get the message ID from the contest_messages list
        message_id = contest_messages[-1]

        # Update the message with new text and buttons
        await bot.edit_message_text(create_text, callback_query.message.chat.id, message_id, parse_mode="Markdown",
                                    reply_markup=keyboard)

    elif button_text == 'decline_create':

        # Clear the waiting state
        await state.finish()

        user_id = callback_query.from_user.id
        user_data = await user_collections.find_one({"_id": user_id})

        if user_data and (
                ("status" in user_data and user_data["status"] in ["Тестер ✨", "Админ 🚗", "Создатель 🎭"]) or int(
                user_data.get("keys", 0)) > 0):
            # Code for existing user
            keyboard = types.InlineKeyboardMarkup()
            search = types.InlineKeyboardButton(text='🔎 Проверить', callback_data='search')
            create = types.InlineKeyboardButton(text='🎫 Создать', callback_data='create')
            change = types.InlineKeyboardButton(text='🍭 Редактировать', callback_data='change')
            keyboard.row(change, search)
            keyboard.row(create)

            # Get the message ID from the contest_messages list
            message_id = contest_messages[-1]
            text = "*🍡 Рады вас видеть в панели управления конкурсами!*\n\n*✨ Воспользуйтесь кнопками для управления конкурсом или его создания:*"

            reply = await bot.edit_message_text(text, callback_query.message.chat.id, message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)

            # Update the message ID in the contest_messages list
            contest_messages[-1] = reply.message_id
        else:
            # Code for existing user
            keyboard = types.InlineKeyboardMarkup()
            input_key = types.InlineKeyboardButton(text='🔑 Ввести ключ', callback_data='input_key')
            keyboard.row(input_key)

            # Get the message ID from the contest_messages list
            message_id = contest_messages[-1]
            text = "*👀 Воспользуйтесь кнопкой и введите уникальный ключ для доступа к созданию конкурсов:*"

            reply = await bot.edit_message_text(text, callback_query.message.chat.id, message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)

            # Update the message ID in the contest_messages list
            contest_messages[-1] = reply.message_id

    elif button_text == 'continue_create':

        # Update the message with new text
        create_text = "*🪁 Введите имя конкурса:*"

        keyboard = types.InlineKeyboardMarkup()
        input_key = types.InlineKeyboardButton(text=' Пропустить 🚩', callback_data='skip_name')
        keyboard.row(input_key)

        # Get the message ID from the contest_messages list
        message_id = contest_messages[-1]

        await bot.edit_message_text(create_text, callback_query.message.chat.id, message_id, parse_mode="Markdown", reply_markup=keyboard)

        # Set the waiting state to capture the user's input
        await CreateContestState.name.set()

    elif button_text == 'confirm_create':

        user_id = callback_query.from_user.id
        user_data = await user_collections.find_one({"_id": user_id})

        if user_data and ("status" in user_data and user_data["status"] in ["Тестер ✨", "Админ 🚗", "Создатель 🎭"]):
            pass
        else:
            await user_collections.update_one({"_id": user_id}, {"$inc": {"keys": -1}})

        # Генерация уникальной ссылки запуска
        start_link = await generate_start_link(contest_id)

        confirmation_text = f"*🍭 Конкурс* `{contest_id}` *был успешно создан!*\n*🗺️ Также, держите ссылку для регистрации:* `{start_link}`"

        # Создание конкурса
        await create_contest(contest_id, user_id, contest_name, contest_description, int(winners), end_date, start_link)

        # Получение идентификатора сообщения из списка contest_messages
        message_id = contest_messages[-1]

        await bot.edit_message_text(confirmation_text, callback_query.message.chat.id, message_id,
                                    parse_mode="Markdown", reply_markup=keyboard)

    elif button_text == 'back_search':

        message_id = contest_messages[-1]

        user_id = callback_query.from_user.id
        user_data = await user_collections.find_one({"_id": user_id})

        if user_data and (
                ("status" in user_data and user_data["status"] in ["Тестер ✨", "Админ 🚗", "Создатель 🎭"]) or int(
                user_data.get("keys", 0)) > 0):

            # Код для существующего пользователя
            keyboard = types.InlineKeyboardMarkup()
            search = types.InlineKeyboardButton(text='🔎 Проверить', callback_data='search')
            create = types.InlineKeyboardButton(text='🎫 Создать', callback_data='create')
            change = types.InlineKeyboardButton(text='🍭 Редактировать', callback_data='change')
            keyboard.row(change, search)
            keyboard.row(create)

            confirmation_text = "*🍡 Рады вас видеть в панели управления конкурсами!*\n\n*✨ Воспользуйтесь кнопками для управления конкурсом или его создания:*"

            reply = await bot.edit_message_text(confirmation_text, callback_query.message.chat.id, message_id,
                                                parse_mode="Markdown",
                                                reply_markup=keyboard)

            # Сохранение ID сообщения в глобальную переменную
            contest_messages.append(reply.message_id)

        else:
            # Код для существующего пользователя
            keyboard = types.InlineKeyboardMarkup()
            input_key = types.InlineKeyboardButton(text='🔑 Ввести ключ', callback_data='input_key')
            keyboard.row(input_key)

            confirmation_text = "*👀 Воспользуйтесь кнопкой и введите уникальный ключ для доступа к созданию конкурсов:*"

            reply = await bot.edit_message_text(confirmation_text, callback_query.message.chat.id, message_id,
                                                parse_mode="Markdown",
                                                reply_markup=keyboard)

            # Сохранение ID сообщения в глобальную переменную
            contest_messages.append(reply.message_id)

    elif button_text.startswith('history'):
        user_id = callback_query.from_user.id

        parts = button_text.split('_')
        if user_id:
            pass
        else:
            user_id = int(parts[1])
        action = parts[2]
        current_page = int(parts[3])

        if action == 'prev':
            current_page -= 1
        elif action == 'next':
            current_page += 1
        else:
            current_page = 1

        await show_user_history(callback_query, user_id, current_page)

    elif button_text == 'back_history':

        user_id = callback_query.from_user.id

        message_id = profile_messages[-1]

        # Поиск данных о пользователе в базе данных
        user_data = await user_collections.find_one({"_id": user_id})

        if user_data:
            username = callback_query.from_user.username
            wins = user_data.get("wins", 0)
            participation = user_data.get("participation", 0)
            creation_date = user_data.get("creation_date", "")
            status = user_data.get("status", "")

            # Создание и отправка сообщения с кнопками
            profile = f'*🍹 Профиль пользователя* `{username}`:\n\n*🍧 Статус:* `{status}`\n\n*🏅 Победы в конкурсах:* `{wins}`\n*🍀 Участие в конкурсах:* `{participation}`\n*📅 Дата регистрации:* `{creation_date}`'
            keyboard = types.InlineKeyboardMarkup()
            history = types.InlineKeyboardButton(text='История участий 📔', callback_data='history')
            id_check = types.InlineKeyboardButton(text='Поиск пользователя 🥏', callback_data='id_check')
            done = types.InlineKeyboardButton(text='Готово ✅', callback_data='done')
            keyboard.add(history, id_check)
            keyboard.add(done)

            reply = await bot.edit_message_text(profile, callback_query.message.chat.id, message_id,
                                                parse_mode="Markdown",
                                                reply_markup=keyboard)
        else:
            # Обработка случая, когда данные о пользователе не найдены
            reply = await bot.send_message(callback_query.message.chat.id, "☠️ Профиль пользователя не найден.")

        # Сохранение ID сообщения в глобальную переменную
        profile_messages.append(reply.message_id)

    elif button_text == 'change':

        user_id = callback_query.from_user.id

        # Поиск конкурса по айди
        contests = await contests_collection.find({"owner_id": user_id}).to_list(length=None)

        message_id = contest_messages[-1]

        if contests:
            # Создаем переменную для хранения сообщения с активными конкурсами
            result_message = "*🎯 Ваши активные конкурсы:*\n\n"

            # Итерация по каждому конкурсу с помощью enumerate
            for idx, contest in enumerate(contests, start=1):
                # Извлечение необходимых данных из найденного конкурса
                contest_id = contest.get("_id")
                contest_name = contest.get("contest_name")
                members = contest.get("members")
                ended = contest.get("ended")

                if ended == "True":
                    pass
                else:
                    if members:
                        members_count = len(members)
                    else:
                        members_count = 0
                    if members_count > 0:
                        members_message = f"{members_count}"
                    else:
                        members_message = "0"

                    # Формирование сообщения с данными конкурса и включение индекса
                    result_message += f"                            *= {idx} =*\n" \
                                      f"*🪁 Имя:* `{contest_name}`\n" \
                                      f"*🧊 Айди конкурса* `{contest_id}`*:*\n" \
                                      f"*🏯 Количество участников:* `{members_message}`\n\n"
        else:
            result_message = "*У вас нет активных конкурсов ❌*"

        keyboard = types.InlineKeyboardMarkup()
        decline_create = types.InlineKeyboardButton(text='Назад 🧿', callback_data='decline_create')
        contest_check = types.InlineKeyboardButton(text='Управление 🧧', callback_data='contest_check')

        keyboard.row(contest_check)
        keyboard.row(decline_create)

        reply = await bot.edit_message_text(result_message, callback_query.message.chat.id, message_id,
                                            parse_mode="Markdown",
                                            reply_markup=keyboard)

        # Сохранение ID сообщения в глобальную переменную
        change_message_id.append(reply.message_id)

    elif button_text == 'contest_check':

        user_id = callback_query.from_user.id

        # Поиск конкурса по айди
        contests = await contests_collection.find({"owner_id": user_id}).to_list(length=None)
        message_id = contest_messages[-1]

        if contests:

            # Создаем переменную для хранения сообщения с активными конкурсами
            result_message = "*🧧 Выберите конкурс, который хотите редактировать:*\n\n"

            # Создаем клавиатуру для кнопок конкурсов
            keyboard = types.InlineKeyboardMarkup()

            # Итерация по каждому конкурсу
            for contest in contests:

                # Извлечение необходимых данных из найденного конкурса
                contest_id = contest.get("_id")
                ended = contest.get("ended")
                if ended == "True":
                    pass
                else:
                    # Генерируем случайный эмодзи из списка
                    random_emoji = random.choice(emojis)

                    # Создаем кнопку для конкретного конкурса с эмодзи
                    contest_button = types.InlineKeyboardButton(text=f'{contest_id} {random_emoji} ',
                                                                callback_data=f'contest_button_{contest_id}')
                    # Добавляем кнопку в клавиатуру
                    keyboard.row(contest_button)

            decline_create = types.InlineKeyboardButton(text='Назад 🧿',
                                                        callback_data="decline_create")
            keyboard.row(decline_create)
            # Обновляем сообщение с активными конкурсами и добавляем клавиатуру
            reply = await bot.edit_message_text(result_message, callback_query.message.chat.id, message_id,
                                                parse_mode="Markdown",
                                                reply_markup=keyboard)

            # Сохранение ID сообщения в глобальную переменную
            change_message_id.append(reply.message_id)

        else:
            # Если нет активных конкурсов, показываем соответствующее сообщение
            no_contests_message = "*У вас не обнаружено активных конкурсов‼️*"
            int_digit = await bot.edit_message_text(no_contests_message, callback_query.message.chat.id, message_id,
                                                    parse_mode="Markdown")
            change_message_id.append(int_digit.message_id)

    elif button_text.startswith('contest_button'):

        contest_id = button_text.split('_')[2]

        # Поиск конкурса по айди
        contest = await contests_collection.find_one({"_id": int(contest_id)})
        message_id = change_message_id[-1]

        if contest:
            # Извлечение необходимых данных из найденного конкурса
            contest_id = contest.get("_id")
            contest_name = contest.get("contest_name")
            contest_description = contest.get("contest_description")
            winners = contest.get("winners")
            members = contest.get("members")
            end_date = contest.get("end_date")

            if members:
                members_count = len(members)
            else:
                members_count = 0

            if members_count > 0:
                members_message = f"{members_count}"
            else:
                members_message = "0"

            result_message = f"*🏆 Редакция конкурса* `{contest_id}`*:*\n\n" \
                                f"*🪁 Имя:* `{contest_name}`\n" \
                                f"*🧊 Идентификатор:* `{contest_id}`\n" \
                                f"*🎗️ Описание:* _{contest_description}_\n" \
                                f"*🎖️ Количество победителей:* `{winners}`\n" \
                                f"*🏯 Количество участников:* `{members_message}`\n" \
                                f"*📆 Дата окончания:* `{end_date}`"

            keyboard = types.InlineKeyboardMarkup()
            contest_change = types.InlineKeyboardButton(text='Изменение 🥨', callback_data=f'contest_change_{contest_id}')
            winner = types.InlineKeyboardButton(text='Выбор победит. 🏆', callback_data=f'winner_refining_{contest_id}')
            members = types.InlineKeyboardButton(text='Участинки 🏯', callback_data=f'members_{contest_id}_None_1')
            back_search = types.InlineKeyboardButton(text='Назад 🧿', callback_data='change')
            keyboard.row(contest_change, winner)
            keyboard.row(members)
            keyboard.row(back_search)

            reply = await bot.edit_message_text(result_message, callback_query.message.chat.id, message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)
            # Сохранение ID сообщения в глобальную переменную
            change_message_id.append(reply.message_id)
        else:
            int_digit = await bot.send_message(callback_query.message.chat.id, "*❌ Конкурс с указанным айди не найден.*",
                                               parse_mode="Markdown")
            await asyncio.sleep(4)
            await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=int_digit.message_id)

    elif button_text.startswith('contest_change'):

        contest_id = button_text.split('_')[2]

        # Поиск конкурса по айди
        contest = await contests_collection.find_one({"_id": int(contest_id)})
        message_id = change_message_id[-1]

        if contest:
            # Извлечение необходимых данных из найденного конкурса
            contest_id = contest.get("_id")
            contest_name = contest.get("contest_name")
            contest_description = contest.get("contest_description")
            winners = contest.get("winners")
            members = contest.get("members")
            end_date = contest.get("end_date")

            if members:
                members_count = len(members)
            else:
                members_count = 0

            if members_count > 0:
                members_message = f"{members_count}"
            else:
                members_message = "0"

            result_message = f"*🏆 Редакция конкурса* `{contest_id}`*:*\n\n" \
                                f"*🪁 Имя:* `{contest_name}`\n" \
                                f"*🧊 Идентификатор:* `{contest_id}`\n" \
                                f"*🎗️ Описание:* _{contest_description}_\n" \
                                f"*🎖️ Количество победителей:* `{winners}`\n" \
                                f"*🏯 Количество участников:* `{members_message}`\n" \
                                f"*📆 Дата окончания:* `{end_date}`"

            keyboard = types.InlineKeyboardMarkup()
            name_change = types.InlineKeyboardButton(text='Имя  ️🪁', callback_data=f'name_change_{contest_id}')
            description_change = types.InlineKeyboardButton(text='Описание 🎗️️', callback_data=f'description_change_{contest_id}')
            winners_change = types.InlineKeyboardButton(text='Победители 🎖️', callback_data=f'winners_change_{contest_id}')
            date_change = types.InlineKeyboardButton(text='Дата  ️📆', callback_data=f'date_change_{contest_id}')
            back = types.InlineKeyboardButton(text='Назад 🧿', callback_data=f'change')
            keyboard.row(name_change)
            keyboard.row(description_change)
            keyboard.row(winners_change)
            keyboard.row(date_change)
            keyboard.row(back)

            reply = await bot.edit_message_text(result_message, callback_query.message.chat.id, message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)
            # Сохранение ID сообщения в глобальную переменную
            change_message_id.append(reply.message_id)
        else:
            int_digit = await bot.send_message(callback_query.message.chat.id, "*❌ Конкурс с указанным айди не найден.*",
                                               parse_mode="Markdown")
            await asyncio.sleep(4)
            await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=int_digit.message_id)

    elif button_text.startswith('winner_refining'):

        contest_id = button_text.split('_')[2]

        # Поиск конкурса по айди
        contest = await contests_collection.find_one({"_id": int(contest_id)})
        members = contest.get("members")
        winners = contest.get("winners")
        message_id = change_message_id[-1]

        if int(winners) > len(members):
            result_message = f"❌ *Недостаточно участников для завершения конкурса* `{contest_id}`*:*\n\n" \
                             f"*🥇 Указанное количество победителей:* `{winners}`\n" \
                             f"*👤 Текущее количество участников:* `{len(members)}`"
            keyboard = types.InlineKeyboardMarkup()
            winner_decline = types.InlineKeyboardButton(text='Назад 🧿', callback_data='change')
            keyboard.row(winner_decline)
        else:
            result_message = f"🏆 *Вы уверены что хотитет завершить конкурс* `{contest_id}`*?*"
            keyboard = types.InlineKeyboardMarkup()
            winner = types.InlineKeyboardButton(text='Подтвердить ✅', callback_data=f'winner_{contest_id}')
            winner_decline = types.InlineKeyboardButton(text='Отмена ❌', callback_data='change')
            keyboard.row(winner_decline, winner)

        reply = await bot.edit_message_text(result_message, callback_query.message.chat.id, message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)
        # Сохранение ID сообщения в глобальную переменную
        change_message_id.append(reply.message_id)

    elif button_text.startswith('winner'):

        contest_id = button_text.split('_')[1]

        # Поиск конкурса по айди
        contest = await contests_collection.find_one({"_id": int(contest_id)})
        winners = contest.get("winners")
        members = contest.get("members")

        message_id = change_message_id[-1]

        if len(members) < int(winners):
            await bot.edit_message_text("*❌ Участников меньше, чем заданное число победителей.*\n\n"
                                        f"🥇 Число победителей: {winners}"
                                        f"👤 Текущее количество участников {len(members)}",
                                        callback_query.message.chat.id, message_id, parse_mode="Markdown")
            return

        # Случайный выбор победителей
        random_winners = random.sample(members, int(winners))
        result_message = f"<b>🏆 Конкурс</b> <code>{contest_id}</code> <b>был успешно завершен!</b>\n\n"

        if int(winners) > 1:
            result_message += "<b>🎖️ Победители:</b>\n"
            share_message = f"** - Конкурс бот 🎭**\n\n**🎖️ Победители конкурса** `{contest_id}`:\n"

            for idx, winner in enumerate(random_winners, start=1):
                user_id = winner
                username = await get_username(user_id)
                if username:
                    formatted_username = username.replace("_", "&#95;")
                else:
                    formatted_username = "None"
                result_message += f"<b>{idx}.</b> @{formatted_username} <b>—</b> <code>{winner}</code>\n"
                share_message += f"**{idx}.** @{username} — `{user_id}`\n"

                # Увеличение счетчика побед пользователя
                user_data = await user_collections.find_one({"_id": user_id})

                if user_data:
                    wins = user_data.get("wins", 0)
                    wins += 1
                    await update_status(user_id)
                    await user_collections.update_one({"_id": user_id}, {"$set": {"wins": wins}}, upsert=True)
                    # Отправка личного сообщения пользователю о победе
                    winner_message = f"*🥇 Поздравляем! Вы стали одним из победителей конкурса* `{contest_id}`*!*"
                    await bot.send_message(user_id, winner_message, parse_mode="Markdown")
                if contest:
                    ended = "True"
                    await contests_collection.update_one({"_id": int(contest_id)}, {"$set": {"ended": ended}}, upsert=True)
                await update_win_contest_members(contest_id, user_id)

        else:
            result_message += "<b>🎖️ Победитель:</b>\n"

            user_id = random_winners[0]

            username = await get_username(user_id)
            if username:
                formatted_username = username.replace("_", "&#95;")
            else:
                formatted_username = "None"

            result_message += f"@{formatted_username} <b>—</b> <code>{user_id}</code>"
            share_message = f"** - Конкурс бот 🎭**\n\n**🎖️ Победитель конкурса** `{contest_id}`:\n" \
                            f"@{username} — `{user_id}`"

            # Увеличение счетчика побед пользователя
            user_data = await user_collections.find_one({"_id": user_id})

            if user_data:
                wins = user_data.get("wins", 0)
                wins += 1
                await update_status(user_id)
                await user_collections.update_one({"_id": user_id}, {"$set": {"wins": wins}}, upsert=True)
                # Отправка личного сообщения пользователю о победе
                winner_message = f"*🥇 Поздравляем! Вы стали победителем конкурса* `{contest_id}`*!*"
                await bot.send_message(user_id, winner_message, parse_mode="Markdown")
            if contest:
                ended = "True"
                await contests_collection.update_one({"_id": int(contest_id)}, {"$set": {"ended": ended}}, upsert=True)
            await update_win_contest_members(contest_id, user_id)

        markup = types.InlineKeyboardMarkup()
        share_button = types.InlineKeyboardButton(text='Поделиться 🫴', switch_inline_query=f'{share_message}')
        markup.add(share_button)

        reply = await bot.edit_message_text(result_message, callback_query.message.chat.id, message_id,
                                            parse_mode="HTML",
                                            reply_markup=markup)

        # Сохранение ID сообщения в глобальную переменную
        change_message_id.append(reply.message_id)

    elif button_text.startswith('members'):

        parts = button_text.split('_')
        contest_id = int(parts[1])
        action = parts[2]
        current_page = int(parts[3])

        if action == 'prev':
            current_page -= 1

        elif action == 'next':
            current_page += 1

        await show_members(callback_query, contest_id, current_page)

    elif button_text.startswith('ban_members'):

        parts = button_text.split('_')
        contest_id = parts[2]
        action = parts[3]
        current_page = int(parts[4])

        if action == 'prev':
            current_page -= 1

        elif action == 'next':
            current_page += 1

        await show_ban_members(callback_query, contest_id, current_page)

    elif button_text.startswith('block_profile'):

        parts = button_text.split('_')
        search_user_id = parts[2]
        contest_id = parts[3]

        # Поиск конкурса по айди
        contest = await contests_collection.find_one({"_id": int(contest_id)})
        user_data = await user_collections.find_one({"_id": int(search_user_id)})
        participation = user_data.get("participation")

        if contest:
            members = contest.get("members")
            ban_members = contest.get("ban_members")
            join_date = contest.get("join_date")

            if int(search_user_id) in members or int(search_user_id) in ban_members:
                user_index = members.index(int(search_user_id))

                await bot.answer_callback_query(callback_query.id, text="Пользователь был успешно заблокирован! ✔️")

                # Удаление search_user_id из members
                members.remove(int(search_user_id))

                # Удаление соответствующего элемента из join_date
                join_date.pop(user_index)

                # Добавление search_user_id в ban_members
                ban_members.append(int(search_user_id))

                if participation > 0:
                    # Уменьшение участий на 1
                    participation_result = int(participation) - 1

                    # Обновление параметра participation в документе пользователя
                    await user_collections.update_one({"_id": int(search_user_id)},
                                                      {"$set": {"participation": participation_result}})
                # Обновление документа в базе данных
                await contests_collection.update_one({"_id": int(contest_id)}, {
                    "$set": {"members": members, "join_date": join_date, "ban_members": ban_members}})

                message_id = change_message_id[-1]

                username = await get_username(search_user_id)
                if username:
                    username = username.replace("_", "&#95;")

                # Формирование сообщения с данными пользователя
                result_message = f"<b>🧶Пользователь:</b> <code>{search_user_id}</code>\n" \
                                 f"<b>🪐 Юзернейм:</b> @{username}\n" \
                                 f"<b>‼️ Состояние:</b> <code>Заблокирован!</code>"
                unblock = types.InlineKeyboardButton(text='Разблокировать ❎',
                                                     callback_data=f'unblock_profile_{search_user_id}_{contest_id}')

                keyboard = types.InlineKeyboardMarkup()
                back_search = types.InlineKeyboardButton(text='Назад 🧿', callback_data='contest_check')
                input_id = types.InlineKeyboardButton(text='Искать ещё 🔎',
                                                      callback_data=f'contest_search_profile_{contest_id}')
                keyboard.row(input_id)
                keyboard.row(unblock)
                keyboard.row(back_search)

                reply = await bot.edit_message_text(result_message, callback_query.message.chat.id, message_id,
                                                    parse_mode="HTML",
                                                    reply_markup=keyboard)

                # Сохранение ID сообщения в глобальную переменную
                change_message_id.append(reply.message_id)
            else:
                int_digit = await bot.send_message(callback_query.message.chat.id, "*❌ Пользователь не обнаружен.*",
                                                   parse_mode="Markdown")
                await asyncio.sleep(4)
                await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=int_digit.message_id)
        else:
            int_digit = await bot.send_message(callback_query.message.chat.id, "*❌ Конкурс не найден.*",
                                               parse_mode="Markdown")
            await asyncio.sleep(4)
            await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=int_digit.message_id)

    elif button_text.startswith('unblock_profile'):

        parts = button_text.split('_')
        search_user_id = parts[2]
        contest_id = parts[3]

        # Поиск конкурса по айди
        contest = await contests_collection.find_one({"_id": int(contest_id)})

        if contest:

            members = contest.get("members")
            ban_members = contest.get("ban_members")

            if int(search_user_id) in members or int(search_user_id) in ban_members:

                await bot.answer_callback_query(callback_query.id, text="Пользователь был успешно разблокирован! ✔️")

                # Удаление search_user_id из ban_members
                ban_members.remove(int(search_user_id))

                # Обновление документа в базе данных
                await contests_collection.update_one({"_id": int(contest_id)}, {
                    "$set": {"ban_members": ban_members}})

                message_id = change_message_id[-1]

                username = await get_username(search_user_id)
                if username:
                    username = username.replace("_", "&#95;")

                # Формирование сообщения с данными пользователя
                result_message = f"<b>🧶Пользователь:</b> <code>{search_user_id}</code>\n" \
                                 f"<b>🪐 Юзернейм:</b> @{username}\n" \
                                 f"<b>❎ Состояние:</b> <code>Разблокирован!</code>"

                keyboard = types.InlineKeyboardMarkup()
                back_search = types.InlineKeyboardButton(text='Назад 🧿', callback_data='contest_check')
                input_id = types.InlineKeyboardButton(text='Искать ещё 🔎',
                                                      callback_data=f'contest_search_profile_{contest_id}')
                keyboard.row(input_id)
                keyboard.row(back_search)

                reply = await bot.edit_message_text(result_message, callback_query.message.chat.id, message_id,
                                                    parse_mode="HTML",
                                                    reply_markup=keyboard)

                # Сохранение ID сообщения в глобальную переменную
                change_message_id.append(reply.message_id)
            else:
                int_digit = await bot.send_message(callback_query.message.chat.id, "*❌ Пользователь не обнаружен.*",
                                                   parse_mode="Markdown")
                await asyncio.sleep(4)
                await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=int_digit.message_id)
        else:
            int_digit = await bot.send_message(callback_query.message.chat.id, "*❌ Конкурс не найден.*",
                                               parse_mode="Markdown")
            await asyncio.sleep(4)
            await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=int_digit.message_id)

    elif button_text.startswith('kick_profile'):

        parts = button_text.split('_')
        search_user_id = parts[2]
        contest_id = parts[3]

        # Поиск конкурса по айди
        contest = await contests_collection.find_one({"_id": int(contest_id)})
        user_data = await user_collections.find_one({"_id": int(search_user_id)})
        participation = user_data.get("participation")

        if contest:
            members = contest.get("members")
            join_date = contest.get("join_date")

            if int(search_user_id) in members:
                user_index = members.index(int(search_user_id))

                await bot.answer_callback_query(callback_query.id, text="Пользователь был успешно исключен! ✔️")

                # Удаление search_user_id из members
                members.remove(int(search_user_id))

                # Удаление соответствующего элемента из join_date
                join_date.pop(user_index)

                if participation > 0:
                    # Уменьшение участий на 1
                    participation_result = int(participation) - 1

                    # Обновление параметра participation в документе пользователя
                    await user_collections.update_one({"_id": int(search_user_id)},
                                                          {"$set": {"participation": participation_result}})

                # Обновление документа в базе данных
                await contests_collection.update_one({"_id": int(contest_id)}, {
                    "$set": {"members": members, "join_date": join_date}})

                message_id = change_message_id[-1]

                username = await get_username(search_user_id)
                if username:
                    username = username.replace("_", "&#95;")

                # Формирование сообщения с данными пользователя
                result_message = f"<b>🧶Пользователь:</b> <code>{search_user_id}</code>\n" \
                                 f"<b>🪐 Юзернейм:</b> @{username}\n" \
                                 f"<b>‼️ Состояние:</b> <code>Исключен!</code>"

                keyboard = types.InlineKeyboardMarkup()
                back_search = types.InlineKeyboardButton(text='Назад 🧿', callback_data='contest_check')
                input_id = types.InlineKeyboardButton(text='Искать ещё 🔎',
                                                      callback_data=f'contest_search_profile_{contest_id}')
                keyboard.row(input_id)
                keyboard.row(back_search)

                reply = await bot.edit_message_text(result_message, callback_query.message.chat.id, message_id,
                                                    parse_mode="HTML",
                                                    reply_markup=keyboard)

                # Сохранение ID сообщения в глобальную переменную
                change_message_id.append(reply.message_id)
            else:
                int_digit = await bot.send_message(callback_query.message.chat.id, "*❌ Пользователь не обнаружен.*",
                                                   parse_mode="Markdown")
                await asyncio.sleep(4)
                await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=int_digit.message_id)
        else:
            int_digit = await bot.send_message(callback_query.message.chat.id, "*❌ Конкурс не найден.*",
                                               parse_mode="Markdown")
            await asyncio.sleep(4)
            await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=int_digit.message_id)

    elif button_text.startswith('promo'):

        parts = button_text.split('_')
        promo = str(parts[1])
        action = parts[2]
        current_page = int(parts[3])
        message_id = promo_message_id[-1]

        if action == 'prev':
            current_page -= 1

        elif action == 'next':
            current_page += 1

        # Поиск конкурса по айди
        promo_code = await promo_collection.find_one({"_id": promo})

        members = promo_code.get("active_members")
        result_message = f"<b>📋 Список пользователей для промокода</b> <code>{promo}</code>:\n\n" \
                         f"                                   <b>Страница {current_page}</b>\n\n"

        keyboard = types.InlineKeyboardMarkup()

        # Количество участников на одной странице
        per_page = 25
        start_index = (current_page - 1) * per_page
        end_index = current_page * per_page
        page_members = members[start_index:end_index] if start_index < len(members) else []
        for idx, user_id in enumerate(page_members, start=start_index + 1):
            username = await get_username(user_id)
            if username:
                username = username.replace("_", "&#95;")
            result_message += f"<b>{idx}.</b> @{username} <b>(</b><code>{user_id}</code><b>)</b>\n"

        # Кнопки перелистывания
        prev_button = types.InlineKeyboardButton(text='◀️ Назад', callback_data=f'promo_{promo}_prev_{current_page}')
        next_button = types.InlineKeyboardButton(text='Вперед ▶️', callback_data=f'promo_{promo}_next_{current_page}')
        back = types.InlineKeyboardButton(text='Выполенено ✅', callback_data='done')

        # Add both buttons if there are both previous and next pages
        if current_page > 1 and end_index < len(members):
            keyboard.row(prev_button, next_button)
        # Add only the previous button if there are no more pages
        elif current_page > 1:
            keyboard.row(prev_button)
        # Add only the next button if this is the first page
        elif end_index < len(members):
            keyboard.row(next_button)
        keyboard.row(back)
        uses = promo_code.get("uses")
        result_message += f"\n\n<b>🧪 Осталось активаций:</b> <code>{uses}</code>"

        await bot.edit_message_text(result_message, callback_query.message.chat.id, message_id, parse_mode="HTML",
                                    reply_markup=keyboard)

    elif button_text == 'buy_key':
        result_message = "*💲 Цена ключа на одну активацию* `1$`\n" \
                         "*🔑 Воспользуйтесь командой* /buy_key *для покупки ключа.*"
        await bot.edit_message_text(result_message, callback_query.message.chat.id, callback_query.message.message_id, parse_mode="Markdown",
                                    reply_markup=keyboard)

    elif button_text == 'done':

        await bot.answer_callback_query(callback_query.id, text="Задача была выполнена успешно! ✔️")

        await bot.delete_message(callback_query.message.chat.id,
                                 callback_query.message.message_id)  # Удаление сообщения

async def perform_contest_draw(contest_id):
    # Получение данных о конкурсе
    contest = await contests_collection.find_one({"_id": int(contest_id)})
    winners = contest.get("winners")
    members = contest.get("members")
    owner_id = contest.get("owner_id")

    if len(members) < winners:
        winners_enough_message = "*❌ Участников меньше, чем заданное число победителей, дата конкурса была изменена.*\n\n" \
                                 f"*🧊 Айди конкурса:* `{contest_id}`\n" \
                                 f"*🥇 Число победителей:* `{winners}`\n" \
                                 f"*👤 Текущее количество участников:* `{len(members)}`"
        await bot.send_message(owner_id, winners_enough_message, parse_mode="Markdown")
        # Update the flag to True since the message has been sent
        await contests_collection.update_one({"_id": int(contest_id)},
                                             {"$set": {"end_date": "Дата не указана. 🚫"}})
        return  # Remove this 'return' statement

    # Случайный выбор победителей
    random_winners = random.sample(members, winners)
    result_message = f"<b>🏆 Конкурс</b> <code>{contest_id}</code> <b>был успешно завершен!</b>\n\n"

    if winners > 1:
        result_message += "<b>🎖️ Победители:</b>\n"
        share_message = f"** - Конкурс бот 🎭**\n\n**🎖️ Победители конкурса** `{contest_id}`:\n"

        for idx, winner in enumerate(random_winners, start=1):
            user_id = winner
            username = await get_username(user_id)
            if username:
                formatted_username = username.replace("_", "&#95;")
            else:
                formatted_username = "None"

            result_message += f"<b>{idx}.</b> @{formatted_username} <b>—</b> <code>{winner}</code>\n"
            share_message += f"**{idx}.** @{username} — `{user_id}`\n"

            # Увеличение счетчика побед пользователя
            user_data = await user_collections.find_one({"_id": user_id})

            if user_data:
                wins = user_data.get("wins", 0)
                wins += 1
                await update_status(user_id)
                await user_collections.update_one({"_id": user_id}, {"$set": {"wins": wins}}, upsert=True)
                # Отправка личного сообщения пользователю о победе
                winner_message = f"*🥇 Поздравляем! Вы стали одним из победителей конкурса* `{contest_id}`*!*"
                await bot.send_message(user_id, winner_message, parse_mode="Markdown")
            await update_win_contest_members(contest_id, user_id)

        if contest:
            ended = "True"
            await contests_collection.update_one({"_id": int(contest_id)}, {"$set": {"ended": ended}}, upsert=True)
    else:
        result_message += "<b>🎖️ Победитель:</b>\n"

        user_id = random_winners[0]

        username = await get_username(user_id)
        if username:
            formatted_username = username.replace("_", "&#95;")
        else:
            formatted_username = "None"

        result_message += f"@{formatted_username} <b>—</b> <code>{user_id}</code>"
        share_message = f"** - Конкурс бот 🎭**\n\n**🎖️ Победитель конкурса** `{contest_id}`:\n" \
                        f"@{username} — `{user_id}`"

        # Увеличение счетчика побед пользователя
        user_data = await user_collections.find_one({"_id": user_id})

        if user_data:
            wins = user_data.get("wins", 0)
            wins += 1
            await update_status(user_id)
            await user_collections.update_one({"_id": user_id}, {"$set": {"wins": wins}}, upsert=True)
            # Отправка личного сообщения пользователю о победе
            winner_message = f"*🥇 Поздравляем! Вы стали победителем конкурса* `{contest_id}`*!*"
            await bot.send_message(user_id, winner_message, parse_mode="Markdown")
        if contest:
            ended = "True"
            await contests_collection.update_one({"_id": int(contest_id)}, {"$set": {"ended": ended}}, upsert=True)
        await update_win_contest_members(contest_id, user_id)

    markup = types.InlineKeyboardMarkup()
    share_button = types.InlineKeyboardButton(text='Поделиться 🫴', switch_inline_query=f'{share_message}')
    markup.add(share_button)

    reply = await bot.send_message(owner_id, result_message, parse_mode="HTML",
                                        reply_markup=markup)

    # Сохранение ID сообщения в глобальную переменную
    change_message_id.append(reply.message_id)

timezone = pytz.timezone('Europe/Kiev')

async def check_and_perform_contest_draw():
    while True:
        # Convert the current time to your specified timezone
        current_time = datetime.now(timezone)

        # Получение всех конкурсов
        contests = await contests_collection.find().to_list(length=None)

        for contest in contests:
            ended = contest.get("ended")
            contest_id = contest.get("_id")
            end_date_str = contest.get("end_date")

            if ended == "Дата не указана. 🚫":
                pass
            else:
                if ended == "True":
                    pass
                else:
                    try:
                        # Преобразование времени окончания в объект datetime с учетом часового пояса
                        end_date = timezone.localize(datetime.strptime(str(end_date_str), "%d.%m.%Y %H:%M"))
                        # Сравнение текущего времени с временем окончания
                        if current_time >= end_date:
                            await perform_contest_draw(contest_id)
                    except ValueError:
                        pass

        # Wait for 1 minute before checking again
        await asyncio.sleep(10)

# log
logging.basicConfig(level=logging.INFO)

# # Команда для покупки ключа
# @dp.message_handler(commands=['buy_key'])
# async def buy_key(message: types.Message):
#     # Генерация ключа, определение его цены и описания
#     key = generate_key()
#     price = 1  # Укажите здесь цену ключа
#     description = f"🔑 Оплата ключа."
#
#     # Отправляем запрос на оплату
#     await bot.send_invoice(
#         chat_id=message.chat.id,
#         title="Оформление заказа 🔰",
#         description=description,
#         payload=key,  # Отправляем ключ в payload, чтобы потом узнать, какой ключ оплатили
#         provider_token=PAYMENTS_TOKEN,
#         currency='USD',  # Валюта (в данном случае российский рубль)
#         prices=[
#             types.LabeledPrice(label='Ключ доступа', amount=price * 100)  # Цена указывается в копейках
#         ],
#         start_parameter='buy_key',  # Уникальный параметр для оплаты
#         need_name=True,
#         need_phone_number=False,
#         need_email=True,
#         need_shipping_address=False,  # Зависит от того, требуется ли доставка товара
#     )
#
# # Обработчик успешной оплаты
# @dp.message_handler(content_types=types.ContentType.SUCCESSFUL_PAYMENT)
# async def process_successful_payment(message: types.Message):
#     # Получаем ключ и прочие данные
#     key = message.successful_payment.invoice_payload
#     uses = 1
#     user_id = message.from_user.id
#
#     # Получаем email пользователя, если он был введен
#     if message.successful_payment.order_info and 'email' in message.successful_payment.order_info:
#         email = message.successful_payment.order_info['email']
#     else:
#         email = "Email не был указан."
#
#     # Вызываем функцию buy_key с необходимыми аргументами
#     await buy_key(key, uses, email, user_id)
#
#     # Выполняем какие-либо действия с ключом и email
#     await message.answer(f"*✅ Покупка была успешна! Вы получили ключ* `{key}`.\n"
#                          f"*🔑 Количество активаций:* {uses}")
#
# # Обработчик предварительной проверки
# @dp.pre_checkout_query_handler(lambda query: True)
# async def process_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
#     # Отправляем ответ о успешной предварительной проверке
#     await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

async def main():
    # Запуск бота
    await dp.start_polling()

# Создание и запуск асинхронного цикла для функции проверки и выполнения розыгрыша конкурсов
contest_draw_loop = asyncio.get_event_loop()
contest_draw_task = contest_draw_loop.create_task(check_and_perform_contest_draw())

# Запуск основного асинхронного цикла для работы бота
bot_loop = asyncio.get_event_loop()
bot_task = bot_loop.create_task(main())

# Запуск обоих задач
loop = asyncio.get_event_loop()

tasks = asyncio.gather(contest_draw_task, bot_task)
loop.run_until_complete(tasks)
