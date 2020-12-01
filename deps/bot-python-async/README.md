# mail.ru python async bot

[Пример бота: example/test_bot.py](./example/test_bot.py)

## Настройка
Для запуска боту необходимы конфиги [logging.ini](./example/logging.ini) и [config.ini](./example/config.ini)

## Статистика
Бот отправляет статитику вызовов функций в graphyte

Включени/отключение данного функционала выполняется через параметр [config.ini:](./example/config.ini)[graphite][enable]

## Логирование 
Ротация логов происходит по сигналу SIGUSR1 на процесс или pid файл

## Регистрация команд
```python
# Обработчик команд по умочанию
bot.dispatcher.add_handler(DefaultHandler(callback=help))

# Обработчик однострочной команды /run
bot.dispatcher.add_handler(CommandHandler(callback=run, command='run'))

# Обработчик многострочных команд
# На вход функция получит помимо (bot, event) объект user, через который можно ожидать следующий ответ пользователя
bot.dispatcher.add_handler(
    MessageHandler(
        multiline=True,
        callback=hello,
        filters=Filter.text(['Ghbdtn', 'Привет', 'Прив', 'Хай'])
    )
)

async def hello(bot, event, user):
    await bot.send_text(chat_id=event.message_author['userId'], text=f"1 ответ на {event.text}")
    response = await user.wait_response()
    await bot.send_text(chat_id=event.message_author['userId'], text=f"2 ответ на {response.text}")

```
Обработчики многострочных команд ограничены настраивмым таймаутом. Поскольку на момент его работы все евенты от пользователя попадают в отдельную очередь. По завершению обработчика все оставшиеся евенты возвращаются в основую очередь для обработки.

## Настройка приоритетов команд
```python
# Создаем обработчик команды
command_handler = CommandHandler(callback=run, command='command', multiline=True)
# Добавляем его боту
bot.dispatcher.add_handler(command_handler)

# Создаем второй обработчик для сообщений и указываем в переменной ignore handler'ы,
# при которых этот обработчик будет проигнорирован
bot.dispatcher.add_handler(
    MessageHandler(
        callback=hello,
        filters=Filter.text(['Текст сообщения']),
        ignore=[command_handler]
    )
)
# То есть, если command_handler активен (совершает какую либо обработку или ждет сообщения от пользователя), 
# то второй MessageHandler бдет проигнорирован при поступлении сообщения
# ---------------------------------------------------------------------
# Возможно отложенное добавление игноров. Это может понадобится, если два  handler'a должны игнорировать друг друга
# Создаем два handler'a
command_handler = CommandHandler(callback=run, command='command', multiline=True)
message_handler = MessageHandler(
        multiline=True,
        callback=hello,
        filters=Filter.text(['Текст сообщения'])
    )

# Добавлем их друг другу в игнорируемые
command_handler.ignore.append(message_handler)
message_handler.ignore.append(command_handler)

# Добавляем в бота
bot.dispatcher.add_handler(command_handler)
bot.dispatcher.add_handler(message_handler)
```

## Требования к проектам:
#### Python
Версия 3.6

#### OS
Проекты ставятся на Centos7. Не привязывваться к сущностям, которое есть на других операционных системах и нет в этой. Например, сигналы для процессов.

#### Имменование:
Разделителем в имени бота всегда выступает только нижнее подчеркивание.

Например: "test_bot.py", "kiss_bot.py", "new_super_bot.py"

Имя основного файла запуска заканчивается на _bot.py 

#### Конфиги:
Добавляем в проекты примеры конфигов в виде:
* logging.ini.example
* config.ini.example
* {bot_name}.service.example

Файлов logging.ini, config.ini и {bot_name}.service не должно быть в git репозитории. Желательно вообще добавить их в .gitignore

#### Зависимости:
Заполняем requirements.txt

Не включать в requirements.txt библиотеки mailru_im_async_bot и pypros

#### Фоновые задачи:
Если есть задача, которая должна крутиться в фоне, она должна уметь останаливаться по команде. 
Без остановки всего скрипта.
Например как сам бот:
```python
    loop.create_task(bot.start_polling())
    loop.create_task(bot.stop_polling())
```

#### Стиль кода
Придерживаемся PEP8.
Единственное исключение: длина строки 120 символов

После написания кода прогоняем все через [flake8](https://flake8.pycqa.org/) c параметрами 
```
--max-line-lengt="120" --max-complexity="14"
```
Для упрощения можно добавть в Action на github автоматическую проверку. Пример yaml файла
```yaml
# This workflow will install Python dependencies, run tests and lint with a single version of Python
# For more information see: https://help.github.com/actions/language-and-framework-guides/using-python-with-github-actions

name: Python application

on:
  push:
    branches: [ master ]
  pull_request:
    branches: [ master ]

jobs:
  build:

    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2
    - name: Set up Python 3.6
      uses: actions/setup-python@v2
      with:
        python-version: 3.6
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install flake8 pytest
        if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
    - name: Lint with flake8
      run: |
        flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
        flake8 . --count --max-complexity=14 --max-line-length=120 --statistics
```

#### Логирование
Объявляем в каждом файле
```python
    log = logging.getLogger(__name__)
```
Логируем как можно больше данных. Но только не тексты сообщений пользователей.

Логируем все ошибки.
#### Статистика
Если нужна статистика каких-то данных, можно добавить вызов метода
```python
    from mailru_im_async_bot import stat
    stat('some_static_name', some_static_value_int)
```
Например, нужно получать статистику сколько юзеров получили картинок:
После кода, где юзер получил картинку добавляем
```python
    stat('user_get_picture', 1)
```
Метод сделает агрегацию данных и отправит на сервер. То есть, можно не заниматься самостоятельным подсчетом количества. 

Также есть декоратор, если нужно получать статистику по какому-либо методу
```python
    stat_decorator('some_static_method_name', 1)
    def some_static_method_name():
        pass
```
Отправка статистики по методам бота и вызова хендлеров встроена по-умолчанию.


#### БД
Используем только tarantool
* Должна быть схема в  файле *.lua
* Схема должна быть подготовлека к многократному запуску. То есть, созлдание первоначальных объектов оборачивать в box.once
* Все объекты при создании должны содержать флаг if_not_exists = true, если они умеют его принимать.