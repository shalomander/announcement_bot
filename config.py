import configparser
import logging
import os
import sys

from logging.config import fileConfig
from mailru_im_async_bot import graphyte


# Set default config path
configs_path = "./"


# Get config path from args
if len(sys.argv) > 1:
    configs_path = sys.argv[1]


# Check exists config
for config in ["config.ini", "logging.ini"]:
    if not os.path.isfile(os.path.join(configs_path, config)):
        raise FileExistsError(f"File {config} not found in path {configs_path}")


# Read config
config = configparser.ConfigParser()
config.read(os.path.join(configs_path, "config.ini"))
fileConfig(os.path.join(configs_path, "logging.ini"), disable_existing_loggers=False)
log = logging.getLogger(__name__)


NAME = "AnnouncementBot"
VERSION = "0.0.1"
HASH_ = None
TOKEN = config.get("icq_bot", "token")
DEV = config.has_option("main", "dev") and config.getboolean("main", "dev")
POLL_TIMEOUT_S = int(config.get("icq_bot", "poll_time_s"))
REQUEST_TIMEOUT_S = int(config.get("icq_bot", "request_timeout_s"))
TASK_TIMEOUT_S = int(config.get("icq_bot", "task_timeout_s"))
TASK_MAX_LEN = int(config.get("icq_bot", "task_max_len"))
TIME_SLEEP = int(config.get("icq_bot", "time_sleep"))
BOT_NAME = config.get("icq_bot", "bot_name")
USER_SPACE_NAME = 'user'
INLINE_USER_SETUP_SPACE_NAME = 'user_inline_setup'
MESSAGES_SPACE_NAME = 'messages'
BOT_SPACE_NAME = 'bots'
ADMIN_SPACE_NAME = 'admins'
ICQ_API = config.get("icq_bot", "api")
LINK_ICQ = 'https://icq.im'


# init graphite sender
if config.getboolean('graphite', 'enable'):

    prefix = "%s.%s.%s" % (
        config.get('graphite', 'prefix'),
        config.get('main', 'alias').split('.')[1],
        config.get('main', 'alias').split('.')[0]
    )

    graphyte.init(
        host=config.get("graphite", "server"),
        port=config.get("graphite", "port"),
        prefix=prefix,
        timeout=2
    )
