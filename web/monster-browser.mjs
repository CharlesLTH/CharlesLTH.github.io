import { esc, route, icon, badge } from './ui.mjs';

export function renderMonsterFilters(r, catalog) {
  const base = { ...r, kind: 'monster', page: '' };
  const sizes = [['', '全部怪物'], ['monster-2501', '大型怪物'], ['monster-2502', '小型怪物']];
  const size = r.group === 'monster-2501' ? 'large' : r.group === 'monster-2502' ? 'small' : '';
  return `<section class="panel monster-filters" aria-label="怪物筛选">
    <nav class="filter-chips" aria-label="怪物大小">${sizes.map(([group, label]) => `<a class="filter-chip ${!r.group && !group || r.group === group ? 'active' : ''}" href="${route({ ...base, group })}" ${(!r.group && !group || r.group === group) ? 'aria-current="true"' : ''}>${label}</a>`).join('')}</nav>
    <label>目录分类<select class="select" data-route-select="family" aria-label="怪物分类"><option value="">全部分类</option>${catalog.families.map(family => {
      const count = size ? family.counts[size] : family.counts.large + family.counts.small;
      return `<option value="${esc(family.key)}" ${r.family === family.key ? 'selected' : ''}>${esc(family.label)}（${count}）</option>`;
    }).join('')}</select></label>
  </section>`;
}

export function renderMonsterTable(items, r, catalog, savedButton) {
  const families = new Map(catalog.families.map(family => [family.key, family.label]));
  const grouped = !r.sort || r.sort === 'default';
  const groups = [];
  for (const entry of items) {
    const family = grouped ? entry.monster_family : '';
    if (!groups.length || groups.at(-1).family !== family) groups.push({ family, rows: [] });
    const marker = ['[新]', '[再]'].includes(entry.monster_marker) ? `<span class="home-marker ${entry.monster_marker === '[新]' ? 'new' : 'returning'}">${entry.monster_marker}</span>` : '';
    groups.at(-1).rows.push(`<tr data-monster-id="${esc(entry.id)}"><td><div class="record-name"><span class="record-symbol">${icon('monster')}</span><div><div class="monster-name"><a href="${route({ id: entry.id })}" data-preview="${esc(entry.id)}">${esc(entry.name)}</a>${marker}</div><div class="record-subtitle">${esc(entry.subtitle)}</div></div></div></td><td><div class="catalog-info"><span>${esc(entry.summary)}</span>${entry.extra ? `<small>${esc(entry.extra)}</small>` : ''}</div></td><td>${savedButton(entry.id)}</td></tr>`);
  }
  return `<div class="table-wrap catalog-table monster-catalog-table"><table><thead><tr><th scope="col">名称 / 分类</th><th scope="col">概览</th><th scope="col"><span class="sr-only">收藏</span></th></tr></thead>${groups.map(group => `<tbody>${group.family ? `<tr class="monster-family-heading"><th colspan="3" scope="rowgroup"><a href="${route({ ...r, kind: 'monster', family: group.family, page: '' })}">${esc(families.get(group.family))}</a></th></tr>` : ''}${group.rows.join('')}</tbody>`).join('')}</table></div>`;
}

export function renderMonsterClassification(entity, catalog) {
  const record = catalog.monsters.find(monster => monster.id === entity.id);
  if (!record) return '';
  return `<div class="monster-classification"><span class="muted">目录分类</span><a class="badge green" href="${route({ kind: 'monster', family: record.family, group: record.size === 'large' ? 'monster-2501' : 'monster-2502' })}">${esc(record.family_label)} ${icon('arrow')}</a>${badge(record.size === 'large' ? '大型怪物' : '小型怪物')}</div>`;
}
