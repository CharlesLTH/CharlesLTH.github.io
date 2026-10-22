import { createDataClient } from './data-client.mjs';
import { renderHome } from './home.mjs';
import { prepareWeapons, renderWeaponBrowser } from './weapon-browser.mjs';
import { prepareArmor, renderArmorBrowser, groupArmorPieces, renderArmorTable } from './armor-browser.mjs';
import { questFilterState, questGroupHub, renderQuestFilters } from './quest-browser.mjs';
import { kinds, weaponTypes, ranks, recipeNames, icon, esc, num, percent, route, refLink, badge, empty, table, sharpness, elements, slots } from './ui.mjs';

const api = createDataClient({ baseUrl: new URL('./data/v1/', document.baseURI).href });
const $ = selector => document.querySelector(selector);
const localAsset = source => { const path = new URL(source).pathname.split('/games/mhxx/')[1]; return path?.startsWith('images/') ? new URL('./assets/' + path, document.baseURI).href : source; };
const page = $('#page');
const searchInput = $('#search');
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const relationCache = new Map();
let manifest, currentEntity, navigationEpoch = 0, workerId = 0, searchTimer, toastTimer, previewTimer;
let lastList = '#home';
let homePromise;
const weaponCatalogs = new Map();
const collapsedWeapons = new Set();
let weaponViewKey = '';
let armorCatalog, armorViewKey = '';
const toggledArmor = new Set();
let currentRoute = {};
let saved = readStorage('mhxx.saved.v1', []).filter(id => typeof id === 'string' && /^[a-z]+:site-\d+$/.test(id));
let recent = readStorage('mhxx.recent.v1', []).filter(e => e && typeof e.id === 'string' && typeof e.name === 'string');

function readStorage(key, fallback) { try { const value = JSON.parse(localStorage.getItem(key)); return Array.isArray(value) ? value : fallback; } catch { return fallback; } }
function persist(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch { toast('浏览器未允许保存，当前会话内仍可使用。'); return false; } }
function toast(message) { clearTimeout(toastTimer); $('#toast').textContent = message; $('#toast').classList.add('visible'); toastTimer = setTimeout(() => $('#toast').classList.remove('visible'), 2300); }
function readRoute() { return Object.fromEntries(new URLSearchParams(location.hash.slice(1))); }
function isHome(r) { return !r.id && !r.kind && !r.q && !r.saved; }
function homeData() {
  if (!homePromise) homePromise = fetch(new URL('./home-data.json', document.baseURI)).then(response => {
    if (!response.ok) throw new Error('首页目录读取失败，请刷新重试。');
    return response.json();
  }).then(data => {
    if (data.dataset_revision !== manifest.dataset_revision) throw new Error('资料已经更新，请刷新页面后继续。');
    return data;
  }).catch(error => { homePromise = undefined; throw error; });
  return homePromise;
}
function navigate(values, replace = false) { const hash = typeof values === 'string' ? values : route(values); if (replace) { history.replaceState(null, '', hash); renderRoute(); } else if (location.hash === hash) renderRoute(); else location.hash = hash; }
function setPage(html, epoch) {
  if (epoch !== navigationEpoch) return;
  const focused = document.activeElement;
  const focusInPage = page.contains(focused);
  const levelFocus = focused?.dataset?.level;
  const selectFocus = focused?.dataset?.routeSelect;
  page.innerHTML = html;
  if (focusInPage) {
    const target = levelFocus ? page.querySelector(`[data-level="${Number(levelFocus)}"]`) : selectFocus ? page.querySelector(`[data-route-select="${selectFocus}"]`) : $('#content');
    target?.focus({ preventScroll: true });
  }
  page.classList.remove('page-enter');
  requestAnimationFrame(() => page.classList.add('page-enter'));
}
function savedButton(id, large = false) { return `<button class="${large ? 'button' : 'icon-button'} ${saved.includes(id) ? (large ? 'selected' : 'saved') : ''}" data-save="${esc(id)}" aria-pressed="${saved.includes(id)}" aria-label="${saved.includes(id) ? '取消收藏' : '收藏'}" title="${saved.includes(id) ? '取消收藏' : '收藏'}">${icon('bookmark')}${large ? `<span>${saved.includes(id) ? '已收藏' : '收藏'}</span>` : ''}</button>`; }
function renderNav() {
  $('#navigation').innerHTML = `<a class="nav-link ${isHome(currentRoute) ? 'active' : ''}" href="#home">${icon('home')}<span>资料首页</span></a><div class="nav-divider"></div><p class="nav-label">资料索引</p>${Object.entries(kinds).map(([kind, name]) => `<a class="nav-link ${!currentRoute.saved && (currentRoute.id?.split(':')[0] || currentRoute.kind) === kind ? 'active' : ''}" href="${route({ kind })}">${icon(kind)}<span>${name}</span><span class="nav-count">${num(manifest?.entity_counts[kind])}</span></a>`).join('')}<div class="nav-divider"></div><p class="nav-label">我的资料</p><a href="#saved=1" class="nav-link ${currentRoute.saved ? 'active' : ''}">${icon('bookmark')}<span>收藏夹</span><span class="nav-count">${saved.length}</span></a>`;
}
function skeleton() { return `<div class="page-heading"><div class="skeleton" style="width:140px;height:22px"></div></div><div class="panel" role="status" aria-label="正在加载资料">${Array.from({ length: 8 }, () => '<div class="skeleton-row"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div>').join('')}</div>`; }
function pagination(total, current, size, values, pageKey = 'page') {
  const pages = Math.max(1, Math.ceil(total / size));
  return `<div class="pagination"><button class="button" data-go="${esc(route({ ...values, [pageKey]: current - 1 }))}" ${current <= 1 ? 'disabled' : ''} aria-label="上一页">${icon('back')}</button><span class="current-page">${current} <span class="muted">/ ${pages}</span></span><button class="button" data-go="${esc(route({ ...values, [pageKey]: current + 1 }))}" ${current >= pages ? 'disabled' : ''} aria-label="下一页">${icon('arrow')}</button></div>`;
}

