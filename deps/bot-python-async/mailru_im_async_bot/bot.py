import inspect
import json

import mailru_im_async_bot
from mailru_im_async_bot import (
    cut_none_decorator,
    url_maker_decorator,
    try_except_request,
    log,
    stat,
    cut_none,
    url_maker
)
from mailru_im_async_bot.dispatcher import Dispatcher
from mailru_im_async_bot.event import Event, EventType
from mailru_im_async_bot.trace_config import trace_config
from cached_property import cached_property
from asyncio import CancelledError, Task
from async_generator import asynccontextmanager
from aiohttp import FormData, ContentTypeError
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
    @cut_none_decorator
    @url_maker_decorator
    async def _get(self, url, *args, **kwargs):
        async with self._session.get(url, ssl=False, *args, **kwargs) as response:
            return await response.json()

    @try_except_request
    @cut_none_decorator
    @url_maker_decorator
    async def _post(self, url, *args, **kwargs):
        async with self._session.post(url, ssl=False, *args, **kwargs) as response:
            return await response.json()

    @asynccontextmanager
    async def _request_cm(self, url, method="GET", *args, **kwargs):
        kwargs = cut_none(kwargs)
        url = url_maker(kwargs, url)
        caller_method_name = None
        try:
            caller_method_name = inspect.stack()[2][3]
        except IndexError as e:
            log.info(e)

        if caller_method_name:
            stat(metric=".".join(["botapi", caller_method_name, "cnt"]), value=1)

        try:
            async with getattr(self._session, str(method).lower())(url, ssl=False, *args, **kwargs) as response:
                if caller_method_name:
                    stat(metric=".".join(
                        ["botapi", caller_method_name, response.method, str(response.status), "cnt"]
                    ), value=1)
                yield response
        except asyncio.TimeoutError as e:
            if caller_method_name:
                stat(metric=".".join(["botapi", caller_method_name, response.method, "timeout", "cnt"]), value=1)
            raise
        except ContentTypeError as e:
            log.warning(f"response is not json: {e}")
            raise
        except CancelledError as e:
            log.info(f"request cancelled: {e}")
        except Exception as e:
            if caller_method_name:
                stat(metric=".".join(["botapi", caller_method_name, response.method, "error", "cnt"]), value=1)
            log.exception(e)
            raise

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
                    if "description" in response and response["description"] == 'Invalid token':
                        raise Exception(response)
                    for event in response.get("events", []):
                        stat('events_queue.cnt', self.events.qsize())
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
            except Exception as e:
                log.exception(e)
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

    async def events_get(self, poll_time_s=None, last_event_id=None):
        poll_time_s = self.poll_time_s if poll_time_s is None else poll_time_s
        last_event_id = self.last_event_id if last_event_id is None else last_event_id

        async with self._request_cm(
            url="{}/events/get".format(self.api_base_url),
            params={
                "token": self.token,
                "pollTime": poll_time_s,
                "lastEventId": last_event_id
            },
            timeout=poll_time_s + self.request_timeout_s
        ) as response:
            return await response.json()

    async def self_get(self):
        async with self._request_cm(
            url="{}/self/get".format(self.api_base_url),
            params={
                "token": self.token
            }
        ) as response:
            return await response.json()

    async def send_text(self, chat_id, text, reply_msg_id=None, forward_chat_id=None, forward_msg_id=None,
                        inline_keyboard_markup=None):
        params = [
            ("token", self.token), ("chatId", chat_id), ("text", text), ("forwardChatId", forward_chat_id),
            ("inlineKeyboardMarkup", inline_keyboard_markup)
        ]

        mailru_im_async_bot.prepare_repeated_params(
            params, {"replyMsgId": reply_msg_id, "forwardMsgId": forward_msg_id}
        )

        async with self._request_cm(
            url="{}/messages/sendText".format(self.api_base_url),
            params=params
        ) as response:
            return await response.json()

    async def send_file(self, chat_id, file_id=None, file=None, caption=None, reply_msg_id=None, forward_chat_id=None,
                        forward_msg_id=None, inline_keyboard_markup=None):
        data = None
        if file:
            data = FormData()
            data.add_field('file', file, filename=os.path.basename(file.name))

        params = [
            ("token", self.token), ("chatId", chat_id), ("fileId", file_id), ("forwardChatId", forward_chat_id),
            ("inlineKeyboardMarkup", inline_keyboard_markup), ("caption", caption)
        ]

        mailru_im_async_bot.prepare_repeated_params(
            params, {"replyMsgId": reply_msg_id, "forwardMsgId": forward_msg_id}
        )

        async with self._request_cm(
            url="{}/messages/sendFile".format(self.api_base_url),
            method="POST",
            params=params,
            data=data,
        ) as response:
            return await response.json()

    async def send_voice(self, chat_id, file_id=None, file=None, reply_msg_id=None, forward_chat_id=None,
                         forward_msg_id=None, inline_keyboard_markup=None):
        data = None
        if file:
            data = FormData()
            data.add_field('file', file, filename=os.path.basename(file.name))

        params = [
            ("token", self.token), ("chatId", chat_id), ("fileId", file_id), ("forwardChatId", forward_chat_id),
            ("inlineKeyboardMarkup", inline_keyboard_markup)
        ]

        mailru_im_async_bot.prepare_repeated_params(
            params, {"replyMsgId": reply_msg_id, "forwardMsgId": forward_msg_id}
        )

        async with self._request_cm(
            url="{}/messages/sendVoice".format(self.api_base_url),
            method="POST",
            params=params,
            data=data,
        ) as response:
            return await response.json()

    async def edit_text(self, chat_id, msg_id, text, inline_keyboard_markup=None):
        async with self._request_cm(
            url="{}/messages/editText".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "msgId": msg_id,
                "text": text,
                "inlineKeyboardMarkup": inline_keyboard_markup
            }
        ) as response:
            return await response.json()

    async def answer_callback_query(self, query_id, text=None, show_alert=False, url=None):
        async with self._request_cm(
            url="{}/messages/answerCallbackQuery".format(self.api_base_url),
            params={
                "token": self.token,
                "queryId": query_id,
                "text": text,
                "showAlert": str(show_alert).lower(),
                "url": url
            }
        ) as response:
            return await response.json()

    async def delete_messages(self, chat_id, msg_id):
        async with self._request_cm(
            url="{}/messages/deleteMessages".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "msgId": msg_id
            },
        ) as response:
            return await response.json()

    async def send_actions(self, chat_id, actions):
        async with self._request_cm(
            url="{}/chats/sendActions".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "actions": actions
            },
        ) as response:
            return await response.json()

    async def get_chat_info(self, chat_id):
        async with self._request_cm(
            url="{}/chats/getInfo".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id
            }
        ) as response:
            return await response.json()

    async def get_chat_admins(self, chat_id):
        async with self._request_cm(
            url="{}/chats/getAdmins".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id
            }
        ) as response:
            return await response.json()

    async def get_chat_members(self, chat_id, cursor=None):
        async with self._request_cm(
            url="{}/chats/getMembers".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "cursor": cursor
            }
        ) as response:
            return await response.json()

    async def get_chat_blocked_users(self, chat_id):
        async with self._request_cm(
            url="{}/chats/getBlockedUsers".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id
            }
        ) as response:
            return await response.json()

    async def get_chat_pending_users(self, chat_id):
        async with self._request_cm(
            url="{}/chats/getPendingUsers".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id
            }
        ) as response:
            return await response.json()

    async def chat_block_user(self, chat_id, user_id, del_last_messages=False):
        async with self._request_cm(
            url="{}/chats/blockUser".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "userId": user_id,
                "delLastMessages": str(del_last_messages).lower()
            }
        ) as response:
            return await response.json()

    async def chat_unblock_user(self, chat_id, user_id):
        async with self._request_cm(
            url="{}/chats/unblockUser".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "userId": user_id
            },
        ) as response:
            return await response.json()

    async def chat_resolve_pending(self, chat_id, approve=True, user_id="", everyone=False):
        async with self._request_cm(
            url="{}/chats/resolvePending".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "approve": str(approve).lower(),
                "userId": user_id,
                "everyone": str(everyone).lower()
            }
        ) as response:
            return await response.json()

    async def set_chat_title(self, chat_id, title):
        async with self._request_cm(
            url="{}/chats/setTitle".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "title": title
            }
        ) as response:
            return await response.json()

    async def set_chat_about(self, chat_id, about):
        async with self._request_cm(
            url="{}/chats/setAbout".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "about": about
            }
        ) as response:
            return await response.json()

    async def set_chat_rules(self, chat_id, rules):
        async with self._request_cm(
            url="{}/chats/setRules".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "rules": rules
            }
        ) as response:
            return await response.json()

    async def get_file_info(self, file_id):
        async with self._request_cm(
            url="{}/files/getInfo".format(self.api_base_url),
            params={
                "token": self.token,
                "fileId": file_id
            }
        ) as response:
            return await response.json()

    async def pin_message(self, chat_id, msg_id):
        async with self._request_cm(
            url="{}/chats/pinMessage".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "msgId": msg_id
            }
        ) as response:
            return await response.json()

    async def unpin_message(self, chat_id, msg_id):
        async with self._request_cm(
            url="{}/chats/unpinMessage".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "msgId": msg_id
            }
        ) as response:
            return await response.json()

    async def add_chat_members(self, chat_id, members):
        async with self._request_cm(
            url="{}/chats/members/add".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "members": json.dumps([{"sn": m} for m in members])
            }
        ) as response:
            return await response.json()

    async def create_chat(
            self, name, about="", rules="", members=None, public=False, join_moderation=False, default_role="member"
    ):
        members = [] if members is None else [members] if type(members) != list else members
        async with self._request_cm(
            url="{}/chats/createChat".format(self.api_base_url),
            params={
                "token": self.token,
                "name": name,
                "about": about,
                "rules": rules,
                "members": json.dumps([{"sn": m} for m in members]),
                "public": "true" if public else "false",
                "defaultRole": default_role,
                "joinModeration": str(join_moderation).lower()
            }
        ) as response:
            return await response.json()

    async def delete_chat_members(self, chat_id, members):
        async with self._request_cm(
            url="{}/chats/members/delete".format(self.api_base_url),
            params={
                "token": self.token,
                "chatId": chat_id,
                "members": json.dumps([{"sn": m} for m in members])
            }
        ) as response:
            return await response.json()
