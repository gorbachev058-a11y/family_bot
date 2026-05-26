// --- Инициализация ---
let currentRole = localStorage.getItem('role') || 'Муж';
let userId = localStorage.getItem('userId');
if (!userId) {
    userId = crypto.randomUUID ? crypto.randomUUID() : 'user_' + Date.now() + '_' + Math.random();
    localStorage.setItem('userId', userId);
}

// Сопоставление устаревших значений ролей
const roleMapping = {
    'муж': 'Муж',
    'жен': 'Жена',
    'пара': 'Пара',
    'ребенок': 'Ребёнок'
};
currentRole = roleMapping[currentRole] || currentRole;
localStorage.setItem('role', currentRole);

// Локальный словарь аватаров (синхронизирован с config.py)
const ROLE_AVATARS = {
    "Муж": {
        name: "Соратник",
        greeting: "Привет. Я Соратник. Сам выгребал из ямы. Давай по делу — что у тебя?"
    },
    "Жена": {
        name: "Доктор Хауз",
        greeting: "Доктор Хауз на связи. Сопли вытру позже, сначала разберем факты. Что случилось?"
    },
    "Пара": {
        name: "Доктор Хауз",
        greeting: "Я Доктор Хауз. Проблемы пар — моя специализация. Кто первый на «операционный стол»?"
    },
    "Ребёнок": {
        name: "Доктор Хауз",
        greeting: "Доктор Хауз на проводе. Что стряслось у твоего мелкого? Рассказывай как есть."
    }
};

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

const moodTexts = ['😢 Ужасно (1)', '😕 Плохо (2)', '😐 Нормально (3)', '🙂 Хорошо (4)', '😊 Отлично (5)'];
let selectedMood = null;

// --- Вспомогательные функции ---
function setActiveRoleButton(role) {
    roleButtons.forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-role') === role);
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
async function changeRole(role) {
    currentRole = role;
    localStorage.setItem('role', role);
    setActiveRoleButton(role);

    // очищаем историю на сервере
    await fetch(`/clear_history?user_id=${userId}`, { method: 'POST' });

    // Показываем приветствие из локального словаря
    const avatar = ROLE_AVATARS[role] || ROLE_AVATARS["Муж"];
    addMessage(avatar.greeting, false);
}

// Обработчик кнопок выбора роли
roleButtons.forEach(btn => {
    btn.addEventListener('click', () => {
        const newRole = btn.getAttribute('data-role');
        if (newRole && newRole !== currentRole) {
            changeRole(newRole);
        }
    });
});

// --- Отправка сообщения ---
async function sendMessageToBot(message) {
    if (!message.trim()) return;

    addMessage(message, true);
    messageInput.value = '';
    statusDiv.textContent = 'Доктор Хауз печатает...';

    try {
        console.log('Отправка на /chat, роль:', currentRole, 'userId:', userId);
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
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
        console.error('Ошибка чата:', error);
        addMessage('⚠️ Извините, произошла ошибка. Попробуйте позже.', false);
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
    };

    recognition.onerror = (event) => {
        console.error('Ошибка распознавания:', event.error);
        statusDiv.textContent = 'Ошибка распознавания речи';
        voiceBtn.disabled = false;
        setTimeout(() => { statusDiv.textContent = ''; }, 2000);
    };

    recognition.onend = () => {
        voiceBtn.disabled = false;
        if (statusDiv.textContent === 'Слушаю...') statusDiv.textContent = '';
    };
} else {
    voiceBtn.style.display = 'none';
    console.warn('Web Speech API не поддерживается');
}

// --- Модалка настроения ---
function openMoodModal() {
    moodModal.style.display = 'block';
    selectedMood = null;
    moodNote.value = '';
    moodRatingSpans.forEach(span => span.classList.remove('selected'));
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

moodRatingSpans.forEach((span, index) => {
    span.addEventListener('click', () => {
        moodRatingSpans.forEach(s => s.classList.remove('selected'));
        span.classList.add('selected');
        selectedMood = parseInt(span.getAttribute('data-mood'));
        if (selectedMoodTextEl) {
            selectedMoodTextEl.textContent = `✓ Выбрано: ${moodTexts[selectedMood - 1]}`;
        }
        statusDiv.textContent = `Выбрано: ${moodTexts[selectedMood - 1]}`;
        setTimeout(() => {
            if (statusDiv.textContent === `Выбрано: ${moodTexts[selectedMood - 1]}`) statusDiv.textContent = '';
        }, 2000);
    });
});

if (saveMoodBtn) {
    saveMoodBtn.addEventListener('click', async () => {
        if (!selectedMood) {
            alert('Пожалуйста, выберите оценку настроения');
            return;
        }
        try {
            const response = await fetch('/mood', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    user_id: userId,
                    mood: selectedMood,
                    note: moodNote.value
                })
            });
            if (response.ok) {
                addSystemMessage(`😊 Настроение сохранено (оценка: ${selectedMood})`);
                closeMoodModal();
            } else {
                addSystemMessage('❌ Ошибка сохранения настроения');
            }
        } catch (error) {
            console.error('Ошибка сохранения настроения:', error);
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
            console.error('Ошибка совета:', error);
            addMessage('Ошибка получения совета', false);
        }
    });
}

// обработчик доната
const donateBtn = document.getElementById('donateBtn');
if (donateBtn) {
    donateBtn.addEventListener('click', () => {
        window.open('https://doctorhauz.ru/donate', '_blank');
    });
}

// --- Очистка истории ---
const clearHistoryBtn = document.getElementById('clearHistoryBtn');
if (clearHistoryBtn) {
    clearHistoryBtn.addEventListener('click', async () => {
        try {
            console.log('Очистка истории для userId:', userId);
            const response = await fetch(`/clear_history?user_id=${userId}`, {method: 'POST'});
            if (response.ok) {
                // Очищаем окно чата полностью
                chatWindow.innerHTML = '';
                // Добавляем приветствие текущего аватара (как при загрузке)
                const avatar = ROLE_AVATARS[currentRole] || ROLE_AVATARS["Муж"];
                addMessage(avatar.greeting, false);
                addSystemMessage('🗑️ История диалога очищена. Начинаем новый разговор.');
            } else {
                addSystemMessage('Ошибка очистки истории');
            }
        } catch (error) {
            console.error('Ошибка очистки истории:', error);
            addSystemMessage('Ошибка очистки истории');
        }
    });
}
// --- Инициализация ---
setActiveRoleButton(currentRole);

// Добавить приветствие при загрузке (если окно чата пусто)
if (chatWindow.children.length === 0) {
    const avatar = ROLE_AVATARS[currentRole] || ROLE_AVATARS["Муж"];
    addMessage(avatar.greeting, false);
}