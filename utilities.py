import re
import logging
import aiohttp

import tarantool_utils as tarantool
from config import (
    ICQ_API,
    BOT_SPACE_NAME,
    ADMIN_SPACE_NAME,
    INLINE_USER_SETUP_SPACE_NAME
)

log = logging.getLogger(__name__)


def parse_bot_info(text: str) -> dict:
    bot_id = re.search(
        r"\d{9,10}", text
    )
    token = re.search(
        r"\d{3}.\d{10}.\d{10}:\d{9}", text
    )
    nick = re.search(
        r"nick: \w+", text
    )
    if not bot_id or not token:
        return {}
    return {
        'botId': bot_id[0],
        'token': token[0],
        'nick': nick[0].split(': ')[1]
    }


def parse_user_id(text: str) -> int:
    result = re.search(
        r"\d+", text
    )
    return result[0] if result else None


def parse_group_link(text: str) -> str:
    result = re.search(
        r"https://icq.im/\w+", text
    )
    return result[0] if result else None


def ltrim(text: str, prefix) -> str:
    if text.startswith(prefix):
        return text[len(prefix):]


def add_bot_admin(user, bot_nick):
    tarantool.insert(ADMIN_SPACE_NAME, (
        user.user_id, bot_nick, True, '', 0, ''
    ))


def get_hello_message(bot_nick) -> str:
    return tarantool.select_index(
        BOT_SPACE_NAME, bot_nick, index='bot'
    )[0][-2]


def is_admin_active(user_id, bot_nick) -> bool:
    return tarantool.select_index(
        ADMIN_SPACE_NAME, (user_id, bot_nick), index='admin_bot'
    )[0][2]


def switch_admin_status(user_id, bot_name) -> str:
    is_active = is_admin_active(
        user_id, bot_name
    )
    try:
        tarantool.update(ADMIN_SPACE_NAME, (user_id, bot_name), (('=', 2, not is_active),))
    except IndexError:
        log.error(
            "Ошибка при получении пользовательских настроек"
        )
    else:
        return "не активен" if is_admin_active else "активен"


def switch_inline_status(token, status: bool = None):
    bot_data = tarantool.select_index('bot_activity', token, 'bot')
    if bot_data:
        bot = bot_data[0]
        new_status = status if status is not None else not bot[1]
        tarantool.update('bot_activity', token, (('=', 1, new_status),))
        return new_status
    else:
        tarantool.insert('bot_activity', (token, True))
        return True


def is_bot_active(token):
    bot_data = tarantool.select_index('bot_activity', token, 'bot')
    return bot_data[0][1] if bot_data else switch_inline_status(token, True)


def get_bot_admins(bot_name):
    data = tarantool.select_index(ADMIN_SPACE_NAME, bot_name, 'bot_nick')
    return [x[0] for x in data]


def change_index_tuple_admin(user_id, bot_name, kwargs) -> None:
    try:
        admin_settings = tarantool.select_index(
            ADMIN_SPACE_NAME, (user_id, bot_name), index='admin_bot'
        )[0]
        for key, value in kwargs.items():
            admin_settings[int(key)] = value
        tarantool.replace(ADMIN_SPACE_NAME, admin_settings)
    except IndexError:
        log.error("Невозможно очистить стороннюю информаицю администратора")


def set_null_admin_tuple(user_id, bot_name) -> None:
    try:
        tarantool.update(ADMIN_SPACE_NAME,
                         (user_id, bot_name),
                         (
                             ('=', 3, ''),
                             ('=', 4, 0),
                             ("=", 5, '')
                         ))
    except IndexError:
        log.error("Невозможно очистить сторонную информаицю администратора")


def change_anonymous_status(user_id, status) -> None:
    try:
        tarantool.update(INLINE_USER_SETUP_SPACE_NAME, user_id, (('=', 2, status),))
    except IndexError:
        log.error("Ошибка при смене статуса анонима пользователя")
    else:
        return None


def parse_callback_name(callback: str):
    parts = callback.split('-')
    return {
        'callback': parts.pop(0),
        'params': parts
    }


def str_to_bool(s: str) -> bool:
    false_strings = [
        '0',
        'false',
        'disable'
    ]
    return s.lower() not in false_strings


def extract_username(event_data):
    print()
    return event_data['from']['nick'] if 'nick' in event_data['from'] else None


async def validate_token(token) -> bool:
    is_valid = re.match(r"\d{3}\.\d{10}\.\d{10}:\d{9}", token)
    if is_valid:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{ICQ_API}/self/get?token={token}") as response:
                response_data = await response.json()
                is_active = response_data['ok']
    return is_valid and is_active


def is_admin(user_id, bot_name):
    return tarantool.exist_index(
        ADMIN_SPACE_NAME, (
            user_id, bot_name
        ), index='admin_bot'
    )


def get_admin_uids(bot_name):
    data = tarantool.select_index(ADMIN_SPACE_NAME, bot_name, index='bot_nick')
    return [x[0] for x in data]


def get_bot_channel(bot_name):
    bot_data = tarantool.select_index(BOT_SPACE_NAME, bot_name, index='bot')
    return bot_data[0][6] if len(bot_data) and bot_data[0][6] else None


def set_bot_channel(uid, token, channel=''):
    tarantool.update(BOT_SPACE_NAME, (uid, token), (('=', 6, channel),))


def has_parts(event):
    return 'parts' in event.data


def is_forwarded(event):
    return has_parts(event) and event.data['parts'][0]['type'] == 'forward'


def get_fwd_id(event):
    return event.data['parts'][0]['payload']['message']['msgId']


def get_fwd_text(event):
    return event.data['parts'][0]['payload']['message']['text']


def get_fwd_chat(event):
    return event.data['parts'][0]['payload']['message']['chat']['chatId']


def is_fwd_from_channel(bot, event):
    is_fwd = False
    if is_forwarded(event):
        message_data = tarantool.select_index('messages', get_fwd_id(event), 'post')
        icq_channel = get_bot_channel(bot.name)
        if message_data[0][6] == icq_channel:
            is_fwd = True
    return is_fwd
