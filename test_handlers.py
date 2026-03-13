from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Импортируем все необходимые состояния из states.py
from states import (
    UserRole,
    TestStates,
    LadderTest,
    AnxietyTest,
    CompatibilityTest,
    ParentingStyleTest,
    SelfAcceptanceTest,
)

router = Router()

# Словарь с тестами (включая новые)
tests_info = {
    "ladder": {
        "name": "🧸 Лесенка (самооценка)",
        "description": "Для детей 4–10 лет. Определяет уровень самооценки.",
        "command": "ladder",
    },
    "anxiety": {
        "name": "😟 Тревожность (опросник)",
        "description": "Для детей 8–12 лет. Краткий скрининг тревожности.",
        "command": "anxiety",
    },
    "compatibility": {
        "name": "💞 Совместимость пары",
        "description": "Для пар. Оценивает уровень взаимопонимания и гармонии.",
        "command": "compatibility",
    },
    "parenting": {
        "name": "👪 Стиль воспитания",
        "description": "Определяет ваш подход к воспитанию детей.",
        "command": "parenting",
    },
    "selfacceptance": {
        "name": "🌟 Самопринятие",
        "description": "Оценивает, насколько вы принимаете себя и свои чувства.",
        "command": "selfacceptance",
    },
}


# Функция для создания клавиатуры с тестами
def get_tests_keyboard():
    kb = InlineKeyboardBuilder()
    for test_id, test in tests_info.items():
        kb.button(text=test["name"], callback_data=f"test_{test_id}")
    kb.button(text="❌ Закрыть меню", callback_data="close_tests")
    kb.adjust(1)
    return kb.as_markup()


# Обработка выбора теста
@router.callback_query(TestStates.choosing_test, F.data.startswith("test_"))
async def test_chosen(callback: CallbackQuery, state: FSMContext):
    test_id = callback.data.replace("test_", "")
    if test_id not in tests_info:
        await callback.answer("Тест не найден")
        return

    await callback.answer()

    # Сохраняем, что мы в режиме тестов, но не теряем роль
    await state.update_data(in_test=True, current_test=test_id)

    if test_id == "ladder":
        await start_ladder_test(callback.message, state)
    elif test_id == "anxiety":
        await start_anxiety_test(callback.message, state)
    elif test_id == "compatibility":
        await start_compatibility_test(callback.message, state)
    elif test_id == "parenting":
        await start_parenting_test(callback.message, state)
    elif test_id == "selfacceptance":
        await start_selfacceptance_test(callback.message, state)


# Обработка закрытия меню тестов
@router.callback_query(TestStates.choosing_test, F.data == "close_tests")
async def close_tests(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "Меню тестов закрыто. Вы можете вернуться к вопросам или ввести /tests снова."
    )
    await state.set_state(UserRole.chatting)


# ---------- Существующие тесты (без изменений) ----------
async def start_ladder_test(message: Message, state: FSMContext):
    await message.answer(
        "🧸 **Тест «Лесенка»**\n\n"
        "Представьте лестницу из 10 ступенек. На самой верхней (10) стоят самые хорошие, умные и добрые дети. "
        "На нижней (1) — те, кто часто огорчает родителей, плохо себя ведёт.\n\n"
        "**Вопрос:** На какую ступеньку ваш ребёнок поставил бы себя? (Ответьте числом от 1 до 10)"
    )
    await state.set_state(LadderTest.waiting_answer)


@router.message(LadderTest.waiting_answer)
async def ladder_answer(message: Message, state: FSMContext):
    try:
        step = int(message.text.strip())
        if step < 1 or step > 10:
            raise ValueError
    except:
        await message.answer("Пожалуйста, введите число от 1 до 10.")
        return

    if step >= 8:
        result = "высокая самооценка (возможно, чуть завышенная, но в пределах нормы)"
    elif 4 <= step <= 7:
        result = "адекватная самооценка"
    else:
        result = "низкая самооценка, стоит обратить внимание на поддержку ребёнка"

    await message.answer(
        f"📊 **Результат:** {step} ступенька — {result}.\n\n"
        "Помните, что это лишь приблизительная оценка, не диагноз. Если вас что-то беспокоит, проконсультируйтесь с детским психологом."
    )

    # Возвращаемся в меню тестов
    await message.answer(
        "📋 Выберите следующий тест или закройте меню:",
        reply_markup=get_tests_keyboard(),
    )
    await state.set_state(TestStates.choosing_test)


