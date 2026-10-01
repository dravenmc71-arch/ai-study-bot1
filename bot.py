import asyncio
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from dotenv import load_dotenv

from database import (
    init_db,
    create_user,
    update_user,
    get_user,
    save_test_result,
    save_question_result,
    get_test_history,
    get_progress,
    add_xp,
    update_streak,
    get_gamification,
    calculate_test_xp,
    get_achievements,
    check_and_unlock_achievements,
)

from services.ai import (
    generate_diagnostic_test,
    analyze_diagnostic_results,
    ai_tutor_explain,
    ai_tutor_answer,
    ai_tutor_exercise,
)


# =========================================================
# ENV
# =========================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")


# =========================================================
# BOT
# =========================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# =========================================================
# STATES
# =========================================================

class Onboarding(StatesGroup):
    waiting_name = State()
    waiting_grade = State()
    waiting_subject = State()
    waiting_language = State()


class Diagnostic(StatesGroup):
    taking_test = State()


class SpecificTest(StatesGroup):
    taking_test = State()


class AITutor(StatesGroup):
    waiting_explanation_topic = State()
    waiting_question = State()
    waiting_exercise_topic = State()


# =========================================================
# SUBJECTS
# =========================================================

SUBJECTS = {
    "math": "🧮 Matematika",
    "english": "🇬🇧 Ingliz tili",
    "physics": "⚡ Fizika",
    "chemistry": "🧪 Kimyo",
}


# =========================================================
# LANGUAGES
# =========================================================

LANGUAGES = {
    "uz": "🇺🇿 O‘zbek tili",
    "en": "🇬🇧 English",
    "ru": "🇷🇺 Русский",
}


# =========================================================
# TEXTS
# =========================================================

TEXTS = {
    "uz": {
        "hello": "👋 Xush kelibsiz!",
        "main": "Quyidagi bo‘limlardan birini tanlang:",
        "settings": "⚙️ Sozlamalar",
        "change_subject": "📚 Fanni o‘zgartirish",
        "change_grade": "🎓 Darajani o‘zgartirish",
        "change_language": "🌐 Tilni o‘zgartirish",
        "back": "🏠 Asosiy menyu",
        "test": "🧠 Testni boshlash",
        "progress": "📊 Progress",
        "history": "📜 Test tarixi",
        "ai_tutor": "🤖 AI Tutor",
        "gamification": "🎮 XP & Achievements",
    },
    "en": {
        "hello": "👋 Welcome!",
        "main": "Choose one of the sections below:",
        "settings": "⚙️ Settings",
        "change_subject": "📚 Change subject",
        "change_grade": "🎓 Change level",
        "change_language": "🌐 Change language",
        "back": "🏠 Main menu",
        "test": "🧠 Start test",
        "progress": "📊 Progress",
        "history": "📜 Test history",
        "ai_tutor": "🤖 AI Tutor",
        "gamification": "🎮 XP & Achievements",
    },
    "ru": {
        "hello": "👋 Добро пожаловать!",
        "main": "Выберите нужный раздел:",
        "settings": "⚙️ Настройки",
        "change_subject": "📚 Изменить предмет",
        "change_grade": "🎓 Изменить класс",
        "change_language": "🌐 Изменить язык",
        "back": "🏠 Главное меню",
        "test": "🧠 Начать тест",
        "progress": "📊 Прогресс",
        "history": "📜 История тестов",
        "ai_tutor": "🤖 AI Tutor",
        "gamification": "🎮 XP и достижения",
    },
}


# =========================================================
# HELPERS
# =========================================================

def get_user_language(telegram_id):
    user = get_user(telegram_id)

    if not user:
        return "uz"

    language = user[4]

    if language not in LANGUAGES:
        return "uz"

    return language


def get_user_profile(telegram_id):
    user = get_user(telegram_id)
    if not user:
        return None

    return {
        "telegram_id": user[0],
        "name": user[1],
        "grade": user[2],
        "subject": user[3],
        "language": user[4],
        "onboarding_completed": user[5],
        "created_at": user[6],
        "xp": user[7] or 0,
        "level": user[8] or 1,
        "streak": user[9] or 0,
        "last_test_date": user[10],
    }


def escape_html(text):
    if text is None:
        return ""

    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def level_progress_bar(current, total, size=10):
    if total <= 0:
        return "░" * size

    filled = int((current / total) * size)
    filled = max(0, min(size, filled))

    return "█" * filled + "░" * (size - filled)


def test_level(score):
    if score >= 80:
        return "advanced"
    elif score >= 60:
        return "intermediate"
    return "beginner"


# =========================================================
# MAIN MENU
# =========================================================

def main_menu_keyboard(language="uz"):
    t = TEXTS[language]

    keyboard = InlineKeyboardBuilder()

    keyboard.button(
        text=t["test"],
        callback_data="menu_test"
    )

    keyboard.button(
        text=t["progress"],
        callback_data="menu_progress"
    )

    keyboard.button(
        text=t["history"],
        callback_data="menu_history"
    )

    keyboard.button(
        text=t["gamification"],
        callback_data="menu_gamification"
    )

    keyboard.button(
        text=t["ai_tutor"],
        callback_data="menu_ai_tutor"
    )

    keyboard.button(
        text=t["settings"],
        callback_data="settings"
    )

    keyboard.adjust(1, 2, 1, 1, 1)

    return keyboard.as_markup()


async def show_main_menu(message: Message, edit=False):
    user = get_user(message.chat.id)

    if not user:
        return

    name = user[1] or message.from_user.first_name
    grade = user[2] or "-"
    subject = user[3] or "-"

    language = user[4] if user[4] in LANGUAGES else "uz"
    t = TEXTS[language]

    subject_name = SUBJECTS.get(subject, subject)
    language_name = LANGUAGES.get(language, language)

    game = get_gamification(message.chat.id)

    text = (
        "🎓 <b>AI Study Bot</b>\n\n"
        f"{t['hello']} <b>{escape_html(name)}</b>!\n\n"
        f"📚 Fan: <b>{subject_name}</b>\n"
        f"🎓 Daraja: <b>{escape_html(grade)}</b>\n"
        f"🌐 Til: <b>{language_name}</b>\n"
        f"⭐ Level: <b>{game['level']}</b> | "
        f"XP: <b>{game['xp']}</b>\n"
        f"🔥 Streak: <b>{game['streak']} kun</b>\n\n"
        f"{t['main']}"
    )

    keyboard = main_menu_keyboard(language)

    if edit:
        await message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    else:
        await message.answer(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )


