import os
import json
import asyncio
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types


# =========================================================
# ENV
# =========================================================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY topilmadi!")

MODEL_NAME = os.getenv(
    "MODEL_NAME",
    "gemini-3.5-flash-lite"
)
# =========================================================
# GEMINI CLIENT
# =========================================================

client = genai.Client(
    api_key=GEMINI_API_KEY
)


# =========================================================
# MODELS
# =========================================================

# Birinchi model ishlamasa keyingisiga o'tadi.
MODELS = [
    "gemini-3.5-flash-lite"

]


# =========================================================
# LANGUAGE SETTINGS
# =========================================================

LANGUAGES = {
    "uz": {
        "name": "O'zbek tili",
        "instruction": """
Barcha savollar, variantlar, mavzular va tushuntirishlar
O'zbek tilida bo'lishi kerak.
"""
    },

    "en": {
        "name": "English",
        "instruction": """
All questions, options, topics and explanations
must be written in English.
"""
    },

    "ru": {
        "name": "Русский язык",
        "instruction": """
Все вопросы, варианты ответов, темы и объяснения
должны быть написаны на русском языке.
"""
    }
}


# =========================================================
# HELPER: GET LANGUAGE
# =========================================================

def get_language_instruction(language: str) -> str:

    return LANGUAGES.get(
        language,
        LANGUAGES["uz"]
    )["instruction"]


# =========================================================
# HELPER: GEMINI REQUEST
# =========================================================

async def generate_with_fallback(
    prompt: str,
    max_retries: int = 2
):

    last_error = None

    for model in MODELS:

        for attempt in range(max_retries + 1):

            try:

                print(
                    f"🤖 Gemini model: {model} | "
                    f"attempt: {attempt + 1}"
                )

                response = await client.aio.models.generate_content(

                    model=model,

                    contents=prompt,

                    config=types.GenerateContentConfig(

                        temperature=0.7,

                        response_mime_type="application/json"
                    )
                )

                if not response.text:

                    raise RuntimeError(
                        "Gemini bo'sh javob qaytardi."
                    )

                return response.text

            except Exception as e:

                last_error = e

                error_text = str(e)

                print(
                    f"⚠️ Gemini error ({model}): "
                    f"{error_text}"
                )

                # Server band bo'lsa kutamiz
                if "503" in error_text or "UNAVAILABLE" in error_text:

                    if attempt < max_retries:

                        wait_time = 2 ** attempt

                        print(
                            f"⏳ {wait_time} sekund kutamiz..."
                        )

                        await asyncio.sleep(wait_time)

                        continue

                # Rate limit
                if "429" in error_text:

                    if attempt < max_retries:

                        wait_time = 3 * (attempt + 1)

                        print(
                            f"⏳ Rate limit. "
                            f"{wait_time} sekund kutamiz..."
                        )

                        await asyncio.sleep(wait_time)

                        continue

                break

    raise RuntimeError(
        f"Gemini barcha modellarida xatolik: {last_error}"
    )


# =========================================================
# JSON PARSER
# =========================================================

def parse_json(text: str) -> Any:

    text = text.strip()

    # ```json ... ``` bo'lsa olib tashlaymiz
    if text.startswith("```"):

        lines = text.splitlines()

        if lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines)

    try:

        return json.loads(text)

    except json.JSONDecodeError as e:

        print("❌ JSON parse error:")
        print(text)

        raise RuntimeError(
            f"AI noto'g'ri JSON qaytardi: {e}"
        )


# =========================================================
# GENERATE DIAGNOSTIC TEST
# =========================================================

