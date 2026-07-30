// --- Инициализация ---
let currentRole = localStorage.getItem('role') || 'Муж';
let userId = localStorage.getItem('userId');
if (!userId) {
    userId = crypto.randomUUID ? crypto.randomUUID() : 'user_' + Date.now() + '_' + Math.random();
    localStorage.setItem('userId', userId);
}

// Приведение ролей к единому формату
const roleMapping = {
    'муж': 'Муж', 'жена': 'Жена', 'пара': 'Пара', 'ребёнок': 'Ребёнок'
};
if (roleMapping[currentRole]) currentRole = roleMapping[currentRole];
localStorage.setItem('role', currentRole);

// Аватары
const ROLE_AVATARS = {
    "Муж": { greeting: "Привет. Я Соратник. Сам выгребал из ямы. Давай по делу — что у тебя?" },
    "Жена": { greeting: "Доктор Хауз на связи. Сопли вытру позже, сначала разберем факты. Что случилось?" },
    "Пара": { greeting: "Я Доктор Хауз. Проблемы пар — моя специализация. Кто первый на «операционный стол»?" },
    "Ребёнок": { greeting: "Доктор Хауз на проводе. Что стряслось у твоего мелкого? Рассказывай как есть." }
};

// DOM элементы
const chatWindow = document.getElementById('chatWindow');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const voiceBtn = document.getElementById('voiceBtn');
const statusDiv = document.getElementById('status');
const roleButtons = document.querySelectorAll('.role-buttons button');

// --- Функции ---
function setActiveRoleButton(role) {
    roleButtons.forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-role') === role);
    });
}

function addMessage(text, isUser) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', isUser ? 'user-message' : 'bot-message');
    messageDiv.textContent = text;
    chatWindow.appendChild(messageDiv);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

async function sendMessageToBot(message) {
    if (!message.trim()) return;
    const token = localStorage.getItem('jwt_token');
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    addMessage(message, true);
    messageInput.value = '';
    statusDiv.textContent = 'Доктор Хауз печатает...';

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({ message, role: currentRole, user_id: userId })
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        addMessage(data.response, false);
    } catch (error) {
        console.error('Ошибка:', error);
        addMessage('⚠️ Извините, произошла ошибка. Попробуйте позже.', false);
    } finally {
        statusDiv.textContent = '';
    }
}

// --- Обработчики ---
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

// Выбор роли
roleButtons.forEach(btn => {
    btn.addEventListener('click', () => {
        const newRole = btn.getAttribute('data-role');
        if (newRole && newRole !== currentRole) {
            currentRole = newRole;
            localStorage.setItem('role', newRole);
            setActiveRoleButton(newRole);
            fetch(`/clear_history?user_id=${userId}`, { method: 'POST' });
            const avatar = ROLE_AVATARS[newRole] || ROLE_AVATARS["Муж"];
            addMessage(avatar.greeting, false);
        }
    });
});
setActiveRoleButton(currentRole);

// Голосовой ввод
if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.lang = 'ru-RU';
    recognition.continuous = false;
    voiceBtn.addEventListener('click', () => {
        recognition.start();
        statusDiv.textContent = 'Слушаю...';
        voiceBtn.disabled = true;
    });
    recognition.onresult = (event) => {
        messageInput.value = event.results[0][0].transcript;
        statusDiv.textContent = '';
        voiceBtn.disabled = false;
    };
    recognition.onerror = () => {
        statusDiv.textContent = 'Ошибка распознавания';
        voiceBtn.disabled = false;
        setTimeout(() => { statusDiv.textContent = ''; }, 2000);
    };
    recognition.onend = () => {
        voiceBtn.disabled = false;
        if (statusDiv.textContent === 'Слушаю...') statusDiv.textContent = '';
    };
} else {
    voiceBtn.style.display = 'none';
}

// --- Кнопки действий ---
// Очистка истории
const clearHistoryBtn = document.getElementById('clearHistoryBtn');
if (clearHistoryBtn) {
    clearHistoryBtn.addEventListener('click', async () => {
        await fetch(`/clear_history?user_id=${userId}`, { method: 'POST' });
        chatWindow.innerHTML = '';
        const avatar = ROLE_AVATARS[currentRole] || ROLE_AVATARS["Муж"];
        addMessage(avatar.greeting, false);
        addMessage('🗑️ История диалога очищена.', false);
    });
}

