import sqlite3
from datetime import datetime


DB_NAME = "study_bot.db"


# =========================================================
# CONNECTION
# =========================================================

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# =========================================================
# INIT DATABASE + MIGRATIONS
# =========================================================

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # -----------------------------------------------------
    # USERS
    # -----------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            name TEXT,
            grade TEXT,
            subject TEXT,
            language TEXT DEFAULT 'uz',
            onboarding_completed INTEGER DEFAULT 0,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            streak INTEGER DEFAULT 0,
            last_test_date TEXT,
            created_at TEXT
        )
    """)

    # Migration: eski users jadvaliga yangi ustunlarni qo'shish
    cursor.execute("PRAGMA table_info(users)")
    columns = {row[1] for row in cursor.fetchall()}

    migrations = {
        "language": "ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'uz'",
        "onboarding_completed": "ALTER TABLE users ADD COLUMN onboarding_completed INTEGER DEFAULT 0",
        "xp": "ALTER TABLE users ADD COLUMN xp INTEGER DEFAULT 0",
        "level": "ALTER TABLE users ADD COLUMN level INTEGER DEFAULT 1",
        "streak": "ALTER TABLE users ADD COLUMN streak INTEGER DEFAULT 0",
        "last_test_date": "ALTER TABLE users ADD COLUMN last_test_date TEXT",
        "created_at": "ALTER TABLE users ADD COLUMN created_at TEXT",
    }

    for column, sql in migrations.items():
        if column not in columns:
            cursor.execute(sql)

    # -----------------------------------------------------
    # TEST RESULTS
    # -----------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            test_type TEXT,
            subject TEXT,
            grade TEXT,
            total_questions INTEGER,
            correct_answers INTEGER,
            score_percent REAL,
            level TEXT,
            xp_earned INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    cursor.execute("PRAGMA table_info(test_results)")
    test_columns = {row[1] for row in cursor.fetchall()}

    if "xp_earned" not in test_columns:
        cursor.execute(
            "ALTER TABLE test_results ADD COLUMN xp_earned INTEGER DEFAULT 0"
        )

    # -----------------------------------------------------
    # QUESTION RESULTS
    # -----------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS question_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER,
            telegram_id INTEGER NOT NULL,
            question TEXT,
            topic TEXT,
            selected_answer TEXT,
            correct_answer TEXT,
            is_correct INTEGER,
            created_at TEXT,
            FOREIGN KEY (test_id) REFERENCES test_results(id) ON DELETE CASCADE
        )
    """)

    # -----------------------------------------------------
    # ACHIEVEMENTS
    # -----------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            achievement_key TEXT NOT NULL,
            created_at TEXT,
            UNIQUE(telegram_id, achievement_key)
        )
    """)

    conn.commit()
    conn.close()

    print("✅ Database initialized!")


# =========================================================
# USER
# =========================================================

def create_user(telegram_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO users (
            telegram_id,
            language,
            onboarding_completed,
            xp,
            level,
            streak,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        telegram_id,
        "uz",
        0,
        0,
        1,
        0,
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()


def update_user(telegram_id, field, value):
    allowed_fields = {
        "name",
        "grade",
        "subject",
        "language",
        "onboarding_completed",
        "xp",
        "level",
        "streak",
        "last_test_date",
    }

    if field not in allowed_fields:
        raise ValueError(f"Ruxsat etilmagan field: {field}")

    conn = get_connection()
    cursor = conn.cursor()

    query = f"""
        UPDATE users
        SET {field} = ?
        WHERE telegram_id = ?
    """

    cursor.execute(query, (value, telegram_id))

    conn.commit()
    conn.close()


def get_user(telegram_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            telegram_id,
            name,
            grade,
            subject,
            language,
            onboarding_completed,
            created_at,
            xp,
            level,
            streak,
            last_test_date
        FROM users
        WHERE telegram_id = ?
    """, (telegram_id,))

    user = cursor.fetchone()

    conn.close()
    return user


# =========================================================
# GAMIFICATION
# =========================================================

