import {summarize,markup,title,htmlDocument,actionNames,statusNames} from './report.js';

const $ = id => document.getElementById(id);
let config, phase='setup', secret='', track=null, plan=null, report=null, provider=null;
let frame=$('game'), loadTimer, generation=0, spent=0;
const decisions=new Map(), pending=new Set(), controllers=new Set(), downloads=new Set();
const seedParam = new URLSearchParams(location.search).get('seed');
if (/^\d+$/.test(seedParam||'')) $('seed').value=seedParam;

function stage(tag,heading,detail='') {
  $('stage').hidden=false; $('stage-tag').textContent=tag;
  $('stage-title').textContent=heading; $('stage-detail').textContent=detail;
  $('ready').hidden=true; $('view-report').hidden=true;
}

function forget() {
  secret=''; $('token').value='';
  controllers.forEach(c=>c.abort()); controllers.clear();
}

function reset() {
  generation++; clearTimeout(loadTimer); forget();
  downloads.forEach(url=>URL.revokeObjectURL(url)); downloads.clear();
  report=null; track=null; plan=null; decisions.clear(); pending.clear(); spent=0;
  $('report').replaceChildren(); $('report-section').hidden=true;
  const fresh=frame.cloneNode(false); fresh.removeAttribute('src'); frame.replaceWith(fresh); frame=fresh;
  phase='setup'; $('play').hidden=true; $('setup').hidden=false;
  $('decision').textContent='—'; $('latency').textContent='—'; $('cost').textContent='$0';
  $('prepare').disabled=false; $('setup-error').textContent='';
  $('token').focus();
}

async function request(path,body,authenticated=false,timeout=6500) {
  const controller=new AbortController(); controllers.add(controller);
  const timer=setTimeout(()=>controller.abort(),timeout);
  try {
    const headers={'Content-Type':'application/json'};
    if(authenticated&&secret) headers.Authorization=`Bearer ${secret}`;
    const response=await fetch(path,{method:'POST',headers,body:JSON.stringify(body),signal:controller.signal,cache:'no-store',credentials:'omit'});
    const data=await response.json();
    if(!response.ok) throw new Error(data.detail || 'Сервер недоступен');
    return data;
  } finally {clearTimeout(timer);controllers.delete(controller);}
}

function fail(message) {
  clearTimeout(loadTimer); phase='error'; forget();
  frame.src='about:blank';
  stage('Заезд остановлен',message,'Нажмите «Новая гонка», чтобы попробовать ещё раз.');
}

function configureEngine() {
  frame.contentWindow.raceConfigure(JSON.stringify({track,view:$('camera').value,bot_name:provider.id==='jev'?'Jev':provider.label}));
}

function begin() {
  if(phase!=='ready') return;
  frame.contentWindow.raceBegin(); frame.focus();
}

$('start-form').addEventListener('submit',async event=>{
  event.preventDefault(); if(phase!=='setup') return;
  provider=config.providers.find(p=>p.id===$('provider').value);
  secret=$('token').value.trim(); $('token').value='';
  if(provider.requires_token&&(secret.length<8||/\s/.test(secret))){secret='';$('setup-error').textContent='Введите корректный API-токен';return;}
  phase='loading'; $('prepare').disabled=true;
  $('setup').hidden=true; $('play').hidden=false;
  stage('Подготовка','Создаём трассу…');
  const run=generation;
  const seed=$('seed').value===''?crypto.getRandomValues(new Uint32Array(1))[0]%1000000001:Number($('seed').value);
  const count=Number($('count').value);
  try {
    track=await request('/api/track',{seed,count}); if(run!==generation)return;
    if(provider.planning) {
      stage('Подготовка','Модель составляет план…','Планирование проходит до старта гонки.');
      plan=await request('/api/plan',{seed,count,provider:provider.id},true,70000);
      if(run!==generation)return;
    }
    $('track-info').textContent=`Трасса #${seed} · препятствий: ${count}`;
    $('live-camera').value=$('camera').value;
    stage('Загрузка','Открываем игру…','Первый запуск загружает движок. Повторные заезды используют кеш файлов игры.');
    frame.src='/game/index.html';
    loadTimer=setTimeout(()=>fail('Игра загружается слишком долго'),120000);
  } catch(error){if(run===generation)fail(error.name==='AbortError'?'Сервер не ответил вовремя':error.message);}
});

