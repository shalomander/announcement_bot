import json
import logging
from tarantool.error import DatabaseError

from config import (
    BOT_SPACE_NAME,
    USER_SPACE_NAME,
    ADMIN_SPACE_NAME,
    LINK_ICQ
)
from response import start_message_inline_bot
import db
import utilities as util

log = logging.getLogger(__name__)

main_bot_funcs = {}


class UserEvent:

    @classmethod
    async def init(cls, bot, event, *args, **kwargs):
        self = UserEvent()
        self.bot = bot
        self.event = event
        self.event_type = event.type.value
        self.user_id = event.data['from']['userId']
        msg_data = self._get_message_data()
        self.message_id = msg_data['id']
        self.message_text = msg_data['text']
        self.parts = msg_data['parts']
        self.chat_id = msg_data['chat_id']
        self.keyboard = []
        self.mentions = []
        self.forwards = []
        self.files = []
        self._parse_parts()
        self.query_id = self._get_query_id()
        self.callback_data = event.data['callbackData'] if 'callbackData' in event.data else ''
        cb_data = self._process_callback_name()
        self.callback_name = cb_data['callback']
        self.callback_params = cb_data['params']
        wait_user_for = self._get_user_for()
        self.wait_user_for = wait_user_for['action']
        self.wait_user_for_params = wait_user_for['params']
        self.args = args
        self.kwargs = kwargs
        return self

    def _get_user_for(self):
        action = None
        params = None
        wait_user_for = db.select('wait_user_for', self.user_id)
        if wait_user_for:
            params = wait_user_for[0][1].split(';')
            action = params.pop(0)
            db.delete('wait_user_for', self.user_id)
        return {'action': action, 'params': params}

    def _process_callback_name(self):
        parts = self.callback_data.split(';')
        return {
            'callback': parts.pop(0),
            'params': parts
        }

    def _get_message_data(self):
        msg_data = self.event.data
        if self.event_type == 'callbackQuery':
            msg_data = self.event.data['message']
        text = msg_data['text'] if 'text' in msg_data else ''
        msg_id = msg_data['msgId']
        parts = msg_data['parts'] if 'parts' in msg_data else []
        chat_id = msg_data['chat']['chatId']
        return {'id': msg_id,
                'text': text,
                'parts': parts,
                'chat_id': chat_id}

    def _get_query_id(self):
        return self.event.data['queryId'] if self.event_type == 'callbackQuery' else None

    def _parse_parts(self):
        for part in self.parts:
            if part['type'] == 'inlineKeyboardMarkup':
                self.keyboard.extend(part['payload'])
            elif part['type'] == 'mention':
                self.mentions.append(part['payload'])
            elif part['type'] == 'forward':
                self.forwards.append(part['payload'])
            elif part['type'] == 'file':
                self.files.append(part['payload'])