def back_keyboard(language="uz"):
    keyboard = InlineKeyboardBuilder()

    keyboard.button(
        text=TEXTS[language]["back"],
        callback_data="back_to_menu"
    )

    return keyboard.as_markup()


# =========================================================
# START
# =========================================================

@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)

    if user and user[5] == 1:
        await state.clear()
        await show_main_menu(message)
        return

    create_user(message.from_user.id)

    await state.set_state(Onboarding.waiting_name)

    await message.answer(
        "🎓 <b>AI Study Bot</b>\n\n"
        "Sizga mos testlar va AI Tutor yaratish uchun "
        "profilingizni sozlaymiz.\n\n"
        "👤 <b>Ismingizni kiriting:</b>",
        parse_mode="HTML"
    )


# =========================================================
# ONBOARDING
# =========================================================

@dp.message(Onboarding.waiting_name)
async def get_name(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Iltimos, ismingizni kiriting.")
        return

    name = message.text.strip()

    if len(name) < 2:
        await message.answer("Iltimos, ismingizni to‘g‘ri kiriting.")
        return

    update_user(message.from_user.id, "name", name)

    await state.set_state(Onboarding.waiting_grade)

    keyboard = InlineKeyboardBuilder()

    keyboard.button(text="5–7-sinf", callback_data="grade_5_7")
    keyboard.button(text="8–9-sinf", callback_data="grade_8_9")
    keyboard.button(text="10–11-sinf", callback_data="grade_10_11")
    keyboard.button(text="Universitet", callback_data="grade_university")

    keyboard.adjust(2)

    await message.answer(
        "🎓 <b>Qaysi darajada o‘qiysiz?</b>",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )


@dp.callback_query(
    Onboarding.waiting_grade,
    F.data.startswith("grade_")
)
async def get_grade(callback: CallbackQuery, state: FSMContext):
    grade = callback.data.replace("grade_", "")

    update_user(
        callback.from_user.id,
        "grade",
        grade
    )

    await state.set_state(Onboarding.waiting_subject)

    keyboard = InlineKeyboardBuilder()

    for key, name in SUBJECTS.items():
        keyboard.button(
            text=name,
            callback_data=f"subject_{key}"
        )

    keyboard.adjust(2)

    await callback.message.edit_text(
        "📚 <b>Qaysi fan bo‘yicha boshlaymiz?</b>",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )

    await callback.answer()


@dp.callback_query(
    Onboarding.waiting_subject,
    F.data.startswith("subject_")
)
async def get_subject(callback: CallbackQuery, state: FSMContext):
    subject = callback.data.replace("subject_", "")

    if subject not in SUBJECTS:
        await callback.answer("Noto‘g‘ri fan.", show_alert=True)
        return

    update_user(
        callback.from_user.id,
        "subject",
        subject
    )

    update_user(
        callback.from_user.id,
        "onboarding_completed",
        1
    )

    update_user(
        callback.from_user.id,
        "language",
        "uz"
    )

    await state.clear()

    keyboard = InlineKeyboardBuilder()

    keyboard.button(
        text="🌐 Tilni tanlash",
        callback_data="settings_language"
    )

    keyboard.button(
        text="🧠 Diagnostic test",
        callback_data="start_diagnostic"
    )

    keyboard.adjust(1)

    await callback.message.edit_text(
        "✅ <b>Profilingiz tayyor!</b>\n\n"
        f"📚 Fan: <b>{SUBJECTS.get(subject)}</b>\n"
        "🌐 Til: <b>🇺🇿 O‘zbek tili</b>\n\n"
        "Avval test tilini tanlashingiz mumkin.",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )

    await callback.answer()


# =========================================================
# SETTINGS
# =========================================================

@dp.callback_query(F.data == "settings")
async def settings_handler(callback: CallbackQuery):
    user = get_user(callback.from_user.id)

    if not user:
        await callback.answer(
            "Avval /start ni bosing.",
            show_alert=True
        )
        return

    language = user[4] if user[4] in LANGUAGES else "uz"
    t = TEXTS[language]

    name = user[1] or "-"
    grade = user[2] or "-"
    subject = SUBJECTS.get(user[3], user[3] or "-")
    language_name = LANGUAGES.get(language)

    keyboard = InlineKeyboardBuilder()

    keyboard.button(
        text=t["change_subject"],
        callback_data="settings_subject"
    )

    keyboard.button(
        text=t["change_grade"],
        callback_data="settings_grade"
    )

    keyboard.button(
        text=t["change_language"],
        callback_data="settings_language"
    )

    keyboard.button(
        text=t["back"],
        callback_data="back_to_menu"
    )

    keyboard.adjust(1)

    await callback.message.edit_text(
        f"{t['settings']}\n\n"
        f"👤 <b>{escape_html(name)}</b>\n"
        f"📚 {subject}\n"
        f"🎓 {escape_html(grade)}\n"
        f"🌐 {language_name}\n\n"
        "Kerakli sozlamani tanlang:",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )

    await callback.answer()


@dp.callback_query(F.data == "settings_subject")
async def settings_subject(callback: CallbackQuery):
    language = get_user_language(callback.from_user.id)

    keyboard = InlineKeyboardBuilder()

    for key, name in SUBJECTS.items():
        keyboard.button(
            text=name,
            callback_data=f"change_subject_{key}"
        )

    keyboard.button(
        text=TEXTS[language]["back"],
        callback_data="settings"
    )

    keyboard.adjust(2, 1)

    await callback.message.edit_text(
        "📚 <b>Fanni tanlang:</b>",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("change_subject_"))
async def change_subject(callback: CallbackQuery):
    subject = callback.data.replace("change_subject_", "")

    if subject not in SUBJECTS:
        await callback.answer(
            "Noto‘g‘ri fan.",
            show_alert=True
        )
        return

    update_user(
        callback.from_user.id,
        "subject",
        subject
    )

    await callback.answer("✅ Fan o‘zgartirildi!")
    await settings_handler(callback)


@dp.callback_query(F.data == "settings_grade")
async def settings_grade(callback: CallbackQuery):
    language = get_user_language(callback.from_user.id)

    keyboard = InlineKeyboardBuilder()

    keyboard.button(
        text="5–7-sinf",
        callback_data="change_grade_5_7"
    )

    keyboard.button(
        text="8–9-sinf",
        callback_data="change_grade_8_9"
    )

    keyboard.button(
        text="10–11-sinf",
        callback_data="change_grade_10_11"
    )

    keyboard.button(
        text="Universitet",
        callback_data="change_grade_university"
    )

    keyboard.button(
        text=TEXTS[language]["back"],
        callback_data="settings"
    )

    keyboard.adjust(2)

    await callback.message.edit_text(
        "🎓 <b>Darajani tanlang:</b>",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("change_grade_"))
async def change_grade(callback: CallbackQuery):
    grade = callback.data.replace("change_grade_", "")

    valid = {
        "5_7",
        "8_9",
        "10_11",
        "university"
    }

    if grade not in valid:
        await callback.answer(
            "Noto‘g‘ri daraja.",
            show_alert=True
        )
        return

    update_user(
        callback.from_user.id,
        "grade",
        grade
    )

    await callback.answer("✅ Daraja o‘zgartirildi!")
    await settings_handler(callback)


@dp.callback_query(F.data == "settings_language")
async def settings_language(callback: CallbackQuery):
    keyboard = InlineKeyboardBuilder()

    keyboard.button(
        text="🇺🇿 O‘zbek tili",
        callback_data="change_language_uz"
    )

    keyboard.button(
        text="🇬🇧 English",
        callback_data="change_language_en"
    )

    keyboard.button(
        text="🇷🇺 Русский",
        callback_data="change_language_ru"
    )

    keyboard.button(
        text="⬅️ Orqaga",
        callback_data="settings"
    )

    keyboard.adjust(1)

    await callback.message.edit_text(
        "🌐 <b>Tilni tanlang:</b>",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("change_language_"))
async def change_language(callback: CallbackQuery):
    language = callback.data.replace("change_language_", "")

    if language not in LANGUAGES:
        await callback.answer(
            "Noto‘g‘ri til.",
            show_alert=True
        )
        return

    update_user(
        callback.from_user.id,
        "language",
        language
    )

    await callback.answer("✅ Til o‘zgartirildi!")
    await settings_handler(callback)


# =========================================================
# TEST MENU
# =========================================================

@dp.callback_query(F.data == "menu_test")
async def menu_test(callback: CallbackQuery):
    language = get_user_language(callback.from_user.id)

    keyboard = InlineKeyboardBuilder()

    keyboard.button(
        text="🧠 Diagnostic Test",
        callback_data="start_diagnostic"
    )

    keyboard.button(
        text="🎯 Specific Test",
        callback_data="specific_test"
    )

    keyboard.button(
        text="📝 Mock Test",
        callback_data="mock_test"
    )

    keyboard.button(
        text=TEXTS[language]["back"],
        callback_data="back_to_menu"
    )

    keyboard.adjust(1)

    await callback.message.edit_text(
        "🧠 <b>Testlar</b>\n\n"
        "Kerakli test turini tanlang:",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )

    await callback.answer()


# =========================================================
# DIAGNOSTIC TEST
# =========================================================

@dp.callback_query(F.data == "start_diagnostic")
async def start_diagnostic(
    callback: CallbackQuery,
    state: FSMContext
):
    user = get_user(callback.from_user.id)

    if not user:
        await callback.answer(
            "Avval /start orqali profilingizni yarating.",
            show_alert=True
        )
        return

    grade = user[2]
    subject = user[3]
    language = user[4] if user[4] in LANGUAGES else "uz"

    await callback.message.edit_text(
        "🧠 <b>Diagnostic test tayyorlanmoqda...</b>\n\n"
        f"📚 Fan: {SUBJECTS.get(subject)}\n"
        f"🎓 Daraja: {escape_html(grade)}\n"
        f"🌐 Til: {LANGUAGES[language]}\n\n"
        "🤖 AI siz uchun savollar yaratmoqda...",
        parse_mode="HTML"
    )

    try:
        test = await generate_diagnostic_test(
            subject=subject,
            grade=grade,
            language=language,
            question_count=5
        )

        questions = test["questions"]

        if not questions:
            raise ValueError("AI bo'sh test qaytardi.")

    except Exception as e:
        print("AI ERROR:", e)

        keyboard = InlineKeyboardBuilder()

        keyboard.button(
            text="🔄 Qayta urinish",
            callback_data="start_diagnostic"
        )

        keyboard.button(
            text=TEXTS[language]["back"],
            callback_data="back_to_menu"
        )

        keyboard.adjust(1)

        await callback.message.edit_text(
            "❌ <b>Testni yaratishda xatolik.</b>\n\n"
            "Iltimos, qayta urinib ko‘ring.",
            reply_markup=keyboard.as_markup(),
            parse_mode="HTML"
        )

        await callback.answer()
        return

    await state.update_data(
        questions=questions,
        current_question=0,
        answers=[],
        language=language,
        test_type="diagnostic"
    )

    await state.set_state(Diagnostic.taking_test)

    await send_question(
        callback.message,
        questions,
        0,
        language,
        "diagnostic"
    )

    await callback.answer()


# =========================================================
# SPECIFIC TEST
# =========================================================

@dp.callback_query(F.data == "specific_test")
async def specific_test_menu(callback: CallbackQuery):
    language = get_user_language(callback.from_user.id)

    keyboard = InlineKeyboardBuilder()

    for key, name in SUBJECTS.items():
        keyboard.button(
            text=name,
            callback_data=f"specific_subject_{key}"
        )

    keyboard.button(
        text=TEXTS[language]["back"],
        callback_data="menu_test"
    )

    keyboard.adjust(2, 1)

    await callback.message.edit_text(
        "🎯 <b>Specific Test</b>\n\n"
        "Qaysi fan bo‘yicha maxsus test ishlamoqchisiz?",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("specific_subject_"))
async def specific_subject(
    callback: CallbackQuery,
    state: FSMContext
):
    subject = callback.data.replace(
        "specific_subject_",
        ""
    )

    if subject not in SUBJECTS:
        await callback.answer(
            "Noto‘g‘ri fan.",
            show_alert=True
        )
        return

    language = get_user_language(callback.from_user.id)

    keyboard = InlineKeyboardBuilder()

    keyboard.button(
        text="5️⃣ 5 ta savol",
        callback_data=f"specific_count_{subject}_5"
    )

    keyboard.button(
        text="🔟 10 ta savol",
        callback_data=f"specific_count_{subject}_10"
    )

    keyboard.button(
        text="2️⃣0️⃣ 20 ta savol",
        callback_data=f"specific_count_{subject}_20"
    )

    keyboard.button(
        text=TEXTS[language]["back"],
        callback_data="specific_test"
    )

    keyboard.adjust(1)

    await callback.message.edit_text(
        "🎯 <b>Specific Test</b>\n\n"
        f"📚 Fan: <b>{SUBJECTS[subject]}</b>\n\n"
        "Savollar sonini tanlang:",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("specific_count_"))
async def start_specific_test(
    callback: CallbackQuery,
    state: FSMContext
):
    parts = callback.data.split("_")

    # specific_count_math_10
    if len(parts) != 4:
        await callback.answer(
            "Noto‘g‘ri test.",
            show_alert=True
        )
        return

    subject = parts[2]

    try:
        question_count = int(parts[3])
    except ValueError:
        await callback.answer(
            "Noto‘g‘ri savollar soni.",
            show_alert=True
        )
        return

    if subject not in SUBJECTS:
        await callback.answer(
            "Noto‘g‘ri fan.",
            show_alert=True
        )
        return

    if question_count not in {5, 10, 20}:
        await callback.answer(
            "Noto‘g‘ri savollar soni.",
            show_alert=True
        )
        return

    user = get_user(callback.from_user.id)

    if not user:
        await callback.answer(
            "Avval /start ni bosing.",
            show_alert=True
        )
        return

    grade = user[2]
    language = user[4] if user[4] in LANGUAGES else "uz"

    await callback.message.edit_text(
        "🎯 <b>Specific Test tayyorlanmoqda...</b>\n\n"
        f"📚 Fan: {SUBJECTS[subject]}\n"
        f"🎓 Daraja: {escape_html(grade)}\n"
        f"❓ Savollar: <b>{question_count}</b>\n\n"
        "🤖 AI maxsus test yaratmoqda...",
        parse_mode="HTML"
    )

    try:
        test = await generate_diagnostic_test(
            subject=subject,
            grade=grade,
            language=language,
            question_count=question_count
        )

        questions = test["questions"]

        if not questions:
            raise ValueError("AI bo'sh test qaytardi.")

    except Exception as e:
        print("SPECIFIC TEST ERROR:", e)

        keyboard = InlineKeyboardBuilder()

        keyboard.button(
            text="🔄 Qayta urinish",
            callback_data=f"specific_count_{subject}_{question_count}"
        )

        keyboard.button(
            text="🎯 Testlar",
            callback_data="menu_test"
        )

        keyboard.adjust(1)

        await callback.message.edit_text(
            "❌ <b>Specific testni yaratishda xatolik.</b>\n\n"
            "Qayta urinib ko‘ring.",
            reply_markup=keyboard.as_markup(),
            parse_mode="HTML"
        )

        await callback.answer()
        return

    await state.update_data(
        questions=questions,
        current_question=0,
        answers=[],
        language=language,
        test_type="specific",
        subject_override=subject
    )

    await state.set_state(SpecificTest.taking_test)

    await send_question(
        callback.message,
        questions,
        0,
        language,
        "specific"
    )

    await callback.answer()


# =========================================================
# SEND QUESTION
# =========================================================

async def send_question(
    message,
    questions,
    index,
    language="uz",
    test_type="diagnostic"
):
    question = questions[index]

    keyboard = InlineKeyboardBuilder()

    letters = ["A", "B", "C", "D"]

    options = question.get("options", [])

    for letter, option in zip(letters, options):
        keyboard.button(
            text=str(option)[:60],
            callback_data=f"answer_{letter}"
        )

    keyboard.button(
        text="❌ Testni to‘xtatish",
        callback_data=f"cancel_{test_type}"
    )

    keyboard.adjust(1)

    if language == "en":
        title = (
            "🎯 Specific Test"
            if test_type == "specific"
            else "🧠 Diagnostic Test"
        )
        question_text = "Question"

    elif language == "ru":
        title = (
            "🎯 Специальный тест"
            if test_type == "specific"
            else "🧠 Диагностический тест"
        )
        question_text = "Вопрос"

    else:
        title = (
            "🎯 Specific Test"
            if test_type == "specific"
            else "🧠 Diagnostic Test"
        )
        question_text = "Savol"

    await message.edit_text(
        f"<b>{title}</b>\n\n"
        f"📌 {question_text} "
        f"<b>{index + 1}/{len(questions)}</b>\n\n"
        f"{question.get('question', '')}",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )


# =========================================================
# CANCEL TEST
# =========================================================

@dp.callback_query(
    F.data.in_({"cancel_diagnostic", "cancel_specific"})
)
async def cancel_test(
    callback: CallbackQuery,
    state: FSMContext
):
    await state.clear()

    await callback.answer("❌ Test to‘xtatildi.")

    await show_main_menu(
        callback.message,
        edit=True
    )


# =========================================================
# PROCESS DIAGNOSTIC ANSWER
# =========================================================

@dp.callback_query(
    Diagnostic.taking_test,
    F.data.startswith("answer_")
)
async def process_diagnostic_answer(
    callback: CallbackQuery,
    state: FSMContext
):
    await process_test_answer(
        callback,
        state,
        "diagnostic"
    )


# =========================================================
# PROCESS SPECIFIC ANSWER
# =========================================================

@dp.callback_query(
    SpecificTest.taking_test,
    F.data.startswith("answer_")
)
async def process_specific_answer(
    callback: CallbackQuery,
    state: FSMContext
):
    await process_test_answer(
        callback,
        state,
        "specific"
    )


# =========================================================
# COMMON TEST PROCESSOR
# =========================================================

async def process_test_answer(
    callback: CallbackQuery,
    state: FSMContext,
    test_type: str
):
    data = await state.get_data()

    questions = data.get("questions", [])
    current_question = data.get("current_question", 0)
    answers = data.get("answers", [])
    language = data.get("language", "uz")

    if not questions or current_question >= len(questions):
        await state.clear()
        await callback.answer(
            "Test holati topilmadi.",
            show_alert=True
        )
        return

    selected_answer = callback.data.replace(
        "answer_",
        ""
    )

    question = questions[current_question]

    correct_answer = str(
        question.get("correct_answer", "")
    ).strip().upper()

    selected_answer = selected_answer.strip().upper()

    is_correct = selected_answer == correct_answer

    answers.append({
        "question": question.get("question", ""),
        "selected": selected_answer,
        "correct": correct_answer,
        "is_correct": is_correct,
        "topic": question.get("topic", "General"),
    })

    next_question = current_question + 1

    if next_question < len(questions):
        await state.update_data(
            current_question=next_question,
            answers=answers
        )

        await send_question(
            callback.message,
            questions,
            next_question,
            language,
            test_type
        )

        await callback.answer()
        return

    # -----------------------------------------------------
    # TEST FINISHED
    # -----------------------------------------------------

    total_questions = len(questions)
    correct_count = sum(
        1 for answer in answers
        if answer["is_correct"]
    )

    score = (
        correct_count / total_questions
    ) * 100

    level = test_level(score)

    user = get_user(callback.from_user.id)

    if not user:
        await state.clear()
        await callback.answer(
            "Foydalanuvchi topilmadi.",
            show_alert=True
        )
        return

    grade = user[2]
    subject = (
        data.get("subject_override")
        or user[3]
    )

    xp_earned = calculate_test_xp(
        total_questions,
        correct_count,
        test_type
    )

    xp_result = add_xp(
        callback.from_user.id,
        xp_earned
    )

    streak_result = update_streak(
        callback.from_user.id
    )

    test_id = save_test_result(
        telegram_id=callback.from_user.id,
        test_type=test_type,
        subject=subject,
        grade=grade,
        total_questions=total_questions,
        correct_answers=correct_count,
        level=level,
        xp_earned=xp_earned
    )

    for answer in answers:
        save_question_result(
            test_id=test_id,
            telegram_id=callback.from_user.id,
            question=answer["question"],
            topic=answer["topic"],
            selected_answer=answer["selected"],
            correct_answer=answer["correct"],
            is_correct=answer["is_correct"]
        )

    unlocked = check_and_unlock_achievements(
        callback.from_user.id,
        score,
        streak_result["new_streak"]
    )

    # -----------------------------------------------------
    # AI ANALYSIS ONLY FOR DIAGNOSTIC
    # -----------------------------------------------------

    analysis = None

    if test_type == "diagnostic":
        await callback.message.edit_text(
            "🤖 <b>AI natijangizni tahlil qilmoqda...</b>",
            parse_mode="HTML"
        )

        try:
            analysis = await analyze_diagnostic_results(
                subject=subject,
                grade=grade,
                answers=answers,
                language=language
            )
        except Exception as e:
            print("AI ANALYSIS ERROR:", e)

    # -----------------------------------------------------
    # RESULT
    # -----------------------------------------------------

    if language == "en":
        result_text = (
            "🎉 <b>Test completed!</b>\n\n"
            f"📊 Score: <b>{correct_count}/{total_questions}</b> "
            f"({score:.0f}%)\n"
            f"📈 Result level: <b>{level}</b>\n\n"
            f"⭐ XP earned: <b>+{xp_earned}</b>\n"
            f"🏅 Total XP: <b>{xp_result['new_xp']}</b>\n"
            f"🎮 Level: <b>{xp_result['new_level']}</b>\n"
            f"🔥 Streak: <b>{streak_result['new_streak']} day(s)</b>\n"
        )

    elif language == "ru":
        result_text = (
            "🎉 <b>Тест завершён!</b>\n\n"
            f"📊 Результат: <b>{correct_count}/{total_questions}</b> "
            f"({score:.0f}%)\n"
            f"📈 Уровень результата: <b>{level}</b>\n\n"
            f"⭐ Получено XP: <b>+{xp_earned}</b>\n"
            f"🏅 Всего XP: <b>{xp_result['new_xp']}</b>\n"
            f"🎮 Уровень игрока: <b>{xp_result['new_level']}</b>\n"
            f"🔥 Серия: <b>{streak_result['new_streak']} дн.</b>\n"
        )

    else:
        result_text = (
            "🎉 <b>Test tugadi!</b>\n\n"
            f"📊 Natija: <b>{correct_count}/{total_questions}</b> "
            f"({score:.0f}%)\n"
            f"📈 Test darajasi: <b>{level}</b>\n\n"
            f"⭐ Olingan XP: <b>+{xp_earned}</b>\n"
            f"🏅 Jami XP: <b>{xp_result['new_xp']}</b>\n"
            f"🎮 Level: <b>{xp_result['new_level']}</b>\n"
            f"🔥 Streak: <b>{streak_result['new_streak']} kun</b>\n"
        )

    if xp_result["leveled_up"]:
        result_text += (
            "\n🎊 <b>LEVEL UP!</b>\n"
            f"Siz endi <b>Level {xp_result['new_level']}</b>!\n"
        )

    if unlocked:
        result_text += "\n🏆 <b>Yangi achievement!</b>\n"

        for achievement in unlocked:
            result_text += (
                f"• {achievement['name']} — "
                f"{achievement['description']}\n"
            )

    if analysis:
        result_text += (
            "\n\n🤖 <b>AI tahlili:</b>\n\n"
            f"{analysis}"
        )

    keyboard = InlineKeyboardBuilder()

    keyboard.button(
        text="📊 Progress",
        callback_data="menu_progress"
    )

    keyboard.button(
        text="🎮 XP & Achievements",
        callback_data="menu_gamification"
    )

    keyboard.button(
        text="🧠 Yangi test",
        callback_data="menu_test"
    )

    keyboard.button(
        text="🤖 AI Tutor",
        callback_data="menu_ai_tutor"
    )

    keyboard.button(
        text="🏠 Asosiy menyu",
        callback_data="back_to_menu"
    )

    keyboard.adjust(2, 2, 1)

    await callback.message.edit_text(
        result_text,
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )

    await state.clear()
    await callback.answer()


# =========================================================
# PROGRESS
# =========================================================

async def get_progress_text(telegram_id):
    progress = get_progress(telegram_id)

    total_tests = progress["total_tests"]
    total_questions = progress["total_questions"]
    total_correct = progress["total_correct"]
    average_score = progress["average_score"]
    topics = progress["topics"]

    game = get_gamification(telegram_id)

    if total_tests == 0:
        return (
            "📊 <b>Progress</b>\n\n"
            "Hozircha test natijalari mavjud emas.\n\n"
            f"⭐ XP: <b>{game['xp']}</b>\n"
            f"🎮 Level: <b>{game['level']}</b>\n"
            f"🔥 Streak: <b>{game['streak']} kun</b>"
        )

    text = (
        "📊 <b>Sizning Progressingiz</b>\n\n"
        f"📝 Testlar: <b>{total_tests}</b>\n"
        f"❓ Savollar: <b>{total_questions}</b>\n"
        f"✅ To‘g‘ri javoblar: <b>{total_correct}</b>\n"
        f"📈 O‘rtacha natija: <b>{average_score:.1f}%</b>\n\n"
        f"⭐ XP: <b>{game['xp']}</b>\n"
        f"🎮 Level: <b>{game['level']}</b>\n"
        f"🔥 Streak: <b>{game['streak']} kun</b>\n\n"
    )

    if topics:
        text += "📚 <b>Mavzular:</b>\n\n"

        for topic, total, correct in topics:
            if total == 0:
                continue

            percentage = (correct / total) * 100

            if percentage >= 80:
                icon = "🟢"
            elif percentage >= 60:
                icon = "🟡"
            else:
                icon = "🔴"

            text += (
                f"{icon} <b>{escape_html(topic)}</b>\n"
                f"   {correct}/{total} ({percentage:.0f}%)\n\n"
            )

    return text


@dp.callback_query(F.data == "menu_progress")
async def menu_progress(callback: CallbackQuery):
    text = await get_progress_text(callback.from_user.id)

    language = get_user_language(callback.from_user.id)

    keyboard = InlineKeyboardBuilder()

    keyboard.button(
        text=TEXTS[language]["test"],
        callback_data="menu_test"
    )

    keyboard.button(
        text=TEXTS[language]["gamification"],
        callback_data="menu_gamification"
    )

    keyboard.button(
        text=TEXTS[language]["back"],
        callback_data="back_to_menu"
    )

    keyboard.adjust(1)

    await callback.message.edit_text(
        text,
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )

    await callback.answer()


# =========================================================
# GAMIFICATION
# =========================================================

@dp.callback_query(F.data == "menu_gamification")
async def menu_gamification(callback: CallbackQuery):
    telegram_id = callback.from_user.id
    language = get_user_language(telegram_id)

    game = get_gamification(telegram_id)

    current = game["xp_into_level"]
    required = game["xp_for_level"]

    bar = level_progress_bar(
        current,
        required
    )

    achievements = get_achievements(telegram_id)

    if language == "en":
        text = (
            "🎮 <b>Gamification</b>\n\n"
            f"🏅 Level: <b>{game['level']}</b>\n"
            f"⭐ Total XP: <b>{game['xp']}</b>\n"
            f"📈 Progress: <b>{current}/{required}</b>\n"
            f"{bar}\n\n"
            f"🔥 Streak: <b>{game['streak']} day(s)</b>\n\n"
            "🏆 <b>Achievements</b>\n"
        )
    elif language == "ru":
        text = (
            "🎮 <b>Геймификация</b>\n\n"
            f"🏅 Уровень: <b>{game['level']}</b>\n"
            f"⭐ Всего XP: <b>{game['xp']}</b>\n"
            f"📈 Прогресс: <b>{current}/{required}</b>\n"
            f"{bar}\n\n"
            f"🔥 Серия: <b>{game['streak']} дн.</b>\n\n"
            "🏆 <b>Достижения</b>\n"
        )
    else:
        text = (
            "🎮 <b>Gamification</b>\n\n"
            f"🏅 Level: <b>{game['level']}</b>\n"
            f"⭐ Jami XP: <b>{game['xp']}</b>\n"
            f"📈 Level progress: <b>{current}/{required}</b>\n"
            f"{bar}\n\n"
            f"🔥 Streak: <b>{game['streak']} kun</b>\n\n"
            "🏆 <b>Achievements</b>\n"
        )

    if achievements:
        achievement_keys = {
            "first_test",
            "five_tests",
            "ten_tests",
            "perfect_test",
            "streak_3",
            "streak_7",
        }

        from database import ACHIEVEMENTS

        for key, _created in achievements:
            if key in achievement_keys:
                a = ACHIEVEMENTS[key]
                text += (
                    f"✅ <b>{a['name']}</b>\n"
                    f"   {a['description']}\n\n"
                )
    else:
        text += "🔒 Hozircha achievement yo‘q."

    keyboard = InlineKeyboardBuilder()

    keyboard.button(
        text=TEXTS[language]["test"],
        callback_data="menu_test"
    )

    keyboard.button(
        text=TEXTS[language]["back"],
        callback_data="back_to_menu"
    )

    keyboard.adjust(1)

    await callback.message.edit_text(
        text,
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )

    await callback.answer()


# =========================================================
# HISTORY
# =========================================================

@dp.callback_query(F.data == "menu_history")
async def menu_history(callback: CallbackQuery):
    history = get_test_history(
        callback.from_user.id,
        limit=10
    )

    if not history:
        text = (
            "📜 <b>Test tarixi</b>\n\n"
            "Hozircha test tarixi mavjud emas."
        )
    else:
        text = "📜 <b>Test tarixi</b>\n\n"

        for index, result in enumerate(history, start=1):
            (
                test_id,
                test_type,
                subject,
                grade,
                total_questions,
                correct_answers,
                score_percent,
                level,
                xp_earned,
                created_at
            ) = result

            if test_type == "diagnostic":
                test_name = "🧠 Diagnostic Test"
            elif test_type == "specific":
                test_name = "🎯 Specific Test"
            else:
                test_name = "📝 Mock Test"

            text += (
                f"<b>{index}. {test_name}</b>\n"
                f"📚 {SUBJECTS.get(subject, subject)}\n"
                f"📊 {correct_answers}/{total_questions} "
                f"({score_percent:.0f}%)\n"
                f"⭐ +{xp_earned} XP\n"
                f"📈 {level or '-'}\n"
                f"📅 {created_at[:10]}\n\n"
            )

    language = get_user_language(callback.from_user.id)

    keyboard = InlineKeyboardBuilder()

    keyboard.button(
        text=TEXTS[language]["test"],
        callback_data="menu_test"
    )

    keyboard.button(
        text=TEXTS[language]["progress"],
        callback_data="menu_progress"
    )

    keyboard.button(
        text=TEXTS[language]["gamification"],
        callback_data="menu_gamification"
    )

    keyboard.button(
        text=TEXTS[language]["back"],
        callback_data="back_to_menu"
    )

    keyboard.adjust(2, 1, 1)

    await callback.message.edit_text(
        text,
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )

    await callback.answer()


# =========================================================
# AI TUTOR MENU
# =========================================================

@dp.callback_query(F.data == "menu_ai_tutor")
async def menu_ai_tutor(callback: CallbackQuery):
    language = get_user_language(callback.from_user.id)

    keyboard = InlineKeyboardBuilder()

    if language == "en":
        keyboard.button(
            text="📚 Explain a topic",
            callback_data="tutor_explain"
        )
        keyboard.button(
            text="❓ Ask a question",
            callback_data="tutor_question"
        )
        keyboard.button(
            text="📝 Create an exercise",
            callback_data="tutor_exercise"
        )
        keyboard.button(
            text="⬅️ Back",
            callback_data="back_to_menu"
        )
        text = "🤖 <b>AI Tutor</b>\n\nWhat would you like to do?"

    elif language == "ru":
        keyboard.button(
            text="📚 Объяснить тему",
            callback_data="tutor_explain"
        )
        keyboard.button(
            text="❓ Задать вопрос",
            callback_data="tutor_question"
        )
        keyboard.button(
            text="📝 Создать упражнение",
            callback_data="tutor_exercise"
        )
        keyboard.button(
            text="⬅️ Назад",
            callback_data="back_to_menu"
        )
        text = "🤖 <b>AI Tutor</b>\n\nЧто вы хотите сделать?"

    else:
        keyboard.button(
            text="📚 Mavzuni tushuntirish",
            callback_data="tutor_explain"
        )
        keyboard.button(
            text="❓ Savol berish",
            callback_data="tutor_question"
        )
        keyboard.button(
            text="📝 Mashq yaratish",
            callback_data="tutor_exercise"
        )
        keyboard.button(
            text="⬅️ Orqaga",
            callback_data="back_to_menu"
        )
        text = "🤖 <b>AI Tutor</b>\n\nQanday yordam kerak?"

    keyboard.adjust(1)

    await callback.message.edit_text(
        text,
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )

    await callback.answer()


# =========================================================
# AI TUTOR - EXPLAIN
# =========================================================

@dp.callback_query(F.data == "tutor_explain")
async def tutor_explain_start(
    callback: CallbackQuery,
    state: FSMContext
):
    language = get_user_language(callback.from_user.id)

    if language == "en":
        text = (
            "📚 <b>Explain a topic</b>\n\n"
            "Enter the topic you want me to explain:"
        )
    elif language == "ru":
        text = (
            "📚 <b>Объяснить тему</b>\n\n"
            "Введите тему, которую вы хотите изучить:"
        )
    else:
        text = (
            "📚 <b>Mavzuni tushuntirish</b>\n\n"
            "Qaysi mavzuni tushuntirib beray?\n\n"
            "Masalan: <i>kvadrat tenglama</i>"
        )

    await state.set_state(
        AITutor.waiting_explanation_topic
    )

    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard(language),
        parse_mode="HTML"
    )

    await callback.answer()