// Search preparation and filtering run outside the rendering thread. Browsers
// without module workers keep the same behavior through an in-thread fallback.
const pendingSearch = new Map();
let worker, fallbackIndex;
try {
  worker = new Worker(new URL('./search-worker.mjs', import.meta.url), { type: 'module' });
  worker.onmessage = ({ data }) => { const pending = pendingSearch.get(data.id); if (!pending) return; pendingSearch.delete(data.id); data.error ? pending.reject(new Error(data.error)) : pending.resolve(data.result); };
  worker.onerror = () => { worker?.terminate(); worker = null; for (const p of pendingSearch.values()) localSearch(p.query).then(p.resolve, p.reject); pendingSearch.clear(); };
} catch { worker = null; }
async function localSearch(query) {
  const { prepareIndex, queryIndex } = await import('./search-core.mjs');
  if (!fallbackIndex) fallbackIndex = fetch(new URL('./browse-index.json', document.baseURI)).then(r => { if (!r.ok) throw new Error('索引读取失败'); return r.json(); }).then(d => ({ revision: d.dataset_revision, entries: prepareIndex(d.items) })).catch(error => { fallbackIndex = undefined; throw error; });
  const index = await fallbackIndex;
  return { ...queryIndex(index.entries, query), revision: index.revision };
}
function search(query) { if (!worker) return localSearch(query); return new Promise((resolve, reject) => { const id = ++workerId; pendingSearch.set(id, { resolve, reject, query }); worker.postMessage({ id, query }); }); }

async function renderWeaponBrowse(r, epoch) {
  const type = Object.hasOwn(weaponTypes, r.wtype) ? r.wtype : 'Great Sword';
  const viewKey = JSON.stringify([type, r.mode, r.wq, r.element, r.focus]);
  if (viewKey !== weaponViewKey) { collapsedWeapons.clear(); weaponViewKey = viewKey; }
  if (!weaponCatalogs.has(type)) {
    const name = type.toLowerCase().replaceAll(' ', '-');
    weaponCatalogs.set(type, fetch(new URL(`./weapon-catalogs/${name}.json`, document.baseURI)).then(response => {
      if (!response.ok) throw new Error('武器派生数据读取失败，请刷新重试。');
      return response.json();
    }).then(data => {
      if (data.dataset_revision !== manifest.dataset_revision) throw new Error('武器资料已经更新，请刷新页面后继续。');
      return prepareWeapons(data);
    }).catch(error => { weaponCatalogs.delete(type); throw error; }));
  }
  const model = await weaponCatalogs.get(type);
  if (epoch !== navigationEpoch) return;
  document.title = `${weaponTypes[type]}派生 · MHXX 资料库`;
  setPage(renderWeaponBrowser(model, r, collapsedWeapons, savedButton), epoch);
}

async function renderArmorBrowse(r, epoch) {
  const viewKey = JSON.stringify([r.group, r.aq, r.atype, r.view]);
  if (viewKey !== armorViewKey) { toggledArmor.clear(); armorViewKey = viewKey; }
  if (!armorCatalog) armorCatalog = fetch(new URL('./armor-catalog.json', document.baseURI)).then(response => {
    if (!response.ok) throw new Error('防具目录读取失败，请刷新重试。');
    return response.json();
  }).then(data => {
    if (data.dataset_revision !== manifest.dataset_revision) throw new Error('防具资料已经更新，请刷新页面后继续。');
    return prepareArmor(data);
  }).catch(error => { armorCatalog = undefined; throw error; });
  const model = await armorCatalog;
  if (epoch !== navigationEpoch) return;
  document.title = '防具一览 · MHXX 资料库';
  setPage(renderArmorBrowser(model, r, toggledArmor, savedButton), epoch);
}

async function renderBrowse(r, epoch) {
  const kind = r.kind || (r.q || r.saved ? '' : 'weapon');
  if (kind === 'weapon' && !r.q && !r.saved) return renderWeaponBrowse(r, epoch);
  if (kind === 'armor' && !r.q && !r.saved) return renderArmorBrowse(r, epoch);
  const navigation = kind === 'quest' || r.group ? await homeData() : null;
  const group = r.group ? navigation.categories[r.group] : null;
  if (r.group && (!group || group.kind !== kind)) throw new Error('这个分类不存在，请从资料首页重新选择。');
  const questFilters = kind === 'quest' ? questFilterState(r, navigation) : {};
  const result = await search({ query: r.q || '', kind, group: r.group || '', weaponType: r.wtype || '', questHub: questFilters.hub, questFlag: questFilters.flag, questType: questFilters.type, saved: r.saved ? saved : undefined, page: r.page || 1, sort: r.sort || 'default' });
  if (result.revision !== manifest.dataset_revision) throw new Error('资料已经更新，请刷新页面后继续。');
  const title = r.saved ? '收藏夹' : r.q ? '搜索结果' : group?.label || kinds[kind] || '全部资料';
  document.title = `${title} · MHXX 资料库`;
  const subtitle = r.q ? `“${r.q}” · 找到 ${num(result.total)} 条资料` : r.saved ? '收藏常用的装备和素材，随时接着查。' : kind === 'weapon' ? '查看各等级性能、生产配方与强化所需素材。' : `浏览${kinds[kind] || '全部'}资料，点击名称查看详情与关联记录。`;
  const filters = r.q || r.saved ? `<div class="filter-chips"><a class="filter-chip ${!kind ? 'active' : ''}" href="${route({ ...r, kind: '', group: '', page: '' })}">全部<small>${num(Object.values(result.counts).reduce((a, b) => a + b, 0))}</small></a>${Object.entries(kinds).map(([k, v]) => `<a class="filter-chip ${kind === k ? 'active' : ''}" href="${route({ ...r, kind: k, group: '', page: '', wtype: '' })}">${v}<small>${result.counts[k]}</small></a>`).join('')}</div>` : kind === 'weapon' ? `<div class="filter-chips"><a class="filter-chip ${!r.wtype ? 'active' : ''}" href="${route({ ...r, kind, wtype: '', page: '' })}">全部武器</a>${Object.entries(weaponTypes).map(([k, v]) => `<a class="filter-chip ${r.wtype === k ? 'active' : ''}" href="${route({ ...r, kind, wtype: k, page: '' })}">${v}</a>`).join('')}</div>` : '';
  const rows = result.items.map(e => [
    `<div class="record-name"><span class="record-symbol">${icon(e.kind)}</span><div><a href="${route({ id: e.id })}" data-preview="${esc(e.id)}">${esc(e.name)}</a><div class="record-subtitle">${esc(e.subtitle || kinds[e.kind])}</div></div></div>`,
    `<div class="catalog-info">${e.kind === 'weapon' ? `<span>攻击 ${num(e.attack_min)} → ${num(e.attack_max)}</span>${badge(`${e.level_count} 个等级`)}${sharpness(e.sharpness)}` : `<span>${esc(e.summary || '—')}</span>${badge(kinds[e.kind])}${e.extra ? `<small>${esc(e.extra)}</small>` : ''}`}</div>`,
    savedButton(e.id),
  ]);
  setPage(`${group ? `<div class="breadcrumb"><a href="#home">资料首页</a>${icon('arrow')}<a href="${route({ kind })}">${kinds[kind]}</a>${icon('arrow')}<span>${esc(group.label)}</span></div>` : ''}<div class="page-heading"><div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><span class="badge green">MHXX</span></div>${filters ? `<div class="filter-row">${filters}</div>` : ''}${kind === 'quest' ? renderQuestFilters(r, navigation) : ''}<section class="panel" aria-label="资料列表"><div class="catalog-subhead"><div><strong>${kind === 'weapon' ? esc(weaponTypes[r.wtype] || '全部武器路线') : esc(title)}</strong><span class="muted">${num(result.total)} 条</span></div><select class="select" data-route-select="sort" aria-label="排序方式"><option value="default" ${!r.sort || r.sort === 'default' ? 'selected' : ''}>默认排序</option><option value="name" ${r.sort === 'name' ? 'selected' : ''}>名称排序</option>${kind === 'weapon' ? `<option value="attack" ${r.sort === 'attack' ? 'selected' : ''}>最高攻击力</option>` : ''}</select></div>${rows.length ? table(['名称', '概览 / 性能', '<span class="sr-only">收藏</span>'], rows, 'catalog-table') : empty(r.saved ? '还没有符合条件的收藏' : '没有找到相关资料', r.saved ? '点击资料旁的书签图标，即可保存在这个浏览器中。' : '试试更短的名称，或切换到“全部”分类。')}<div class="catalog-footer"><span>${result.total ? `${(result.page - 1) * result.pageSize + 1}–${Math.min(result.page * result.pageSize, result.total)} / ${num(result.total)} 条` : '0 条记录'}</span>${pagination(result.total, result.page, result.pageSize, { ...r, kind })}</div></section>${r.saved ? '<p class="notes" style="margin-top:14px">收藏仅保存在当前浏览器，不会上传。</p>' : ''}`, epoch);
}

