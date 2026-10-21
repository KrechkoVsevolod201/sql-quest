const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = { dashboard: null, modules: [], databases: [], exercises: [], generatedExercises: [], selected: null, module: 'select', mode: 'practice', startedAt: Date.now(), timer: null, lastResult: null, labMode: 'setup', labSchema: [], generatedTask: null, aiReviewing: false, aiReturnFocus: null };
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pretty = (ms) => ms < 1 ? `${Number(ms).toFixed(3)} ms` : `${Number(ms).toFixed(2)} ms`;
let toastTimeout;

async function api(url, body) {
  const response = await fetch(url, body ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || `HTTP ${response.status}`);
  return value;
}
function toast(message) { const el=$('#toast'); el.textContent=message; el.classList.add('show'); clearTimeout(toastTimeout); toastTimeout=setTimeout(()=>el.classList.remove('show'),3000); }
function go(page) {
  $$('.page').forEach(el=>el.classList.toggle('active',el.id===`page-${page}`));
  $$('.nav-item').forEach(el=>el.classList.toggle('active',el.dataset.page===page));
  $('#crumb').textContent=({home:'Главная',learn:'Учиться',lab:'SQL-лаборатория',stats:'Моя статистика',settings:'Настройки AI'})[page]||'Главная';
  if(page==='stats') renderStats();
  if(page==='lab') refreshLabSchema();
  if(page==='learn') { if(!state.selected&&state.exercises.length) openModule('select'); else if(state.selected) startClock(); }
  window.scrollTo(0,0);
}
function formatDuration(ms) { const sec=Math.floor(ms/1000); return `${String(Math.floor(sec/60)).padStart(2,'0')}:${String(sec%60).padStart(2,'0')}`; }
function startClock() { clearInterval(state.timer); state.startedAt=Date.now(); $('#timer-display').textContent='00:00'; $('#timer-display').classList.remove('urgent'); state.timer=setInterval(()=>{const sec=Math.floor((Date.now()-state.startedAt)/1000); $('#timer-display').textContent=formatDuration(Date.now()-state.startedAt); $('#timer-display').classList.toggle('urgent',state.mode==='timed'&&sec>=100);},500); }
function renderDashboard(d) {
  state.dashboard=d;
  $('#side-level').textContent=`Уровень ${d.profile.level}`; $('#side-xp').textContent=`${d.profile.xp} XP всего`;
  $('#side-progress').style.width=`${d.profile.level_progress}%`; $('#side-progress-text').textContent=`${d.profile.level_progress} / 100 XP`;
  $('#xp-total').innerHTML=`${d.profile.xp} <small>XP</small>`; $('#main-progress').style.width=`${d.profile.level_progress}%`; $('#xp-next').textContent=`Ещё ${100-d.profile.level_progress} XP до уровня ${d.profile.level+1}`;
  $('#streak').textContent=`${d.profile.streak} ${d.profile.streak===1?'день':'дней'}`; $('#completed-count').textContent=d.completed_count; $('#exercise-count').textContent=d.exercise_count; $('#attempt-count').textContent=d.attempt_count; $('#avg-time').textContent=Number(d.avg_query_ms).toFixed(3);
  const daily=d.daily.exercise; $('#daily-title').textContent=daily.title; $('#daily-prompt').textContent=daily.prompt; $('.daily-footer .reward').textContent=`✦ +${30+daily.difficulty*5} XP${d.daily.completed?' · выполнено':''}`; $('.daily-card .difficulty').textContent=`${'◆'.repeat(daily.difficulty)}${'◇'.repeat(3-daily.difficulty)} · ${{1:'НАЧАЛЬНЫЙ',2:'СРЕДНИЙ',3:'ПРОДВИНУТЫЙ'}[daily.difficulty]}`;
  const dt=new Date(); $('#date-pill').textContent=new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'short'}).format(dt).replace('.','');
  $('#module-grid').innerHTML=d.modules.map(m=>`<button class="module-card" data-module="${esc(m.id)}"><div class="module-top"><span class="module-icon">${esc(m.icon||'✧')}</span><b>${esc(m.name)}</b><span class="module-count">${m.completed}/${m.total}</span></div><p>${esc(m.description)}</p><div class="module-progress"><i style="width:${m.total?m.completed/m.total*100:0}%"></i></div><div class="module-bottom"><span>${esc(m.topics.join(' · '))}</span><span>${m.total?Math.round(m.completed/m.total*100):0}%</span></div></button>`).join('');
  const recent=$('#history-list');
  const modeName={practice:'Практика',timed:'На время',fastest:'Рекорд скорости',optimal:'Оптимальный SQL'};
  if(d.recent.length) recent.innerHTML=d.recent.map(r=>`<div class="history-row"><b>${esc(r.title||exerciseName(r.exercise_id))}</b><span>${esc(modeName[r.mode]||r.mode)}</span><span>${formatDuration(r.duration_ms)}</span><span class="xp-earned">+${r.xp} XP</span></div>`).join('');
  else recent.innerHTML='<p class="muted">Реши первое задание — оно появится здесь.</p>';
  const completedIds=new Set(d.recent.map(r=>r.exercise_id));
  $('#exercise-list').innerHTML=state.exercises.filter(e=>e.module===state.module).map(e=>`<button class="exercise-link ${completedIds.has(e.id)?'done':''} ${state.selected?.id===e.id?'active':''}" data-exercise="${esc(e.id)}">${esc(e.title)}</button>`).join('');
  $('#module-list').innerHTML=state.modules.map(m=>`<button class="lesson-module ${state.module===m.id?'active':''}" data-module="${esc(m.id)}"><span>${esc(m.icon||'✧')}</span>${esc(m.name)}</button>`).join('');
  renderGeneratedExercises(completedIds);
}
function exerciseName(id) { return state.exercises.find(e=>e.id===id)?.title || state.generatedExercises.find(e=>e.id===id)?.title || `Задание ${id}`; }
function renderGeneratedExercises(completedIds=new Set()) {
  const row=$('#generated-picker-row');
  if(!row) return;
  row.hidden=!state.generatedExercises.length;
  $('#generated-exercise-list').innerHTML=state.generatedExercises.map(e=>`<button class="exercise-link generated-exercise-link ${completedIds.has(e.id)?'done':''} ${state.selected?.id===e.id?'active':''}" data-exercise="${esc(e.id)}"><span>✦</span>${esc(e.title)}</button>`).join('');
}
async function loadAll() {
  const [dash, modules, dbs, exercises, aiSettings, generated]=await Promise.all([api('/api/dashboard'),api('/api/modules'),api('/api/databases'),api('/api/exercises'),api('/api/ai/settings'),api('/api/ai/challenges')]);
  state.modules=modules; state.databases=dbs; state.exercises=exercises; state.generatedExercises=generated;
  $('#database-select').innerHTML=dbs.map(db=>`<option value="${esc(db.id)}">${esc(db.name)}</option>`).join('');
  $('#generator-topic').innerHTML=`<option value="">Выбери тему</option>${modules.map(m=>`<optgroup label="${esc(m.name)}">${m.topics.map(topic=>`<option value="${esc(topic)}" data-module="${esc(m.id)}">${esc(topic)}</option>`).join('')}</optgroup>`).join('')}<option value="__custom__">Своя тема…</option>`;
  renderDashboard(dash); renderStats();
  $('#lab-avg').textContent=Number(dash.lab_avg_ms).toFixed(3);
  $('#lm-base-url').value=aiSettings.base_url; $('#lm-model').value=aiSettings.model;
  $('#lm-connection-badge').textContent=aiSettings.configured?'Настроено':'Не подключено';
  $('#lm-feedback').textContent=aiSettings.configured?`Настройки сохранены · ${aiSettings.api_key_set?'API-ключ сохранён':'без API-ключа'}. Проверь доступность сервера.`:'Укажи адрес LM Studio, проверь соединение и сохрани настройки.';
  if(!dash.ai_enabled) $('#ai-status').textContent='Настрой LM Studio в разделе «Настройки AI»';
  if(!state.selected) { const q=await api('/api/lab/template'); $('#lab-editor').value=q.sql; }
  if(!state.selected&&state.exercises.length) await selectExercise(state.exercises[0].id);
}
async function openModule(module, exerciseId) {
  state.module=module==='daily'?(state.dashboard?.daily.exercise.module||'select'):module;
  $('#module-list').innerHTML=state.modules.map(m=>`<button class="lesson-module ${state.module===m.id?'active':''}" data-module="${esc(m.id)}"><span>${esc(m.icon||'✧')}</span>${esc(m.name)}</button>`).join('');
  const lessonExercises=state.exercises.filter(e=>e.module===state.module);
  let exercise=exerciseId?lessonExercises.find(e=>e.id===exerciseId):null;
  if(!exercise&&module==='daily') exercise=state.dashboard.daily.exercise;
  if(!exercise) exercise=lessonExercises[0];
  if(!exercise){toast('В этом модуле пока нет заданий');return;}
  await selectExercise(exercise.id); go('learn'); renderDashboard(state.dashboard);
}
async function selectExercise(id) {
  const exercise=await api(`/api/exercises/${encodeURIComponent(id)}`);
  state.selected=exercise; state.lastResult=null;
  $('#empty-lesson').hidden=true; $('#lesson-content').hidden=false;
  $('#task-title').textContent=exercise.title; $('#task-prompt').textContent=exercise.prompt;
  let recordLabel=$('#task-record');
  if(!recordLabel){recordLabel=document.createElement('div');recordLabel.id='task-record';recordLabel.style.cssText='margin-top:6px;color:#baa5e9;font:8px var(--mono)';$('#task-title').after(recordLabel);}
  const record=state.dashboard?.records?.[exercise.id]; recordLabel.textContent=record?`Личный рекорд · ${formatDuration(record.best_ms)} · лучший SQL ${pretty(record.best_query_ms)}`:'Первое прохождение — поставь личный рекорд!';
  const topicModule=state.modules.find(m=>m.id===exercise.module);
  $('#task-topic').textContent=exercise.generated?`AI-КВЕСТ · ${exercise.topic}`:(topicModule?.topics||[]).join(' · ');
  const difficultyLabel={1:'НАЧАЛЬНЫЙ',2:'СРЕДНИЙ',3:'ПРОДВИНУТЫЙ'}[exercise.difficulty]||'СРЕДНИЙ';
  $('#task-difficulty').textContent=`${'◆'.repeat(exercise.difficulty)}${'◇'.repeat(3-exercise.difficulty)} · ${difficultyLabel}`;
  if(exercise.generated&&![...$('#database-select').options].some(option=>option.value===exercise.database)) $('#database-select').insertAdjacentHTML('beforeend',`<option value="${esc(exercise.database)}">AI · ${esc(exercise.topic)}</option>`);
  $('#database-select').value=exercise.database;
  $('#schema-tables').innerHTML=schemaHtml(exercise.schema);
  $$('.exercise-link').forEach(el=>el.classList.toggle('active',el.dataset.exercise===id));
  $('#result-panel').hidden=true; $('#result-panel').innerHTML=''; $('#sql-editor').value='';
  if($('#page-learn').classList.contains('active')) startClock();
}
async function generateStudyChallenge() {
  const button=$('#generate-study-task'), status=$('#generator-status');
  const mode=$('.generator-mode.active')?.dataset.genMode||'random';
  const difficulty=Number($('#generator-difficulty').value||2);
  let topic='', moduleId='';
  if(mode==='topic') {
    const chosen=$('#generator-topic').value;
    if(chosen==='__custom__') topic=$('#generator-custom-topic').value.trim();
    else {topic=chosen;moduleId=$('#generator-topic option:checked').dataset.module||'';}
    if(!topic){status.textContent='Сначала выбери тему или введи свою.';$('#generator-topic').focus();return;}
  }
  button.disabled=true; button.classList.add('is-loading'); status.textContent='LM Studio придумывает задание и собирает учебную базу…';
  try {
    const challenge=await api('/api/ai/challenge',{mode,topic,difficulty});
    if(moduleId) challenge.module=moduleId;
    state.generatedExercises=[challenge,...state.generatedExercises.filter(item=>item.id!==challenge.id)].slice(0,20);
    state.module=state.modules.some(module=>module.id===challenge.module)?challenge.module:state.module;
    renderDashboard(state.dashboard);
    await selectExercise(challenge.id); go('learn');
    const tableCount=challenge.schema?.length||0;
    status.textContent=`Готово · ${tableCount} таблиц · сложность ${challenge.difficulty}/3`;
    toast('AI-квест готов: база данных и правильный ответ проверены.');
  } catch(error) {
    status.textContent=error.message; toast(`Не удалось создать задание: ${error.message}`);
  } finally {button.disabled=false;button.classList.remove('is-loading');}
}
function schemaHtml(tables) {
  if(!tables?.length) return '<p class="muted">Нет таблиц в базе.</p>';
  const relationships=[...new Map(tables.flatMap(t=>t.foreign_keys||[]).map(r=>[`${r.from_table}.${r.from_column}:${r.to_table}.${r.to_column}`,r])).values()];
  const links=relationships.length?`<div class="relationship-list"><div class="relationship-title">СВЯЗИ МЕЖДУ ТАБЛИЦАМИ</div>${relationships.map(r=>`<div class="relationship-row"><span class="relation-end"><b>${esc(r.from_table)}</b><small>${esc(r.from_column)}</small></span><span class="relation-track"><i></i><b>→</b></span><span class="relation-end"><b>${esc(r.to_table)}</b><small>🔑 ${esc(r.to_column)}</small></span><span class="relation-cardinality">${esc(r.cardinality||'N:1')}</span></div>`).join('')}</div>`:'';
  const cards=tables.map(t=>`<article class="erd-table"><header><span>▤</span><b>${esc(t.name)}</b><small>${t.columns.length} cols</small></header><div class="erd-columns">${t.columns.map(c=>`<div class="erd-column"><span class="column-key">${c.primary_key?'🔑':relationships.some(r=>r.from_table===t.name&&r.from_column===c.name)?'↗':''}</span><b>${esc(c.name)}</b><small>${esc(c.type||'TEXT')}</small></div>`).join('')}</div></article>`).join('');
  return `<div class="schema-graph">${links}<div class="erd-table-grid">${cards}</div></div>`;
}

