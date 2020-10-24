import os
from ctypes import cdll, c_char_p, c_int, c_uint

lib = cdll.LoadLibrary(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + "icrc32.so")
lib.icrc32.restype = c_uint

def calc(s: bytes):
    if isinstance(s, str):
        s = bytes(s, encoding='utf8')
    return lib.icrc32(c_uint(0), c_char_p(s), c_uint(len(s)))