function header(entity, subtitle = '') {
  return `<div class="breadcrumb"><a href="${lastList}">资料索引</a>${icon('arrow')}<a href="${route({ kind: entity.kind, wtype: entity.kind === 'weapon' ? entity.data.weapon_type : undefined })}">${kinds[entity.kind]}</a>${icon('arrow')}<span>${esc(entity.name)}</span></div><div class="page-heading"><div><h1>${esc(entity.name)}</h1><p>${esc(subtitle || kinds[entity.kind])}</p></div><div class="heading-actions"><a class="button mobile-back" href="${lastList}" aria-label="返回列表">${icon('back')}</a>${savedButton(entity.id, true)}<button class="button" data-copy aria-label="复制当前资料链接">${icon('copy')}<span>复制链接</span></button></div></div>`;
}
function recentPanel(entity) { const items = recent.filter(e => e.id !== entity.id).slice(0, 4); return items.length ? `<section class="panel"><div class="panel-heading"><h2>最近浏览</h2></div><div class="panel-body pinned-list">${items.map(e => `<a href="${route({ id: e.id })}">${icon(e.kind)}${esc(e.name)}</a>`).join('')}</div></section>` : ''; }
function notes(data, title = '数据说明') { return data.notes?.length ? `<details class="panel source-details"><summary>${icon('info')}${esc(title)}</summary><div class="panel-body">${data.notes.map(n => `<p>${esc(n.text)}</p>`).join('')}</div></details>` : ''; }
function recipeCard(recipe, title) {
  const difference = recipe.cost_comparison && recipe.cost_comparison.mhgu_stored_zenny !== recipe.money;
  return `<section class="panel"><div class="panel-heading"><h2>${esc(title || recipeNames[recipe.kind] || recipe.kind || '所需素材')}</h2>${badge('所需素材')}</div><div class="panel-body"><div class="recipe-list">${(recipe.ingredients || []).map(i => `<div class="material-row">${refLink(i.item, i.item?.name || i.label)}<span class="qty">× ${num(i.quantity)}</span></div>`).join('')}${(recipe.material_points || []).map(i => `<div class="material-row"><span>${esc(i.label)}</span><span class="qty">${num(i.points)} 点</span></div>`).join('')}${!(recipe.ingredients?.length || recipe.material_points?.length) ? '<p class="notes">暂无具体素材记录。</p>' : ''}</div><div class="recipe-cost"><span>所需费用</span><strong>${num(recipe.money)} <span class="unit">z</span></strong></div>${difference ? `<div class="notice">费用数值待核对。</div>` : ''}${recipe.unparsed?.length ? `<p class="notes" style="margin-top:10px">${esc(recipe.unparsed.join(' / '))}</p>` : ''}</div></section>`;
}

