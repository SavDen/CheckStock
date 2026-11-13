'use strict';
const $ = (s, root = document) => root.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const number = value => Number(value).toLocaleString('ru-RU');
const titles = {stock:'Остатки товаров', movements:'Движения товара', warehouses:'Склады фулфилмента', history:'История операций'};
const descriptions = {stock:'На складе, в резерве и в пути — без потерь между статусами.', movements:'Весь маршрут товара: от резерва до подтверждённой приёмки.', warehouses:'Действующие склады и сохранённые остатки удалённых ФФ.', history:'Каждое изменение учтено. От первого прихода до последней отправки.'};
const kinds = {transfer:'Между ФФ',fbs:'FBS · клиенту',fbo:'FBO · маркетплейсу'};
const statuses = {reserved:['В резерве','amber'],transit:['В пути','blue'],completed:['Завершено','green'],cancelled:['Отменено','']};
const eventNames = {receipt:'Приход',transfer_sent:'Перемещение отправлено',transfer_received:'Перемещение принято',fbs_reserved:'Резерв FBS',fbs_sent:'Заказ FBS отправлен',fbs_cancelled:'Резерв FBS отменён',fbs_received:'Заказ доставлен',fbo_sent:'Поставка FBO отправлена',fbo_received:'Поставка FBO принята',warehouse_created:'Склад добавлен',warehouse_renamed:'Склад переименован',warehouse_archived:'Склад удалён'};
let data = null, view = 'stock', query = '', warehouseFilter = '', showArchive = true, movementFilter = 'active';
let formMode = '', formWarehouse = null, retrySignature = '', retryKey = '', submitting = false, refreshing = false;
const dialog = $('#operation-dialog');
const sum = (rows, key) => rows.reduce((n, r) => n + r[key], 0);
const getProduct = id => data.products.find(p => p.id === id);
const getWarehouse = id => data.warehouses.find(w => w.id === id);
const warehouseName = id => getWarehouse(id)?.name || '—';
const badge = (text, color = '') => `<span class="badge ${color}">${esc(text)}</span>`;
const empty = (title, text) => `<div class="empty">${icon('box')}<strong>${esc(title)}</strong><p>${esc(text)}</p></div>`;
function matches(p) { return !query || `${p.name} ${p.sku}`.toLowerCase().includes(query.toLowerCase()); }
function productHTML(p) { return `<div class="product-info"><span class="product-symbol">${icon('box')}</span><div><strong>${esc(p.name)}</strong><span class="sku">${esc(p.sku)}</span></div></div>`; }
function dateText(value) { return new Date(value).toLocaleString('ru-RU', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}); }
function toast(message) { const el = $('#toast'); el.textContent = message; el.hidden = false; clearTimeout(toast.timer); toast.timer = setTimeout(() => el.hidden = true, 4500); }
async function api(path, method = 'GET', body, key) {
  if (window.CheckStockDemo) return window.CheckStockDemo.request(path, method, body, key);
  let response;
  try { response = await fetch(path, {method, headers:{...(body !== undefined ? {'Content-Type':'application/json'} : {}), ...(key ? {'Idempotency-Key':key} : {})}, body:body !== undefined ? JSON.stringify(body) : undefined, signal:AbortSignal.timeout(15000)}); }
  catch { throw new Error('Нет ответа от сервера. Проверьте соединение и повторите: тот же запрос не спишет товар дважды.'); }
  const result = await response.json();
  if (!response.ok) {
    let message = result.message || 'Не удалось выполнить операцию.';
    if (result.details?.alternatives?.length) message += ' На других складах: ' + result.details.alternatives.map(w => `${w.name}${w.archived ? ' (удалён)' : ''} — ${w.available} шт`).join('; ') + '.';
    throw new Error(message);
  }
  return result;
}
async function load({initial = false} = {}) {
  if (refreshing) return;
  refreshing = true; $('#refresh').disabled = true;
  try {
    data = await api('/api/snapshot');
    $('#load-error').hidden = true;
    $('#connection').className = 'connection online'; $('#connection').innerHTML = window.CheckStockDemo ? '<i></i>Данные в браузере' : '<i></i>База подключена';
    $('#updated').textContent = 'Обновлено в ' + new Date().toLocaleTimeString('ru-RU', {hour:'2-digit',minute:'2-digit'});
    render();
    if (initial) $('#view-root').classList.add('main-enter');
  } catch (error) {
    $('#load-error').textContent = error.message; $('#load-error').hidden = false;
    $('#connection').className = 'connection offline'; $('#connection').innerHTML = '<i></i>Нет соединения';
    if (!data) $('#view-root').innerHTML = empty('Данные пока недоступны', 'Убедитесь, что приложение и PostgreSQL запущены, затем нажмите обновление.');
  } finally { refreshing = false; $('#refresh').disabled = false; }
}
function summaryHTML() {
  const stocks = data.stocks.filter(b => (!warehouseFilter || String(b.warehouse_id) === warehouseFilter) && (showArchive || !getWarehouse(b.warehouse_id).archived) && matches(getProduct(b.product_id)));
  const active = data.movements.filter(m => m.status === 'transit' && matches(getProduct(m.product_id)) && (!warehouseFilter || String(m.source_id) === warehouseFilter || String(m.destination_id) === warehouseFilter));
  return `<div class="summary" aria-label="Сводка по текущему фильтру">
    <div class="summary-item"><span>Физически на ФФ</span><strong>${number(sum(stocks,'physical'))}</strong><small>шт.</small></div>
    <div class="summary-item available"><span>Доступно к отправке</span><strong>${number(stocks.reduce((n,s)=>n+s.available,0))}</strong><small>шт.</small></div>
    <div class="summary-item reserved"><span>В резерве FBS</span><strong>${number(sum(stocks,'reserved'))}</strong><small>шт.</small></div>
    <div class="summary-item"><span>Всего в пути</span><strong>${number(sum(active,'quantity'))}</strong><small>шт.</small></div>
  </div>`;
}
function searchHTML(placeholder = 'Название товара или артикул') { return `<label class="search-field">${icon('search')}<input id="search" type="search" value="${esc(query)}" placeholder="${placeholder}" aria-label="Поиск товара"></label>`; }
function inventoryHTML() {
  const warehouses = data.warehouses.filter(w => (!warehouseFilter || String(w.id) === warehouseFilter) && (showArchive || !w.archived));
  let rows = '';
  for (const p of data.products.filter(matches)) {
    warehouses.forEach((w,i) => {
      const b = data.stocks.find(s=>s.product_id===p.id && s.warehouse_id===w.id) || {physical:0,available:0,reserved:0};
      rows += `<tr>${i === 0 ? `<td class="product-cell" rowspan="${warehouses.length}">${productHTML(p)}</td>` : ''}<td><span class="warehouse-name"><i></i>${esc(w.name)} ${w.archived ? badge('Удалён') : ''}</span></td><td class="number">${number(b.physical)}</td><td class="number available-number">${number(b.available)}</td><td class="number ${b.reserved ? '' : 'muted'}">${number(b.reserved)}</td><td>${w.archived ? badge('В архиве') : b.available === 0 ? badge('Нет доступных','red') : badge('В наличии','green')}</td></tr>`;
    });
  }
  const active = data.movements.filter(m=>m.status==='transit' && matches(getProduct(m.product_id)) && (!warehouseFilter || String(m.source_id)===warehouseFilter || String(m.destination_id)===warehouseFilter));
  const transit = kind => number(sum(active.filter(m=>m.kind===kind),'quantity'));
  return `${summaryHTML()}<section class="panel" aria-label="Остатки по товарам и складам"><div class="toolbar">${searchHTML()}<div class="toolbar-right"><label class="checkbox-label"><input type="checkbox" id="show-archive" ${showArchive?'checked':''}>Удалённые ФФ</label><select id="warehouse-filter" aria-label="Фильтр склада"><option value="">Все склады</option>${data.warehouses.map(w=>`<option value="${w.id}" ${String(w.id)===warehouseFilter?'selected':''}>${esc(w.name)}${w.archived?' · удалён':''}</option>`).join('')}</select></div></div>${rows ? `<div class="table-scroll"><table><thead><tr><th>Товар / артикул</th><th>Склад ФФ</th><th class="number">На складе</th><th class="number">Доступно</th><th class="number">Резерв FBS</th><th>Статус</th></tr></thead><tbody>${rows}</tbody></table></div>` : empty('Ничего не найдено','Измените запрос или фильтр склада.')}<div class="table-foot"><span>Доступно = физический остаток − резерв FBS</span><span>В пути учитывается отдельно</span></div></section>
  <div class="section-heading"><h2>Товар в пути</h2><a class="text-link" href="#movements">Все движения ${icon('arrow')}</a></div><section class="transit-row" aria-label="Товар в пути по направлениям"><div class="transit-item"><span class="transit-icon">${icon('warehouse')}</span><div><strong>${transit('transfer')}</strong><small>шт.</small><p>Между складами ФФ</p></div></div><div class="transit-item"><span class="transit-icon">${icon('box')}</span><div><strong>${transit('fbo')}</strong><small>шт.</small><p>На маркетплейс · FBO</p></div></div><div class="transit-item"><span class="transit-icon">${icon('route')}</span><div><strong>${transit('fbs')}</strong><small>шт.</small><p>К клиенту · FBS</p></div></div></section>`;
}
function movementActions(m) {
  if (m.status==='reserved') return `<button class="button small secondary" data-action="cancel" data-id="${m.id}">Отменить</button><button class="button small primary" data-action="send" data-id="${m.id}">Отправить</button>`;
  if (m.status==='transit') return `<button class="button small secondary" data-action="receive" data-id="${m.id}">${m.kind==='fbs'?'Подтвердить доставку':'Принять'}</button>`;
  return '<span class="muted">—</span>';
}
function movementsHTML() {
  const movements = data.movements.filter(m=> matches(getProduct(m.product_id)) && (movementFilter==='all' || (movementFilter==='active' ? ['reserved','transit'].includes(m.status) : ['completed','cancelled'].includes(m.status))));
  return `<section class="panel"><div class="toolbar"><div class="tabs" aria-label="Статус движения">${[['active','Активные'],['closed','Завершённые'],['all','Все']].map(([v,label])=>`<button class="tab ${v===movementFilter?'active':''}" data-movement-filter="${v}">${label}</button>`).join('')}</div>${searchHTML()}</div>${movements.length ? `<div class="table-scroll"><table><thead><tr><th>Товар</th><th>Направление</th><th>Маршрут</th><th class="number">Кол-во</th><th>Статус</th><th class="number">Действие</th></tr></thead><tbody>${movements.map(m=>{const [label,color]=statuses[m.status];return `<tr><td class="movement-product"><strong>${esc(getProduct(m.product_id).name)}</strong><span class="sku">${esc(getProduct(m.product_id).sku)} · ${dateText(m.created_at)}</span></td><td>${badge(kinds[m.kind])}</td><td><div class="route">${esc(warehouseName(m.source_id))}${icon('arrow')}${esc(m.destination_id?warehouseName(m.destination_id):m.destination_label)}</div>${m.destination_id && getWarehouse(m.destination_id).archived ? '<span class="history-note">Склад назначения удалён · приёмка сохранится в архиве</span>' : ''}</td><td class="number">${number(m.quantity)}</td><td>${badge(label,color)}</td><td><div class="actions">${movementActions(m)}</div></td></tr>`;}).join('')}</tbody></table></div>` : empty('Движений пока нет',query?'Измените поисковый запрос.':'Создайте резерв FBS, поставку FBO или перемещение между складами.')}<div class="table-foot"><span>Резерв блокирует товар до отправки или отмены</span><span>${movements.length} операций</span></div></section>`;
}
function warehousesHTML() {
  return `<div class="info-note">${icon('info')}<span>Удаление переводит склад в архив. Остатки и история сохраняются; товар можно вывезти перемещением. Ранее созданные резервы и поставки можно завершить.</span></div><section class="warehouses-grid">${data.warehouses.map(w=>{
    const stocks=data.stocks.filter(b=>b.warehouse_id===w.id);
    return `<article class="warehouse-card ${w.archived?'archived':''}"><div class="warehouse-card-head">${icon('warehouse')}<h2>${esc(w.name)}</h2>${badge(w.archived?'Удалён':'Действует',w.archived?'':'green')}</div><dl><div><dt>На складе</dt><dd>${sum(stocks,'physical')}</dd></div><div><dt>Доступно</dt><dd class="available-number">${sum(stocks,'available')}</dd></div><div><dt>Резерв FBS</dt><dd>${sum(stocks,'reserved')}</dd></div></dl>${data.products.map(p=>{const b=stocks.find(s=>s.product_id===p.id);return `<div class="warehouse-stock-line"><span>${esc(p.name)}</span><span>${b?.physical||0} шт. <span class="muted">/ резерв ${b?.reserved||0}</span></span></div>`;}).join('')}<div class="actions">${w.archived?`<button class="button small secondary" data-evacuate="${w.id}">Вывезти остаток</button>`:`<button class="button small secondary" data-rename="${w.id}">Переименовать</button><button class="button small danger" data-archive="${w.id}">Удалить склад</button>`}</div></article>`;
  }).join('')}</section>`;
}
function historyHTML() {
  const events = data.events.filter(e=>!query || (e.product_id && matches(getProduct(e.product_id))) || `${eventNames[e.action]} ${e.source_label} ${e.destination_label} ${e.note}`.toLowerCase().includes(query.toLowerCase()));
  return `<section class="panel"><div class="toolbar">${searchHTML('Товар, склад или операция')}<span class="muted" style="font-size:11px">${events.length} записей · сначала новые</span></div>${events.length ? `<div class="table-scroll"><table><thead><tr><th>Время</th><th>Операция</th><th>Товар</th><th>Откуда → куда</th><th class="number">Кол-во</th></tr></thead><tbody>${events.map(e=>`<tr><td class="muted">${dateText(e.created_at)}<span class="sku">#${String(e.id).padStart(4,'0')}</span></td><td><span class="history-action">${esc(eventNames[e.action]||e.action)}</span>${e.note?`<span class="history-note">${esc(e.note)}</span>`:''}</td><td>${e.product_id?`${esc(getProduct(e.product_id).name)}<span class="sku">${esc(getProduct(e.product_id).sku)}</span>`:'<span class="muted">—</span>'}</td><td><div class="route">${esc(e.source_label||'—')}${icon('arrow')}${esc(e.destination_label||'—')}</div></td><td class="number">${e.quantity?number(e.quantity):'—'}</td></tr>`).join('')}</tbody></table></div>`:empty('Записи не найдены','Попробуйте другой поисковый запрос.')}<div class="table-foot"><span>Названия складов зафиксированы на момент операции</span><span>Повторные подтверждения не создают дубли</span></div></section>`;
}
function render() {
  if (!data) return;
  const root=$('#view-root'); const focused = document.activeElement?.id; const selection = focused==='search' ? $('#search').selectionStart : null;
  $('#page-title').textContent=titles[view]; $('#page-description').textContent=descriptions[view];
  $('#breadcrumb').textContent={stock:'Остатки',movements:'Движения',warehouses:'Склады',history:'История'}[view];
  document.title=`${titles[view]} — CheckStock`;
  document.querySelectorAll('[data-view]').forEach(a=>{a.classList.toggle('active',a.dataset.view===view);if(a.dataset.view===view)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  $('#nav-count').textContent=data.movements.filter(m=>['reserved','transit'].includes(m.status)).length;
  $('#new-operation').innerHTML=icon('plus')+(view==='warehouses'?'Добавить склад':'Новая операция');
  root.innerHTML=({stock:inventoryHTML,movements:movementsHTML,warehouses:warehousesHTML,history:historyHTML}[view])();
  if(focused==='search' && $('#search')) { $('#search').focus(); if($('#search').type!=='search')$('#search').setSelectionRange(selection,selection); }
}
function selectField(name,label,options,selected='',hint='') {return `<label class="field"><span>${label}</span><select name="${name}" required>${options.map(([value,text])=>`<option value="${esc(value)}" ${String(value)===String(selected)?'selected':''}>${esc(text)}</option>`).join('')}</select>${hint?`<small>${hint}</small>`:''}</label>`;}
function renderForm(selected = {}) {
  const active=data.warehouses.filter(w=>!w.archived); const all=data.warehouses;
  const value=(k,fallback='')=>selected[k] ?? fallback;
  if(formMode==='warehouse'||formMode==='rename') {
    $('#dialog-title').textContent=formMode==='rename'?'Переименовать склад':'Добавить склад';
    $('#form-fields').innerHTML=`<label class="field"><span>Название склада ФФ</span><input name="name" maxlength="80" required placeholder="Например, Восток" value="${esc(formMode==='rename'?warehouseName(formWarehouse):'')}"></label>`;
    $('#submit-operation').textContent='Сохранить';return;
  }
  if(formMode==='archive') {
    const w=getWarehouse(formWarehouse), stocks=data.stocks.filter(b=>b.warehouse_id===w.id);
    $('#dialog-title').textContent='Удалить склад?';
    $('#form-fields').innerHTML=`<p class="confirm-copy">Склад <strong>${esc(w.name)}</strong> будет убран из действующих. На нём останется <strong>${sum(stocks,'physical')} шт.</strong>, включая резерв <strong>${sum(stocks,'reserved')} шт.</strong></p><div class="form-context">Остатки и история сохранятся в архиве. Товар можно вывезти; ранее начатые операции можно завершить.</div>`;
    $('#submit-operation').textContent='Удалить в архив'; return;
  }
  $('#dialog-title').textContent='Новая операция';$('#submit-operation').textContent='Провести операцию';
  const type=value('type', formMode==='evacuate'?'transfer':'receipt');
  let html=selectField('type','Тип операции',[['receipt','Приход товара'],['transfer','Перемещение между ФФ'],['fbs','Резерв заказа FBS'],['fbo','Отправка на маркетплейс FBO']],type);
  html+=selectField('product_id','Товар',data.products.map(p=>[p.id,`${p.name} · ${p.sku}`]),value('product_id',data.products[0]?.id));
  const options=(type==='transfer'?all:active).map(w=>[w.id,w.name+(w.archived?' · удалён':'')]);
  html+=selectField(type==='receipt'?'warehouse_id':'source_id',type==='receipt'?'На какой ФФ':'Откуда · склад ФФ',options,value(type==='receipt'?'warehouse_id':'source_id',formWarehouse||options[0]?.[0]),type==='transfer'?'С удалённого склада разрешён вывоз остатков.':'');
  if(type==='transfer') html+=selectField('destination_id','Куда · склад ФФ',active.map(w=>[w.id,w.name]),value('destination_id',active.find(w=>String(w.id)!==String(value('source_id',formWarehouse||options[0]?.[0])))?.id));
  if(type==='fbo'||type==='fbs') html+=`<label class="field"><span>${type==='fbs'?'Клиент / номер заказа':'Склад маркетплейса'}</span><input name="destination_label" maxlength="100" placeholder="${type==='fbs'?'Например, заказ № 2041':'Например, WB · Коледино'}" value="${esc(value('destination_label'))}"><small>Необязательное поле. Если пусто, используем стандартное название.</small></label>`;
  html+=`<label class="field"><span>Количество, шт.</span><input name="quantity" type="number" min="1" max="1000000" step="1" inputmode="numeric" value="${esc(value('quantity',1))}" required></label><div id="stock-context" class="form-context"></div>`;
  $('#form-fields').innerHTML=html; updateFormContext();
}
function updateFormContext(){
  if(!$('#stock-context'))return;
  const fields=Object.fromEntries(new FormData($('#operation-form')));
  const b=data.stocks.find(s=>s.product_id===Number(fields.product_id)&&s.warehouse_id===Number(fields.source_id||fields.warehouse_id))||{physical:0,available:0,reserved:0};
  const help={receipt:'Приход увеличит физический и доступный остаток.',transfer:'После отправки товар будет в пути до подтверждения приёмки.',fbs:'Резерв уменьшит доступное количество. Физический остаток изменится при отправке.',fbo:'Товар покинет ФФ и будет числиться в пути до приёмки маркетплейсом.'};
  $('#stock-context').textContent=`На выбранном ФФ: ${b.physical} шт. · доступно ${b.available} · резерв ${b.reserved}. ${help[fields.type]}`;
}
function openForm(mode='operation',id=null){
  if(!data){toast('Дождитесь загрузки данных');return;}
  formMode=mode;formWarehouse=id;retryKey='';retrySignature='';$('#form-error').hidden=true;
  renderForm();dialog.showModal();
}
async function submitForm(event){
  event.preventDefault();if(submitting)return;
  const values=Object.fromEntries(new FormData(event.currentTarget));
  let path,method='POST',payload;
  if(formMode==='warehouse'){path='/api/warehouses';payload={name:values.name};}
  else if(formMode==='rename'){path=`/api/warehouses/${formWarehouse}`;method='PATCH';payload={name:values.name};}
  else if(formMode==='archive'){path=`/api/warehouses/${formWarehouse}`;method='DELETE';}
  else if(values.type==='receipt'){path='/api/receipts';payload={product_id:Number(values.product_id),warehouse_id:Number(values.warehouse_id),quantity:Number(values.quantity)};}
  else {path='/api/movements';payload={kind:values.type,product_id:Number(values.product_id),source_id:Number(values.source_id),quantity:Number(values.quantity)};if(values.type==='transfer')payload.destination_id=Number(values.destination_id);else payload.destination_label=values.destination_label;}
  const signature=JSON.stringify([path,method,payload]);if(signature!==retrySignature){retryKey=crypto.randomUUID();retrySignature=signature;}
  submitting=true;$('#submit-operation').disabled=true;$('#form-error').hidden=true;
  try{await api(path,method,payload,retryKey);dialog.close();toast(formMode==='archive'?'Склад удалён в архив. Остатки сохранены.':'Операция проведена');await load();}
  catch(error){$('#form-error').textContent=error.message;$('#form-error').hidden=false;}
  finally{submitting=false;$('#submit-operation').disabled=false;}
}
async function handleTransition(button){
  if(button.disabled)return;button.disabled=true;
  try{await api(`/api/movements/${button.dataset.id}/${button.dataset.action}`,'POST',undefined,crypto.randomUUID());toast('Статус обновлён. Остатки пересчитаны.');await load();}
  catch(error){toast(error.message);button.disabled=false;}
}
function route(){const next=location.hash.slice(1);view=titles[next]?next:'stock';query='';warehouseFilter='';render();}
window.addEventListener('hashchange',route);
$('#refresh').addEventListener('click',()=>load());
$('#new-operation').addEventListener('click',()=>openForm(view==='warehouses'?'warehouse':'operation'));
$('#operation-form').addEventListener('submit',submitForm);
$('#operation-form').addEventListener('change',event=>{
  if(event.target.name==='type'){const values=Object.fromEntries(new FormData($('#operation-form')));renderForm(values);$('#form-error').hidden=true;}
  else updateFormContext();
});
dialog.addEventListener('cancel',event=>{if(submitting)event.preventDefault();});
document.addEventListener('click',event=>{
  const close=event.target.closest('[data-close]');if(close&&!submitting)dialog.close();
  const action=event.target.closest('[data-action]');if(action)handleTransition(action);
  const tab=event.target.closest('[data-movement-filter]');if(tab){movementFilter=tab.dataset.movementFilter;render();}
  const rename=event.target.closest('[data-rename]');if(rename)openForm('rename',Number(rename.dataset.rename));
  const archive=event.target.closest('[data-archive]');if(archive)openForm('archive',Number(archive.dataset.archive));
  const evacuate=event.target.closest('[data-evacuate]');if(evacuate)openForm('evacuate',Number(evacuate.dataset.evacuate));
});
$('#view-root').addEventListener('input',event=>{if(event.target.id==='search'){query=event.target.value;render();}});
$('#view-root').addEventListener('change',event=>{
  if(event.target.id==='warehouse-filter'){warehouseFilter=event.target.value;render();}
  if(event.target.id==='show-archive'){showArchive=event.target.checked;render();}
});
if (window.CheckStockDemo) {
  const resetDialog = $('#demo-reset-dialog');
  $('#reset-demo').addEventListener('click', () => { resetDialog.returnValue = 'cancel'; resetDialog.showModal(); });
  resetDialog.addEventListener('close', async () => {
    if (resetDialog.returnValue !== 'reset') return;
    try { await window.CheckStockDemo.reset(); await load(); toast('Восстановлены исходные демонстрационные данные'); }
    catch (error) { toast(error.message); }
  });
  window.addEventListener('storage', event => { if (event.key === 'checkstock:pages-demo:v1') load(); });
}
route();load({initial:true});
