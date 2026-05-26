import random
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

router = Router()

# ---------------------- СОСТОЯНИЯ ----------------------

class ValuesTestStates(StatesGroup):
    # Для теста Рокича: перебираем по одной ценности
    waiting_for_rockeach_terminal = State()
    waiting_for_rockeach_instrumental = State()

class SchwartzTestStates(StatesGroup):
    waiting_for_schwartz_answer = State()

class StrengthsTestStates(StatesGroup):
    waiting_for_strength_answer = State()

class SelfAnalysisStates(StatesGroup):
    waiting_for_answer = State()

# ---------------------- МАТЕРИАЛЫ ----------------------

# Терминальные ценности (18)
TERMINAL_VALUES = [
    "Активная деятельная жизнь (полнота и эмоциональная насыщенность)",
    "Жизненная мудрость (зрелость суждений и здравый смысл)",
    "Здоровье (физическое и психическое)",
    "Интересная работа",
    "Красота природы и искусства",
    "Любовь (духовная и физическая близость с любимым человеком)",
    "Материально обеспеченная жизнь",
    "Наличие хороших и верных друзей",
    "Общественное признание (уважение окружающих)",
    "Познание (возможность расширения образования и кругозора)",
    "Продуктивная жизнь (максимальное использование своих возможностей)",
    "Развитие (работа над собой, постоянное совершенствование)",
    "Развлечения (приятное времяпрепровождение)",
    "Свобода (самостоятельность, независимость)",
    "Счастливая семейная жизнь",
    "Счастье других (благосостояние других людей)",
    "Творчество",
    "Уверенность в себе"
]

INSTRUMENTAL_VALUES = [
    "Аккуратность",
    "Воспитанность",
    "Высокие запросы",
    "Жизнерадостность",
    "Исполнительность",
    "Независимость",
    "Непримиримость к недостаткам",
    "Образованность",
    "Ответственность",
    "Рационализм",
    "Самоконтроль",
    "Смелость",
    "Твердая воля",
    "Терпимость",
    "Широта взглядов",
    "Честность",
    "Эффективность",
    "Чуткость"
]

# Опросник Шварца: 10 описаний
SCHWARTZ_ITEMS = [
    ("Власть", "Для него/неё важен социальный статус, престиж, доминирование над людьми. Он/она стремится к контролю и влиянию."),
    ("Достижение", "Для него/неё важен личный успех, общественное признание, компетентность. Он/она любит добиваться целей."),
    ("Гедонизм", "Для него/неё важны удовольствия, наслаждение жизнью, хорошее времяпрепровождение."),
    ("Стимуляция", "Для него/неё важна новизна, волнение, насыщенная впечатлениями жизнь. Он/она ищет приключения."),
    ("Самостоятельность", "Для него/неё важна независимость в суждениях и поступках, свобода выбора."),
    ("Универсализм", "Для него/неё важны всеобщее благополучие, социальная справедливость, равенство, защита природы."),
    ("Доброта", "Для него/неё важна забота о близких, их счастье и благополучие. Он/она стремится помогать."),
    ("Традиция", "Для него/неё важны уважение обычаев, смирение, религиозность, следование культурным нормам."),
    ("Конформность", "Для него/неё важно сдерживать действия, которые могут нарушить общественные ожидания или навредить другим."),
    ("Безопасность", "Для него/неё важна стабильность, безопасность общества, семьи, защищённость.")
]

