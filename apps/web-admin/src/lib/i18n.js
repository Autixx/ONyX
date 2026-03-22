// i18n.js — Language, translations, applyI18n, locale refresh

window.LANG = 'en';

var I18N = {
  en: {
    'nav.grp.core':        'Core',
    'nav.grp.policy':      'Policy',
    'nav.grp.operations':  'Operations',
    'nav.grp.visual':      'Visual',
    'nav.system':          'System',
    'nav.nodes':           'Nodes',
    'nav.traffic':         'Node Traffic',
    'nav.links':           'Links',
    'nav.policies':        'Policies',
    'nav.jobs':            'Jobs',
    'nav.peers':           'Peers',
    'nav.xray':            'Xray Services',
    'nav.transit':         'Transit Policies',
    'nav.awg':             'AWG Services',
    'nav.wg':              'WG Services',
    'nav.ovpn':            'OpenVPN+Cloak Services',
    'nav.registrations':   'Registrations',
    'nav.audit':           'Audit / Access',
    'nav.topology':        'Topology',
    'nav.apidebug':        'API Debug',
    'page.registrations':  'Registrations',
    'page.audit':          'Audit / Access',
    'page.topology':       'Topology',
    'reg.filter.all':      'all statuses',
    'reg.filter.pending':  'pending',
    'reg.filter.approved': 'approved',
    'reg.filter.rejected': 'rejected',
    'reg.refresh':         'REFRESH',
    'reg.col.login':       'Login',
    'reg.col.email':       'E-mail',
    'reg.col.date':        'Date',
    'reg.col.refcode':     'Referral Code',
    'reg.col.devices':     'Devices',
    'reg.col.status':      'Status',
    'reg.col.actions':     'Actions',
    'reg.approve':         'APPROVE',
    'reg.reject':          'REJECT',
    'reg.empty':           'No registration requests.',
    'topo.reachable':      'reachable',
    'topo.degraded':       'degraded',
    'topo.unreachable':    'unreachable',
    'topo.unknown':        'unknown',
    'topo.hint':           'click node or link for detail',
    'topo.planpath':       'PLAN PATH',
    'topo.refresh':        'REFRESH',
    'topo.auto':           'LIVE',
    'topo.snapshot':       'Graph Snapshot',
    'topo.pathoverlay':    'Path Overlay',
  },
  ru: {
    'nav.grp.core':        'Основное',
    'nav.grp.policy':      'Политики',
    'nav.grp.operations':  'Операции',
    'nav.grp.visual':      'Визуал',
    'nav.system':          'Система',
    'nav.nodes':           'Узлы',
    'nav.traffic':         'Трафик узлов',
    'nav.links':           'Связи',
    'nav.policies':        'Политики',
    'nav.jobs':            'Задачи',
    'nav.peers':           'Пиры',
    'nav.xray':            'XRAY Сервисы',
    'nav.transit':         'Transit Policies',
    'nav.awg':             'AWG Сервисы',
    'nav.wg':              'WG Сервисы',
    'nav.ovpn':            'OpenVPN+Cloak Сервисы',
    'nav.registrations':   'Регистрации',
    'nav.audit':           'Аудит / Доступ',
    'nav.topology':        'Топология',
    'nav.apidebug':        'API Отладка',
    'page.registrations':  'Регистрации',
    'page.audit':          'Аудит / Доступ',
    'page.topology':       'Топология',
    'reg.filter.all':      'все статусы',
    'reg.filter.pending':  'ожидают',
    'reg.filter.approved': 'одобрены',
    'reg.filter.rejected': 'отклонены',
    'reg.refresh':         'ОБНОВИТЬ',
    'reg.col.login':       'Логин',
    'reg.col.email':       'E-mail',
    'reg.col.date':        'Дата',
    'reg.col.refcode':     'Реф. код',
    'reg.col.devices':     'Устройств',
    'reg.col.status':      'Статус',
    'reg.col.actions':     'Действия',
    'reg.approve':         'ОДОБРИТЬ',
    'reg.reject':          'ОТКЛОНИТЬ',
    'reg.empty':           'Заявок на регистрацию нет.',
    'topo.reachable':      'доступен',
    'topo.degraded':       'деградация',
    'topo.unreachable':    'недоступен',
    'topo.unknown':        'неизвестно',
    'topo.hint':           'клик по узлу или линку — детали',
    'topo.planpath':       'МАРШРУТ',
    'topo.refresh':        'ОБНОВИТЬ',
    'topo.auto':           'LIVE',
    'topo.snapshot':       'Снимок графа',
    'topo.pathoverlay':    'Наложение пути',
  }
};

