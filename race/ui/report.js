export const actionNames = {jump:'прыжок',slide:'подкат',shield:'щит',shoot:'выстрел',none:'пропуск'};
export const statusNames = {ok:'ответ получен',timeout:'тайм-аут',invalid_token:'токен не принят',rate_limited:'лимит API',unavailable:'нет связи',invalid_response:'некорректный ответ',cancelled:'запрос отменён'};
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const quantile = (values,q) => values.length ? values[Math.max(0,Math.ceil(values.length*q)-1)] : null;
const millis = n => n == null ? '—' : `${Math.round(n)} мс`;

export function summarize(track, results, decisions, provider, plan, inputPrice, autoHuman=false) {
  const racers = {};
  for (const actor of ['human','jev']) {
    const value = results[actor];
    if (!value || !Number.isFinite(value.elapsed) || value.outcomes.length !== track.events.length) throw new Error('Неполный результат гонки');
    const penalties = value.outcomes.filter(o=>!o.safe).length;
    racers[actor] = {...value, penalties, score: value.elapsed + track.penalty_seconds*penalties};
  }
  const byActor = actor => track.events.map(event => decisions.get(`${actor}:${event.id}`) ||
    {actor,event_id:event.id,status:'unavailable',action:'none',cost_usd:0});
  const rows = byActor('jev');
  const humanRows = autoHuman ? byActor('human') : [];
  const allRows = [...rows,...humanRows];
  const failures = allRows.filter(d=>d.status!=='ok').length;
  let winner = failures ? 'technical' : Math.abs(racers.human.score-racers.jev.score)<0.005 ? 'draw' : racers.human.score<racers.jev.score ? 'human':'jev';
  const latencies = allRows.filter(d=>d.status==='ok' && Number.isFinite(d.latency_ms)).map(d=>d.latency_ms).sort((a,b)=>a-b);
  return {version:2,created_at:new Date().toISOString(),track,provider,plan,auto_human:autoHuman,
    result:{winner,racers,technical_failures:failures},decisions:rows,human_decisions:humanRows,
    metrics:{requests:allRows.length,successful:allRows.filter(d=>d.status==='ok').length,
      p50_ms:quantile(latencies,.5),p95_ms:quantile(latencies,.95),
      cost_usd:allRows.reduce((sum,d)=>sum+(d.cost_usd||0),0),input_price_per_million:inputPrice}};
}

export function title(report) {
  return {human:'Вы победили!',
    jev:`${report.provider.label} побеждает`,draw:'Ничья',technical:'Заезд без зачёта'}[report.result.winner];
}

