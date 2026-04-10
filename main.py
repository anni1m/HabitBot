import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import psycopg2
import os
import time
from datetime import date

# ================== ENV ==================
DATABASE_URL = "postgresql://postgres:dDeBhbcdRnbzXQDpLucowSLYTwfwKVfU@postgres.railway.internal:5432/railway"
VK_TOKEN = "vk1.a.JfQYO98XK7OY13qrDBwjQtKBUWIX3MP6AqPTlw7DT6Z8_-tIzzwxgOZKq7d4lvW4FE_jWfjUPmeN3tUV6RqqVz304_ipl7Dul3UaMqL7E2TbsNtOgNlOnp2jOfZkDWFY59GBm6H4YHP3mjbDWzcYqFSC2Dj-0MT5QN373HXe9k0HzGjtYziLq9xU90GMLosEEsk_7kpEjzjwy14fPIrixQ"
GROUP_ID = 237312363

if not DATABASE_URL:
    raise Exception("DATABASE_URL не задана")
if not VK_TOKEN:
    raise Exception("VK_TOKEN не задан")
if not GROUP_ID:
    raise Exception("GROUP_ID не задан")

# ================== DB ==================
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            vk_id BIGINT PRIMARY KEY,
            full_name TEXT,
            registered_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            habit_id SERIAL PRIMARY KEY,
            habit_name TEXT NOT NULL,
            habit_key TEXT NOT NULL,
            unit TEXT,
            target_value FLOAT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS habit_logs (
            log_id SERIAL PRIMARY KEY,
            vk_id BIGINT REFERENCES users(vk_id),
            habit_id INT REFERENCES habits(habit_id),
            actual_value FLOAT,
            log_date DATE DEFAULT CURRENT_DATE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("SELECT COUNT(*) FROM habits")
    if cur.fetchone()[0] == 0:
        habits = [
            ('Пить воду', 'water', 'стаканов', 8),
            ('Зарядка', 'exercise', 'минут', 15),
            ('Чтение', 'reading', 'страниц', 20),
            ('Медитация', 'meditation', 'минут', 10),
            ('Ранний подъём', 'early_bird', 'раз', 1)
        ]
        for h in habits:
            cur.execute(
                "INSERT INTO habits (habit_name, habit_key, unit, target_value) VALUES (%s, %s, %s, %s)", h
            )

    conn.commit()
    cur.close()
    conn.close()


def get_habits():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT habit_id, habit_name, habit_key, unit, target_value FROM habits")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def log_habit(vk_id, habit_id, value):
    conn = get_db_connection()
    cur = conn.cursor()
    today = date.today()

    cur.execute(
        "SELECT log_id FROM habit_logs WHERE vk_id = %s AND habit_id = %s AND log_date = %s",
        (vk_id, habit_id, today)
    )
    existing = cur.fetchone()

    if existing:
        cur.execute(
            "UPDATE habit_logs SET actual_value = %s WHERE log_id = %s",
            (value, existing[0])
        )
    else:
        cur.execute(
            "INSERT INTO habit_logs (vk_id, habit_id, actual_value, log_date) VALUES (%s, %s, %s, %s)",
            (vk_id, habit_id, value, today)
        )

    conn.commit()
    cur.close()
    conn.close()


def get_today_stats(vk_id):
    conn = get_db_connection()
    cur = conn.cursor()
    today = date.today()

    cur.execute("""
        SELECT h.habit_name, h.unit, h.target_value, l.actual_value
        FROM habits h
        LEFT JOIN habit_logs l 
        ON h.habit_id = l.habit_id AND l.vk_id = %s AND l.log_date = %s
        ORDER BY h.habit_id
    """, (vk_id, today))

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def get_achievements_count(vk_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) 
        FROM habit_logs l
        JOIN habits h ON l.habit_id = h.habit_id
        WHERE l.vk_id = %s AND l.actual_value >= h.target_value
    """, (vk_id,))

    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count


# ================== UI ==================
def get_main_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button('✅ Отметить привычку', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('📊 Моя статистика', color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button('📋 Список привычек', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('❓ Помощь', color=VkKeyboardColor.SECONDARY)
    return keyboard


def get_habits_keyboard():
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button('💧 Пить воду', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('🤸 Зарядка', color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button('📚 Чтение', color=VkKeyboardColor.PRIMARY)
    keyboard.add_button('🧘 Медитация', color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button('🌅 Ранний подъём', color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button('❌ Отмена', color=VkKeyboardColor.NEGATIVE)
    return keyboard


def get_cancel_keyboard():
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button('❌ Отмена', color=VkKeyboardColor.NEGATIVE)
    return keyboard


def send_message(vk, peer_id, message, keyboard=None):
    params = {
        'peer_id': peer_id,
        'message': message,
        'random_id': int(time.time() * 1000)
    }
    if keyboard:
        params['keyboard'] = keyboard.get_keyboard()
    vk.messages.send(**params)


# ================== BOT ==================
def main():
    print("Запуск бота...")
    print("DATABASE_URL:", DATABASE_URL)
    init_db()
    print("База данных подключена")

    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, GROUP_ID)

    print("Бот работает")

    user_states = {}

    for event in longpoll.listen():
        if event.type != VkBotEventType.MESSAGE_NEW:
            continue

        msg = event.object.message
        user_id = msg['from_id']
        text = msg['text'].strip()
        peer_id = msg['peer_id']

        if text == "✅ Отметить привычку":
            send_message(vk, peer_id, "Выбери привычку:", get_habits_keyboard())

        elif text in ["💧 Пить воду", "🤸 Зарядка", "📚 Чтение", "🧘 Медитация", "🌅 Ранний подъём"]:
            mapping = {
                "💧 Пить воду": "water",
                "🤸 Зарядка": "exercise",
                "📚 Чтение": "reading",
                "🧘 Медитация": "meditation",
                "🌅 Ранний подъём": "early_bird"
            }
            user_states[user_id] = mapping[text]

            prompts = {
                "water": "Сколько стаканов?",
                "exercise": "Сколько минут?",
                "reading": "Сколько страниц?",
                "meditation": "Сколько минут?",
                "early_bird": "1 да / 0 нет"
            }
            send_message(vk, peer_id, prompts[mapping[text]], get_cancel_keyboard())

        elif text == "📊 Моя статистика":
            stats = get_today_stats(user_id)
            achievements = get_achievements_count(user_id)
            msg_text = "📊 Твоя статистика:\n\n"
            for name, unit, target, actual in stats:
                msg_text += f"{name}: {actual}/{target} {unit}\n" if actual else f"{name}: не отмечено\n"
            msg_text += f"\n🏆 Всего достижений: {achievements}"
            send_message(vk, peer_id, msg_text, get_main_keyboard())

        elif text == "📋 Список привычек":
            habits = get_habits()
            msg_text = "📋 Список привычек:\n\n"
            for h in habits:
                msg_text += f"{h[1]} — {h[4]} {h[3]}\n"
            send_message(vk, peer_id, msg_text, get_main_keyboard())

        elif text == "❓ Помощь":
            send_message(
                vk, peer_id,
                "✅ Отметить привычку - записать выполнение\n📊 Моя статистика - посмотреть прогресс\n📋 Список привычек - все привычки",
                get_main_keyboard()
            )

        elif text == "❌ Отмена":
            user_states.pop(user_id, None)
            send_message(vk, peer_id, "Отменено", get_main_keyboard())

        elif user_id in user_states:
            try:
                value = float(text)
                habit_key = user_states[user_id]
                habits = get_habits()
                for h in habits:
                    if h[2] == habit_key:
                        log_habit(user_id, h[0], value)
                        status = "✅" if value >= h[4] else "⚠️"
                        send_message(vk, peer_id, f"{status} {h[1]}: {value}/{h[4]} {h[3]}", get_main_keyboard())
                        break
                user_states.pop(user_id, None)
            except ValueError:
                send_message(vk, peer_id, "Введи число", get_cancel_keyboard())

        else:
            send_message(vk, peer_id, "Используй кнопки", get_main_keyboard())


if __name__ == "__main__":
    main()
