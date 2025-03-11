import logging
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, JobQueue

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

# Хранение записей (можно заменить на базу данных)
appointments = {}
available_slots = {}

# Длительность процедур
service_durations = {
    "Ботулинотерапия": 45,
    "Чистка": 90
}

# Генерация доступных слотов на день
def generate_available_slots(date_str):
    """Генерируем доступные слоты на день"""
    date = datetime.strptime(date_str, "%d.%m.%Y")
    slots = []
    start_time = datetime(date.year, date.month, date.day, 9, 0)
    end_time = datetime(date.year, date.month, date.day, 20, 0)

    while start_time < end_time:
        slots.append(start_time.strftime("%d.%m.%Y %H:%M"))
        start_time += timedelta(hours=1)  # Интервал 1 час
    return slots

# Функция /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_keyboard = [['Записаться на прием', 'Часы работы', 'Услуги', 'Когда у меня запись?']]
    await update.message.reply_text(
        'Привет! 👋 Я бот-администратор **Healthy Skin Aesthetics**.\n\n'
        'Вот что я умею:\n'
        '🔹 **Записаться на прием** – выберите услугу, дату и время.\n'
        '🔹 **Проверить вашу запись** – узнайте, когда у вас назначен визит.\n'
        '🔹 **Узнать часы работы** – график работы салона.\n'
        '🔹 **Посмотреть список услуг** – доступные процедуры и уходовые программы.\n'
        '🔹 **Получать напоминания** – я напомню вам за 1 час до записи.\n\n'
        'Выберите действие из меню ниже 👇',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )

# Функция для отправки напоминаний
async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if job.data:
        await context.bot.send_message(job.data, text='Напоминание: у вас есть запись в наш салон сегодня!')

# Обработка сообщений от пользователей
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    user_id = update.message.chat.id  

    if text == 'Назад':
        reply_keyboard = [['Записаться на прием', 'Часы работы', 'Услуги', 'Когда у меня запись?']]
        await update.message.reply_text(
            'Вы вернулись в главное меню.',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
        )
        context.user_data.clear()
        return

    if text == 'Записаться на прием':
        reply_keyboard = [['Чистка', 'Ботулинотерапия']]
        await update.message.reply_text(
            'Пожалуйста, выберите услугу:',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
        )
        context.user_data['awaiting_service'] = True
    elif context.user_data.get('awaiting_service'):
        context.user_data['service'] = text
        await update.message.reply_text('Введите дату в формате "ДД.ММ.ГГГГ".')
        context.user_data['awaiting_service'] = False
        context.user_data['awaiting_date'] = True
    elif context.user_data.get('awaiting_date'):
        date = text
        available_slots[date] = generate_available_slots(date)
        reply_keyboard = [[slot] for slot in available_slots[date]]
        await update.message.reply_text(
            'Выберите время:',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
        )
        context.user_data['selected_date'] = date
        context.user_data['awaiting_date'] = False
        context.user_data['awaiting_time'] = True
    elif context.user_data.get('awaiting_time'):
        selected_time = text
        service = context.user_data['service']
        duration = service_durations[service]

        # Проверка занятых слотов
        appointment_time = datetime.strptime(selected_time, '%d.%m.%Y %H:%M')
        end_time = appointment_time + timedelta(minutes=duration)

        for _, time in appointments.values():
            booked_time = datetime.strptime(time, '%d.%m.%Y %H:%M')
            booked_end = booked_time + timedelta(minutes=service_durations[appointments[user_id][0]])

            if (appointment_time < booked_end) and (booked_time < end_time):
                await update.message.reply_text('Этот слот пересекается с другой записью. Выберите другое время.')
                return

        # Запись пользователя
        appointments[user_id] = (service, selected_time)

        # Блокировка слотов
        selected_date = context.user_data['selected_date']
        if selected_date in available_slots:
            new_slots = []
            for slot in available_slots[selected_date]:
                slot_time = datetime.strptime(slot, '%d.%m.%Y %H:%M')
                if slot_time >= end_time or slot_time < appointment_time:
                    new_slots.append(slot)
            available_slots[selected_date] = new_slots

        await update.message.reply_text(
            f'Запись на {service} {selected_time} подтверждена! Напоминание за 1 час до процедуры.'
        )

        # Установка напоминания за 1 час
        reminder_time = appointment_time - timedelta(hours=1)
        delay = (reminder_time - datetime.now()).total_seconds()

        if delay > 0:
            context.job_queue.run_once(send_reminder, delay, data=user_id)

        # Очистка данных пользователя
        context.user_data.clear()

        # Возвращение в главное меню
        reply_keyboard = [['Записаться на прием', 'Часы работы', 'Услуги', 'Когда у меня запись?']]
        await update.message.reply_text(
            'Вы вернулись в главное меню.',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
        )

    elif text == 'Часы работы':
        await update.message.reply_text('Мы работаем с 9:00 до 20:00, пн-сб.')
    elif text == 'Услуги':
        await update.message.reply_text('Доступные услуги:\n- Чистка (90 минут)\n- Ботулинотерапия (45 минут)')
    elif text == 'Когда у меня запись?':
        if user_id in appointments:
            service, appointment_time = appointments[user_id]
            await update.message.reply_text(f'Ваша запись: {service} на {appointment_time}.')
        else:
            await update.message.reply_text('У вас нет записей.')

# Обработка ошибок
def error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning(f'Update {update} caused error {context.error}')

# Основная функция запуска бота
def main():
    token = '8181202531:AAHYmgGNpU4BndY7leECn6RpE0LmDD6T6b8'
    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error)

    application.run_polling()

if __name__ == '__main__':
    main()
