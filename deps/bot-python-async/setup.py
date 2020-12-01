import os
from setuptools import setup
import mailru_im_async_bot

name = 'mailru_im_async_bot'

f = os.path.dirname(os.path.realpath(__file__))
requirementPath = f + './requirements.txt'
install_requires = []
if os.path.isfile(requirementPath):
    with open(requirementPath) as f:
        install_requires = f.read().splitlines()


setup(
    name=name,
    version=mailru_im_async_bot.__version__,
    packages=[name],
    license='',
    author='e.sineokov',
    author_email='e.sineokov@corp.mail.ru',
    description='python async bot library',
    install_requires=install_requires,
)
