CREATE TABLE site_domain_pages (
    page TEXT PRIMARY KEY REFERENCES site_pages(path),
    kind TEXT NOT NULL CHECK(kind IN ('monster','quest','armor','skill')),
    name TEXT NOT NULL, metadata_json TEXT NOT NULL, notes_json TEXT NOT NULL,
    tables_json TEXT NOT NULL, issues_json TEXT NOT NULL
);
CREATE TABLE site_rewards (
    id INTEGER PRIMARY KEY, page TEXT NOT NULL REFERENCES site_domain_pages(page),
    group_name TEXT NOT NULL, rank TEXT, condition_text TEXT, attempts INTEGER,
    item_page TEXT REFERENCES site_items(page), quantity INTEGER NOT NULL CHECK(quantity>0),
    percentage INTEGER CHECK(percentage BETWEEN 0 AND 100),
    raw_text TEXT NOT NULL, source_xpath TEXT NOT NULL, segment INTEGER NOT NULL,
    UNIQUE(page,source_xpath,segment)
);
CREATE TABLE site_monster_hitzones (
    page TEXT NOT NULL REFERENCES site_domain_pages(page), ordinal INTEGER NOT NULL,
    body_part TEXT NOT NULL, values_json TEXT NOT NULL, source_xpath TEXT NOT NULL,
    PRIMARY KEY(page,ordinal)
);
CREATE TABLE site_quest_references (
    page TEXT NOT NULL REFERENCES site_domain_pages(page), ordinal INTEGER NOT NULL,
    role TEXT NOT NULL, target_page TEXT NOT NULL REFERENCES site_pages(path),
    label TEXT NOT NULL, href TEXT NOT NULL, source_xpath TEXT NOT NULL,
    PRIMARY KEY(page,ordinal)
);
CREATE TABLE site_monster_quests (
    page TEXT NOT NULL REFERENCES site_domain_pages(page), ordinal INTEGER NOT NULL,
    quest_page TEXT NOT NULL REFERENCES site_domain_pages(page), rank_label TEXT NOT NULL,
    quest_type TEXT, location_page TEXT REFERENCES site_pages(path),
    health_bar REAL CHECK(health_bar BETWEEN 0 AND 100),
    defense_bar REAL CHECK(defense_bar BETWEEN 0 AND 100),
    intrusion INTEGER NOT NULL CHECK(intrusion IN (0,1)),
    monsters_json TEXT NOT NULL, source_xpath TEXT NOT NULL,
    PRIMARY KEY(page,ordinal)
);
CREATE TABLE site_armor_pieces (
    id INTEGER PRIMARY KEY, page TEXT NOT NULL REFERENCES site_domain_pages(page), ordinal INTEGER NOT NULL,
    name TEXT NOT NULL, slot TEXT NOT NULL, hunter_type TEXT NOT NULL, rarity INTEGER,
    gender_text TEXT, defense INTEGER NOT NULL, max_defense INTEGER NOT NULL,
    fire INTEGER NOT NULL, water INTEGER NOT NULL, thunder INTEGER NOT NULL,
    ice INTEGER NOT NULL, dragon INTEGER NOT NULL, slots INTEGER CHECK(slots BETWEEN 0 AND 3),
    source_xpath TEXT NOT NULL, UNIQUE(page,ordinal)
);
CREATE TABLE site_armor_skills (
    armor_id INTEGER NOT NULL REFERENCES site_armor_pieces(id), ordinal INTEGER NOT NULL,
    skill_page TEXT REFERENCES site_domain_pages(page), points INTEGER,
    label TEXT NOT NULL, raw_text TEXT NOT NULL, source_xpath TEXT NOT NULL,
    PRIMARY KEY(armor_id,ordinal)
);
CREATE TABLE site_armor_recipes (
    id INTEGER PRIMARY KEY, page TEXT NOT NULL REFERENCES site_domain_pages(page),
    kind TEXT NOT NULL CHECK(kind IN ('Create','Improve')), slot TEXT, level INTEGER NOT NULL,
    raw_text TEXT NOT NULL, unparsed_json TEXT NOT NULL, source_xpath TEXT NOT NULL
);
CREATE TABLE site_armor_recipe_items (
    recipe_id INTEGER NOT NULL REFERENCES site_armor_recipes(id), ordinal INTEGER NOT NULL,
    item_page TEXT NOT NULL REFERENCES site_items(page), quantity INTEGER NOT NULL CHECK(quantity>0),
    label TEXT NOT NULL, raw_text TEXT NOT NULL, PRIMARY KEY(recipe_id,ordinal)
);
CREATE TABLE site_armor_recipe_points (
    recipe_id INTEGER NOT NULL REFERENCES site_armor_recipes(id), ordinal INTEGER NOT NULL,
    label TEXT NOT NULL, points INTEGER NOT NULL CHECK(points>0), raw_text TEXT NOT NULL,
    PRIMARY KEY(recipe_id,ordinal)
);
CREATE TABLE site_skill_activations (
    page TEXT NOT NULL REFERENCES site_domain_pages(page), ordinal INTEGER NOT NULL,
    name TEXT NOT NULL, points INTEGER, description TEXT NOT NULL, source_xpath TEXT NOT NULL,
    PRIMARY KEY(page,ordinal)
);
CREATE TABLE domain_matches (
    page TEXT NOT NULL REFERENCES site_domain_pages(page), ordinal INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('monster','quest','armor')),
    upstream_id INTEGER, status TEXT NOT NULL, evidence_json TEXT NOT NULL,
    PRIMARY KEY(page,ordinal)
);
CREATE TABLE domain_value_differences (
    page TEXT NOT NULL, ordinal INTEGER NOT NULL, field TEXT NOT NULL,
    site_value_json TEXT NOT NULL, upstream_value_json TEXT NOT NULL,
    PRIMARY KEY(page,ordinal,field), FOREIGN KEY(page,ordinal) REFERENCES domain_matches(page,ordinal)
);
CREATE INDEX site_rewards_item_lookup ON site_rewards(item_page);
CREATE INDEX site_rewards_page_lookup ON site_rewards(page);
CREATE INDEX site_armor_recipe_item_lookup ON site_armor_recipe_items(item_page);
CREATE INDEX site_armor_skill_lookup ON site_armor_skills(skill_page);
CREATE INDEX site_quest_target_lookup ON site_quest_references(target_page);
CREATE UNIQUE INDEX domain_match_unique_target ON domain_matches(kind,upstream_id) WHERE upstream_id IS NOT NULL;
CREATE VIEW site_item_reward_sources AS
    SELECT r.*,d.kind AS source_kind,d.name AS source_name
    FROM site_rewards r JOIN site_domain_pages d ON d.page=r.page;
