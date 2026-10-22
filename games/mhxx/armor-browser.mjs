import { esc, num, route, refLink, badge, slots, icon, empty } from './ui.mjs';
import { normalize } from './search-core.mjs';

export const armorTypes = { common: '通用', blade: '剑士', gunner: '射手' };
const pieceSlots = { Head: '头', Body: '胴', Arms: '腕', Waist: '腰', Legs: '脚' };

export function groupArmorPieces(pieces) {
  return Object.entries({ common: '通用', blade: '剑士用', gunner: '神枪手用' }).flatMap(([type, sourceType]) => {
    const selected = pieces.filter(p => p.hunter_type === sourceType);
    if (!selected.length) return [];
    const skills = new Map();
    for (const piece of selected) for (const s of piece.skills) {
      const key = s.skill?.id || s.label;
      const prior = skills.get(key);
      skills.set(key, { ...s, points: prior ? (prior.points == null || s.points == null ? null : prior.points + s.points) : s.points });
    }
    const sum = key => selected.some(p => p[key] == null) ? null : selected.reduce((n, p) => n + p[key], 0);
    return [{ type, pieces: selected, summary: { defense: sum('defense'), max_defense: sum('max_defense'), slots: sum('slots'), skills: [...skills.values()] } }];
  });
}

export function prepareArmor(catalog) {
  return { ...catalog, sets: catalog.sets.map(set => ({ ...set, terms: normalize([
    set.name, ...set.aliases,
    ...set.variants.flatMap(v => v.pieces.flatMap(p => [p.name, ...p.skills.map(s => s.label)])),
  ].join(' ')) })) };
}

export function queryArmor(model, { group = '', query = '', type = '', sort = '', page = 1 } = {}) {
  if (group && !model.categories.some(c => c.key === group)) throw new Error('这个防具分类不存在，请从资料首页重新选择。');
  const term = normalize(query);
  const sets = model.sets.filter(s => (!group || s.group === group) && (!term || s.terms.includes(term)) && (!type || s.variants.some(v => v.type === type)));
  if (sort === 'name') sets.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN', { numeric: true }));
  const pageSize = 20, total = sets.length, totalPages = Math.max(1, Math.ceil(total / pageSize));
  page = Math.max(1, Math.min(totalPages, Math.floor(Number(page)) || 1));
  // Paginate whole sets, keeping their swordsman/gunner variants together.
  return { sets: sets.slice((page - 1) * pageSize, page * pageSize), total, totalPages, page, pageSize };
}

function skillPoints(skills) {
  return skills.length ? `<div class="armor-skills">${skills.map(s => `<span class="armor-skill">${refLink(s.skill, s.label)} <b class="${s.points < 0 ? 'negative' : ''}">${s.points == null ? '未记载' : `${s.points > 0 ? '+' : ''}${s.points}`}</b></span>`).join('')}</div>` : '<span class="muted">—</span>';
}

export function renderArmorTable(set, expanded = false, selectedPiece = '', type = '') {
  const defense = p => `<span class="armor-defense">${num(p.defense)}<wbr> / <wbr>${num(p.max_defense)}</span>`;
  return `<div class="table-wrap armor-catalog-table"><table><thead><tr><th scope="col">${expanded ? '部位 / 名称' : '类型 / 合计'}</th><th scope="col">防御<br>初始 / 最高</th><th scope="col">技能点</th><th scope="col">孔</th></tr></thead>${set.variants.filter(v => !type || v.type === type).map(v => `<tbody data-armor-type="${v.type}">
    <tr class="armor-summary"><th scope="row"><span class="armor-type ${v.type}">${armorTypes[v.type]}</span><small>${v.pieces.length} 件合计</small></th><td>${defense(v.summary)}</td><td>${skillPoints(v.summary.skills)}</td><td><span class="armor-slot-total" aria-label="合计 ${num(v.summary.slots)} 个孔槽">${num(v.summary.slots)}</span></td></tr>
    ${expanded ? v.pieces.map(p => `<tr class="armor-piece ${String(p.ordinal) === String(selectedPiece) ? 'selected-row' : ''}" data-piece="${p.ordinal}"><td><div class="armor-piece-name"><small>${esc(pieceSlots[p.slot] || p.slot)}</small><a class="entity-link" href="${route({ id: set.id, piece: p.ordinal })}">${esc(p.name)}</a></div></td><td>${defense(p)}</td><td>${skillPoints(p.skills)}</td><td>${slots(p.slots)}</td></tr>`).join('') : ''}
  </tbody>`).join('')}</table></div>`;
}

