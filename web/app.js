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
  vocabulary: { title: 'Vocabulary', kicker: 'BUILD YOUR WORD BANK', render: () => '<div class="panel"><div class="panel-body"><p class="muted">词汇训练正在准备中。</p></div></div>' },
  writing: { title: 'Writing', kicker: 'THINK · WRITE · REVISE', render: () => '<div class="panel"><div class="panel-body"><p class="muted">写作训练正在准备中。</p></div></div>' },
  listening: { title: 'Listening', kicker: 'HEAR EVERY DETAIL', render: () => '<div class="panel"><div class="panel-body"><p class="muted">听力训练正在准备中。</p></div></div>' },
  review: { title: 'Review', kicker: 'TURN WEAKNESS INTO MEMORY', render: () => '<div class="panel"><div class="panel-body"><p class="muted">复习中心正在准备中。</p></div></div>' },
  settings: { title: 'Settings', kicker: 'LOCAL CONFIGURATION', render: renderSettings },
};

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

document.addEventListener('click', event => {
  const target = event.target.closest('[data-route]');
  if (target) navigate(target.dataset.route).catch(error => toast(error.message));
});
$('#menu-button').addEventListener('click', () => $('.sidebar').classList.toggle('open'));
$('#today-label').textContent = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' }).format(new Date());
navigate(location.hash.slice(1) || 'dashboard').catch(error => toast(error.message));

