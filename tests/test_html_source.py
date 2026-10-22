from pathlib import Path

import pytest
from lxml import html

from mhxx_data.html_source import parse_recipes, parse_weapon, profile, restore_values, text

ROOT = Path(__file__).resolve().parents[1]


def test_literal_hydration_preserves_markup_and_tail_without_running_scripts():
    doc = html.fromstring('''<div>before<span class="cpg1_2"></span>after
        <script>$('.cpg1_2').html('<a href="../ida/123.html">铁矿石</a> x4');
        throw new Error("must never run");</script></div>''')
    assert restore_values(doc) == 1
    assert text(doc) == "before 铁矿石 x4 after"
    assert doc.xpath('.//a/@href') == ["../ida/123.html"]
    assert not doc.xpath('.//script')


@pytest.mark.parametrize("script", ["$('.cpg1').html(compute());", ""])
def test_nonliteral_or_missing_value_fails_closed(script):
    doc = html.fromstring(f'<div><span class="cpg1"></span><script>{script}</script></div>')
    with pytest.raises(ValueError, match="Unresolved placeholder"):
        restore_values(doc)


def test_conflicting_assignments_are_not_silently_overwritten():
    doc = html.fromstring('''<div><span class="cpg1"></span><script>
        $('.cpg1').html('10'); $('.cpg1').html('20');</script></div>''')
    with pytest.raises(ValueError, match="Conflicting"):
        restore_values(doc)


def test_alternative_production_points_and_output_scraps_remain_separate():
    cell = html.fromstring('''<td><a href="../ida/1.html">石</a> x2<br>
        矿石素材 x6<br>100z<br>入手端材：<a href="../ida/9.html">端材 x3</a><br>
        <div><span>[生产G]</span><br><a href="../ida/2.html">宝石 x4</a><br>200z</div></td>''')
    a, b = parse_recipes(cell, "ida/100.html", 3, "Improve", "/fixture")
    assert (a["kind"], a["money"], a["material_points"][0]["points"]) == ("Improve", 100, 6)
    assert [(i["item_page"], i["quantity"]) for i in a["ingredients"]] == [("ida/1.html", 2)]
    assert (b["kind"], b["money"], b["ingredients"][0]["quantity"]) == ("Create", 200, 4)


def test_unlinked_material_is_retained_for_review():
    recipe = parse_recipes(html.fromstring("<td>新红莲石 x4<br>100z</td>"), "ida/1.html", 1, "Create", "/fixture")[0]
    assert recipe["unparsed"] == ["新红莲石 x4"]
    assert recipe["ingredients"] == []


def test_dual_affinity_and_element_values_remain_distinct():
    result = profile("攻击：300 会心 -35 / 10 % 冰12 毒8 防御+15 孔槽：◯ - -", 1)
    assert (result["affinity"], result["slots"], result["defense"]) == ("-35/10", 1, 15)
    assert result["elements"] == [("Ice", 12), ("Poison", 8)]


@pytest.mark.parametrize("page, level, count, money", [
    ("218099", 1, 2, 1275),
    ("219228", 8, 4, 34000),
    ("227292", 1, 4, 2550),
])
def test_real_pages_production_recipes_do_not_include_upgrade_materials(page, level, count, money):
    doc = html.fromstring((ROOT / f"games/mhxx_old/ida/{page}.html").read_bytes())
    restore_values(doc)
    weapon = parse_weapon(doc, f"ida/{page}.html")
    recipe, = [r for r in weapon["recipes"] if r["kind"] == "Create" and r["level"] == level]
    assert (len(recipe["ingredients"]), recipe["money"]) == (count, money)
    assert not recipe["unparsed"]


def test_ancestor_recipe_is_not_assigned_to_child_weapon():
    doc = html.fromstring((ROOT / "games/mhxx_old/ida/219273.html").read_bytes())
    restore_values(doc)
    weapon = parse_weapon(doc, "ida/219273.html")
    assert weapon["ancestors"]
    assert not any(r["kind"] == "Create" and r["level"] == 1 for r in weapon["recipes"])


def test_weapon_branch_links_retain_the_exact_parent_level_and_source():
    doc = html.fromstring((ROOT / "games/mhxx_old/ida/218099.html").read_bytes())
    restore_values(doc)
    branches = parse_weapon(doc, "ida/218099.html")["branches"]
    assert [(b["level"], b["target_page"]) for b in branches] == [
        (2, "ida/220141.html"), (3, "ida/220136.html"), (3, "ida/220139.html"),
        (4, "ida/220135.html"), (5, "ida/228132.html")]
    assert all(doc.xpath(b["source_xpath"])[0].text_content() == b["label"] for b in branches)
