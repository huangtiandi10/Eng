const state = { route: 'dashboard', settings: null };

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]);

async function api(path, options = {}) {
  const request = token => fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(token ? { 'X-Access-Token': token } : {}), ...(options.headers || {}) },
  });
  let token = localStorage.getItem('cet6_access_token') || '';
  let response = await request(token);
  if (response.status === 401 && path !== '/api/login') {
    token = window.prompt('请输入 Mac 服务端的访问令牌（config.yaml 的 server.access_token）：') || '';
    if (!token) throw new Error('未提供访问令牌');
    const login = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ access_token: token }),
    });
    if (!login.ok) throw new Error('访问令牌无效');
    localStorage.setItem('cet6_access_token', token);
    response = await request(token);
  }
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
  dashboard: { title: 'Dashboard', kicker: "TODAY'S PLAN", render: renderDashboard },
  vocabulary: { title: 'Vocabulary', kicker: 'BUILD YOUR WORD BANK', render: renderVocabulary },
  writing: { title: 'Writing', kicker: 'THINK · WRITE · REVISE', render: renderWriting },
  listening: { title: 'Listening', kicker: 'HEAR EVERY DETAIL', render: renderListening },
  review: { title: 'Review', kicker: 'TURN WEAKNESS INTO MEMORY', render: renderReview },
  settings: { title: 'Settings', kicker: 'LOCAL CONFIGURATION', render: renderSettings },
};

function renderDashboard() {
  return '<div id="dashboard-view"><div class="panel"><div class="panel-body"><p class="muted">正在读取本地学习记录…</p></div></div></div>';
}

function renderReview() {
  return '<div id="review-view"><div class="panel"><div class="panel-body"><p class="muted">正在整理复习内容…</p></div></div></div>';
}