export function markup(report) {
  const {track,result,metrics} = report;
  const max = Math.max(...Object.values(result.racers).map(r=>r.score),1);
  const cards = ['human','jev'].map(actor => {
    const r = result.racers[actor];
    const name=actor==='human'?'Вы':report.provider.label;
    return `<div class="card ${result.winner===actor?'winner-card':''}"><div class="eyebrow">${esc(name)}</div><div class="score">${r.score.toFixed(2)} с</div><div class="scorebar"><span class="run" style="width:${100*r.elapsed/max}%"></span><span class="penalty" style="width:${100*r.penalties*track.penalty_seconds/max}%"></span></div><p>Бег ${r.elapsed.toFixed(2)} с + ${r.penalties} × ${track.penalty_seconds} с штрафа</p></div>`;
  }).join('');
  const cell = o => `<td class="${o.safe?'good':'bad'}">${esc(actionNames[o.action]||o.action)} · ${o.safe?'успех':'штраф'}</td>`;
  const rows = track.events.map((event,i)=>{
    const d=report.decisions[i];
    const auto=report.auto_human?`<td>${esc(actionNames[report.human_decisions[i].action]||report.human_decisions[i].action)} · ${millis(report.human_decisions[i].latency_ms)}</td>`:'';
    return `<tr><td>${i+1}</td><td>${esc(event.title)}</td>${cell(result.racers.human.outcomes[i])}${auto}${cell(result.racers.jev.outcomes[i])}<td>${esc(actionNames[d.action]||d.action)} / ${esc(statusNames[d.status]||d.status)}</td><td>${millis(d.latency_ms)}</td><td>${millis(d.roundtrip_ms)}</td></tr>`;
  }).join('');
  return `<h3 class="report-title">${esc(title(report))}</h3><p>Трасса #${track.seed} · препятствий: ${track.events.length} · ${new Date(report.created_at).toLocaleString('ru-RU')}</p>${result.technical_failures?`<p class="bad">Ответ не получен для ${result.technical_failures} запросов. Такой заезд не определяет победителя.</p>`:''}<div class="report-grid">${cards}</div><div class="metrics"><div><small>Ответы модели</small><b>${metrics.successful}/${metrics.requests}</b></div><div><small>P50 через сервер</small><b>${millis(metrics.p50_ms)}</b></div><div><small>P95 через сервер</small><b>${millis(metrics.p95_ms)}</b></div><div><small>Оценочная стоимость</small><b>$${metrics.cost_usd.toFixed(6)}</b></div></div><div class="card"><h3>Препятствия и действия</h3><div class="scroll"><table><thead><tr><th>#</th><th>Препятствие</th><th>Вы</th>${report.auto_human?'<th>Выбор игрока</th>':''}<th>Исполнение бота</th><th>Выбор модели / API</th><th>Сервер → модель</th><th>Полный запрос</th></tr></thead><tbody>${rows}</tbody></table></div></div><p class="report-note">Цель — меньшее время с учётом штрафов. Стартовый заряд: 3; +1 каждые 3 препятствия. Зелёная полоса — бег, оранжевая — штрафы. Время ответа включает сетевой запрос к провайдеру, а полный запрос — ещё и путь от браузера до сервера. Цена Jev рассчитана по $${metrics.input_price_per_million} за миллион входных токенов; фактический счёт определяет TypeSafe.</p><p class="report-note">Бот выбирает приём, а контроллер автоматически подбирает момент его исполнения. ${report.auto_human?'Персонажем игрока в этом заезде тоже управляла модель: два независимых запроса на каждое препятствие.':'Человек нажимает сам.'} Эта игра показывает отдельные решения и задержку, а не служит строгим сравнением интеллекта. Результат вычислен в браузере; публичной таблицы рекордов нет.</p>${report.plan?.plan?`<div class="card"><h3>План до гонки</h3><p>${esc(report.plan.plan)}</p><small>Подготовка: ${millis(report.plan.latency_ms)}</small></div>`:''}`;
}

export function htmlDocument(report) {
  return `<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Jev Race — отчёт</title><style>body{font:16px system-ui,sans-serif;background:#091b2c;color:#edfaff;max-width:1100px;margin:40px auto;padding:20px}p{line-height:1.5}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:10px;border-bottom:1px solid #405d6c;text-align:left}.card{background:#163548;border:1px solid #4a7182;border-radius:12px;padding:18px;margin:12px 0}.report-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.score{font-size:36px;font-weight:800}.metrics{display:flex;flex-wrap:wrap;gap:25px;margin:22px 0}.metrics b{display:block;font-size:22px}.scorebar{display:flex;height:12px;background:#274c5f;margin:12px 0}.run{background:#78d6bd}.penalty{background:#eea87f}.good{color:#91e6bf}.bad{color:#ffb4a2}.scroll{overflow:auto}.report-note{font-size:13px;color:#c1d1db}.winner-card{border-color:#91e6bf}@media(max-width:600px){.report-grid{grid-template-columns:1fr}}</style><h1>Jev Race · ваш отчёт</h1>${markup(report)}<p>Этот файл автономный. Он не отправляет запросы и не содержит токена.</p></html>`;
}
