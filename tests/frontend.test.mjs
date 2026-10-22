import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { prepareIndex, queryIndex } from '../web/search-core.mjs';
import { esc, refLink, route, sharpness, percent, slots } from '../web/ui.mjs';
import { prepareWeapons, queryWeapons } from '../web/weapon-browser.mjs';
import { prepareArmor, queryArmor, groupArmorPieces } from '../web/armor-browser.mjs';
import { questFilterState } from '../web/quest-browser.mjs';

const document = JSON.parse(await readFile(new URL('../games/mhxx/browse-index.json', import.meta.url)));
const index = prepareIndex(document.items);
const home = JSON.parse(await readFile(new URL('../games/mhxx/home-data.json', import.meta.url)));
const weapons = prepareWeapons(JSON.parse(await readFile(new URL('../games/mhxx/weapon-catalogs/great-sword.json', import.meta.url))));
const armor = prepareArmor(JSON.parse(await readFile(new URL('../games/mhxx/armor-catalog.json', import.meta.url))));

test('quest categories, progression flags and types combine without guessing from names', () => {
  const totals = { village: 370, guild: 569, permit: 228, arena: 17, challenge: 20, event: 133 };
  for (const [questHub, count] of Object.entries(totals)) assert.equal(queryIndex(index, { kind: 'quest', questHub }).total, count);
  assert.equal(queryIndex(index, { kind: 'quest', questFlag: 'key' }).total, 122);
  assert.equal(queryIndex(index, { kind: 'quest', questFlag: 'urgent' }).total, 29);
  assert.equal(queryIndex(index, { kind: 'quest', questFlag: 'progression' }).total, 151);
  assert.equal(queryIndex(index, { kind: 'quest', questHub: 'guild', questFlag: 'key' }).total, 60);
  const g4 = queryIndex(index, { kind: 'quest', questHub: 'guild', questFlag: 'key', group: 'quest-2996', questType: '狩猎' });
  assert.equal(g4.total, 6);
  assert.ok(g4.items.every(quest => quest.name.startsWith('G★4')));
  const captures = queryIndex(index, { kind: 'quest', questHub: 'village', group: 'quest-2014', questType: '捕获' });
  assert.deepEqual(new Set(captures.items.map(quest => quest.id)), new Set(['quest:site-219992', 'quest:site-220211']));
  assert.equal(queryIndex(index, { kind: 'quest', questHub: 'permit', questFlag: 'key' }).total, 0);
  assert.deepEqual(questFilterState({ group: 'quest-2987' }, home), { hub: 'guild', flag: 'progression', type: '' });
  assert.deepEqual(questFilterState({ group: 'quest-2011' }, home), { hub: 'village', flag: '', type: '' });
  const ids = [];
  for (let page = 1; page <= 4; page++) ids.push(...queryIndex(index, { kind: 'quest', questFlag: 'key', page }).items.map(quest => quest.id));
  assert.equal(ids.length, 122);
  assert.equal(new Set(ids).size, 122);
});

test('map task pagination covers every destination quest across ranks and day/night', () => {
  const seen = [];
  for (let page = 1; page <= 4; page++) {
    const result = queryIndex(index, { kind: 'quest', destination: 'map:site-2400', page });
    assert.equal(result.total, 129);
    assert.equal(result.page, page);
    assert.equal(result.items.length, page === 4 ? 9 : 40);
    seen.push(...result.items);
  }
  assert.equal(new Set(seen.map(quest => quest.id)).size, 129);
  assert.ok(seen.some(quest => quest.extra.includes('<昼>')));
  assert.ok(seen.some(quest => quest.extra.includes('<夜>')));
  assert.ok(seen.some(quest => quest.name.startsWith('G★')));
  assert.ok(!seen.some(quest => quest.id === 'quest:site-219992'), 'Volcano capture quest must not appear in Ancient Forest');
  assert.equal(queryIndex(index, { destination: 'map:site-unknown' }).total, 0);
});

