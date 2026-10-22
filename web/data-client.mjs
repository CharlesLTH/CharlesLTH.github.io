/** Static MHXX API v1 client. All hrefs are relative to the API root. */
const directories = Object.freeze({
  weapon: "weapons", item: "items", monster: "monsters", quest: "quests",
  armor: "armor", skill: "skills", map: "maps", combining: "combining",
});

const normalize = value => value.normalize("NFKC").toLowerCase().replace(/\s+/gu, "");

export function createDataClient({ baseUrl, fetch: fetcher = globalThis.fetch } = {}) {
  if (!baseUrl || typeof fetcher !== "function") throw new TypeError("baseUrl and fetch are required");
  const root = new URL(baseUrl, globalThis.location?.href);
  if (!root.pathname.endsWith("/")) root.pathname += "/";
  if (!["http:", "https:"].includes(root.protocol) || root.search || root.hash) {
    throw new TypeError("baseUrl must be an HTTP(S) API directory without a query or fragment");
  }
  const cache = new Map();
  let manifestPromise;

  function resolve(href) {
    if (typeof href !== "string" || !href || href.includes("\\") || href.includes(":") || href.startsWith("/") ||
        href.split("/").some(part => !part || part === "." || part === "..") || /[%?#]/u.test(href)) {
      throw new TypeError("Expected a relative API href");
    }
    const url = new URL(href, root);
    if (url.origin !== root.origin || !url.pathname.startsWith(root.pathname)) throw new TypeError("API href escaped its root");
    return url;
  }

  async function read(href) {
    const url = resolve(href);
    if (!cache.has(href)) {
      const pending = (async () => {
        const response = await fetcher(url, { credentials: "omit" });
        if (!response.ok) throw new Error(`MHXX API ${response.status}: ${href}`);
        const doc = await response.json();
        if (doc.api_version !== 1 || typeof doc.dataset_revision !== "string") throw new Error("Unsupported MHXX API response");
        if (href === "manifest.json" && (doc.type !== "manifest" || doc.generator !== "mhxx-static-api")) {
          throw new Error("Invalid MHXX API manifest");
        }
        if (href !== "manifest.json") {
          const manifest = await getManifest();
          if (doc.dataset_revision !== manifest.dataset_revision) throw new Error("Dataset changed; create a new client and retry");
        }
        return doc;
      })();
      cache.set(href, pending);
      pending.catch(() => cache.delete(href));
    }
    return cache.get(href);
  }

  function getManifest() {
    if (!manifestPromise) {
      manifestPromise = read("manifest.json").catch(error => { manifestPromise = undefined; throw error; });
    }
    return manifestPromise;
  }

  async function get(entity) {
    let id, href;
    if (typeof entity === "string") {
      const match = /^([a-z]+):site-(\d+)$/u.exec(entity);
      if (!match || !directories[match[1]]) throw new TypeError("Expected a typed site entity ID");
      id = entity;
      href = `${directories[match[1]]}/${match[2]}.json`;
    } else {
      id = entity?.id;
      href = entity?.href;
    }
    if (typeof id !== "string") throw new TypeError("Expected an entity reference");
    await getManifest();
    const doc = await read(href);
    if (doc.type !== "entity" || doc.id !== id) throw new Error("Entity reference does not match its target");
    return doc;
  }

  async function page(collection, number = 1) {
    if (!collection || collection.type !== "collection" || !Number.isSafeInteger(number) || number < 1) {
      throw new TypeError("Expected a collection descriptor and a positive page number");
    }
    if (!Number.isSafeInteger(collection.total) || collection.total < 0 || !Number.isSafeInteger(collection.page_size) || collection.page_size < 1) {
      throw new TypeError("Invalid collection descriptor");
    }
    if (collection.total === 0 && number === 1) return { type: "collection_page", total: 0, page: 1, items: [], links: { next: null, previous: null } };
    if (number > Math.ceil(collection.total / collection.page_size)) throw new RangeError("Page is outside the collection");
    if (typeof collection.href !== "string" || !collection.href.endsWith("/1.json")) throw new TypeError("Invalid collection href");
    await getManifest();
    const doc = await read(collection.href.replace(/\/1\.json$/u, `/${number}.json`));
    if (doc.type !== "collection_page" || doc.page !== number || doc.total !== collection.total || doc.page_size !== collection.page_size) {
      throw new Error("Collection page does not match its descriptor");
    }
    return doc;
  }

  async function* iterate(collection) {
    const count = Math.ceil(collection.total / collection.page_size);
    for (let n = 1; n <= Math.max(1, count); n++) {
      for (const item of (await page(collection, n)).items) yield item;
    }
  }

  async function list(kind, number = 1) {
    if (!directories[kind]) throw new TypeError("Unknown entity kind");
    return page((await getManifest()).catalogs[kind], number);
  }

  async function search(query, { kind, offset = 0, limit = 20 } = {}) {
    if (typeof query !== "string" || (kind !== undefined && !directories[kind])) throw new TypeError("Invalid search query or kind");
    if (!Number.isSafeInteger(offset) || offset < 0 || !Number.isSafeInteger(limit) || limit < 1 || limit > 100) {
      throw new RangeError("Search requires offset >= 0 and limit between 1 and 100");
    }
    const term = normalize(query);
    if (!term) return { total: 0, offset, limit, items: [] };
    const manifest = await getManifest();
    const index = await read(manifest.search.href);
    const matches = index.items.filter(entry => (!kind || kind === entry.kind) && entry.terms.some(name => normalize(name).includes(term)));
    return { total: matches.length, offset, limit, items: matches.slice(offset, offset + limit).map(({ terms, ...entry }) => entry) };
  }

  return Object.freeze({ manifest: getManifest, get, page, iterate, list, search });
}
