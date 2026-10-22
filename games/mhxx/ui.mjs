export const kinds = { weapon: '武器', armor: '防具', item: '道具与素材', monster: '怪物', quest: '任务', skill: '技能', map: '地图', combining: '调合' };
export const weaponTypes = { 'Great Sword': '大剑', 'Long Sword': '太刀', 'Sword and Shield': '片手剑', 'Dual Blades': '双剑', Hammer: '大锤', 'Hunting Horn': '狩猎笛', Lance: '长枪', Gunlance: '铳枪', 'Switch Axe': '斩斧', 'Charge Blade': '盾斧', 'Insect Glaive': '操虫棍', 'Light Bowgun': '轻弩', 'Heavy Bowgun': '重弩', Bow: '弓' };
export const ranks = { LR: '下位', HR: '上位', G: 'G 位' };
export const elementNames = { Fire: '火', Water: '水', Ice: '冰', Thunder: '雷', Dragon: '龙', Poison: '毒', Paralysis: '麻痹', Sleep: '睡眠', Blast: '爆破', Blastblight: '爆破' };
export const recipeNames = { Create: '生产', Improve: '强化', CreateByForge: '生产', Scrap: '端材' };
const paths = {
 home: '<path d="m3 10 9-7 9 7v11H3Z"/><path d="M9 21v-8h6v8"/>',
 weapon: '<path d="m14 3 7 0 0 7-12 12-7-7Z"/><path d="m6 14 4 4m-3 1-4 4m-1-4 3 3"/>',
 armor: '<path d="m8 3 4 3 4-3 6 5-4 5-2-2v11H8V11l-2 2-4-5Z"/>',
 item: '<path d="m12 2 9 6v10l-9 5-9-5V8Z"/><path d="m3 8 9 6 9-6M12 14v9m-5-18 10 6"/>',
 monster: '<path d="m5 9-2-6 7 3h4l7-3-2 6 2 7-6 5H9l-6-5Z"/><path d="m7 12 3 1m7-1-3 1m-4 4h4"/>',
 quest: '<rect x="5" y="4" width="14" height="18" rx="2"/><path d="M9 4V2h6v2M9 10h6m-6 4h6m-6 4h4"/>',
 skill: '<path d="m13 2-9 12h7l-1 9 10-14h-7Z"/>',
 map: '<path d="m2 5 6-3 8 3 6-3v18l-6 3-8-3-6 3Zm6-3v18m8-15v18"/>',
 combining: '<path d="M9 2h6m-5 0v7L3 19q-1 3 3 3h12q4 0 3-3L14 9V2M7 15h10"/>',
 bookmark: '<path d="M6 3h12v19l-6-4-6 4Z"/>',
 search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
 arrow: '<path d="m9 5 7 7-7 7"/>',
 back: '<path d="m15 5-7 7 7 7"/>',
 link: '<path d="M14 3h7v7m0-7L10 14M10 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/>',
 menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
 check: '<path d="m4 12 5 5L20 6"/>',
 close: '<path d="m5 5 14 14M5 19 19 5"/>',
 info: '<circle cx="12" cy="12" r="10"/><path d="M12 11v6m0-10v1"/>',
 copy: '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
};
export const icon = (name, cls = '') => `<svg class="icon ${cls}" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.item}</svg>`;
export const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
export const num = value => value == null ? '—' : Number(value).toLocaleString('zh-CN');
export const percent = value => value == null ? '<span class="muted">未记载</span>' : `${esc(value)}<span class="unit">%</span>`;
export function route(values = {}) { return '#' + new URLSearchParams(Object.entries(values).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString(); }
export const refLink = (ref, label, extra = {}) => ref ? `<a class="entity-link" href="${route({ id: ref.id, ...extra })}" data-preview="${esc(ref.id)}">${esc(label || ref.name)}</a>` : `<span>${esc(label || '未记载')}</span>`;
export const badge = (text, cls = '') => `<span class="badge ${cls}">${esc(text)}</span>`;
export const empty = (title, detail = '') => `<div class="empty-state">${icon('search')}<strong>${esc(title)}</strong><p>${esc(detail)}</p></div>`;
export function table(headers, rows, cls = '') { return rows.length ? `<div class="table-wrap ${cls}"><table><thead><tr>${headers.map(h => `<th scope="col">${h}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(c => `<td>${c ?? '—'}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : empty('暂无记录', '暂未收录这部分资料。'); }
export function sharpness(values, label = '') {
  // Match the original site's .kr0–.kr6 palette (games/mhxx_old/index.css).
  const colors = ['#bc0b43', '#f45600', '#ffc836', '#4de200', '#4068fa', '#fff', '#cc33cc'];
  if (!values?.length) return '<span class="muted">—</span>';
  // Original bars use a shared 180px scale. Percentages keep both the colour
  // proportions and the shorter base bars when the available column shrinks.
  const scale = Math.max(180, values.reduce((sum, v) => sum + Number(v), 0));
  return `<span class="sharpness" role="img" aria-label="${esc(label || '斩味色条')}">${values.map((v, i) => `<i style="width:${Number(v) / scale * 100}%;background:${colors[i]}" title="${['红', '橙', '黄', '绿', '蓝', '白', '紫'][i]}"></i>`).join('')}</span>`;
}
export function elements(level) { return level.elements?.length ? level.elements.map(([e, v]) => `<span class="element">${esc(elementNames[e] || e)} <b>${esc(v)}</b></span>`).join(' ') : '<span class="muted">无</span>'; }
export function slots(value) { return `<span class="slots" role="img" aria-label="${Number(value) || 0} 个孔槽">${[0, 1, 2].map(i => `<i class="${i < Number(value) ? 'filled' : 'empty'}"></i>`).join('')}</span>`; }
