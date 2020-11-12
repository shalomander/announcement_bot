import json
from abc import ABC
import logging
from tarantool.error import DatabaseError

from config import (
    BOT_NAME,
    BOT_SPACE_NAME,
    USER_SPACE_NAME,
    ADMIN_SPACE_NAME,
    LINK_ICQ, MESSAGES_SPACE_NAME
)
from response import start_message_inline_bot
from tarantool_utils import (
    select, insert, replace, select_index, delete
)
import utilities as util

log = logging.getLogger(__name__)


class CallBackMiddlewareBase(ABC):
    """
    Базовый класс для промежуточных обработчиков callback-функций
    """

    async def __call__(self, bot, user_id, callback_name, query_id, **kwargs):
        """
        :param bot: Объект бота
        :param user_id: User
        :param callback_name:Название функции для вызова
        :param query_id: ID для ответа на callback
        :return:
        """

        callback_data = util.parse_callback_name(callback_name)

        self.bot = bot
        self.user_id = user_id
        self.callback_name = callback_data['callback']
        self.query_id = query_id
        self.kwargs = kwargs
        self.callback_params = callback_data['params']
        self.event_data = self.kwargs['event'].data if 'event' in self.kwargs else []
        self.username = util.extract_username(self.event_data)
        print()
        try:
            await getattr(self, self.callback_name)()
            await self.set_null_callback()
        except AttributeError as e:
            log.error(f"AttributeError in callback_middleware: {e}")

    async def set_null_callback(self):
        """
        Закрыть обращение к callback-функции
        :return:
        """
        await self.bot.answer_callback_query(
            query_id=self.query_id,
            text="",
            show_alert=False
        )

    async def set_answer_callback(self, text):
        """
        Закрыть обращение к callback-функции
        :return: None
        """
        await self.bot.answer_callback_query(
            query_id=self.query_id,
            text=text,
            show_alert=False
        )

    async def callback_ignore(self):
        """
        Игнорирование обратного вызова
        :return:
        """
        await self.set_null_callback()


class CallBackMiddleware(CallBackMiddlewareBase):
    """
    Распределение callback-функций внутри основного бота
    """

    async def call_back_instruction(self):
        """
        Вывод информации о @metabot
        """

        await self.bot.send_text(
            chat_id=self.user_id,
            text=(
                f"Как создать бота используя @metabot\n"
                f"1) Открой @metabot\n"
                f"2) Создай нового бота при помощи команды /newbot\n"
                f"3) Придумай никнейм своему боту помошнику, "
                f'ник обязательно должен заканчиваться на словом “bot” 👇'
                f"https://files.icq.net/get/0dQlW000hNBmuU2TvlRRUP5ed263b51ae"
                f"4) Отправь команду /setjoingroups после успешного создания бота 👇\n"
                f"https://files.icq.net/get/0dC9G000CFJARbEleLxsxl5ed263de1ae\n\n"
                f"Следующие шаги 5-7 не обязательны и нужны для доп. настройки твоего бота-помощника:\n"
                f"5) Придумай имя своему боту /setname 👇\n"
                f"https://files.icq.net/get/0dYaO000MquODLncJY3uMB5ed2642f1ae\n"
                f"6) Укажи описание для своего бота /setdescription 👇\n"
                f"https://files.icq.net/get/0dUaY000WcqonvlVrDFAcS5ed264621ae\n"
                f"7) Пришли аватарку для своего бота /setuserpic 👇\n"
                f"https://files.icq.net/get/0dKj8000frHsEa2YyUS1zE5ed266211ae\n\n"
                f"⚠️ Важно: перешли @{BOT_NAME} сообщение с данными о своем боте 👇\n"
                f"https://files.icq.net/get/0aE48000e9N8zzuD0O1VBt5ed266931ae"
            )
        )
        await self.set_null_callback()

    async def call_back_bot_connect(self):
        """
        Сохранение данных о боте
        """
        _, bot_token, bot_id, bot_nick = select(USER_SPACE_NAME, self.user_id)[0]
        replace(USER_SPACE_NAME, (self.user_id, '', '', ''))

        try:
            insert(BOT_SPACE_NAME, (
                self.user_id,
                bot_token,
                bot_id,
                bot_nick,
                False,
                start_message_inline_bot,
                ''
            ))

            insert(ADMIN_SPACE_NAME, (
                self.user_id, bot_nick, True, '', 0, ''
            ))
            self.kwargs['bot_callbacks']['start'](bot_nick)

        except DatabaseError:
            await self.bot.send_text(
                self.user_id,
                text="Бот с таким botId уже был добавлен",
                inline_keyboard_markup=json.dumps([
                    [{"text": "Попробовать еще раз", "callbackData": "callback_start"}],
                ])
            )

        else:
            await self.bot.send_text(
                self.user_id,
                text=(
                    f"Твой бот @{bot_nick} готов к работе!\n"
                    f"Открой @{bot_nick} для получения сообщений и настройки "
                    f"бота для пересылки сообщений в группы или каналы"
                ),
                inline_keyboard_markup=json.dumps([
                    [{"text": "Открыть бота", "url": f"https://icq.im/{bot_nick}"}],
                    [{"text": "Создать еще одного бота", "callbackData": "callback_start"}],
                ])
            )
        await self.set_null_callback()