async def generate_diagnostic_test(
    subject: str,
    grade: str,
    question_count: int = 5,
    language: str = "uz"
):

    language_instruction = get_language_instruction(
        language
    )

    prompt = f"""
You are an AI educational test generator.

Create a diagnostic test for a student.

SUBJECT:
{subject}

GRADE:
{grade}

NUMBER OF QUESTIONS:
{question_count}

LANGUAGE:
{language}

{language_instruction}

IMPORTANT:

1. Questions must match the student's grade.
2. Start from easy questions and gradually increase difficulty.
3. Questions must test different topics.
4. Every question must have exactly 4 options.
5. Exactly one option must be correct.
6. Do not create ambiguous questions.
7. The correct answer must be represented by A, B, C or D.
8. Difficulty must be one of:
   easy
   medium
   hard

Return ONLY valid JSON.

Use this exact structure:

{{
    "questions": [
        {{
            "question": "Question text",
            "options": [
                "A) option",
                "B) option",
                "C) option",
                "D) option"
            ],
            "correct_answer": "A",
            "topic": "Topic name",
            "difficulty": "easy"
        }}
    ]
}}

Do not add Markdown.
Do not add explanations outside JSON.
"""

    raw_response = await generate_with_fallback(
        prompt
    )

    result = parse_json(
        raw_response
    )

    if "questions" not in result:

        raise RuntimeError(
            "AI javobida 'questions' topilmadi."
        )

    questions = result["questions"]

    if not isinstance(questions, list):

        raise RuntimeError(
            "'questions' list bo'lishi kerak."
        )

    if len(questions) != question_count:

        print(
            f"⚠️ Kutilgan savollar: {question_count}, "
            f"olingan: {len(questions)}"
        )

    # Basic validation
    for i, question in enumerate(questions):

        required_fields = [
            "question",
            "options",
            "correct_answer",
            "topic",
            "difficulty"
        ]

        for field in required_fields:

            if field not in question:

                raise RuntimeError(
                    f"{i + 1}-savolda '{field}' yo'q."
                )

        if len(question["options"]) != 4:

            raise RuntimeError(
                f"{i + 1}-savolda 4 ta variant bo'lishi kerak."
            )

        if question["correct_answer"] not in [
            "A",
            "B",
            "C",
            "D"
        ]:

            raise RuntimeError(
                f"{i + 1}-savolda correct_answer noto'g'ri."
            )

    return result


# =========================================================
# ANALYZE DIAGNOSTIC RESULTS
# =========================================================

async def analyze_diagnostic_results(
    subject: str,
    grade: str,
    questions: list,
    answers: list,
    language: str = "uz"
):

    language_instruction = get_language_instruction(
        language
    )

    result_data = []

    for question, answer in zip(
        questions,
        answers
    ):

        result_data.append({

            "question": question.get(
                "question"
            ),

            "topic": question.get(
                "topic"
            ),

            "difficulty": question.get(
                "difficulty"
            ),

            "correct_answer": question.get(
                "correct_answer"
            ),

            "selected_answer": answer.get(
                "selected"
            ),

            "is_correct": answer.get(
                "is_correct"
            )
        })

    prompt = f"""
You are an AI educational tutor.

Analyze the diagnostic test results of a student.

SUBJECT:
{subject}

GRADE:
{grade}

LANGUAGE:
{language}

{language_instruction}

STUDENT RESULTS:

{json.dumps(result_data, ensure_ascii=False, indent=2)}

Analyze:

1. Overall knowledge level.
2. Topics the student understands.
3. Topics the student struggles with.
4. Specific mistakes.
5. Recommended topics to study.
6. A short personalized learning recommendation.

Use these levels:

beginner
elementary
intermediate
advanced

Return ONLY valid JSON.

Use this exact structure:

{{
    "level": "intermediate",

    "score": 0,

    "strengths": [
        "topic 1",
        "topic 2"
    ],

    "weak_topics": [
        "topic 1",
        "topic 2"
    ],

    "mistakes": [
        {{
            "topic": "topic",
            "explanation": "short explanation"
        }}
    ],

    "recommendations": [
        "recommendation 1",
        "recommendation 2"
    ],

    "summary": "Personalized summary"
}}

Do not add Markdown.
Do not add explanations outside JSON.
"""

    raw_response = await generate_with_fallback(
        prompt
    )

    result = parse_json(
        raw_response
    )

    return result


# =========================================================
# AI EXPLANATION
# =========================================================

async def explain_question(
    question: str,
    correct_answer: str,
    student_answer: str,
    topic: str,
    language: str = "uz"
):

    language_instruction = get_language_instruction(
        language
    )

    prompt = f"""
You are a friendly AI tutor.

Explain a student's mistake.

QUESTION:
{question}

CORRECT ANSWER:
{correct_answer}

STUDENT ANSWER:
{student_answer}

TOPIC:
{topic}

{language_instruction}

Explain:

1. Why the student's answer is incorrect.
2. What the correct answer is.
3. Step-by-step how to solve it.
4. Give one short tip for remembering the concept.

Keep the explanation suitable for a school student.

Return ONLY valid JSON.

Structure:

{{
    "correct_answer": "{correct_answer}",
    "explanation": "explanation",
    "steps": [
        "step 1",
        "step 2",
        "step 3"
    ],
    "tip": "short tip"
}}
"""

    raw_response = await generate_with_fallback(
        prompt
    )

    return parse_json(
        raw_response
    )