anxiety_questions = [
    "1. Ребёнок часто выглядит напряжённым, скованным? (да/нет)",
    "2. Легко ли ребёнок плачет, расстраивается? (да/нет)",
    "3. Часто ли ребёнок говорит, что боится чего-то (темноты, чужих людей, ошибок)? (да/нет)",
    "4. Трудно ли ребёнку успокоиться после замечания? (да/нет)",
    "5. Бывает ли, что ребёнок просыпается ночью с плачем? (да/нет)",
]


async def start_anxiety_test(message: Message, state: FSMContext):
    await message.answer(
        "🧩 **Тест на тревожность**\n\nОтветьте 'да' или 'нет' на следующие вопросы."
    )
    await message.answer(anxiety_questions[0])
    await state.set_state(AnxietyTest.q1)


@router.message(AnxietyTest.q1)
async def anxiety_q1(message: Message, state: FSMContext):
    answer = message.text.lower().strip()
    if answer not in ["да", "нет"]:
        await message.answer("Пожалуйста, ответьте 'да' или 'нет'.")
        return
    await state.update_data(q1=answer)
    await message.answer(anxiety_questions[1])
    await state.set_state(AnxietyTest.q2)


@router.message(AnxietyTest.q2)
async def anxiety_q2(message: Message, state: FSMContext):
    answer = message.text.lower().strip()
    if answer not in ["да", "нет"]:
        await message.answer("Пожалуйста, ответьте 'да' или 'нет'.")
        return
    await state.update_data(q2=answer)
    await message.answer(anxiety_questions[2])
    await state.set_state(AnxietyTest.q3)


@router.message(AnxietyTest.q3)
async def anxiety_q3(message: Message, state: FSMContext):
    answer = message.text.lower().strip()
    if answer not in ["да", "нет"]:
        await message.answer("Пожалуйста, ответьте 'да' или 'нет'.")
        return
    await state.update_data(q3=answer)
    await message.answer(anxiety_questions[3])
    await state.set_state(AnxietyTest.q4)


@router.message(AnxietyTest.q4)
async def anxiety_q4(message: Message, state: FSMContext):
    answer = message.text.lower().strip()
    if answer not in ["да", "нет"]:
        await message.answer("Пожалуйста, ответьте 'да' или 'нет'.")
        return
    await state.update_data(q4=answer)
    await message.answer(anxiety_questions[4])
    await state.set_state(AnxietyTest.q5)


@router.message(AnxietyTest.q5)
async def anxiety_q5(message: Message, state: FSMContext):
    answer = message.text.lower().strip()
    if answer not in ["да", "нет"]:
        await message.answer("Пожалуйста, ответьте 'да' или 'нет'.")
        return
    await state.update_data(q5=answer)

    data = await state.get_data()
    score = sum(
        1
        for ans in [
            data.get("q1"),
            data.get("q2"),
            data.get("q3"),
            data.get("q4"),
            data.get("q5"),
        ]
        if ans == "да"
    )

    if score <= 1:
        level = "низкий уровень тревожности"
    elif score <= 3:
        level = "средний уровень тревожности"
    else:
        level = "высокий уровень тревожности"

    await message.answer(
        f"📊 **Результат:** {score} баллов из 5 — {level}.\n\n"
        "Помните: это лишь скрининговый тест, не диагноз. При повышенной тревожности рекомендуется консультация специалиста."
    )

    # Возвращаемся в меню тестов
    await message.answer(
        "📋 Выберите следующий тест или закройте меню:",
        reply_markup=get_tests_keyboard(),
    )
    await state.set_state(TestStates.choosing_test)