function renderWeapon(entity, r, epoch) {
  const data = entity.data;
  const level = data.levels.find(l => l.level === Number(r.level)) || data.levels[0];
  const stats = `<div class="stats"><div class="stat"><span>攻击力</span><strong>${num(level.attack)}</strong></div><div class="stat"><span>会心率</span><strong>${esc(level.affinity ?? '—')}<span class="unit">%</span></strong></div><div class="stat"><span>属性</span>${elements(level)}</div><div class="stat"><span>孔槽</span>${slots(level.slots)}</div></div>`;
  const sharp = level.sharpness_px?.length ? `<div class="panel-body" style="border-top:1px solid var(--line)">${level.sharpness_px.map((s, i) => `<div class="sharpness-line"><span>${['基础斩味', '匠 +1', '匠 +2'][i]}</span>${sharpness(s)}</div>`).join('')}</div>` : '';
  const performance = level.performance?.slice(1).filter(Boolean).join(' / ');
  const rows = data.levels.map(l => [`<button data-level="${l.level}" aria-label="选择 ${esc(l.name)} LV ${l.level}" ${l.level === level.level ? 'aria-current="true"' : ''}>${esc(l.name)}<small>Lv ${l.level}</small></button>`, num(l.attack), `<div class="weapon-performance"><span class="weapon-affinity">会心 ${esc(l.affinity ?? '—')}%</span>${elements(l)}${l.defense ? `<small>防御 +${num(l.defense)}</small>` : ''}</div>`, sharpness(l.sharpness_px?.[0]), slots(l.slots)]);
  const derivation = `<section class="panel"><div class="panel-heading"><h2>关联派生</h2><a class="home-all" href="${route({ kind: 'weapon', wtype: data.weapon_type, focus: entity.id, mode: 'branch' })}">打开完整派生树 ${icon('arrow')}</a></div><div class="panel-body weapon-derivations">${(data.parents || []).map(p => `<p>由 ${refLink(p.weapon, p.weapon.name, { level: p.level })} Lv ${p.level} 派生</p>`).join('')}${(data.branches || []).map(b => `<p class="${b.level === level.level ? 'current' : ''}"><span>Lv ${b.level} →</span>${refLink(b.target, b.label, { level: b.target_level })}</p>`).join('') || '<p class="notes">此路线没有其他武器分支。</p>'}</div></section>`;
  const main = `<div class="stack"><section class="panel"><div class="panel-heading"><h2>${esc(level.name)}</h2>${badge(`LV ${level.level}`, 'green')}</div><div class="panel-body"><div class="level-picker" aria-label="武器等级">${data.levels.map(l => `<button class="level-button ${l.level === level.level ? 'active' : ''}" data-level="${l.level}" aria-pressed="${l.level === level.level}">Lv ${l.level}</button>`).join('')}</div></div>${stats}${sharp}<div class="panel-caption">防御加成 ${num(level.defense)}${level.performance_differences.length ? ' · 部分性能数值待核对' : ''}</div></section><section class="panel"><div class="panel-heading"><h2>强化路线</h2><span class="muted" style="font-size:11px">点击等级查看配方</span></div>${table(['武器 / 等级', '攻击', '性能', '基础斩味', '孔'], rows, 'level-table weapon-table')}</section>${derivation}${performance ? `<details class="panel source-details"><summary>${icon('info')}等级性能详情</summary><div class="panel-body">${esc(performance)}</div></details>` : ''}</div>`;
  setPage(`${header(entity, `${weaponTypes[data.weapon_type] || data.weapon_type} · ${data.levels.length} 个强化等级`)}<div class="detail-grid"><div class="detail-main">${main}</div><aside class="detail-aside">${level.recipes.map(recipe => recipeCard(recipe)).join('') || `<section class="panel">${empty('暂无配方记录')}</section>`}${recentPanel(entity)}</aside></div>`, epoch);
  if (epoch === navigationEpoch) page.querySelectorAll(`[data-level="${level.level}"]`).forEach(button => button.closest('tr')?.classList.add('selected-row'));
}