function t(key){ return (I18N[window.LANG] && I18N[window.LANG][key]) || (I18N.en[key]) || key; }

window.LITERAL_TEXT = {
  ru: {
    'Control Plane Access': 'Доступ к панели управления',
    'Username': 'Имя пользователя',
    'Password': 'Пароль',
    'AUTHENTICATE': 'ВОЙТИ',
    'AUTHENTICATING...': 'ВХОД...',
    'Logout': 'Выйти',
    'control plane': 'панель управления',
    'System': 'Система',
    'Network': 'Сеть',
    'Access Control': 'Управление доступом',
    'Services': 'Сервисы',
    'Topology': 'Топология',
    'Debug': 'Отладка',
    'Nodes': 'Узлы',
    'Node Traffic': 'Трафик узлов',
    'Links': 'Связи',
    'Policies': 'Политики',
    'Transit Policies': 'Политики транзита',
    'Transport Packages': 'Транспортные пакеты',
    'Jobs': 'Задачи',
    'Peers': 'Пиры',
    'Registrations': 'Регистрации',
    'Users': 'Пользователи',
    'Management': 'Управление',
    'Plans': 'Планы',
    'Subscriptions': 'Подписки',
    'Referral Codes': 'Реферальные коды',
    'Devices': 'Устройства',
    'Audit / Access': 'Аудит / доступ',
    'Failban': 'Fail2ban',
    'Fail2Ban': 'Fail2ban',
    'Control Plane': 'Панель',
    'E-Mail': 'E-mail',
    'Support Chat': 'Чат поддержки',
    'XRAY Services': 'XRAY-сервисы',
    'AWG Services': 'AWG-сервисы',
    'WG Services': 'WG-сервисы',
    'OpenVPN+CLOAK Services': 'OpenVPN+Cloak-сервисы',
    'OpenVPN+Cloak Services': 'OpenVPN+Cloak-сервисы',
    'CODE GEN': 'ГЕН КОДОВ',
    'GENERATE POOL': 'СГЕНЕРИРОВАТЬ ПУЛ',
    'Generate': 'Сгенерировать',
    'Generate Pool': 'Сгенерировать пул',
    'Generate Referral Codes': 'Генерация реферальных кодов',
    'Generated Referral Codes': 'Сгенерированные реферальные коды',
    'Length': 'Длина',
    'Quantity': 'Количество',
    'Lifetime days': 'Срок жизни, дни',
    'Codes': 'Коды',
    'Expires': 'Истекает',
    'COPY': 'КОПИРОВАТЬ',
    'Copy': 'Копировать',
    'Route Policy': 'Политика маршрутизации',
    'DNS Policy': 'DNS-политика',
    'DNS Policies': 'DNS-политики',
    'Geo Policy': 'Гео-политика',
    'Geo Policies': 'Гео-политики',
    'Balancer': 'Балансировщик',
    'Balancers': 'Балансировщики',
    'Transit Routing': 'Транзитная маршрутизация',
    'Routing Summary': 'Сводка маршрутизации',
    'API Debug': 'Отладка API',
    'XRAY': 'XRAY',
    'AWG': 'AWG',
    'WG': 'WG',
    'oVPN': 'oVPN',
    'Backend': 'Backend',
    'Worker': 'Worker',
    'Nodes Online': 'Узлы онлайн',
    'Active Links': 'Активные связи',
    'Age': 'Возраст',
    'Lease': 'Лиз',
    'Live Event Stream " WS /api/v1/ws/admin/events': 'Поток событий " WS /api/v1/ws/admin/events',
    'PROBE HEALTH': 'ПРОВЕРИТЬ СОСТОЯНИЕ',
    'all statuses': 'все статусы',
    'reachable': 'доступен',
    'degraded': 'деградация',
    'offline': 'не в сети',
    'unknown': 'неизвестно',
    'all states': 'все состояния',
    'normal': 'норма',
    'warning': 'предупреждение',
    'exceeded': 'превышен',
    'suspended': 'приостановлен',
    'hard enforced': 'жёстко ограничен',
    '+ ADD NODE': '+ ДОБАВИТЬ УЗЕЛ',
    '+ ADD USER': '+ ДОБАВИТЬ ПОЛЬЗОВАТЕЛЯ',
    '+ ADD SUBSCRIPTION': '+ ДОБАВИТЬ ПОДПИСКУ',
    '+ ADD PLAN': '+ ДОБАВИТЬ ПЛАН',
    '+ ADD REFERRAL CODE': '+ ДОБАВИТЬ РЕФЕРАЛЬНЫЙ КОД',
    '+ ADD XRAY SERVICE': '+ ДОБАВИТЬ XRAY-СЕРВИС',
    '+ ADD TRANSIT POLICY': '+ ДОБАВИТЬ ПОЛИТИКУ ТРАНЗИТА',
    '+ ADD AWG SERVICE': '+ ДОБАВИТЬ AWG-СЕРВИС',
    '+ ADD WG SERVICE': '+ ДОБАВИТЬ WG-СЕРВИС',
    '+ ADD OPENVPN+CLOAK SERVICE': '+ ДОБАВИТЬ OPENVPN+CLOAK-СЕРВИС',
    'REFRESH': 'ОБНОВИТЬ',
    'VIEW': 'ОТКРЫТЬ',
    'EDIT': 'ИЗМЕНИТЬ',
    'DELETE': 'УДАЛИТЬ',
    'DEL': 'УДАЛИТЬ',
    'PROBE': 'ПРОВЕРИТЬ',
    'RESET': 'СБРОСИТЬ',
    'ROLLOVER': 'НОВЫЙ ЦИКЛ',
    'REVOKE': 'ОТОЗВАТЬ',
    'PACKAGE': 'ПАКЕТ',
    'RECONCILE': 'СИНХРОНИЗИРОВАТЬ',
    'PREVIEW': 'ПРЕДПРОСМОТР',
    'APPLY': 'ПРИМЕНИТЬ',
    'GUIDE': 'МАСТЕР',
    'RETRY NOW': 'ПОВТОРИТЬ',
    'MARK CANCELLED': 'ПОМЕТИТЬ КАК ОТМЕНЁННУЮ',
    'MARK AS CANCELLED': 'ПОМЕТИТЬ КАК ОТМЕНЁННУЮ',
    'RELEASE TARGET': 'СНЯТЬ БЛОКИРОВКУ ЦЕЛИ',
    'ABORT REMOTE': 'ПРЕРВАТЬ НА УЗЛЕ',
    'PAUSE': 'ПАУЗА',
    'RESUME': 'ПРОДОЛЖИТЬ',
    'SEND': 'ОТПРАВИТЬ',
    'PROBE SSH': 'ПРОВЕРИТЬ SSH',
    'BOOTSTRAP': 'ПОДГОТОВИТЬ',
    'REBOOT': 'ПЕРЕЗАГРУЗИТЬ',
    'FORCE REBOOT': 'ПРИНУДИТЕЛЬНАЯ ПЕРЕЗАГРУЗКА',
    'VALIDATE': 'ПРОВЕРИТЬ',
    'PICK': 'ВЫБРАТЬ',
    'VIEW CONFIG': 'ПОКАЗАТЬ КОНФИГ',
    'OPEN TRANSIT': 'ОТКРЫТЬ ТРАНЗИТ',
    'ATTACH NEXT HOP': 'ПРИВЯЗАТЬ СЛЕДУЮЩИЙ ХОП',
    'CREATE TRANSIT': 'СОЗДАТЬ ТРАНЗИТ',
    'Name': 'Имя',
    'Role': 'Роль',
    'Mgmt Address': 'Mgmt-адрес',
    'Status': 'Статус',
    'State': 'Состояние',
    'Kind': 'Тип',
    'Target': 'Цель',
    'Step': 'Шаг',
    'Error': 'Ошибка',
    'Date': 'Дата',
    'Traffic Used': 'Использовано',
    'Limit': 'Лимит',
    'Capabilities': 'Возможности',
    'Actions': 'Действия',
    'Node': 'Узел',
    'Cycle Start': 'Начало цикла',
    'Cycle End': 'Конец цикла',
    'Used': 'Использовано',
    'Usage': 'Использование',
    'Suspended': 'Приостановлен',
    'Enforced': 'Принудительно',
    'No users.': 'Пользователей нет.',
    'No plans.': 'Планов нет.',
    'No subscriptions.': 'Подписок нет.',
    'No referral codes.': 'Реферальных кодов нет.',
    'No devices.': 'Устройств нет.',
    'No transport packages.': 'Транспортных пакетов нет.',
    'No nodes match the current filter.': 'По текущему фильтру узлы не найдены.',
    'No node traffic entries match the current filter.': 'По текущему фильтру записи трафика не найдены.',
    'all reachable': 'все доступны',
    'all active': 'все активны',
    'total': 'всего',
    'No registration requests.': 'Заявок на регистрацию нет.',
    'lifetime': 'бессрочно',
    'pending': 'ожидает',
    'approved': 'одобрен',
    'rejected': 'отклонён',
    'active': 'активен',
    'deleted': 'удалён',
    'cancelled': 'отменён',
    'running': 'выполняется',
    'succeeded': 'успешно',
    'failed': 'ошибка',
    'dead': 'провал',
    'No account?': 'Нет аккаунта?',
    'Request access': 'Запросить доступ'
  }
};

