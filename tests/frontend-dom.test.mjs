// DOM-only integration tests. No browser, device, display or Computer Use.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { Window } from 'happy-dom';

const window = new Window({ url: 'https://mhxx.test/games/mhxx/' });
const document = window.document;
const html = await readFile(new URL('../web/index.html', import.meta.url), 'utf8');
document.write(html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, '').replace(/<link\b[^>]*>/g, ''));
for (const name of ['window', 'document', 'location', 'history', 'localStorage', 'navigator']) {
  Object.defineProperty(globalThis, name, { configurable: true, value: name === 'window' ? window : window[name] });
}
globalThis.matchMedia = window.matchMedia.bind(window);
globalThis.requestAnimationFrame = window.requestAnimationFrame.bind(window);
globalThis.innerWidth = 1280;
globalThis.innerHeight = 900;
const requests = [];
globalThis.fetch = async input => {
  const url = new URL(String(input));
  assert.equal(url.origin, 'https://mhxx.test', 'DOM tests must never contact external services');
  const relative = url.pathname.replace('/games/mhxx/', '');
  assert.ok(!relative.includes('..') && !relative.startsWith('/'));
  requests.push(relative);
  try { return new Response(await readFile(new URL('../games/mhxx/' + relative, import.meta.url)), { status: 200 }); }
  catch { return new Response('{}', { status: 404 }); }
};
await import('../web/app.mjs');

const $ = selector => document.querySelector(selector);
async function until(check, label) {
  const end = Date.now() + 6000;
  // Hash navigation queues its event; do not accept the old DOM synchronously.
  await new Promise(resolve => setTimeout(resolve, 15));
  while (Date.now() < end) {
    if (check() && $('#page').getAttribute('aria-busy') === 'false') {
      assert.ok([...document.querySelectorAll('a[href]')].every(link => new URL(link.href).origin === window.location.origin), 'Frontend navigation stays within this site');
      assert.ok([...document.querySelectorAll('a[href]')].every(link => !new URL(link.href).pathname.startsWith('/games/mhxx_old/')), 'No navigation to the archived site');
      assert.doesNotMatch($('#page').textContent, /原站|资料来源与说明|查看原始页面/);
      return;
    }
    await new Promise(resolve => setTimeout(resolve, 15));
  }
  throw new Error(`${label}: hash=${window.location.hash}, rank=${$('[data-route-select="rank"]')?.value}, busy=${$('#page').getAttribute('aria-busy')}; ${$('#page').textContent.slice(0, 500)}`);
}
async function navigate(values, expected) {
  window.location.hash = new URLSearchParams(values).toString();
  await until(() => $('#page').textContent.includes(expected), 'Navigation to ' + expected);
}