test('armor defaults retain common or paired variants and paginate whole sets', () => {
  const seen = [];
  const initial = queryArmor(armor);
  assert.equal(initial.total, 656);
  assert.equal(queryArmor(armor, { group: 'armor-2301' }).total, 30);
  assert.equal(queryArmor(armor, { group: 'armor-2998' }).total, 66);
  assert.equal(queryArmor(armor, { type: 'common' }).total, 60);
  assert.equal(queryArmor(armor, { type: 'blade' }).total, 596);
  for (let page = 1; page <= initial.totalPages; page++) {
    const result = queryArmor(armor, { page });
    for (const set of result.sets) {
      assert.ok(set.variants.length === 1 && set.variants[0].type === 'common' || set.variants.length === 2 && set.variants[0].type === 'blade' && set.variants[1].type === 'gunner');
      seen.push(set.id);
    }
  }
  assert.equal(new Set(seen).size, 656);
  assert.throws(() => queryArmor(armor, { group: 'not-a-category' }), /分类不存在/);
});

test('armor search includes original names, piece aliases and skill points without combining hunter types', async () => {
  assert.equal(queryArmor(armor, { query: '贝鲁纳头巾' }).sets[0].id, 'armor:site-218352');
  assert.ok(queryArmor(armor, { query: '身体系统加倍' }).total > 0);
  const hunting = armor.sets.find(s => s.id === 'armor:site-219748');
  assert.deepEqual(hunting.variants.map(v => [v.summary.defense, v.summary.max_defense, v.summary.slots]), [[10, 250, 4], [5, 250, 4]]);
  const entity = JSON.parse(await readFile(new URL('../games/mhxx/data/v1/armor/226291.json', import.meta.url)));
  const grouped = groupArmorPieces(entity.data.pieces);
  const source = armor.sets.find(s => s.id === entity.id);
  for (const variant of grouped) {
    const expected = source.variants.find(v => v.type === variant.type).summary;
    assert.equal(variant.summary.defense, expected.defense);
    assert.deepEqual(Object.fromEntries(variant.summary.skills.map(s => [s.skill.id, s.points])), Object.fromEntries(expected.skills.map(s => [s.skill.id, s.points])));
    assert.equal(variant.summary.skills.find(s => s.label === '会心强化').points, 5, 'Preserve original raw sums, not an inferred activated Torso Up effect');
  }
});

test('weapon modes retain actual final levels, branch points and level-specific performance', () => {
  const final = queryWeapons(weapons, { mode: 'final', query: '贝鲁纳大剑' });
  assert.equal(final.total, 1);
  assert.equal(final.rows[0].node.key, 'weapon:site-218099@11');
  assert.equal(final.rows[0].node.attack, 320);
  assert.equal(final.rows[0].node.slots, 3);
  assert.equal(queryWeapons(weapons, { mode: 'final' }).total, 136);
  assert.equal(queryWeapons(weapons, { mode: 'first' }).total, 136);
  const branch = queryWeapons(weapons, { mode: 'branch', focus: 'weapon:site-218099' });
  assert.ok(branch.rows.some(r => r.node.key === 'weapon:site-218099@2'));
  assert.ok(!branch.rows.some(r => r.node.key === 'weapon:site-218099@7'));
  assert.ok(branch.rows.some(r => r.node.key === 'weapon:site-220141@1'));
  assert.equal(weapons.byKey.get('weapon:site-220141@1').parent, 'weapon:site-218099@2');
});