function renderVocabulary() {
  return `
    <div class="vocabulary-source-row">
      <label for="vocabulary-source">词汇来源</label>
      <select id="vocabulary-source" aria-label="选择词汇来源">
        <option value="new">新词（未练习）</option>
        <option value="mistakes">错题集</option>
        <option value="mastered">已完成</option>
      </select>
      <span id="vocabulary-source-count" class="muted"></span>
    </div>
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

function renderWriting() {
  return `
    <div class="writing-layout">
      <section class="writing-editor panel">
        <div class="panel-header"><h2>Essay workspace</h2><button id="random-prompt" class="btn" type="button">换一个题目</button></div>
        <div class="panel-body">
          <div class="field"><label for="essay-title">Topic</label><input id="essay-title"></div>
          <div class="field prompt-field"><label for="essay-prompt">Prompt</label><textarea id="essay-prompt" rows="3"></textarea></div>
          <div class="editor-label"><label for="essay-content">Your essay</label><span><strong id="word-count">0</strong> words · 建议 160-200</span></div>
          <textarea id="essay-content" class="essay-textarea" placeholder="Start writing here…" spellcheck="true"></textarea>
          <div class="editor-actions"><span class="muted">文章保存在 Mac 服务端</span><button id="evaluate-essay" class="btn primary" type="button">AI Evaluate</button></div>
        </div>
      </section>
      <aside id="writing-result" class="writing-result panel">
        <div class="empty-result"><span>100</span><p>提交后在这里查看评分与修改建议。</p></div>
      </aside>
    </div>`;
}

function renderListening() {
  return `
    <div class="mode-tabs listening-tabs"><button class="active" data-listening-mode="mixed">Mixed</button><button data-listening-mode="word">Words</button><button data-listening-mode="sentence">Sentences</button></div>
    <section class="listening-stage panel">
      <div class="listening-top"><span id="listening-type">MIXED DICTATION</span><div class="listening-controls"><label>Voice <select id="speech-voice"><option value="">Loading voices…</option></select></label><button id="refresh-voices" class="icon-btn" type="button" title="刷新可用音色" aria-label="刷新可用音色">↻</button><label>Speed <select id="speech-rate"><option value="0.7">0.7×</option><option value="0.85">0.85×</option><option value="1" selected>1×</option></select></label></div></div>
      <div class="audio-focus">
        <button id="play-audio" class="play-button" type="button" aria-label="播放听力">▶</button>
        <p id="listen-instruction">点击播放，然后写下你听到的内容</p>
        <span id="listen-meta"></span>
      </div>
      <form id="listening-form" class="listening-form">
        <label for="listening-answer">What did you hear?</label>
        <textarea id="listening-answer" rows="3" autocomplete="off" spellcheck="false"></textarea>
        <div class="listening-actions"><button id="replay-audio" class="btn" type="button">↻ Replay</button><button class="btn primary" type="submit">Check transcript</button></div>
      </form>
      <div id="listening-feedback" class="listening-feedback" hidden></div>
      <button id="next-listening" class="btn primary" type="button" hidden>Next dictation</button>
    </section>`;
}

function renderSettings() {
  const ai = state.settings?.ai || {};
  const study = state.settings?.study || {};
  return `
    <form id="settings-form" class="panel">
      <div class="panel-header"><h2>AI Provider</h2><span class="muted">API Key 仅保存在 Mac 服务端</span></div>
      <div class="panel-body form-grid">
        <div class="field"><label for="provider">服务商</label><select id="provider"><option value="openai">OpenAI</option><option value="deepseek">DeepSeek</option><option value="custom">Custom compatible</option></select></div>
        <div class="field"><label for="model">模型</label><input id="model" value="${escapeHtml(ai.model || '')}" placeholder="gpt-4o-mini"></div>
        <div class="field full"><label for="base-url">Base URL</label><input id="base-url" value="${escapeHtml(ai.base_url || '')}" placeholder="https://api.openai.com/v1"></div>
        <div class="field full"><label for="api-key">API Key</label><input id="api-key" type="password" placeholder="${ai.has_api_key ? '已保存，留空则保持不变' : 'sk-...'}" autocomplete="off"></div>
      </div>
      <div class="panel-header"><h2>Daily Goal</h2><span class="muted">达到目标后仍可继续训练</span></div>
      <div class="panel-body form-grid">
        <div class="field"><label for="new-words">新词</label><input id="new-words" type="number" min="0" value="${study.daily_new_words ?? 30}"></div>
        <div class="field"><label for="reviews">复习词</label><input id="reviews" type="number" min="0" value="${study.daily_reviews ?? 50}"></div>
        <div class="field"><label for="phrases">词组</label><input id="phrases" type="number" min="0" value="${study.daily_phrases ?? 10}"></div>
        <div class="field"><label for="listening-goal">听写</label><input id="listening-goal" type="number" min="0" value="${study.daily_listening ?? 5}"></div>
        <div class="field"><label for="exam-date">考试日期</label><input id="exam-date" type="date" value="${escapeHtml(study.exam_date || '')}"></div>
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
  if (state.route === 'dashboard') {
    loadDashboard();
    return;
  }
  if (state.route === 'vocabulary') {
    bindVocabulary();
    return;
  }
  if (state.route === 'writing') {
    bindWriting();
    return;
  }
  if (state.route === 'listening') {
    bindListening();
    return;
  }
  if (state.route === 'review') {
    loadReview();
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

async function loadDashboard() {
  const data = await api('/api/dashboard');
  const goals = data.goals;
  const goalCard = (label, goal, route) => {
    const percent = goal.target ? Math.min(100, Math.round(goal.done * 100 / goal.target)) : 100;
    return `<button class="goal-card" data-route="${route}"><div><span>${label}</span><strong>${goal.done}<small> / ${goal.target}</small></strong></div><div class="progress"><i style="width:${percent}%"></i></div><em>${percent}%</em></button>`;
  };
  $('#dashboard-view').innerHTML = `
    <section class="dashboard-intro"><div><h2>稳步走向 500</h2><p>完成目标不是终点，今天随时可以继续训练。</p></div>${data.days_to_exam !== null ? `<div class="exam-count"><strong>${data.days_to_exam}</strong><span>days to exam</span></div>` : '<button class="btn" data-route="settings">设置考试日期</button>'}</section>
    <div class="metric-grid">
      <div class="metric"><span>Vocabulary mastery</span><strong>${data.mastered}<small> / ${data.total_words}</small></strong><p>${data.unfamiliar} unfamiliar words</p></div>
      <div class="metric"><span>Writing score</span><strong>${data.latest_essay ? data.latest_essay.score : '—'}<small> / 100</small></strong><p>${data.latest_essay ? escapeHtml(data.latest_essay.title) : 'No essay yet'}</p></div>
      <div class="metric"><span>Listening accuracy</span><strong>${data.listening_accuracy}<small>%</small></strong><p>All dictation attempts</p></div>
      <div class="metric"><span>Study streak</span><strong>${data.streak}<small> days</small></strong><p>Stored on Mac server</p></div>
    </div>
    <section class="panel today-panel"><div class="panel-header"><h2>Today</h2><span class="muted">Daily targets</span></div><div class="goal-grid">${goalCard('Vocabulary', goals.vocabulary, 'vocabulary')}${goalCard('Phrases', goals.phrases, 'vocabulary')}${goalCard('Listening', goals.listening, 'listening')}<button class="goal-card writing-goal" data-route="writing"><div><span>Writing</span><strong>Practice</strong></div><p>Write, score, revise</p><em>→</em></button></div></section>`;
}

async function loadReview() {
  const data = await api('/api/review');
  $('#review-view').innerHTML = `
    <section class="review-head"><div><p>DUE NOW</p><h2>${data.due} items waiting</h2><span>陌生词会混入普通训练，不需要一次清空。</span></div><button class="btn primary" data-route="vocabulary">Start review</button></section>
    <div class="review-grid">
      <section class="panel"><div class="panel-header"><h2>Unfamiliar words</h2><button id="export-words" class="btn" type="button">Export .txt</button></div><div class="word-table">${data.unfamiliar.length ? data.unfamiliar.map(item => `<div><strong>${escapeHtml(item.word)}</strong><span>${escapeHtml(item.pos)}</span><p>${escapeHtml(item.meaning)}</p><em>${Math.round(item.mastery)}%</em></div>`).join('') : '<p class="empty-copy">还没有陌生词。训练时点击“不认识”后会出现在这里。</p>'}</div></section>
      <section class="panel"><div class="panel-header"><h2>Writing reminders</h2></div><div class="note-list">${data.writing_notes.length ? data.writing_notes.map(item => `<p>${escapeHtml(item)}</p>`).join('') : '<p class="empty-copy">完成一篇作文后，这里会积累修改重点。</p>'}</div></section>
    </div>`;
  const exportButton = $('#export-words');
  if (exportButton) exportButton.addEventListener('click', () => {
    const text = data.unfamiliar.map(item => `${item.word}\t${item.pos}\t${item.meaning}`).join('\n');
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
    link.download = `cet6-unfamiliar-${new Date().toISOString().slice(0, 10)}.txt`;
    link.click();
    URL.revokeObjectURL(link.href);
  });
}

function bindListening() {
  const session = { mode: 'mixed', question: null };
  const voiceSelect = $('#speech-voice');
  const voiceStorageKey = 'cet6_listening_voice';
  let voices = [];
  function voiceKey(voice) { return `${voice.name}||${voice.lang}`; }
  function refreshVoices() {
    if (!('speechSynthesis' in window)) return;
    const available = speechSynthesis.getVoices();
    voices = available.filter(voice => /^en(?:-|$)/i.test(voice.lang));
    voiceSelect.innerHTML = '';
    if (!voices.length) {
      voiceSelect.innerHTML = '<option value="">系统未返回英语音色</option>';
      return;
    }
    const saved = localStorage.getItem(voiceStorageKey);
    voices.forEach(voice => {
      const option = document.createElement('option');
      option.value = voiceKey(voice);
      option.textContent = `${voice.name} (${voice.lang})${voice.default ? ' · default' : ''}`;
      voiceSelect.append(option);
    });
    const preferred = voices.find(voice => voiceKey(voice) === saved) || voices.find(voice => voice.default) || voices[0];
    voiceSelect.value = voiceKey(preferred);
  }
  function selectedVoice() {
    return voices.find(voice => voiceKey(voice) === voiceSelect.value) || null;
  }
  async function loadQuestion() {
    speechSynthesis.cancel();
    session.question = await api(`/api/listening/next?mode=${session.mode}`);
    $('#listening-type').textContent = session.question.mode === 'word' ? 'WORD DICTATION' : 'SENTENCE DICTATION';
    $('#listen-meta').textContent = session.question.mode === 'word' ? '1 word' : `${session.question.word_count} words`;
    $('#listening-answer').value = '';
    $('#listening-answer').disabled = false;
    $('#listening-feedback').hidden = true;
    $('#next-listening').hidden = true;
  }
  function speak() {
    if (!session.question || !('speechSynthesis' in window)) return toast('当前浏览器不支持语音播放');
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(session.question.speech);
    const voice = selectedVoice();
    if (voice) {
      utterance.voice = voice;
      utterance.lang = voice.lang;
    } else {
      utterance.lang = 'en-US';
    }
    utterance.rate = +$('#speech-rate').value;
    speechSynthesis.speak(utterance);
    $('#play-audio').classList.add('playing');
    utterance.onend = () => $('#play-audio').classList.remove('playing');
  }
  $$('[data-listening-mode]').forEach(button => button.addEventListener('click', async () => {
    session.mode = button.dataset.listeningMode;
    $$('[data-listening-mode]').forEach(item => item.classList.toggle('active', item === button));
    await loadQuestion();
  }));
  $('#play-audio').addEventListener('click', speak);
  $('#replay-audio').addEventListener('click', speak);
  voiceSelect.addEventListener('change', () => {
    localStorage.setItem(voiceStorageKey, voiceSelect.value);
    speak();
  });
  $('#refresh-voices').addEventListener('click', refreshVoices);
  $('#listening-form').addEventListener('submit', async event => {
    event.preventDefault();
    const result = await api('/api/listening/answer', { method: 'POST', body: JSON.stringify({ id: session.question.id, mode: session.question.mode, answer: $('#listening-answer').value }) });
    const diff = result.diff.map(item => `<span class="${item.correct ? 'heard' : 'missed'}">${escapeHtml(item.word)}</span>`).join(' ');
    const feedback = $('#listening-feedback');
    feedback.hidden = false;
    feedback.innerHTML = `<strong>${result.correct ? 'Perfect transcript.' : 'Compare word by word'}</strong><p class="word-diff">${diff}</p><p>${escapeHtml(result.pos)} ${escapeHtml(result.meaning)}${result.phonetic ? ` · /${escapeHtml(result.phonetic)}/` : ''}</p>`;
    $('#listening-answer').disabled = true;
    $('#next-listening').hidden = false;
    $('#next-listening').focus();
  });
  $('#next-listening').addEventListener('click', loadQuestion);
  refreshVoices();
  if ('speechSynthesis' in window) speechSynthesis.onvoiceschanged = refreshVoices;
  loadQuestion().catch(error => toast(error.message));
}

async function bindWriting() {
  const { prompts } = await api('/api/writing/prompts');
  let index = Math.floor(Math.random() * prompts.length);
  function setPrompt() {
    const item = prompts[index];
    $('#essay-title').value = item.title;
    $('#essay-prompt').value = item.prompt;
  }
  function updateCount() {
    const words = $('#essay-content').value.match(/[A-Za-z]+(?:'[A-Za-z]+)?/g) || [];
    $('#word-count').textContent = words.length;
  }
  setPrompt();
  $('#essay-content').addEventListener('input', updateCount);
  $('#random-prompt').addEventListener('click', () => {
    index = (index + 1 + Math.floor(Math.random() * (prompts.length - 1))) % prompts.length;
    setPrompt();
  });
  $('#evaluate-essay').addEventListener('click', async () => {
    const button = $('#evaluate-essay');
    button.disabled = true;
    button.textContent = 'Evaluating…';
    try {
      const result = await api('/api/writing/evaluate', { method: 'POST', body: JSON.stringify({ title: $('#essay-title').value, prompt: $('#essay-prompt').value, content: $('#essay-content').value }) });
      renderWritingResult(result);
      if (result.warning) toast(result.warning);
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
      button.textContent = 'AI Evaluate';
    }
  });
}

function renderWritingResult(result) {
  const dimensions = result.dimensions || {};
  const dimensionNames = { content: 'Content', organization: 'Structure', language: 'Language', task_completion: 'Task' };
  $('#writing-result').innerHTML = `
    <div class="score-block"><div class="score-ring"><strong>${result.score}</strong><span>/ 100</span></div><div><span class="source-badge">${result.source === 'ai' ? 'AI REVIEW' : 'LOCAL REVIEW'}</span><p>${result.word_count} words</p></div></div>
    <div class="result-section"><h3>Overall</h3><p>${escapeHtml(result.summary)}</p></div>
    <div class="dimension-list">${Object.entries(dimensions).map(([key, value]) => `<div><span>${dimensionNames[key] || key}</span><meter min="0" max="25" value="${value}"></meter><strong>${value}/25</strong></div>`).join('')}</div>
    <div class="result-section"><h3>Issues</h3><ul>${(result.issues || []).map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul></div>
    <div class="result-section"><h3>Next revision</h3><ul>${(result.suggestions || []).map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul></div>
    ${result.revised_essay ? `<details class="revision"><summary>Revised version</summary><p>${escapeHtml(result.revised_essay).replace(/\n/g, '<br>')}</p></details>` : ''}`;
}

function bindVocabulary() {
  const session = { source: 'new', mode: 'mixed', question: null, failures: 0, completed: 0, correct: 0, unfamiliar: 0, resolved: false };
  const labels = { 'zh-en': '中译英', 'en-zh': '英译中', phrase: '词组', mixed: '混合' };
  const sourceSelect = $('#vocabulary-source');
  const sourceCount = $('#vocabulary-source-count');

  async function loadSources() {
    const data = await api('/api/vocabulary/sources');
    sourceSelect.innerHTML = data.sources.map(item => `<option value="${item.id}">${escapeHtml(item.label)}（${item.count}）</option>`).join('');
    sourceSelect.value = session.source;
    const selected = data.sources.find(item => item.id === session.source);
    sourceCount.textContent = selected ? `${selected.count} 个词` : '';
  }

  async function loadQuestion() {
    session.question = await api(`/api/vocabulary/next?mode=${session.mode}&source=${session.source}`);
    session.failures = 0;
    session.resolved = false;
    const q = session.question;
    $('#question-mode').textContent = labels[q.mode].toUpperCase();
    $('#question-area').innerHTML = `
      ${q.unfamiliar ? '<span class="unfamiliar-badge">REVIEW</span>' : ''}
      <p class="question-prompt">${escapeHtml(q.prompt)}</p>
      <p class="question-detail">${escapeHtml(q.pos)} ${q.mode !== 'en-zh' ? `· ${q.letter_count} letters` : q.phonetic ? `· /${escapeHtml(q.phonetic)}/` : ''}</p>`;
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
    $('#next-word').focus();
    const feedback = $('#answer-feedback');
    feedback.className = `feedback ${gaveUp ? 'warn' : 'success'}`;
    feedback.innerHTML = `${gaveUp ? '已加入陌生词。' : 'Correct.'} <strong>${escapeHtml(result.word)}</strong> ${escapeHtml(result.pos)} ${escapeHtml(result.meaning)}${result.example ? `<small>${escapeHtml(result.example)}</small>` : ''}`;
  }

  $$('.mode-tabs button').forEach(button => button.addEventListener('click', async () => {
    session.mode = button.dataset.mode;
    $$('.mode-tabs button').forEach(item => item.classList.toggle('active', item === button));
    await loadQuestion();
  }));
  sourceSelect.addEventListener('change', async () => {
    session.source = sourceSelect.value;
    session.completed = 0;
    session.correct = 0;
    session.unfamiliar = 0;
    $('#question-count').textContent = '0 completed';
    $('#session-correct').textContent = '0';
    $('#session-unfamiliar').textContent = '0';
    const selected = [...sourceSelect.options].find(option => option.value === session.source);
    sourceCount.textContent = selected ? selected.textContent.match(/（(\d+)）/)?.[1] + ' 个词' : '';
    await loadQuestion();
  });
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
      feedback.innerHTML = `未匹配。完整释义：<strong>${escapeHtml(result.pos)} ${escapeHtml(result.answer)}</strong>。请再输入一次以加强记忆。`;
    } else {
      const positions = result.hint.wrong_positions.length ? `错误位置：${result.hint.wrong_positions.join(', ')}` : '长度不匹配';
      const pattern = session.failures >= 3 ? ` · ${result.hint.pattern}` : '';
      feedback.textContent = `${positions} · ${result.hint.letter_count} letters${pattern}`;
    }
    $('#answer-input').select();
  });
  $('#give-up').addEventListener('click', async () => {
    const result = await api('/api/vocabulary/give-up', { method: 'POST', body: JSON.stringify({ id: session.question.id, mode: session.question.mode }) });
    resolveQuestion(result, true);
  });
  $('#next-word').addEventListener('click', loadQuestion);
  loadSources().then(loadQuestion).catch(error => toast(error.message));
}

document.addEventListener('click', event => {
  const target = event.target.closest('[data-route]');
  if (target) navigate(target.dataset.route).catch(error => toast(error.message));
});
document.addEventListener('keydown', event => {
  if (event.key !== 'Enter' || event.isComposing) return;
  const active = document.activeElement;
  const nextListening = $('#next-listening');
  const nextWord = $('#next-word');
  if (state.route === 'listening' && nextListening && !nextListening.hidden && active !== nextListening) {
    event.preventDefault();
    nextListening.click();
  } else if (state.route === 'vocabulary' && nextWord && !nextWord.hidden && active !== nextWord) {
    event.preventDefault();
    nextWord.click();
  }
});
$('#menu-button').addEventListener('click', () => $('.sidebar').classList.toggle('open'));
$('#today-label').textContent = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' }).format(new Date());
navigate(location.hash.slice(1) || 'dashboard').catch(error => toast(error.message));