# ---------- НОВЫЙ ТЕСТ: Совместимость пары ----------
compatibility_questions = [
    "**Вопрос 1 из 5:**\nКак вы проводите свободное время?\n"
    "а) Вместе, это всегда интересно\n"
    "б) Иногда вместе, иногда порознь\n"
    "в) Чаще порознь, у каждого свои увлечения",
    "**Вопрос 2 из 5:**\nКак вы решаете конфликты?\n"
    "а) Спокойно обсуждаем, ищем компромисс\n"
    "б) Иногда ссоримся, но быстро миримся\n"
    "в) Часто спорим, каждый стоит на своём",
    "**Вопрос 3 из 5:**\nНасколько вы доверяете партнёру?\n"
    "а) Полностью доверяю\n"
    "б) Доверяю, но бывают сомнения\n"
    "в) Есть серьёзные проблемы с доверием",
    "**Вопрос 4 из 5:**\nКак у вас обстоят дела с общими целями?\n"
    "а) Есть общие планы на будущее\n"
    "б) Обсуждаем, но не всегда совпадаем\n"
    "в) У каждого свои цели, не пересекаются",
    "**Вопрос 5 из 5:**\nЧувствуете ли вы эмоциональную поддержку?\n"
    "а) Да, всегда\n"
    "б) Иногда не хватает\n"
    "в) Редко или никогда",
]


async def start_compatibility_test(message: Message, state: FSMContext):
    await message.answer(
        "💞 **Тест на совместимость пары**\n\n"
        "Ответьте на 5 вопросов вместе (или по очереди), выбирая один из вариантов: а, б или в."
    )
    await message.answer(compatibility_questions[0])
    await state.set_state(CompatibilityTest.q1)


async def handle_compatibility_answer(message: Message, state: FSMContext, question_num: int):
    answer = message.text.lower().strip()
    if answer not in ["а", "б", "в", "a", "b", "c"]:  # допускаем и латиницу
        await message.answer("Пожалуйста, ответьте одной буквой: а, б или в.")
        return

    # Преобразуем в единый формат
    if answer in ["a", "а"]:
        score = 2
    elif answer in ["b", "б"]:
        score = 1
    else:
        score = 0

    await state.update_data({f"q{question_num}": score})

    if question_num < 5:
        await message.answer(compatibility_questions[question_num])
        next_state = getattr(CompatibilityTest, f"q{question_num+1}")
        await state.set_state(next_state)
    else:
        # Завершение теста
        data = await state.get_data()
        total = sum(data.get(f"q{i}", 0) for i in range(1, 6))

        if total >= 8:
            result = "🌟 Отличная совместимость! У вас крепкие отношения."
        elif total >= 5:
            result = "😊 Хорошая совместимость, но есть над чем поработать."
        else:
            result = "🤔 Есть некоторые сложности. Возможно, стоит обратиться к психологу."

        await message.answer(
            f"**Результат теста на совместимость**\n\n"
            f"Ваш балл: {total} из 10\n\n{result}"
        )

        # Возврат в меню тестов
        await message.answer(
            "📋 Выберите следующий тест или закройте меню:",
            reply_markup=get_tests_keyboard(),
        )
        await state.set_state(TestStates.choosing_test)


@router.message(CompatibilityTest.q1)
async def compatibility_q1(message: Message, state: FSMContext):
    await handle_compatibility_answer(message, state, 1)


@router.message(CompatibilityTest.q2)
async def compatibility_q2(message: Message, state: FSMContext):
    await handle_compatibility_answer(message, state, 2)


@router.message(CompatibilityTest.q3)
async def compatibility_q3(message: Message, state: FSMContext):
    await handle_compatibility_answer(message, state, 3)


@router.message(CompatibilityTest.q4)
async def compatibility_q4(message: Message, state: FSMContext):
    await handle_compatibility_answer(message, state, 4)


@router.message(CompatibilityTest.q5)
async def compatibility_q5(message: Message, state: FSMContext):
    await handle_compatibility_answer(message, state, 5)