export function renderArmorBrowser(model, r, toggled, savedButton) {
  const type = Object.hasOwn(armorTypes, r.atype) ? r.atype : '';
  const result = queryArmor(model, { group: r.group, query: r.aq, type, sort: r.sort, page: r.page });
  const category = model.categories.find(c => c.key === r.group);
  const title = category ? `防具 · ${category.label}` : '防具一览';
  const values = { ...r, kind: 'armor' };
  const allExpanded = r.view === 'pieces';
  const categories = `<a class="filter-chip ${!r.group ? 'active' : ''}" href="${route({ ...values, group: '', page: '' })}">全部</a>${model.categories.map(c => `<a class="filter-chip ${r.group === c.key ? 'active' : ''}" href="${route({ ...values, group: c.key, page: '' })}">${esc(c.label.replace('稀有度', 'R'))}</a>`).join('')}`;
  const pager = `<div class="pagination"><button class="button" data-go="${esc(route({ ...values, page: result.page - 1 }))}" ${result.page <= 1 ? 'disabled' : ''} aria-label="上一页">${icon('back')}</button><span class="current-page">${result.page} / ${result.totalPages}</span><button class="button" data-go="${esc(route({ ...values, page: result.page + 1 }))}" ${result.page >= result.totalPages ? 'disabled' : ''} aria-label="下一页">${icon('arrow')}</button></div>`;
  return `<div class="armor-browser"><div class="breadcrumb"><a href="#home">资料首页</a>${icon('arrow')}<span>防具</span></div><div class="page-heading"><div><h1>${esc(title)}</h1><p>默认对照通用或剑士／射手合计，展开套装查看各件性能。</p></div>${badge('MHXX', 'green')}</div>
    <nav class="filter-chips armor-category-links" aria-label="防具稀有度">${categories}</nav>
    <section class="panel armor-controls"><div class="armor-toolbar"><form id="armor-filter-form"><input name="aq" class="weapon-name-filter" type="search" value="${esc(r.aq || '')}" placeholder="套装、单件名称或技能" aria-label="筛选防具名称或技能"><button class="button" type="submit">筛选</button></form>
    <select class="select" data-route-select="atype" aria-label="防具类型"><option value="">全部类型</option>${Object.entries(armorTypes).map(([key, label]) => `<option value="${key}" ${type === key ? 'selected' : ''}>${label}</option>`).join('')}</select>
    <select class="select" data-route-select="sort" aria-label="防具排序"><option value="">默认顺序</option><option value="name" ${r.sort === 'name' ? 'selected' : ''}>名称排序</option></select>
    <div class="armor-view-actions"><button class="button ${!allExpanded ? 'selected' : ''}" data-armor-view="sets">全部折叠</button><button class="button ${allExpanded ? 'selected' : ''}" data-armor-view="pieces">全部展开</button></div><span class="notes">${num(result.total)} 套</span></div>
    <p class="armor-list-note">防御为初始 / 最高值；套装显示孔数与技能点合计。身体系统加倍单独列出，不计入其他技能的合计。</p></section>
    <div class="armor-sets">${result.sets.map(set => {
      const expanded = allExpanded !== toggled.has(set.id);
      const tableId = `armor-pieces-${set.id.split(':')[1]}`;
      return `<section class="panel armor-set" data-armor-set="${esc(set.id)}"><div class="armor-set-heading"><h2><a href="${route({ id: set.id })}">${esc(set.name)}</a></h2>${badge(`R${set.rarity}`)}${set.gender !== '男女通用' ? badge(set.gender) : ''}<div class="armor-set-actions">${savedButton(set.id)}<button class="armor-toggle" data-armor-toggle="${esc(set.id)}" aria-expanded="${expanded}" aria-controls="${tableId}" aria-label="${expanded ? '折叠' : '展开'}${esc(set.name)}的单件数据">${expanded ? '−' : '+'}</button></div></div><div id="${tableId}">${renderArmorTable(set, expanded, '', type)}</div></section>`;
    }).join('') || empty('没有符合条件的防具', '试试其他名称、技能或稀有度。')}</div>
    <div class="catalog-footer"><span>${result.total ? `${(result.page - 1) * result.pageSize + 1}–${Math.min(result.page * result.pageSize, result.total)} / ${num(result.total)} 套` : '0 套'}</span>${pager}</div></div>`;
}
