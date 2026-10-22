"""Retain the original homepage's reference navigation without its news feed."""

import hashlib
import posixpath
from pathlib import Path
from urllib.parse import urlsplit

from lxml import html

SITE_URL = "https://charleslth.github.io/games/mhxx/"


def source_path(page, href):
    url = urlsplit(href)
    if url.scheme or url.netloc or not url.path:
        return None
    path = posixpath.normpath(posixpath.join(posixpath.dirname(page), url.path))
    return path if path.startswith(("data/", "ida/")) and path.endswith(".html") else None


def build_homepage(site_root, entities, entries, revision):
    site_root = Path(site_root)
    homepage = "index/index.html"
    raw = (site_root / homepage).read_bytes()
    document = html.fromstring(raw)
    by_page = {e["source"]["page"]: e for e in entities}
    entry_by_id = {e["id"]: e for e in entries}
    categories, sources, sections = {}, {homepage: hashlib.sha256(raw).hexdigest()}, {}

    def category(page, kind, label):
        key = f"{kind}-{Path(page).stem}"
        if key in categories:
            return categories[key]
        raw = (site_root / page).read_bytes()
        tree = html.fromstring(raw)
        sources[page] = hashlib.sha256(raw).hexdigest()
        # Quest and armor headings identify actual list entries, excluding
        # ingredients, prerequisite quests and other links inside their details.
        xpath = '//div[contains(concat(" ",normalize-space(@class)," ")," panel-heading ")]//a[@href]' if kind in ("quest", "armor") else '//table//a[@href]'
        ids = set()
        for link in tree.xpath(xpath):
            target = by_page.get(source_path(page, link.get("href")))
            if target and target["kind"] == kind:
                ids.add(target["id"])
        if not ids:
            return None
        for entity_id in sorted(ids):
            entry_by_id[entity_id].setdefault("groups", []).append(key)
        result = {"key": key, "kind": kind, "label": label, "count": len(ids), "source_page": page}
        categories[key] = result
        return result

    def convert(link, section):
        label = " ".join(link.text_content().split())
        page = source_path(homepage, link.get("href"))
        if not page or not (site_root / page).is_file():
            raise ValueError(f"Missing original homepage target: {link.get('href')}")
        result = {"label": label, "source_page": page}
        # Status tags are siblings of the link, not part of its text.
        sibling = link.getnext()
        if sibling is not None and sibling.tag == "span":
            marker = "".join(sibling.text_content().split())
            if marker in ("[新]", "[再]"):
                result["marker"] = marker
        target = by_page.get(page)
        if target:
            return {**result, "route": {"id": target["id"]}, "kind": target["kind"]}
        all_pages = {"data/2300.html": "armor", "data/2100.html": "item", "data/2200.html": "skill", "data/2503.html": "combining"}
        if page in all_pages:
            return {**result, "route": {"kind": all_pages[page]}}
        kind = {"防具": "armor", "道具": "item", "技能": "skill", "任务": "quest", "怪物": "monster"}.get(section)
        # Unlock guides retain their explanatory context in the original page.
        guides = {"data/2824.html", "data/2950.html", "data/2951.html", "data/2952.html", "data/2953.html", "data/2208.html"}
        if kind and page not in guides:
            group = category(page, kind, label)
            if group:
                return {**result, "route": {"kind": kind, "group": group["key"]}, "count": group["count"]}
        return {**result, "url": SITE_URL + page}

    for table in document.xpath('//table[contains(concat(" ",normalize-space(@class)," ")," t0 ")]'):
        title = " ".join(table.xpath('.//th')[0].text_content().split())
        links, groups, seen = [], [], set()
        current_group = None
        for row in table.xpath('./tr|./tbody/tr'):
            headings = row.xpath('./th')
            if title == "怪物" and headings:
                name = " ".join(headings[0].text_content().split())
                if name not in (title, "一览"):
                    current_group = {"label": name, "links": []}
                    groups.append(current_group)
            for anchor in row.xpath('.//a[@href]'):
                value = convert(anchor, title)
                if value["source_page"] in seen:
                    continue
                seen.add(value["source_page"])
                links.append(value)
                if current_group is not None:
                    current_group["links"].append(value)
        sections[title] = {"links": links, "groups": groups}

    weapon_counts = {}
    for entry in entries:
        if entry["kind"] == "weapon":
            kind = entry["weapon_type"]
            weapon_counts[kind] = weapon_counts.get(kind, 0) + 1
    return {"dataset_revision": revision, "sections": sections, "categories": categories,
            "weapon_counts": weapon_counts, "source_pages": sources}