# ---------- НОВЫЙ ТЕСТ: Стиль воспитания ----------
parenting_questions = [
    "**Вопрос 1 из 5:**\nКогда ребёнок не слушается, я обычно...\n"
    "а) Настаиваю на своём, требую подчинения\n"
    "б) Объясняю и стараюсь договориться\n"
    "в) Позволяю ему делать что хочет",
    "**Вопрос 2 из 5:**\nКак часто вы хвалите ребёнка?\n"
    "а) Только за большие достижения\n"
    "б) Часто, даже за мелочи\n"
    "в) Редко, чтобы не избаловать",
    "**Вопрос 3 из 5:**\nЕсли ребёнок пришёл с плохой оценкой...\n"
    "а) Строго наказываю (лишаю развлечений, ругаю)\n"
    "б) Обсуждаю причины и помогаю исправить\n"
    "в) Не обращаю внимания, сам разберётся",
    "**Вопрос 4 из 5:**\nКак вы относитесь к тому, что ребёнок имеет свои секреты?\n"
    "а) Считаю, что у детей не должно быть секретов от родителей\n"
    "б) Уважаю личное пространство, но в разумных пределах\n"
    "в) Мне всё равно, пусть делает что хочет",
    "**Вопрос 5 из 5:**\nЕсли ребёнок спорит со мной...\n"
    "а) Пресекаю, последнее слово должно быть за мной\n"
    "б) Выслушиваю и объясняю свою позицию\n"
    "в) Уступаю, чтобы избежать конфликта",
]


async def start_parenting_test(message: Message, state: FSMContext):
    await message.answer(
        "👪 **Тест на стиль воспитания**\n\n"
        "Ответьте на 5 вопросов, выбирая один из вариантов: а, б или в."
    )
    await message.answer(parenting_questions[0])
    await state.set_state(ParentingStyleTest.q1)


async def handle_parenting_answer(message: Message, state: FSMContext, question_num: int):
    answer = message.text.lower().strip()
    if answer not in ["а", "б", "в", "a", "b", "c"]:
        await message.answer("Пожалуйста, ответьте одной буквой: а, б или в.")
        return

    # Сохраняем букву, а не баллы (для определения типа)
    await state.update_data({f"q{question_num}": answer[0]})

    if question_num < 5:
        await message.answer(parenting_questions[question_num])
        next_state = getattr(ParentingStyleTest, f"q{question_num+1}")
        await state.set_state(next_state)
    else:
        data = await state.get_data()
        answers = [data.get(f"q{i}", "б") for i in range(1, 6)]

        # Подсчёт: считаем количество а, б, в
        count_a = sum(1 for ans in answers if ans in ["а", "a"])
        count_b = sum(1 for ans in answers if ans in ["б", "b"])
        count_c = sum(1 for ans in answers if ans in ["в", "c"])

        if count_a >= 3:
            style = "авторитарный стиль (вы контролируете, требуете послушания)"
        elif count_b >= 3:
            style = "авторитетный стиль (вы сочетаете контроль и поддержку, лучший для развития)"
        elif count_c >= 3:
            style = "либеральный стиль (вы мало контролируете, много свободы)"
        else:
            style = "смешанный стиль (в разных ситуациях ведёте себя по-разному)"

        await message.answer(
            f"**Результат теста на стиль воспитания**\n\n"
            f"Ваш преобладающий стиль: **{style}**\n\n"
            "Рекомендация: для гармоничного развития ребёнка старайтесь сочетать тёплые отношения с разумной дисциплиной."
        )

        # Возврат в меню тестов
        await message.answer(
            "📋 Выберите следующий тест или закройте меню:",
            reply_markup=get_tests_keyboard(),
        )
        await state.set_state(TestStates.choosing_test)


@router.message(ParentingStyleTest.q1)
async def parenting_q1(message: Message, state: FSMContext):
    await handle_parenting_answer(message, state, 1)


@router.message(ParentingStyleTest.q2)
async def parenting_q2(message: Message, state: FSMContext):
    await handle_parenting_answer(message, state, 2)


