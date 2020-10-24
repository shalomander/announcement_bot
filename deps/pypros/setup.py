import os
import sys

from setuptools import setup
from setuptools.command.install import install

name = 'pypros'

f = os.path.dirname(os.path.realpath(__file__))
requirementPath = f + '/requirements.txt'
install_requires = []
if os.path.isfile(requirementPath):
    with open(requirementPath) as f:
        install_requires = f.read().splitlines()


class PostInstallCommand(install):
    """Post-installation for installation mode."""
    def run(self):
        install.run(self)
        sps = sys.path
        for sp in sps:
            if os.path.exists(os.path.join(sp, name)):
                print("make icrc32.c in {}".format(os.path.join(sp, name)))
                try:
                    os.system("cd {} && make".format(os.path.join(sp, name)))
                except Exception as e:
                    print('fail to make icrc32.c\n{}\ntry make it manually'.format(e))


setup(
    name=name,
    version='1.0',
    packages=[name],
    url='https://gitlab.corp.mail.ru/icqdev/pypros',
    license='',
    author='a.simonov',
    author_email='a.simonov@corp.mail.ru',
    description='Python implementation of ipros protocol',
    install_requires=install_requires,
    cmdclass={
        'install': PostInstallCommand
    },
    package_data={name: ['icrc32.c', 'Makefile']}
)
