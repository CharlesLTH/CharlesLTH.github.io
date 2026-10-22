import { kinds, weaponTypes, icon, esc, num, route } from './ui.mjs';

function homeLink(link, label) {
  if (!link.route) return '';
  const text = esc(label || link.label);
  const marker = ['[新]', '[再]'].includes(link.marker) ? `<span class="home-marker ${link.marker === '[新]' ? 'new' : 'returning'}">${link.marker}</span>` : '';
  return `<a class="home-link" href="${route(link.route)}" ${link.route.id ? `data-preview="${esc(link.route.id)}"` : ''}><span>${text}</span>${marker}</a>`;
}

function linkRow(label, links, transform) {
  links = links.filter(link => link.route);
  return links.length ? `<div class="home-link-row">${label ? `<h3>${esc(label)}</h3>` : ''}<div class="home-links">${links.map(link => homeLink(link, transform?.(link))).join('')}</div></div>` : '';
}

function panel(title, kind, body, count) {
  return `<section class="panel home-section" data-home-section="${kind}"><div class="panel-heading"><h2>${icon(kind)}${esc(title)}</h2><a class="home-all" href="${route({ kind })}">全部${count ? ` ${num(count)}` : ''} ${icon('arrow')}</a></div><div class="home-panel-body">${body}</div></section>`;
}

export function renderHome({ navigation, counts, recent = [], favorites = [] }) {
  const sections = navigation.sections;
  const links = title => (sections[title]?.links || []).filter(link => link.route);
  const questLinks = links('任务');
  const quest = (test, label, transform) => linkRow(label, questLinks.filter(test), transform);
  const keyQuests = questLinks.filter(l => /关键任务/.test(l.label));
  const progression = quest(l => /^村\d+$/.test(l.label), '村任务', l => `★${l.label.slice(1)}`)
    + quest(l => /^集\d+$/.test(l.label), '集会所', l => `★${l.label.slice(1)}`)
    + quest(l => /^G\d+$/.test(l.label), 'G 级')
    + quest(l => /^(特许|特殊|斗技|挑战|活动)/.test(l.label), '特殊任务')
    + quest(l => /^(村民|食材|狩技|装备|设施)/.test(l.label), '解锁与委托');
  const weapons = `<div class="home-weapon-grid">${Object.entries(weaponTypes).map(([kind, label]) => `<a href="${route({ kind: 'weapon', wtype: kind })}"><span>${esc(label)}</span><small>${num(navigation.weapon_counts[kind])} 条路线</small></a>`).join('')}</div>${linkRow('', links('武器补足'))}`;
  const itemLinks = links('道具');
  const reading = l => /行$/.test(l.label);
  const items = linkRow('素材分类', itemLinks.filter(l => !reading(l) && l.label !== '道具一览'))
    + linkRow('获取与调合', links('道具入手'))
    + `<details class="home-reading"><summary>按原文读音查找</summary>${linkRow('', itemLinks.filter(reading))}</details>`;
  const armorLinks = links('防具').filter(l => l.label !== '防具一览');
  const armor = linkRow('稀有度 1–7', armorLinks.filter(l => /^稀有度[1-7]$/.test(l.label)), l => l.label.replace('稀有度', 'R'))
    + linkRow('G 级防具', armorLinks.filter(l => !/^稀有度[1-7]$/.test(l.label)), l => l.label.replace('稀有度', 'R'))
    + linkRow('装饰品', links('装饰品'));
  const skills = linkRow('', links('技能').filter(l => l.label !== '技能一览'));
  const maps = `<div class="home-map-grid">${links('地图').map(l => homeLink(l)).join('')}</div>`;
  const monsterGroups = sections['怪物'].groups;
  const monsters = `<div class="home-monster-types">${links('怪物').filter(l => !l.route?.id).map(l => homeLink(l)).join('')}<span class="notes">[新] 新增 · [再] 回归</span></div><div class="home-monster-grid">${monsterGroups.map(group => `<section class="home-monster-group"><h3>${esc(group.label)}</h3><div class="home-monster-links">${group.links.map(l => homeLink(l)).join('')}</div></section>`).join('')}</div>`;
  const extras = ['狩技', '武器操作', '随从猫装备', '随从猫技能', '随从猫任务', '来访猎人', '猫饭', '交易窗口'].filter(title => links(title).length);
  const personal = recent.length || favorites.length ? `<section class="panel home-personal" aria-label="我的常用资料">${recent.length ? linkRow('最近浏览', recent.slice(0, 5).map(e => ({ label: e.name, route: { id: e.id } }))) : ''}${favorites.length ? linkRow('我的收藏', favorites.slice(0, 5).map(e => ({ label: e.name, route: { id: e.id } }))) : ''}<a class="home-all" href="#saved=1">收藏夹 ${icon('arrow')}</a></section>` : '';
  return `<div class="home-page"><div class="page-heading"><div><h1>资料导航</h1><p>装备、任务、素材与狩猎资料，按分类直接查找。</p></div><span class="badge green">MHXX</span></div>
    <nav class="home-quicklinks" aria-label="主要资料分类">${Object.entries(kinds).map(([kind, label]) => `<a href="${route({ kind })}" aria-label="${esc(label)}全部资料">${icon(kind)}<span>${kind === 'item' ? '素材' : label}</span></a>`).join('')}</nav>
    ${personal}
    <div class="home-grid">
      ${panel('武器派生', 'weapon', weapons, counts.weapon)}
      ${panel('任务与关键任务', 'quest', `<div class="home-key-quests">${keyQuests.map(l => homeLink(l)).join('')}</div>${progression}`, counts.quest)}
      <div class="home-stack">${panel('道具与素材', 'item', items, counts.item)}${panel('技能', 'skill', skills, counts.skill)}</div>
      <div class="home-stack">${panel(links('装饰品').length ? '防具与装饰品' : '防具', 'armor', armor, counts.armor)}${panel('地图采集', 'map', maps, counts.map)}</div>
    </div>
    ${panel('怪物资料', 'monster', monsters, counts.monster)}
    ${extras.length ? `<section class="panel home-section home-more"><div class="panel-heading"><h2>${icon('info')}更多狩猎资料</h2></div><div class="home-extra-grid">${extras.map(title => `<section><h3>${esc(title)}</h3><div class="home-links">${links(title).map(l => homeLink(l)).join('')}</div></section>`).join('')}</div></section>` : ''}
  </div>`;
}