test('weapon tree pagination keeps complete trees and collapse never changes matching counts', () => {
  const seen = [];
  const initial = queryWeapons(weapons);
  for (let page = 1; page <= initial.totalPages; page++) {
    const result = queryWeapons(weapons, { page });
    const keys = new Set(result.rows.map(r => r.node.key));
    const byKey = new Map(result.rows.map(r => [r.node.key, r]));
    for (const row of result.rows) {
      assert.equal(row.trails.length, Math.max(0, row.depth - 1));
      if (row.node.parent) {
        assert.ok(keys.has(row.node.parent));
        assert.equal(row.depth, byKey.get(row.node.parent).depth + 1, 'Every upgrade keeps its own indentation level');
      } else assert.equal(row.depth, 0);
    }
    assert.equal(result.maxDepth, Math.max(...result.rows.map(r => r.depth)));
    seen.push(...keys);
  }
  assert.equal(new Set(seen).size, weapons.nodes.length);
  const root = initial.rows[0].node.key;
  const collapsed = queryWeapons(weapons, { collapsed: new Set([root]) });
  assert.equal(collapsed.total, initial.total);
  assert.ok(collapsed.rows.length < initial.rows.length);
  assert.equal(collapsed.maxDepth, initial.maxDepth, 'Collapsing must not rescale the remaining branches');
  assert.equal(collapsed.rows.filter(r => r.node.root === root).length, 1);
  assert.deepEqual(queryWeapons(weapons).rows.map(r => r.node.key), initial.rows.map(r => r.node.key));
});

test('weapon element filters keep contextual ancestors and final sorting uses the displayed attack', () => {
  const fire = queryWeapons(weapons, { mode: 'final', element: 'Fire', sort: 'attack' });
  assert.ok(fire.rows.length > 0);
  assert.ok(fire.rows.every(r => r.node.final && r.node.elements.some(([e]) => e === 'Fire')));
  assert.ok(fire.rows.every((r, i, rows) => !i || rows[i - 1].node.attack >= r.node.attack));
  const tree = queryWeapons(weapons, { mode: 'branch', query: '防卫者' });
  assert.ok(tree.rows.some(r => r.context && r.node.key === 'weapon:site-218099@2'));
  assert.ok(tree.rows.some(r => !r.context && r.node.id === 'weapon:site-220141'));
  assert.equal(queryWeapons(weapons, { query: 'nonexistent weapon' }).rows.length, 0);
});

test('original homepage categories filter complete records without keyword approximations', () => {
  for (const category of Object.values(home.categories)) {
    const result = queryIndex(index, { kind: category.kind, group: category.key });
    assert.equal(result.total, category.count, category.key);
    assert.ok(result.total > 0);
    assert.ok(result.items.every(e => e.kind === category.kind && e.groups.includes(category.key)));
  }
  const village1 = queryIndex(index, { kind: 'quest', group: 'quest-2011' });
  const village10 = queryIndex(index, { kind: 'quest', group: 'quest-2020' });
  assert.equal(village1.total, 7);
  assert.equal(village10.total, 50);
  assert.ok(village1.items.every(e => !e.groups.includes('quest-2020')));
  assert.equal(queryIndex(index, { kind: 'monster', group: 'monster-2501' }).total, 94);
  assert.equal(queryIndex(index, { kind: 'monster', group: 'monster-2502' }).total, 36);
  assert.equal(queryIndex(index, { kind: 'item', group: 'item-2112' }).total, 48);
  assert.equal(queryIndex(index, { kind: 'armor', group: 'missing' }).total, 0);
});

test('all 6577 entities are searchable; aliases and full-width names work', () => {
  assert.equal(index.length, 6577);
  assert.equal(queryIndex(index, { query: '智慧大剑11' }).items[0].id, 'weapon:site-218099');
  assert.ok(queryIndex(index, { query: 'ＬＶ２通常弾' }).items.some(e => e.kind === 'combining'));
  assert.equal(queryIndex(index, { query: '%' }).total, 0);
  assert.equal(queryIndex(index, { query: '药　草' }).items[0].name, '药草');
});