async function records(collection) {
  if (!collection?.total) return [];
  if (!relationCache.has(collection.href)) relationCache.set(collection.href, (async () => { const all = []; for await (const row of api.iterate(collection)) all.push(row); return all; })().catch(error => { relationCache.delete(collection.href); throw error; }));
  return relationCache.get(collection.href);
}
const relationNames = { gathering: '地图采集', rewards: '怪物 / 任务奖励', weapon_uses: '武器用途', armor_uses: '防具用途', combining_inputs: '调合原料', combining_outputs: '调合产物', quests: '相关任务', armor: '关联防具' };
function strengthGauges(strength) {
  return `<div class="quest-strength">${[['health', '体力', 'health'], ['defense', '全体防御', 'defense']].map(([key, label, cls]) => {
    const value = strength?.[key];
    return `<div><span title="${label}">${key === 'defense' ? '防御' : label}</span>${value == null ? '<span class="muted">未记载</span>' : `<span class="strength-track ${cls}" role="img" aria-label="${label}相对强度 ${num(value)} / 100"><i style="width:${Number(value)}%"></i></span><small>${num(value)}</small>`}</div>`;
  }).join('')}</div>`;
}
function monsterQuestTable(entries, owner) {
  const monsters = row => `<div class="quest-monsters">${(row.monsters || []).map(m => `<div class="quest-monster ${m.monster?.id === owner.id ? 'subject' : ''}">${refLink(m.monster, m.label)}${m.count > 1 ? `<span>×${num(m.count)}</span>` : ''}${m.intrusion ? badge('乱入', 'amber') : ''}</div>`).join('')}</div>`;
  return `<p class="quest-strength-note">强度条对应${esc(owner.name)}：体力（绿）／全体防御（橙），越长越强。0–100 为相对刻度，非实际血量或防御率，仅适合同一怪物的任务间比较。</p>${table(['任务 / 目标', '出现怪物', '相对强度'], entries.map(r => [
    `<div class="quest-name">${refLink(r.quest)}<div class="quest-meta">${r.rank_label ? badge(r.rank_label) : ''}${r.quest_type ? badge(r.quest_type) : ''}${refLink(r.location)}${r.intrusion || r.role === '乱入' ? badge('本怪物乱入', 'amber') : ''}</div><p class="notes">${esc(r.objective || '')}</p></div>`,
    monsters(r), strengthGauges(r.strength),
  ]), 'monster-quest-table')}`;
}
function relationTable(name, entries, owner) {
  if (name === 'gathering') return table(['地图 / 难度', '点位 / 条件', '数量', '概率'], entries.map(r => [
    `<div class="gathering-location">${refLink(r.map, null, { area: r.area, rank: r.rank })}${badge(ranks[r.rank] || r.rank, r.rank === 'G' ? 'purple' : '')}</div>`,
    `<div>${esc(r.area)} 区 / ${esc(r.point)} 点</div><small class="muted">${r.attempts_infinite ? '无限采集' : `采集 ${r.attempts_min === r.attempts_max ? num(r.attempts_min) : `${num(r.attempts_min)}–${num(r.attempts_max)}`} 次`}</small><div class="cell-tags">${r.rare ? badge('稀有', 'amber') : badge('普通')}${r.fixed ? badge('固定') : ''}</div>`,
    `× ${num(r.quantity)}`, percent(r.percentage),
  ]), 'gathering-table');
  if (name === 'weapon_uses') return table(['武器', '等级', '用途', '数量'], entries.map(r => [refLink(r.weapon, null, { level: r.level }), `LV ${r.level}`, esc(recipeNames[r.kind] || r.kind), `× ${num(r.quantity)}`]));
  if (name === 'armor_uses') return table(['防具', '部位', '用途', '数量'], entries.map(r => [refLink(r.armor), esc(({ Head: '头部', Body: '身体', Arms: '腕部', Waist: '腰部', Legs: '脚部' })[r.slot] || r.slot || '—'), esc(recipeNames[r.kind] || r.kind), `× ${num(r.quantity)}`]));
  if (name.startsWith('combining')) return table(['调合产物', '备注'], entries.map(r => [refLink(r.recipe), name === 'combining_inputs' ? `原料 ${r.slot || ''}` : '产物']));
  if (name === 'quests') return monsterQuestTable(entries, owner);
  if (name === 'armor') return table(['防具', '单件', '技能点'], entries.map(r => [refLink(r.armor), esc(r.name || r.piece_name || r.label || '—'), num(r.points)]));
  return table(owner.kind === 'item' ? ['来源', '难度', '条件 / 奖励组', '数量', '概率'] : ['素材', '难度', '条件 / 奖励组', '数量', '概率'], entries.map(r => [refLink(owner.kind === 'item' ? r.source : r.item, owner.kind === 'item' ? r.source?.name : r.item?.name || r.label || r.raw_text), r.rank ? badge(ranks[r.rank] || r.rank) : '—', `<span class="readable">${esc([r.group_name, r.condition_text].filter(Boolean).join(' · ') || '—')}</span>`, `× ${num(r.quantity)}`, percent(r.percentage)]), 'reward-table');
}
async function relationsPanel(entity, r, fixedName = '') {
  const names = Object.keys(entity.relations).filter(key => relationNames[key]);
  if (!names.length || (fixedName && !names.includes(fixedName))) return '';
  const name = fixedName || (names.includes(r.tab) ? r.tab : (names.includes('gathering') ? 'gathering' : names.includes('rewards') ? 'rewards' : names[0]));
  const pageKey = fixedName ? `${name}Page` : 'page';
  const rankKey = fixedName ? `${name}Rank` : 'rank';
  const all = await records(entity.relations[name]);
  const hasRanks = all.some(row => row.rank);
  // Keep old monster tab/page links readable while each visible section now has
  // its own pagination and filters. Empty new values explicitly reset a filter.
  const requestedRank = r[rankKey] ?? (r.tab === name ? r.rank : '');
  const selectedRank = hasRanks && ['LR', 'HR', 'G'].includes(requestedRank) ? requestedRank : '';
  const selectedMap = fixedName ? '' : r.map;
  const filtered = all.filter(row => (!selectedRank || row.rank === selectedRank) && (!selectedMap || row.map?.id === selectedMap));
  const requestedPage = r[pageKey] ?? (r.tab === name ? r.page : 1);
  const size = 40, total = filtered.length, pages = Math.max(1, Math.ceil(total / size)), number = Math.max(1, Math.min(pages, Math.floor(Number(requestedPage)) || 1));
  const maps = [...new Map(all.filter(row => row.map).map(row => [row.map.id, row.map])).values()];
  const rankFilter = hasRanks ? `<select class="select" data-route-select="${rankKey}" data-page-key="${pageKey}" aria-label="${fixedName ? relationNames[name] : ''}难度"><option value="">全部难度</option>${Object.entries(ranks).map(([value, label]) => `<option value="${value}" ${selectedRank === value ? 'selected' : ''}>${label}</option>`).join('')}</select>` : '';
  const heading = fixedName
    ? `<div class="panel-heading"><h2>${relationNames[name]}</h2><span class="notes">${num(entity.relations[name].total)} 条</span></div>`
    : `<div class="tabs" role="navigation" aria-label="关联资料">${names.map(key => `<a class="tab ${key === name ? 'active' : ''}" aria-current="${key === name ? 'page' : 'false'}" href="${route({ id: entity.id, tab: key })}">${relationNames[key]}<span>${num(entity.relations[key].total)}</span></a>`).join('')}</div>`;
  const mapFilter = maps.length ? `<select class="select" data-route-select="map" data-page-key="${pageKey}" aria-label="地图筛选"><option value="">全部地图</option>${maps.map(map => `<option value="${esc(map.id)}" ${selectedMap === map.id ? 'selected' : ''}>${esc(map.name)}</option>`).join('')}</select>` : '';
  const toolbar = !fixedName || rankFilter || mapFilter ? `<div class="relation-toolbar">${rankFilter}${mapFilter}<span class="notes">${num(total)} 条${name === 'gathering' ? ' · 概率为参考值' : ''}</span></div>` : '';
  return `<section class="panel" data-relation="${name}">${heading}${toolbar}<div aria-label="${relationNames[name]}">${total ? relationTable(name, filtered.slice((number - 1) * size, number * size), entity) : empty('当前条件下没有记录', all.length ? '试试切换难度或地图。' : '暂无这类关联记录。')}</div><div class="catalog-footer"><span>${total ? `${(number - 1) * size + 1}–${Math.min(number * size, total)} / ${num(total)} 条` : '0 条记录'}</span>${pagination(total, number, size, fixedName ? r : { ...r, tab: name }, pageKey)}</div></section>`;
}
function itemProperties(data) {
  const pairs = [];
  for (const row of data.basic_rows || []) for (let i = 0; i + 1 < row.length; i += 2) if (row[i] !== '名称') pairs.push([row[i].replace('稀有度度', '稀有度').replace('説明', '说明').replace('売値', '出售价格').replace('所持', '持有上限').replace('評価値', '素材点数'), row[i + 1]]);
  return pairs;
}
function keyValues(pairs) { return `<dl class="key-values">${pairs.map(([label, value]) => `<div><dt>${esc(label)}</dt><dd>${esc(value ?? '未记载')}</dd></div>`).join('')}</dl>`; }
async function renderItem(entity, r, epoch) {
  const relations = await relationsPanel(entity, r);
  setPage(`${header(entity, '获取途径、调合配方与装备用途')}<div class="stack"><section class="panel"><div class="panel-heading"><h2>道具信息</h2>${badge('素材档案', 'green')}</div><div class="panel-body">${keyValues(itemProperties(entity.data))}</div></section>${relations}</div>`, epoch);
}