function buildLearningWorkspace() {
  $('#page-learn').innerHTML=`
    <div class="page-intro learn-intro"><div class="eyebrow">ТРЕНИРОВОЧНАЯ ПЛОЩАДКА</div><h1>Учиться SQL</h1><p>Выбери тему, изучи связи между таблицами и напиши запрос.</p></div>
    <div class="learning-picker"><div class="picker-label">УЧЕБНЫЕ МОДУЛИ</div><div id="module-list" class="module-chips"></div><div class="exercise-picker-row"><span class="picker-label">ЗАДАНИЯ</span><div id="exercise-list" class="exercise-chips"></div></div><div class="generated-picker-row" id="generated-picker-row" hidden><span class="picker-label">МОИ AI-КВЕСТЫ</span><div id="generated-exercise-list" class="exercise-chips"></div></div></div>
    <details class="challenge-generator" id="challenge-generator"><summary><span class="generator-summary-icon">✦</span><span><b>Сгенерировать новое задание</b><small>Нейросеть создаст тему, базу данных, записи и эталонный ответ</small></span><span class="generator-chevron">⌄</span></summary><div class="generator-content"><div class="generator-row"><span>РЕЖИМ</span><div class="generator-mode-switch"><button class="generator-mode active" data-gen-mode="random">Случайная тема</button><button class="generator-mode" data-gen-mode="topic">Выбрать тему</button></div></div><div class="generator-row"><label for="generator-difficulty">СЛОЖНОСТЬ</label><select id="generator-difficulty" class="mode-select"><option value="1">Начальная</option><option value="2" selected>Средняя</option><option value="3">Продвинутая</option></select></div><div class="generator-row topic-generator-options" id="topic-generator-options" hidden><label for="generator-topic">ТЕМА ЗАДАНИЯ</label><select id="generator-topic" class="mode-select"><option value="">Выбери тему</option></select><input id="generator-custom-topic" type="text" maxlength="120" placeholder="Или напиши свою тему…" hidden></div><div class="generator-footer"><button class="primary-button" id="generate-study-task">✦ Сгенерировать задание</button><span id="generator-status" aria-live="polite">Используется подключённая LM Studio</span></div></div></details>
    <div id="empty-lesson" class="empty-state" hidden><div>⌘</div><h3>Выбери задание</h3><p>Твои SQL-приключения начинаются здесь.</p></div>
    <div id="lesson-content" class="lesson-workspace">
      <section class="challenge-panel"><div class="challenge-heading"><div class="challenge-title"><div class="daily-meta"><span class="difficulty" id="task-difficulty"></span><span class="task-topic" id="task-topic"></span></div><h2 id="task-title"></h2><div id="task-record" class="task-record"></div></div><div class="challenge-controls"><label for="mode-select">РЕЖИМ</label><select id="mode-select" class="mode-select"><option value="practice">Спокойная практика</option><option value="timed">⏱ На время · 2 мин</option><option value="fastest">ϟ Самое быстрое</option><option value="optimal">⌁ Оптимальный запрос</option></select><span class="timer-display" id="timer-display">00:00</span></div></div><div class="task-prompt"><span class="prompt-icon">✦</span><div><b>Твоя задача</b><p id="task-prompt"></p></div></div></section>
      <div class="workbench-grid"><section class="query-workbench"><div class="workbench-heading"><div><span class="workbench-icon">⌘</span><div><b>SQL-редактор</b><small>SQLite · Ctrl + Enter для запуска</small></div></div><span class="editor-language">SQLITE</span></div><div class="code-editor"><div class="line-numbers">1<br>2<br>3<br>4<br>5<br>6<br>7<br>8</div><textarea id="sql-editor" spellcheck="false" autocomplete="off" autocapitalize="off" placeholder="SELECT ...&#10;FROM ...&#10;WHERE ...;"></textarea><button class="editor-hint" id="hint-button">✧ Подсказка</button></div><div class="editor-actions"><button class="secondary-button" id="run-button">▶ Запустить запрос</button><button class="primary-button" id="check-button">Проверить решение <span>→</span></button></div><div class="result-panel" id="result-panel" hidden></div></section>
      <aside class="database-workbench"><div class="database-heading"><div><span class="workbench-icon database-icon">▤</span><div><b>Схема базы</b><small>Таблицы и связи</small></div></div><select id="database-select" aria-label="Учебная база данных" disabled></select></div><div id="schema-tables" class="schema-tables"></div><div class="schema-legend"><span><b>🔑</b> первичный ключ</span><span><b>↗</b> внешний ключ</span><span class="legend-relation">──→ связь</span></div></aside></div>
    </div>`;
}
function renderResult(container, result, status='') {
  container.hidden=false;
  if(result.error||result.message&&!result.rows) { container.innerHTML=`<div class="result-heading"><b class="error">Запрос не выполнен</b></div><div class="error-message">${esc(result.error||result.message)}</div>${typeof result.correct==='boolean'?'<button class="ai-review-button ask-ai-inline" style="margin-top:9px">✦ Получить AI-разбор решения</button>':''}`; return; }
  const rows=result.rows||[];
  let table='';
  if(result.columns?.length) table=`<table class="result-table"><thead><tr>${result.columns.map(c=>`<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(v=>`<td>${esc(v===null?'NULL':v)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  const title=status||'Результат запроса';
  container.innerHTML=`<div class="result-heading"><b class="${status.includes('✓')?'success':''}">${esc(title)}</b><span class="muted">${rows.length} строк · ${pretty(result.elapsed_ms||0)}</span></div>${table||'<span class="muted">Запрос выполнен.</span>'}${result.message?`<div class="result-note">${esc(result.message)}</div>`:''}${typeof result.correct==='boolean'?'<button class="ai-review-button ask-ai-inline" style="margin-top:9px">✦ Получить AI-разбор решения</button>':''}`;
}
async function runExercise(check) {
  if(!state.selected){toast('Сначала выбери задание');return;}
  const sql=$('#sql-editor').value;
  try {
    const result=check?await api('/api/grade',{exercise_id:state.selected.id,sql}):await api('/api/run',{database:state.selected.database,sql});
    state.lastResult=result;
    if(check) {
      renderResult($('#result-panel'),result,result.correct?'✓ Верно!':'Пока не совпало');
      if(result.correct) {
        const elapsed=Date.now()-state.startedAt;
        const reward=await api('/api/complete',{exercise_id:state.selected.id,mode:state.mode,duration_ms:elapsed,query_ms:result.elapsed_ms,correct:true});
        $('#result-panel').insertAdjacentHTML('beforeend',`<div class="result-note">${esc(reward.message)} · ${formatDuration(elapsed)}${state.mode==='timed'&&elapsed>120000?' · Таймер вышел, но решение засчитано':''}</div>`);
        clearInterval(state.timer); await refreshDashboard(); toast(reward.message);
      }
    } else renderResult($('#result-panel'),result,'Результат запроса');
  } catch(error){ renderResult($('#result-panel'),{error:error.message}); }
}
async function refreshDashboard() { state.dashboard=await api('/api/dashboard'); renderDashboard(state.dashboard); $('#lab-avg').textContent=Number(state.dashboard.lab_avg_ms).toFixed(3); }
function renderStats() {
  const d=state.dashboard;if(!d)return;
  $('#stats-level').textContent=d.profile.level;$('#stats-streak').textContent=d.profile.streak;$('#stats-lab').textContent=d.lab_runs;
  $('#progress-modules').innerHTML=d.modules.map(m=>`<div class="progress-module"><b>${esc(m.name)}</b><small>${m.completed} из ${m.total} заданий · ${m.total?Math.round(m.completed/m.total*100):0}%</small><div class="module-progress"><i style="width:${m.total?m.completed/m.total*100:0}%"></i></div></div>`).join('');
}
async function setLabMode(mode) {
  state.labMode=mode;
  $$('.lab-tab').forEach(b=>b.classList.toggle('active',b.dataset.labTab===mode));
  $('#lab-run').textContent=mode==='setup'?'▶ Создать / обновить базу':state.generatedTask?'✦ Проверить AI-квест':'▶ Выполнить запрос';
  if(mode==='query') { $('#lab-editor').value='SELECT *\nFROM events;'; $('#lab-status').textContent='Режим запроса · SQLite'; }
  else { $('#lab-status').textContent='Режим схемы · изолированная лаборатория'; }
}
async function runLab() {
  try {
    const result=state.labMode==='setup'?await api('/api/lab',{mode:'setup',sql:$('#lab-editor').value}):null;
    if(state.labMode==='setup') {
      state.labSchema=result.tables; $('#lab-schema').innerHTML=schemaHtml(result.tables); $('#lab-status').textContent=result.message; $('#lab-tables-count').textContent=result.tables.length;
      $('#lab-result').hidden=false; $('#lab-result').innerHTML=`<div class="result-heading"><b class="success">✓ ${esc(result.message)}</b></div>${schemaHtml(result.tables)}`; toast(result.message);
    } else if(state.generatedTask) {
      const grade=await api('/api/lab/grade',{sql:$('#lab-editor').value,solution:state.generatedTask.solution_sql});
      state.lastResult=grade; renderResult($('#lab-result'),grade,grade.correct?'✓ AI-квест решён!':'Попробуй ещё раз');
      $('#lab-status').textContent=grade.correct?'AI-квест пройден':'Результат AI-квеста не совпал';
      if(grade.correct&&!state.generatedTask.completed){
        const reward=await api('/api/lab/complete',{challenge_id:state.generatedTask.challenge_id,correct:true}); state.generatedTask.completed=true;
        $('#lab-result').insertAdjacentHTML('beforeend',`<div class="result-note">${esc(reward.message)}</div>`); toast(reward.message);
      }
      await refreshDashboard();
    } else {
      const queryResult=await api('/api/lab',{mode:'query',sql:$('#lab-editor').value});
      state.lastResult=queryResult;
      renderResult($('#lab-result'),queryResult,'Лабораторный замер'); $('#lab-status').textContent=`Запрос вернул ${queryResult.row_count} строк`; await refreshDashboard();
    }
  } catch(error) {renderResult($('#lab-result'),{error:error.message});$('#lab-status').textContent='Ошибка выполнения';}
}
async function refreshLabSchema() {
  try { state.labSchema=await api('/api/lab/schema'); $('#lab-schema').innerHTML=schemaHtml(state.labSchema); $('#lab-tables-count').textContent=state.labSchema.length; }
  catch(error) { $('#lab-schema').innerHTML=`<p class="muted">${esc(error.message)}</p>`; }
}
async function reviewSql(question=state.selected?.prompt||'Разбери запрос из лаборатории', sql=state.selected?$('#sql-editor').value:$('#lab-editor').value, result=state.lastResult) {
  if(state.aiReviewing) return;
  state.aiReviewing=true;
  state.aiReturnFocus=document.activeElement;
  const button=$('#ai-review'); if(button) button.disabled=true;
  const overlay=$('#ai-response-overlay');
  overlay.hidden=false; document.body.classList.add('ai-dialog-open');
  $('#ai-response-title').textContent='Разбор от ИИ';
  $('#ai-response-status').textContent='LM Studio анализирует запрос…';
  $('#ai-response-content').innerHTML='<div class="ai-loading" role="status" aria-label="Загрузка"><i></i><i></i><i></i></div>';
  $('#ai-response-close').focus();
  try {
    const review=await api('/api/ai/review',{question,sql,result});
    $('#ai-response-title').textContent=review.score===null?'Ответ от ИИ':`AI-разбор · ${review.score}/100`;
    $('#ai-response-status').textContent='Ответ получен от LM Studio';
    $('#ai-response-content').innerHTML=renderAiReview(review);
  } catch(error) {
    $('#ai-response-status').textContent='Не удалось получить разбор';
    $('#ai-response-content').innerHTML=`<div class="ai-response-error"><b>LM Studio вернула ошибку</b><p>${esc(error.message)}</p><small>Проверь, что модель загружена и выбранный ID модели совпадает с настройками LM Studio.</small></div>`;
  } finally {state.aiReviewing=false;if(button) button.disabled=false;}
}
function renderAiReview(review) {
  const hasScore=review.score!==null&&review.score!==undefined&&review.score!==''&&Number.isFinite(Number(review.score));
  const score=hasScore?Math.max(0,Math.min(100,Number(review.score))):null;
  const strengths=Array.isArray(review.strengths)?review.strengths:[];
  const suggestions=Array.isArray(review.suggestions)?review.suggestions:[];
  const list=(title,items,kind)=>items.length?`<section class="ai-review-section ${kind}"><h3>${kind==='ai-strengths'?'Сильные стороны':'Что можно улучшить'}</h3><ul>${items.map(item=>`<li>${esc(item)}</li>`).join('')}</ul></section>`:'';
  return `${score===null?'':`<section class="ai-score-card"><div class="ai-score-number"><b>${score}</b><span>/100</span></div><div class="ai-score-detail"><b>Оценка решения</b><div class="ai-score-track"><i style="--score-width:${score}%"></i></div><small>${score>=85?'Отличный результат':score>=65?'Хорошая основа':'Есть над чем поработать'}</small></div></section>`}${review.verdict?`<section class="ai-verdict"><h3>Общий разбор</h3><p>${esc(review.verdict)}</p></section>`:''}${list('Сильные стороны',strengths,'ai-strengths')}${list('Что можно улучшить',suggestions,'ai-suggestions')}${review.next_hint?`<section class="ai-next-hint"><span>✧</span><div><b>Следующая подсказка</b><p>${esc(review.next_hint)}</p></div></section>`:''}${!review.verdict&&!strengths.length&&!suggestions.length&&!review.next_hint?'<p class="ai-empty-answer">Модель ответила, но не прислала текст разбора. Попробуй отправить запрос ещё раз.</p>':''}`;
}
function closeAiReview() {
  const overlay=$('#ai-response-overlay');
  if(overlay.hidden) return;
  overlay.hidden=true; document.body.classList.remove('ai-dialog-open');
  if(state.aiReturnFocus?.focus) state.aiReturnFocus.focus();
}
async function generateDatabase() {
  const topic=state.module||'SELECT и фильтрация';
  const button=$('#generate-db'); button.disabled=true; button.textContent='✦ Генерирую…';
  try {
    const generated=await api('/api/ai/generate',{topic,level:'начальный–средний',database:'небольшой учебный проект'});
    state.generatedTask={...generated,challenge_id:globalThis.crypto?.randomUUID?.()||`${Date.now()}-${Math.random()}`,completed:false};
    $('#lab-editor').value=`-- ${generated.title||'Сгенерированная база'}\n${generated.schema_sql||''}\n\n${generated.seed_sql||''}`;
    $('#ai-result').hidden=false; $('#ai-result').innerHTML=`<h3>✦ ${esc(generated.title||'Новая задача')}</h3><p>${esc(generated.description||generated.task||'Скрипт готов. Перейди в режим создания таблиц и запусти его.')}</p><p><b>Задание:</b> ${esc(generated.task||'')}</p>${generated.hint?`<p><b>Подсказка:</b> ${esc(generated.hint)}</p>`:''}${generated.solution_sql?`<details><summary>Показать решение</summary><pre>${esc(generated.solution_sql)}</pre></details>`:''}`;
    await setLabMode('setup'); go('lab'); toast('AI подготовил схему и задание — запусти скрипт в лаборатории.');
  } catch(error) {$('#ai-result').hidden=false;$('#ai-result').innerHTML=`<p>${esc(error.message)}</p>`;}
  finally {button.disabled=false;button.textContent='✦ ИИ-конструктор';}
}

async function testLmStudio() {
  const button=$('#lm-test-button'), feedback=$('#lm-feedback'); button.disabled=true; feedback.textContent='Подключаемся к LM Studio…';
  try {
    const result=await api('/api/ai/test',{base_url:$('#lm-base-url').value,api_key:$('#lm-api-key').value});
    const models=result.models||[];
    $('#lm-model-list').innerHTML=models.map(model=>`<option value="${esc(model.id)}"></option>`).join('');
    if(!$('#lm-model').value&&models.length) $('#lm-model').value=models[0].id;
    $('#lm-connection-badge').textContent='Сервер доступен';
    feedback.textContent=`${result.message}${models.length?` Модели: ${models.map(model=>model.id).join(', ')}`:' Запусти модель в LM Studio.'}`;
  } catch(error) {
    $('#lm-connection-badge').textContent='Нет соединения'; feedback.textContent=error.message;
  } finally {button.disabled=false;}
}
async function saveLmSettings() {
  const button=$('#lm-save-button'), feedback=$('#lm-feedback'); button.disabled=true; feedback.textContent='Сохраняем настройки…';
  try {
    const settings=await api('/api/ai/settings',{base_url:$('#lm-base-url').value,model:$('#lm-model').value,api_key:$('#lm-api-key').value,clear_api_key:$('#lm-clear-key').checked});
    $('#lm-api-key').value=''; $('#lm-clear-key').checked=false;
    $('#lm-connection-badge').textContent='Настроено'; $('#ai-status').textContent='LM Studio настроена';
    feedback.textContent=`Настройки сохранены · ${settings.api_key_set?'API-ключ сохранён':'без API-ключа'}. Нажми «Проверить соединение», если ещё не проверяла.`;
    if(state.dashboard) state.dashboard.ai_enabled=true;
    toast('Настройки LM Studio сохранены');
  } catch(error) {feedback.textContent=error.message;$('#lm-connection-badge').textContent='Ошибка настройки';}
  finally {button.disabled=false;}
}

document.addEventListener('click',async event=>{
  if(event.target.closest('#ai-response-close')||event.target.id==='ai-response-overlay'){closeAiReview();return;}
  const nav=event.target.closest('[data-page]'); if(nav){go(nav.dataset.page);return;}
  const goto=event.target.closest('[data-goto]');if(goto){go(goto.dataset.goto);return;}
  const generationMode=event.target.closest('[data-gen-mode]');if(generationMode){$$('.generator-mode').forEach(button=>button.classList.toggle('active',button===generationMode));$('#topic-generator-options').hidden=generationMode.dataset.genMode!=='topic';$('#generator-status').textContent=generationMode.dataset.genMode==='random'?'LM Studio сама выберет тему из учебного каталога.':'Выбери тему из каталога или задай свою.';return;}
  const module=event.target.closest('[data-module]');if(module){openModule(module.dataset.module);return;}
  const exercise=event.target.closest('[data-exercise]');if(exercise){selectExercise(exercise.dataset.exercise);return;}
  if(event.target.closest('[data-start-daily]')){openModule('daily');return;}
  const mode=event.target.closest('[data-mode]');if(mode){state.mode=mode.dataset.mode;$('#mode-select').value=state.mode;openModule(state.dashboard.daily.exercise.module);return;}
  if(event.target.closest('#run-button')){runExercise(false);return;}
  if(event.target.closest('#check-button')){runExercise(true);return;}
  if(event.target.closest('#hint-button')){toast(state.selected?.hint||'Выбери задание, чтобы увидеть подсказку.');return;}
  if(event.target.closest('#generate-study-task')){generateStudyChallenge();return;}
  const tab=event.target.closest('[data-lab-tab]');if(tab){setLabMode(tab.dataset.labTab);return;}
  if(event.target.closest('#lab-run')){runLab();return;}
  if(event.target.closest('#generate-db')){generateDatabase();return;}
  if(event.target.closest('#refresh-lab')){refreshLabSchema();return;}
  if(event.target.closest('#ai-review')){reviewSql('Разбери запрос из SQL-лаборатории',$('#lab-editor').value,state.lastResult);return;}
  if(event.target.closest('#lm-test-button')){testLmStudio();return;}
  if(event.target.closest('#lm-save-button')){saveLmSettings();return;}
  if(event.target.closest('.ask-ai-inline')){if($('#page-lab').classList.contains('active'))reviewSql(state.generatedTask?.task||'Разбери запрос из лаборатории',$('#lab-editor').value,state.lastResult);else reviewSql(state.selected?.prompt,$('#sql-editor').value,state.lastResult);return;}
});
document.addEventListener('keydown',event=>{if(event.key==='Escape')closeAiReview();});
buildLearningWorkspace();
$('#mode-select').addEventListener('change',event=>{state.mode=event.target.value;startClock();});
$('#database-select').addEventListener('change',async event=>{try{$('#schema-tables').innerHTML=schemaHtml(await api(`/api/schema?database=${encodeURIComponent(event.target.value)}`));}catch(error){toast(error.message);}});
$('#generator-topic').addEventListener('change',event=>{const custom=event.target.value==='__custom__';$('#generator-custom-topic').hidden=!custom;if(custom)$('#generator-custom-topic').focus();});
$('#sql-editor').addEventListener('keydown',event=>{if(event.key==='Enter'&&(event.ctrlKey||event.metaKey)){event.preventDefault();runExercise(false);}if(event.key==='Tab'){event.preventDefault();const start=event.target.selectionStart;event.target.setRangeText('  ',start,event.target.selectionEnd,'end');}});
loadAll().catch(error=>toast(`Ошибка загрузки: ${error.message}`));
