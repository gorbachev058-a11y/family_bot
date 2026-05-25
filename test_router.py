from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Dict, List, Optional
import json

router = APIRouter(prefix="/api/tests", tags=["tests"])

# ---------- Модели ----------
class RokichRequest(BaseModel):
    terminal_scores: Dict[str, int]
    instrumental_scores: Dict[str, int]

class SchwartzRequest(BaseModel):
    answers: Dict[str, int]

class CompatibilityRequest(BaseModel):
    scores: List[int]

class ParentingRequest(BaseModel):
    answers: List[str]

class SelfAcceptanceRequest(BaseModel):
    answers: List[str]

class LadderRequest(BaseModel):
    step: int

class AnxietyRequest(BaseModel):
    answers: List[str]

# ---------- Роуты ----------

@router.post("/rokich")
async def process_rokich(req: RokichRequest):
    with open("values_log.txt", "a", encoding="utf-8") as f:
        f.write(json.dumps({"terminal": req.terminal_scores, "instrumental": req.instrumental_scores}) + "\n")
    terminal_sorted = sorted(req.terminal_scores.items(), key=lambda x: x[1], reverse=True)[:5]
    instrumental_sorted = sorted(req.instrumental_scores.items(), key=lambda x: x[1], reverse=True)[:5]
    return {"terminal": terminal_sorted, "instrumental": instrumental_sorted}

@router.post("/schwartz")
async def process_schwartz(req: SchwartzRequest):
    with open("schwartz_log.txt", "a", encoding="utf-8") as f:
        f.write(json.dumps(req.answers) + "\n")
    openness = req.answers.get("Самостоятельность", 0) + req.answers.get("Стимуляция", 0)
    conservatism = req.answers.get("Безопасность", 0) + req.answers.get("Конформность", 0) + req.answers.get("Традиция", 0)
    enhancement = req.answers.get("Власть", 0) + req.answers.get("Достижение", 0)
    transcendence = req.answers.get("Универсализм", 0) + req.answers.get("Доброта", 0)
    profile = {
        "Открытость изменениям": openness,
        "Консерватизм": conservatism,
        "Самоутверждение": enhancement,
        "Забота о других": transcendence
    }
    with open("schwartz_log.txt", "a", encoding="utf-8") as f:
        f.write(json.dumps(req.answers) + "\n")
    return {"profile": profile, "answers": req.answers}

@router.post("/compatibility")
async def process_compatibility(req: CompatibilityRequest):
    total = sum(req.scores)
    if total >= 8:
        text = "🌟 Отличная совместимость! У вас крепкие отношения."
    elif total >= 5:
        text = "😊 Хорошая совместимость, но есть над чем поработать."
    else:
        text = "🤔 Есть сложности. Возможно, стоит обратиться к психологу."
    return {"result": f"Балл: {total} из 10. {text}"}

@router.post("/parenting")
async def process_parenting(req: ParentingRequest):
    count_a = sum(1 for a in req.answers if a == 'а')
    count_b = sum(1 for a in req.answers if a == 'б')
    count_c = sum(1 for a in req.answers if a == 'в')
    if count_a >= 3:
        style = "авторитарный стиль"
    elif count_b >= 3:
        style = "авторитетный стиль (оптимальный)"
    elif count_c >= 3:
        style = "либеральный стиль"
    else:
        style = "смешанный стиль"
    return {"result": f"Ваш преобладающий стиль: {style}."}

@router.post("/selfacceptance")
async def process_selfacceptance(req: SelfAcceptanceRequest):
    score = 0
    if req.answers[0] == "да": score += 1
    if req.answers[1] == "нет": score += 1
    if req.answers[2] == "нет": score += 1
    if req.answers[3] == "да": score += 1
    if req.answers[4] == "нет": score += 1
    if score >= 4:
        level = "высокий уровень самопринятия"
    elif score >= 2:
        level = "средний уровень самопринятия"
    else:
        level = "низкий уровень самопринятия"
    return {"result": f"Балл: {score} из 5. {level}."}

@router.post("/ladder")
async def process_ladder(req: LadderRequest):
    step = req.step
    if not 1 <= step <= 10:
        return {"result": "Ошибка: введите число от 1 до 10."}
    if step >= 8:
        text = "высокая самооценка"
    elif step >= 4:
        text = "адекватная самооценка"
    else:
        text = "низкая самооценка"
    return {"result": f"Ступенька {step} — {text}."}

@router.post("/anxiety")
async def process_anxiety(req: AnxietyRequest):
    score = sum(1 for a in req.answers if a == "да")
    if score <= 1:
        level = "низкий уровень тревожности"
    elif score <= 3:
        level = "средний уровень тревожности"
    else:
        level = "высокий уровень тревожности"
    return {"result": f"Балл: {score} из 5. {level}."}