from aiogram.fsm.state import State, StatesGroup

class UserRole(StatesGroup):
    choosing_role = State()
    chatting = State()

class TestStates(StatesGroup):
    choosing_test = State()

class LadderTest(StatesGroup):
    waiting_answer = State()

class AnxietyTest(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()
    q5 = State()

# НОВЫЕ КЛАССЫ
class CompatibilityTest(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()
    q5 = State()

class ParentingStyleTest(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()
    q5 = State()

class SelfAcceptanceTest(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()
    q5 = State()