# VIA-IS (сокращённые 24 вопроса, по одному на каждое достоинство)
VIA_QUESTIONS = [
    ("Креативность", "Я часто придумываю новые и оригинальные идеи."),
    ("Любознательность", "Мне интересно узнавать новое, я задаю много вопросов."),
    ("Открытость ума", "Я объективно рассматриваю разные точки зрения, даже если не согласен."),
    ("Любовь к учёбе", "Мне нравится учиться, осваивать новые навыки."),
    ("Честность", "Я всегда говорю правду, даже если это неудобно."),
    ("Смелость", "Я не отступаю перед трудностями и готов(а) идти на риск ради важного."),
    ("Настойчивость", "Я довожу начатое до конца, несмотря на препятствия."),
    ("Жизнерадостность", "Я обычно нахожу повод для радости и энтузиазма."),
    ("Способность любить и быть любимым", "Я ценю близкие отношения и умею проявлять любовь."),
    ("Доброта", "Я часто помогаю другим, делаю что-то хорошее без ожидания награды."),
    ("Социальный интеллект", "Я понимаю чувства и мотивы других людей."),
    ("Лидерство", "Я могу организовать людей и вести за собой."),
    ("Справедливость", "Я отношусь ко всем равно и справедливо."),
    ("Умение работать в команде", "Я хорошо сотрудничаю с другими, нахожу компромиссы."),
    ("Прощение", "Я готов прощать обиды и не держу зла."),
    ("Смирение", "Я не считаю себя лучше других, умею признавать ошибки."),
    ("Осторожность", "Я тщательно обдумываю решения, не рискую без нужды."),
    ("Саморегуляция", "Я контролирую свои эмоции и желания."),
    ("Appreciation of beauty (эстетическое чувство)", "Я замечаю и ценю красоту в природе, искусстве, повседневности."),
    ("Благодарность", "Я часто испытываю благодарность и выражаю её."),
    ("Надежда", "Я верю в лучшее будущее и планирую его."),
    ("Юмор", "Я люблю шутить и смеяться, даже в трудные моменты."),
    ("Духовность", "У меня есть чувство цели, связи с чем-то большим."),
    ("Гибкость", "Я легко адаптируюсь к новым обстоятельствам.")  # заменяет недостающее
]

# Группы VIA (соответствие индексов вопросов)
VIA_GROUPS = {
    "Мудрость и знание": [0,1,2,3],
    "Мужество": [4,5,6,7],
    "Любовь и гуманность": [8,9,10],
    "Справедливость": [11,12,13],
    "Умеренность": [14,15,16,17],
    "Трансценденция": [18,19,20,21,22,23]
}

# Вопросы для /selfanalysis (сокращённый список)
SELF_QUESTIONS = [
    "Какие моменты своей жизни вы вспоминаете с тёплой гордостью?",
    "Что вы любите делать просто так, а не ради результата?",
    "В какие моменты вы чувствуете себя по-настоящему живым?",
    "Какой я? (опишите 10 словами)",
    "Что меня искренне радует?",
    "Какие мои сильные стороны?",
    "Чего я боюсь больше всего?",
    "Если бы у меня было неограниченное количество времени и денег, чем бы я занимался?",
    "Что я хочу оставить после себя?",
    "Какие две-три вещи, которые вы сделали, заставили вас гордиться собой?",
    "Что вы узнали о себе за последний год?",
    "Какие люди вас вдохновляют?",
    "Что вы хотите, чтобы другие люди говорили о вас?",
    "Если бы я мог дать себе совет в прошлом, что бы я сказал?",
    "Как вы обычно справляетесь со страхами?",
    "Опишите свой идеальный день.",
    "Что для вас значит 'быть успешным'?",
    "В чём ваша истина и живёте ли вы подлинно?"
]

# ---------------------- КОМАНДЫ ----------------------

@router.message(Command("values"))
async def start_values(message: Message, state: FSMContext):
    """Запуск теста Рокича (ценности)"""
    await state.update_data(terminal_scores={}, value_index=0)
    await state.set_state(ValuesTestStates.waiting_for_rockeach_terminal)
    await message.answer(
        "Сейчас мы оценим ваши терминальные ценности (цели). "
        "Я буду показывать ценность, а вы оцените её важность для вас по шкале от 1 до 10.\n"
        "Первая ценность:",
        reply_markup=ReplyKeyboardRemove()
    )
    await message.answer(TERMINAL_VALUES[0])

