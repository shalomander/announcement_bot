import asyncio
import handlers
import logging
from asyncio import Task

from config import (
    BOT_SPACE_NAME, config
)
import db
from mailru_im_async_bot.handler import (
    CommandHandler, BotButtonCommandHandler, MessageHandler
)
from mailru_im_async_bot.bot import Bot
import utilities as util

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
    running_tasks = []

    def __init__(self, token, name, user_id, **kwargs):
        self.TOKEN = token
        self.NAME = name
        self.owner_id = user_id
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
            CommandHandler(callback=handlers.set_state, command='off')
        )

        self.bot.dispatcher.add_handler(
            CommandHandler(callback=handlers.set_state, command='on')
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
        self.running_tasks.append(self.loop.create_task(self._run_tasks()))
        self.update_status_bot(False)
        self.is_running = True

    def stop(self):
        log.info('\nStop inline bot @{self.NAME}')
        if isinstance(self._polling_task, Task):
            self._polling_task.cancel()
        for task in self.running_tasks:
            task.cancel()
        self._polling_task = None
        self.update_status_bot(False)
        self.is_running = False

    def update_status_bot(self, status: bool) -> None:
        """
        Обновляет статус бота
        :param status: Новый статус для бота
        :return: None
        """
        bot_data = util.get_bot_data(self.NAME)
        bot_data[4] = status
        db.replace(BOT_SPACE_NAME, bot_data)

    async def check_token(self):
        if not await util.validate_token(self.TOKEN):
            db.delete(config.BOT_SPACE_NAME, (self.owner_id, self.TOKEN))

    async def _run_tasks(self):
        while self.is_running:
            try:
                await self.check_token()
                await asyncio.sleep(30)
            except Exception as e:
                log.exception(e)
