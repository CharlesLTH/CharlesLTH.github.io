import { esc, num, badge, slots, elements, table } from './ui.mjs';

function fields(values) {
  return `<dl class="performance-fields">${values.map(([name, value]) => `<div><dt>${esc(name)}</dt><dd>${value}</dd></div>`).join('')}</dl>`;
}

function section(title, content, note = '') {
  return `<section class="performance-section"><h3>${esc(title)}</h3>${note ? `<p class="notes">${esc(note)}</p>` : ''}${content}</section>`;
}

function loadCell(load) {
  if (!load) return '<span class="ammo-unavailable">不适用</span>';
  if (load.count == null) return '<span class="ammo-unavailable" aria-label="不可使用">—</span>';
  return `<span class="ammo-load ${load.requires_skill ? 'requires-skill' : ''}"><b>${num(load.count)}</b>${load.requires_skill ? '<small>需技能</small>' : ''}</span>`;
}

export function renderWeaponPerformance(level, detail) {
  const basic = fields([
    ['攻击力', num(level.attack)], ['会心率', `${esc(level.affinity ?? '—')}%`],
    ['防御加成', `+${num(level.defense)}`], ['孔槽', `<span class="performance-slots">${slots(level.slots)}<span>${num(level.slots)} / 3</span></span>`],
    ['属性 / 异常状态', elements(level)],
    ...detail.fields.map(field => [field.label, esc(field.value)]),
  ]);
  const blocks = [section('基础性能', basic)];
  if (detail.ammunition) {
    const leveled = detail.ammunition.filter(ammo => ammo.loads.length > 1);
    const single = detail.ammunition.filter(ammo => ammo.loads.length === 1);
    blocks.push(section('弹药装填', `<div class="ammo-tables">${section('分级弹 · 装填数（发）', table(['弹种', 'Lv1', 'Lv2', 'Lv3'], leveled.map(ammo => [esc(ammo.name), ...[0, 1, 2].map(i => loadCell(ammo.loads[i]))]), 'ammo-level-table'))}${section('单级弹 · 装填数（发）', table(['弹种', '装填数'], single.map(ammo => [esc(ammo.name), loadCell(ammo.loads[0])]), 'ammo-single-table'))}</div>`, '数字为每次装填的数量；“需技能”表示需发动对应弹追加技能，“—”表示不可使用。'));
    blocks.push(section('内藏弹', detail.internal_ammo.length
      ? table(['弹种', '携带数（发）', '装填数（发）'], detail.internal_ammo.map(ammo => [esc(ammo.name), esc(ammo.carried), esc(ammo.loaded)]), 'internal-ammo-table')
      : '<p class="notes">无内藏弹。</p>', '携带数是内藏弹总量，装填数是每次装填的数量。'));
    if (detail.crouching_fire) blocks.push(section('蹲射弹种', detail.crouching_fire.length
      ? `<ul class="performance-list">${detail.crouching_fire.map(name => `<li>${esc(name)}</li>`).join('')}</ul>` : '<p class="notes">无蹲射弹种。</p>'));
    if (detail.rapid_fire) blocks.push(section('速射', detail.rapid_fire.length
      ? table(['弹种', '连发数', '速射硬直'], detail.rapid_fire.map(ammo => [esc(ammo.name), esc(ammo.shots), esc(ammo.recovery)]), 'rapid-fire-table')
      : '<p class="notes">无速射弹种。</p>'));
  }
  if (detail.charges) blocks.push(section('蓄力攻击', table(['蓄力阶段', '射击类型 / 等级', '使用条件'], detail.charges.map(charge => [`第 ${charge.level} 阶段`, esc(charge.shot), charge.requires_skill ? '需装填数UP' : '可用']), 'bow-charge-table')));
  if (detail.coatings) blocks.push(section('可用瓶', table(['瓶种', '使用状态'], detail.coatings.map(coating => [esc(coating.name), coating.available ? (coating.enhanced ? badge('可用 · 强化', 'green') : '可用') : '<span class="ammo-unavailable">不可使用</span>']), 'bow-coating-table')));
  if (detail.melodies) blocks.push(section('狩猎笛旋律', table(['音色顺序', '旋律效果'], detail.melodies.map(melody => [esc(melody.notes.join(' → ')), esc(melody.effect)]), 'melody-table')));
  if (detail.expected_attack?.length) blocks.push(section('攻击期待值（参考）', fields(detail.expected_attack.map((value, i) => [detail.expected_attack.length === 1 ? '期待值' : ['基础斩味', '匠 +1', '匠 +2'][i], esc(value)])), '计算参考值；括号内为对应斩味颜色与长度。'));
  return `<section class="panel weapon-level-details" aria-label="等级性能详情"><div class="panel-heading"><h2>等级性能详情</h2>${badge(`Lv ${level.level}`, 'green')}</div><div class="panel-body"><p class="performance-name">${esc(level.name)}</p><div class="performance-sections">${blocks.join('')}</div></div></section>`;
}
