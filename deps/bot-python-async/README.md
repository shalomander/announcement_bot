# mail.ru python async bot

[Пример бота: example/test_bot.py](./example/test_bot.py)

## Настройка
Для запуска боту необходимы конфиги [logging.ini](./example/logging.ini) и [config.ini](./example/config.ini)

## Статистика
Бот отправляет статитику вызовов функций в graphyte

Включени/отключение данного функционала выполняется через параметр [config.ini:](./example/config.ini)[graphite][enable]

## Логировагие 
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