window.PLACEHOLDER_TEXT = {
  ru: {
    'search nodes': 'поиск узлов',
    'search node traffic': 'поиск трафика узлов',
    'search links': 'поиск связей',
    'search peers...': 'поиск пиров...',
    '// JSON request body (for POST / PUT)': '// JSON-тело запроса (для POST / PUT)'
  }
};

window.uiLiteral = function uiLiteral(text){
  var base = String(text || '');
  return (window.LITERAL_TEXT[window.LANG] && window.LITERAL_TEXT[window.LANG][base]) || base;
};

window.uiPlaceholder = function uiPlaceholder(text){
  var base = String(text || '');
  return (window.PLACEHOLDER_TEXT[window.LANG] && window.PLACEHOLDER_TEXT[window.LANG][base]) || base;
};

window.applyLiteralTranslations = function applyLiteralTranslations(root){
  var scope = root || document.body;
  if(!scope) return;
  var dynamicIdSkip = {
    sb:true, sw:true, sn:true, snSub:true, sl:true, slSub:true,
    sysCpu:true, sysRam:true, wsl:true, ubtn:true, lerr:true, topoZoomLabel:true, dpt:true,
    'failban-scope-line':true
  };
  scope.querySelectorAll('*').forEach(function(el){
    if(el.hasAttribute('data-i18n')) return;
    if(el.id && dynamicIdSkip[el.id]) return;
    if(el.placeholder != null){
      if(!el.dataset.i18nOriginalPlaceholder) el.dataset.i18nOriginalPlaceholder = el.placeholder;
      el.placeholder = window.LANG === 'en' ? el.dataset.i18nOriginalPlaceholder : window.uiPlaceholder(el.dataset.i18nOriginalPlaceholder);
    }
    if(el.title){
      if(!el.dataset.i18nOriginalTitle) el.dataset.i18nOriginalTitle = el.title;
      el.title = window.LANG === 'en' ? el.dataset.i18nOriginalTitle : window.uiLiteral(el.dataset.i18nOriginalTitle);
    }
    if(el.children.length === 0){
      var raw = el.textContent;
      var trimmed = raw.trim();
      if(!trimmed) return;
      if(!el.dataset.i18nOriginalText) el.dataset.i18nOriginalText = trimmed;
      var original = el.dataset.i18nOriginalText;
      var translated = window.LANG === 'en' ? original : window.uiLiteral(original);
      if(translated !== trimmed){
        el.textContent = raw.replace(trimmed, translated);
      }
    }
  });
};

