import json
import logging
from callback_middleware import (
    callback_middleware, callback_middleware_inline_bot,
)

from config import (
    BOT_NAME,
    ADMIN_SPACE_NAME,
    USER_SPACE_NAME,
    BOT_SPACE_NAME,
    INLINE_USER_SETUP_SPACE_NAME,
    MESSAGES_SPACE_NAME
)
from tarantool_utils import (
    replace, select_index, exist_index,
    select, insert
)
from text_middleware import (
    text_middleware_inline_bot
)
import utilities as util

log = logging.getLogger(__name__)
main_bot_callbacks = {}


async def start(bot, event):
    """
    Обработка стартового сообщения

    :param bot: Объект бота
    :param event: Объект события
    :return: Текст с информацией о боте
    """

    # Получение пользователя
    user = event.data['from']['userId']

    replace(USER_SPACE_NAME, (
        USER_SPACE_NAME, '', '', ''
    ))

    await bot.send_text(
        chat_id=user,
        text=(
            "Привет, я создаю ботов-объявлений для админов каналов и групп\n\n"
            "Зачем нужен бот-объявлений:\n"
            "-Ты хочешь иметь единый анонимный канал постинга объявлений в свою группу или канал,"
            " это важно в случае нескольких админов ведущих группу или канал\n"
            "-Ты хочешь иметь возможность отслеживать изменения в объявлениях\n\n"
            "Инструкция для создания бота:\n"
            "1) Создай бота с помощью @metabot (подробнее по кнопке \"🤖 Инструкция @metabot\")\n"
            f"2) Перешли мне (@{BOT_NAME}) сообщение с информацией о своем новом боте от @metabot\n"
            "Сообщение выглядит примерно так:\n"
            "https://files.icq.net/get/0aE48000e9N8zzuD0O1VBt5ed266931ae"
        ),
        inline_keyboard_markup="[{}]".format(json.dumps([
            {"text": "🤖 Инструкция @metabot", "callbackData": "call_back_instruction"},
        ])))


async def callbacks(bot, event):
    """
    Обработка всех фукнций с обратным вызовом
    :param bot: Объект бота
    :param event: Объект события
    """

    user = event.data['from']['userId']

    callback_name = event.data['callbackData']

    if callback_name == 'callback_start':
        await bot.answer_callback_query(
            query_id=event.data['queryId'],
            text="",
            show_alert=False
        )
        await start(bot, event)

    else:
        await callback_middleware(
            bot,
            user,
            callback_name,
            event.data['queryId'],
            bot_callbacks=main_bot_callbacks,
            event=event
        )


async def message(bot, event):
    """
    Обрабокта сообщений
    :param bot: Объект бота
    :param event: Объект события
    """
    user = event.data['from']['userId']
    message_id = event.data['msgId']

    try:
        # Обработка пересланного сообщения с информацией о боте
        text = event.data['parts'][0]['payload']['message']['text']
    except KeyError:
        # Если информацию о боте скопировали
        text = event.data['text']

    try:
        secret_bot = util.parse_bot_info(text)
        if 'token' in secret_bot:
            if await util.validate_token(secret_bot['token']):
                replace(USER_SPACE_NAME, (
                    user,
                    secret_bot['token'], secret_bot['botId'], secret_bot['nick']
                ))
                await bot.send_text(
                    chat_id=user,
                    reply_msg_id=message_id,
                    text="Подключить бота?",
                    inline_keyboard_markup=json.dumps([
                        [{"text": "Подключить", "callbackData": "call_back_bot_connect"}],
                        [{"text": "Отмена", "callbackData": "callback_start"}],
                    ])
                )
            else:
                await bot.send_text(
                    chat_id=user,
                    reply_msg_id=message_id,
                    text="Токен недействителен\n"
                )
    except KeyError:
        pass


# Inline bot

async def start_inline_message(bot, event):
    """
    Приветственное сообщение для встроенного бота
    :param bot:
    :param event:
    :return:
    """

    try:
        bot_name = bot.name
        user_id = event.data['from']['userId']
        is_admin = exist_index(
            ADMIN_SPACE_NAME, (
                user_id, bot_name
            ), index='admin_bot'
        )
        start_message = select_index(
            BOT_SPACE_NAME, bot_name, index='bot'
        )[0][-2]

        if is_admin:
            util.set_null_admin_tuple(
                user_id, bot_name
            )
            is_active = util.is_admin_active(
                user_id, bot_name
            )
            if is_active:
                button = "⛔ ️Выключить"
                message_active = f'Остановить бота можно командой /off или по кнопке "{button}"'
            else:
                button = "Включить"
                message_active = f'Включить бота можно командой /on или по кнопке "{button}"'

            icq_channel = select_index(BOT_SPACE_NAME, bot_name, index='bot')[0][-1]
            if True or icq_channel:
                await bot.send_text(
                    chat_id=user_id,
                    text=(
                        f"Привет, я твой бот объявлений. Мой никнейм @{bot_name}\n\n"
                        "1) Чтобы настроить группу или канал для постинга объявлений, нажми \"Настроить объявления\"\n"
                        "2) Чтобы добавить или удалить админов,"
                        " которые могут публиковать объявления, нажми \"Настроить админов\"\n"
                        f"3) @{message_active}\n"
                        "4) Для публикации объявления просто пошли мне\n"
                        "5) Для редактирования объявления пришли в меня оригинальное сообщение из группы или канала\n\n"
                        "Возможности Бота-объявлений:\n"
                        "-Единый способ публикации объявлений в группу или канал\n"
                        "-Отслеживание истории изменений объявлений (все админы увидят, кто поменял объявление)"
                    ),
                    inline_keyboard_markup=json.dumps([
                        [{"text": "Настроить объявления", "callbackData": "callback_check_icq_channel"}],
                        [{"text": "Настроить админов", "callbackData": "callback_config_reply"}],
                        [{"text": f"{button}", "callbackData": "callback_switch_inline"}],
                    ])
                )
            else:
                await callback_middleware_inline_bot(
                    bot,
                    user_id,
                    'callback_add_new_icq_channels',
                    None,
                    bot_callbacks=main_bot_callbacks,
                    event=event
                )

        else:
            is_anon = False
            try:
                _, _, is_anon = select(INLINE_USER_SETUP_SPACE_NAME, user_id)[0]
            except IndexError:
                replace(INLINE_USER_SETUP_SPACE_NAME, (
                    user_id, bot_name, is_anon
                ))
            text = f"Отправить {'не ' if not is_anon else ''}анонимно"
            callback = f"callback_switch_anonymous-{is_anon}"
            await bot.send_text(
                chat_id=user_id,
                text=util.get_hello_message(bot_name),
                inline_keyboard_markup=json.dumps([
                    [{"text": text, "callbackData": callback}],
                ])
            )
    except IndexError:
        log.error("Ошибка получения стартового сообщения встроенного бота")