async function mapQuestsPanel(entity, r) {
  const result = await search({ kind: 'quest', destination: entity.id, page: r.questsPage || 1 });
  if (result.revision !== manifest.dataset_revision) throw new Error('任务资料已经更新，请刷新页面后继续。');
  const rows = result.items.map(quest => [
    `${refLink(quest)}<div class="record-subtitle">${esc(quest.subtitle)}</div>`,
    `<div class="catalog-info"><span>${esc(quest.summary)}</span>${quest.extra ? `<small>${esc(quest.extra)}</small>` : ''}</div>`,
  ]);
  return `<section class="panel map-quests" aria-label="本地图任务"><div class="panel-heading"><h2>本地图任务</h2><span class="notes">共 ${num(result.total)} 条</span></div>${rows.length ? table(['任务', '目标 / 概览'], rows, 'map-quest-table') : empty('暂无相关任务', '暂未收录以此地图为目的地的任务。')}<div class="catalog-footer"><span>${result.total ? `${(result.page - 1) * result.pageSize + 1}–${Math.min(result.page * result.pageSize, result.total)} / ${num(result.total)} 条` : '0 条记录'}</span>${pagination(result.total, result.page, result.pageSize, r, 'questsPage')}</div></section>`;
}

async function renderMap(entity, r, epoch) {
  const sections = entity.data.sections;
  const areas = [...new Set(sections.map(s => s.area))];
  const area = areas.includes(r.area) ? r.area : areas[0];
  const rank = sections.some(s => s.area === area && s.rank === r.rank) ? r.rank : 'LR';
  const section = sections.find(s => s.area === area && s.rank === rank) || sections.find(s => s.area === area);
  const [nodes, quests] = await Promise.all([records(entity.relations[section.relation]), mapQuestsPanel(entity, r)]);
  const fullImage = entity.data.images[0];
  const areaImage = entity.data.images.find(i => i.source_path.endsWith(`_${area}.gif`));
  setPage(`${header(entity, '按区域与难度查看采集点和素材概率')}<div class="stack"><div class="map-layout"><div class="stack"><section class="panel"><div class="panel-heading"><h2>地图总览</h2><span class="notes">采集概率为参考值</span></div><div class="panel-body">${fullImage ? `<img class="map-image" src="${esc(localAsset(fullImage.url))}" alt="${esc(entity.name)}地图总览" loading="lazy">` : '<p class="notes">暂无地图图片。</p>'}</div>${areaImage ? `<div class="panel-body"><img class="map-image" src="${esc(localAsset(areaImage.url))}" alt="${esc(area)}区采集点位" loading="lazy"></div>` : ''}</section></div><div><div class="filter-row"><select class="select" data-route-select="area" aria-label="地图区域">${areas.map(a => `<option ${a === area ? 'selected' : ''} value="${esc(a)}">${esc(a)} 区</option>`).join('')}</select><div class="filter-chips">${Object.entries(ranks).map(([value, label]) => `<a class="filter-chip ${section.rank === value ? 'active' : ''}" href="${route({ ...r, area, rank: value })}">${label}</a>`).join('')}</div></div><div class="nodes-grid">${nodes.map(node => `<section class="panel"><div class="panel-heading"><h2 class="node-heading">${node.icon_url ? `<img src="${esc(localAsset(node.icon_url))}" alt="采集种类">` : ''}点位 ${esc(node.point_label || node.point)}</h2>${badge(node.rare ? '稀有' : '普通', node.rare ? 'amber' : '')}</div>${table(['素材', '数量', '概率'], node.items.map(i => [refLink(i.item, i.item?.name || i.label), `× ${num(i.quantity)}`, percent(i.percentage)]))}<div class="panel-caption">${esc(node.attempts_raw || '次数未记载')}${node.percentage_sum !== 100 ? ` · 概率合计 ${node.percentage_sum}%` : ''}</div></section>`).join('') || empty('当前区域没有采集记录', section.empty_text || '')}</div></div></div>${quests}</div>`, epoch);
}

async function renderOther(entity, r, epoch) {
  const d = entity.data;
  let body = '';
  if (entity.kind === 'monster') {
    const headers = ['切', '打', '弾', '火', '水', '雷', '冰', '龙', '气绝'];
    body = `<section class="panel"><div class="panel-heading"><h2>基本信息</h2></div><div class="panel-body">${keyValues(Object.entries(d.metadata).filter(([, v]) => typeof v !== 'object'))}</div></section><section class="panel hitzone-panel"><div class="panel-heading"><h2>部位肉质</h2><span class="notes">括号值为特殊状态</span></div>${table(['部位', ...headers], d.hitzones.map(h => [esc(h.body_part), ...headers.map(k => esc(h.values[k] ?? '—'))]), 'hitzone-table')}</section>${notes(d)}`;
  } else if (entity.kind === 'quest') {
    body = `<section class="panel"><div class="panel-heading"><h2>任务信息</h2><span>${d.flags.map(f => badge(f, 'green')).join(' ')}</span></div><div class="panel-body">${keyValues([['主任务', d.objective], ['副任务', d.sub_objective], ['目的地', d.destination_text], ['时间限制', d.time_minutes == null ? null : `${d.time_minutes} 分钟`], ['任务报酬', d.reward_zenny == null ? null : `${num(d.reward_zenny)} z`], ['契约金', d.fee_zenny == null ? null : `${num(d.fee_zenny)} z`]])}<div style="margin-top:16px;display:flex;gap:16px;flex-wrap:wrap">${d.references.filter(ref => ref.target).map(ref => refLink(ref.target, ref.label)).join('')}</div></div></section>`;
  } else if (entity.kind === 'skill') {
    body = `<section class="panel"><div class="panel-heading"><h2>技能发动</h2></div>${table(['技能', '所需点数', '效果'], d.activations.map(a => [esc(a.name), badge(a.points > 0 ? `+${a.points}` : a.points, a.points > 0 ? 'green' : 'amber'), `<span class="readable wrap-text">${esc(a.description)}</span>`]), 'skill-table')}</section>`;
  } else if (entity.kind === 'armor') {
    body = `<section class="panel"><div class="panel-heading"><h2>套装部件</h2>${badge(`稀有度 ${d.metadata['稀有度'] || '—'}`)}</div>${renderArmorTable({ id: entity.id, variants: groupArmorPieces(d.pieces) }, true, r.piece)}</section><section class="panel"><div class="panel-heading"><h2>属性耐性</h2></div>${table(['防具', '火', '水', '雷', '冰', '龙'], d.pieces.map(p => [esc(p.name), ...['fire', 'water', 'thunder', 'ice', 'dragon'].map(k => num(p[k]))]), 'resistance-table')}</section><details class="panel source-details"><summary>${icon('info')}生产与强化配方（${d.recipes.length}）</summary><div class="panel-body">${d.recipes.map(recipe => recipeCard(recipe, `${recipeNames[recipe.kind] || recipe.kind} · ${recipe.slot || ''} LV ${recipe.level}`)).join('')}</div></details>${notes(d, '装备说明')}`;
  } else if (entity.kind === 'combining') {
    body = `<section class="panel"><div class="panel-heading"><h2>调合配方</h2>${badge(d.category)}</div><div class="panel-body"><div class="recipe-list">${d.inputs.map(i => `<div class="material-row"><span class="muted">原料 ${i.slot}</span>${refLink(i.item, i.item?.name || i.label)}</div>`).join('')}<div class="material-row"><strong>产物</strong>${refLink(d.result, d.result_label)}</div></div><div style="margin-top:20px">${keyValues([['产出数量', d.amount_min === d.amount_max ? d.amount_min : `${d.amount_min}–${d.amount_max}`], ['成功率', d.percentage == null ? null : `${d.percentage}%`]])}</div>${!d.result ? '<p class="notes" style="margin-top:14px">此产物暂无独立道具页。</p>' : ''}</div></section>`;
  }
  const relations = entity.kind === 'monster'
    ? (await Promise.all(['rewards', 'quests'].map(name => relationsPanel(entity, r, name)))).join('')
    : await relationsPanel(entity, r);
  setPage(`${header(entity)}<div class="stack">${body}${relations}</div>`, epoch);
}

