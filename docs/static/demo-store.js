/* Browser-only demo for GitHub Pages. The authoritative server is app/service.py. */
(function (root, factory) {
  const exports = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = exports;
  else root.CheckStockDemo = exports.createDemoStore({
    getItem: key => root.localStorage.getItem(key),
    setItem: (key, value) => root.localStorage.setItem(key, value),
    locks: root.navigator.locks,
    uuid: () => root.crypto.randomUUID(),
  });
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  const KEY = 'checkstock:pages-demo:v1';
  const clone = value => JSON.parse(JSON.stringify(value));
  const canonical = value => JSON.stringify(value, (_, v) => v && typeof v === 'object' && !Array.isArray(v)
    ? Object.keys(v).sort().reduce((out, key) => { out[key] = v[key]; return out; }, {}) : v);

  function createDemoStore(options) {
    let queue = Promise.resolve();
    const now = options.now || (() => new Date().toISOString());
    const uuid = options.uuid;
    function fail(message) { throw new Error(message); }
    function fresh() {
      const state = {
        version: 1, store: 'Ракета · демомагазин', nextWarehouse: 3, nextEvent: 1, idempotency: {},
        products: [{id:1,sku:'SKU-101',name:'Органайзер'},{id:2,sku:'SKU-102',name:'Контейнер'},{id:3,sku:'SKU-103',name:'Корзина'}],
        warehouses: [{id:1,name:'Север',archived:false},{id:2,name:'Юг',archived:false}], stocks: [], movements: [], events: [],
      };
      for (const [product_id, quantities] of [[1,[10,6]],[2,[5,0]],[3,[0,4]]]) {
        quantities.forEach((quantity, index) => {
          const warehouse_id = index + 1;
          state.stocks.push({product_id, warehouse_id, physical:quantity, reserved:0});
          if (quantity) event(state, 'receipt', {product_id, quantity, destination_id:warehouse_id, physical_delta:quantity});
        });
      }
      return state;
    }
    function warehouse(state, id, active = false) {
      const w = state.warehouses.find(w => w.id === id);
      if (!w) fail('Склад не найден');
      if (active && w.archived) fail('Склад удалён. Можно вывезти остаток или завершить старые операции.');
      return w;
    }
    function product(state, id) {
      const p = state.products.find(p => p.id === id);
      if (!p) fail('Товар не найден');
      return p;
    }
    function balance(state, product_id, warehouse_id) {
      let b = state.stocks.find(b => b.product_id === product_id && b.warehouse_id === warehouse_id);
      if (!b) { b = {product_id, warehouse_id, physical:0, reserved:0}; state.stocks.push(b); }
      return b;
    }
    function event(state, action, data = {}) {
      const source = data.source_id ? warehouse(state, data.source_id).name : action === 'receipt' ? 'Поставщик' : '';
      const destination = data.destination_id ? warehouse(state, data.destination_id).name : data.destination_label || '';
      state.events.unshift({id:state.nextEvent++, action, product_id:null, quantity:0, source_id:null,
        destination_id:null, movement_id:null, physical_delta:0, reserved_delta:0, note:'', ...data,
        source_label:source, destination_label:destination, created_at:now()});
    }
    function validate(state) {
      if (state.version !== 1 || !Array.isArray(state.stocks) || !Array.isArray(state.movements)
          || !Array.isArray(state.products) || !Array.isArray(state.warehouses) || !Array.isArray(state.events))
        fail('Сохранённая демоверсия несовместима. Нажмите «Сбросить демо».');
      const pairs = new Set();
      for (const b of state.stocks) {
        if (![b.physical,b.reserved].every(Number.isSafeInteger) || b.reserved < 0 || b.physical < b.reserved)
          fail('Нарушен учёт демоверсии. Нажмите «Сбросить демо».');
        const key = `${b.product_id}:${b.warehouse_id}`;
        if (pairs.has(key)) fail('Найдены дубли остатков. Нажмите «Сбросить демо».');
        pairs.add(key);
        product(state,b.product_id); warehouse(state,b.warehouse_id);
        const reserved = state.movements.filter(m => m.product_id === b.product_id && m.source_id === b.warehouse_id && m.status === 'reserved').reduce((n,m) => n+m.quantity,0);
        if (reserved !== b.reserved) fail('Резервы демоверсии не сходятся. Нажмите «Сбросить демо».');
      }
      for (const p of state.products) {
        const incoming = state.events.filter(e => e.action === 'receipt' && e.product_id === p.id).reduce((n,e) => n+e.quantity,0);
        const physical = state.stocks.filter(b => b.product_id === p.id).reduce((n,b) => n+b.physical,0);
        const external = state.movements.filter(m => m.product_id === p.id && (m.status === 'transit' || (m.status === 'completed' && m.kind !== 'transfer'))).reduce((n,m) => n+m.quantity,0);
        if (incoming !== physical+external) fail('Общее количество демоверсии не сходится. Нажмите «Сбросить демо».');
      }
      return state;
    }
    function read() {
      let raw;
      try { raw = options.getItem(KEY); }
      catch { fail('Браузер запретил локальное сохранение. Разрешите данные сайта и обновите страницу.'); }
      if (!raw) return fresh();
      try { return validate(JSON.parse(raw)); }
      catch (error) { fail(error instanceof SyntaxError ? 'Демоданные повреждены. Нажмите «Сбросить демо».' : error.message); }
    }
    function save(state) {
      validate(state);
      try { options.setItem(KEY, JSON.stringify(state)); }
      catch { fail('Не удалось сохранить демоданные. Проверьте свободное место и разрешения браузера.'); }
    }
    function exclusive(fn) {
      const task = () => options.locks ? options.locks.request(KEY, fn) : fn();
      const pending = queue.then(task, task);
      queue = pending.catch(() => {});
      return pending;
    }
    function positive(value) {
      if (!Number.isSafeInteger(value) || value < 1 || value > 1000000) fail('Количество и идентификаторы должны быть целыми числами от 1 до 1 000 000.');
      return value;
    }
    function requireAvailable(state, b, quantity) {
      const available = b.physical-b.reserved;
      if (quantity <= available) return;
      const alternatives = state.stocks.filter(s => s.product_id === b.product_id && s.warehouse_id !== b.warehouse_id && s.physical > s.reserved)
        .map(s => `${warehouse(state,s.warehouse_id).name}${warehouse(state,s.warehouse_id).archived ? ' (удалён)' : ''} — ${s.physical-s.reserved} шт.`);
      fail(`На выбранном ФФ доступно ${available} шт., требуется ${quantity}. Выберите другой склад или сначала оформите перемещение.${alternatives.length ? ' На других складах: '+alternatives.join('; ') : ''}`);
    }
    function snapshot(state) {
      const result = clone(state);
      result.stocks = result.stocks.map(b => ({...b, available:b.physical-b.reserved}));
      delete result.idempotency; delete result.version; delete result.nextEvent; delete result.nextWarehouse;
      return result;
    }
    function apply(state, path, method, body) {
      let match;
      if (path === '/api/warehouses' || ((match = path.match(/^\/api\/warehouses\/(\d+)$/)) && ['PATCH','DELETE'].includes(method))) {
        if (path === '/api/warehouses' && method !== 'POST') fail('Действие недоступно');
        const w = match ? warehouse(state,Number(match[1]),method === 'PATCH') : null;
        if (method === 'DELETE') {
          if (!w.archived) {w.archived = true; event(state,'warehouse_archived',{source_id:w.id,note:'Склад удалён из активных; товар и история сохранены'});}
          return {id:w.id,archived:true};
        }
        const name = typeof body.name === 'string' ? body.name.trim() : '';
        if (!name || name.length > 80) fail('Укажите название склада: от 1 до 80 символов.');
        if (state.warehouses.some(x => !x.archived && x.id !== w?.id && x.name === name)) fail('Действующий склад с таким названием уже существует');
        if (w) {const old=w.name;w.name=name;event(state,'warehouse_renamed',{destination_id:w.id,note:`${old} → ${name}`});return {id:w.id,name};}
        const item = {id:state.nextWarehouse++,name,archived:false};state.warehouses.push(item);
        event(state,'warehouse_created',{destination_id:item.id,note:'Создан склад'});return {id:item.id,name};
      }
      if (path === '/api/receipts' && method === 'POST') {
        product(state,positive(body.product_id)); warehouse(state,positive(body.warehouse_id),true);
        const q = positive(body.quantity), b = balance(state,body.product_id,body.warehouse_id);b.physical += q;
        event(state,'receipt',{product_id:body.product_id,quantity:q,destination_id:body.warehouse_id,physical_delta:q});
        return {warehouse_id:body.warehouse_id,product_id:body.product_id,physical:b.physical,reserved:b.reserved};
      }
      if (path === '/api/movements' && method === 'POST') {
        if (!['transfer','fbs','fbo'].includes(body.kind)) fail('Неизвестный тип движения');
        product(state,positive(body.product_id)); warehouse(state,positive(body.source_id),body.kind !== 'transfer');
        const q = positive(body.quantity);let destination=null;
        if (body.kind === 'transfer') {
          if (!body.destination_id || body.destination_id === body.source_id) fail('Выберите другой склад назначения');
          destination=warehouse(state,positive(body.destination_id),true);
        } else if (body.destination_id != null) fail('Для FBS/FBO укажите получателя, а не склад ФФ');
        const b=balance(state,body.product_id,body.source_id);requireAvailable(state,b,q);
        if (body.destination_label != null && (typeof body.destination_label !== 'string' || body.destination_label.length > 100)) fail('Название получателя: не более 100 символов.');
        const m={id:uuid(),kind:body.kind,status:body.kind === 'fbs'?'reserved':'transit',product_id:body.product_id,
          source_id:body.source_id,destination_id:destination?.id || null,
          destination_label:destination?.name || body.destination_label?.trim() || (body.kind === 'fbs'?'Клиент FBS':'Маркетплейс FBO'),quantity:q,created_at:now()};
        state.movements.unshift(m);
        if (m.kind === 'fbs') b.reserved += q; else b.physical -= q;
        event(state,m.kind === 'fbs'?'fbs_reserved':`${m.kind}_sent`,{product_id:m.product_id,quantity:q,source_id:m.source_id,
          destination_id:m.destination_id,destination_label:m.destination_label,movement_id:m.id,
          physical_delta:m.kind === 'fbs'?0:-q,reserved_delta:m.kind === 'fbs'?q:0});
        return {id:m.id,status:m.status};
      }
      match=path.match(/^\/api\/movements\/([^/]+)\/(send|receive|cancel)$/);
      if (match && method === 'POST') {
        const m=state.movements.find(m => m.id === match[1]);if(!m)fail('Операция не найдена');
        const action=match[2],q=m.quantity,b=balance(state,m.product_id,m.source_id);
        if ((action === 'send' && m.kind === 'fbs' && ['transit','completed'].includes(m.status)) || (action === 'receive' && m.status === 'completed') || (action === 'cancel' && m.status === 'cancelled')) return {id:m.id,status:m.status,repeated:true};
        let name,physical_delta=0,reserved_delta=0;
        if (action === 'send' && m.kind === 'fbs' && m.status === 'reserved') {
          b.physical-=q;b.reserved-=q;physical_delta=reserved_delta=-q;m.status='transit';name='fbs_sent';
        } else if (action === 'cancel' && m.kind === 'fbs' && m.status === 'reserved') {
          b.reserved-=q;reserved_delta=-q;m.status='cancelled';name='fbs_cancelled';
        } else if (action === 'receive' && m.status === 'transit') {
          if (m.kind === 'transfer') {balance(state,m.product_id,m.destination_id).physical+=q;physical_delta=q;}
          m.status='completed';name=`${m.kind}_received`;
        } else fail('Действие недоступно для текущего статуса операции');
        event(state,name,{product_id:m.product_id,quantity:q,source_id:m.source_id,destination_id:m.destination_id,
          destination_label:m.destination_label,movement_id:m.id,physical_delta,reserved_delta});
        return {id:m.id,status:m.status};
      }
      fail('Неизвестная команда демоверсии');
    }
    return {
      request(path, method = 'GET', body = {}, key) {
        return exclusive(() => {
          const state=read();
          if (path === '/api/snapshot' && method === 'GET') {save(state);return snapshot(state);}
          if (typeof key !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(key)) fail('Для изменения нужен уникальный ключ команды.');
          const fingerprint=canonical([method,path,body]);
          if (state.idempotency[key]) {
            if (state.idempotency[key].fingerprint !== fingerprint) fail('Этот ключ уже использован для другой команды.');
            return clone(state.idempotency[key].response);
          }
          const result=apply(state,path,method,body || {});
          state.idempotency[key]={fingerprint,response:clone(result)};save(state);return clone(result);
        });
      },
      reset() {return exclusive(() => {save(fresh());});},
    };
  }
  return {createDemoStore};
});