window.rerenderLocalizedViews = function rerenderLocalizedViews(){
  window.renderNodes?.();
  window.renderNodeTraffic?.();
  window.renderLinks?.();
  window.renderPolicies?.();
  window.renderJobs?.();
  window.renderAudit?.();
  window.renderElog?.();
  window.renderPeers?.();
  window.renderXrayServices?.();
  window.renderTransitPolicies?.();
  window.renderAwgServices?.();
  window.renderWgServices?.();
  window.renderOpenvpnCloakServices?.();
  window.renderRegistrations?.();
  window.renderUsers?.();
  window.renderPlans?.();
  window.renderSubscriptions?.();
  window.renderReferralCodes?.();
  window.renderDevices?.();
  window.renderTransportPackages?.();
  window.renderTopologyMeta?.();
};

var _localeRefreshScheduled = false;
window.scheduleLocaleRefresh = function scheduleLocaleRefresh(){
  if(_localeRefreshScheduled) return;
  _localeRefreshScheduled = true;
  setTimeout(function(){
    _localeRefreshScheduled = false;
    window.applyLiteralTranslations(document.body);
  }, 0);
};

window.applyI18n = function applyI18n(){
  document.documentElement.lang = window.LANG;
  document.querySelectorAll('[data-i18n]').forEach(function(el){
    var key = el.getAttribute('data-i18n');
    if(el.tagName === 'OPTION'){
      el.textContent = t(key);
    } else if(el.tagName === 'BUTTON' && !el.hasAttribute('data-i18n-keep')){
      el.textContent = t(key);
    } else {
      el.textContent = t(key);
    }
  });
  window.rerenderLocalizedViews();
  window.scheduleLocaleRefresh();
};

window.setLang = function setLang(lang){
  window.LANG = lang;
  try{ localStorage.setItem('onyx-lang', lang); }catch(e){}
  document.querySelectorAll('.lang-btn').forEach(function(b){
    b.classList.toggle('active', b.textContent.trim().toLowerCase() === lang);
  });
  window.applyI18n();
};

export var setLang   = window.setLang;
export var applyI18n = window.applyI18n;
