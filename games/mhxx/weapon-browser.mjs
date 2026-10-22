import { esc, num, route, table, badge, elements, slots, sharpness, weaponTypes, elementNames, icon, empty } from './ui.mjs';
import { normalize } from './search-core.mjs';

export const weaponModes = { all: '全部等级', final: '仅最终', first: 'LV1', ends: 'LV1 · 最终', branch: 'LV1 · 派生 · 最终' };
export function prepareWeapons(catalog) {
  const byKey = new Map(catalog.nodes.map(n => [n.key, n]));
  const familyTerms = new Map();
  for (const node of catalog.nodes) {
    if (!familyTerms.has(node.id)) familyTerms.set(node.id, []);
    familyTerms.get(node.id).push(normalize(node.name));
  }
  return { ...catalog, byKey, familyTerms };
}

export function queryWeapons(model, { mode = 'all', query = '', element = '', sort = '', page = 1, focus = '', collapsed = new Set() } = {}) {
  if (!weaponModes[mode]) mode = 'all';
  const term = normalize(query);
  const focusRoot = focus ? model.nodes.find(n => n.id === focus)?.root : null;
  const qualifies = n => mode === 'all' || (mode === 'final' ? n.final : mode === 'first' ? n.level === 1 : n.level === 1 || n.final || (mode === 'branch' && n.branch));
  const matched = model.nodes.filter(n => qualifies(n) && (!focusRoot || n.root === focusRoot)
    && (!term || model.familyTerms.get(n.id).some(name => name.includes(term)))
    && (!element || (element === 'none' ? !n.elements.length : n.elements.some(([key]) => key === element))));
  const pageSize = mode === 'final' ? 40 : 6;
  let units, visible;
  const matches = new Set(matched.map(n => n.key));
  if (mode === 'final') {
    units = [...matched];
    if (sort === 'attack') units.sort((a, b) => b.attack - a.attack || a.name.localeCompare(b.name, 'zh-CN'));
    else if (sort === 'name') units.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN', { numeric: true }));
  } else {
    visible = new Set(matches);
    // Keep the visible ancestor chain as context, skipping levels hidden by the
    // selected mode. Filtering never presents an orphan as a new root.
    for (const node of matched) {
      let parent = model.byKey.get(node.parent);
      while (parent) {
        if (qualifies(parent)) visible.add(parent.key);
        parent = model.byKey.get(parent.parent);
      }
    }
    const roots = new Set(matched.map(n => n.root));
    units = model.roots.filter(key => roots.has(key));
  }
  const totalPages = Math.max(1, Math.ceil(units.length / pageSize));
  page = Math.max(1, Math.min(totalPages, Math.floor(Number(page)) || 1));
  const selected = units.slice((page - 1) * pageSize, page * pageSize);
  let rows, maxDepth = 0;
  if (mode === 'final') rows = selected.map(node => ({ node, depth: 0, trails: [], last: true, toggle: false, context: false }));
  else {
    const children = new Map(), roots = new Set(selected);
    for (const node of model.nodes) {
      if (!visible.has(node.key) || !roots.has(node.root)) continue;
      let parent = model.byKey.get(node.parent);
      while (parent && !visible.has(parent.key)) parent = model.byKey.get(parent.parent);
      const key = parent?.key || '';
      if (!children.has(key)) children.set(key, []);
      children.get(key).push(node.key);
    }
    rows = [];
    function walk(key, trails, last, depth, hidden = false) {
      const node = model.byKey.get(key), descendants = children.get(key) || [];
      // Include hidden descendants in the depth budget so collapsing a branch
      // does not change the indentation scale of the remaining rows.
      maxDepth = Math.max(maxDepth, depth);
      if (!hidden) rows.push({ node, depth, trails, last, toggle: descendants.length > 0, collapsed: collapsed.has(key), context: !matches.has(key), root: depth === 0 });
      descendants.forEach((child, i) => walk(child, depth ? [...trails, !last] : [], i === descendants.length - 1, depth + 1, hidden || collapsed.has(key)));
    }
    (children.get('') || []).forEach(key => walk(key, [], true, 0));
  }
  return { rows, maxDepth, total: matched.length, mode, page, pageSize, totalPages, units: units.length, focusRoot };
}

function weaponRow(row, model, savedButton, focus) {
  const { node: n } = row;
  const parent = model.byKey.get(n.parent);
  const guides = row.depth ? `<span class="tree-guides" aria-hidden="true">${row.trails.map(continues => `<i class="${continues ? 'tree-through' : ''}"></i>`).join('')}<i class="${row.last ? 'tree-elbow' : 'tree-fork'}"></i></span>` : '';
  const branchFrom = parent && parent.id !== n.id ? `<small class="weapon-parent">由 <a href="${route({ id: parent.id, level: parent.level })}">${esc(parent.name)} Lv ${parent.level}</a> 派生</small>` : '';
  const toggle = row.toggle ? `<button class="tree-toggle" data-tree-toggle="${esc(n.key)}" aria-expanded="${!row.collapsed}" aria-label="${row.collapsed ? '展开' : '收起'}${esc(n.name)}的派生">${row.collapsed ? '+' : '−'}</button>` : '';
  const sharp = n.sharpness_px.length ? `<div class="weapon-sharpness">${[0, 2].filter(i => n.sharpness_px[i]).map(i => `<div><small>${i ? '匠+2' : '基础'}</small>${sharpness(n.sharpness_px[i], i ? '匠+2斩味' : '基础斩味')}</div>`).join('')}</div>` : `<span class="weapon-ranged">${esc(n.special || '不适用')}</span>`;
  return [
    `<div class="weapon-tree-name ${row.root ? 'root' : ''} ${row.context ? 'context' : ''} ${focus === n.id ? 'focused' : ''}" style="--tree-depth:${row.depth}" data-tree-depth="${row.depth}">${guides}<div><a class="weapon-name" href="${route({ id: n.id, level: n.level })}" data-preview="${esc(n.id)}" data-preview-level="${n.level}">${esc(n.name)}</a><div class="weapon-row-tags">${toggle}<span>Lv ${n.level}</span>${n.final ? badge('最终', 'purple') : ''}${n.can_create ? badge('生产', 'green') : ''}${n.xx ? badge('XX') : ''}${row.context ? '<span>派生路径</span>' : ''}${savedButton(n.id)}</div>${branchFrom}</div></div>`,
    `<strong class="weapon-attack">${num(n.attack)}</strong>`,
    `<div class="weapon-performance"><span class="weapon-affinity">会心 ${esc(n.affinity ?? '—')}%</span><div class="weapon-elements">${elements(n)}${n.defense ? `<small>防御 +${num(n.defense)}</small>` : ''}</div></div>`,
    sharp, slots(n.slots),
  ];
}