@router.message(ValuesTestStates.waiting_for_rockeach_terminal)
async def process_terminal_value(message: Message, state: FSMContext):
    data = await state.get_data()
    idx = data.get("value_index", 0)
    score_str = message.text.strip()
    if not score_str.isdigit() or not (1 <= int(score_str) <= 10):
        await message.answer("Пожалуйста, введите число от 1 до 10.")
        return
    score = int(score_str)
    scores = data.get("terminal_scores", {})
    scores[TERMINAL_VALUES[idx]] = score
    await state.update_data(terminal_scores=scores)
    idx += 1
    if idx < len(TERMINAL_VALUES):
        await state.update_data(value_index=idx)
        await message.answer(TERMINAL_VALUES[idx])
    else:
        # Переходим к инструментальным ценностям
        await state.update_data(instrumental_scores={}, value_index=0)
        await state.set_state(ValuesTestStates.waiting_for_rockeach_instrumental)
        await message.answer("Отлично! Теперь оцените инструментальные ценности (средства). Первая:")
        await message.answer(INSTRUMENTAL_VALUES[0])

@router.message(ValuesTestStates.waiting_for_rockeach_instrumental)
async def process_instrumental_value(message: Message, state: FSMContext):
    data = await state.get_data()
    idx = data.get("value_index", 0)
    score_str = message.text.strip()
    if not score_str.isdigit() or not (1 <= int(score_str) <= 10):
        await message.answer("Пожалуйста, введите число от 1 до 10.")
        return
    score = int(score_str)
    scores = data.get("instrumental_scores", {})
    scores[INSTRUMENTAL_VALUES[idx]] = score
    await state.update_data(instrumental_scores=scores)
    idx += 1
    if idx < len(INSTRUMENTAL_VALUES):
        await state.update_data(value_index=idx)
        await message.answer(INSTRUMENTAL_VALUES[idx])
    else:
        # Завершаем, выводим результаты
        terminal = data.get("terminal_scores", {})
        instrument = data.get("instrumental_scores", {})
        # Сортируем по убыванию
        top_terminal = sorted(terminal.items(), key=lambda x: x[1], reverse=True)[:5]
        top_instrum = sorted(instrument.items(), key=lambda x: x[1], reverse=True)[:5]
        result_msg = "🌟 *Ваши главные ценности (топ-5):*\n\n"
        result_msg += "🏁 *Терминальные (цели):*\n"
        for val, sc in top_terminal:
            result_msg += f"  • {val} — {sc}/10\n"
        result_msg += "\n🛠 *Инструментальные (средства):*\n"
        for val, sc in top_instrum:
            result_msg += f"  • {val} — {sc}/10\n"
        result_msg += "\n_Это ваши приоритеты, которые определяют жизненный путь._"
        await message.answer(result_msg, reply_markup=ReplyKeyboardRemove())
        # Сохраняем логи
        with open("values_log.txt", "a", encoding="utf-8") as f:
            f.write(f"User {message.from_user.id}: Terminal={terminal}, Instrumental={instrument}\n")
        await state.clear()

# ---------------------- ШВАРЦ ----------------------

class SchwartzStates(StatesGroup):
    waiting_for_answer = State()

@router.message(Command("schwartz"))
async def start_schwartz(message: Message, state: FSMContext):
    await state.update_data(responses=[], idx=0)
    await state.set_state(SchwartzStates.waiting_for_answer)
    item = SCHWARTZ_ITEMS[0]
    await message.answer(
        f"Оцените, насколько это описание похоже на вас (1 – совсем не похож, 6 – очень похож):\n\n"
        f"*{item[0]}*: {item[1]}"
    )