// Дневник настроения
const moodBtn = document.getElementById('moodBtn');
const moodModal = document.getElementById('moodModal');
const closeModal = document.querySelector('.close');
const saveMoodBtn = document.getElementById('saveMoodBtn');
let selectedMood = null;
if (moodBtn && moodModal) {
    moodBtn.addEventListener('click', () => {
        moodModal.style.display = 'block';
        selectedMood = null;
        document.querySelectorAll('.mood-rating span').forEach(s => s.classList.remove('selected'));
        if (document.getElementById('moodNote')) document.getElementById('moodNote').value = '';
        if (document.getElementById('selectedMoodText')) document.getElementById('selectedMoodText').textContent = '(оценка не выбрана)';
    });
    if (closeModal) closeModal.addEventListener('click', () => moodModal.style.display = 'none');
    window.addEventListener('click', (e) => { if (e.target === moodModal) moodModal.style.display = 'none'; });
    document.querySelectorAll('.mood-rating span').forEach(span => {
        span.addEventListener('click', () => {
            document.querySelectorAll('.mood-rating span').forEach(s => s.classList.remove('selected'));
            span.classList.add('selected');
            selectedMood = parseInt(span.getAttribute('data-mood'));
            if (document.getElementById('selectedMoodText')) {
                document.getElementById('selectedMoodText').textContent = `✓ Выбрано: ${selectedMood}`;
            }
        });
    });
    if (saveMoodBtn) {
        saveMoodBtn.addEventListener('click', async () => {
            if (!selectedMood) return alert('Выберите оценку');
            const note = document.getElementById('moodNote')?.value || '';
            await fetch('/mood', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, mood: selectedMood, note })
            });
            moodModal.style.display = 'none';
            addMessage(`😊 Настроение сохранено (оценка: ${selectedMood})`, false);
        });
    }
}

// Совет дня
const adviceBtn = document.getElementById('adviceBtn');
if (adviceBtn) {
    adviceBtn.addEventListener('click', async () => {
        const res = await fetch('/advice');
        if (res.ok) {
            const data = await res.json();
            addMessage(`💡 Совет дня:\n${data.advice}`, false);
        } else {
            addMessage('Не удалось получить совет', false);
        }
    });
}

// Премиум
const premiumBtn = document.getElementById('premiumBtn');
if (premiumBtn) {
    premiumBtn.addEventListener('click', () => {
        window.open('https://doctorhauz.ru/premium', '_blank');
    });
}

// Донат (единственный обработчик)
const donateBtn = document.getElementById('donateBtn');
if (donateBtn) {
    donateBtn.addEventListener('click', () => {
        window.open('https://doctorhauz.ru/donate', '_blank');
    });
}

// Вход через Telegram
const telegramLoginBtn = document.getElementById('telegramLoginBtn');
if (telegramLoginBtn) {
    telegramLoginBtn.addEventListener('click', () => {
        const botUsername = '8180335343';
        const redirectUri = encodeURIComponent(window.location.origin + '/');
        window.open(`https://oauth.telegram.org/auth?bot_id=${botUsername}&origin=${window.location.origin}&redirect_uri=${redirectUri}&request_access=write`, '_blank', 'width=600,height=700');
    });
}
async function handleTelegramCallback() {
    const params = new URLSearchParams(window.location.search);
    const authData = params.get('auth_data');
    if (authData) {
        try {
            const decoded = JSON.parse(decodeURIComponent(authData));
            const res = await fetch('/auth/telegram', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(decoded)
            });
            const data = await res.json();
            if (data.token) {
                localStorage.setItem('jwt_token', data.token);
                localStorage.setItem('user_id', data.user_id);
                addMessage(`Добро пожаловать, ${decoded.first_name}! Вы вошли через Telegram.`, false);
                window.history.replaceState({}, document.title, '/');
            } else {
                addMessage('Ошибка авторизации Telegram', false);
            }
        } catch (e) {
            console.error(e);
        }
    }
}
window.addEventListener('load', handleTelegramCallback);

// Приветствие при загрузке
if (chatWindow.children.length === 0) {
    const avatar = ROLE_AVATARS[currentRole] || ROLE_AVATARS["Муж"];
    addMessage(avatar.greeting, false);
}