def xp_for_next_level(level):
    # Level 1 -> 2: 100 XP
    # Level 2 -> 3: 200 XP
    # Level 3 -> 4: 300 XP ...
    return max(100, level * 100)


def calculate_level(total_xp):
    level = 1
    remaining = max(0, int(total_xp))

    while remaining >= xp_for_next_level(level):
        remaining -= xp_for_next_level(level)
        level += 1

    return level


def add_xp(telegram_id, amount):
    amount = max(0, int(amount))

    user = get_user(telegram_id)
    if not user:
        create_user(telegram_id)
        user = get_user(telegram_id)

    old_xp = user[7] or 0
    old_level = user[8] or 1

    new_xp = old_xp + amount
    new_level = calculate_level(new_xp)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE users
        SET xp = ?, level = ?
        WHERE telegram_id = ?
    """, (new_xp, new_level, telegram_id))

    conn.commit()
    conn.close()

    return {
        "old_xp": old_xp,
        "new_xp": new_xp,
        "old_level": old_level,
        "new_level": new_level,
        "leveled_up": new_level > old_level,
        "xp_gained": amount,
    }


def update_streak(telegram_id):
    today = datetime.now().date()

    user = get_user(telegram_id)
    if not user:
        create_user(telegram_id)
        user = get_user(telegram_id)

    old_streak = user[9] or 0
    last_test_date = user[10]

    if last_test_date:
        try:
            last_date = datetime.fromisoformat(last_test_date).date()
        except ValueError:
            last_date = None
    else:
        last_date = None

    if last_date == today:
        new_streak = old_streak
    elif last_date and (today - last_date).days == 1:
        new_streak = old_streak + 1
    else:
        new_streak = 1

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE users
        SET streak = ?, last_test_date = ?
        WHERE telegram_id = ?
    """, (
        new_streak,
        today.isoformat(),
        telegram_id
    ))

    conn.commit()
    conn.close()

    return {
        "old_streak": old_streak,
        "new_streak": new_streak,
        "continued": (
            last_date is not None
            and last_date != today
            and (today - last_date).days == 1
        ),
    }


def get_gamification(telegram_id):
    user = get_user(telegram_id)

    if not user:
        return {
            "xp": 0,
            "level": 1,
            "streak": 0,
            "xp_into_level": 0,
            "xp_for_level": 100,
            "xp_to_next": 100,
        }

    xp = user[7] or 0
    level = user[8] or 1
    streak = user[9] or 0

    # Level chegarasini hisoblash
    spent = sum(xp_for_next_level(i) for i in range(1, level))
    xp_into_level = max(0, xp - spent)
    xp_needed = xp_for_next_level(level)
    xp_to_next = max(0, xp_needed - xp_into_level)

    return {
        "xp": xp,
        "level": level,
        "streak": streak,
        "xp_into_level": xp_into_level,
        "xp_for_level": xp_needed,
        "xp_to_next": xp_to_next,
    }


def calculate_test_xp(total_questions, correct_answers, test_type="diagnostic"):
    total_questions = max(0, int(total_questions))
    correct_answers = max(0, min(int(correct_answers), total_questions))

    # Har bir savol uchun XP + to'g'ri javob bonus
    base_xp = total_questions * 5
    correct_xp = correct_answers * 10

    if test_type == "mock":
        type_bonus = 20
    elif test_type == "specific":
        type_bonus = 15
    else:
        type_bonus = 10

    perfect_bonus = 25 if (
        total_questions > 0 and
        correct_answers == total_questions
    ) else 0

    return base_xp + correct_xp + type_bonus + perfect_bonus


# =========================================================
# TEST RESULTS
# =========================================================

def save_test_result(
    telegram_id,
    test_type,
    subject,
    grade,
    total_questions,
    correct_answers,
    level,
    xp_earned=0
):
    total_questions = max(1, int(total_questions))
    correct_answers = max(0, min(int(correct_answers), total_questions))

    score_percent = (
        correct_answers / total_questions
    ) * 100

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO test_results (
            telegram_id,
            test_type,
            subject,
            grade,
            total_questions,
            correct_answers,
            score_percent,
            level,
            xp_earned,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        telegram_id,
        test_type,
        subject,
        grade,
        total_questions,
        correct_answers,
        score_percent,
        level,
        xp_earned,
        datetime.now().isoformat()
    ))

    test_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return test_id