export function renderWeaponBrowser(model, r, collapsed, savedButton) {
  const result = queryWeapons(model, { mode: r.mode, query: r.wq, element: r.element, sort: r.sort, page: r.page, focus: r.focus, collapsed });
  const kind = model.weapon_type;
  const values = { ...r, kind: 'weapon', wtype: kind, mode: result.mode };
  const typeLinks = Object.entries(weaponTypes).map(([key, label]) => `<a class="filter-chip ${key === kind ? 'active' : ''}" href="${route({ kind: 'weapon', wtype: key, mode: result.mode })}">${label}</a>`).join('');
  const modes = Object.entries(weaponModes).map(([key, label]) => `<a class="weapon-mode ${key === result.mode ? 'active' : ''}" aria-current="${key === result.mode ? 'page' : 'false'}" href="${route({ ...values, mode: key, sort: '', page: '' })}">${label}</a>`).join('');
  const unitLabel = result.mode === 'final' ? '把武器' : '棵派生树';
  const pagination = `<div class="pagination"><button class="button" data-go="${esc(route({ ...values, page: result.page - 1 }))}" ${result.page <= 1 ? 'disabled' : ''} aria-label="上一页">${icon('back')}</button><span class="current-page">${result.page} / ${result.totalPages}</span><button class="button" data-go="${esc(route({ ...values, page: result.page + 1 }))}" ${result.page >= result.totalPages ? 'disabled' : ''} aria-label="下一页">${icon('arrow')}</button></div>`;
  const ranged = ['Bow', 'Light Bowgun', 'Heavy Bowgun'].includes(kind);
  return `<div class="weapon-browser" style="--tree-max-depth:${Math.max(1, result.maxDepth)}"><div class="breadcrumb"><a href="#home">资料首页</a>${icon('arrow')}<span>武器</span></div><div class="page-heading"><div><h1>${esc(weaponTypes[kind])} · 武器派生</h1><p>直接对照各等级性能，点击武器名称查看对应配方。</p></div>${badge('MHXX', 'green')}</div>
    <nav class="filter-chips weapon-type-links" aria-label="武器类型">${typeLinks}</nav>
    <section class="panel"><nav class="weapon-modes" aria-label="武器显示模式">${modes}</nav>
    <div class="weapon-toolbar"><form id="weapon-filter-form"><input name="wq" class="weapon-name-filter" type="search" value="${esc(r.wq || '')}" placeholder="筛选本类武器名称" aria-label="筛选本类武器名称"><button class="button" type="submit">筛选</button></form>
    <select class="select" data-route-select="element" aria-label="武器属性"><option value="">全部属性</option>${Object.entries({ ...elementNames, Blastblight: '爆破', none: '无属性' }).filter(([key]) => key !== 'Blast').map(([key, name]) => `<option value="${key}" ${r.element === key ? 'selected' : ''}>${name}</option>`).join('')}</select>
    ${result.mode === 'final' ? `<select class="select" data-route-select="sort" aria-label="最终武器排序"><option value="">派生顺序</option><option value="attack" ${r.sort === 'attack' ? 'selected' : ''}>攻击力由高到低</option><option value="name" ${r.sort === 'name' ? 'selected' : ''}>名称排序</option></select>` : '<button class="button" data-tree-expand-all>展开分支</button>'}
    ${result.focusRoot ? `<a class="filter-chip active" href="${route({ ...values, focus: '', page: '' })}">仅此派生树 ×</a>` : ''}
    <span class="notes">${num(result.total)} 条等级记录 · ${num(result.units)} ${unitLabel}</span></div>
    <p class="weapon-table-hint">${result.mode === 'final' ? '最终按每条武器路线的最后一级展示。' : '＋／− 展开或收起后续分支；每页保留完整派生树。'} ${ranged ? '远程武器显示蓄力或装填性能。' : '斩味上条为基础，下条为匠+2。'}</p>
    ${result.rows.length ? table(['武器 / 派生树', '攻击', '性能', ranged ? '远程性能' : '斩味<br>基础 / +2', '孔'], result.rows.map(row => weaponRow(row, model, savedButton, r.focus)), 'weapon-tree-table weapon-table') : empty('没有符合条件的武器', '试试更短的名称或其他属性。')}
    <div class="catalog-footer"><span>${result.mode === 'final' ? '最终武器' : '完整树分组'} · ${num(result.rows.length)} 行</span>${pagination}</div></section></div>`;
}