test('weapon filters, attack sorting and pagination cover the full index exactly once', () => {
  const filtered = queryIndex(index, { kind: 'weapon', weaponType: 'Great Sword', sort: 'attack' });
  assert.ok(filtered.total > 40);
  assert.ok(filtered.items.every(e => e.weapon_type === 'Great Sword'));
  assert.ok(filtered.items.every((e, i, list) => i === 0 || e.attack_max <= list[i - 1].attack_max));
  const ids = [];
  const total = queryIndex(index, { kind: 'weapon' }).total;
  for (let page = 1; page <= Math.ceil(total / 40); page++) ids.push(...queryIndex(index, { kind: 'weapon', page }).items.map(e => e.id));
  assert.equal(total, 1592);
  assert.equal(new Set(ids).size, total);
  assert.equal(queryIndex(index, { kind: 'weapon', page: 9999 }).page, Math.ceil(total / 40));
});

test('saved filters and global counts reflect selected names without inventing results', () => {
  const saved = ['weapon:site-218099', 'item:site-189643', 'item:site-9999999'];
  const result = queryIndex(index, { saved });
  assert.equal(result.total, 2);
  assert.equal(result.counts.weapon, 1);
  assert.equal(result.counts.item, 1);
  assert.equal(queryIndex(index, { saved, kind: 'map' }).total, 0);
  assert.equal(queryIndex(index, { saved: [] }).total, 0);
});

test('source labels and unknown values remain safe and distinguishable in HTML', () => {
  const unsafe = '<img src=x onerror="alert(1)">';
  assert.equal(esc(unsafe), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
  assert.ok(!refLink({ id: 'item:site-1', name: unsafe }).includes('<img'));
  assert.match(percent(null), /未记载/);
  assert.match(percent(0), /^0/);
  assert.match(slots(0), /0 个孔槽/);
  assert.match(sharpness([1, 2, 3, 0, 0, 0, 0]), /role="img"/);
  const values = Object.fromEntries(new URLSearchParams(route({ id: 'map:site-2400', area: '秘境', rank: 'G' }).slice(1)));
  assert.deepEqual(values, { id: 'map:site-2400', area: '秘境', rank: 'G' });
});

test('responsive sharpness retains a common scale across base and handicraft bars', () => {
  const widths = values => [...sharpness(values).matchAll(/width:([\d.]+)%/g)].map(m => Number(m[1]));
  const base = widths([18, 36, 36, 0, 0, 0, 0]);
  const extended = widths([18, 36, 36, 90, 0, 0, 0]);
  assert.deepEqual(base, [10, 20, 20, 0, 0, 0, 0]);
  assert.deepEqual(extended, [10, 20, 20, 50, 0, 0, 0]);
  assert.equal(base.reduce((a, b) => a + b), 50, 'Shorter base bars must not stretch to the full upgraded length');
  assert.equal(extended.reduce((a, b) => a + b), 100);
  assert.equal((slots(2).match(/class="filled"/g) || []).length, 2);
  assert.equal((slots(2).match(/class="empty"/g) || []).length, 1);
});

test('project layout policy prevents scroll strips and oversized table minimum widths', async () => {
  // Static guard for the explicit project constraint. This is not a browser
  // layout measurement; happy-dom intentionally does not provide one.
  const css = (await readFile(new URL('../web/styles.css', import.meta.url), 'utf8')).replace(/\/\*[\s\S]*?\*\//g, '');
  for (const [, selector, declarations] of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    assert.doesNotMatch(declarations, /(?:^|;)\s*overflow(?:-x)?\s*:\s*(?:auto|scroll)\b/, selector);
    if (/(?:table|\.tabs|\.panel|^\s*(?:body|main)\b)/.test(selector)) {
      assert.doesNotMatch(declarations, /(?:^|;)\s*min-width\s*:\s*[1-9]/, selector);
      assert.doesNotMatch(declarations, /(?:^|;)\s*overflow(?:-x)?\s*:\s*(?:hidden|clip)\b/, selector);
    }
  }
  const html = await readFile(new URL('../web/index.html', import.meta.url), 'utf8');
  assert.match(html, /name="viewport" content="width=device-width/);
});
