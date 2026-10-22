"""Conservative cross-source candidates from independently mapped ingredients.

Reward matching compares a projection onto known item IDs, ignoring translated
condition names. This is evidence of identity, NOT full reward equivalence.
Armor matching requires base stats and a complete physical creation recipe;
maximum defense and skills are not used as identity evidence.
"""

from collections import Counter, defaultdict

from .domains import integer


def signature(values):
    return tuple(sorted(Counter(values).items()))


def quest_hub(domain):
    name = domain["name"]
    for prefix, hub in (("村", "Village"), ("集", "Guild"), ("配信", "Event"),
                        ("斗技大会", "Arena"), ("【特殊许可】", "Permit")):
        if name.startswith(prefix):
            return hub
    return None


def compare_domains(connection, domains, item_matches):
    ids = {p: m["item_id"] for p, m in item_matches.items() if m["item_id"] is not None}
    known = set(ids.values())
    matches = []
    for kind, table, key in (("monster", "hunting_rewards", "monster_id"), ("quest", "quest_rewards", "quest_id")):
        upstream, index = defaultdict(list), defaultdict(list)
        for row in connection.execute(f"SELECT * FROM {table}"):
            if kind == "monster" and row["condition"] == "Meowster Hunter":
                continue  # local meow rewards are a separate supplementary table
            if row["item_id"] in known:
                prefix = row["rank"] if kind == "monster" else "reward"
                upstream[row[key]].append((prefix, row["item_id"], row["stack_size"], row["percentage"]))
        for uid, values in upstream.items():
            index[signature(values)].append(uid)
        hubs = dict(connection.execute("SELECT _id,hub FROM quests")) if kind == "quest" else {}
        for d in (d for d in domains if d["kind"] == kind):
            values = [(r["rank"] if kind == "monster" else "reward", ids[r["item_page"]], r["quantity"], r["percentage"])
                      for r in d["rewards"] if r["item_page"] in ids and r["percentage"] is not None
                      and not (kind == "monster" and r["group"] == "フリー狩猎")]
            candidates = index.get(signature(values), [])
            if kind == "quest" and (hub := quest_hub(d)):
                candidates = [uid for uid in candidates if hubs[uid] == hub]
            distinct = len({v[1] for v in values})
            status = "reward_projection_unique" if len(candidates) == 1 else "reward_projection_ambiguous" if candidates else "no_reward_projection_match"
            if distinct < 3 or len(values) < 6:
                status, candidates = "insufficient_mapped_rewards", []
            if any(i["kind"] in ("missing_probability", "unparsed_reward") for i in d["issues"]):
                status, candidates = "incomplete_reward_values", []
            matches.append({"kind": kind, "page": d["page"], "ordinal": 0,
                "upstream_id": candidates[0] if len(candidates) == 1 else None, "status": status,
                "evidence": {"candidate_ids": candidates, "mapped_reward_rows": len(values),
                    "distinct_mapped_items": distinct, "total_site_rows": len(d["rewards"]),
                    "method": "exact_multiset_of_known_items_quantities_probabilities",
                    "scope": "monster rank retained; free hunt and Meowster Hunter excluded; translated conditions and quest reward slots not compared",
                    "item_evidence": "existing weapon-recipe item_matches; these domains cannot bootstrap them"}})

    fields = ("slot", "defense", "fire", "water", "thunder", "ice", "dragon", "slots", "rarity")
    armor, profiles = {}, defaultdict(list)
    for row in connection.execute("""SELECT a.*,a.fire_res AS fire,a.water_res AS water,a.thunder_res AS thunder,
            a.ice_res AS ice,a.dragon_res AS dragon,a.num_slots AS slots,i.rarity,i.name
            FROM armor a JOIN items i USING(_id)"""):
        row = dict(row)
        armor[row["_id"]] = row
        profiles[tuple(row[f] for f in fields)].append(row["_id"])
    components = defaultdict(list)
    for row in connection.execute("""SELECT c.created_item_id,c.component_item_id,c.quantity
            FROM components c JOIN armor a ON a._id=c.created_item_id
            JOIN items i ON i._id=c.component_item_id WHERE c.type='Create' AND i.type<>'Materials'"""):
        components[row["created_item_id"]].append((row["component_item_id"], row["quantity"]))
    for d in (d for d in domains if d["kind"] == "armor"):
        for piece in d["pieces"]:
            p = piece | {"rarity": integer(d["metadata"].get("稀有度", ""))}
            profile_candidates = profiles.get(tuple(p[f] for f in fields), [])
            recipes = [r for r in d["recipes"] if r["kind"] == "Create" and r["slot"] == p["slot"]]
            candidates, ingredients = [], []
            if len(recipes) == 1:
                r = recipes[0]
                ingredients = [(ids.get(i["item_page"]), i["quantity"]) for i in r["ingredients"]]
                if len({i for i, _ in ingredients}) >= 2 and all(i for i, _ in ingredients) and not r["unparsed"]:
                    candidates = [uid for uid in profile_candidates if signature(components[uid]) == signature(ingredients)]
            status = "base_profile_and_recipe_unique" if len(candidates) == 1 else "base_profile_and_recipe_ambiguous" if candidates else "no_complete_profile_recipe_match"
            uid = candidates[0] if len(candidates) == 1 else None
            differences = []
            if uid and piece["max_defense"] != armor[uid]["max_defense"]:
                differences.append({"field": "max_defense", "site": piece["max_defense"], "upstream": armor[uid]["max_defense"]})
            matches.append({"kind": "armor", "page": d["page"], "ordinal": piece["ordinal"],
                "upstream_id": uid, "status": status, "differences": differences,
                "evidence": {"candidate_ids": candidates, "profile_candidates": profile_candidates,
                    "method": "base_defense_resistances_slots_rarity_slot_and_complete_physical_creation_recipe",
                    "scope": "maximum defense recorded separately; skills, gender, hunter type and upgrade recipes not compared"}})
    # A source record is never assigned to multiple local entities silently.
    assigned = Counter((m["kind"], m["upstream_id"]) for m in matches if m["upstream_id"] is not None)
    for m in matches:
        if m["upstream_id"] is not None and assigned[m["kind"], m["upstream_id"]] > 1:
            m.update(upstream_id=None, status="non_bijective_candidates", differences=[])
    return matches
