import logging
from asyncio import CancelledError
from functools import wraps
from traceback import format_exc
import graphyte
from aiohttp import ContentTypeError

try:
    from urllib import parse as urlparse
except ImportError:
    # noinspection PyUnresolvedReferences
    import urlparse


__version__ = "0.0.11"

# Set default logging handler to avoid "No handler found" warnings.
logging.getLogger(__name__).addHandler(logging.NullHandler())
log = logging.getLogger(__name__)


def url_maker(func):
    """
    Replacement for built-in aiohttp url maker
    Since it can't log the full url composed of query params
    """
    async def wrapper(*args, **kwargs):
        if 'url' in kwargs and 'params' in kwargs:
            kwargs['url'] = f"{kwargs['url']}?{urlparse.urlencode(kwargs.pop('params'))}"
        return await func(*args, **kwargs)
    return wrapper


def cut_none(func):
    def cut(params):
        return {
            key: (value if not isinstance(value, dict) else cut(value))
            for (key, value) in params.items() if value is not None
        }

    async def wrapper(*args, **kwargs):
        return await func(*args, **cut(kwargs))
    return wrapper


def try_except_request(func):
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ContentTypeError as e:
            log.warning('response is not json')
        except CancelledError as e:
            log.info('request cancelled')
        except:
            log.exception(format_exc())
    return wrapper


def stat(*args, **kwargs):
    if graphyte.default_sender is not None:
        graphyte.send(*args, **kwargs)


def stat_decorator(*s_args, **s_kwargs):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if s_args == () and s_kwargs == {}:
                s_kwargs['metric'] = func.__name__
                s_kwargs['value'] = 1
            stat(*s_args, **s_kwargs)
            return await func(*args, **kwargs)
        return wrapper
    return decorator

