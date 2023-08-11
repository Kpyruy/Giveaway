from datetime import datetime
import asyncio
import aiogram
import random
import re
import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ParseMode, ChatMember, CallbackQuery
from aiogram.types.message import ContentType
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.exceptions import TelegramAPIError
import aiogram.utils.markdown as md
from aiogram.utils import executor
from configparser import ConfigParser
from pymongo import MongoClient
import motor.motor_asyncio
import json
import logging
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher.handler import CancelHandler, current_handler
import zipfile
import os
import aiohttp

logging.basicConfig(
    level=logging.DEBUG,  # Set the logging level to DEBUG to log everything
    filename='private/bot.log',   # Log everything to a file named 'bot.log'
    filemode='w',         # 'w' will overwrite the file each time the script runs, use 'a' to append instead
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Compass - 3GuIBMmZRoJlG3OE
cluster = motor.motor_asyncio.AsyncIOMotorClient("mongodb+srv://Admin:T8Lylcpso9jNs5Yw@cluster0.1t9opzs.mongodb.net/RandomBot?retryWrites=true&w=majority")
user_collections = cluster.RandomBot.user
key_collection = cluster.RandomBot.key
contests_collection = cluster.RandomBot.contests
promo_collection = cluster.RandomBot.promo
test_collection = cluster.RandomBot.test
game_collection = cluster.RandomBot.game

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
    welcome = State()

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
        "draws": 0,
        "game_participation": 0,
        "game_wins": 0,
        "status": "Новичок 🆕",
        "keys": 0,
        "ban_members": []
    }
    user_collections.insert_one(user_data)

# Get the bot's username from the bot instance
async def get_bot_username() -> str:
    bot_info = await bot.get_me()
    return bot_info.username

# Now you can generate the start link using the bot's username
async def generate_start_link(contest_id):
    bot_username = await get_bot_username()
    start_link = f"t.me/{bot_username}?start={contest_id}"
    return start_link

async def generate_room_link(room_id):
    bot_username = await get_bot_username()
    play_link = f"t.me/{bot_username}?play={room_id}"
    return play_link

def generate_room_id(length=16):
    characters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    room = ''.join(random.choice(characters) for _ in range(length))
    return room

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

