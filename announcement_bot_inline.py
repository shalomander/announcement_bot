import asyncio
import handlers
import logging
from asyncio import Task

from config import (
    BOT_SPACE_NAME, config
)
import tarantool_utils as tarantool
from mailru_im_async_bot.handler import (
    CommandHandler, BotButtonCommandHandler, MessageHandler
)
from mailru_im_async_bot.bot import Bot

log = logging.getLogger(__name__)


class InlineAnnouncementBot:
    NAME = ''
    VERSION = "0.0.1"
    HASH_ = None
    TOKEN = ''
    DEV = config.has_option("main", "dev") and config.getboolean("main", "dev")
    POLL_TIMEOUT_S = int(config.get("icq_bot", "poll_time_s"))
    REQUEST_TIMEOUT_S = int(config.get("icq_bot", "request_timeout_s"))
    TASK_TIMEOUT_S = int(config.get("icq_bot", "task_timeout_s"))
    TASK_MAX_LEN = int(config.get("icq_bot", "task_max_len"))
    TIME_SLEEP = int(config.get("icq_bot", "time_sleep"))

    loop = None
    bot = None
    is_running = False
    _polling_task = None

    def __init__(self, token, name, **kwargs):
        self.TOKEN = token
        self.NAME = name
        self.loop = kwargs['loop'] if 'loop' in kwargs else asyncio.get_event_loop()
        self.bot = Bot(
            token=self.TOKEN,
            version=self.VERSION,
            name=self.NAME,
            poll_time_s=self.POLL_TIMEOUT_S,
            request_timeout_s=self.REQUEST_TIMEOUT_S,
            task_max_len=self.TASK_MAX_LEN,
            task_timeout_s=self.TASK_TIMEOUT_S
        )
        self.bot.dispatcher.add_handler(
            CommandHandler(callback=handlers.start_inline_message, command='start')
        )

        self.bot.dispatcher.add_handler(
            CommandHandler(callback=handlers.off_bot_for_admin, command='off')
        )

        self.bot.dispatcher.add_handler(
            CommandHandler(callback=handlers.on_bot_for_admin, command='on')
        )

        self.bot.dispatcher.add_handler(
            BotButtonCommandHandler(callback=handlers.callbacks_inline)
        )

        self.bot.dispatcher.add_handler(
            MessageHandler(
                callback=handlers.message_inline,
            )
        )

    def start(self):
        log.info(f'\nStart inline bot @{self.NAME}')
        self._polling_task = self.loop.create_task(self.bot.start_polling())
        self.update_status_bot(False)
        self.is_running = True

    def stop(self):
        log.info('\nStop inline bot @{self.NAME}')
        if isinstance(self._polling_task, Task):
            self._polling_task.cancel()
        self._polling_task = None
        self.update_status_bot(False)
        self.is_running = False

    def update_status_bot(self, status: bool) -> None:
        """
        Обновляет статус бота
        :param status: Новый статус для бота
        :return: None
        """
        bot = tarantool.select_index(BOT_SPACE_NAME, self.NAME, index='bot')[0]
        bot[4] = status
        tarantool.replace(BOT_SPACE_NAME, bot)
