import asyncio
import logging
import os
import pypros
from mailru_im_async_bot.bot import Bot
from mailru_im_async_bot.handler import (
    CommandHandler,
    BotButtonCommandHandler,
    MessageHandler
)
from pid import PidFile
from pypros.ipros import IncomingRequest
import config
import handlers
from announcement_bot_inline import InlineAnnouncementBot
import db
import utilities as util
from callback import main_bot_funcs
log = logging.getLogger(__name__)

file_hash = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'hash')
if os.path.exists(file_hash) and os.path.isfile(file_hash):
    with open(file=file_hash) as f:
        HASH_ = f.readline()

loop = asyncio.get_event_loop()
bot = Bot(
    token=config.TOKEN,
    version=config.VERSION,
    name=config.NAME,
    poll_time_s=config.POLL_TIMEOUT_S,
    request_timeout_s=config.REQUEST_TIMEOUT_S,
    task_max_len=config.TASK_MAX_LEN,
    task_timeout_s=config.TASK_TIMEOUT_S
)

inline_bots = {}

bot.dispatcher.add_handler(
    CommandHandler(callback=handlers.start, command='start')
)
bot.dispatcher.add_handler(
    BotButtonCommandHandler(callback=handlers.callbacks)
)
bot.dispatcher.add_handler(
    MessageHandler(
        callback=handlers.message,
    )
)


# ---------------------------------------------------------------------


def role_change(current, new):
    if current == new:
        log.info(f"the role remained the same: {current}")
    else:
        if new == 'main':
            loop.create_task(bot.start_polling())
            loop.create_task(update_bot_name(bot))
            loop.create_task(start_all())
        else:
            loop.create_task(bot.stop_polling())
            db.close()
        log.info(f"role was change from {current} to {new}")


async def start_bot(bot_nick, bot_data=None):
    bot_data = bot_data or util.get_bot_data(bot_nick)
    if bot_data:
        user_id, bot_token, _, bot_name, *_ = bot_data
        if await util.validate_token(bot_token):
            bot_instance = InlineAnnouncementBot(bot_token, bot_name, user_id)
            bot_instance.start()
            await update_bot_name(bot_instance.bot)
            if bot_instance.is_running:
                log.info(f"Success: {bot_name}\n")
                inline_bots[bot_name] = bot_instance
        else:
            db.delete(config.BOT_SPACE_NAME, (user_id, bot_token))


def stop_bot(bot_nick):
    bot_instance = inline_bots.pop(bot_nick)
    if bot_instance.is_running:
        bot_instance.stop()


async def start_all():
    log.info("\nStarting bots:\n")
    bots = db.select(config.BOT_SPACE_NAME)
    for bot_data in bots:
        await start_bot(None, bot_data)


def stop_all():
    for key, bot_instance in inline_bots.items():
        if bot_instance.is_running:
            bot_instance.stop()
        inline_bots.pop(key)


async def update_bot_name(bot_instance: Bot):
    bot_self = await bot_instance.self_get()
    if bot_self.get("ok"):
        bot_instance.name = bot_self.get('nick')

main_bot_funcs['start'] = start_bot


async def process(rq: IncomingRequest):
    log.info('{}: process called'.format(rq))
    rq.reply(200, 'ok')


with PidFile(config.NAME):
    if not config.DEV:
        pypros.ctlr.G_git_hash = HASH_ if HASH_ else config.VERSION

        pypros.ctlr.role_changed_cb = lambda current, new: role_change(
            current, new
        )

        pypros.ctlr.IncomingHandlers.CHECK = lambda cn, p: cn.reply(
            p, 200, 'ok'
        )

        pypros.ctlr.init(
            self_alias=config.config['main']['alias'],
            host=config.config['ctlr']['host'],
            port=config.config['ctlr']['port']
        )
    server = None
    try:
        loop.run_until_complete(bot.init())
        if not config.DEV:
            server = loop.run_until_complete(
                pypros.listen(
                    config.config['main']['host'],
                    int(config.config['main']['port']), process)
            )
        else:
            role_change('None', 'main')
        loop.run_forever()
    finally:
        if server:
            server.close()
        db.close()
        loop.run_until_complete(pypros.ipros.shutdown())
        loop.close()