@router.message(ParentingStyleTest.q3)
async def parenting_q3(message: Message, state: FSMContext):
    await handle_parenting_answer(message, state, 3)


@router.message(ParentingStyleTest.q4)
async def parenting_q4(message: Message, state: FSMContext):
    await handle_parenting_answer(message, state, 4)


@router.message(ParentingStyleTest.q5)
async def parenting_q5(message: Message, state: FSMContext):
    await handle_parenting_answer(message, state, 5)


# ---------- НОВЫЙ ТЕСТ: Самопринятие ----------
selfacceptance_questions = [
    "1. Я принимаю себя таким(ой), какой(ая) я есть, со всеми достоинствами и недостатками. (да/нет)",
    "2. Мне трудно прощать себя за ошибки. (да/нет)",
    "3. Я часто сравниваю себя с другими и чувствую неудовлетворение. (да/нет)",
    "4. Я отношусь к себе с добротой и поддержкой, даже когда что-то не получается. (да/нет)",
    "5. Мне важно, что думают обо мне другие, и это влияет на моё самоощущение. (да/нет)",
]


async def start_selfacceptance_test(message: Message, state: FSMContext):
    await message.answer(
        "🌟 **Тест на самопринятие**\n\n"
        "Ответьте 'да' или 'нет' на следующие утверждения."
    )
    await message.answer(selfacceptance_questions[0])
    await state.set_state(SelfAcceptanceTest.q1)


async def handle_selfacceptance_answer(message: Message, state: FSMContext, question_num: int):
    answer = message.text.lower().strip()
    if answer not in ["да", "нет"]:
        await message.answer("Пожалуйста, ответьте 'да' или 'нет'.")
        return

    await state.update_data({f"q{question_num}": answer})

    if question_num < 5:
        await message.answer(selfacceptance_questions[question_num])
        next_state = getattr(SelfAcceptanceTest, f"q{question_num+1}")
        await state.set_state(next_state)
    else:
        data = await state.get_data()
        # Вопросы 1 и 4 – позитивные (да = 1 балл), вопросы 2,3,5 – негативные (нет = 1 балл)
        score = 0
        if data.get("q1") == "да":
            score += 1
        if data.get("q2") == "нет":
            score += 1
        if data.get("q3") == "нет":
            score += 1
        if data.get("q4") == "да":
            score += 1
        if data.get("q5") == "нет":
            score += 1

        if score >= 4:
            level = "высокий уровень самопринятия (вы хорошо относитесь к себе)"
        elif score >= 2:
            level = "средний уровень самопринятия (иногда вы себя критикуете, но в целом принимаете)"
        else:
            level = "низкий уровень самопринятия (стоит поработать над отношением к себе)"

        await message.answer(
            f"**Результат теста на самопринятие**\n\n"
            f"Ваш балл: {score} из 5 — {level}.\n\n"
            "Помните: самопринятие — важная часть психологического здоровья. "
            "Если вы чувствуете, что это мешает вам жить, обратитесь к психологу."
        )

        # Возврат в меню тестов
        await message.answer(
            "📋 Выберите следующий тест или закройте меню:",
            reply_markup=get_tests_keyboard(),
        )
        await state.set_state(TestStates.choosing_test)


@router.message(SelfAcceptanceTest.q1)
async def selfacceptance_q1(message: Message, state: FSMContext):
    await handle_selfacceptance_answer(message, state, 1)


@router.message(SelfAcceptanceTest.q2)
async def selfacceptance_q2(message: Message, state: FSMContext):
    await handle_selfacceptance_answer(message, state, 2)


@router.message(SelfAcceptanceTest.q3)
async def selfacceptance_q3(message: Message, state: FSMContext):
    await handle_selfacceptance_answer(message, state, 3)


@router.message(SelfAcceptanceTest.q4)
async def selfacceptance_q4(message: Message, state: FSMContext):
    await handle_selfacceptance_answer(message, state, 4)


@router.message(SelfAcceptanceTest.q5)
async def selfacceptance_q5(message: Message, state: FSMContext):
    await handle_selfacceptance_answer(message, state, 5)