async def create_gameroom(room_id, user_id, type, formate, rounds, create_date, room_link):
    await game_collection.insert_one({
        "_id": room_id,
        "owner_id": int(user_id),
        "type": str(type),
        "format": str(formate),
        "rounds": rounds,
        "members": [],
        "winners": [],
        "draw": " ",
        "create_date": str(create_date),
        "room_link": room_link,
        "room_status": "wait",
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

async def add_key_to_data(key, uses, email, user_id):
    key_data = {
        "_id": key,
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

async def get_ban_username(banned_user_id):
    # Use the get_chat method to get the user's information
    user = await bot.get_chat(banned_user_id)

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
            ended = contest.get("ended")

            if ended == "True":
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
            else:
                continue

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

async def show_user_permanent(callback_query, user_id, current_page):
    # Retrieve contests where the user with the specified user_id was a member
    user_history = await user_collections.find({"_id": user_id}).to_list(length=None)

    # Check if there are any results
    if user_history:
        user_data = user_history[0]  # Get the first dictionary from the list
        banned_members = user_data.get("ban_members")

        if banned_members:
            # Your logic to display user history based on the current_page
            per_page = 20
            start_index = (current_page - 1) * per_page
            end_index = current_page * per_page
            page_history = banned_members[start_index:end_index] if start_index < len(banned_members) else []
            all_pages = len(banned_members) // per_page

            if len(banned_members) % per_page != 0:  # Check if there are any remaining items for an extra page
                all_pages += 1

            # Create the message containing the user history for the current page
            result_message = f"<b>♾️ Черный список — Страница</b> <code>{current_page}</code> <b>из</b> <code>{all_pages}</code>:\n\n"
            for idx, banned_member in enumerate(page_history, start=start_index + 1):
                username = await get_ban_username(banned_member)
                if username:
                    username = username.replace("_", "&#95;")
                result_message += f"{idx}. @{username} (<code>{banned_member}</code>)\n"
            result_message += "\n<b>📛 Чтобы добавить/удалить пользователя</b> /permanent <code>{id}</code>"
            # Create the inline keyboard with pagination buttons
            keyboard = types.InlineKeyboardMarkup()
            prev_button = types.InlineKeyboardButton(text='◀️ Предыдущая',
                                                     callback_data=f'permanent_{user_id}_prev_{current_page}')
            next_button = types.InlineKeyboardButton(text='Следущая ▶️',
                                                     callback_data=f'permanent_{user_id}_next_{current_page}')

            if current_page > 1 and end_index < all_pages:
                keyboard.row(prev_button, next_button)
            elif current_page > 1:
                keyboard.row(prev_button)
            elif current_page < all_pages:
                keyboard.row(next_button)
            back = types.InlineKeyboardButton(text='Выполнено ✅', callback_data='done')
            keyboard.row(back)

            # Send or edit the message with pagination
            await bot.edit_message_text(result_message, callback_query.message.chat.id,
                                                callback_query.message.message_id, parse_mode="HTML",
                                                reply_markup=keyboard)
    else:
        result_message = "*Заблокированных пользователей нет. 🚫*"
        keyboard = types.InlineKeyboardMarkup()
        back = types.InlineKeyboardButton(text='Выполнено ✅', callback_data='done')
        keyboard.row(back)

        # Send or edit the message with pagination
        await bot.edit_message_text(result_message, callback_query.message.chat.id,
                                            callback_query.message.message_id, parse_mode="Markdown",
                                            reply_markup=keyboard)

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
    promo_list_update = types.InlineKeyboardButton(text='Обновить 🌀',
                                                   callback_data=f'list_update_{promo}_{current_page}')
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
    keyboard.row(promo_list_update)
    keyboard.row(back)
    uses = promo_code.get("uses")
    result_message += f"\n\n<b>🧪 Осталось активаций:</b> <code>{uses}</code>"
    # Send the formatted message with the keyboard
    reply = await bot.send_message(chat_id, result_message,
                                   parse_mode="HTML",
                                   reply_markup=keyboard)

    # Сохранение ID сообщения в глобальную переменную
    promo_message_id.append(reply.message_id)

async def update_promo_members(promo, current_page, chat_id, message_id):
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
    promo_list_update = types.InlineKeyboardButton(text='Обновить 🌀',
                                                   callback_data=f'list_update_{promo}_{current_page}')
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
    keyboard.row(promo_list_update)
    keyboard.row(back)
    uses = promo_code.get("uses")
    result_message += f"\n\n<b>🧪 Осталось активаций:</b> <code>{uses}</code>"
    # Send the formatted message with the keyboard
    # Send or edit the message with pagination
    await bot.edit_message_text(result_message, chat_id,
                                message_id, parse_mode="HTML",
                                reply_markup=keyboard)

# Add this at the beginning of your script to enable logging
logging.basicConfig(level=logging.INFO)

async def handle_promo_code(promo_code: str, user_id: int, chat_id):
    try:
        promo = await promo_collection.find_one({"_id": promo_code})

        if promo:
            active_members = promo.get("active_members", [])

            if user_id in active_members:
                logging.info(f"{chat_id} активирован")
                await bot.send_message(chat_id, "*❌ Вы уже активировали данный промокод.*", parse_mode="Markdown")
            else:
                uses = promo.get("uses", 0)
                if uses > 0:
                    await activate_promo_code(promo_code, user_id, chat_id)
                else:
                    logging.info(f"{chat_id} не действителен")
                    await bot.send_message(chat_id, "*❌ Промокод больше не действителен.*", parse_mode="Markdown")
        else:
            logging.info(f"{chat_id} не найден")
            await bot.send_message(chat_id, "*Промокод не найден. ❌*", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in handle_promo_code: {str(e)}")
        await bot.send_message(chat_id, "*❌ Произошла ошибка при обработке промокода. Попробуйте позже.*", parse_mode="Markdown")

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

async def activate_promo_code(promo_code: str, user_id: int, chat_id: int):
    try:

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
        logging.info(f"{chat_id} успешно")
        await bot.send_message(chat_id, f"*Промокод* `{promo_code}` *активирован. ✅*", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in handle_promo_code: {str(e)}")
        await bot.send_message(chat_id, "*❌ Произошла ошибка при обработке промокода. Попробуйте позже.*",
                               parse_mode="Markdown")

def generate_promo_code():
    promo_length = 8  # Длина промокода
    allowed_characters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return ''.join(random.choices(allowed_characters, k=promo_length))

async def send_profile(username, user_id, chat_id):
    # Поиск данных о пользователе в базе данных
    user_data = await user_collections.find_one({"_id": user_id})

    wins = user_data.get("wins", 0)
    participation = user_data.get("participation", 0)

    # Вычисление процента побед
    win_percentage = (wins / participation) * 100 if participation > 0 else 0
    creation_date = user_data.get("creation_date", "")
    status = user_data.get("status", "")

    # Создание и отправка сообщения с кнопками
    profile = f'*🍹 Профиль пользователя* `{username}`:\n\n' \
              f'*🍧 Статус:* `{status}`\n\n' \
              f'*🍀 Участие в конкурсах:* `{participation}`\n' \
              f'*🏅 Победы в конкурсах:* `{wins}`\n' \
              f'*🏆 Процент побед:* `{win_percentage:.2f}%`\n\n' \
              f'*📅 Дата регистрации:* `{creation_date}`'
    keyboard = types.InlineKeyboardMarkup()
    game_profile = types.InlineKeyboardButton(text='Игровой профиль 🎮', callback_data=f'game_profile_{user_id}_buttons')
    history = types.InlineKeyboardButton(text='История участий 📔', callback_data=f'history_{user_id}_None_1')
    active_history_drawings = types.InlineKeyboardButton(text='Активные участия 🦪', callback_data=f'active_{user_id}_None_1')
    id_check = types.InlineKeyboardButton(text='Поиск пользователя 🥏', callback_data='id_check')
    done = types.InlineKeyboardButton(text='Готово ✅', callback_data='done')
    keyboard.add(game_profile)
    keyboard.add(history, active_history_drawings)
    keyboard.add(id_check)
    keyboard.add(done)

    await bot.send_message(chat_id, text=profile, parse_mode="Markdown",
                                   reply_markup=keyboard)

async def show_profile(username, user_id, chat_id, message_id):
    # Поиск данных о пользователе в базе данных
    user_data = await user_collections.find_one({"_id": user_id})

    wins = user_data.get("wins", 0)
    participation = user_data.get("participation", 0)

    # Вычисление процента побед
    win_percentage = (wins / participation) * 100 if participation > 0 else 0
    creation_date = user_data.get("creation_date", "")
    status = user_data.get("status", "")

    # Создание и отправка сообщения с кнопками
    profile = f'*🍹 Профиль пользователя* `{username}`:\n\n' \
              f'*🍧 Статус:* `{status}`\n\n' \
              f'*🍀 Участие в конкурсах:* `{participation}`\n' \
              f'*🏅 Победы в конкурсах:* `{wins}`\n' \
              f'*🏆 Процент побед:* `{win_percentage:.2f}%`\n\n' \
              f'*📅 Дата регистрации:* `{creation_date}`'
    keyboard = types.InlineKeyboardMarkup()
    game_profile = types.InlineKeyboardButton(text='Игровой профиль 🎮', callback_data=f'game_profile_{user_id}_buttons')
    history = types.InlineKeyboardButton(text='История участий 📔', callback_data=f'history_{user_id}_None_1')
    active_history_drawings = types.InlineKeyboardButton(text='Активные участия 🦪', callback_data=f'active_{user_id}_None_1')
    id_check = types.InlineKeyboardButton(text='Поиск пользователя 🥏', callback_data='id_check')
    done = types.InlineKeyboardButton(text='Готово ✅', callback_data='done')
    keyboard.add(game_profile)
    keyboard.add(history, active_history_drawings)
    keyboard.add(id_check)
    keyboard.add(done)

    # Send or edit the message with pagination
    reply = await bot.edit_message_text(profile, chat_id,
                                message_id, parse_mode="Markdown",
                                reply_markup=keyboard)
    # Сохранение ID сообщения в глобальную переменную
    profile_messages.append(reply.message_id)

async def show_user_drawings(callback_query, user_id, current_page):
    # Retrieve contests where the user with the specified user_id was a member
    user_history = await contests_collection.find({"members": user_id}).to_list(length=None)

    # Check if there are any active contests for the user
    active_contests_exist = any(contest.get("ended", "True") == "False" for contest in user_history)

    if user_history and active_contests_exist:
        # Your logic to display user history based on the current_page
        per_page = 3
        start_index = (current_page - 1) * per_page
        end_index = current_page * per_page
        page_history = user_history[start_index:end_index] if start_index < len(user_history) else []
        all_pages = len(user_history) // per_page

        if all_pages == 0:
            all_pages = 1
        else:
            pass
        # Create the message containing the user history for the current page
        result_message = f"*🦪 Участие в конкурсах - Страница* `{current_page}` из `{all_pages}`:\n\n"
        for idx, contest in enumerate(page_history, start=start_index + 1):
            # Extract relevant information about the contest, e.g., its title, end date, etc.
            contest_name = contest.get("contest_name")
            contest_id = contest.get("_id")
            contest_end_date = contest.get("end_date")
            contest_members = contest.get("members")
            ended = contest.get("ended")
            if ended == "True":
                pass
            else:
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
        prev_button = types.InlineKeyboardButton(text='◀️ Предыдущая', callback_data=f'active_{user_id}_prev_{current_page}')
        next_button = types.InlineKeyboardButton(text='Следущая ▶️', callback_data=f'active_{user_id}_next_{current_page}')

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
        result_message = "*🦪 Сейчас вы не участвуете в каких-либо конкурсах.*"
        keyboard = types.InlineKeyboardMarkup()
        back = types.InlineKeyboardButton(text='Назад 🥏', callback_data='profile_edit')
        keyboard.row(back)

        # Send or edit the message with pagination
        reply = await bot.edit_message_text(result_message, callback_query.message.chat.id,
                                            callback_query.message.message_id, parse_mode="Markdown", reply_markup=keyboard)
        profile_messages.append(reply.message_id)

def get_participation_word(count):
    if count % 10 == 1 and count % 100 != 11:
        return "участие"
    elif 2 <= count % 10 <= 4 and (count % 100 < 10 or count % 100 >= 20):
        return "участия"
    else:
        return "участий"

def get_wins_word(count):
    if count % 10 == 1 and count % 100 != 11:
        return "победа"
    elif 2 <= count % 10 <= 4 and (count % 100 < 10 or count % 100 >= 20):
        return "победы"
    else:
        return "побед"

async def get_chat_administrators(chat_id):
    administrators = await bot.get_chat_administrators(chat_id)
    admins_ids = [admin.user.id for admin in administrators]
    return admins_ids

async def get_chat_members_count(chat_id):
    count = await bot.get_chat_members_count(chat_id)
    return count

async def create_and_send_archive(chat_id):
    # Create a zip archive of the 'data' folder
    archive_filename = 'data_archive.zip'
    with zipfile.ZipFile(archive_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for foldername, subfolders, filenames in os.walk('data'):
            for filename in filenames:
                file_path = os.path.join(foldername, filename)
                zipf.write(file_path, os.path.relpath(file_path, 'data'))

    # Prepare the form data for the POST request
    form = aiohttp.FormData()
    form.add_field('chat_id', str(chat_id))
    form.add_field('document', open(archive_filename, 'rb'))

    # Send the archive file to the chat
    async with aiohttp.ClientSession() as session:
        async with session.post(f'https://api.telegram.org/bot{BOT_TOKEN}/sendDocument', data=form) as response:
            if response.status == 200:
                print('Archive sent successfully')

    # Delete the archive file after sending
    os.remove(archive_filename)

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

# Установка списка команд бота
async def set_bot_commands():
    commands = [
        types.BotCommand(command="/start", description="-  Открыть основное меню 🫥"),
        types.BotCommand(command="/search", description="-  Поиск по айди 🔎"),
        types.BotCommand(command="/profile", description="-  Открыть свой профиль 👤"),
        types.BotCommand(command="/promo", description="-  Воспользоваться промокодом 🧪"),
        types.BotCommand(command="/wins", description="-  Топ пользователей по победам в конкурсах 🥇"),
        types.BotCommand(command="/participations", description="-  Топ пользователей по участиям в конкурсах 🍀"),
        types.BotCommand(command="/create", description="-  Создать игровую комнату. 🎮"),
        types.BotCommand(command="/contest", description="-  Конкурс меню 🎖"),
        types.BotCommand(command="/generate", description="-  Получить ключ доступа 🔑"),
        types.BotCommand(command="/permanent", description="-  Список заблокированный пользователей 🚫"),
        types.BotCommand(command="/help", description="-  Показать навигацию по боту❔")
        # Добавьте остальные команды, если есть
    ]
    await bot.set_my_commands(commands)

# async def test():
#     # Пример списка winners с несколькими победителями
#     winners = [{1738263685, 826511051}]
#
#     winner_team = winners[0]  # это ваш кортеж
#
#     if len(winner_team) == 1:
#         username = await get_username(winner_user_id)
#         if username:
#             username = username.replace("_", "&#95;")
#             winner_message = f"<b>🥇 Поздравляю, пользователь</b> @{username} <code>{winner_user_id1}</code> <b>победил, отличная была игра!</b>"
#         print(winner_message)
#     # Если у нас несколько победителей
#     else:
#         winners_usernames = []
#         for winner_team in winners:
#             winner_usernames = []
#             for user_id in winner_team:
#                 username = await get_username(user_id)
#                 if username:
#                     username = username.replace("_", "&#95;")
#                     winner_usernames.append(f"{username} - {user_id}")
#
#             winners_usernames.append(", ".join(winner_usernames))
#         winners_message = f"<b>🥇 Поздравляю команду с победой:</b>\n<code>{', '.join(winners_usernames)}</code> <b>\n👤 Данные в профиле были обновлены!</b>"
#         print(winners_message)
# # Вызываем функцию test() в самом начале кода
# asyncio.run(test())

@dp.message_handler(commands=['create'])
async def create_room(message: types.Message):
    if message.chat.type != 'private':
        await bot.send_message(message.chat.id, "*❌ Команда /create доступна только в личных сообщениях.*", parse_mode="Markdown")
        return

    user_id = message.from_user.id
    user_data = await game_collection.find_one({"owner_id": user_id, "ended": "False"})

    if user_data:
        keyboard = types.InlineKeyboardMarkup()
        check_rooms = types.InlineKeyboardButton(text='🔎 Мои комнаты', callback_data='check_rooms')
        keyboard.row(check_rooms)

        await message.reply(
                "*🖥️ У вас уже создана игровая комната!*\n\n*✨ Воспользуйтесь кнопкой для просмотра активных комнат:*",
                parse_mode="Markdown", reply_markup=keyboard)

    else:
        keyboard = types.InlineKeyboardMarkup()
        create_room = types.InlineKeyboardButton(text='🕹️ Создать', callback_data='create_room')
        check_rooms = types.InlineKeyboardButton(text='🔎 Мои комнаты', callback_data=f'check_rooms')
        keyboard.row(check_rooms)
        keyboard.row(create_room)

        await message.reply(
                "*🖥️ Панель создания игровых комнат!*\n\n*✨ Воспользуйтесь кнопками для управления комнатами или их создания:*",
                parse_mode="Markdown", reply_markup=keyboard)

@dp.message_handler(commands=['play'])
async def play_command(message: types.Message):

    # Check if there are any arguments after the command
    if message.chat.type != 'private':
        await bot.send_message(message.chat.id, "*❌ Команда /play доступна только в личных сообщениях.*", parse_mode="Markdown")
        return

    # Get the game_id from the arguments
    game_id = message.get_args()

    # Check if the game with the specified game_id exists in the database
    game = await game_collection.find_one({"_id": game_id})
    if game is None:
        await message.reply("*❌ Комната не найдена. Пожалуйста, используйте правильный ID.*", parse_mode="Markdown")
        return

    # Check if the format of the game is either 2vs2 or 1vs1
    game_format = game.get("format", "")
    if game_format not in ["2vs2", "1vs1"]:
        await message.reply("`Invalid game format. The game format should be either 2vs2 or 1vs1.`\n\n"
                            "*🛑 Отправьте это сообщение с ошибкой разработичку бота!*", parse_mode="Markdown")
        return

    # Add the player to the members array of the game
    user_id = message.from_user.id
    if user_id in game.get("members", []):
        keyboard = types.InlineKeyboardMarkup()
        info_room = types.InlineKeyboardButton(text='Открыть 🖥️', callback_data=f'info_room_{game_id}')
        keyboard.row(info_room)
        await message.reply("*❌ Вы уже добавлены в эту комнату.*", parse_mode="Markdown", reply_markup=keyboard)
        return

    # Check if the game already has the maximum number of players based on its format
    max_players = 4 if game_format == "2vs2" else 2
    current_players = len(game.get("members", []))
    if current_players == max_players:
        await message.reply("*🖥️ В комнате уже максимальное количество участников.*", parse_mode="Markdown")
        return

    game["members"] = game.get("members", []) + [user_id]
    await user_collections.update_one({"_id": user_id}, {"$inc": {"game_participation": 1}})

    # Save the updated game back to the database
    await game_collection.replace_one({"_id": game_id}, game)
    keyboard = types.InlineKeyboardMarkup()
    info_room = types.InlineKeyboardButton(text='Открыть 🖥️', callback_data=f'info_room_{game_id}')
    keyboard.row(info_room)

    await message.reply(f"*☑️ Вы успешно были добавлены ID* `{game_id}`*!*\n\n*⌛ Ожидайте начала игры. Её запускает создатель комнаты.️.*", parse_mode="Markdown", reply_markup=keyboard)

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
            try:
                contest = await contests_collection.find_one({"_id": int(contest_id)})
            except Exception as e:
                # Код, если конкурс с указанной ссылкой не найден
                await message.reply("*К сожалению, такого конкурса не существует. ❌*",
                                                   parse_mode="Markdown")
                return
            if contest:
                ended = contest.get("ended")  # Проверяем значение параметра "ended", по умолчанию False
                owner_id = contest.get("owner_id")
                owner_data = await user_collections.find_one({"_id": int(owner_id)})

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
        # Код для существующего пользователя
        keyboard = types.InlineKeyboardMarkup()
        buy_key = types.InlineKeyboardButton(text='Купить ключ 🔑', callback_data='text_for_key')
        keyboard.row(buy_key)

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

    if user_data and (("status" in user_data and user_data["status"] in ["Тестер 🔰", "Админ 🚗", "Создатель 🎭"]) or int(user_data.get("keys", 0)) > 0):

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

    if user_data and (("status" in user_data and user_data["status"] in ["Тестер 🔰", "Админ 🚗", "Создатель 🎭"]) or int(
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

# Regular expression pattern to match links
link_pattern = r"https?://\S+"
link_regex = re.compile(link_pattern, re.IGNORECASE)

@dp.message_handler(state=CreateContestState.description)
async def process_description(message: types.Message, state: FSMContext):
    # Получение введенного пользователем описания конкурса
    contest_description = message.text

    # Удаление сообщения пользователя
    await bot.delete_message(message.chat.id, message.message_id)

    if not contest_description:
        contest_description = "Описание отсутствует 🚫"
    else:
        # Check if the description contains any links and remove them
        contest_description = link_regex.sub("", contest_description)

        # Check if the description contains any formatting (bold, italics, etc.) and remove them
        contest_description = contest_description.replace("_", "").replace("*", "").replace("`", "")

    # Check character count and notify the user if it exceeds the limit
    max_char_count = 1500
    excess_chars = len(contest_description) - max_char_count

    if excess_chars > 0:
        contest_description = contest_description[:max_char_count]
        excess_chars_message = f"\n\n*⚠️ Описание слишком большое и было сокращено на {excess_chars} символов.*"
        wrong_symbol = await bot.send_message(message.chat.id,
                                                   excess_chars_message, parse_mode="Markdown")
        await asyncio.sleep(4)
        await bot.delete_message(chat_id=message.chat.id, message_id=wrong_symbol.message_id)

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

    if user_data and (("status" in user_data and user_data["status"] in ["Тестер 🔰", "Админ 🚗", "Создатель 🎭"]) or int(user_data.get("keys", 0)) > 0):

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

        await show_profile(username, user_id, callback_query.message.chat.id, callback_query.message.message_id)
    else:
        # Обработка случая, когда данные о пользователе не найдены
        reply = await message.reply("☠️ Профиль пользователя не найден.")
        # Сохранение ID сообщения в глобальную переменную
        profile_messages.append(reply.message_id)

@dp.message_handler(state=MenuCategories.id_check)
async def process_search(message: types.Message, state: FSMContext):
    await bot.delete_message(message.chat.id, message.message_id)
    username = message.from_user.username
    if not message.text.isdigit():
        int_digit = await bot.send_message(message.chat.id, "*❌ Введите пожалуйста целочисленный идентификатор пользователя.*", parse_mode="Markdown")
        await asyncio.sleep(3)
        await bot.delete_message(chat_id=message.chat.id, message_id=int_digit.message_id)
        return

    prev_message_id = (await state.get_data()).get('prev_message_id')

    user_id = int(message.text)

    # Поиск конкурса по айди
    user = await user_collections.find_one({"_id": user_id})

    # Отправьте результаты поиска
    result = await bot.send_message(message.chat.id, "*🏯 Результаты поиска пользователя...*", parse_mode="Markdown")
    await asyncio.sleep(2)
    await bot.delete_message(chat_id=message.chat.id, message_id=result.message_id)

    if user:
        user_data = await user_collections.find_one({"_id": user_id})

        wins = user_data.get("wins", 0)
        participation = user_data.get("participation", 0)

        # Вычисление процента побед
        win_percentage = (wins / participation) * 100 if participation > 0 else 0
        creation_date = user_data.get("creation_date", "")
        status = user_data.get("status", "")

        # Создание и отправка сообщения с кнопками
        profile = f'*🍹 Профиль пользователя* `{username}`:\n\n' \
                  f'*🍧 Статус:* `{status}`\n\n' \
                  f'*🍀 Участие в конкурсах:* `{participation}`\n' \
                  f'*🏅 Победы в конкурсах:* `{wins}`\n' \
                  f'*🏆 Процент побед:* `{win_percentage:.2f}%`\n\n' \
                  f'*📅 Дата регистрации:* `{creation_date}`'
        keyboard = types.InlineKeyboardMarkup()
        game_profile = types.InlineKeyboardButton(text='Игровой профиль 🎮', callback_data=f'game_profile_{user_id}_check')
        id_check = types.InlineKeyboardButton(text='Поиск пользователя 🥏', callback_data='id_check')
        back = types.InlineKeyboardButton(text='Назад 🧿', callback_data='profile_edit')
        keyboard.add(game_profile)
        keyboard.add(id_check)
        keyboard.add(back)

        reply = await bot.edit_message_text(profile, message.chat.id, prev_message_id, parse_mode="Markdown",
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

    reply = await bot.edit_message_text(search_text, callback_query.message.chat.id, callback_query.message.message_id,
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
    # Check character count and notify the user if it exceeds the limit

    new_description = message.text

    max_char_count = 1500
    excess_chars = len(new_description) - max_char_count

    if excess_chars > 0:
        new_description = new_description[:max_char_count]
        excess_chars_message = f"\n\n*⚠️ Описание слишком большое и было сокращено на {excess_chars} символов.*"
        wrong_symbol = await bot.send_message(message.chat.id,
                                              excess_chars_message, parse_mode="Markdown")
        await asyncio.sleep(4)
        await bot.delete_message(chat_id=message.chat.id, message_id=wrong_symbol.message_id)

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

# Изменение welcome message
@dp.callback_query_handler(text='decline_welcome', state=MenuCategories.welcome)
async def decline_search_callback(callback_query: types.CallbackQuery, state: FSMContext):
    chat_id = (await state.get_data()).get('chat_id')
    user_id = callback_query.from_user.id
    await callback_query.answer()
    await state.finish()
    keyboard = types.InlineKeyboardMarkup()
    not_back = types.InlineKeyboardButton(text='Остаться ✏️',
                                      callback_data=f'welcome_{chat_id}_{user_id}')
    back = types.InlineKeyboardButton(text='Вернуться 📘',
                                      callback_data=f'group_{chat_id}_{user_id}_edit')
    keyboard.row(back, not_back)
    result_message = "*💬 Вы уверены что хотите отменить изменение приветственного сообщения?*"
    await bot.edit_message_text(result_message, callback_query.message.chat.id, callback_query.message.message_id,
                                            parse_mode="Markdown",
                                            reply_markup=keyboard)

@dp.message_handler(state=MenuCategories.welcome)
async def process_search(message: types.Message, state: FSMContext):
    await bot.delete_message(message.chat.id, message.message_id)

    chat_id = (await state.get_data()).get('chat_id')
    message_id = (await state.get_data()).get('message_id')
    await state.finish()

    user_id = message.from_user.id

    new_welcome = message.text

    await groups_collection.update_one({"_id": int(chat_id)},
                                      {"$set": {"welcome": new_welcome}})
    # Поиск конкурса по айди
    group = await groups_collection.find_one({"_id": int(chat_id)})

    welcome = group.get("welcome")
    result_message = "*✅ Новое приветственное сообщение:*\n" \
                     f"{welcome}"

    keyboard = types.InlineKeyboardMarkup()
    back = types.InlineKeyboardButton(text='Назад 📘', callback_data=f'group_{chat_id}_{user_id}')
    keyboard.row(back)

    await bot.edit_message_text(result_message, message.chat.id, message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith('welcome'))
async def search_callback(callback_query: types.CallbackQuery, state: FSMContext):
    call_user_id = callback_query.from_user.id

    button_text = callback_query.data
    parts = button_text.split('_')
    chat_id = int(parts[1])
    user_id = int(parts[2])

    if call_user_id != user_id:
        await bot.answer_callback_query(callback_query.id,
                                        text="❌ Увы, эта кнопка не является вашой, а так хотелось...")
        return

    welcome_text = "<b>⚙️ Для использования доступны параметры:</b>\n" \
                   "*текст* - <b>Жирный</b>\n" \
                   "_текст_ - <i>Курсив</i>\n" \
                   "{user_id} - айди пользователя который присоединился.\n\n" \
                   "<b>✏️ Введите новое сообщение:</b>" \

    keyboard = types.InlineKeyboardMarkup()
    input_id = types.InlineKeyboardButton(text='Отмена ❌', callback_data='decline_welcome')
    keyboard.row(input_id)

    await bot.edit_message_text(welcome_text, callback_query.message.chat.id, callback_query.message.message_id,
                                parse_mode="HTML", reply_markup=keyboard)
    await MenuCategories.welcome.set()
    await state.update_data(chat_id=chat_id)
    await state.update_data(message_id=callback_query.message.message_id)
    await state.update_data(prev_message_id=callback_query.message.message_id)

# Поиск через команду
@dp.message_handler(commands=['search'])
async def process_search_command(message: types.Message, state: FSMContext):
    args = message.get_args()
    send_user_id = message.from_user.id
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

        # Вычисление процента побед
        win_percentage = (wins / participation) * 100 if participation > 0 else 0
        creation_date = user_data.get("creation_date", "")
        status = user_data.get("status", "")

        # Создание и отправка сообщения с кнопками
        profile = f'*🍹 Профиль пользователя* `{user_id}`:\n\n' \
                  f'*🍧 Статус:* `{status}`\n\n' \
                  f'*🍀 Участие в конкурсах:* `{participation}`\n' \
                  f'*🏅 Победы в конкурсах:* `{wins}`\n' \
                  f'*🏆 Процент побед:* `{win_percentage:.2f}%`\n\n' \
                  f'*📅 Дата регистрации:* `{creation_date}`'
        keyboard = types.InlineKeyboardMarkup()
        game_profile = types.InlineKeyboardButton(text='Игровой профиль🎮', callback_data=f'game_profile_{user_id}_none_{send_user_id}')
        keyboard.add(game_profile)

        await bot.send_chat_action(message.chat.id, action="typing")
        await asyncio.sleep(0.5)
        await bot.send_message(message.chat.id, profile, parse_mode="Markdown", reply_markup=keyboard)
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
            username = message.from_user.username
            wins = user_data.get("wins", 0)
            participation = user_data.get("participation", 0)

            # Вычисление процента побед
            win_percentage = (wins / participation) * 100 if participation > 0 else 0
            creation_date = user_data.get("creation_date", "")
            status = user_data.get("status", "")

            # Создание и отправка сообщения с кнопками
            profile = f'*🍹 Профиль пользователя* `{username}`:\n\n' \
                      f'*🍧 Статус:* `{status}`\n\n' \
                      f'*🍀 Участие в конкурсах:* `{participation}`\n' \
                      f'*🏅 Победы в конкурсах:* `{wins}`\n' \
                      f'*🏆 Процент побед:* `{win_percentage:.2f}%`\n\n' \
                      f'*📅 Дата регистрации:* `{creation_date}`'
            keyboard = types.InlineKeyboardMarkup()
            history = types.InlineKeyboardButton(text='Игровой профиль 🎮', callback_data=f'game_profile_{user_id}_none')
            keyboard.add(history)

            reply = await message.reply(profile, parse_mode="Markdown", reply_markup=keyboard)
        else:
            reply = await message.reply("*☠️ Профиль пользователя не найден.*\n\n*👤 Напишите команду* /start *в личные сообщения боту, это создаст ваш профиль!*", parse_mode="Markdown")

        # Сохранение ID сообщения в глобальную переменную
        profile_messages.append(reply.message_id)

# # Перманнентная блокировака через команду
@dp.message_handler(commands=['permanent'])
async def process_search_command(message: types.Message, state: FSMContext):
    args = message.get_args()

    if message.chat.type != 'private':
        await bot.send_message(message.chat.id, "*❌ Команда /permanent доступна только в личных сообщениях.*", parse_mode="Markdown")
        return

    global permanent_message_id

    profile_user_id = message.from_user.id
    user_data = await user_collections.find_one({"_id": profile_user_id})  # Use profile_user_id instead of permanent_message_id
    ban_members = user_data.get("ban_members")

    if not args and not message.reply_to_message:
        if ban_members:
            # Your logic to display user history based on the current_page
            per_page = 20
            current_page = 1
            start_index = (current_page - 1) * per_page
            end_index = current_page * per_page
            page_history = ban_members[start_index:end_index] if start_index < len(ban_members) else []
            all_pages = len(ban_members) // per_page

            if len(ban_members) % per_page != 0:  # Check if there are any remaining items for an extra page
                all_pages += 1

            # Create the message containing the user history for the current page
            result_message = f"<b>♾️ Черный список — Страница</b> <code>{current_page}</code> <b>из</b> <code>{all_pages}</code>:\n\n"
            for idx, banned_member in enumerate(page_history, start=start_index + 1):
                username = await get_ban_username(banned_member)
                if username:
                    username = username.replace("_", "&#95;")
                result_message += f"{idx}. @{username} (<code>{banned_member}</code>)\n"
            result_message += "\n<b>📛 Чтобы добавить/удалить пользователя</b> /permanent <code>{id}</code>"
            # Create the inline keyboard with pagination buttons
            keyboard = types.InlineKeyboardMarkup()
            prev_button = types.InlineKeyboardButton(text='◀️ Предыдущая',
                                                     callback_data=f'permanent_{profile_user_id}_prev_{current_page}')
            next_button = types.InlineKeyboardButton(text='Следущая ▶️',
                                                     callback_data=f'permanent_{profile_user_id}_next_{current_page}')

            if current_page > 1 and end_index < all_pages:
                keyboard.row(prev_button, next_button)
            elif current_page > 1:
                keyboard.row(prev_button)
            elif current_page < all_pages:
                keyboard.row(next_button)

        await bot.send_message(message.chat.id, result_message, parse_mode="HTML", reply_markup=keyboard)
        return

    if args:
        user_id = args
    elif message.reply_to_message:
        replied_user = message.reply_to_message.from_user
        user_id = replied_user.id
    else:
        user_id = profile_user_id

    if isinstance(user_id, int):
        user_id = str(user_id)

    try:
        user_id = int(user_id)
    except ValueError:
        await bot.send_message(message.chat.id, "*❌ Введенный айди пользователя должен быть числом.*", parse_mode="Markdown")
        return

    if args and user_id == profile_user_id:  # Remove the redundant check for user_data
        await bot.send_message(message.chat.id, "*❌ Нельзя добавить самого себя в черный список.*", parse_mode="Markdown")
        return

    # Проверка на существование пользователя
    try:
        await get_ban_username(user_id)
    except Exception:
        await bot.send_message(message.chat.id, "*❌ Такого пользователя не существует.*", parse_mode="Markdown")
        return

    if not args:
        if ban_members:
            result_message = "<b>♾️ Черный список:</b>\n\n"
            for idx, banned_user_id in enumerate(ban_members, start=1):
                username = await get_ban_username(banned_user_id)
                if username:
                    username = username.replace("_", "&#95;")
                result_message += f"{idx}. @{username} (<code>{banned_user_id}</code>)\n"
        else:
            result_message = "<b>Заблокированных пользователей нет. 🚫</b>\n"

        result_message += "\n<b>📛 Чтобы добавить/удалить пользователя</b>\n" \
                          "/permanent <code>{id}</code>"

        await bot.send_message(message.chat.id, result_message, parse_mode="HTML")
        return

    if user_id in ban_members:
        await del_profile_ban_members(profile_user_id, user_id)

        username = await get_username(user_id)
        if username:
            username = username.replace("_", "&#95;")

        profile = f'<b>🍁 Пользователь</b> @{username} (<code>{user_id}</code>) <b>был удален из черного списка вашего профиля!</b>\n\n' \
                  f'<b>♾️ Для просмотра всех заблокированных пользователей напишите /permanent</b>'
        await bot.send_message(message.chat.id, profile, parse_mode="HTML")
        await state.finish()
    else:
        await update_profile_ban_members(profile_user_id, user_id)

        username = await get_username(user_id)
        if username:
            username = username.replace("_", "&#95;")

        profile = f'<b>🍁 Пользователь</b> @{username} (<code>{user_id}</code>) <b>был внесен в черный список вашего профиля!</b>\n\n' \
                  f'<b>♾️ Для просмотра всех заблокированных пользователей напишите /permanent</b>'
        await bot.send_message(message.chat.id, profile, parse_mode="HTML")

# Команда промокод
@dp.message_handler(commands=['promo'])
async def process_promo_command(message: types.Message):
    args = message.get_args()

    parts = args.split(' ')
    if args:
        user_data = await user_collections.find_one({"_id": message.from_user.id})
        if user_data:
            status = user_data.get("status")
            if status == "Создатель 🎭" or status == "Админ 🚗":
                if len(parts) == 1:
                    # Обработка команды /promo (сам промокод)
                    promo_code = args
                    await handle_promo_code(promo_code, message.from_user.id, chat_id=message.chat.id)
                elif len(parts) == 2:
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
                    await handle_promo_code(promo_code, message.from_user.id, chat_id=message.chat.id)
        else:
            unreg = f"*❌ Вы не зарегестированы в боте!*\n*🔰 Для регистрации напишите /start мне в личные сообщения.*"
            await bot.send_message(message.chat.id, unreg, parse_mode="Markdown")
    else:
        active_promos = await get_active_promo_codes()
        if active_promos:
            promos = f"*📽️ Активные промокоды:*\n{active_promos}\n\n" \
                     "*🧪 Для активации промокода* /promo `{промокод}`"
        else:
            promos = "*🤫 Активных промокодов не обнаружено!*\n\n" \
                     "*🧪 Для активации промокода* /promo `{промокод}`"
        await bot.send_message(message.chat.id, promos, parse_mode="Markdown")

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
                    # Создаем кнопку с коллбэк-данными, включающими айди сообщения
                    keyboard = types.InlineKeyboardMarkup()
                    promo_list_update = types.InlineKeyboardButton(text='Обновить 🌀',
                                                                   callback_data=f'list_update_{promo_id}_{current_page}')
                    keyboard.row(promo_list_update)

                    # Отправляем сообщение и сохраняем его айди
                    await message.reply(
                        f"*📋 Промокод* `{promo_id}` *не был активирован ни одним пользователем.*",
                        parse_mode="Markdown", reply_markup=keyboard)

            else:
                await message.reply("*❌ Промокод не найден.*", parse_mode="Markdown")
        else:
            await message.reply("*❌ Пожалуйста, укажите идентификатор промокода.*", parse_mode="Markdown")

# Обработчик команды для получения лог файла в канал
@dp.message_handler(commands=['log'])
async def send_log_to_channel_command(message: types.Message):
    chat_id = -1001855834243  # Replace with your desired channel ID
    log_file_path = 'private/bot.log'

    with open(log_file_path, 'rb') as log_file:
        try:
            await bot.send_message(chat_id, "*🚧 Log file:*", parse_mode="Markdown")
            await bot.send_document(chat_id, log_file)
        except TelegramAPIError as e:
            logging.error(f"Error while sending log to channel: {str(e)}")

@dp.message_handler(commands=['check'])
async def check_command_handler(message: types.Message):
    chat_id = 1738263685
    await create_and_send_archive(chat_id)

@dp.message_handler(commands=['id'])
async def get_user_profile(message: types.Message):
    # Get the user ID from the command arguments
    args = message.get_args()
    if not args:
        await message.reply("🔰 Пожалуйста укажите айди. Пример: /id <айди>")
        return

    try:
        user_id = int(args)
    except ValueError:
        await message.reply("👩‍🦽 Инвалид. Пожалуйста, укажите правильный айди.")
        return

    try:
        # Get the user information using the provided user ID
        user = await bot.get_chat(user_id)
        username = user.username
        first_name = user.first_name
        last_name = user.last_name

        # Create the message showing the user profile
        if username:
            result_message = f"<b>Профиль 📒</b>\n\n" \
                             f"<b>👥 Тэг:</b> @{username}\n"
        else:
            result_message = "<b>Юзернейм отсутствует ❌</b>\n\n"

        # Add first name and last name if available
        if first_name:
            result_message += f"<b>🍭 Имя:</b> <code>{first_name}</code>"
        if last_name:
            result_message += f"<code>{last_name}</code>"

        await message.reply(result_message, parse_mode="HTML")
    except Exception as e:
        print(e)
        await message.reply("Ошибка при получении профиля пользователя. Пожалуйста, убедитесь, что вы указали правильный айди.")

@dp.message_handler(commands=['wins'])
async def wins_leaderboard(message: types.Message, state: FSMContext):
    # Retrieve the user's status from the user_collections
    profile_user_id = message.from_user.id
    user_data = await user_collections.find_one({"_id": profile_user_id})
    user_wins = user_data.get("wins")

    # Retrieve all users sorted by wins in descending order
    all_users = await user_collections.find().sort("wins", -1).to_list(length=None)

    # Filter out users with more wins than participations
    top_users = [user for user in all_users if user.get("wins", 0) <= user.get("participation", 0)]

    # Find the position of the calling user in the top_users list
    calling_user_position = None
    for idx, user in enumerate(top_users):
        if user["_id"] == profile_user_id:
            calling_user_position = idx + 1
            break

    # Prepare the leaderboard message
    leaderboard_message = "<b>🏅 Таблица лидеров по победам (Топ 15):</b>\n\n"
    for idx, user in enumerate(top_users[:15]):
        username = await get_username(user['_id'])
        if username:
            username = username.replace("_", "&#95;")
        word_wins = get_wins_word(user['wins'])  # Получаем правильное слово для побед
        leaderboard_message += f"<b>{idx + 1}. {username} [</b><code>{user['status']}</code><b>] —</b> <code>{user['wins']}</code> <b>{word_wins}</b>\n"
    if profile_user_id == 1738263685:
        # Add the calling user's position
        leaderboard_message += f"\n<b>👤 Ваша позиция:</b>\n" \
                               f"<b>0.</b> <code>{profile_user_id}</code> <b>—</b> <code>{user_wins}</code> <b>{get_wins_word(user_wins)}</b>"
    else:
        # Add the calling user's position
        leaderboard_message += f"\n<b>👤 Ваша позиция:</b>\n" \
                               f"<b>{calling_user_position}.</b> <code>{profile_user_id}</code> <b>—</b> <code>{user_wins}</code> <b>{get_wins_word(user_wins)}</b>"
    keyboard = types.InlineKeyboardMarkup()
    done = types.InlineKeyboardButton(text='Игровой топ побед 🎰', callback_data=f'game_wins_{profile_user_id}')
    keyboard.add(done)

    # Send the leaderboard message
    await message.answer(leaderboard_message, parse_mode="HTML", reply_markup=keyboard)

@dp.message_handler(commands=['participations'])
async def wins_leaderboard(message: types.Message, state: FSMContext):
    # Retrieve the user's status from the user_collections
    profile_user_id = message.from_user.id
    user_data = await user_collections.find_one({"_id": profile_user_id})
    user_participation = user_data.get("participation")

    # Retrieve all users sorted by participations in descending order
    top_users = await user_collections.find().sort("participation", -1).to_list(length=None)

    # Find the position of the calling user in the top_users list
    calling_user_position = None
    for idx, user in enumerate(top_users):
        if user["_id"] == profile_user_id:
            calling_user_position = idx + 1
            break

    # Prepare the leaderboard message
    leaderboard_message = "<b>🍀 Таблица лидеров по участиям (Топ 15):</b>\n\n"
    for idx, user in enumerate(top_users[:15]):
        username = await get_username(user['_id'])
        if username:
            username = username.replace("_", "&#95;")
        word_participation = get_participation_word(user['participation'])  # Получаем правильное слово для участий
        leaderboard_message += f"<b>{idx + 1}. {username} [</b><code>{user['status']}</code><b>] —</b> <code>{user['participation']}</code> <b>{word_participation}</b>\n"

    # Add the calling user's position
    leaderboard_message += f"\n<b>👤 Ваша позиция:</b>\n" \
                           f"<b>{calling_user_position}.</b> <code>{profile_user_id}</code> <b>—</b> <code>{user_participation}</code> <b>{get_participation_word(user_participation)}</b>"
    keyboard = types.InlineKeyboardMarkup()
    done = types.InlineKeyboardButton(text='Игровой топ участий 🀄', callback_data=f'game_participations_{profile_user_id}')
    keyboard.add(done)

    # Send the leaderboard message
    await message.answer(leaderboard_message, parse_mode="HTML", reply_markup=keyboard)

@dp.message_handler(commands=['buy_key'])
async def buy_key(message: types.Message):
    # Отправляем вопрос о количестве активаций с вариантами выбора
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("1 активация", callback_data="buy_1"),
        types.InlineKeyboardButton("3 активации", callback_data="buy_3"),
        types.InlineKeyboardButton("5 активаций", callback_data="buy_5"),
        types.InlineKeyboardButton("10 активаций", callback_data="buy_10"),
    )

    await message.answer("*На сколько активаций хотите купить ключ?*", reply_markup=keyboard, parse_mode="Markdown")

# Обработчик выбора количества активаций
@dp.callback_query_handler(lambda call: call.data.startswith("buy"))
async def process_activation_choice(call: types.CallbackQuery):
    activation_choice = call.data.split("_")[1]  # Извлекаем выбор количества активаций из callback_data
    uses = int(activation_choice)
    await bot.answer_callback_query(call.id)

    # Delete the original message with the inline keyboard
    await bot.delete_message(call.message.chat.id, call.message.message_id)

    # Генерация ключа, определение его цены и описания
    key = generate_key()
    price = uses * 1
    if uses == 1:
        description = f"🔑 Оплата ключа на {uses} активацию."
    elif uses == 3:
        description = f"🔑 Оплата ключа на {uses} активации."
    else:
        description = f"🔑 Оплата ключа на {uses} активаций."

    # Отправляем запрос на оплату
    await bot.send_invoice(
        chat_id=call.message.chat.id,
        title="Оформление заказа 🔰",
        description=description,
        payload=key,  # Отправляем ключ в payload, чтобы потом узнать, какой ключ оплатили
        provider_token=PAYMENTS_TOKEN,
        currency='USD',  # Валюта (в данном случае доллары США)
        prices=[
            types.LabeledPrice(label='Ключ доступа', amount=price * 100)  # Цена указывается в центах
        ],
        start_parameter='buy_key',  # Уникальный параметр для оплаты
        need_name=True,
        need_phone_number=False,
        need_email=True,
        need_shipping_address=False,  # Зависит от того, требуется ли доставка товара
    )

# Обработчик успешной оплаты
@dp.message_handler(content_types=types.ContentType.SUCCESSFUL_PAYMENT)
async def process_successful_payment(message: types.Message):
    # Получаем ключ и прочие данные
    key = message.successful_payment.invoice_payload
    uses = 1
    user_id = message.from_user.id

    # Получаем email пользователя, если он был введен
    if message.successful_payment.order_info and 'email' in message.successful_payment.order_info:
        email = message.successful_payment.order_info['email']
    else:
        email = "Email не был указан."

    await add_key_to_data(key, uses, email, user_id)
    # Выполняем какие-либо действия с ключом и email
    await message.answer(f"*✅ Покупка была успешна! Вы получили ключ* `{key}`.\n"
                         f"*🔑 Количество активаций:* `{uses}`", parse_mode="Markdown")

# Обработчик предварительной проверки
@dp.pre_checkout_query_handler(lambda query: True)
async def process_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    # Отправляем ответ о успешной предварительной проверке
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.callback_query_handler(lambda query: query.data.startswith('room_create'))
async def choose_game_type_or_rounds(callback_query: types.CallbackQuery):
    format_choice = callback_query.data.split('_')[2]
    game_types = {
        '🎲': 'Кубик',
        '🎯': 'Дартс',
        '🏀': 'Баскетбол',
        '⚽': 'Футбол',
        '🎳': 'Боулинг',
        '🎰': 'Казино',
    }
    if format_choice == '1vs1':
        # Ask the user to select the game type for 1vs1 format
        type_message = "*🎮 Выберите тип игры:*"
        keyboard = types.InlineKeyboardMarkup()
        for emoji, game_type in game_types.items():
            callback_data = f'roomcreate_{format_choice}_{emoji}'
            keyboard.add(types.InlineKeyboardButton(text=f'{emoji} {game_type}', callback_data=callback_data))

        await bot.edit_message_text(type_message, callback_query.message.chat.id,
                                    callback_query.message.message_id, parse_mode="Markdown",
                                    reply_markup=keyboard)

    elif format_choice == '2vs2':
        # Ask the user to select the game type for 2vs2 format
        type_message = "*🎮 Выберите тип игры:*"
        keyboard = types.InlineKeyboardMarkup()
        for emoji, game_type in game_types.items():
            callback_data = f'roomcreate_{format_choice}_{emoji}'
            keyboard.add(types.InlineKeyboardButton(text=f'{emoji} {game_type}', callback_data=callback_data))

        await bot.edit_message_text(type_message, callback_query.message.chat.id,
                                    callback_query.message.message_id, parse_mode="Markdown",
                                    reply_markup=keyboard)

@dp.callback_query_handler(lambda query: query.data.startswith('roomcreate_1vs1') or query.data.startswith('roomcreate_2vs2'))
async def choose_game_type(callback_query: types.CallbackQuery):
    format_and_type_choice = callback_query.data.split('_')[1:]

    if len(format_and_type_choice) >= 2:
        format_choice, type_choice = format_and_type_choice[0], format_and_type_choice[1]

        # Ask the user to select the number of rounds
        rounds_message = "*🔄 Выберите количество раундов (1, 2, 3, 4, 5):*"
        keyboard = types.InlineKeyboardMarkup()
        for rounds in range(1, 6):
            emoji = format_choice  # Get the emoji from the format_choice variable
            callback_data = f'createroom_{emoji}_{type_choice}_{rounds}'
            keyboard.add(types.InlineKeyboardButton(text=str(rounds), callback_data=callback_data))

        await bot.edit_message_text(rounds_message, callback_query.message.chat.id,
                                    callback_query.message.message_id, parse_mode="Markdown",
                                    reply_markup=keyboard)
    else:
        # Handle the case when there are not enough elements in the list
        error_message = "❌ Error: Invalid data format in callback query."
        await bot.send_message(user_id, error_message)

@dp.callback_query_handler(lambda query: query.data.startswith('createroom_'))
async def create_game_room(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    choices = callback_query.data.split('_')[1:]

    if len(choices) >= 3:
        format_choice, type_choice, rounds = choices[0], choices[1], int(choices[2])

        room_id = generate_room_id()
        room_link = await generate_room_link(room_id)

        current_time = datetime.now(timezone)
        create_date = current_time.strftime("%Y-%m-%d %H:%M:%S")

        # Retrieve contests where the user with the specified user_id was a member
        user_games = await game_collection.find({"owner_id": user_id}).to_list(length=None)
        # Check if there are any active contests for the user
        active_games = [game for game in user_games if "ended" in game and game["ended"] == "False"]

        if len(active_games) >= 1:
            result_message = "*❌ У вас уже есть активная комната!.*"
            keyboard = types.InlineKeyboardMarkup()
            back = types.InlineKeyboardButton(text='Назад 🥏', callback_data='create_back')
            keyboard.row(back)

            # Send or edit the message with pagination
            await bot.edit_message_text(result_message, callback_query.message.chat.id,
                                                callback_query.message.message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)
        elif len(active_games) < 1:
            # Save the selected format, type, rounds, and other details in the database
            await create_gameroom(room_id, user_id, type_choice, format_choice, rounds, create_date, room_link)

            # Create the confirmation message with the formatted room_link
            confirmation_message = f"*☑️ Комната успешно создана!*\n\n" \
                                   f"*🔘 ID Комнаты:* `{room_id}`\n" \
                                   f"*🛒 Игра:* `{type_choice}`\n" \
                                   f"*👥 Формат:* `{format_choice}`\n" \
                                   f"*🔄 Количество раундов:* `{rounds}`\n" \
                                   f"*🗓️ Дата создания:* `{create_date}`\n\n" \
                                   f"*🔗 Логин в комнату:* `/play {room_id}`"

        # Send the formatted confirmation message with the clickable link
        await bot.edit_message_text(confirmation_message, callback_query.message.chat.id,
                                    callback_query.message.message_id, parse_mode="Markdown")
    else:
        # Handle the case when there are not enough elements in the list
        error_message = "❌ Error: Invalid data format in callback query."
        await bot.send_message(user_id, error_message)

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
              f'/wins — 🥇 Топ пользователей по победам.\n' \
              f'/participations — 🍀 Топ пользователей по их участиям.\n' \
              f'/create — 🎮 Создать игровую комнату.' \
              f'/promo - 🧪 Просмотр активных промокодов, также их активация!\n' \
              f'/contest - 🎖 Меню для создания ваших конкурсов и управлениями ими, доступ к меню получается только через `ключ 🔑`.\n' \
              f'/generate - 🗝️ Покупка (в будущем) ключа для формирования конкурсов!\n' \
              f'/permanent - 🚫 Список заблокированных пользователей.\n\n'

    # Создание кнопки-ссылки "Детальнее"
    inline_keyboard = types.InlineKeyboardMarkup()
    inline_keyboard.add(types.InlineKeyboardButton(text="Детальнее ❔", url="https://teletype.in/@kpyr/Flame"))

    await message.reply(profile, parse_mode="Markdown", reply_markup=inline_keyboard)

@dp.message_handler(commands=['event'])
async def send_event_to_all_users(message: types.Message):
    args = message.get_args()

    # Retrieve the user's status from the user_collections
    profile_user_id = message.from_user.id
    user_data = await user_collections.find_one({"_id": profile_user_id})
    status = user_data.get("status")

    if status == "Создатель 🎭":

        if not args:
            await message.reply("*❔ Вы не указали сообщение, которое хотите отправить!*", parse_mode="Markdown")
            return

        # Retrieve all user_ids from the user_collections
        user_ids = [user['_id'] for user in await user_collections .find({}, {'_id': 1}).to_list(length=None)]

        # Send the event message to all users
        for user_id in user_ids:
            try:
                await bot.send_message(user_id, args, parse_mode="Markdown")
            except Exception as e:
                await message.reply(f"*🛑 Произошла ошибка, не получилось отправить сообщение пользователю* `{user_id}`: {e}", parse_mode="Markdown")

        await message.reply(f"*💠 Уведомлений было отправлено* `{len(user_ids)}`*.*", parse_mode="Markdown")
    else:
        await message.reply("*⚠️ Нельзя воспользоваться командой, так как у вас недостаточно прав для этого.*", parse_mode="Markdown")

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

            await send_profile(username, user_id, callback_query.message.chat.id)
        else:
            # Обработка случая, когда данные о пользователе не найдены
            await bot.send_message(callback_query.message.chat.id, "☠️ Профиль пользователя не найден.")

    elif button_text == 'profile_edit':

        user_id = callback_query.from_user.id

        # Поиск данных о пользователе в базе данных
        user_data = await user_collections.find_one({"_id": user_id})

        if user_data:
            username = callback_query.from_user.username

            await show_profile(username, user_id, callback_query.message.chat.id, callback_query.message.message_id)
        else:
            profile = "☠️ Профиль пользователя не найден."

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
                ("status" in user_data and user_data["status"] in ["Тестер 🔰", "Админ 🚗", "Создатель 🎭"]) or int(
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

        if user_data and ("status" in user_data and user_data["status"] in ["Тестер 🔰", "Админ 🚗", "Создатель 🎭"]):
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
                ("status" in user_data and user_data["status"] in ["Тестер 🔰", "Админ 🚗", "Создатель 🎭"]) or int(
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

    elif button_text.startswith('active'):
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

        await show_user_drawings(callback_query, user_id, current_page)

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
        message_id = callback_query.message.message_id

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

    elif button_text.startswith('list_update'):

        parts = button_text.split('_')
        promo = parts[2]
        current_page = int(parts[3])
        try:
            await update_promo_members(promo, current_page, callback_query.message.chat.id, callback_query.message.message_id)
        except Exception as e:
            await bot.answer_callback_query(callback_query.id, text="Новых участников не появилось, пожалуйста перестаньте ломать палец. 🥬")

    elif button_text.startswith('permanent'):
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

        await show_user_permanent(callback_query, user_id, current_page)

    elif button_text == 'text_for_key':
        result_message = "<b>💲 Цена ключа на одну активацию</b> <code>1$</code>\n" \
                         "<b>🔑 Воспользуйтесь командой</b> /buy_key <b>для покупки ключа.</b>"
        await bot.edit_message_text(result_message, callback_query.message.chat.id, callback_query.message.message_id,
                                    parse_mode="HTML")

    elif button_text == 'check_rooms':
        user_id = callback_query.from_user.id

        # Retrieve contests where the user with the specified user_id was a member
        user_games = await game_collection.find({"members": user_id}).to_list(length=None)

        # Check if there are any active contests for the user
        active_games = [game for game in user_games if "ended" in game and game["ended"] == "False"]

        if active_games:
            number = 0
            # Create the message containing the user history for the current page
            result_message = f"*🖥️ Ваши комнаты:*\n\n"
            for game in active_games:
                # Increment the room number for the next iteration
                number += 1
                result_message += f"                            *= {number} =*\n"
                result_message += f"*🔘 ID Комнаты:* `{game['_id']}`\n"
                result_message += f"*🛒 Игра:* `{game['type']}`\n"
                result_message += f"*🏁 Количество участников:* `{len(game['members'])}`\n"
                result_message += f"*🗓️ Дата создания:* `{game['create_date']}`\n\n"
            keyboard = types.InlineKeyboardMarkup()
            back = types.InlineKeyboardButton(text='Назад 🥏', callback_data='create_back')
            keyboard.row(back)

            # Send or edit the message with pagination
            await bot.edit_message_text(result_message, callback_query.message.chat.id,
                                                callback_query.message.message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)
        else:
            result_message = "*🔎 Сейчас вы не участвуете в каких-либо играх.*"
            keyboard = types.InlineKeyboardMarkup()
            back = types.InlineKeyboardButton(text='Назад 🥏', callback_data='create_back')
            keyboard.row(back)

            # Send or edit the message with pagination
            await bot.edit_message_text(result_message, callback_query.message.chat.id,
                                                callback_query.message.message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)

    elif button_text == 'create_room':
        user_id = callback_query.from_user.id

        # Retrieve contests where the user with the specified user_id was a member
        user_games = await game_collection.find({"owner_id": user_id}).to_list(length=None)

        # Check if there are any active contests for the user
        active_games = [game for game in user_games if "ended" in game and game["ended"] == "False"]

        if len(active_games) > 1:
            result_message = "*❌ У вас уже есть активная комната!.*"
            keyboard = types.InlineKeyboardMarkup()
            back = types.InlineKeyboardButton(text='Назад 🥏', callback_data='create_back')
            keyboard.row(back)

            # Send or edit the message with pagination
            await bot.edit_message_text(result_message, callback_query.message.chat.id,
                                                callback_query.message.message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)
        else:
            # Create the message containing the user history for the current page
            result_message = f"*🖥️ Выберите формат:*\n\n"
            keyboard = types.InlineKeyboardMarkup()
            chose_1 = types.InlineKeyboardButton(text='1vs1 👤', callback_data='room_create_1vs1_formate')
            chose_2 = types.InlineKeyboardButton(text='2vs2 👥', callback_data='room_create_2vs2_formate')
            keyboard.row(chose_1)
            keyboard.row(chose_2)

            # Send or edit the message with pagination
            await bot.edit_message_text(result_message, callback_query.message.chat.id,
                                                callback_query.message.message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)

    elif button_text == 'create_back':
        user_id = callback_query.from_user.id
        user_data = await game_collection.find_one({"owner_id": user_id, "ended": "False"})

        if user_data:
            keyboard = types.InlineKeyboardMarkup()
            check_rooms = types.InlineKeyboardButton(text='🔎 Мои комнаты', callback_data='check_rooms')
            keyboard.row(check_rooms)
            result_message = "*🖥️ У вас уже создана игровая комната!*\n\n" \
                             "*✨ Воспользуйтесь кнопкой для просмотра активных комнат:*"
            # Send or edit the message with pagination
            await bot.edit_message_text(result_message, callback_query.message.chat.id,
                                                callback_query.message.message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)

        else:
            keyboard = types.InlineKeyboardMarkup()
            create_room = types.InlineKeyboardButton(text='🕹️ Создать', callback_data='create_room')
            check_rooms = types.InlineKeyboardButton(text='🔎 Мои комнаты', callback_data=f'check_rooms')
            keyboard.row(check_rooms)
            keyboard.row(create_room)

            result_message = "*🖥️ Панель создания игровых комнат!*\n\n" \
                             "*✨ Воспользуйтесь кнопками для управления комнатами или их создания:*"
            # Send or edit the message with pagination
            await bot.edit_message_text(result_message, callback_query.message.chat.id,
                                                callback_query.message.message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)

    elif button_text.startswith('info_room'):
        user_id = callback_query.from_user.id
        room_id = button_text.split('_')[2]

        # Retrieve contests where the user with the specified user_id was a member
        room = await game_collection.find_one({"_id": room_id})

        members = room.get("members")
        if user_id in members:
            pass
        else:
            await bot.answer_callback_query(callback_query.id, text="❌ Вы не являетесь участником данной комнаты. ️")
            await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
            return

        if room:
            # Create the message containing the user history for the current page
            result_message = f"*🖥️ Информация о комнате:*\n\n"
            # Increment the room number for the next iteration
            result_message += f"*🔘 ID Комнаты:* `{room['_id']}`\n"
            result_message += f"*🛒 Игра:* `{room['type']}`\n"
            result_message += f"*👥 Формат:* `{room['format']}`\n"
            result_message += f"*🔄 Количество раундов:* `{room['rounds']}`\n"
            result_message += f"*🏁 Количество участников:* `{len(room['members'])}`\n"
            result_message += f"*🗓️ Дата создания:* `{room['create_date']}`\n\n"
            keyboard = types.InlineKeyboardMarkup()
            game_members = types.InlineKeyboardButton(text='Посмотреть участников 👥', callback_data=f'game_members_{room_id}')
            keyboard.row(game_members)

            if int(user_id) == room["owner_id"]:
                start_game = types.InlineKeyboardButton(text='Начать ✅', callback_data=f'start_game_{room_id}')
                keyboard.row(start_game)
            else:
                leave_room = types.InlineKeyboardButton(text='Покинуть комнату ❌',
                                                        callback_data=f'leave_room_{room_id}')
                keyboard.row(leave_room)

            # Send or edit the message with pagination
            await bot.edit_message_text(result_message, callback_query.message.chat.id,
                                                callback_query.message.message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)
        else:
            result_message = "*❌ Произошла ошибка.*"
            keyboard = types.InlineKeyboardMarkup()
            back = types.InlineKeyboardButton(text='Закрыть ☑️️', callback_data='done')
            keyboard.row(back)

            # Send or edit the message with pagination
            await bot.edit_message_text(result_message, callback_query.message.chat.id,
                                                callback_query.message.message_id, parse_mode="Markdown",
                                                reply_markup=keyboard)

    elif button_text.startswith('leave_room'):

        user_id = callback_query.from_user.id
        room_id = button_text.split('_')[2]

        # Retrieve the room using the room_id
        room = await game_collection.find_one({"_id": room_id})
        user = await user_collections.find_one({"_id": user_id})
        members = room.get("members", [])
        room_status = room.get("room_status")

        if user_id in members:
            pass
        else:
            await bot.answer_callback_query(callback_query.id, text="❌ Вы не являетесь участником данной комнаты. ️")
            await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
            return

        if room_status == "wait":
            await bot.answer_callback_query(callback_query.id, text="✅ ️")
        elif room_status == "game":
            await bot.answer_callback_query(callback_query.id, text="❌ Вы не можете покинуть комнату во время игры. ️")
            await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
            return
        elif room_status == "ended":
            await bot.answer_callback_query(callback_query.id, text="❌ Вы не можете покинуть комнату после того как игра в ней была окончена. ️")
            await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
            return

        if room:
            members = room.get("members", [])
            if user_id in members:
                members.remove(user_id)

                await game_collection.update_one({"_id": room_id}, {"$set": {"members": members}})
                game_participation = user.get("game_participation")
                if game_participation > 0:
                    await user_collections.update_one({"_id": user_id}, {"$inc": {"game_participation": -1}})
                else:
                    pass
                # Optionally, you can inform the user that they have left the room
                await bot.edit_message_text("*✅ Вы успешно покинули комнату!*", callback_query.message.chat.id,
                                            callback_query.message.message_id, parse_mode="Markdown")
            else:
                # Send or edit the message with pagination
                await bot.edit_message_text("*❌ Вы не являетесь участником данной комнаты!*", callback_query.message.chat.id,
                                            callback_query.message.message_id, parse_mode="Markdown")
        else:
            # Send or edit the message with pagination
            await bot.edit_message_text("*❌ Комната не найдена*", callback_query.message.chat.id,
                                        callback_query.message.message_id, parse_mode="Markdown")

    elif button_text.startswith('game_members'):
        room_id = button_text.split('_')[2]

        room = await game_collection.find_one({"_id": room_id})

        owner_id = room.get("owner_id")
        members = room.get("members")
        if user_id in members:
            pass
        else:
            await bot.answer_callback_query(callback_query.id, text="❌ Вы не являетесь участником данной комнаты. ️")
            await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
            return

        result_message = f"<b>🎮 Участники комнаты</b> <code>{room_id}</code><b>:</b>\n\n"

        keyboard = types.InlineKeyboardMarkup()
        current_page = 1
        per_page = 25
        start_index = (current_page - 1) * per_page
        end_index = current_page * per_page
        page_members = members[start_index:end_index] if start_index < len(members) else []

        for idx, user_id in enumerate(page_members, start=start_index + 1):
            username = await get_username(user_id)
            if username:
                username = username.replace("_", "&#95;")
            creator_label = "<b>— Создатель комнаты 💽</b>" if user_id == owner_id else ""
            result_message += f"{idx}. @{username} (<code>{user_id}</code>) {creator_label}\n"
        back = types.InlineKeyboardButton(text='Назад 🥏', callback_data=f'info_room_{room_id}')
        keyboard.row(back)

        await bot.edit_message_text(result_message, callback_query.message.chat.id, callback_query.message.message_id,
                                    parse_mode="HTML",
                                    reply_markup=keyboard)

    elif button_text.startswith('start_game'):
        room_id = button_text.split('_')[2]

        # Retrieve contests where the user with the specified user_id was a member
        room = await game_collection.find_one({"_id": room_id})

        # Check if the format of the game is either 2vs2 or 1vs1
        room_format = room.get("format", "")
        max_players = 4 if room_format == "2vs2" else 2
        current_players = len(room.get("members", []))
        room_status = room.get("room_status")
        if room_status == "wait":
            await bot.answer_callback_query(callback_query.id, text="✅ ️")
        elif room_status == "game":
            await bot.answer_callback_query(callback_query.id,
                                            text="❌ Вы не можете начать игру, так как она уже идёт. ️")
            await bot.delete_message(chat_id=callback_query.message.chat.id,
                                     message_id=callback_query.message.message_id)
            return
        elif room_status == "ended":
            await bot.answer_callback_query(callback_query.id,
                                            text="❌ Вы не можете начать игру, так как она уже окончена. ️")
            await bot.delete_message(chat_id=callback_query.message.chat.id,
                                     message_id=callback_query.message.message_id)
            return

        if current_players < max_players:
            await bot.answer_callback_query(callback_query.id, text="Недостаточно участников в комнате! ❌")
        else:
            await game_collection.update_one({"_id": room_id}, {"$set": {"room_status": "game"}})
            result_message = "*Удачи! 🍀*"

            # Send or edit the message with pagination
            await bot.edit_message_text(result_message, callback_query.message.chat.id,
                                        callback_query.message.message_id, parse_mode="Markdown",
                                        reply_markup=keyboard)
            rounds = room.get("rounds")
            members = room.get("members", [])  # Define the members variable

            # Split members into two teams for 2vs2 format
            if room_format == "2vs2":
                team1 = members[:2]
                team2 = members[2:]
            else:
                # If it is 1vs1, create the "teams" of individual members
                team1, team2 = [members[0]], [members[1]]

            # Initialise dictionaries to count the wins of each team
            team_wins = {tuple(team1): 0, tuple(team2): 0}
            team_scores = {tuple(team1): 0, tuple(team2): 0}

            # Informing users about the start of the game
            start_game_message = "<b>🎮 Игра началась!</b>\n\n"
            team_message = ""

            for team_name, team_members in {"<b>🫑 Первая команда</b>": team1, "<b>🍏 Вторая команда</b>": team2}.items():
                # Create a string for all members in a single team
                members_string = ', '.join([f"@{await get_username(member)} <code>[{member}]</code>" for member in team_members])
                team_message += "{}:\n{}\n\n".format(team_name, members_string)

            # Send message to each member
            for member in team1 + team2:
                await bot.send_message(member, start_game_message, parse_mode="HTML")
                await bot.send_chat_action(user_id, action="typing")
                await asyncio.sleep(0.7)
                await bot.send_message(member, team_message, parse_mode="HTML")

            for _ in range(rounds):
                # Define the match_results variable
                match_results = {tuple(team1): 0, tuple(team2): 0}

                for team in [team1, team2]:
                    for member in team:
                        # Send message to each member
                        await bot.send_message(member, "*Летит! 🕊️*", parse_mode="Markdown")
                        basketball = await bot.send_dice(member, emoji=room["type"])
                        match_results[tuple(team)] += basketball['dice']['value']  # Record the result
                        team_scores[tuple(team)] += basketball['dice']['value']  # Update the team scores

                        # Создаем новый словарь с ключами без кортежей
                        text_match_results = {team[0]: score for team, score in match_results.items()}

                        await bot.send_chat_action(user_id, action="typing")
                        await asyncio.sleep(2.5)

                # Compare results and decide the winner and loser
                winner = max(match_results, key=match_results.get)
                loser = min(match_results, key=match_results.get)

                if match_results[winner] == match_results[loser]:  # It's a draw
                    for team in [team1, team2]:
                        for member in team:
                            await bot.send_message(member, "*Этот раунд закончился в ничью! 🤝*", parse_mode="Markdown")
                    continue
                else:
                    team_wins[winner] += 1  # Update the number of wins for the winning team

                # Sending messages about victory and defeat
                for team in [winner, loser]:
                    for member in team:
                        if team == winner:
                            await bot.send_message(member, "*Отличный раунд, ваша команда победила! 🏅*",
                                                   parse_mode="Markdown")
                        else:
                            await bot.send_message(member, "*Похоже, ваша команда этот раунд проиграла... 🫥*",
                                                   parse_mode="Markdown")
            max_wins = max(team_wins.values())
            winners = [team for team, wins in team_wins.items() if wins == max_wins]

        unique_wins = set(team_wins.values())

        if len(unique_wins) == 1 and list(unique_wins)[0] > 0:
            max_wins = max(team_wins.values())
            winners = [team for team, wins in team_wins.items() if wins == max_wins]
            # Отправка сообщения о ничьей всем участникам
            draw_message = "*🌉 Данная игра была закончена ничьей, поэтому победителей нет.*"
            for member in members:
                await user_collections.update_one({"_id": member}, {"$inc": {"draws": 1}})
                await bot.send_message(member, draw_message, parse_mode="Markdown")
            await game_collection.update_one({"_id": room_id}, {"$set": {"draw": "True"}})
        elif max(team_wins.values()):  # If there's at least one win
            max_wins = max(team_wins.values())
            winners = [player for player, wins in team_wins.items() if wins == max_wins]
            winner_team = winners[0]  # это ваш кортеж

            # Если у нас один победитель
            if len(winner_team) == 1:
                # Получаем значение айди пользователя из первого кортежа
                winner_user_id = winners[0][0]
                username = await get_username(winner_user_id)
                if username:
                    username = username.replace("_", "&#95;")
                    team_names = {
                        tuple(team1): "Первая команда",
                        tuple(team2): "Вторая команда"
                    }

                    team_scores_message = "\n".join([
                        f"<b>{team_names[team]}</b> <code>[{''.join([str(member) for member in team])}]</code><b>:</b> <code>{score}</code> <b>очков.</b>"
                        for team, score in team_scores.items()
                    ])

                    winner_message = (
                        f"<b>🥇 Поздравляю, пользователь</b> @{username} <code>[{winner_user_id}]</code>"
                        f" <b>победил, отличная была игра!</b>\n\n"
                        f"<b>🏆 Счет команд:</b>\n{team_scores_message}"
                    )
                    for member in members:
                        await bot.send_message(member, winner_message, parse_mode="HTML")
                # Обновление коллекции игры с информацией о победителе и окончании игры
                await game_collection.update_one({"_id": room_id}, {"$push": {"winners": {"$each": [winner_user_id]}}})
                await user_collections.update_one({"_id": winner_user_id}, {"$inc": {"game_wins": 1}})

            # Если у нас несколько победителей
            else:
                winners_usernames = []
                for winner_team in winners:
                    winner_usernames = []
                    for user_id in winner_team:
                        username = await get_username(user_id)
                        if username:
                            username = username.replace("_", "&#95;")
                            winner_usernames.append(f"@{username} <b>—</b> <code>{user_id}</code>\n")

                        team_names = {
                            tuple(team1): "Первая команда",
                            tuple(team2): "Вторая команда"
                        }

                        team_scores_message = "\n".join([
                            f"<b>{team_names[team]}</b> <code>[{', '.join([str(member) for member in team])}]</code><b>:</b> <code>{score}</code> <b>очков.</b>"
                            for team, score in team_scores.items()
                        ])

                        # Увеличиваем счетчик "game_wins" для текущего пользователя
                        await user_collections.update_one({"_id": user_id}, {"$inc": {"game_wins": 1}})

                    winners_usernames.append("".join(winner_usernames))
                winners_message = f"<b>🥇 Поздравляю команду с победой:</b>\n{''.join(winners_usernames)}\n" \
                        f"<b>🏆 Счет команд:</b>\n{team_scores_message}"

                for member in members:
                    await bot.send_message(member, winners_message, parse_mode="HTML")

                # Обновление коллекции игры с информацией о победителе и окончании игры
                await game_collection.update_one({"_id": room_id}, {"$push": {"winners": {"$each": [user_id]}}})
        else:
            # Отправка сообщения о ничьей всем участникам
            draw_message = "*🌉 Данная игра была закончена ничьей, поэтому победителей нет.*"
            for member in members:
                await user_collections.update_one({"_id": member}, {"$inc": {"draws": 1}})
                await bot.send_message(member, draw_message, parse_mode="Markdown")
            await game_collection.update_one({"_id": room_id}, {"$set": {"draw": "True"}})
        await game_collection.update_one({"_id": room_id}, {"$set": {"room_status": "ended"}})
        await game_collection.update_one({"_id": room_id}, {"$set": {"ended": "True"}})

    elif button_text.startswith('game_profile'):
        user_id = button_text.split('_')[2]
        type = button_text.split('_')[3]
        try:
            send_id = button_text.split('_')[4]
        except Exception:
            send_id = None
            pass

        if send_id:
            click_user_id = callback_query.from_user.id
            if int(send_id) != click_user_id:
                await bot.answer_callback_query(callback_query.id, text="❌ Увы эта кнопка не ваша, а так хотелось...")
                return
        else:
            click_user_id = callback_query.from_user.id
            if int(user_id) != click_user_id:
                await bot.answer_callback_query(callback_query.id, text="❌ Увы эта кнопка не ваша, а так хотелось...")
                return

        user_data = await user_collections.find_one({"_id": int(user_id)})

        if user_data:
            if type == "buttons":
                username = callback_query.from_user.username
            else:
                username = user_id
            wins = user_data.get("game_wins", 0)
            draws = user_data.get("draws", 0)
            participation = user_data.get("game_participation", 0)

            # Вычисление процента побед
            win_percentage = (wins / participation) * 100 if participation > 0 else 0
            # Вычисление процента ничьих
            draw_percentage = (draws / participation) * 100 if participation > 0 else 0

            creation_date = user_data.get("creation_date", "")
            status = user_data.get("status", "")

            # Создание и отправка сообщения с кнопками
            profile = f'*🎮 Игровой профиль пользователя* `{username}`:\n\n' \
                      f'*🍧 Статус:* `{status}`\n\n' \
                      f'*🍀 Участие в играх:* `{participation}`\n' \
                      f'*🕊️ Ничьи:* `{draws}`\n' \
                      f'*🥇 Победы в играх:* `{wins}`\n' \
                      f'*🏆 Процент побед:* `{win_percentage:.2f}%`\n' \
                      f'*⚖️ Процент ничьих:* `{draw_percentage:.2f}%`\n\n' \
                      f'*📅 Дата регистрации:* `{creation_date}`'
            keyboard = types.InlineKeyboardMarkup()

            if type == "buttons":
                contest_profile = types.InlineKeyboardButton(text='Конкурсный профиль 🍭', callback_data=f'contest_profile_{user_id}_buttons')

                history = types.InlineKeyboardButton(text='История участий 📔',
                                                     callback_data=f'history_{user_id}_None_1')
                active_history_drawings = types.InlineKeyboardButton(text='Активные участия 🦪',
                                                                     callback_data=f'active_{user_id}_None_1')
                id_check = types.InlineKeyboardButton(text='Поиск пользователя 🥏', callback_data='id_check')
                done = types.InlineKeyboardButton(text='Готово ✅', callback_data='done')
                keyboard.add(contest_profile)
                keyboard.add(history, active_history_drawings)
                keyboard.add(id_check)
                keyboard.add(done)

            elif type == "check":
                contest_profile = types.InlineKeyboardButton(text='Конкурсный профиль 🍭', callback_data=f'contest_profile_{user_id}_check')
                id_check = types.InlineKeyboardButton(text='Поиск пользователя 🥏', callback_data='id_check')
                back = types.InlineKeyboardButton(text='Назад 🧿', callback_data=f'profile_edit')
                keyboard.add(contest_profile)
                keyboard.add(id_check)
                keyboard.add(back)

            elif type == "none":
                if send_id:
                    history = types.InlineKeyboardButton(text='Конкурсный профиль 🍭', callback_data=f'contest_profile_{user_id}_none_{send_id}')
                else:
                    history = types.InlineKeyboardButton(text='Конкурсный профиль 🍭', callback_data=f'contest_profile_{user_id}_none')
                keyboard.add(history)

            # Send or edit the message with pagination
            await bot.edit_message_text(profile, callback_query.message.chat.id,
                                        callback_query.message.message_id, parse_mode="Markdown",
                                        reply_markup=keyboard)
        else:
            result_message = "*☠️ Профиль пользователя не найден.*\n\n*👤 Напишите команду* /start *в личные сообщения боту, это создаст ваш профиль!*"
            # Send or edit the message with pagination
            await bot.edit_message_text(result_message, callback_query.message.chat.id,
                                        callback_query.message.message_id, parse_mode="Markdown",
                                        reply_markup=keyboard)

    elif button_text.startswith('contest_profile'):
        user_id = button_text.split('_')[2]
        type = button_text.split('_')[3]
        try:
            send_id = button_text.split('_')[4]
        except Exception:
            send_id = None
            pass

        if send_id:
            click_user_id = callback_query.from_user.id
            if int(send_id) != click_user_id:
                await bot.answer_callback_query(callback_query.id, text="❌ Увы эта кнопка не ваша, а так хотелось...")
                return
        else:
            click_user_id = callback_query.from_user.id
            if int(user_id) != click_user_id:
                await bot.answer_callback_query(callback_query.id, text="❌ Увы эта кнопка не ваша, а так хотелось...")
                return

        user_data = await user_collections.find_one({"_id": int(user_id)})

        if user_data:
            if type == "buttons":
                username = callback_query.from_user.username
            else:
                username = user_id
            wins = user_data.get("wins", 0)
            participation = user_data.get("participation", 0)

            # Вычисление процента побед
            win_percentage = (wins / participation) * 100 if participation > 0 else 0
            creation_date = user_data.get("creation_date", "")
            status = user_data.get("status", "")

            # Создание и отправка сообщения с кнопками
            profile = f'*🍹 Конкурсный профиль пользователя* `{username}`:\n\n' \
                      f'*🍧 Статус:* `{status}`\n\n' \
                      f'*🍀 Участие в играх:* `{participation}`\n' \
                      f'*🥇 Победы в играх:* `{wins}`\n' \
                      f'*🏆 Процент побед:* `{win_percentage:.2f}%`\n\n' \
                      f'*📅 Дата регистрации:* `{creation_date}`'
            keyboard = types.InlineKeyboardMarkup()

            if type == "buttons":
                contest_profile = types.InlineKeyboardButton(text='Игровой профиль 🎮', callback_data=f'game_profile_{user_id}_buttons')

                history = types.InlineKeyboardButton(text='История участий 📔',
                                                     callback_data=f'history_{user_id}_None_1')
                active_history_drawings = types.InlineKeyboardButton(text='Активные участия 🦪',
                                                                     callback_data=f'active_{user_id}_None_1')
                id_check = types.InlineKeyboardButton(text='Поиск пользователя 🥏', callback_data='id_check')
                done = types.InlineKeyboardButton(text='Готово ✅', callback_data='done')
                keyboard.add(contest_profile)
                keyboard.add(history, active_history_drawings)
                keyboard.add(id_check)
                keyboard.add(done)

            elif type == "check":
                contest_profile = types.InlineKeyboardButton(text='Игровой профиль 🎮', callback_data=f'game_profile_{user_id}_check')
                id_check = types.InlineKeyboardButton(text='Поиск пользователя 🥏', callback_data='id_check')
                back = types.InlineKeyboardButton(text='Назад 🧿', callback_data=f'profile_edit')
                keyboard.add(contest_profile)
                keyboard.add(id_check)
                keyboard.add(back)

            elif type == "none":
                if send_id:
                    history = types.InlineKeyboardButton(text='Игровой профиль 🎮', callback_data=f'game_profile_{user_id}_none_{send_id}')
                else:
                    history = types.InlineKeyboardButton(text='Игровой профиль 🎮', callback_data=f'game_profile_{user_id}_none')
                keyboard.add(history)

            # Send or edit the message with pagination
            await bot.edit_message_text(profile, callback_query.message.chat.id,
                                        callback_query.message.message_id, parse_mode="Markdown",
                                        reply_markup=keyboard)
        else:
            result_message = "*☠️ Профиль пользователя не найден.*\n\n*👤 Напишите команду* /start *в личные сообщения боту, это создаст ваш профиль!*"
            # Send or edit the message with pagination
            await bot.edit_message_text(result_message, callback_query.message.chat.id,
                                        callback_query.message.message_id, parse_mode="Markdown",
                                        reply_markup=keyboard)

    elif button_text.startswith('game_wins'):
        user_id = button_text.split('_')[2]
        click_user_id = callback_query.from_user.id
        await bot.answer_callback_query(callback_query.id, text="⌛ Загружаю топ...")

        if int(user_id) != click_user_id:
            await bot.answer_callback_query(callback_query.id, text="❌ Увы эта кнопка не ваша, а так хотелось...")
            return

        user_data = await user_collections.find_one({"_id": int(user_id)})
        user_wins = user_data.get("game_wins", 0)

        # Retrieve all users sorted by wins in descending order
        all_users = await user_collections.find().sort("game_wins", -1).to_list(length=None)
        # Filter out users with more wins than participations
        top_users = [user for user in all_users if user.get("game_wins", 0) <= user.get("game_participation", 0)]

        # Find the position of the calling user in the top_users list
        calling_user_position = None
        for idx, user in enumerate(top_users):
            if user["_id"] == int(user_id):
                calling_user_position = idx + 1
                break

        # Prepare the leaderboard message
        leaderboard_message = "<b>🎰 Таблица лидеров по победам (Топ 15):</b>\n\n"

        for idx, user in enumerate(top_users[:15]):
            username = await get_username(user['_id'])
            if username:
                username = username.replace("_", "&#95;")
            word_wins = get_wins_word(user['game_wins'])  # Получаем правильное слово для побед
            leaderboard_message += f"<b>{idx + 1}. {username} [</b><code>{user['status']}</code><b>] —</b> <code>{user['game_wins']}</code> <b>{word_wins}</b>\n"

        if int(user_id) == 1738263685:
            # Add the calling user's position
            leaderboard_message += f"\n<b>👤 Ваша позиция:</b>\n" \
                                           f"<b>{calling_user_position}.</b> <code>{user_id}</code> <b>—</b> <code>{user_wins}</code> <b>{get_wins_word(user_wins)}</b>"
        else:
            # Add the calling user's position
            leaderboard_message += f"\n<b>👤 Ваша позиция:</b>\n" \
                                       f"<b>{calling_user_position}.</b> <code>{user_id}</code> <b>—</b> <code>{user_wins}</code> <b>{get_wins_word(user_wins)}</b>"
        keyboard = types.InlineKeyboardMarkup()
        done = types.InlineKeyboardButton(text='Конкурсный топ побед 🥇', callback_data=f'wins_{user_id}')
        keyboard.add(done)

        await bot.edit_message_text(leaderboard_message, callback_query.message.chat.id,
                                    callback_query.message.message_id, parse_mode="HTML",
                                    reply_markup=keyboard)

    elif button_text.startswith('game_participation'):
        user_id = button_text.split('_')[2]
        click_user_id = callback_query.from_user.id
        await bot.answer_callback_query(callback_query.id, text="⌛ Загружаю топ...")

        if int(user_id) != click_user_id:
            await bot.answer_callback_query(callback_query.id, text="❌ Увы эта кнопка не ваша, а так хотелось...")
            return

        # Retrieve the user's status from the user_collections
        user_data = await user_collections.find_one({"_id": int(user_id)})
        user_participation = user_data.get("game_participation")

        # Retrieve all users sorted by participations in descending order
        top_users = await user_collections.find().sort("game_participation", -1).to_list(length=None)

        # Find the position of the calling user in the top_users list
        calling_user_position = None

        for idx, user in enumerate(top_users):
            if user["_id"] == int(user_id):
                calling_user_position = idx + 1
                break

        # Prepare the leaderboard message
        leaderboard_message = "<b>🀄 Таблица лидеров по участиям (Топ 15):</b>\n\n"

        for idx, user in enumerate(top_users[:15]):
            username = await get_username(user['_id'])
            if username:
                username = username.replace("_", "&#95;")
            word_participation = get_participation_word(
                user['game_participation'])  # Получаем правильное слово для участий
            leaderboard_message += f"<b>{idx + 1}. {username} [</b><code>{user['status']}</code><b>] —</b> <code>{user['game_participation']}</code> <b>{word_participation}</b>\n"

        # Add the calling user's position
        leaderboard_message += f"\n<b>👤 Ваша позиция:</b>\n" \
                               f"<b>{calling_user_position}.</b> <code>{user_id}</code> <b>—</b> <code>{user_participation}</code> <b>{get_participation_word(user_participation)}</b>"

        keyboard = types.InlineKeyboardMarkup()
        done = types.InlineKeyboardButton(text='Конкурсный топ участий 🍀', callback_data=f'participation_{user_id}')
        keyboard.add(done)

        await bot.edit_message_text(leaderboard_message, callback_query.message.chat.id,
                                    callback_query.message.message_id, parse_mode="HTML",
                                    reply_markup=keyboard)

    elif button_text.startswith('wins'):
        profile_user_id = button_text.split('_')[1]
        click_user_id = callback_query.from_user.id
        await bot.answer_callback_query(callback_query.id, text="⌛ Загружаю топ...")

        if int(profile_user_id) != click_user_id:
            await bot.answer_callback_query(callback_query.id, text="❌ Увы эта кнопка не ваша, а так хотелось...")
            return

        # Retrieve the user's status from the user_collections
        user_data = await user_collections.find_one({"_id": int(profile_user_id)})
        user_wins = user_data.get("wins")

        # Retrieve all users sorted by wins in descending order
        all_users = await user_collections.find().sort("wins", -1).to_list(length=None)

        # Filter out users with more wins than participations
        top_users = [user for user in all_users if user.get("wins", 0) <= user.get("participation", 0)]

        # Find the position of the calling user in the top_users list
        calling_user_position = None
        for idx, user in enumerate(top_users):
            if user["_id"] == int(profile_user_id):
                calling_user_position = idx + 1
                break

        # Prepare the leaderboard message
        leaderboard_message = "<b>🏅 Таблица лидеров по победам (Топ 15):</b>\n\n"
        for idx, user in enumerate(top_users[:15]):
            username = await get_username(user['_id'])
            if username:
                username = username.replace("_", "&#95;")
            word_wins = get_wins_word(user['wins'])  # Получаем правильное слово для побед
            leaderboard_message += f"<b>{idx + 1}. {username} [</b><code>{user['status']}</code><b>] —</b> <code>{user['wins']}</code> <b>{word_wins}</b>\n"
        if int(profile_user_id) == 1738263685:
            # Add the calling user's position
            leaderboard_message += f"\n<b>👤 Ваша позиция:</b>\n" \
                                   f"<b>0.</b> <code>{profile_user_id}</code> <b>—</b> <code>{user_wins}</code> <b>{get_wins_word(user_wins)}</b>"
        else:
            # Add the calling user's position
            leaderboard_message += f"\n<b>👤 Ваша позиция:</b>\n" \
                                   f"<b>{calling_user_position}.</b> <code>{profile_user_id}</code> <b>—</b> <code>{user_wins}</code> <b>{get_wins_word(user_wins)}</b>"
        keyboard = types.InlineKeyboardMarkup()
        done = types.InlineKeyboardButton(text='Игровой топ побед 🎰', callback_data=f'game_wins_{profile_user_id}')
        keyboard.add(done)
        await bot.edit_message_text(leaderboard_message, callback_query.message.chat.id,
                                    callback_query.message.message_id, parse_mode="HTML",
                                    reply_markup=keyboard)

    elif button_text.startswith('participation'):
        profile_user_id = button_text.split('_')[1]
        click_user_id = callback_query.from_user.id
        await bot.answer_callback_query(callback_query.id, text="⌛ Загружаю топ...")

        if int(profile_user_id) != click_user_id:
            await bot.answer_callback_query(callback_query.id, text="❌ Увы эта кнопка не ваша, а так хотелось...")
            return

        # Retrieve the user's status from the user_collections
        user_data = await user_collections.find_one({"_id": int(profile_user_id)})
        user_participation = user_data.get("participation")

        # Retrieve all users sorted by participations in descending order
        top_users = await user_collections.find().sort("participation", -1).to_list(length=None)

        # Find the position of the calling user in the top_users list
        calling_user_position = None
        for idx, user in enumerate(top_users):
            if user["_id"] == int(profile_user_id):
                calling_user_position = idx + 1
                break

        # Prepare the leaderboard message
        leaderboard_message = "<b>🍀 Таблица лидеров по участиям (Топ 15):</b>\n\n"
        for idx, user in enumerate(top_users[:15]):
            username = await get_username(user['_id'])
            if username:
                username = username.replace("_", "&#95;")
            word_participation = get_participation_word(
                user['participation'])  # Получаем правильное слово для участий
            leaderboard_message += f"<b>{idx + 1}. {username} [</b><code>{user['status']}</code><b>] —</b> <code>{user['participation']}</code> <b>{word_participation}</b>\n"

        # Add the calling user's position
        leaderboard_message += f"\n<b>👤 Ваша позиция:</b>\n" \
                               f"<b>{calling_user_position}.</b> <code>{profile_user_id}</code> <b>—</b> <code>{user_participation}</code> <b>{get_participation_word(user_participation)}</b>"
        keyboard = types.InlineKeyboardMarkup()
        done = types.InlineKeyboardButton(text='Игровой топ участий 🀄',
                                          callback_data=f'game_participations_{profile_user_id}')
        keyboard.add(done)

        await bot.edit_message_text(leaderboard_message, callback_query.message.chat.id,
                                    callback_query.message.message_id, parse_mode="HTML",
                                    reply_markup=keyboard)

    elif button_text == 'done':

        await bot.answer_callback_query(callback_query.id, text="Задача была выполнена успешно! ✔ ️")
        await bot.delete_message(callback_query.from_user.id, callback_query.message.message_id)  # Удаление сообщения

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

# Определение словарей статусов
stat_maps = [
    {1: "Начинающий 🍥", 5: "Юный победитель 🥮", 10: "Молодчик 🧋", 15: "Удачливый 🤞",
     25: "Лакер 🍀", 50: "Уникум ♾️"},
    {5: "Начало положено 🍤", 15: "Активный 🦈", 25: "Батарейка 🔋", 50: "Смотрящий 👀",
     100: "Невероятный 🧭"},
    {5: "Двойная радость 🎉", 25: "Стратегический взлет 🎯", 50: "Энтузиаст 🎴", 75: "Победный путь ✨",
     100: "Игровой мастер🌐", 200: "Венец побед 🌿", 300: "Игровая легенда 🎗️"},
    {15: "Любитель 🎲", 30: "Увлеченный 💥", 55: "Неутолимый 🧠", 110: "Стремительный 🕹️",
     250: "Ловец приключений 🏞️", 500: "Игровой афиционадо 🔭", 1000: "Бесконечная игра 🌀"}
]

async def update_statuses():
    while True:
        users = await user_collections.find().to_list(length=None)

        for user in users:
            user_id = user.get("_id")
            status_counts = [user.get("wins", 0), user.get("participation", 0),
                             user.get("game_wins", 0), user.get("game_participation", 0)]

            if user.get("status") in ["Создатель 🎭", "Тестер 🔰", "Админ 🚗"]:
                continue  # Пропустить пользователя с этим статусом

            matched_statuses = []
            for i in range(len(stat_maps)):  # Перебор словарей статусов
                for key in reversed(sorted(stat_maps[i].keys())):  # Проверка от большего числа
                    if status_counts[i] >= key:
                        matched_statuses.append((key, stat_maps[i][key]))
                        break  # После нахождения подходящего статуса, переходим к следующему словарю

            if not matched_statuses:
                status = None  # Не менять статус, если подходящих статусов нет
            else:
                status = max(matched_statuses)[1]  # Выбор статуса с наибольшим ключом

            if status:
                await user_collections.update_one({"_id": user_id}, {"$set": {"status": status}})

        await asyncio.sleep(1)

# async def update_statuses():
#     # Получение всех пользователей
#     users = await user_collections.find().to_list(length=None)
#
#     for user in users:
#         user_id = user["_id"]
#         print(user)
#         # Добавляем новые параметры с начальным значением 0
#         await user_collections.update_one({"_id": user_id},
#                                           {"$set": {"draws": 0, "game_wins": 0, "game_participation": 0}})

async def update_promo():
    while True:
        # Получение всех пользователей
        promo_codes = await promo_collection.find().to_list(length=None)

        for promo in promo_codes:
            promo_code = promo.get("_id")
            uses = promo.get("uses")

            visible = promo.get("visible")
            if visible in ["False"]:
                continue  # Пропустить пользователя с этим статусом

            if uses == 0:
                visible = "False"
                await promo_collection.update_one({"_id": promo_code}, {"$set": {"visible": visible}})

        # Подождать 1 секунду перед следующей проверкой и обновлением статусов
        await asyncio.sleep(1)

async def is_user_active(user_id):
    try:
        await bot.send_chat_action(user_id, types.ChatActions.TYPING)
        return True
    except:
        return False

async def remove_inactive_users():
    while True:
        # Get all users from the database
        users = await user_collections.find().to_list(length=None)

        for user in users:
            user_id = user.get("_id")
            is_active = await is_user_active(user_id)

            check_result =f"{user_id} has been checked. Result: {is_active}"
            with open(f"data/check_results.txt", "a") as file:
                file.write(check_result + "\n")

            if not is_active:
                # User is not active, save their information to a file and then remove from the database
                user_info = await user_collections.find_one({"_id": user_id})
                if user_info:
                    with open(f"data/user_{user_id}_info.json", "w") as file:
                        json.dump(user_info, file)
                    await user_collections.delete_one({"_id": user_id})
                    remove = f"User {user_id} removed from the database."
                    with open(f"data/check_results.txt", "a") as file:
                        file.write(remove + "\n")
                    print(f"User {user_id} removed from the database.")
        check_result = "The inspection was successfully completed 0"
        with open(f"data/check_results.txt", "a") as file:
            file.write(check_result + "\n")

        # Wait for a certain time before checking again
        await asyncio.sleep(3600)  # Check every hour

async def main():
    # Start the bot
    await dp.start_polling()

# Создание и запуск асинхронного цикла для функции проверки и выполнения розыгрыша конкурсов
contest_draw_loop = asyncio.get_event_loop()
contest_draw_task = contest_draw_loop.create_task(check_and_perform_contest_draw())

# Создание и запуск асинхронного цикла для функции обновления статусов пользователей
update_statuses_task = asyncio.get_event_loop().create_task(update_statuses())

# Создание и запуск асинхронного цикла для функции обновления статусов пользователей
update_promo_task = asyncio.get_event_loop().create_task(update_promo())

# Создание и запуск асинхронного цикла для функции обновления статусов пользователей
clear_database_task = asyncio.get_event_loop().create_task(remove_inactive_users())

# Создание и запуск асинхронного цикла для функции обновления статусов пользователей
bot_commands_tak = asyncio.get_event_loop().create_task(set_bot_commands())

# Запуск основного асинхронного цикла для работы бота
bot_loop = asyncio.get_event_loop()
bot_task = bot_loop.create_task(main())

# Запуск всех задач
loop = asyncio.get_event_loop()
tasks = asyncio.gather(bot_task, contest_draw_task, update_statuses_task, update_promo_task, clear_database_task, bot_commands_tak)
loop.run_until_complete(tasks)