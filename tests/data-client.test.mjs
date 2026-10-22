import assert from "node:assert/strict";

const baseUrl = process.argv[2];
const moduleResponse = await fetch(new URL("client.mjs", baseUrl));
assert.match(moduleResponse.headers.get("content-type"), /javascript/);
const code = await moduleResponse.text();
const { createDataClient } = await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
const api = createDataClient({ baseUrl });
const manifest = await api.manifest();
assert.equal(manifest.entity_counts.weapon, 1592);

const found = await api.search("贝鲁纳大剑", { kind: "weapon" });
assert.ok(found.items.some(r => r.id === "weapon:site-218099"));
const weapon = await api.get("weapon:site-218099");
const level3 = weapon.data.levels.find(l => l.level === 3);
const ingredient = level3.recipes[0].ingredients[0];
assert.equal(ingredient.quantity, 2);
const stone = await api.get(ingredient.item);
assert.equal(stone.name, "圆盘石");
assert.equal(stone.relations.gathering.total, 91);
const source = (await api.page(stone.relations.gathering)).items[0];
const map = await api.get(source.map);
assert.equal(map.kind, "map");

const herb = await api.get("item:site-189643");
let gathered = 0;
for await (const entry of api.iterate(herb.relations.gathering)) {
  assert.ok(entry.map.href.startsWith("maps/"));
  gathered++;
}
assert.equal(gathered, 337); // All four pages, not merely the first sample.
const catalog = await api.list("item", 2);
assert.equal(catalog.page, 2);
assert.equal(catalog.items.length, 100);
const ammo = await api.search("ＬＶ２通常弾", { kind: "combining" });
assert.equal(ammo.total, 1);
const ammoRecipe = await api.get(ammo.items[0]);
assert.equal(ammoRecipe.data.result, null);
assert.deepEqual([ammoRecipe.data.amount_min, ammoRecipe.data.amount_max], [2, 4]);
const potion = await api.get("item:site-188416");
assert.deepEqual((await api.page(potion.relations.gathering)).items, []);
assert.equal((await api.search("%", { kind: "item" })).total, 0);

await assert.rejects(() => api.get({ id: "item:site-1", href: "../outside.json" }), /relative API href/);
await assert.rejects(() => api.get("item:site-999999999"), /404/);
await assert.rejects(() => api.page(herb.relations.gathering, 999), /outside/);
await assert.rejects(() => api.search("x", { limit: 0 }), /limit/);

const inconsistent = createDataClient({ baseUrl, fetch: async (url, options) => {
  const response = await fetch(url, options);
  const doc = await response.json();
  if (url.pathname.endsWith("items/188416.json")) doc.dataset_revision = "changed";
  return { ok: true, json: async () => doc };
} });
await assert.rejects(() => inconsistent.get("item:site-188416"), /Dataset changed/);
console.log(JSON.stringify({ status: "ok", gathered, prefix: new URL(baseUrl).pathname }));