async function decide(event) {
  const run=generation, start=performance.now();
  $('decision').textContent='выбирает…';
  let response;
  try {
    response=await request('/api/decide',{seed:track.seed,count:track.events.length,
      provider:provider.id,event_id:event.event_id,energy:event.energy,plan:plan?.plan||''},true);
  } catch(error) {response={event_id:event.event_id,status:error.name==='AbortError'?'timeout':'unavailable',action:'none',cost_usd:0};}
  if(run!==generation||phase==='error'||phase==='setup')return;
  response.roundtrip_ms=performance.now()-start;
  decisions.set(event.event_id,response);
  spent+=response.cost_usd||0;
  $('decision').textContent=response.status==='ok'?(actionNames[response.action]||response.action):(statusNames[response.status]||'сбой');
  $('latency').textContent=response.latency_ms==null?'—':`${Math.round(response.latency_ms)} мс`;
  $('cost').textContent=`$${spent.toFixed(6)}`;
  if(response.status==='invalid_token'){fail('TypeSafe не принял токен');return;}
  frame.contentWindow?.raceDecision?.(JSON.stringify(response));
}

window.addEventListener('message',async event=>{
  if(event.origin!==location.origin||event.source!==frame.contentWindow||!event.data)return;
  const data=event.data;
  if(data.type==='engine-ready'&&phase==='loading')configureEngine();
  if(data.type==='race-ready'&&phase==='loading'){
    clearTimeout(loadTimer);phase='ready';stage('Трасса готова','Нажмите любую клавишу, если готовы','Или нажмите кнопку ниже. Гонка начнётся после вашего действия.');$('ready').hidden=false;
  }
  if(data.type==='race-started'&&phase==='ready'){phase='running';$('stage').hidden=true;frame.focus();}
  if(data.type==='model-request'&&phase==='running'&&!decisions.has(data.event_id)){
    const task=decide(data);pending.add(task);task.finally(()=>pending.delete(task));
  }
  if(data.type==='race-finished'&&phase==='running'){
    phase='finishing';stage('Финиш','Собираем отчёт…');
    const run=generation;await Promise.allSettled([...pending]);
    if(run!==generation||phase==='error')return;
    forget();
    try {
      report=summarize(track,data.results,decisions,{id:provider.id,label:provider.id==='jev'?'Jev':provider.label},plan,config.input_price);
      phase='finished'; $('report').innerHTML=markup(report);$('report-section').hidden=false;
      stage('Гонка завершена',title(report),report.result.technical_failures?'Часть ответов модели не получена. Подробности — в отчёте.':'Токен очищен. Скачайте отчёт перед новой игрой.');
      $('view-report').hidden=false;
    }catch{fail('Не удалось сформировать полный отчёт');}
  }
});

$('provider').addEventListener('change',()=>{
  const selected=config.providers.find(p=>p.id===$('provider').value);
  $('token-label').hidden=!selected.requires_token;$('token').required=selected.requires_token;
});
$('live-camera').addEventListener('change',()=>{frame.contentWindow?.raceSetView?.($('live-camera').value);if(phase==='running')frame.focus();});
$('ready').addEventListener('click',begin);
window.addEventListener('keydown',event=>{if(phase==='ready'&&!event.repeat){event.preventDefault();begin();}});
$('restart').addEventListener('click',reset);
$('cancel').addEventListener('click',reset);
$('view-report').addEventListener('click',()=>$('report-section').scrollIntoView({behavior:'smooth'}));
window.addEventListener('pagehide',reset);
window.addEventListener('pageshow',event=>{if(event.persisted)reset();});

function download(format) {
  if(!report)return;
  const text=format==='html'?htmlDocument(report):JSON.stringify(report,null,2);
  const url=URL.createObjectURL(new Blob([text],{type:format==='html'?'text/html;charset=utf-8':'application/json'}));
  downloads.add(url);const link=document.createElement('a');link.href=url;link.download=`jev-race-${report.track.seed}.${format}`;link.click();
  setTimeout(()=>{URL.revokeObjectURL(url);downloads.delete(url);},10000);
}
$('download-html').addEventListener('click',()=>download('html'));
$('download-json').addEventListener('click',()=>download('json'));

fetch('/api/config',{cache:'no-store',credentials:'omit'}).then(r=>{if(!r.ok)throw new Error();return r.json();}).then(value=>{
  config=value;$('provider').replaceChildren(...config.providers.map(p=>new Option(p.label,p.id)));
  $('count').max=String(config.max_obstacles);$('prepare').disabled=false;$('prepare').textContent='Подготовить трассу →';
}).catch(()=>{$('setup-error').textContent='Не удалось соединиться с сервером. Обновите страницу.';});