class CallbackProcessor:

    async def __call__(self, cb_event: UserEvent, **kwargs):
        try:
            coro = await getattr(CallbackProcessor, cb_event.callback_name)(cb_event)
            await self.set_null_callback(cb_event) if not coro else await coro()
        except AttributeError as e:
            log.error(e)

    @staticmethod
    async def set_null_callback(cb_event):
        if cb_event.query_id:
            await cb_event.bot.answer_callback_query(
                query_id=cb_event.query_id,
                text="",
                show_alert=False
            )

    @staticmethod
    async def set_answer_callback(cb_event, text):
        if cb_event.query_id:
            await cb_event.bot.answer_callback_query(
                query_id=cb_event.query_id,
                text=text,
                show_alert=False
            )

    @staticmethod
    async def instruction(cb_event):
        await cb_event.bot.send_text(
            chat_id=cb_event.user_id,
            text=(
                f"Как создать бота, используя @metabot:\n"
                f"1) Открой @metabot\n"
                f"2) Создай нового бота при помощи команды /newbot\n"
                f"3) Придумай никнейм своему боту-помощнику. "
                f'Ник обязательно должен заканчиваться на “bot” 👇\n'
                f"https://files.icq.net/get/0dQlW000hNBmuU2TvlRRUP5ed263b51ae\n"
                f"4) Отправь команду /setjoingroups после успешного создания бота 👇\n"
                f"https://files.icq.net/get/0dC9G000CFJARbEleLxsxl5ed263de1ae\n"
                f"Следующие шаги 5-7 не обязательны и нужны для доп. настройки твоего бота:\n"
                f"5) Придумай имя своему боту /setname 👇\n"
                f"https://files.icq.net/get/0dYaO000MquODLncJY3uMB5ed2642f1ae\n"
                f"6) Укажи описание для своего бота /setdescription 👇\n"
                f"https://files.icq.net/get/0dUaY000WcqonvlVrDFAcS5ed264621ae\n"
                f"7) Пришли аватарку для своего бота /setuserpic 👇\n"
                f"https://files.icq.net/get/0dKj8000frHsEa2YyUS1zE5ed266211ae\n"
                f"⚠️ Важно: перешли @{cb_event.bot.name} сообщение с данными о своем боте 👇\n"
                f"https://files.icq.net/get/0aE48000e9N8zzuD0O1VBt5ed266931ae"
            )
        )

    @staticmethod
    async def connect_bot(cb_event):
        # some dark magic from prev developer
        # needs rework but has no time
        bot_data = db.select(USER_SPACE_NAME, cb_event.user_id)
        if bot_data:
            _, bot_token, bot_id, bot_nick = db.select(USER_SPACE_NAME, cb_event.user_id)[0]
            try:
                db.insert(BOT_SPACE_NAME, (
                    cb_event.user_id,
                    bot_token,
                    bot_id,
                    bot_nick,
                    False,
                    start_message_inline_bot,
                    ''
                ))
                db.insert(ADMIN_SPACE_NAME, (
                    cb_event.user_id, bot_nick, True, '', 0, ''
                ))
                await main_bot_funcs['start'](bot_nick)
                if bot_id and bot_nick:
                    message_text = (f"Твой бот @{bot_nick} готов к работе!\n"
                                    f"Открой @{bot_nick} для получения сообщений и настройки "
                                    f"бота для пересылки сообщений в группы или каналы")
                    inline_keyboard = [
                        [{"text": "Открыть бота", "url": f"https://icq.im/{bot_nick}"}],
                        [{"text": "Создать еще одного бота", "callbackData": "callback_start"}]
                    ]
            except DatabaseError:
                message_text = "Бот с таким botId уже был добавлен"
                inline_keyboard = [
                    [{"text": "Попробовать еще раз", "callbackData": "callback_start"}]
                ]
            await cb_event.bot.edit_text(
                chat_id=cb_event.user_id,
                msg_id=cb_event.message_id,
                text=message_text,
                inline_keyboard_markup=json.dumps(inline_keyboard)
            )

    @staticmethod
    async def switch_inline(cb_event, new_state=None):
        new_bot_state = cb_event.callback_params[0] if len(cb_event.callback_params) else new_state
        util.switch_inline_status(cb_event.bot.token, util.str_to_bool(new_bot_state))
        is_active = util.is_bot_active(cb_event.bot.token)
        if is_active:
            admin_message = f"Админ @[{cb_event.user_id}] включил бота"
            callback_message = "Бот включен"
            switch_button_text = '⛔ ️Выключить'
            switch_button_action = 'disable'

        else:
            admin_message = f"Админ @[{cb_event.user_id}] выключил бота"
            callback_message = "Бот выключен"
            switch_button_text = 'Включить'
            switch_button_action = 'enable'
        buttons = cb_event.keyboard
        buttons[-1] = [
            {"text": f"{switch_button_text}", "callbackData": f"switch_inline;{switch_button_action}"}]
        await cb_event.bot.edit_text(
            chat_id=cb_event.chat_id,
            msg_id=cb_event.message_id,
            text=cb_event.message_text,
            inline_keyboard_markup=json.dumps(buttons)
        )
        # send notification to other admins
        admins = util.get_admin_uids(cb_event.bot.name)
        admins.remove(cb_event.user_id)
        for admin in admins:
            await cb_event.bot.send_text(
                chat_id=admin,
                text=admin_message
            )

        return CallbackProcessor.set_answer_callback(cb_event, callback_message)

    @staticmethod
    async def check_icq_channel(cb_event):
        try:
            icq_channel = util.get_bot_channel(cb_event.bot.name)
            if icq_channel:
                await cb_event.bot.send_text(
                    cb_event.user_id,
                    text=(
                        f"Бот уже подключен к каналу {LINK_ICQ}/{icq_channel}\n"
                        "Заменить на новый канал?"
                    ),
                    inline_keyboard_markup=json.dumps([
                        [{"text": "Да", "callbackData": "add_new_icq_channel"}],
                        [{"text": "Нет", "callbackData": "start_inline_message"}],
                    ])
                )
            else:
                await CallbackProcessor.add_new_icq_channel(cb_event)
        except IndexError:
            log.error("Ошибка при проверке наличия канала или группы")

    @staticmethod
    async def add_new_icq_channel(cb_event):
        util.change_index_tuple_admin(cb_event.user_id, cb_event.bot.name, {
            '3': "set_icq_channel",
            "4": 1
        })
        await cb_event.bot.send_text(
            cb_event.user_id,
            text=(
                "Чтобы в группу или канал начали публиковаться объявления, нужно:\n"
                f"1) Добавить @{cb_event.bot.name} в группу или канал\n"
                '2) Сделать бота администратором\n'
                "3) Прислать сюда ссылку на группу или канал\n"
                "⚠️ ВАЖНО: группа или канал может быть только один"
            ),
            inline_keyboard_markup=json.dumps([
                [{"text": "Ошибка при добавлении", "callbackData": "add_icq_channel_error"}],
                [{"text": "Отмена", "callbackData": "start_inline_message"}],
            ])
        )

    @staticmethod
    async def add_icq_channel_error(cb_event):
        inline_keyboard = [
            [{"text": "Назад", "callbackData": "add_new_icq_channel"}],
        ]
        await cb_event.bot.send_text(
            cb_event.user_id,
            text=(
                "Если не получается добавить бота в группу или канал, нужно:\n"
                "1) Открыть @metabot\n"
                "2) Отправить команду /setjoingroups и послать никнейм вашего бота\n"
                "https://files.icq.net/get/0dC9G000CFJARbEleLxsxl5ed263de1ae"
            ),
            inline_keyboard_markup=json.dumps(inline_keyboard)
        )

    @staticmethod
    async def config_reply(cb_event):
        inline_keyboard = [
            [{"text": "Добавить админa", "callbackData": "reply_add_admin"}],
            [{"text": "Удалить админа", "callbackData": "reply_remove_admin"}],
            [{"text": "Отмена", "callbackData": "start_inline_message"}],
        ]
        await cb_event.bot.send_text(
            cb_event.user_id,
            text=(
                "Удалить или добавить администраторов бота:\n"
                "1) Добавить админов, которые смогут публиковать объявления и будут получать сообщения"
                " об изменении и публикации новых объявлений через бота - \"Добавить админа\"\n"
                "2) Удалить админов - \"Удалить админа\""
            ),
            inline_keyboard_markup=json.dumps(inline_keyboard)
        )

    @staticmethod
    async def reply_add_admin(cb_event):
        util.set_wait_user_for(cb_event.user_id, 'add_admin')
        inline_keyboard = [
            [{"text": "Назад", "callbackData": "config_reply"}],
        ]
        await cb_event.bot.send_text(
            cb_event.user_id,
            text=(
                "Чтобы добавить администратора, пришли мне ссылку на его профиль."
            ),
            inline_keyboard_markup=json.dumps(inline_keyboard)
        )

    @staticmethod
    async def add_admin(cb_event):
        if cb_event.mentions:
            for mention in cb_event.mentions:
                try:
                    db.insert(ADMIN_SPACE_NAME, (
                        mention['userId'], cb_event.bot.name, True, '', 0, ''
                    ))
                    await cb_event.bot.send_text(
                        cb_event.user_id,
                        text=(
                            f"Пользователь @[{mention['userId']}] назначен дминистратором бота.\n"
                            f"⚠️ ВАЖНО: пользователь должен САМ открыть @{cb_event.bot.name} и стартовать его, "
                            "чтобы начать получать сообщения"
                        )
                    )
                except DatabaseError:
                    await cb_event.bot.send_text(
                        cb_event.user_id,
                        text=(
                            f"Не удалось добавить админа @[{mention['userId']}]"
                        )
                    )
        else:
            await cb_event.bot.send_text(
                cb_event.user_id,
                text=(
                    "Ошибка!\n\n"
                    "Пользователь не найден или не существует."
                )
            )

    @staticmethod
    async def reply_remove_admin(cb_event):
        util.set_wait_user_for(cb_event.user_id, 'remove_admin')
        inline_keyboard = [
            [{"text": "Назад", "callbackData": "config_reply"}],
        ]
        admin_list_text = "Администраторы:\n"
        admin_list_index = 1
        admins = util.get_admin_uids(cb_event.bot.name)
        for admin in admins:
            admin_list_text += f"{admin_list_index}) @[{admin}]\n"
            admin_list_index += 1
        await cb_event.bot.send_text(
            cb_event.user_id,
            text=(
                "Чтобы удалить администратора, пришли мне ссылку на его профиль.\n\n "
                f"{admin_list_text}\n"
            ),
            inline_keyboard_markup=json.dumps(inline_keyboard)
        )

    @staticmethod
    async def remove_admin(cb_event):
        if cb_event.mentions:
            admins = util.get_admin_uids(cb_event.bot.name)
            if cb_event.user_id not in admins:
                return await cb_event.bot.send_text(
                    cb_event.user_id,
                    text=(
                        "Вы не являетесь администратором этого бота"
                    )
                )
            for mention in cb_event.mentions:
                admin_id = mention['userId']
                if cb_event.user_id == admin_id:
                    return await cb_event.bot.send_text(
                        cb_event.user_id,
                        text=(
                            "Вы не можете удалить себя из списка администраторов."
                        )
                    )
                try:
                    if len(db.select(ADMIN_SPACE_NAME, (admin_id, cb_event.bot.name))):
                        db.delete(ADMIN_SPACE_NAME, (admin_id, cb_event.bot.name))
                        await cb_event.bot.send_text(
                            cb_event.user_id,
                            text=(
                                f"Пользователь @[{admin_id}] удален из списка администраторов бота."
                            )
                        )
                    else:
                        await cb_event.bot.send_text(
                            cb_event.user_id,
                            text=(
                                f"Пользователь @[{admin_id}] не является администратором этого бота"
                            )
                        )
                except DatabaseError as e:
                    log.error(e)

    @staticmethod
    async def set_channel_success(cb_event):
        try:
            icq_channel = db.select(
                ADMIN_SPACE_NAME, (cb_event.user_id, cb_event.bot.name)
            )[0][5]
            # icq_channel = util.get_bot_channel(cb_event.bot.name)
            response = await cb_event.bot.get_chat_admins(icq_channel)
            if not response.get('ok'):
                inline_keyboard = [
                    [{"text": "Повторить", "callbackData": "set_channel_success"}],
                    [{"text": "Отмена", "callbackData": "start_inline_message"}],
                ]
                await cb_event.bot.send_text(
                    cb_event.user_id,
                    text=(
                        "Ошибка подключения объявлений\n\n"
                        f"Бот @{cb_event.bot.name} не добавлен в группу или канал или не имеет право писать туда.\n\n"
                    ),
                    inline_keyboard_markup=json.dumps(inline_keyboard)
                )
            else:
                util.set_null_admin_tuple(cb_event.user_id, cb_event.bot.name)
                bot_info = util.get_bot_data(cb_event.bot.name)
                if bot_info:
                    bot_info[6] = icq_channel
                    db.replace(BOT_SPACE_NAME, bot_info)
                    inline_keyboard = [
                        [{"text": "Назад", "callbackData": "start_inline_message"}],
                    ]
                    await cb_event.bot.send_text(
                        cb_event.user_id,
                        text=(
                            "Объявления успешно настроены.\n\n"
                            "Теперь, чтобы опубликовать сообщение, отправь его в меня, "
                            "и я предложу тебе его опубликовать и запинить"
                        ),
                        inline_keyboard_markup=json.dumps(inline_keyboard)
                    )
        except IndexError as e:
            log.error(e)

    @staticmethod
    async def send_post(cb_event):
        if util.is_admin(cb_event.user_id, cb_event.bot.name):
            icq_channel = util.get_bot_channel(cb_event.bot.name)
            response = await cb_event.bot.get_chat_admins(icq_channel)
            if not response.get('ok'):
                util.set_bot_channel(cb_event.user_id, cb_event.bot.token)
                await cb_event.bot.send_text(
                    chat_id=cb_event.user_id,
                    text="⚠️ Чтобы в группу или канал начали публиковаться объявления,"
                         " нужно сначала его настроить",
                    inline_keyboard_markup=json.dumps([
                        [{"text": "Настроить объявления", "callbackData": "check_icq_channel"}]
                    ])
                )
            else:
                original_msg_id = cb_event.callback_params[0]
                try:
                    message_data = db.select('messages', original_msg_id)
                    if message_data:
                        msg_id, msg_text, msg_sender, msg_reply, msg_controls, *_ = message_data[0]
                        # send original text to target channel
                        target_msg = await cb_event.bot.send_text(
                            chat_id=icq_channel,
                            text=msg_text
                        )
                        if target_msg.get('ok'):
                            msg_posted = target_msg['msgId']
                            db.update('messages', msg_id, (('=', 5, msg_posted), ('=', 6, icq_channel)))

                            # forward original message to admins
                            admins = util.get_admin_uids(cb_event.bot.name)
                            admins.remove(cb_event.user_id)
                            for admin in admins:
                                await cb_event.bot.send_text(
                                    chat_id=admin,
                                    text=f"Админ @[{cb_event.user_id}] опубликовал объявление",
                                    forward_chat_id=msg_sender,
                                    forward_msg_id=msg_id
                                )

                            # edit controls message
                            inline_keyboard = [
                                [{"text": "Закрепить в чате?", "callbackData": f"pin_msg;{msg_posted}"}],
                                [{"text": "Готово", "callbackData": f"disable_buttons;{msg_controls}"}],
                            ]
                            await cb_event.bot.edit_text(
                                chat_id=msg_sender,
                                msg_id=msg_controls,
                                text="Опубликовано! Уведомление о публикации отправлено всем админам",
                                inline_keyboard_markup=json.dumps(inline_keyboard)
                            )
                except IndexError as e:
                    log.error(e)
        else:
            await cb_event.bot.send_text(
                chat_id=cb_event.user_id,
                text="Вас нет в списке администраторов. Вы не можете публиковать объявления"
            )

    @staticmethod
    async def delete_post(cb_event):
        original_msg_id = cb_event.callback_params[0]
        try:
            message_data = db.select('messages', original_msg_id)
            if message_data:
                msg_id, msg_text, msg_sender, msg_reply, msg_controls, *_ = message_data[0]
                await cb_event.bot.delete_messages(
                    chat_id=msg_sender,
                    msg_id=msg_controls
                )
                await cb_event.bot.delete_messages(
                    chat_id=msg_sender,
                    msg_id=msg_reply
                )
        except IndexError as e:
            log.error(e)

    @staticmethod
    async def delete_fwd(cb_event):
        try:
            icq_channel = util.get_bot_channel(cb_event.bot.name)
            post_id = cb_event.callback_params[0]
            message_data = db.select('messages', post_id)
            if message_data:
                message = message_data[0]
                # delete forwarded message
                await cb_event.bot.delete_messages(
                    chat_id=icq_channel,
                    msg_id=post_id
                )

                # delete replied message
                await cb_event.bot.delete_messages(
                    chat_id=cb_event.user_id,
                    msg_id=message[3]
                )

                # forward notification to admins
                admins = util.get_admin_uids(cb_event.bot.name)
                admins.remove(cb_event.user_id)
                for admin in admins:
                    await cb_event.bot.send_text(
                        chat_id=admin,
                        text=f"@[{cb_event.user_id}] удалил сообщение:\n"
                             f"{message[1]}"
                    )
                # edit replied message
                await CallbackProcessor.disable_buttons(cb_event, True, target_id=message[4])
        except IndexError as e:
            log.error(e)

    @staticmethod
    async def edit_fwd(cb_event):
        post_id = cb_event.callback_params[0]
        util.set_wait_user_for(cb_event.user_id, f'edit_message;{post_id}')
        inline_keyboard = [
            [{"text": "Назад", "callbackData": f"reply_message;{post_id}"}]
        ]
        await cb_event.bot.send_text(
            chat_id=cb_event.user_id,
            text="Пришли мне отредактированный текст сообщения целиком.",
            inline_keyboard_markup=json.dumps(inline_keyboard)
        )

    @staticmethod
    async def edit_message(cb_event):
        old_message_id = cb_event.wait_for_user_params[0]
        new_message_id = cb_event.message_id
        inline_keyboard = [
            [{"text": "Опубликовать правки", "callbackData": f"update_post;{old_message_id}"}],
            [{"text": "Опубликовать как новое", "callbackData": f"send_post;{new_message_id}"}],
            [{"text": "Назад", "callbackData": f"reply_message;{old_message_id}"}],
        ]
        await cb_event.bot.send_text(
            chat_id=cb_event.user_id,
            reply_msg_id=new_message_id,
            text="Что сделать с исправленным объявлением?",
            inline_keyboard_markup=json.dumps(inline_keyboard)
        )

    @staticmethod
    async def update_post(cb_event):
        post_id = cb_event.callback_params[0]
        cb_id = cb_event.message_id
        update_message_data = db.select_index('messages', post_id, 'post')
        cb_message_data = db.select_index('messages', cb_id, 'controls')
        icq_channel = util.get_bot_channel(cb_event.bot.name)
        if update_message_data and cb_message_data:
            message = update_message_data[0]
            cb_message = cb_message_data[0]
            old_text = message[1]
            new_text = cb_message[1]
            await cb_event.bot.edit_text(
                chat_id=icq_channel,
                msg_id=post_id,
                text=new_text
            )
            db.update('messages', message[0], (('=', 1, new_text),))

            # forward original message to admins
            admins = util.get_admin_uids(cb_event.bot.name)
            admins.remove(cb_event.user_id)
            for admin in admins:
                await cb_event.bot.send_text(
                    chat_id=admin,
                    forward_chat_id=cb_event.user_id,
                    forward_msg_id=cb_event.forwards[0]['message']['msgId'],
                    text=f"Оригинальное сообщение:\n{old_text}"
                )

            # edit replied message
            replied_id = cb_event.message_id
            inline_keyboard = [
                [{"text": "Закрепить в чате?", "callbackData": f"pin_msg;{post_id}"}],
                [{"text": "Готово", "callbackData": f"disable_buttons;{replied_id}"}],
            ]
            await cb_event.bot.edit_text(
                chat_id=cb_event.user_id,
                msg_id=replied_id,
                text="Опубликовано! Уведомление о публикации отправлено всем админам",
                inline_keyboard_markup=json.dumps(inline_keyboard)
            )

    @staticmethod
    async def pin_msg(cb_event):
        try:
            msg_posted = cb_event.callback_params[0]
            message_data = db.select_index('messages', msg_posted, index='post')
            if message_data:
                msg_id, msg_text, msg_sender, msg_reply, msg_controls, *_ = message_data[0]
                icq_channel = util.get_bot_channel(cb_event.bot.name)
                # pin target message
                await cb_event.bot.pin_message(
                    chat_id=icq_channel,
                    msg_id=msg_posted
                )
                # send notification to other admins
                admins = util.get_admin_uids(cb_event.bot.name)
                admins.remove(cb_event.user_id)
                for admin in admins:
                    await cb_event.bot.send_text(
                        chat_id=admin,
                        forward_chat_id=icq_channel,
                        forward_msg_id=msg_posted,
                        text=f"Aдмин @[{cb_event.user_id}] закрепил сообщение в чате"
                    )
                # edit controls in replied message
                await cb_event.bot.edit_text(
                    chat_id=msg_sender,
                    msg_id=msg_controls,
                    text="Закреплено в чате! Уведомление отправлено всем админам",
                )
        except IndexError as e:
            log.error(e)

    @staticmethod
    async def disable_buttons(cb_event, deleted=False, target_id=None):
        controls_id = target_id or cb_event.callback_params[0] if cb_event.callback_params else cb_event.message_id
        text = cb_event.message_text
        await cb_event.bot.edit_text(
            chat_id=cb_event.chat_id,
            msg_id=controls_id,
            text='Удалено' if deleted else text
        )

    @staticmethod
    async def reply_message(cb_event):
        is_callback = len(cb_event.callback_params) > 0
        message_id = cb_event.message_id if not is_callback else cb_event.callback_params[0]
        if cb_event.files:
            message_text = f"https://files.icq.net/get/{cb_event.files[0]['fileId']} {cb_event.files[0]['caption']}"
        else:
            message_text = cb_event.message_text
        message_chat_id = cb_event.user_id
        is_fwd = is_callback or util.is_fwd_from_channel(cb_event.bot.name, cb_event.event)
        is_edit = cb_event.wait_user_for == 'edit_message'
        inline_keyboard = []
        send_button_text = "Опубликовать"

        if is_fwd:
            if not is_callback:
                message_id = cb_event.forwards[0]['message']['msgId']
                message_text = cb_event.forwards[0]['message']['text']
                message_chat_id = cb_event.forwards[0]['message']['chat']['chatId']
            inline_keyboard.append([{"text": "Редактировать",
                                     "callbackData": f"edit_fwd;{message_id}"}])
            inline_keyboard.append([{"text": "Удалить",
                                     "callbackData": f"delete_fwd;{message_id}"}])
            send_button_text = "Продублировать как новое"

        if is_edit:
            edit_message_id = cb_event.wait_user_for_prams[0]
            inline_keyboard.append([{"text": "Опубликовать правки",
                                     "callbackData": f"update_post;{edit_message_id}"}])
            send_button_text = "Опубликовать как новое"

        inline_keyboard.append([{"text": send_button_text, "callbackData": f"send_post;{message_id}"}])
        inline_keyboard.append([{"text": "Отмена", "callbackData": f"delete_post;{message_id}"}])

        reply_msg = None
        if is_fwd:
            if not is_callback:
                reply_msg = await cb_event.bot.send_text(
                    chat_id=cb_event.user_id,
                    forward_msg_id=message_id,
                    forward_chat_id=message_chat_id,
                    text=''
                )
        else:
            reply_msg = await cb_event.bot.send_text(
                chat_id=cb_event.user_id,
                reply_msg_id=message_id,
                text=''
            )
        controls_msg = await cb_event.bot.send_text(
            chat_id=cb_event.user_id,
            text="Что сделать с объявлением",
            inline_keyboard_markup=json.dumps(inline_keyboard)
        )
        if reply_msg and reply_msg.get('ok') and controls_msg.get('ok'):
            reply_id = reply_msg['msgId']
            controls_id = controls_msg['msgId']
            db.insert('messages', (message_id,
                                   message_text,
                                   cb_event.user_id,
                                   reply_id,
                                   controls_id,
                                   '',
                                   '')
                      )

    @staticmethod
    async def set_icq_channel(cb_event):
        try:
            channel_id = cb_event.message_text.split('icq.im/')[1]
            util.change_index_tuple_admin(cb_event.user_id, cb_event.bot.name, {
                '-1': channel_id
            })
            inline_keyboard = [
                    [{"text": "Подключить", "callbackData": "set_channel_success"}],
                    [{"text": "Отмена", "callbackData": "start_inline_message"}],
                ]
            await cb_event.bot.send_text(
                chat_id=cb_event.user_id,
                reply_msg_id=cb_event.message_id,
                text="Подключить постинг объявлений?",
                inline_keyboard_markup=json.dumps(inline_keyboard)
            )
        except IndexError:
            await cb_event.bot.send_text(
                chat_id=cb_event.user_id,
                reply_msg_id=cb_event.message_id,
                text="Укажите корректную ссылку на icq-канал"
            )

    @staticmethod
    async def start_inline_message(cb_event):
        try:
            bot_name = cb_event.bot.name
            user_id = cb_event.user_id
            is_admin = db.exist_index(
                ADMIN_SPACE_NAME, (
                    user_id, bot_name
                ), index='admin_bot'
            )

            if is_admin:
                util.set_null_admin_tuple(
                    user_id, bot_name
                )
                is_active = util.is_bot_active(
                    cb_event.bot.token
                )
                if is_active:
                    button = "⛔ ️Выключить"
                    button_action = 'disable'
                    message_active = f'Остановить бота можно командой /off или по кнопке "{button}"'
                else:
                    button = "Включить"
                    button_action = 'enable'
                    message_active = f'Включить бота можно командой /on или по кнопке "{button}"'

                await cb_event.bot.send_text(
                    chat_id=user_id,
                    text=(
                        f"Привет, я твой бот объявлений. Мой никнейм @{bot_name}\n\n"
                        "1) Чтобы настроить группу или канал для постинга объявлений, "
                        "нажми \"Настроить объявления\"\n"
                        "2) Чтобы добавить или удалить админов,"
                        " которые могут публиковать объявления, нажми \"Настроить админов\"\n"
                        f"3) @{message_active}\n"
                        "4) Для публикации объявления просто пришли мне его текст\n"
                        "5) Для редактирования объявления перешли в меня оригинальное сообщение"
                        " из группы или канала\n\n"
                        "Возможности бота объявлений:\n"
                        "- Единый способ публикации объявлений в группу или канал\n"
                        "- Отслеживание истории изменений объявлений "
                        "(все админы увидят, кто поменял объявление)"
                    ),
                    inline_keyboard_markup=json.dumps([
                        [{"text": "Настроить объявления", "callbackData": "check_icq_channel"}],
                        [{"text": "Настроить админов", "callbackData": "config_reply"}],
                        [{"text": f"{button}", "callbackData": f"switch_inline;{button_action}"}],
                    ])
                )
            else:
                await cb_event.bot.send_text(
                    chat_id=user_id,
                    text="Привет. Этот бот позволяет отправлять объявления в привязанный канал или группу. "
                         "К сожалению, эта функция доступна только для администраторов бота."
                )
        except IndexError:
            log.error("Ошибка получения стартового сообщения встроенного бота")