def save_question_result(
    test_id,
    telegram_id,
    question,
    topic,
    selected_answer,
    correct_answer,
    is_correct
):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO question_results (
            test_id,
            telegram_id,
            question,
            topic,
            selected_answer,
            correct_answer,
            is_correct,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        test_id,
        telegram_id,
        question,
        topic,
        selected_answer,
        correct_answer,
        int(is_correct),
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()


# =========================================================
# HISTORY
# =========================================================

def get_test_history(telegram_id, limit=10):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            test_type,
            subject,
            grade,
            total_questions,
            correct_answers,
            score_percent,
            level,
            xp_earned,
            created_at
        FROM test_results
        WHERE telegram_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (
        telegram_id,
        limit
    ))

    results = cursor.fetchall()

    conn.close()
    return results


# =========================================================
# PROGRESS
# =========================================================

def get_progress(telegram_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*),
            COALESCE(SUM(total_questions), 0),
            COALESCE(SUM(correct_answers), 0),
            COALESCE(AVG(score_percent), 0)
        FROM test_results
        WHERE telegram_id = ?
    """, (telegram_id,))

    row = cursor.fetchone()

    total_tests = row[0]
    total_questions = row[1]
    total_correct = row[2]
    average_score = row[3]

    cursor.execute("""
        SELECT
            topic,
            COUNT(*),
            SUM(is_correct)
        FROM question_results
        WHERE telegram_id = ?
        GROUP BY topic
        ORDER BY topic
    """, (telegram_id,))

    topics = cursor.fetchall()

    conn.close()

    return {
        "total_tests": total_tests,
        "total_questions": total_questions,
        "total_correct": total_correct,
        "average_score": average_score,
        "topics": topics,
    }


# =========================================================
# ACHIEVEMENTS
# =========================================================

ACHIEVEMENTS = {
    "first_test": {
        "name": "🥇 Birinchi test",
        "description": "Birinchi testingizni yakunladingiz.",
    },
    "five_tests": {
        "name": "🔥 5 ta test",
        "description": "5 ta test yakunladingiz.",
    },
    "ten_tests": {
        "name": "🏆 10 ta test",
        "description": "10 ta test yakunladingiz.",
    },
    "perfect_test": {
        "name": "💯 Perfect",
        "description": "100% natija oldingiz.",
    },
    "streak_3": {
        "name": "🔥 3 kunlik streak",
        "description": "3 kun ketma-ket test ishladingiz.",
    },
    "streak_7": {
        "name": "⚡ 7 kunlik streak",
        "description": "7 kun ketma-ket test ishladingiz.",
    },
}


def unlock_achievement(telegram_id, achievement_key):
    if achievement_key not in ACHIEVEMENTS:
        return False

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO user_achievements (
            telegram_id,
            achievement_key,
            created_at
        )
        VALUES (?, ?, ?)
    """, (
        telegram_id,
        achievement_key,
        datetime.now().isoformat()
    ))

    created = cursor.rowcount == 1

    conn.commit()
    conn.close()

    return created


def get_achievements(telegram_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT achievement_key, created_at
        FROM user_achievements
        WHERE telegram_id = ?
        ORDER BY id DESC
    """, (telegram_id,))

    rows = cursor.fetchall()
    conn.close()

    return rows


def check_and_unlock_achievements(
    telegram_id,
    score_percent,
    streak
):
    unlocked = []

    progress = get_progress(telegram_id)
    total_tests = progress["total_tests"]

    checks = []

    if total_tests >= 1:
        checks.append("first_test")

    if total_tests >= 5:
        checks.append("five_tests")

    if total_tests >= 10:
        checks.append("ten_tests")

    if score_percent >= 100:
        checks.append("perfect_test")

    if streak >= 3:
        checks.append("streak_3")

    if streak >= 7:
        checks.append("streak_7")

    for key in checks:
        if unlock_achievement(telegram_id, key):
            unlocked.append(ACHIEVEMENTS[key])

    return unlocked