# =========================================================
# PERSONALIZED QUESTION GENERATION
# =========================================================

async def generate_personalized_questions(
    subject: str,
    grade: str,
    weak_topics: list,
    language: str = "uz",
    question_count: int = 5
):

    language_instruction = get_language_instruction(
        language
    )

    weak_topics_text = ", ".join(
        weak_topics
    )

    prompt = f"""
You are an adaptive AI tutor.

Create a personalized practice test.

SUBJECT:
{subject}

GRADE:
{grade}

WEAK TOPICS:
{weak_topics_text}

QUESTION COUNT:
{question_count}

LANGUAGE:
{language}

{language_instruction}

Focus mainly on the weak topics.

Start with easier questions and gradually increase
difficulty.

Every question must have:

- question
- exactly 4 options
- correct_answer
- topic
- difficulty

Return ONLY valid JSON.

Structure:

{{
    "questions": [
        {{
            "question": "Question",
            "options": [
                "A) option",
                "B) option",
                "C) option",
                "D) option"
            ],
            "correct_answer": "A",
            "topic": "topic",
            "difficulty": "easy"
        }}
    ]
}}
"""

    raw_response = await generate_with_fallback(
        prompt
    )

    return parse_json(
        raw_response
    )

async def ai_tutor_explain(
    subject,
    grade,
    topic,
    language="uz"
):
    """
    User bergan mavzuni tushuntiradi.
    """

    language_names = {
        "uz": "Uzbek",
        "en": "English",
        "ru": "Russian"
    }

    language_name = language_names.get(
        language,
        "Uzbek"
    )

    prompt = f"""
You are an AI Tutor inside an educational Telegram bot.

Student information:
Subject: {subject}
Grade/level: {grade}
Requested topic: {topic}
Response language: {language_name}

Explain the topic clearly for this student's level.

Requirements:
- Answer ONLY in {language_name}.
- Use simple language.
- Give a clear explanation.
- Give 1-2 examples.
- If appropriate, include formulas.
- Do not make the explanation unnecessarily complicated.
- End with a short practice question.

Return only the educational answer.
"""

    response = await client.aio.models.generate_content(
        model=MODEL_NAME,
        contents=prompt
    )

    return response.text


async def ai_tutor_answer(
    subject,
    grade,
    question,
    language="uz"
):
    """
    Student savoliga AI Tutor javob beradi.
    """

    language_names = {
        "uz": "Uzbek",
        "en": "English",
        "ru": "Russian"
    }

    language_name = language_names.get(
        language,
        "Uzbek"
    )

    prompt = f"""
You are an AI Tutor.

Student information:
Subject: {subject}
Grade/level: {grade}
Student question: {question}
Response language: {language_name}

Answer the student's question clearly.

Requirements:
- Answer ONLY in {language_name}.
- Explain step by step when necessary.
- Adapt the explanation to the student's level.
- If the question is mathematical or scientific, show the reasoning.
- Do not assume advanced knowledge.
- If the student's question is unclear, explain what information is missing.

Return only the educational answer.
"""

    response = await client.aio.models.generate_content(
        model=MODEL_NAME,
        contents=prompt
    )

    return response.text


async def ai_tutor_exercise(
    subject,
    grade,
    topic,
    language="uz"
):
    """
    Berilgan mavzu bo'yicha mashq yaratadi.
    """

    language_names = {
        "uz": "Uzbek",
        "en": "English",
        "ru": "Russian"
    }

    language_name = language_names.get(
        language,
        "Uzbek"
    )

    prompt = f"""
You are an AI Tutor creating a practice exercise.

Student information:
Subject: {subject}
Grade/level: {grade}
Topic: {topic}
Language: {language_name}

Create ONE suitable practice exercise.

Requirements:
- Write everything in {language_name}.
- Match the student's grade/level.
- Make the exercise understandable.
- Do not immediately reveal the answer.
- After the exercise, write:
  "Answer:" followed by a short answer or solution.

Return only the exercise and answer.
"""

    response = await client.aio.models.generate_content(
        model=MODEL_NAME,
        contents=prompt
    )

    return response.text