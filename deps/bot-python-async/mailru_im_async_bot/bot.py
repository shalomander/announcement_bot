import mailru_im_async_bot
from mailru_im_async_bot import cut_none, url_maker, try_except_request, log, stat, stat_decorator
from mailru_im_async_bot.dispatcher import Dispatcher
from mailru_im_async_bot.event import Event, EventType
from mailru_im_async_bot.trace_config import trace_config
from cached_property import cached_property
from asyncio import CancelledError, Task
from traceback import format_exc
from aiohttp import FormData
import asyncio
import aiohttp
import os


class Bot:
    def __init__(
            self,
            token,
            name=None,
            version=None,
            api_url_base=None,
            poll_time_s=300,
            task_timeout_s=60,
            request_timeout_s=7,
            task_max_len=100000,
            loop=None
    ):
        self.api_base_url = "https://api.icq.net/bot/v1" if api_url_base is None else api_url_base
        self.loop = asyncio.get_event_loop() if loop is None else loop
        self.events = asyncio.Queue(maxsize=task_max_len)
        self.request_timeout_s = request_timeout_s
        self.task_timeout_s = task_timeout_s
        self.dispatcher = Dispatcher(self)
        self.poll_time_s = poll_time_s
        self.task_max_len = task_max_len
        self.is_polling = False
        self.last_event_id = 0
        self.version = version
        self.is_running = True
        self.users = dict()
        self.token = token
        self.name = name

        self._uin = token.split(":")[-1]
        self._dispatcher_task = None
        self._polling_task = None
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.request_timeout_s),
            trace_configs=[trace_config],
            headers={'User-agent': self.user_agent}
        )

    async def init(self):
        log.warning("deprecated")

    async def stop(self):
        log.info('stop bot')
        self.is_running = False
        await self.stop_polling()
        await self._session.close()

    @try_except_request
    @cut_none
    @url_maker
    async def _get(self, url, *args, **kwargs):
        async with self._session.get(url, ssl=False, *args, **kwargs) as response:
            return await response.json()

    @try_except_request
    @cut_none
    @url_maker
    async def _post(self, url, *args, **kwargs):
        async with self._session.post(url, ssl=False, *args, **kwargs) as response:
            return await response.json()

    async def start_polling(self):
        for item, message in (
                (self.is_polling, 'polling already run'),
                (self._polling_task, 'polling task already exists'),
                (self._dispatcher_task, 'dispatcher task already exists')
        ):
            if item:
                log.warning(message)
                break
        else:
            log.info('start polling')
            self.is_polling = True
            self._polling_task = self.loop.create_task(self._polling())
            self._dispatcher_task = self.loop.create_task(self.dispatcher.dispatch())

    async def stop_polling(self):
        log.info('stop polling')
        self.is_polling = False
        if isinstance(self._polling_task, Task):
            self._polling_task.cancel()
        if isinstance(self._dispatcher_task, Task):
            self._dispatcher_task.cancel()
        self._polling_task = None
        self._dispatcher_task = None

    async def _polling(self):
        while self.is_running and self.is_polling:
            try:
                response = await self.events_get()
                if response:
                    for event in response.get("events", []):
                        stat('events_queue', self.events.qsize())
                        if self.events.full():
                            log.critical("events queue overflow")
                            await asyncio.sleep(1)
                        else:
                            self.last_event_id = max(response['events'], key=lambda e: e['eventId'])['eventId']
                            await self.events.put(
                                Event(id=event['eventId'], type_=EventType(event["type"]), data=event["payload"])
                            )
            except CancelledError:
                log.warning("pooling cancelled")
            except Exception:
                log.exception(format_exc())
                await asyncio.sleep(5)

    async def idle(self):
        while self.is_running:
            await asyncio.sleep(0.1)

    @property
    def uin(self):
        return self._uin

    @cached_property
    def user_agent(self):
        return "{name}/{version} (uin={uin}) mailru-im-async-bot/{library_version}".format(
            name=self.name,
            version=self.version,
            uin="" if self.uin is None else self.uin,
            library_version=mailru_im_async_bot.__version__
        )

    @stat_decorator()
    async def events_get(self, poll_time_s=None, last_event_id=None):
        poll_time_s = self.poll_time_s if poll_time_s is None else poll_time_s
        last_event_id = self.last_event_id if last_event_id is None else last_event_id

        return await self._get(
            url="{}/events/get".format(self.api_base_url),
            params={
                "token": self.token,
                "pollTime": poll_time_s,
                "lastEventId": last_event_id
            },
            timeout=poll_time_s + self.request_timeout_s
        )

    @stat_decorator()
    async def self_get(self):
        return await self._get(
            url="{}/self/get".format(self.api_base_url),
            params={
                "token": self.token
            }
        )

    @stat_decorator()
    async def send_text(self, chat_id, text, reply_msg_id=None, forward_chat_id=None, forward_msg_id=None,
                        inline_keyboard_markup=None):
        return await self._get(
            url="{}/messages/sendText".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "text": text,
                "replyMsgId": reply_msg_id,
                "forwardChatId": forward_chat_id,
                "forwardMsgId": forward_msg_id,
                "inlineKeyboardMarkup": inline_keyboard_markup
            }
        )

    @stat_decorator()
    async def send_file(self, chat_id, file_id=None, file=None, caption=None, reply_msg_id=None, forward_chat_id=None,
                        forward_msg_id=None, inline_keyboard_markup=None):
        data = None
        if file:
            data = FormData()
            data.add_field('file', file, filename=os.path.basename(file.name))

        return await self._post(
            url="{}/messages/sendFile".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "fileId": file_id,
                "caption": caption,
                "replyMsgId": reply_msg_id,
                "forwardChatId": forward_chat_id,
                "forwardMsgId": forward_msg_id,
                "inlineKeyboardMarkup": inline_keyboard_markup
            },
            data=data,
        )

    @stat_decorator()
    async def send_voice(self, chat_id, file_id=None, file=None, reply_msg_id=None, forward_chat_id=None,
                         forward_msg_id=None, inline_keyboard_markup=None):
        data = None
        if file:
            data = FormData()
            data.add_field('file', file, filename=os.path.basename(file.name))

        return await self._post(
            url="{}/messages/sendVoice".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "fileId": file_id,
                "replyMsgId": reply_msg_id,
                "forwardChatId": forward_chat_id,
                "forwardMsgId": forward_msg_id,
                "inlineKeyboardMarkup": inline_keyboard_markup
            },
            data=data,
        )

    @stat_decorator()
    async def edit_text(self, chat_id, msg_id, text, inline_keyboard_markup=None):
        return await self._get(
            url="{}/messages/editText".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "msgId": msg_id,
                "text": text,
                "inlineKeyboardMarkup": inline_keyboard_markup
            }
        )

    @stat_decorator()
    async def answer_callback_query(self, query_id, text=None, show_alert=False, url=None):
        return await self._get(
            url="{}/messages/answerCallbackQuery".format(self.api_base_url),
            params={
                "token": self.token,
                "queryId": query_id,
                "text": text,
                "showAlert": str(show_alert).lower(),
                "url": url
            }
        )

    @stat_decorator()
    async def delete_messages(self, chat_id, msg_id):
        return await self._get(
            url="{}/messages/deleteMessages".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "msgId": msg_id
            },
        )

    @stat_decorator()
    async def send_actions(self, chat_id, actions):
        return await self._get(
            url="{}/chats/sendActions".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "actions": actions
            },
        )

    @stat_decorator()
    async def get_chat_info(self, chat_id):
        return await self._get(
            url="{}/chats/getInfo".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id
            }
        )

    @stat_decorator()
    async def get_chat_admins(self, chat_id):
        return await self._get(
            url="{}/chats/getAdmins".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id
            }
        )

    @stat_decorator()
    async def get_chat_members(self, chat_id, cursor=None):
        return await self._get(
            url="{}/chats/getMembers".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "cursor": cursor
            }
        )

    @stat_decorator()
    async def get_chat_blocked_users(self, chat_id):
        return await self._get(
            url="{}/chats/getBlockedUsers".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id
            }
        )

    @stat_decorator()
    async def get_chat_pending_users(self, chat_id):
        return await self._get(
            url="{}/chats/getPendingUsers".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id
            }
        )

    @stat_decorator()
    async def chat_block_user(self, chat_id, user_id, del_last_messages=False):
        return await self._get(
            url="{}/chats/blockUser".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "userId": user_id,
                "delLastMessages": str(del_last_messages).lower()
            }
        )

    @stat_decorator()
    async def chat_unblock_user(self, chat_id, user_id):
        return await self._get(
            url="{}/chats/unblockUser".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "userId": user_id
            },
        )

    @stat_decorator()
    async def chat_resolve_pending(self, chat_id, approve=True, user_id="", everyone=False):
        return await self._get(
            url="{}/chats/resolvePending".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "approve": str(approve).lower(),
                "userId": user_id,
                "everyone": str(everyone).lower()
            }
        )

    @stat_decorator()
    async def set_chat_title(self, chat_id, title):
        return await self._get(
            url="{}/chats/setTitle".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "title": title
            }
        )

    @stat_decorator()
    async def set_chat_about(self, chat_id, about):
        return await self._get(
            url="{}/chats/setAbout".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "about": about
            }
        )

    @stat_decorator()
    async def set_chat_rules(self, chat_id, rules):
        return await self._get(
            url="{}/chats/setRules".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "rules": rules
            }
        )

    @stat_decorator()
    async def get_file_info(self, file_id):
        return await self._get(
            url="{}/files/getInfo".format(self.api_base_url),
            params={
                "token": self.token,
                "fileId": file_id
            }
        )

    @stat_decorator()
    async def pin_message(self, chat_id, msg_id):
        return await self._get(
            url="{}/chats/pinMessage".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "msgId": msg_id
            }
        )

    @stat_decorator()
    async def unpin_message(self, chat_id, msg_id):
        return await self._get(
            url="{}/chats/unpinMessage".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "msgId": msg_id
            }
        )