@dp.message(AITutor.waiting_explanation_topic)
async def tutor_explain_process(
    message: Message,
    state: FSMContext
):
    if not message.text:
        await message.answer(
            "Iltimos, mavzuni matn ko‘rinishida yuboring."
        )
        return

    topic = message.text.strip()
    user = get_user(message.from_user.id)

    if not user:
        await state.clear()
        await message.answer("Avval /start ni bosing.")
        return

    subject = user[3]
    grade = user[2]
    language = get_user_language(message.from_user.id)

    await message.answer(
        "🤖 <b>AI Tutor mavzuni tushuntirmoqda...</b>",
        parse_mode="HTML"
    )

    try:
        result = await ai_tutor_explain(
            topic=topic,
            subject=subject,
            grade=grade,
            language=language
        )
    except Exception as e:
        print("AI TUTOR EXPLAIN ERROR:", e)
        await message.answer(
            "❌ Mavzuni tushuntirishda xatolik yuz berdi."
        )
        return

    await state.clear()

    await message.answer(
        f"📚 <b>{escape_html(topic)}</b>\n\n"
        f"{result}",
        reply_markup=back_keyboard(language),
        parse_mode="HTML"
    )


# =========================================================
# AI TUTOR - QUESTION
# =========================================================

@dp.callback_query(F.data == "tutor_question")
async def tutor_question_start(
    callback: CallbackQuery,
    state: FSMContext
):
    language = get_user_language(callback.from_user.id)

    if language == "en":
        text = (
            "❓ <b>Ask a question</b>\n\n"
            "Send your question:"
        )
    elif language == "ru":
        text = (
            "❓ <b>Задать вопрос</b>\n\n"
            "Отправьте свой вопрос:"
        )
    else:
        text = (
            "❓ <b>Savol berish</b>\n\n"
            "Savolingizni yozib yuboring.\n\n"
            "Masalan: <i>Nyutonning 2-qonuni nima?</i>"
        )

    await state.set_state(
        AITutor.waiting_question
    )

    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard(language),
        parse_mode="HTML"
    )

    await callback.answer()


