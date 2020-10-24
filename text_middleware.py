import json
import logging
from utilities import change_index_tuple_admin

log = logging.getLogger(__name__)


class TextMiddlewareInlineBot:
    """
    Класс для обработки текстовых сообщений пользователя внутри бота-помощника
    """

    async def __call__(self, bot, user_id, message_id, quiz_name, **kwargs):
        self.bot = bot
        self.user_id = user_id
        self.message_id = message_id
        self.quiz_name = quiz_name
        self.kwargs = kwargs

        try:
            await getattr(self, self.quiz_name)()

        except AttributeError:
            log.error("Обработчика для указанного квиза не существует")

    async def change_start_message(self):
        """
        Утрверждение, что сообщение необходимо менять
        :return:
        """

        try:
            change_index_tuple_admin(self.user_id, self.bot.name, {
                '-1': self.kwargs.get('text')
            })

            await self.bot.send_text(
                chat_id=self.user_id,
                reply_msg_id=self.message_id,
                text="Сохранить новое приветственное сообщение?",
                inline_keyboard_markup=json.dumps([
                    [{"text": "Сохранить", "callbackData": "callback_change_start_message_success"}],
                    [{"text": "Назад", "callbackData": "callback_change_start_message"}],
                ])
            )

        except IndexError:
            log.error("Error change_start_message")

    async def set_icq_channel(self):
        """
        Парсинг нового канала для предложки
        :return:
        """
        try:
            channel_id = self.kwargs.get('text').split('icq.im/')[1]
            change_index_tuple_admin(self.user_id, self.bot.name, {
                '-1': channel_id
            })

            await self.bot.send_text(
                chat_id=self.user_id,
                reply_msg_id=self.message_id,
                text="Подключить постинг объявлений?",
                inline_keyboard_markup=json.dumps([
                    [{"text": "Подключить", "callbackData": "callback_set_icq_channel_success"}],
                    [{"text": "Отмена", "callbackData": "start_inline_message"}],
                ])
            )

        except IndexError:
            await self.bot.send_text(
                chat_id=self.user_id,
                reply_msg_id=self.message_id,
                text="Укажите корректную ссылку на icq-канал"
            )


text_middleware_inline_bot = TextMiddlewareInlineBot()
