// --- Инициализация ---
let currentRole = localStorage.getItem('role') || 'муж';
let userId = localStorage.getItem('userId');
if (!userId) {
    userId = crypto.randomUUID ? crypto.randomUUID() : 'user_' + Date.now() + '_' + Math.random();
    localStorage.setItem('userId', userId);
}

// DOM элементы
const chatWindow = document.getElementById('chatWindow');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const voiceBtn = document.getElementById('voiceBtn');
const statusDiv = document.getElementById('status');
const roleButtons = document.querySelectorAll('.role-buttons button');

// --- Элементы для модалки настроения ---
const moodBtn = document.getElementById('moodBtn');
const moodModal = document.getElementById('moodModal');
const closeModal = document.querySelector('.close');
const moodRatingSpans = document.querySelectorAll('.mood-rating span');
const moodNote = document.getElementById('moodNote');
const saveMoodBtn = document.getElementById('saveMoodBtn');
const selectedMoodTextEl = document.getElementById('selectedMoodText');

// Текстовые описания оценок
const moodTexts = ['😢 Ужасно (1)', '😕 Плохо (2)', '😐 Нормально (3)', '🙂 Хорошо (4)', '😊 Отлично (5)'];

let selectedMood = null;

// --- Вспомогательные функции UI ---
function setActiveRoleButton(role) {
    roleButtons.forEach(btn => {
        if (btn.getAttribute('data-role') === role) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
}

function addMessage(text, isUser) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message');
    messageDiv.classList.add(isUser ? 'user-message' : 'bot-message');
    messageDiv.textContent = text;
    chatWindow.appendChild(messageDiv);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

function addSystemMessage(text) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', 'bot-message');
    messageDiv.style.fontStyle = 'italic';
    messageDiv.textContent = text;
    chatWindow.appendChild(messageDiv);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

// --- Смена роли ---
function changeRole(role) {
    currentRole = role;
    localStorage.setItem('role', role);
    setActiveRoleButton(role);
    addSystemMessage(`Роль изменена на "${role}". Задайте свой вопрос.`);
}

roleButtons.forEach(btn => {
    btn.addEventListener('click', () => {
        const newRole = btn.getAttribute('data-role');
        if (newRole !== currentRole) changeRole(newRole);
    });
});

// --- Отправка сообщения ---
async function sendMessageToBot(message) {
    if (!message.trim()) return;

    addMessage(message, true);
    messageInput.value = '';
    statusDiv.textContent = 'Доктор Хауз печатает...';

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                role: currentRole,
                user_id: userId
            })
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        addMessage(data.response, false);
    } catch (error) {
        console.error('Ошибка:', error);
        addMessage('Извините, произошла ошибка. Попробуйте позже.', false);
    } finally {
        statusDiv.textContent = '';
    }
}

sendBtn.addEventListener('click', () => {
    const msg = messageInput.value.trim();
    if (msg) sendMessageToBot(msg);
});
messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        sendBtn.click();
    }
});

// --- Голосовой ввод ---
if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.lang = 'ru-RU';
    recognition.continuous = false;
    recognition.interimResults = false;

    voiceBtn.addEventListener('click', () => {
        recognition.start();
        statusDiv.textContent = 'Слушаю...';
        voiceBtn.disabled = true;
    });

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        messageInput.value = transcript;
        statusDiv.textContent = '';
        voiceBtn.disabled = false;
        // Раскомментируйте, если хотите автоматически отправлять распознанное
        // sendMessageToBot(transcript);
    };

    recognition.onerror = (event) => {
        console.error('Ошибка голоса', event.error);
        statusDiv.textContent = 'Ошибка распознавания';
        voiceBtn.disabled = false;
        setTimeout(() => { if (statusDiv.textContent === 'Ошибка распознавания') statusDiv.textContent = ''; }, 2000);
    };

    recognition.onend = () => {
        voiceBtn.disabled = false;
        if (statusDiv.textContent === 'Слушаю...') statusDiv.textContent = '';
    };
} else {
    voiceBtn.style.display = 'none';
}