callback_middleware = CallBackMiddleware()


class CallBackMiddlewareInlineBot(CallBackMiddlewareBase):
    """
    Класс для обработки кол-бэк функций внутри бота-помощника
    """

    edit_admin_mode = {}

    def is_edit_admin_enabled(self) -> bool:
        return bool(self.edit_admin_mode.get(self.user_id, False))

    async def callback_switch_inline(self):
        """
        переключение статуса пересылки
        :return:
        """
        util.switch_inline_status(self.bot.name)
        is_active = util.is_admin_active(
            self.user_id, self.bot.name
        )
        if is_active:
            message = (
                f"Теперь сообщения, которые подписчики написали "
                f"@{self.bot.name} начнут приходить и вам Остановить получение "
                f"сообщений можно командой /off или по кнопке “Выключить”"
            )
            switch_button_text = 'Выключить'
        else:
            message = (
                "Получение сообщений для вас отключено. Сообщения которые "
                "пользователи будут отправлять в бота будут утеряны"
            )
            switch_button_text = 'Включить обратно'
        inline_keyboard = [
            [{"text": f"{switch_button_text}", "callbackData": "callback_switch_inline"}],
            [{"text": "Назад", "callbackData": "start_inline_message"}],
        ]
        await self.bot.send_text(
            chat_id=self.user_id,
            text=message,
            inline_keyboard_markup=json.dumps(inline_keyboard)
        )
        await self.set_null_callback()

    async def callback_on_off_success(self):
        """
        Подтверждение смены статуса активности для пользователя
        :return: None
        """
        message = util.switch_admin_status(
            self.user_id, self.bot.name
        )

        await self.set_answer_callback(
            f"Теперь бот {message}"
        )

    async def callback_change_start_message(self):
        """
        Смена стартового сообщения встроенного бота
        :return:
        """

        try:
            util.change_index_tuple_admin(self.user_id, self.bot.name, {
                '3': "change_start_message",
                "4": 1
            })

            await self.bot.send_text(
                self.user_id,
                text=(
                    "Пришли мне новое приветственное "
                    "сообщение которое увидят подписчики когда "
                    "откроют бота для отправки сообщения"
                ),
                inline_keyboard_markup=json.dumps([
                    [{"text": "Отмена", "callbackData": "start_inline_message"}],
                ])
            )

        except IndexError:
            log.error("Администратор не найден")

        else:
            await self.set_null_callback()

    async def callback_change_start_message_success(self):
        """
        Утверждение нового стартового сообщения
        :return:
        """

        try:
            new_message = select_index(
                ADMIN_SPACE_NAME, (
                    self.user_id, self.bot.name
                ), index='admin_bot'
            )[0][-1]

            bot_info = select_index(BOT_SPACE_NAME, self.bot.name, index='bot')[0]
            bot_info[-2] = new_message

            replace(BOT_SPACE_NAME, bot_info)

            util.change_index_tuple_admin(self.user_id, self.bot.name, {
                "3": "",
                "4": 1,
                "5": ""
            })

            await self.bot.send_text(
                self.user_id,
                text="Приветственное сообщение успешно сохранено",
                inline_keyboard_markup=json.dumps([
                    [{"text": "Назад", "callbackData": "start_inline_message"}],
                ])
            )

        except IndexError:
            log.error("Ошибка добавления нового сообщения")

        await self.set_null_callback()

    async def callback_check_icq_channel(self):
        """
        Проверка наличия канала для предложки
        :return:
        """

        try:
            icq_channel = select_index(BOT_SPACE_NAME, self.bot.name, index='bot')[0][-1]
            if icq_channel:
                await self.bot.send_text(
                    self.user_id,
                    text=(
                        f"Предложка уже подключена к каналу {LINK_ICQ}/{icq_channel}\n"
                        "Заменить на новый канал?"
                    ),
                    inline_keyboard_markup=json.dumps([
                        [{"text": "Да", "callbackData": "callback_add_new_icq_channels"}],
                        [{"text": "Нет", "callbackData": "start_inline_message"}],
                    ])
                )
            else:
                await self.callback_add_new_icq_channels()
        except IndexError:
            log.error("Ошибка при провпрка наличия канала для прослушивания")
        finally:
            await self.set_null_callback()

    async def callback_config_reply(self):
        """
        Вывод начального сообщения настроек пересылки
        :return:
        """
        await self.bot.send_text(
            self.user_id,
            text=(
                "Удалить или добавить администраторов бота:\n"
                "1) Добавить админов, которые смогут публиковать объявления и будут получать сообщения"
                " об изменении и публикации новых объявлений через бота - \"Добавить админа\"\n"
                "2) Удалить админов - \"Удалить админа\""
            ),
            inline_keyboard_markup=json.dumps([
                [{"text": "Добавить админa", "callbackData": "reply_add_admin"}],
                [{"text": "Удалить админа", "callbackData": "reply_disable"}],
                [{"text": "Отмена", "callbackData": "start_inline_message"}],
            ])
        )

    async def reply_add_admin(self):
        """
        Вывод сообщения добавления админов
        :return:
        """
        self.edit_admin_mode[self.user_id] = 'add'
        await self.bot.send_text(
            self.user_id,
            text=(
                "Чтобы добавить администратора, пришли мне ссылку на его профиль."
            ),
            inline_keyboard_markup=json.dumps([
                [{"text": "Назад", "callbackData": "reply_cancel"}],
            ])
        )

    async def reply_add_group(self):
        """
        Вывод сообщения добавления групп
        :return:
        """
        self.edit_admin_mode[self.user_id] = 'add_group'
        await self.bot.send_text(
            self.user_id,
            text=(
                "Чтобы настроить пересылку свех сообщений в группу с админами:\n"
                f"1) добавить @{BOT_NAME} в группу\n"
                "2) прислать сюда ссылку на группу"
            ),
            inline_keyboard_markup=json.dumps([
                [{"text": "Назад", "callbackData": "reply_cancel"}],
            ])
        )

    async def edit_admin(self, event_data):
        message_type = event_data['parts'][0]['type'] if 'parts' in event_data else 'message'
        edit_mode = self.edit_admin_mode.get(self.user_id, False)
        link = admin_id = ''
        if message_type == 'mention':
            admin_id = event_data['parts'][0]['payload']['userId']
        else:
            link = util.parse_group_link(event_data['text'])
        if edit_mode == 'add':
            await self.add_admin(admin_id)
        elif edit_mode == 'add_group':
            await self.add_group(link)
        elif edit_mode == 'remove':
            await self.remove_admin(admin_id or link)
        self.edit_admin_mode.pop(self.user_id)

    async def add_admin(self, new_admin_id: int):
        """
        добавление нового админа
        :return:
        """
        response = await self.bot.get_chat_info(new_admin_id)
        if response.get("ok"):
            username = response.get('nick') or new_admin_id
            try:
                insert(ADMIN_SPACE_NAME, (
                    new_admin_id, self.bot.name, True, '', 0, ''
                ))
            except DatabaseError:
                await self.bot.send_text(
                    self.user_id,
                    text=(
                        f"Не удалось добавить админа @{username}"
                    )
                )
            else:
                await self.bot.send_text(
                    self.user_id,
                    text=(
                        f"Пользователь @{username} назначен Администратором бота.\n"
                        f"⚠️ ВАЖНО: Пользователь должен САМ открыть @{self.bot.name} и стартовать его, "
                        "чтобы начать получать сообщения"
                    )
                )
        else:
            await self.bot.send_text(
                self.user_id,
                text=(
                    "Ошибка\n\n"
                    "Пользователь не найден или не существует."
                )
            )
        await self.callback_config_reply()

    async def add_group(self, new_group_link):
        """
        добавление новой группы админов
        :return:
        """
        group_id = util.ltrim(new_group_link, 'https://icq.im/')
        response = await self.bot.get_chat_info(group_id)
        if response.get("ok"):
            try:
                insert(ADMIN_SPACE_NAME, (
                    group_id, self.bot.name, True, '', 0, ''
                ))
            except DatabaseError:
                await self.add_group_error()
            else:
                await self.bot.send_text(
                    self.user_id,
                    text=(
                        "Пересылка успешно настроена.\n\n"
                        "Теперь все входящие сообщения будут пересылаться в группу (канал) и все Администраторы"
                        "группы могут ими управлять (в  случае если настроена Предложка)\n"
                        f"@{group_id}"
                    )
                )
        else:
            await self.add_group_error()

    async def add_group_error(self):
        await self.bot.send_text(
            self.user_id,
            text=(
                "Ошибка настройки пересылки.\n\n"
                f"Проверьте что ссылка валидна и что бот @{BOT_NAME} добавлен в группу и имеет право писать туда.\n"
            ),
            inline_keyboard_markup=json.dumps([
                [{"text": "Повторить", "callbackData": "reply_add_group"}],
                [{"text": "Назад", "callbackData": "reply_cancel"}],
            ])
        )

    async def remove_admin(self, admin_id: int):
        """
        Удаление админа
        :return:
        """
        username = None
        response = await self.bot.get_chat_info(admin_id)
        if response.get("ok"):
            username = response.get('nick') or admin_id
        try:
            delete(ADMIN_SPACE_NAME, (admin_id, self.bot.name))
        except DatabaseError:
            await self.bot.send_text(
                self.user_id,
                text=(
                    f"не удалось удалить админа @{username}"
                )
            )
        else:
            await self.bot.send_text(
                self.user_id,
                text=(
                    f"Пользователь @{username} удален из списка Администраторов бота."
                )
            )
        await self.callback_config_reply()

    async def reply_disable(self):
        """
        Вывод сообщения удаления админов и групп
        :return:
        """

        self.edit_admin_mode[self.user_id] = 'remove'
        admin_list_text = "Администраторы:\n"
        admin_list_index = 1
        admins = select_index(ADMIN_SPACE_NAME, self.bot.name, index='bot_nick')
        for admin in admins:
            response = await self.bot.get_chat_info(admin[0])
            if response.get("ok"):
                if response.get('type') == 'private':
                    admin_list_text += f"{admin_list_index}) @{response.get('nick') or admin[0]}\n"
                    admin_list_index += 1
        await self.bot.send_text(
            self.user_id,
            text=(
                "Чтобы удалить администратора, пришли мне ссылку на его профиль.\n\n "
                f"{admin_list_text}\n"
            ),
            inline_keyboard_markup=json.dumps([
                [{"text": "Назад", "callbackData": "reply_cancel"}],
            ])
        )

    async def reply_cancel(self):
        """
        Переход в настройки пересылки
        :return:
        """
        await self.callback_config_reply()

    async def callback_add_new_icq_channels(self):
        """
        Вывод информации о настроке предложки пользователя
        :return:
        """

        util.change_index_tuple_admin(self.user_id, self.bot.name, {
            '3': "set_icq_channel",
            "4": 1
        })

        await self.bot.send_text(
            self.user_id,
            text=(
                "Чтобы в группу или канал начали публиковываться объявления, нужно:\n"
                "после проверки администратором, нужно:\n"
                f"1) добавить @{self.bot.name} в канал\n"
                '2) сделать бота администратором\n'
                "3) прислать сюда ссылку на группу или канал\n"
                "⚠️ ВАЖНО: Канал может быть только один"
            ),
            inline_keyboard_markup=json.dumps([
                [{"text": "Ошибка при добавлении", "callbackData": "error_for_add_icq_channel"}],
                [{"text": "Отмена", "callbackData": "start_inline_message"}],
            ])
        )
        await self.set_null_callback()

    async def error_for_add_icq_channel(self):
        """
        Указание действий при выозниквновении ошибок
        :return:
        """
        await self.bot.send_text(
            self.user_id,
            text=(
                "Если не получается добавить бота в канал нужно:\n"
                "1) Открой @metabot\n"
                "2) Отправь команду /setjoingroups и послать никнейм вашего бота\n"
                "https://files.icq.net/get/0dC9G000CFJARbEleLxsxl5ed263de1ae"
            ),
            inline_keyboard_markup=json.dumps([
                [{"text": "Назад", "callbackData": "callback_add_new_icq_channels"}],
            ])
        )

        await self.set_null_callback()

    async def callback_set_icq_channel_success(self):
        """
        Сохранение icq-канала для предложки
        :return:
        """
        try:
            icq_channel = select(
                ADMIN_SPACE_NAME, (self.user_id, self.bot.name)
            )[0][-1]
            response = await self.bot.get_chat_admins(icq_channel)
            if not response.get('ok'):
                await self.bot.send_text(
                    self.user_id,
                    text=(
                        "Ошибка подключения объявлений\n\n"
                        f"Бот @{self.bot.name} не добавлен в группу или канал или не имеет право писать туда.\n\n"
                    ),
                    inline_keyboard_markup=json.dumps([
                        [{"text": "Повторить", "callbackData": "callback_set_icq_channel_success"}],
                        [{"text": "Отмена", "callbackData": "start_inline_message"}],
                    ])
                )
            else:
                util.set_null_admin_tuple(self.user_id, self.bot.name)
                bot_info = select_index(BOT_SPACE_NAME, self.bot.name, index='bot')[0]
                bot_info[-1] = icq_channel
                replace(BOT_SPACE_NAME, bot_info)
                await self.bot.send_text(
                    self.user_id,
                    text=(
                        "Объявления успешно настроены.\n\n"
                        "Теперь чтобы опубликовать сообщение отправь его в меня, "
                        "и я предложу тебе его опубликовать и запинить"
                    ),
                    inline_keyboard_markup=json.dumps([
                        [{"text": "Назад", "callbackData": "start_inline_message"}],
                    ])
                )
        except IndexError:
            pass
        finally:
            await self.set_null_callback()

    async def callback_switch_anonymous(self):
        """
        Установка отправки сообщений пользователя в анонимном режиме
        :return:
        """
        is_anon = util.str_to_bool(self.callback_params[0])
        util.change_anonymous_status(self.user_id, is_anon)
        if is_anon:
            text = "Включен анонимный режим. Все следующие сообщения будут отправлены анонимно"
            callback_text = "Отключить"
        else:
            text = "Анонимный режим выключен. Владелец бота увидит отправителя"
            callback_text = "Включить"

        await self.bot.send_text(
            self.user_id,
            text=text,
            inline_keyboard_markup=json.dumps([
                [{"text": callback_text, "callbackData": f"callback_switch_anonymous-{not is_anon}"}],
            ])
        )
        await self.set_null_callback()

    async def callback_set_true_user_anonymous(self):
        """
        Установка отправки сообщений пользователя в анонимном режиме
        :return:
        """
        util.change_anonymous_status(self.user_id, True)
        await self.bot.send_text(
            self.user_id,
            text=(
                "Включен анонимный режим. Все следующие сообщения будут отправлены анонимно"
            ),
            inline_keyboard_markup=json.dumps([
                [{"text": "Отключить", "callbackData": "callback_set_false_user_anonymous"}],
            ])
        )
        await self.set_null_callback()

    async def callback_set_false_user_anonymous(self):
        """
        Установка отправки сообщений пользователя в анонимном режиме
        :return:
        """
        util.change_anonymous_status(self.user_id, False)
        await self.bot.send_text(
            self.user_id,
            text=(
                "Анонимный режим выключен. Владелец бота увидит отправителя"
            ),
            inline_keyboard_markup=json.dumps([
                [{"text": "Включить", "callbackData": "callback_set_true_user_anonymous"}],
            ])
        )
        await self.set_null_callback()

    async def callback_send_post(self):
        """
        Отправка поста в канал
        :return:
        """
        try:
            icq_channel = util.get_bot_channel(self.bot.name)
            original_msg_id = self.callback_params[0]
            if 'parts' in self.event_data['message']:
                text = self.event_data['message']['parts'][0]['payload']['message']['text']

                # send original text to target channel
                target_msg = await self.bot.send_text(
                    chat_id=icq_channel,
                    text=text
                )

                # forward original message to admins
                admins = util.get_admins(self.bot.name)
                forwarded_id = []
                for admin in admins:
                    admin_id = admin[0]
                    message_obj = await self.bot.send_text(
                        chat_id=admin_id,
                        forward_chat_id=self.user_id,
                        forward_msg_id=original_msg_id
                    )
                    forwarded_id.append((admin_id, message_obj.get('msgId')))
                insert(MESSAGES_SPACE_NAME, (
                    original_msg_id, forwarded_id
                ))

                # edit replied message
                replied_id = self.event_data['message']['msgId']
                inline_keyboard = [
                    [{"text": "Закрепить в чате?", "callbackData": f"callback_pin_msg-{target_msg.get('msgId')}"}],
                    [{"text": "Отмена", "callbackData": f"callback_disable_buttons-{replied_id}"}],
                ]
                self.bot.edit_text(
                    msg_id=replied_id,
                    text="Опубликовано! Уведомление о публикации отправлено всем админам",
                    inline_keyboard_markup=json.dumps(inline_keyboard)
                )

        except IndexError as e:
            log.error(f"IndexError in callback_send_post: {e}")

    async def callback_delete_post(self):
        try:
            await self.bot.delete_messages(
                    chat_id=self.user_id,
                    msg_id=self.event_data['message']['msgId']
                )
        except IndexError:
            pass

    async def callback_pin_msg(self):
        try:
            pin_msg_id = self.callback_params[0]
            icq_channel = util.get_bot_channel(self.bot.name)

            # pin target message
            self.bot.pin_message(
                chat_id=icq_channel,
                msg_id=pin_msg_id
            )

        except IndexError:
            pass


callback_middleware_inline_bot = CallBackMiddlewareInlineBot()