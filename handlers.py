import json
import logging
from callback_middleware import (
    callback_middleware, callback_middleware_inline_bot,
)

from config import (
    ADMIN_SPACE_NAME,
    USER_SPACE_NAME,
)
from tarantool_utils import (
    replace, select_index, exist_index
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
    inline_keyboard = [
        [{"text": "🤖 Инструкция @metabot", "callbackData": "call_back_instruction"}]
    ]
    await bot.send_text(
        chat_id=user,
        text=(
            "Привет, я создаю ботов-объявлений для админов каналов и групп\n\n"
            "Зачем нужен бот объявлений:\n"
            "- Ты хочешь иметь единый анонимный канал постинга объявлений в свою группу или канал"
            " Это важно в случае нескольких админов ведущих группу или канал\n"
            "- Ты хочешь иметь возможность отслеживать изменения в объявлениях\n\n"
            "Инструкция для создания бота:\n"
            "1) Создай бота с помощью @metabot (подробнее по кнопке \"🤖 Инструкция @metabot\")\n"
            f"2) Перешли мне (@{bot.name}) сообщение с информацией о своем новом боте от @metabot\n"
            "Сообщение выглядит примерно так:\n"
            "https://files.icq.net/get/0aE48000e9N8zzuD0O1VBt5ed266931ae"
        ),
        inline_keyboard_markup=json.dumps(inline_keyboard)
    )


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

        if is_admin:
            util.set_null_admin_tuple(
                user_id, bot_name
            )
            is_active = util.is_admin_active(
                user_id, bot_name
            )
            if is_active:
                button = "⛔ ️Выключить"
                button_action = 'disable'
                message_active = f'Остановить бота можно командой /off или по кнопке "{button}"'
            else:
                button = "Включить"
                button_action = 'enable'
                message_active = f'Включить бота можно командой /on или по кнопке "{button}"'

            await bot.send_text(
                chat_id=user_id,
                text=(
                    f"Привет, я твой бот объявлений. Мой никнейм @{bot_name}\n\n"
                    "1) Чтобы настроить группу или канал для постинга объявлений, нажми \"Настроить объявления\"\n"
                    "2) Чтобы добавить или удалить админов,"
                    " которые могут публиковать объявления, нажми \"Настроить админов\"\n"
                    f"3) @{message_active}\n"
                    "4) Для публикации объявления просто пришли мне его текст\n"
                    "5) Для редактирования объявления перешли в меня оригинальное сообщение из группы или канала\n\n"
                    "Возможности бота объявлений:\n"
                    "- Единый способ публикации объявлений в группу или канал\n"
                    "- Отслеживание истории изменений объявлений (все админы увидят, кто поменял объявление)"
                ),
                inline_keyboard_markup=json.dumps([
                    [{"text": "Настроить объявления", "callbackData": "callback_check_icq_channel"}],
                    [{"text": "Настроить админов", "callbackData": "callback_config_reply"}],
                    [{"text": f"{button}", "callbackData": f"callback_switch_inline-{button_action}"}],
                ])
            )
        else:
            await bot.send_text(
                chat_id=user_id,
                text="Привет. Этот бот позволяет отправлять объявления в привязанный канал или группу. "
                     "К сожалению, эта функция доступна только для администраторов бота."
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
    message_id = event.data['msgId']
    text = event.data['text'] if 'text' in event.data else ''
    is_admin = util.is_admin(user_id, bot_name)

    if event.from_chat != user_id:
        return

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
                elif not util.is_bot_active(bot.token):
                    await bot.send_text(
                        chat_id=user_id,
                        text="Чтобы публиковать объявления, необходимо включить бота"
                    )
                elif callback_middleware_inline_bot.is_edit_admin_enabled(user_id):
                    await callback_middleware_inline_bot.edit_admin(event.data)
                # elif callback_middleware_inline_bot.is_edit_msg_enabled(user_id):
                #     await callback_middleware_inline_bot.edit_message(event.data)
                #     await callback_middleware_inline_bot.callback_reply_message(bot, event)
                elif not util.get_bot_channel(bot_name):
                    await bot.send_text(
                        chat_id=user_id,
                        text="⚠️ Чтобы в группу или канал начали публиковаться объявления,"
                             " нужно сначала его настроить",
                        inline_keyboard_markup=json.dumps([
                            [{"text": "Настроить объявления", "callbackData": "callback_check_icq_channel"}]
                        ])
                    )
                else:
                    # reply message with control buttons
                    await callback_middleware_inline_bot.callback_reply_message(bot, event)

            except IndexError:
                pass
        else:
            await bot.send_text(
                chat_id=user_id,
                text="Вы не являетесь админом"
            )


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
