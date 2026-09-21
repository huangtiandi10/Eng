const state = { route: 'dashboard', settings: null };

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请求失败');
  return data;
}

function toast(message) {
  const element = $('#toast');
  element.textContent = message;
  element.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove('show'), 2400);
}

const pages = {
  dashboard: { title: 'Dashboard', kicker: "TODAY'S PLAN", render: () => '<div class="panel"><div class="panel-body"><p class="muted">学习概览正在准备中。</p></div></div>' },
  vocabulary: { title: 'Vocabulary', kicker: 'BUILD YOUR WORD BANK', render: renderVocabulary },
  writing: { title: 'Writing', kicker: 'THINK · WRITE · REVISE', render: () => '<div class="panel"><div class="panel-body"><p class="muted">写作训练正在准备中。</p></div></div>' },
  listening: { title: 'Listening', kicker: 'HEAR EVERY DETAIL', render: () => '<div class="panel"><div class="panel-body"><p class="muted">听力训练正在准备中。</p></div></div>' },
  review: { title: 'Review', kicker: 'TURN WEAKNESS INTO MEMORY', render: () => '<div class="panel"><div class="panel-body"><p class="muted">复习中心正在准备中。</p></div></div>' },
  settings: { title: 'Settings', kicker: 'LOCAL CONFIGURATION', render: renderSettings },
};

function renderVocabulary() {
  return `
    <div class="mode-tabs" role="tablist" aria-label="训练模式">
      <button class="active" data-mode="mixed">Mixed</button>
      <button data-mode="zh-en">中 → EN</button>
      <button data-mode="en-zh">EN → 中</button>
      <button data-mode="phrase">Phrases</button>
    </div>
    <section class="practice-layout">
      <div class="practice-card">
        <div class="question-meta"><span id="question-mode">MIXED</span><span id="question-count">0 completed</span></div>
        <div id="question-area" class="question-area"><p class="muted">正在选择题目…</p></div>
        <form id="answer-form" class="answer-box">
          <label for="answer-input">Your answer</label>
          <div class="answer-row"><input id="answer-input" autocomplete="off" spellcheck="false"><button class="btn primary" type="submit">Check</button></div>
          <p id="answer-feedback" class="feedback" aria-live="polite"></p>
        </form>
        <div class="practice-actions"><button id="give-up" class="btn danger" type="button">不认识 / Give up</button><button id="next-word" class="btn" type="button" hidden>Next →</button></div>
      </div>
      <aside class="session-panel panel">
        <div class="panel-header"><h3>Session</h3></div>
        <div class="session-stat"><strong id="session-correct">0</strong><span>Mastered</span></div>
        <div class="session-stat"><strong id="session-unfamiliar">0</strong><span>Unfamiliar</span></div>
        <p class="session-note">答错后继续尝试。连续错误三次会出现首字母提示。</p>
      </aside>
    </section>`;
}

function renderSettings() {
  const ai = state.settings?.ai || {};
  const study = state.settings?.study || {};
  return `
    <form id="settings-form" class="panel">
      <div class="panel-header"><h2>AI Provider</h2><span class="muted">API Key 仅保存在本机</span></div>
      <div class="panel-body form-grid">
        <div class="field"><label for="provider">服务商</label><select id="provider"><option value="openai">OpenAI</option><option value="deepseek">DeepSeek</option><option value="custom">Custom compatible</option></select></div>
        <div class="field"><label for="model">模型</label><input id="model" value="${ai.model || ''}" placeholder="gpt-4o-mini"></div>
        <div class="field full"><label for="base-url">Base URL</label><input id="base-url" value="${ai.base_url || ''}" placeholder="https://api.openai.com/v1"></div>
        <div class="field full"><label for="api-key">API Key</label><input id="api-key" type="password" placeholder="${ai.has_api_key ? '已保存，留空则保持不变' : 'sk-...'}" autocomplete="off"></div>
      </div>
      <div class="panel-header"><h2>Daily Goal</h2><span class="muted">达到目标后仍可继续训练</span></div>
      <div class="panel-body form-grid">
        <div class="field"><label for="new-words">新词</label><input id="new-words" type="number" min="0" value="${study.daily_new_words ?? 30}"></div>
        <div class="field"><label for="reviews">复习词</label><input id="reviews" type="number" min="0" value="${study.daily_reviews ?? 50}"></div>
        <div class="field"><label for="phrases">词组</label><input id="phrases" type="number" min="0" value="${study.daily_phrases ?? 10}"></div>
        <div class="field"><label for="listening-goal">听写</label><input id="listening-goal" type="number" min="0" value="${study.daily_listening ?? 5}"></div>
        <div class="field"><label for="exam-date">考试日期</label><input id="exam-date" type="date" value="${study.exam_date || ''}"></div>
        <div class="full"><button class="btn primary" type="submit">保存设置</button></div>
      </div>
    </form>`;
}

async function navigate(route) {
  state.route = pages[route] ? route : 'dashboard';
  if (state.route === 'settings') state.settings = await api('/api/settings');
  const page = pages[state.route];
  $('#page-title').textContent = page.title;
  $('#page-kicker').textContent = page.kicker;
  $('#app-content').innerHTML = page.render();
  $$('[data-route]').forEach(button => button.classList.toggle('active', button.dataset.route === state.route));
  $('.sidebar').classList.remove('open');
  history.replaceState(null, '', `#${state.route}`);
  bindPageEvents();
}