@dp.message(AITutor.waiting_question)
async def tutor_question_process(
    message: Message,
    state: FSMContext
):
    if not message.text:
        await message.answer(
            "Iltimos, savolni matn ko‘rinishida yuboring."
        )
        return

    question = message.text.strip()
    user = get_user(message.from_user.id)

    if not user:
        await state.clear()
        await message.answer("Avval /start ni bosing.")
        return

    subject = user[3]
    grade = user[2]
    language = get_user_language(message.from_user.id)

    await message.answer(
        "🤖 <b>AI Tutor javob tayyorlamoqda...</b>",
        parse_mode="HTML"
    )

    try:
        result = await ai_tutor_answer(
            question=question,
            subject=subject,
            grade=grade,
            language=language
        )
    except Exception as e:
        print("AI TUTOR ANSWER ERROR:", e)
        await message.answer(
            "❌ Savolga javob berishda xatolik yuz berdi."
        )
        return

    await state.clear()

    await message.answer(
        f"❓ <b>Savol:</b>\n"
        f"{escape_html(question)}\n\n"
        f"🤖 <b>AI Tutor:</b>\n\n"
        f"{result}",
        reply_markup=back_keyboard(language),
        parse_mode="HTML"
    )


# =========================================================
# AI TUTOR - EXERCISE
# =========================================================

