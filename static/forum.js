const API_BASE = '';
const userId = localStorage.getItem('userId') || (() => {
    const id = crypto.randomUUID ? crypto.randomUUID() : 'user_' + Date.now();
    localStorage.setItem('userId', id);
    return id;
})();

// Загрузка списка тем
async function loadTopics() {
    const res = await fetch('/forum/topics?limit=20');
    const topics = await res.json();
    const container = document.getElementById('topicsList');
    if (!topics.length) {
        container.innerHTML = '<p>Пока нет тем. Будьте первым!</p>';
        return;
    }
    container.innerHTML = topics.map(topic => `
        <div class="topic-item" data-id="${topic.id}">
            <div class="topic-title">${escapeHtml(topic.title)}</div>
            <div class="topic-meta">${topic.user_id} • ${new Date(topic.created_at).toLocaleString()}</div>
        </div>
    `).join('');
    document.querySelectorAll('.topic-item').forEach(el => {
        el.addEventListener('click', () => showTopic(el.dataset.id));
    });
}

// Показать конкретную тему с комментариями
async function showTopic(topicId) {
    const res = await fetch(`/forum/topic/${topicId}`);
    const data = await res.json();
    const topic = data.topic;
    const comments = data.comments;

    let html = `
        <div class="topic-detail">
            <button id="backToListBtn" class="primary-btn" style="margin-bottom:1rem;">← Назад к списку</button>
            <div class="topic-item" style="border:none; padding-bottom:0;">
                <div class="topic-title">${escapeHtml(topic.title)}</div>
                <div class="topic-meta">${topic.user_id} • ${new Date(topic.created_at).toLocaleString()}</div>
                <div class="topic-content" style="margin-top:0.75rem; white-space:pre-wrap;">${escapeHtml(topic.content)}</div>
            </div>
            <hr>
            <h3>Ответы</h3>
            <div id="commentsList">
                ${comments.map(comment => `
                    <div class="comment" data-id="${comment.id}" style="border-left:3px solid ${comment.is_expert_answer ? '#2c3e66' : '#ccc'}; margin:1rem 0; padding:0.5rem 1rem; background:#f9f9f9;">
                        <div><strong>${comment.user_id}</strong> ${comment.is_expert_answer ? '🧠 Эксперт' : ''} • ${new Date(comment.created_at).toLocaleString()}</div>
                        <div style="margin:0.5rem 0; white-space:pre-wrap;">${escapeHtml(comment.content)}</div>
                        ${comment.is_expert_answer && userId === 'admin_user_id' ? `<button class="add-to-kb-btn" data-id="${comment.id}">📚 Добавить в базу знаний</button>` : ''}
                    </div>
                `).join('') || '<p>Пока нет комментариев. Будьте первым!</p>'}
            </div>
            <div class="new-comment">
                <textarea id="newCommentContent" rows="3" placeholder="Ваш комментарий..." style="width:100%; margin:1rem 0;"></textarea>
                <button id="submitCommentBtn" class="primary-btn">Ответить</button>
            </div>
        </div>
    `;
    const container = document.getElementById('topicsList');
    container.innerHTML = html;

    document.getElementById('backToListBtn').addEventListener('click', () => loadTopics());
    document.getElementById('submitCommentBtn').addEventListener('click', () => addComment(topicId));
    document.querySelectorAll('.add-to-kb-btn').forEach(btn => {
        btn.addEventListener('click', () => addToKnowledgeBase(btn.dataset.id));
    });
}

async function addComment(topicId) {
    const content = document.getElementById('newCommentContent').value.trim();
    if (!content) return alert('Введите текст');
    const res = await fetch('/forum/comment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic_id: topicId, user_id: userId, content })
    });
    if (res.ok) {
        document.getElementById('newCommentContent').value = '';
        showTopic(topicId);
    } else {
        alert('Ошибка при отправке комментария');
    }
}

async function addToKnowledgeBase(commentId) {
    const tags = prompt('Введите теги через запятую (например: отношения, развод, совет)');
    if (!tags) return;
    const tagsArray = tags.split(',').map(t => t.trim().toLowerCase());
    const res = await fetch('/forum/add-to-kb', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ comment_id: parseInt(commentId), user_id: userId, tags: tagsArray })
    });
    if (res.ok) {
        alert('Комментарий добавлен в базу знаний!');
    } else {
        const err = await res.json();
        alert(`Ошибка: ${err.detail}`);
    }
}

function escapeHtml(str) {
    return str.replace(/[&<>]/g, function(m) {
        if (m === '&') return '&amp;';
        if (m === '<') return '&lt;';
        if (m === '>') return '&gt;';
        return m;
    });
}

// Инициализация
document.getElementById('newTopicBtn').addEventListener('click', () => {
    document.getElementById('topicModal').style.display = 'block';
});
document.querySelector('.close').addEventListener('click', () => {
    document.getElementById('topicModal').style.display = 'none';
});
document.getElementById('submitTopicBtn').addEventListener('click', async () => {
    const title = document.getElementById('topicTitle').value.trim();
    const content = document.getElementById('topicContent').value.trim();
    if (!title || !content) return alert('Заполните все поля');
    const res = await fetch('/forum/topic', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, title, content })
    });
    if (res.ok) {
        document.getElementById('topicModal').style.display = 'none';
        document.getElementById('topicTitle').value = '';
        document.getElementById('topicContent').value = '';
        loadTopics();
    } else {
        alert('Ошибка создания темы');
    }
});

loadTopics();