async function renderRoute() {
  const epoch = ++navigationEpoch;
  const previous = currentRoute;
  currentRoute = readRoute();
  const r = currentRoute;
  const changedPage = previous.id !== r.id || (!r.id && JSON.stringify(previous) !== JSON.stringify(r));
  clearTimeout(previewTimer); $('#hover-card').hidden = true;
  $('#sidebar').classList.remove('open'); $('#menu-toggle').setAttribute('aria-expanded', 'false');
  if (!r.id && document.activeElement !== searchInput) searchInput.value = r.q || '';
  renderNav();
  page.setAttribute('aria-busy', 'true');
  const slow = setTimeout(() => { if (epoch === navigationEpoch) page.innerHTML = skeleton(); }, 180);
  try {
    if (!manifest) manifest = await api.manifest();
    if (epoch !== navigationEpoch) return;
    renderNav();
    if (isHome(r)) {
      currentEntity = null;
      lastList = '#home';
      document.title = '资料导航 · MHXX 资料库';
      const navigation = await homeData();
      const favoriteResults = await Promise.allSettled(saved.slice(0, 5).map(id => api.get(id)));
      setPage(renderHome({ navigation, counts: manifest.entity_counts, recent, favorites: favoriteResults.filter(value => value.status === 'fulfilled').map(value => value.value) }), epoch);
    }
    else if (!r.id) { currentEntity = null; lastList = location.hash; await renderBrowse(r, epoch); }
    else {
      const entity = await api.get(r.id);
      if (epoch !== navigationEpoch) return;
      currentEntity = entity;
      document.title = `${entity.name} · MHXX 资料库`;
      if (entity.kind === 'weapon') renderWeapon(entity, r, epoch);
      else if (entity.kind === 'item') await renderItem(entity, r, epoch);
      else if (entity.kind === 'map') await renderMap(entity, r, epoch);
      else await renderOther(entity, r, epoch);
      if (epoch !== navigationEpoch) return;
      recent = [{ id: entity.id, kind: entity.kind, name: entity.name }, ...recent.filter(e => e.id !== entity.id)].slice(0, 8);
      persist('mhxx.recent.v1', recent);
    }
  } catch (error) {
    setPage(`<div class="panel">${empty('暂时无法读取资料', /404/.test(error.message) ? '这条资料不存在，请返回列表重新选择。' : error.message)}<div style="text-align:center;padding:0 20px 30px"><button class="button primary" data-retry>重新加载</button> <a class="button" href="#home">返回资料首页</a></div></div>`, epoch);
  } finally {
    clearTimeout(slow);
    if (epoch === navigationEpoch) {
      page.setAttribute('aria-busy', 'false');
      if (changedPage) window.scrollTo({ top: 0, behavior: 'instant' });
    }
  }
}