@dp.callback_query(F.data == "tutor_exercise")
async def tutor_exercise_start(
    callback: CallbackQuery,
    state: FSMContext
):
    language = get_user_language(callback.from_user.id)

    if language == "en":
        text = (
            "📝 <b>Create an exercise</b>\n\n"
            "Enter the topic for the exercise:"
        )
    elif language == "ru":
        text = (
            "📝 <b>Создать упражнение</b>\n\n"
            "Введите тему упражнения:"
        )
    else:
        text = (
            "📝 <b>Mashq yaratish</b>\n\n"
            "Qaysi mavzu bo‘yicha mashq yaratish kerak?\n\n"
            "Masalan: <i>Kasrlar</i>"
        )

    await state.set_state(
        AITutor.waiting_exercise_topic
    )

    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard(language),
        parse_mode="HTML"
    )

    await callback.answer()


@dp.message(AITutor.waiting_exercise_topic)
async def tutor_exercise_process(
    message: Message,
    state: FSMContext
):
    if not message.text:
        await message.answer(
            "Iltimos, mavzuni matn ko‘rinishida yuboring."
        )
        return

    topic = message.text.strip()
    user = get_user(message.from_user.id)

    if not user:
        await state.clear()
        await message.answer("Avval /start ni bosing.")
        return

    subject = user[3]
    grade = user[2]
    language = get_user_language(message.from_user.id)

    await message.answer(
        "🤖 <b>AI Tutor mashq yaratmoqda...</b>",
        parse_mode="HTML"
    )

    try:
        result = await ai_tutor_exercise(
            topic=topic,
            subject=subject,
            grade=grade,
            language=language
        )
    except Exception as e:
        print("AI TUTOR EXERCISE ERROR:", e)
        await message.answer(
            "❌ Mashq yaratishda xatolik yuz berdi."
        )
        return

    await state.clear()

    await message.answer(
        f"📝 <b>{escape_html(topic)}</b>\n\n"
        f"{result}",
        reply_markup=back_keyboard(language),
        parse_mode="HTML"
    )


