"""Readable weapon performance, retaining source rows and availability markers."""

from copy import deepcopy
import hashlib
import re
from pathlib import Path

from lxml import html

from .html_source import ELEMENTS, restore_values, segments, text

AMMO = {
    "通": "通常弹", "贯": "贯通弹", "散": "散弹", "徹": "彻甲榴弹", "扩": "扩散弹",
    "回": "回复弹", "毒": "毒弹", "麻": "麻痹弹", "睡": "睡眠弹", "灭": "减气弹", "减": "减气弹",
    "火": "火炎弹", "水": "水冷弹", "雷": "电击弹", "冰": "冰结弹", "龙": "灭龙弹",
    "捕": "捕获用麻醉弹", "染": "染色弹",
}
AMMO_ORDER = ["通常弹", "贯通弹", "散弹", "彻甲榴弹", "扩散弹", "回复弹", "毒弹", "麻痹弹", "睡眠弹", "减气弹",
              "火炎弹", "水冷弹", "电击弹", "冰结弹", "灭龙弹", "捕获用麻醉弹", "染色弹"]
COATINGS = {"強1": "Lv1 强击瓶", "強2": "Lv2 强击瓶", "属1": "Lv1 属性强化瓶", "属2": "Lv2 属性强化瓶",
            "接": "接击瓶", "染": "染色瓶", "毒": "毒瓶", "麻": "麻痹瓶", "睡": "睡眠瓶", "减": "减气瓶", "爆": "爆破瓶"}
NOTE_COLORS = {"#f3f3f3": "白", "#00cc00": "绿", "#e0002a": "红", "#ff00ff": "紫", "#00eeee": "青",
               "#ef810f": "橙", "blue": "蓝", "#eeee00": "黄"}


def lines(cell, notes=False):
    if notes:
        cell = deepcopy(cell)
        for span in cell.xpath('.//span[@style]'):
            if text(span) == "■":
                color = re.search(r"(?:^|;)\s*color:([^;]+)", span.get("style"))
                if not color or color[1] not in NOTE_COLORS:
                    raise ValueError(f"Unknown musical note: {html.tostring(span)}")
                span.text = NOTE_COLORS[color[1]]
    return [part["text"] for part in segments(cell)]


def extra_fields(cell, kind):
    fields = []
    for value in lines(cell, notes=kind == "Hunting Horn"):
        if re.match(r"攻击[:：]|会心|防御|孔槽", value) or any(re.match(re.escape(element) + r"\s*\d", value) for element in ELEMENTS):
            continue  # These already have typed fields in the entity API.
        if re.match(r"\(期待値[:：]", value):
            fields.append({"label": "攻击期待值（参考）", "value": re.sub(r"^\(期待値[:：]|\)$", "", value).strip()})
        elif re.match(r"装填快?速度[:：]|摇晃[:：]|后座力[:：]", value):
            label, content = re.split(r"[:：]", value, maxsplit=1)
            label = {"装填快速度": "装填速度", "摇晃": "偏移（摇晃）"}.get(label, label)
            fields.append({"label": label, "value": content.strip()})
        else:
            label = {"Gunlance": "炮击类型 / 等级", "Switch Axe": "瓶类型", "Charge Blade": "瓶类型",
                     "Insect Glaive": "猎虫攻击类型", "Bow": "曲射类型", "Hunting Horn": "音色"}.get(kind, "其他性能")
            if kind == "Gunlance":
                value = re.sub(r"^(通常|放射|扩散)(\d+)$", r"\1型 · Lv\2", value)
            fields.append({"label": label, "value": value})
    return fields


def ammunition(cell):
    result = []
    for row in cell.xpath('.//table[@class="in_bullet"]/tr'):
        current = None
        for col in row:
            if col.tag == "th":
                current = {"name": AMMO[text(col)], "loads": []}
                result.append(current)
            elif col.tag == "td":
                value, classes = text(col), col.get("class", "").split()
                if value != "-" and not value.isdigit():
                    raise ValueError(f"Unknown ammo capacity: {value}")
                if not {"bt1", "bt2"}.intersection(classes):
                    raise ValueError(f"Unknown ammo availability: {classes}")
                current["loads"].append({"count": int(value) if value != "-" else None,
                                         "requires_skill": value != "-" and "bt2" in classes})
    if len(result) != 17 or len({r["name"] for r in result}) != 17:
        raise ValueError("Incomplete ammo table")
    return sorted(result, key=lambda row: AMMO_ORDER.index(row["name"]))


def tuples(cell, labels):
    result = []
    for value in lines(cell):
        if value in ("无", "-", "なし"):
            continue
        parts = [part.strip() for part in value.split(",")]
        if len(parts) != len(labels):
            raise ValueError(f"Unrecognized weapon row: {value}")
        result.append(dict(zip(labels, parts)))
    return result


def build_weapon_details(site_root, entities, revision):
    result = {}
    for entity in entities:
        if entity["kind"] != "weapon":
            continue
        page = entity["source"]["page"]
        raw = (Path(site_root) / page).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != entity["source"]["sha256"]:
            raise ValueError(f"Weapon detail source changed: {page}")
        document = html.fromstring(raw)
        restore_values(document)
        kind, levels = entity["data"]["weapon_type"], []
        for level in entity["data"]["levels"]:
            row = document.xpath(level["source_xpath"])[0]
            cols = row.xpath('./td')
            if not re.match(rf"LV{level['level']}(?:\s|$)", text(cols[0])):
                raise ValueError(f"Weapon level mismatch: {entity['id']}")
            detail = {"level": level["level"], "fields": extra_fields(cols[1], kind)}
            if kind in ("Light Bowgun", "Heavy Bowgun"):
                detail["ammunition"] = ammunition(cols[2])
                detail["internal_ammo"] = tuples(cols[3], ["name", "carried", "loaded"])
                if kind == "Light Bowgun":
                    detail["rapid_fire"] = tuples(cols[4], ["name", "shots", "recovery"])
                else:
                    detail["crouching_fire"] = [line for line in lines(cols[4]) if line not in ("无", "-", "なし")]
            else:
                detail["expected_attack"] = [value.replace("■", "").strip() for value in lines(cols[2])]
                if kind == "Bow":
                    detail["charges"] = [{"level": i + 1, "shot": text(span), "requires_skill": "#cc44ff" in span.get("style", "")}
                                         for i, span in enumerate(cols[3].xpath('./div/span'))]
                    available = {text(span): "c_r" in span.get("class", "").split() for span in cols[3].xpath('.//p//span[@class]')}
                    detail["coatings"] = [{"name": name, "available": key in available, "enhanced": available.get(key, False)}
                                          for key, name in COATINGS.items()]
                    if len(detail["charges"]) != 4 or not set(available) <= COATINGS.keys():
                        raise ValueError(f"Unrecognized bow data: {entity['id']}")
                elif kind == "Hunting Horn":
                    detail["melodies"] = []
                    for value in lines(cols[3], notes=True):
                        match = re.fullmatch(r"((?:[白绿红紫青橙蓝黄]\s+)+)(.+)", value)
                        if not match:
                            raise ValueError(f"Unrecognized melody: {value}")
                        detail["melodies"].append({"notes": match[1].split(), "effect": match[2]})
            levels.append(detail)
        result[entity["id"].split("site-")[1]] = {"dataset_revision": revision, "id": entity["id"], "weapon_type": kind,
            "source": {"page": page, "sha256": digest}, "levels": levels}
    return result
