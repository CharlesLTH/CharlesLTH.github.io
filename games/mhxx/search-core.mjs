export const normalize = value => String(value ?? '').normalize('NFKC').toLowerCase().replace(/\s+/gu, '');

export function prepareIndex(entries) {
  return entries.map(entry => ({ ...entry, terms: [entry.name, ...(entry.aliases || [])].map(normalize) }));
}

export function queryIndex(entries, { query = '', kind = '', weaponType = '', group = '', destination = '', questHub = '', questFlag = '', questType = '', saved, sort = 'default', page = 1, pageSize = 40 } = {}) {
  const term = normalize(query);
  const savedSet = saved ? new Set(saved) : null;
  const matched = entries.filter(e => (!savedSet || savedSet.has(e.id)) && (!term || e.terms.some(n => n.includes(term))));
  const counts = Object.fromEntries(['weapon', 'item', 'monster', 'quest', 'armor', 'skill', 'map', 'combining'].map(k => [k, 0]));
  matched.forEach(e => counts[e.kind]++);
  const flagNames = { key: ['关键'], urgent: ['紧急'], progression: ['关键', '紧急'] };
  let filtered = matched.filter(e => (!kind || e.kind === kind) && (!weaponType || e.weapon_type === weaponType) && (!group || e.groups?.includes(group)) && (!destination || e.map_ids?.includes(destination))
    && (!questHub || e.quest_hub === questHub)
    && (!questFlag || flagNames[questFlag]?.some(flag => e.quest_flags?.includes(flag)))
    && (!questType || (e.kind === 'quest' && e.subtitle === questType)));
  if (sort === 'name') filtered.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN', { numeric: true }));
  else if (sort === 'attack') filtered.sort((a, b) => (b.attack_max ?? -1) - (a.attack_max ?? -1));
  else if (term) filtered.sort((a, b) => Number(b.terms[0] === term) - Number(a.terms[0] === term));
  const total = filtered.length;
  page = Math.max(1, Math.min(Math.ceil(total / pageSize) || 1, Math.floor(Number(page)) || 1));
  return { total, counts, page, pageSize, items: filtered.slice((page - 1) * pageSize, page * pageSize).map(({ terms, ...entry }) => entry) };
}