@router.message(SchwartzStates.waiting_for_answer)
async def process_schwartz(message: Message, state: FSMContext):
    data = await state.get_data()
    idx = data.get("idx", 0)
    score_str = message.text.strip()
    if not score_str.isdigit() or not (1 <= int(score_str) <= 6):
        await message.answer("Введите число от 1 до 6.")
        return
    score = int(score_str)
    responses = data.get("responses", [])
    responses.append((SCHWARTZ_ITEMS[idx][0], score))
    idx += 1
    if idx < len(SCHWARTZ_ITEMS):
        await state.update_data(responses=responses, idx=idx)
        item = SCHWARTZ_ITEMS[idx]
        await message.answer(f"*{item[0]}*: {item[1]}")
    else:
        # Результаты
        profile = {name: sc for name, sc in responses}
        # Вычисляем измерения
        openness = profile.get("Самостоятельность",0) + profile.get("Стимуляция",0)
        conservatism = profile.get("Безопасность",0) + profile.get("Конформность",0) + profile.get("Традиция",0)
        enhancement = profile.get("Власть",0) + profile.get("Достижение",0)
        transcendence = profile.get("Универсализм",0) + profile.get("Доброта",0)
        result = (
            "📊 *Ваш профиль по Шварцу:*\n\n"
            f"🔓 Открытость изменениям: {openness}/12\n"
            f"🔒 Консерватизм: {conservatism}/18\n"
            f"⬆️ Самоутверждение: {enhancement}/12\n"
            f"🌍 Забота о других: {transcendence}/12\n\n"
            "Подробнее по типам:\n"
        )
        for name, sc in responses:
            result += f"  • {name}: {sc}/6\n"
        await message.answer(result)
        with open("schwartz_log.txt", "a", encoding="utf-8") as f:
            f.write(f"User {message.from_user.id}: {responses}\n")
        await state.clear()

# ---------------------- VIA-IS (сокращённый) ----------------------

class StrengthsStates(StatesGroup):
    waiting_for_answer = State()

@router.message(Command("strengths"))
async def start_strengths(message: Message, state: FSMContext):
    await state.update_data(answers=[], idx=0)
    await state.set_state(StrengthsStates.waiting_for_answer)
    q = VIA_QUESTIONS[0]
    await message.answer("Оцените утверждение по шкале от 1 (совсем не про меня) до 5 (точно про меня):")
    await message.answer(f"*{q[0]}*: {q[1]}")

@router.message(StrengthsStates.waiting_for_answer)
async def process_strength(message: Message, state: FSMContext):
    data = await state.get_data()
    idx = data.get("idx", 0)
    score_str = message.text.strip()
    if not score_str.isdigit() or not (1 <= int(score_str) <= 5):
        await message.answer("Введите число от 1 до 5.")
        return
    score = int(score_str)
    answers = data.get("answers", [])
    answers.append(score)
    idx += 1
    if idx < len(VIA_QUESTIONS):
        await state.update_data(answers=answers, idx=idx)
        q = VIA_QUESTIONS[idx]
        await message.answer(f"*{q[0]}*: {q[1]}")
    else:
        # Подсчёт групп
        group_scores = {}
        for grp, indices in VIA_GROUPS.items():
            s = sum(answers[i] for i in indices)
            group_scores[grp] = s
        sorted_groups = sorted(group_scores.items(), key=lambda x: x[1], reverse=True)
        result = "🌟 *Ваши сильные стороны (VIA-IS):*\n\n"
        for grp, total in sorted_groups:
            result += f"  • {grp}: {total} баллов\n"
        result += "\nСамые развитые достоинства — ваша опора!"
        await message.answer(result)
        with open("strengths_log.txt", "a", encoding="utf-8") as f:
            f.write(f"User {message.from_user.id}: {answers}\n")
        await state.clear()

# ---------------------- САМОАНАЛИЗ / ВОПРОС ДНЯ ----------------------

@router.message(Command("selfanalysis"))
async def start_selfanalysis(message: Message, state: FSMContext):
    question = random.choice(SELF_QUESTIONS)
    await state.update_data(question=question)
    await state.set_state(SelfAnalysisStates.waiting_for_answer)
    await message.answer(f"🧘 *Вопрос дня:* {question}\n\nНапишите развёрнутый ответ (если хотите)", reply_markup=ReplyKeyboardRemove())

@router.message(SelfAnalysisStates.waiting_for_answer)
async def process_self_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    question = data.get("question")
    answer = message.text
    # Сохраняем ответ в файл
    with open("selfanalysis_log.txt", "a", encoding="utf-8") as f:
        f.write(f"{message.from_user.id} | {question} | {answer}\n")
    await message.answer("Записал. Продолжим? Отправьте /selfanalysis для нового вопроса, или /cancel чтобы выйти.")
    await state.clear()

# ---------------------- ОТМЕНА ----------------------

@router.message(Command("cancel"))
async def cancel_all(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=ReplyKeyboardRemove())