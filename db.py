import tarantool
from config import config
import logging

log = logging.getLogger(__name__)

__db = tarantool.connect(config.get('tarantool', 'host'), config.get('tarantool', 'port'))


def insert(space_name, args) -> tuple:
    __db.insert(space_name, args)
    return args


def replace(space_name, args) -> tuple:
    __db.replace(space_name, args)
    return args


def select(space_name, primary_key=None) -> list:
    return __db.select(space_name, primary_key if primary_key else None)


def delete(space_name, unique_key) -> list:
    return __db.delete(space_name, unique_key)


def select_index(space_name, arg, index) -> list:
    return __db.select(space_name, arg, index=index)


def exist_index(space_name, arg, index) -> bool:
    return True if __db.select(space_name, arg, index=index) else False


def upsert(space_name, tuple_value, op_list) -> tuple:
    return __db.upsert(space_name, tuple_value, op_list)


def update(space_name, key, op_list) -> tuple:
    return __db.update(space_name, key, op_list)


def close():
    return __db.close()