$('#show-saved').innerHTML = icon('bookmark');
$('#menu-toggle').innerHTML = icon('menu') + '<span>分类</span>';
$('#show-saved').addEventListener('click', () => navigate({ saved: '1' }));
$('#menu-toggle').addEventListener('click', () => { const open = $('#sidebar').classList.toggle('open'); $('#menu-toggle').setAttribute('aria-expanded', String(open)); });
function submitSearch(replace) { clearTimeout(searchTimer); navigate(searchInput.value.trim() ? { q: searchInput.value.trim() } : '#home', replace); }
searchInput.addEventListener('input', event => { if (!event.isComposing) { clearTimeout(searchTimer); searchTimer = setTimeout(() => submitSearch(true), 160); } });
searchInput.addEventListener('compositionend', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => submitSearch(true), 160); });
$('#search-form').addEventListener('submit', event => { event.preventDefault(); submitSearch(false); });
window.addEventListener('hashchange', renderRoute);
document.addEventListener('keydown', event => {
  const editing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName);
  if ((event.key.toLowerCase() === 'k' && (event.metaKey || event.ctrlKey)) || (event.key === '/' && !editing)) { event.preventDefault(); searchInput.focus(); searchInput.select(); }
  if (event.key === 'Escape') { clearTimeout(previewTimer); $('#hover-card').hidden = true; $('#sidebar').classList.remove('open'); $('#menu-toggle').setAttribute('aria-expanded', 'false'); if (document.activeElement === searchInput) searchInput.blur(); }
});
document.addEventListener('click', async event => {
  const button = event.target.closest('button');
  if (!button || button.disabled) return;
  if (button.dataset.armorToggle || button.dataset.armorView) {
    const key = button.dataset.armorToggle;
    if (key) toggledArmor.has(key) ? toggledArmor.delete(key) : toggledArmor.add(key);
    else {
      toggledArmor.clear();
      if (currentRoute.view !== button.dataset.armorView) { navigate({ ...currentRoute, view: button.dataset.armorView }); return; }
    }
    await renderArmorBrowse(currentRoute, navigationEpoch);
    if (key) [...page.querySelectorAll('[data-armor-toggle]')].find(node => node.dataset.armorToggle === key)?.focus({ preventScroll: true });
    else page.querySelector(`[data-armor-view="${button.dataset.armorView}"]`)?.focus({ preventScroll: true });
    return;
  }
  if (button.dataset.treeToggle || button.hasAttribute('data-tree-expand-all')) {
    const key = button.dataset.treeToggle;
    if (key) { collapsedWeapons.has(key) ? collapsedWeapons.delete(key) : collapsedWeapons.add(key); }
    else collapsedWeapons.clear();
    await renderWeaponBrowse(currentRoute, navigationEpoch);
    if (key) [...page.querySelectorAll('[data-tree-toggle]')].find(node => node.dataset.treeToggle === key)?.focus({ preventScroll: true });
    return;
  }
  if (button.hasAttribute('data-retry')) { location.reload(); return; }
  if (button.dataset.go) { navigate(button.dataset.go); return; }
  if (button.dataset.level) {
    const next = { id: currentEntity.id, level: button.dataset.level };
    // URL state remains copyable; native View Transitions enhance cached level changes.
    if (document.startViewTransition && !reduced.matches) document.startViewTransition(() => { history.pushState(null, '', route(next)); return renderRoute(); });
    else navigate(next);
    return;
  }
  if (button.dataset.save) {
    const id = button.dataset.save, wasSaved = saved.includes(id);
    saved = wasSaved ? saved.filter(value => value !== id) : [...saved, id];
    const stored = persist('mhxx.saved.v1', saved);
    if (stored) toast(wasSaved ? '已移出收藏夹' : '已加入收藏夹');
    if (currentRoute.saved) renderRoute();
    else { document.querySelectorAll('[data-save]').forEach(node => { if (node.dataset.save === id) node.outerHTML = savedButton(id, node.classList.contains('button')); }); renderNav(); }
  }
  if (button.hasAttribute('data-copy')) {
    try { await navigator.clipboard.writeText(location.href); toast('资料链接已复制'); }
    catch { toast('无法自动复制，请复制浏览器地址栏中的链接。'); }
  }
});
document.addEventListener('submit', event => {
  if (!['weapon-filter-form', 'armor-filter-form'].includes(event.target.id)) return;
  event.preventDefault();
  const key = event.target.id === 'armor-filter-form' ? 'aq' : 'wq';
  navigate({ ...currentRoute, [key]: event.target.querySelector(`[name="${key}"]`).value.trim(), page: '' });
});
document.addEventListener('change', async event => {
  if (event.target.hasAttribute('data-quest-group')) {
    const r = currentRoute, epoch = navigationEpoch, group = event.target.value;
    const navigation = await homeData();
    if (epoch !== navigationEpoch) return;
    const state = questFilterState(r, navigation);
    navigate({ ...r, group, qhub: group ? questGroupHub(navigation.categories[group]) : state.hub, qflag: state.flag, qtype: state.type, page: '' });
    return;
  }
  const key = event.target.dataset.routeSelect;
  if (key) navigate({ ...currentRoute, [key]: event.target.value, [event.target.dataset.pageKey || 'page']: '' });
});

async function showPreview(link) {
  if (!matchMedia('(hover:hover) and (min-width:761px)').matches) return;
  const id = link.dataset.preview;
  try {
    const entity = await api.get(id);
    if (!link.isConnected || !(link.matches(':hover') || document.activeElement === link)) return;
    const card = $('#hover-card');
    const d = entity.data;
    const previewLevel = entity.kind === 'weapon' ? d.levels.find(l => l.level === Number(link.dataset.previewLevel)) : null;
    const summary = entity.kind === 'weapon' ? previewLevel ? `Lv ${previewLevel.level} · 攻击 ${previewLevel.attack} · 会心 ${previewLevel.affinity}% · ${previewLevel.slots} 孔` : `${weaponTypes[d.weapon_type] || d.weapon_type} · 攻击 ${d.levels[0].attack} → ${d.levels.at(-1).attack}` : entity.kind === 'item' ? `${num(entity.relations.gathering.total)} 条采集记录 · ${num(entity.relations.rewards.total)} 条奖励记录` : kinds[entity.kind];
    card.innerHTML = `${badge(kinds[entity.kind], 'green')}<strong style="display:block;margin-top:7px">${esc(entity.name)}</strong><p>${esc(summary)}</p><p>点击查看完整资料 ${icon('arrow')}</p>`;
    const rect = link.getBoundingClientRect();
    card.style.left = `${Math.max(12, Math.min(rect.left, innerWidth - 277))}px`;
    card.style.top = `${Math.max(10, Math.min(rect.bottom + 10, innerHeight - 150))}px`;
    card.hidden = false;
  } catch { /* A preview must not interrupt reading or navigation. */ }
}
document.addEventListener('pointerover', event => { const link = event.target.closest('[data-preview]'); if (!link || link.contains(event.relatedTarget)) return; clearTimeout(previewTimer); previewTimer = setTimeout(() => showPreview(link), 350); });
document.addEventListener('pointerout', event => { const link = event.target.closest('[data-preview]'); if (link && !link.contains(event.relatedTarget)) { clearTimeout(previewTimer); $('#hover-card').hidden = true; } });
document.addEventListener('focusin', event => { const link = event.target.closest('[data-preview]'); if (link) { clearTimeout(previewTimer); previewTimer = setTimeout(() => showPreview(link), 450); } });
document.addEventListener('focusout', () => { clearTimeout(previewTimer); $('#hover-card').hidden = true; });
window.addEventListener('scroll', () => { $('#hover-card').hidden = true; }, { passive: true });
window.addEventListener('storage', event => { if (event.key === 'mhxx.saved.v1') { saved = readStorage(event.key, []); renderRoute(); } });
renderRoute();
