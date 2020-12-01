import inspect
import logging
from asyncio import CancelledError
from functools import wraps
from aiohttp import ContentTypeError

from mailru_im_async_bot import graphyte

try:
    from urllib import parse as urlparse
except ImportError:
    # noinspection PyUnresolvedReferences
    import urlparse


__version__ = "0.2.0"

# Set default logging handler to avoid "No handler found" warnings.
logging.getLogger(__name__).addHandler(logging.NullHandler())
log = logging.getLogger(__name__)


def url_maker(kwargs, url=None):
    """
    Replacement for built-in aiohttp url maker
    Since it can't log the full url composed of query params
    """
    url = kwargs['url'] if 'url' in kwargs else url
    if url and 'params' in kwargs:
        return f"{url}?{urlparse.urlencode(kwargs.pop('params'))}"


def url_maker_decorator(func):
    async def wrapper(*args, **kwargs):
        if 'url' in kwargs:
            kwargs['url'] = url_maker(kwargs)
        return await func(*args, **kwargs)
    return wrapper


def cut_none(params):
    if type(params) == dict:
        return {
            key: cut_none(value) for key, value in params.items() if value is not None
        }

    if type(params) == list:
        if any([type(i) == tuple for i in params]):
            return [i for i in params if i[1] is not None]

    return params


def cut_none_decorator(func):
    async def wrapper(*args, **kwargs):
        return await func(*args, **cut_none(kwargs))
    return wrapper


def try_except_request(func):
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ContentTypeError as e:
            log.warning(f"response is not json: {e}")
            raise
        except CancelledError as e:
            log.info(f"request cancelled: {e}")
        except Exception as e:
            log.exception(e)
            raise
    return wrapper


def stat(*args, **kwargs):
    if graphyte.default_sender is not None:
        graphyte.send(*args, **kwargs)


def stat_decorator(*s_args, **s_kwargs):
    def call_stat(func):
        if s_args == () and s_kwargs == {}:
            s_kwargs['metric'] = f"method.{func.__name__}.cnt"
            s_kwargs['value'] = 1
        stat(*s_args, **s_kwargs)

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            call_stat(func)
            return await func(*args, **kwargs)

        @wraps(func)
        def wrapper(*args, **kwargs):
            call_stat(func)
            return func(*args, **kwargs)

        return async_wrapper if inspect.iscoroutinefunction(func) else wrapper
    return decorator


def prepare_repeated_params(params: list, repeated_values: dict):
    for key, values in repeated_values.items():
        if values is not None:
            values = values if type(values) == list else [values]
            for value in values:
                params.append((key, value))