test('real app: search, level selection, material sources, filters, map, saved state and every entity kind', async () => {
  try {
    await until(() => $('.home-page'), 'Initial homepage');
    assert.equal($('h1').textContent, '资料导航');
    assert.equal(document.querySelectorAll('.home-quicklinks a').length, 8);
    assert.equal(document.querySelectorAll('.home-weapon-grid a').length, 14);
    assert.equal(document.querySelectorAll('.home-map-grid a').length, 24);
    assert.ok($('.home-monster-group h3'));
    const newMonster = [...document.querySelectorAll('.home-monster-links a')].find(a => a.textContent.includes('胧隐夜鸟'));
    const returningMonster = [...document.querySelectorAll('.home-monster-links a')].find(a => a.textContent.includes('白速龙王'));
    assert.equal(newMonster.querySelector('.home-marker').textContent, '[新]');
    assert.equal(returningMonster.querySelector('.home-marker').textContent, '[再]');
    assert.ok(!requests.includes('browse-index.json'), 'Homepage does not need the full search index');
    assert.ok(!$('.catalog-table'), 'Default entry must be the useful homepage, not a weapon list');
    assert.ok(!$('.home-more'), 'Unmigrated external entries leave no empty section');
    assert.ok([...document.querySelectorAll('.home-link-row')].every(row => row.querySelector('a')), 'Home categories must contain working internal links');
    const homepageMonsters = [...document.querySelectorAll('.home-monster-links a')].map(a => new URLSearchParams(a.hash.slice(1)).get('id'));
    assert.equal(homepageMonsters.length, 94);
    assert.ok(!requests.includes('monster-catalog.json'), 'Homepage classifications do not need the detailed monster catalog');
    const monsterRows = () => [...document.querySelectorAll('[data-monster-id]')].map(row => row.dataset.monsterId);
    await navigate({ group: 'monster-2501', kind: 'monster' }, '大型怪物');
    assert.deepEqual(monsterRows(), homepageMonsters.slice(0, 40), 'Existing large-monster URL follows homepage order');
    assert.equal($('.monster-family-heading').textContent, '鸟龙种');
    const newMonsterId = new URLSearchParams(newMonster.hash.slice(1)).get('id');
    assert.equal($(`[data-monster-id="${newMonsterId}"] .home-marker`).textContent, '[新]');
    assert.match($('[data-route-select="sort"]').textContent, /主页顺序/);
    $('[aria-label="下一页"]').click();
    await until(() => monsterRows()[0] === homepageMonsters[40], 'Monster pagination keeps ordering');
    assert.deepEqual(monsterRows(), homepageMonsters.slice(40, 80));
    const familySelect = $('[data-route-select="family"]');
    familySelect.value = 'fanged-beast';
    familySelect.dispatchEvent(new window.Event('change', { bubbles: true }));
    await until(() => monsterRows().length === 13, 'Family selection from a later page');
    assert.ok(!new URLSearchParams(window.location.hash.slice(1)).has('page'));
    assert.ok($('[data-route-select="family"] option[value="fanged-beast"]').hasAttribute('selected'));
    assert.equal($('.monster-family-heading').textContent, '牙兽种');
    $('.monster-filters a[href*="group=monster-2502"]').click();
    await until(() => monsterRows().length === 3, 'Size and family filters combine');
    assert.ok([...document.querySelectorAll('.record-subtitle')].every(node => node.textContent === '牙兽种 · 小型'));
    await navigate({ kind: 'monster', group: 'monster-2502', family: 'flying-wyvern' }, '没有找到相关资料');
    assert.ok($('.monster-filters'), 'Empty family combinations keep recovery controls');
    $('.monster-filters a[href*="group=monster-2501"]').click();
    await until(() => monsterRows().length === 21, 'Recover by switching to large monsters');
    const detailId = monsterRows()[0];
    $('.monster-name a').click();
    await until(() => $('.monster-classification'), 'Monster detail classification');
    assert.match($('.monster-classification').textContent, /目录分类飞龙种.*大型怪物/);
    $('.monster-classification a').click();
    await until(() => monsterRows().length === 21, 'Classification returns to matching list');
    assert.equal(monsterRows()[0], detailId);
    await navigate({ kind: 'monster', family: 'flying-wyvern', sort: 'name' }, '飞龙种');
    assert.ok(!$('.monster-family-heading'), 'Explicit name sorting stays alphabetical without fake grouping');
    await navigate({ kind: 'monster', family: 'missing-family' }, '这个怪物分类不存在');
    $('.brand').click();
    await until(() => $('.home-page'), 'Back to homepage for family shortcut');
    $('.home-monster-group h3 a[href*="family=fanged-beast"]').click();
    await until(() => monsterRows().length === 13, 'Homepage family heading opens classified list');
    assert.match(window.location.hash, /group=monster-2501/);
    assert.equal(requests.filter(path => path === 'monster-catalog.json').length, 1, 'Cache classifications across list and detail routes');
    $('.brand').click();
    await until(() => $('.home-page'), 'Back to homepage for quest navigation');
    $('[href*="group=quest-2011"]').click();
    await until(() => $('h1')?.textContent === '村1', 'Village one-star category');
    assert.equal(document.querySelectorAll('.catalog-table tbody tr').length, 7);
    assert.ok([...document.querySelectorAll('.record-name a')].every(link => /^村★1\D/.test(link.textContent)));
    assert.equal($('[aria-label="任务分类"] .active').textContent, '村任务');
    assert.ok($('[data-quest-group] option[value="quest-2011"]').hasAttribute('selected'));
    await navigate({ kind: 'quest' }, '关键任务');
    assert.equal($('[aria-label="任务分类"] .active').textContent, '全部');
    assert.doesNotMatch($('.quest-filters').textContent, /委托/);
    $('[aria-label="任务进度"] a[href*="qflag=key"]').click();
    await until(() => /122 条/.test($('.catalog-subhead')?.textContent), 'Only key quests');
    $('[aria-label="任务分类"] a[href*="qhub=guild"]').click();
    await until(() => /60 条/.test($('.catalog-subhead')?.textContent), 'Guild key quests');
    const questGroup = $('[data-quest-group]');
    questGroup.value = 'quest-2996';
    questGroup.dispatchEvent(new window.Event('change', { bubbles: true }));
    await until(() => /6 条/.test($('.catalog-subhead')?.textContent), 'G four-star key quests');
    assert.ok([...document.querySelectorAll('.record-name a')].every(link => /^G★4/.test(link.textContent)));
    assert.equal($('[aria-label="任务进度"] .active').textContent, '关键任务');
    await navigate({ kind: 'quest', group: 'quest-2014' }, '村4');
    const questType = $('[data-route-select="qtype"]');
    questType.value = '捕获';
    questType.dispatchEvent(new window.Event('change', { bubbles: true }));
    await until(() => document.querySelectorAll('.catalog-table tbody tr').length === 2, 'Capture quests within village four-star');
    assert.match($('.catalog-table').textContent, /镰蟹1只的捕获/);
    await navigate({ kind: 'quest', group: 'quest-2859' }, '村关键任务');
    assert.match($('.catalog-subhead').textContent, /78 条/);
    assert.equal($('[aria-label="任务进度"] .active').textContent, '关键＋紧急');
    $('[aria-label="任务进度"] a[href*="qflag=urgent"]').click();
    await until(() => /16 条/.test($('.catalog-subhead')?.textContent), 'Urgent village quests');
    $('[aria-label="任务进度"] a:first-child').click();
    await until(() => /370 条/.test($('.catalog-subhead')?.textContent), 'Clear progression filter without losing village category');
    await navigate({ kind: 'quest', qflag: 'key', page: '3' }, '关键任务');
    $('[aria-label="任务分类"] a[href*="qhub=permit"]').click();
    await until(() => $('#page').textContent.includes('没有找到相关资料'), 'Empty combined quest filter');
    assert.ok(!new URLSearchParams(window.location.hash.slice(1)).has('page'), 'Changing categories resets pagination');
    assert.ok($('.quest-filters'), 'Keep filters available for recovering from an empty result');
    $('.brand').click();
    await until(() => $('.home-page'), 'Logo returns to homepage');
    $('[href*="group=item-2112"]').click();
    await until(() => $('h1')?.textContent === '矿石', 'Ore category');
    assert.match($('#page').textContent, /48 条/);
    await navigate({ kind: 'armor', group: 'armor-2301' }, '防具 · 稀有度1');
    assert.ok(requests.includes('armor-catalog.json'));
    assert.equal(document.querySelectorAll('.armor-set').length, 20);
    assert.ok(!$('.armor-piece'), 'Default armor view shows aggregate rows, without expanded pieces');
    const leather = $('[data-armor-set="armor:site-219222"]');
    assert.equal(leather.querySelectorAll('tbody').length, 1);
    assert.equal(leather.querySelector('tbody').dataset.armorType, 'common');
    assert.match(leather.textContent, /5 件合计.*5 \/ 250.*反复无常 \+10/);
    const huntingSelector = '[data-armor-set="armor:site-219748"]';
    assert.deepEqual([...document.querySelectorAll(`${huntingSelector} tbody`)].map(n => n.dataset.armorType), ['blade', 'gunner']);
    $(`${huntingSelector} [data-armor-toggle]`).click();
    await until(() => $(`${huntingSelector} .armor-piece`), 'Expand one armor set');
    assert.equal(document.querySelectorAll(`${huntingSelector} .armor-piece`).length, 10);
    assert.equal(document.querySelectorAll(`${huntingSelector} thead th`).length, 4);
    assert.match($(`${huntingSelector} .armor-piece`).textContent, /狩猎头盔.*2 \/ 50.*千里眼 \+3/);
    assert.equal($(`${huntingSelector} .armor-piece .slots`).getAttribute('aria-label'), '1 个孔槽');
    $(`${huntingSelector} .armor-piece-name a`).click();
    await until(() => $('.armor-catalog-table .selected-row'), 'Armor piece link selects the actual piece');
    assert.match(window.location.hash, /piece=0/);
    assert.match($('.armor-catalog-table .selected-row').textContent, /狩猎头盔/);
    assert.equal(document.querySelectorAll('.armor-catalog-table tbody').length, 2);
    await navigate({ kind: 'armor', group: 'armor-2301' }, '防具 · 稀有度1');
    $('[data-armor-view="pieces"]').click();
    await until(() => document.querySelectorAll('.armor-piece').length > 10, 'Expand all armor sets');
    $('[data-armor-view="sets"]').click();
    await until(() => !$('.armor-piece'), 'Collapse all armor sets');
    $('[data-armor-toggle]').click();
    await until(() => $('.armor-piece'), 'Expand in already collapsed mode');
    $('[data-armor-view="sets"]').click();
    await until(() => !$('.armor-piece'), 'Collapse all clears individual overrides even when mode is unchanged');
    $('#armor-filter-form [name="aq"]').value = '贝鲁纳头巾';
    $('#armor-filter-form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
    await until(() => document.querySelectorAll('.armor-set').length === 1, 'Find an armor set by piece name');
    assert.equal($('.armor-set').dataset.armorSet, 'armor:site-218352');
    await navigate({ kind: 'weapon' }, '大剑 · 武器派生');
    assert.equal(document.querySelectorAll('.weapon-modes a').length, 5);
    assert.equal(document.querySelectorAll('.weapon-type-links a').length, 14);
    assert.equal(document.querySelectorAll('.weapon-tree-table thead th').length, 5);
    assert.ok($('.weapon-tree-name [data-save]'), 'Bookmark belongs with the name, without taking a whole column');
    assert.match($('.weapon-performance').textContent, /会心.*%/);
    assert.equal(document.querySelectorAll('.weapon-tree-table tbody tr:first-child .slots i').length, 3);
    const depthBudget = $('.weapon-browser').style.getPropertyValue('--tree-max-depth');
    assert.ok(Number(depthBudget) > 4, 'Exercise a tree deeper than the old truncated guide');
    for (const name of document.querySelectorAll('.weapon-tree-name')) {
      const depth = Number(name.dataset.treeDepth);
      assert.equal(Number(name.style.getPropertyValue('--tree-depth')), depth);
      assert.equal(name.querySelectorAll('.tree-guides i').length, depth, 'Render every guide level, including deep branches');
    }
    assert.ok(requests.includes('weapon-catalogs/great-sword.json'));
    const expandedCount = document.querySelectorAll('.weapon-tree-table tbody tr').length;
    const toggleKey = $('[data-tree-toggle]').dataset.treeToggle;
    $('[data-tree-toggle]').click();
    await until(() => document.querySelectorAll('.weapon-tree-table tbody tr').length < expandedCount, 'Collapse a weapon branch');
    assert.equal([...document.querySelectorAll('[data-tree-toggle]')].find(b => b.dataset.treeToggle === toggleKey).getAttribute('aria-expanded'), 'false');
    assert.equal($('.weapon-browser').style.getPropertyValue('--tree-max-depth'), depthBudget);
    $('[data-tree-expand-all]').click();
    await until(() => document.querySelectorAll('.weapon-tree-table tbody tr').length === expandedCount, 'Restore complete weapon tree');
    $('.weapon-mode[href*="mode=final"]').click();
    await until(() => $('.weapon-mode.active')?.textContent === '仅最终', 'Final weapon mode');
    assert.equal(document.querySelectorAll('.weapon-tree-table tbody tr').length, 40);
    assert.ok(!$('.weapon-tree-table .tree-guides'), 'Flat final mode has no artificial indentation');
    const finalWeapon = $('.weapon-name[data-preview="weapon:site-218099"]');
    assert.equal(finalWeapon.dataset.previewLevel, '11');
    assert.match(finalWeapon.closest('tr').textContent, /320/);
    assert.match(finalWeapon.closest('tr').textContent, /智慧大剑11/);
    finalWeapon.click();
    await until(() => $('.level-button.active')?.textContent === 'Lv 11', 'Final name opens the final level');
    // happy-dom has no layout engine or @layer support. Apply only the actual
    // stat/slot rules to test the selector cascade responsible for stacked slots.
    const sourceCSS = await readFile(new URL('../web/styles.css', import.meta.url), 'utf8');
    const slotStyle = document.createElement('style');
    slotStyle.textContent = [...sourceCSS.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter(([, selector]) => /^\s*\.(?:stat(?:\b|[ >.:])|slots\b)/.test(selector)).map(([, selector, declarations]) => `${selector}{${declarations}}`).join('\n');
    document.head.append(slotStyle);
    assert.equal(window.getComputedStyle($('.stat .slots')).display, 'inline-grid', 'Slot graphic must keep its three-column grid inside weapon stats');
    assert.equal(document.querySelectorAll('.stat .slots i').length, 3);
    slotStyle.remove();
    assert.equal(document.querySelectorAll('.level-table thead th').length, 5);
    assert.equal($('.level-table tr.selected-row [data-level]').dataset.level, '11');
    assert.match($('.weapon-derivations').textContent, /Lv 2 →防卫者/);
    $('[href*="focus=weapon%3Asite-218099"]').click();
    await until(() => $('.weapon-browser') && $('#page').textContent.includes('仅此派生树'), 'Weapon detail opens its whole family tree');
    assert.match($('.weapon-tree-table').textContent, /防卫者/);
    await navigate({ kind: 'weapon', wtype: 'Great Sword', mode: 'final', element: 'Fire' }, '仅最终');
    assert.ok([...document.querySelectorAll('.weapon-elements')].every(n => n.textContent.includes('火')));
    await navigate({ kind: 'weapon', wtype: 'Bow', mode: 'final' }, '弓 · 武器派生');
    assert.ok($('.weapon-ranged'));
    assert.match($('.weapon-tree-table').textContent, /连射/);
    // Exercise the real detail route at narrow phone widths, using DOM only.
    // The stylesheet guard separately enforces fixed tables and wrapping.
    const setWidth = width => { window.happyDOM.setWindowSize({ width, height: 900 }); globalThis.innerWidth = width; };
    const performanceValue = label => [...document.querySelectorAll('.weapon-level-details dt')].find(node => node.textContent === label)?.nextElementSibling.textContent;
    setWidth(320);
    await navigate({ id: 'weapon:site-310279', level: '5' }, '无敌恐怖弩5');
    assert.equal(performanceValue('攻击力'), '370');
    assert.equal(performanceValue('装填速度'), '缓慢');
    assert.equal(performanceValue('偏移（摇晃）'), '左/大');
    assert.equal(performanceValue('后座力'), '中');
    assert.equal($('.weapon-level-details .slots').getAttribute('aria-label'), '1 个孔槽');
    const ammoRows = [...document.querySelectorAll('.ammo-level-table tbody tr')];
    const scatter = ammoRows.find(row => row.firstElementChild.textContent === '散弹');
    assert.deepEqual([...scatter.children].map(node => node.textContent), ['散弹', '3', '4', '4需技能']);
    assert.deepEqual([...document.querySelectorAll('.internal-ammo-table tbody tr')].map(row => [...row.children].map(node => node.textContent)), [['Lv1重击弹', '15', '3'], ['Lv2重击弹', '15', '3']]);
    assert.deepEqual([...document.querySelectorAll('.performance-list li')].map(node => node.textContent), ['Lv1贯通弹', 'Lv2贯通弹', 'Lv2通常弹']);
    assert.ok(!$('.weapon-level-details').closest('details'), 'Parameters are directly readable without expanding a raw-text disclosure');
    assert.ok(!$('.weapon-level-details').textContent.includes('重击弹,15,3'));
    assert.equal($('.weapon-level-details').nextElementSibling.querySelector('h2').textContent, '强化路线');
    setWidth(390);
    $('[data-level="1"]').click();
    await until(() => performanceValue('攻击力') === '220', 'Level change refreshes all detailed parameters');
    assert.deepEqual([...$('.internal-ammo-table tbody tr').children].map(node => node.textContent), ['Lv1重击弹', '8', '1']);
    setWidth(1280);
    $('[data-level="5"]').click();
    await until(() => performanceValue('攻击力') === '370', 'Return to final bowgun level');
    assert.equal(requests.filter(path => path === 'weapon-details/310279.json').length, 1, 'Changing levels reuses the same small detail file');
    await navigate({ id: 'weapon:site-219234', level: '11' }, '速射硬直');
    assert.deepEqual([...$('.rapid-fire-table tbody tr').children].map(node => node.textContent), ['碎石弹', '3', '小']);
    await navigate({ id: 'weapon:site-219233', level: '11' }, '蓄力攻击');
    assert.equal(document.querySelectorAll('.bow-charge-table tbody tr').length, 4);
    assert.match($('.bow-charge-table tbody tr:last-child').textContent, /第 4 阶段.*扩散4.*需装填数UP/);
    assert.equal(document.querySelectorAll('.bow-coating-table tbody tr').length, 11);
    await navigate({ id: 'weapon:site-219226', level: '11' }, '狩猎笛旋律');
    assert.match($('.melody-table').textContent, /白 → 红 → 红.*攻击力強化【小】/);
    assert.equal($('#menu-toggle').textContent, '分类');
    assert.equal($('#menu-toggle').getAttribute('aria-controls'), 'sidebar');
    $('#menu-toggle').click();
    assert.ok($('#sidebar').classList.contains('open'));
    assert.equal(document.querySelectorAll('#navigation .nav-link').length, 10);
    $('#menu-toggle').click();
    assert.ok(!$('#sidebar').classList.contains('open'));
    $('#search').value = '贝鲁纳大剑';
    $('#search-form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
    await until(() => $('h1')?.textContent === '搜索结果', 'Search');
    const weaponLink = $('.record-name a');
    assert.match(weaponLink.textContent, /贝鲁纳大剑/);
    weaponLink.click();
    await until(() => $('.level-picker'), 'Weapon detail');
    $('[data-level="3"]').click();
    await until(() => $('.level-button.active')?.textContent === 'Lv 3', 'Level selection');
    assert.match(window.location.hash, /level=3/);
    const material = [...document.querySelectorAll('.detail-aside .entity-link')].find(link => link.textContent === '圆盘石');
    assert.ok(material);
    material.click();
    await until(() => $('h1')?.textContent === '圆盘石', 'Material sources');
    assert.match($('#page').textContent, /91 条/);
    const rank = $('[data-route-select="rank"]');
    rank.value = 'G';
    rank.dispatchEvent(new window.Event('change', { bubbles: true }));
    // happy-dom 21 miscomputes select.value after parsing innerHTML; check the
    // selected attribute and actual filtered rows instead of its selection model.
    await until(() => $('[data-route-select="rank"] option[value="G"]')?.hasAttribute('selected') && /rank=G/.test(window.location.hash), 'Rank filter');
    const rows = [...document.querySelectorAll('tbody tr')];
    assert.ok(rows.length > 0 && rows.every(row => row.querySelector('.gathering-location .badge')?.textContent === 'G 位'));
    assert.equal(document.querySelectorAll('.gathering-table thead th').length, 4);
    assert.match($('.gathering-table tbody tr').textContent, /区.*点.*采集/);
    $('tbody .entity-link').click();
    await until(() => $('.map-layout'), 'Source map');
    assert.ok([...document.querySelectorAll('.map-layout img')].every(img => img.src.startsWith('https://mhxx.test/games/mhxx/assets/')));
    await navigate({ id: 'map:site-2400', area: '1', rank: 'G' }, '本地图任务');
    assert.equal($('.map-quests').previousElementSibling, $('.map-layout'), 'Tasks follow the entire map and gathering layout');
    assert.match($('.map-quests .panel-heading').textContent, /129 条/);
    const mapTasks = [];
    for (let pageNumber = 1; pageNumber <= 4; pageNumber++) {
      mapTasks.push(...[...document.querySelectorAll('.map-quest-table tbody td:first-child a')].map(link => link.hash));
      if (pageNumber < 4) {
        $('.map-quests [aria-label="下一页"]').click();
        await until(() => $('.map-quests .current-page')?.textContent.startsWith(String(pageNumber + 1)), 'Map task pagination');
      }
    }
    assert.equal(mapTasks.length, 129);
    assert.equal(new Set(mapTasks).size, 129);
    assert.match(window.location.hash, /area=1&rank=G/);
    assert.equal($('.map-layout .filter-chip.active').textContent, 'G 位');
    $('.map-quest-table tbody .entity-link').click();
    await until(() => $('#page').textContent.includes('任务信息'), 'Map task opens its details');
    await navigate({ id: 'item:site-189643' }, '药草');
    assert.match($('#page').textContent, /337 条/);
    assert.ok(requests.includes('data/v1/items/189643/gathering/4.json'));
    $('[aria-label="下一页"]').click();
    await until(() => /41–80/.test($('#page').textContent), 'Material pagination');
    $('[data-save]').click();
    assert.deepEqual(JSON.parse(localStorage.getItem('mhxx.saved.v1')), ['item:site-189643']);
    await navigate({ saved: '1' }, '收藏夹');
    assert.equal(document.querySelectorAll('.catalog-table tbody tr').length, 1);
    assert.equal($('.record-name a').textContent, '药草');
    $('.brand').click();
    await until(() => $('.home-personal'), 'Homepage saved and recent shortcuts');
    assert.match($('.home-personal').textContent, /我的收藏.*药草/);
    assert.match($('.home-personal').textContent, /最近浏览/);
    for (const [id, expected, required] of [
      ['monster:site-1829', '斩龙', '部位肉质'],
      ['quest:site-218315', '村★1讨伐跳狗龙群！', '跳狗龙10头的讨伐'],
      ['armor:site-218352', '贝鲁纳头巾', '生产与强化配方'],
      ['skill:site-183534', '技能发动', '精灵加护'],
      ['combining:site-210126', 'LV2通常弾', '空心果'],
      ['weapon:site-292565', '强化路线', '-45/20'],
    ]) {
      await navigate({ id }, expected);
      assert.match($('#page').textContent, new RegExp(required));
      assert.doesNotMatch($('#page').textContent, /undefined|NaN|\[object Object\]|暂时无法读取/);
    }
    await navigate({ id: 'monster:site-1829' }, '出现怪物');
    assert.deepEqual([...document.querySelectorAll('[data-relation]')].map(panel => panel.dataset.relation), ['rewards', 'quests']);
    assert.ok(!$('.tabs'), 'Monster rewards and quests stay visible without choosing a tab');
    assert.ok($('.reward-table'));
    assert.match($('#page').textContent, /数据说明/);
    assert.match($('#page').textContent, /赤热时/, 'Retain the actual monster state explanation');
    const questRow = [...document.querySelectorAll('.monster-quest-table tbody tr')].find(r => r.textContent.includes('灼热之刃'));
    assert.ok(questRow);
    assert.match(questRow.textContent, /斩龙1头的狩猎/);
    assert.match(questRow.textContent, /古代林/);
    assert.equal(questRow.querySelector('.strength-track.health').getAttribute('aria-label'), '体力相对强度 12 / 100');
    assert.equal(questRow.querySelector('.strength-track.defense i').style.width, '5%');
    assert.match($('.monster-quest-table').textContent, /本怪物乱入/);
    assert.match($('.quest-strength-note').textContent, /非实际血量或防御率/);
    assert.equal(document.querySelectorAll('.monster-quest-table thead th').length, 3);
    assert.match(questRow.children[0].textContent, /古代林/);
    assert.ok(!$('.hitzone-table').hasAttribute('tabindex'), 'Data tables are no longer scroll controls');
    assert.equal(document.querySelectorAll('.hitzone-table thead th').length, 10);
    const firstQuest = $('.monster-quest-table tbody .entity-link').href;
    $('[data-relation="rewards"] [aria-label="下一页"]').click();
    await until(() => /41–80/.test($('[data-relation="rewards"] .catalog-footer')?.textContent), 'Reward pagination');
    assert.equal($('.monster-quest-table tbody .entity-link').href, firstQuest);
    $('[data-relation="quests"] [aria-label="下一页"]').click();
    await until(() => /41–50/.test($('[data-relation="quests"] .catalog-footer')?.textContent), 'Monster quest pagination');
    assert.match($('[data-relation="rewards"] .catalog-footer').textContent, /41–80/);
    const rewardRank = $('[data-route-select="rewardsRank"]');
    rewardRank.value = 'G';
    rewardRank.dispatchEvent(new window.Event('change', { bubbles: true }));
    await until(() => $('[data-route-select="rewardsRank"] option[value="G"]')?.hasAttribute('selected'), 'Independent reward rank filter');
    assert.match($('[data-relation="rewards"] .catalog-footer').textContent, /^1–/);
    assert.ok([...document.querySelectorAll('.reward-table tbody tr')].every(row => row.children[1].textContent === 'G 位'));
    assert.match($('[data-relation="quests"] .catalog-footer').textContent, /41–50/);
    await navigate({ id: 'monster:site-1829', tab: 'quests', page: '2' }, '出现怪物');
    assert.match($('[data-relation="quests"] .catalog-footer').textContent, /41–50/, 'Old quest-tab deep links retain their page');
    await navigate({ id: 'monster:site-1829', tab: 'rewards' }, '条件 / 奖励组');
    assert.equal($('.reward-table thead th:last-child').textContent, '概率');
    assert.match($('.reward-table tbody td:last-child').textContent, /%/);
    await navigate({ id: 'item:site-99999999' }, '这条资料不存在');
    assert.ok($('[data-retry]'));
    $('#menu-toggle').click();
    assert.equal($('#menu-toggle').getAttribute('aria-expanded'), 'true');
    document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    assert.equal($('#menu-toggle').getAttribute('aria-expanded'), 'false');
    document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true }));
    assert.equal(document.activeElement, $('#search'));
  } finally { await window.happyDOM.abort(); window.close(); }
});