function bindPageEvents() {
  if (state.route === 'vocabulary') {
    bindVocabulary();
    return;
  }
  if (state.route !== 'settings') return;
  $('#provider').value = state.settings.ai.provider || 'openai';
  $('#settings-form').addEventListener('submit', async event => {
    event.preventDefault();
    const payload = {
      ai: { provider: $('#provider').value, base_url: $('#base-url').value.trim(), api_key: $('#api-key').value.trim(), model: $('#model').value.trim(), timeout_seconds: 60 },
      study: { daily_new_words: +$('#new-words').value, daily_reviews: +$('#reviews').value, daily_phrases: +$('#phrases').value, daily_listening: +$('#listening-goal').value, exam_date: $('#exam-date').value },
    };
    await api('/api/settings', { method: 'POST', body: JSON.stringify(payload) });
    toast('设置已保存');
    state.settings = await api('/api/settings');
  });
}

function bindVocabulary() {
  const session = { mode: 'mixed', question: null, failures: 0, completed: 0, correct: 0, unfamiliar: 0, resolved: false };
  const labels = { 'zh-en': '中译英', 'en-zh': '英译中', phrase: '词组', mixed: '混合' };

  async function loadQuestion() {
    session.question = await api(`/api/vocabulary/next?mode=${session.mode}`);
    session.failures = 0;
    session.resolved = false;
    const q = session.question;
    $('#question-mode').textContent = labels[q.mode].toUpperCase();
    $('#question-area').innerHTML = `
      ${q.unfamiliar ? '<span class="unfamiliar-badge">REVIEW</span>' : ''}
      <p class="question-prompt">${q.prompt}</p>
      <p class="question-detail">${q.pos} ${q.mode !== 'en-zh' ? `· ${q.letter_count} letters` : q.phonetic ? `· /${q.phonetic}/` : ''}</p>`;
    $('#answer-input').value = '';
    $('#answer-input').placeholder = q.mode === 'en-zh' ? '输入一个你知道的中文意思' : 'Type in English';
    $('#answer-input').disabled = false;
    $('#answer-feedback').className = 'feedback';
    $('#answer-feedback').textContent = '';
    $('#next-word').hidden = true;
    $('#give-up').hidden = false;
    $('#answer-input').focus();
  }

  function resolveQuestion(result, gaveUp = false) {
    session.resolved = true;
    session.completed += 1;
    session.correct += gaveUp ? 0 : 1;
    session.unfamiliar += gaveUp ? 1 : 0;
    $('#question-count').textContent = `${session.completed} completed`;
    $('#session-correct').textContent = session.correct;
    $('#session-unfamiliar').textContent = session.unfamiliar;
    $('#answer-input').disabled = true;
    $('#give-up').hidden = true;
    $('#next-word').hidden = false;
    const feedback = $('#answer-feedback');
    feedback.className = `feedback ${gaveUp ? 'warn' : 'success'}`;
    feedback.innerHTML = `${gaveUp ? '已加入陌生词。' : 'Correct.'} <strong>${result.word}</strong> ${result.pos} ${result.meaning}${result.example ? `<small>${result.example}</small>` : ''}`;
  }

  $$('.mode-tabs button').forEach(button => button.addEventListener('click', async () => {
    session.mode = button.dataset.mode;
    $$('.mode-tabs button').forEach(item => item.classList.toggle('active', item === button));
    await loadQuestion();
  }));
  $('#answer-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (session.resolved) return loadQuestion();
    const answer = $('#answer-input').value.trim();
    if (!answer) return toast('先填写答案');
    session.failures += 1;
    const result = await api('/api/vocabulary/answer', { method: 'POST', body: JSON.stringify({ id: session.question.id, mode: session.question.mode, answer, failures: session.failures }) });
    if (result.correct) return resolveQuestion(result);
    const feedback = $('#answer-feedback');
    feedback.className = 'feedback error';
    if (session.question.mode === 'en-zh') {
      feedback.innerHTML = `未匹配。完整释义：<strong>${result.pos} ${result.answer}</strong>。请再输入一次以加强记忆。`;
    } else {
      const positions = result.hint.wrong_positions.length ? `错误位置：${result.hint.wrong_positions.join(', ')}` : '长度不匹配';
      const pattern = result.hint.pattern.includes('_') && session.failures >= 3 ? ` · ${result.hint.pattern}` : '';
      feedback.textContent = `${positions} · ${result.hint.letter_count} letters${pattern}`;
    }
    $('#answer-input').select();
  });
  $('#give-up').addEventListener('click', async () => {
    const result = await api('/api/vocabulary/give-up', { method: 'POST', body: JSON.stringify({ id: session.question.id, mode: session.question.mode }) });
    resolveQuestion(result, true);
  });
  $('#next-word').addEventListener('click', loadQuestion);
  loadQuestion().catch(error => toast(error.message));
}

document.addEventListener('click', event => {
  const target = event.target.closest('[data-route]');
  if (target) navigate(target.dataset.route).catch(error => toast(error.message));
});
$('#menu-button').addEventListener('click', () => $('.sidebar').classList.toggle('open'));
$('#today-label').textContent = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' }).format(new Date());
navigate(location.hash.slice(1) || 'dashboard').catch(error => toast(error.message));