async def callbacks_inline(bot, event):
    """
    Обработка всех фукнций с обратным вызовом внутри бота
    :param bot: Объект бота
    :param event: Объект события
    """

    user = event.data['from']['userId']
    message_id = event.data['message'].get('msgId')
    text = event.data['message'].get('text')

    callback_name = event.data['callbackData']

    if callback_name == 'start_inline_message':
        await bot.answer_callback_query(
            query_id=event.data['queryId'],
            text="",
            show_alert=False
        )
        await start_inline_message(bot, event)

    else:
        await callback_middleware_inline_bot(
            bot, user, callback_name, event.data['queryId'], message_id=message_id,
            text=text, event=event
        )


async def message_inline(bot, event):
    """
    Обрабокта текстовых сообщений внутри встроенного бота
    :param bot: Объект бота
    :param event: Объект события
    """

    bot_name = bot.name

    user_id = event.data['from']['userId']
    user_name = util.extract_username(event.data)
    message_id = event.data['msgId']
    text = event.data['text']
    is_admin = util.is_admin(user_id, bot_name)
    if not text.startswith("/"):
        if is_admin:
            try:
                _, _, _, quiz, step, _ = select_index(
                    ADMIN_SPACE_NAME, (
                        user_id, bot_name
                    ), index='admin_bot'
                )[0]
                if quiz:
                    await text_middleware_inline_bot(
                        bot, user_id, message_id, quiz, text=text, step=step
                    )
                elif callback_middleware_inline_bot.is_edit_admin_enabled():
                    await callback_middleware_inline_bot.edit_admin(event.data)
            except IndexError:
                pass
        else:
            message_obj = await bot.send_text(
                chat_id=user_id,
                text=f"Что сделать с объявлением?",
                reply_msg_id=message_id,
                inline_keyboard_markup=json.dumps([
                    [{"text": "Опубликовть", "callbackData": f"callback_send_post-{message_id}"}],
                    [{"text": "Отмена", "callbackData": f"callback_delete_post"}],
                ])
            )
            admins = select_index(ADMIN_SPACE_NAME, bot_name, index='bot_nick')

            user = f"👤 @{user_name or user_id}"

            forwarded_id = []

            # for admin_info in admins:
            #     active = admin_info[2]
            #     if active:
            #         admin_id = admin_info[0]
            #         message_obj = await bot.send_text(
            #             chat_id=admin_id,
            #             text=f"Что сделать с объявлением?",
            #             reply_msg_id=message_id,
            #             inline_keyboard_markup=json.dumps([
            #                 [{"text": "Опубликовть", "callbackData": f"callback_send_post-{message_id}"}],
            #                 [{"text": "Отмена", "callbackData": f"callback_delete_post-{message_id}"}],
            #             ])
            #         )
            #         forwarded_id.append((admin_id, message_obj.get('msgId')))
            #
            # insert(MESSAGES_SPACE_NAME, (
            #     message_id, forwarded_id
            # ))


async def on_bot_for_admin(bot, event):
    """
    Включение бота для администратора
    :param bot:
    :param event:
    :return:
    """
    await sub_on_off(bot, event)


async def off_bot_for_admin(bot, event):
    """
    Выключение бота для администратора
    :param bot:
    :param event:
    :return:
    """
    await sub_on_off(bot, event)


async def sub_on_off(bot, event):

    bot_name = bot.name
    user_id = event.data['from']['userId']

    is_admin = exist_index(
        ADMIN_SPACE_NAME, (
            user_id, bot_name
        ), index='admin_bot'
    )

    if is_admin:
        messages = util.switch_admin_status(
            user_id, bot_name
        )

        await bot.send_text(
            chat_id=user_id,
            text=f"Бот теперь {messages}",
            inline_keyboard_markup=json.dumps([
                [{"text": "Назад", "callbackData": "start_inline_message"}],
            ])
        )