import json
import logging
import callback

from config import (
    ADMIN_SPACE_NAME,
    USER_SPACE_NAME,
)
import utilities as util
import db
log = logging.getLogger(__name__)
main_bot_callbacks = {}
cb_processor = callback.CallbackProcessor()


async def start(bot, event):
    # Получение пользователя
    user = event.data['from']['userId']
    inline_keyboard = [
        [{"text": "🤖 Инструкция @metabot", "callbackData": "instruction"}]
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
    callback_name = event.data['callbackData']
    if callback_name == 'callback_start':
        await bot.answer_callback_query(
            query_id=event.data['queryId'],
            text="",
            show_alert=False
        )
        await start(bot, event)
    else:
        cb_event = await callback.UserEvent.init(bot, event)
        await cb_processor(cb_event)


async def message(bot, event):
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
                db.replace(USER_SPACE_NAME, (
                    user,
                    secret_bot['token'], secret_bot['botId'], secret_bot['nick']
                ))
                await bot.send_text(
                    chat_id=user,
                    reply_msg_id=message_id,
                    text="Подключить бота?",
                    inline_keyboard_markup=json.dumps([
                        [{"text": "Подключить", "callbackData": "connect_bot"}],
                        [{"text": "Отмена", "callbackData": "callback_start"}],
                    ])
                )
            else:
                await bot.send_text(
                    chat_id=user,
                    reply_msg_id=message_id,
                    text="Токен недействителен\n"
                )
    except KeyError as e:
        log.error(e)


# Inline bot
async def start_inline_message(bot, event):
    cb_event = await callback.UserEvent.init(bot, event)
    await cb_processor.start_inline_message(cb_event)


async def callbacks_inline(bot, event):
    cb_event = await callback.UserEvent.init(bot, event)
    await cb_processor(cb_event)


async def message_inline(bot, event):
    cb_event = await callback.UserEvent.init(bot, event)
    bot_name = bot.name
    user_id = event.data['from']['userId']
    text = event.data['text'] if 'text' in event.data else ''
    is_admin = util.is_admin(user_id, bot_name)

    if event.from_chat != user_id:
        return

    if not text.startswith("/"):
        if is_admin:
            try:
                _, _, _, quiz, step, _ = db.select_index(
                    ADMIN_SPACE_NAME, (
                        user_id, bot_name
                    ), index='admin_bot'
                )[0]
                if quiz:
                    await cb_processor.set_icq_channel(cb_event)
                elif cb_event.wait_user_for is not None:
                    cb_event.callback_name = cb_event.wait_user_for
                    await cb_processor(cb_event)
                elif not util.is_bot_active(bot.token):
                    await bot.send_text(
                        chat_id=user_id,
                        text="Чтобы публиковать объявления, необходимо включить бота"
                    )
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
                    await cb_processor.reply_message(cb_event)
            except IndexError as e:
                log.error(e)
        else:
            await bot.send_text(
                chat_id=user_id,
                text="Вы не являетесь админом"
            )


async def bot_enable(bot, event):
    cb_event = await callback.UserEvent.init(bot, event)
    cb_processor.switch_inline(cb_event, True)
    await sub_on_off(bot, event)


async def bot_disable(bot, event):
    cb_event = await callback.UserEvent.init(bot, event)
    cb_processor.switch_inline(cb_event, False)
    await sub_on_off(bot, event)


async def sub_on_off(bot, event):
    user_id = event.data['from']['userId']
    is_active = util.is_bot_active(bot.token)
    await bot.send_text(
            chat_id=user_id,
            text=f"Бот теперь {'активен' if is_active else 'не активен'}",
            inline_keyboard_markup=json.dumps([
                [{"text": "Назад", "callbackData": "start_inline_message"}],
            ])
        )