# =========================================================
# BACK
# =========================================================

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(
    callback: CallbackQuery,
    state: FSMContext
):
    await state.clear()

    await show_main_menu(
        callback.message,
        edit=True
    )

    await callback.answer()


# =========================================================
# MOCK TEST
# =========================================================

@dp.callback_query(F.data == "mock_test")
async def mock_test(callback: CallbackQuery):
    language = get_user_language(callback.from_user.id)

    keyboard = InlineKeyboardBuilder()

    keyboard.button(
        text=TEXTS[language]["back"],
        callback_data="menu_test"
    )

    await callback.message.edit_text(
        "📝 <b>Mock Test</b>\n\n"
        "🚧 Mock Test tizimi keyingi bosqichda qo‘shiladi.",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )

    await callback.answer()


# =========================================================
# COMMANDS
# =========================================================

@dp.message(Command("test"))
async def test_command(message: Message):
    user = get_user(message.from_user.id)

    if not user or user[5] != 1:
        await message.answer(
            "Avval /start orqali profilingizni sozlang."
        )
        return

    language = get_user_language(message.from_user.id)

    keyboard = InlineKeyboardBuilder()

    keyboard.button(
        text="🧠 Diagnostic Test",
        callback_data="start_diagnostic"
    )

    keyboard.button(
        text="🎯 Specific Test",
        callback_data="specific_test"
    )

    keyboard.button(
        text="📝 Mock Test",
        callback_data="mock_test"
    )

    keyboard.button(
        text=TEXTS[language]["back"],
        callback_data="back_to_menu"
    )

    keyboard.adjust(1)

    await message.answer(
        "🧠 <b>Testlar</b>\n\n"
        "Test turini tanlang:",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )


@dp.message(Command("xp"))
async def xp_command(message: Message):
    game = get_gamification(message.from_user.id)

    await message.answer(
        "🎮 <b>Gamification</b>\n\n"
        f"🏅 Level: <b>{game['level']}</b>\n"
        f"⭐ XP: <b>{game['xp']}</b>\n"
        f"📈 Level progress: "
        f"<b>{game['xp_into_level']}/{game['xp_for_level']}</b>\n"
        f"🔥 Streak: <b>{game['streak']} kun</b>",
        parse_mode="HTML"
    )


# =========================================================
# MAIN
# =========================================================

async def main():
    init_db()

    print("🤖 AI Study Bot ishga tushdi!")

    await dp.start_polling(bot)


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    asyncio.run(main())