// --- Функции модалки настроения ---
function openMoodModal() {
    moodModal.style.display = 'block';
    selectedMood = null;
    moodNote.value = '';
    // Сброс подсветки
    moodRatingSpans.forEach(span => span.classList.remove('selected'));
    // Сброс текстовой подсказки
    if (selectedMoodTextEl) selectedMoodTextEl.textContent = '(оценка не выбрана)';
}

function closeMoodModal() {
    moodModal.style.display = 'none';
    if (selectedMoodTextEl) selectedMoodTextEl.textContent = '(оценка не выбрана)';
    moodNote.value = '';
    selectedMood = null;
    moodRatingSpans.forEach(span => span.classList.remove('selected'));
}

if (moodBtn) moodBtn.addEventListener('click', openMoodModal);
if (closeModal) closeModal.addEventListener('click', closeMoodModal);
window.addEventListener('click', (e) => {
    if (e.target === moodModal) closeMoodModal();
});

// Обработка клика по смайлам
moodRatingSpans.forEach((span, index) => {
    span.addEventListener('click', () => {
        // Снимаем выделение со всех
        moodRatingSpans.forEach(s => s.classList.remove('selected'));
        span.classList.add('selected');
        selectedMood = parseInt(span.getAttribute('data-mood'));
        // Показываем текстовое описание
        if (selectedMoodTextEl) {
            selectedMoodTextEl.textContent = `✓ Выбрано: ${moodTexts[selectedMood-1]}`;
        }
        // Дополнительно в статусной строке
        statusDiv.textContent = `Выбрано: ${moodTexts[selectedMood-1]}`;
        setTimeout(() => {
            if (statusDiv.textContent === `Выбрано: ${moodTexts[selectedMood-1]}`) statusDiv.textContent = '';
        }, 2000);
    });
});

// Сохранение настроения
if (saveMoodBtn) {
    saveMoodBtn.addEventListener('click', async () => {
        if (!selectedMood) {
            alert('Пожалуйста, выберите оценку настроения');
            return;
        }
        const note = moodNote.value;
        try {
            const response = await fetch('/mood', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: userId,
                    mood: selectedMood,
                    note: note
                })
            });
            if (response.ok) {
                addSystemMessage(`😊 Настроение сохранено (оценка: ${selectedMood})`);
                closeMoodModal();
            } else {
                addSystemMessage('❌ Ошибка сохранения настроения');
            }
        } catch (error) {
            console.error(error);
            addSystemMessage('❌ Ошибка сохранения настроения');
        }
    });
}

// --- Совет дня ---
const adviceBtn = document.getElementById('adviceBtn');
if (adviceBtn) {
    adviceBtn.addEventListener('click', async () => {
        try {
            const response = await fetch('/advice');
            if (response.ok) {
                const data = await response.json();
                addMessage(`💡 Совет дня:\n${data.advice}`, false);
            } else {
                addMessage('Не удалось получить совет дня', false);
            }
        } catch (error) {
            console.error(error);
            addMessage('Ошибка получения совета', false);
        }
    });
}

// --- Очистка истории диалога (сессии) ---
const clearHistoryBtn = document.getElementById('clearHistoryBtn');
if (clearHistoryBtn) {
    clearHistoryBtn.addEventListener('click', async () => {
        try {
            const response = await fetch(`/clear_history?user_id=${userId}`, { method: 'POST' });
            if (response.ok) {
                addSystemMessage('🗑️ История диалога очищена. Начинаем новый разговор.');
            } else {
                addSystemMessage('Ошибка очистки истории');
            }
        } catch (error) {
            console.error(error);
            addSystemMessage('Ошибка очистки истории');
        }
    });
}

// --- Начальная настройка роли ---
setActiveRoleButton(currentRole);