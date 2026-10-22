CREATE TABLE source_manifest (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
CREATE TABLE site_pages (
    path TEXT PRIMARY KEY, category TEXT NOT NULL, title TEXT NOT NULL, sha256 TEXT NOT NULL
);
CREATE TABLE site_items (
    page TEXT PRIMARY KEY REFERENCES site_pages(path), name TEXT NOT NULL, basic_rows_json TEXT NOT NULL
);
CREATE TABLE data_reviews (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, page TEXT NOT NULL REFERENCES site_pages(path),
    details_json TEXT NOT NULL
);
CREATE TABLE site_weapon_lines (
    page TEXT PRIMARY KEY REFERENCES site_pages(path), wtype TEXT NOT NULL,
    issues_json TEXT NOT NULL, ancestors_json TEXT NOT NULL
);
CREATE TABLE site_weapon_levels (
    page TEXT NOT NULL REFERENCES site_weapon_lines(page), level INTEGER NOT NULL,
    name TEXT NOT NULL, attack INTEGER NOT NULL, slots INTEGER NOT NULL,
    affinity TEXT NOT NULL, defense INTEGER NOT NULL, elements_json TEXT NOT NULL,
    sharpness_px_json TEXT NOT NULL, performance_json TEXT NOT NULL, source_xpath TEXT NOT NULL,
    PRIMARY KEY (page, level)
);
CREATE TABLE site_recipes (
    id INTEGER PRIMARY KEY, page TEXT NOT NULL, level INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('Create','Improve')), money INTEGER,
    unparsed_json TEXT NOT NULL, source_xpath TEXT NOT NULL, raw_text TEXT NOT NULL,
    also_seen_at_json TEXT NOT NULL,
    FOREIGN KEY (page,level) REFERENCES site_weapon_levels(page,level)
);
CREATE TABLE site_weapon_branches (
    page TEXT NOT NULL, level INTEGER NOT NULL, ordinal INTEGER NOT NULL,
    target_page TEXT NOT NULL, target_level INTEGER NOT NULL,
    label TEXT NOT NULL, source_xpath TEXT NOT NULL,
    PRIMARY KEY(page,level,ordinal), UNIQUE(target_page,target_level),
    FOREIGN KEY(page,level) REFERENCES site_weapon_levels(page,level),
    FOREIGN KEY(target_page,target_level) REFERENCES site_weapon_levels(page,level)
);
CREATE TABLE site_recipe_items (
    recipe_id INTEGER NOT NULL REFERENCES site_recipes(id), ordinal INTEGER NOT NULL,
    item_page TEXT NOT NULL REFERENCES site_items(page), quantity INTEGER NOT NULL CHECK(quantity>0),
    label TEXT NOT NULL, raw_text TEXT NOT NULL, PRIMARY KEY(recipe_id,ordinal)
);
CREATE TABLE site_recipe_points (
    recipe_id INTEGER NOT NULL REFERENCES site_recipes(id), ordinal INTEGER NOT NULL,
    label TEXT NOT NULL, points INTEGER NOT NULL CHECK(points>0), raw_text TEXT NOT NULL,
    PRIMARY KEY(recipe_id,ordinal)
);
CREATE TABLE reviewed_recipe_items (
    recipe_id INTEGER NOT NULL REFERENCES site_recipes(id),
    review_id TEXT NOT NULL REFERENCES data_reviews(id),
    item_page TEXT NOT NULL REFERENCES site_items(page), quantity INTEGER NOT NULL CHECK(quantity>0),
    raw_text TEXT NOT NULL, PRIMARY KEY(recipe_id,review_id)
);
CREATE TABLE weapon_matches (
    page TEXT PRIMARY KEY REFERENCES site_weapon_lines(page), family INTEGER UNIQUE,
    status TEXT NOT NULL, evidence_json TEXT NOT NULL
);
CREATE TABLE item_matches (
    page TEXT PRIMARY KEY REFERENCES site_items(page), item_id INTEGER UNIQUE REFERENCES items(_id),
    status TEXT NOT NULL, supporting_weapon_lines INTEGER NOT NULL,
    candidate_ids_json TEXT NOT NULL, evidence_json TEXT NOT NULL
);
CREATE TABLE recipe_checks (
    recipe_id INTEGER PRIMARY KEY REFERENCES site_recipes(id), weapon_id INTEGER NOT NULL REFERENCES weapons(_id),
    status TEXT NOT NULL
);
CREATE TABLE audit_differences (
    id INTEGER PRIMARY KEY, recipe_id INTEGER NOT NULL REFERENCES site_recipes(id),
    weapon_id INTEGER NOT NULL REFERENCES weapons(_id), field TEXT NOT NULL,
    site_value_json TEXT NOT NULL, upstream_value_json TEXT NOT NULL
);
CREATE TABLE weapon_value_differences (
    page TEXT NOT NULL, level INTEGER NOT NULL, weapon_id INTEGER NOT NULL REFERENCES weapons(_id),
    field TEXT NOT NULL, site_value_json TEXT NOT NULL, upstream_value_json TEXT NOT NULL,
    review_id TEXT NOT NULL REFERENCES data_reviews(id), PRIMARY KEY(page,level,field),
    FOREIGN KEY(page,level) REFERENCES site_weapon_levels(page,level)
);
CREATE TABLE cost_reviews (
    recipe_id INTEGER PRIMARY KEY REFERENCES site_recipes(id), pattern TEXT NOT NULL,
    site_marks_xx INTEGER NOT NULL, resolution TEXT NOT NULL
);
CREATE INDEX site_recipe_item_lookup ON site_recipe_items(item_page);
CREATE INDEX site_recipe_weapon_lookup ON site_recipes(page,level,kind);
CREATE INDEX weapon_family_lookup ON weapons(family);
CREATE INDEX source_component_lookup ON components(created_item_id,type);
CREATE INDEX source_gathering_lookup ON gathering(item_id);
CREATE INDEX source_hunting_lookup ON hunting_rewards(item_id);
CREATE INDEX source_quest_reward_lookup ON quest_rewards(item_id);
CREATE VIEW candidate_weapon_labels AS
    SELECT l.*, w._id AS upstream_id, i.name AS upstream_name, m.status AS match_status
    FROM site_weapon_levels l JOIN weapon_matches m ON m.page=l.page
    JOIN weapons w ON w.family=m.family AND w._id%256=l.level
    JOIN items i ON i._id=w._id;
CREATE VIEW candidate_item_labels AS
    SELECT s.page,s.name AS site_name,i._id AS upstream_id,i.name AS upstream_name,m.status
    FROM item_matches m JOIN site_items s ON s.page=m.page JOIN items i ON i._id=m.item_id;
CREATE VIEW annotated_recipe_items AS
    SELECT recipe_id,ordinal,item_page,quantity,label,raw_text,'html_link' AS reference_origin,NULL AS review_id
    FROM site_recipe_items
    UNION ALL
    SELECT recipe_id,1000,item_page,quantity,raw_text,raw_text,'review_annotation',review_id
    FROM reviewed_recipe_items;
CREATE VIEW mhxx_recipe_costs AS
    SELECT r.id AS recipe_id,r.page,r.level,r.kind,r.money AS display_zenny,'site_html' AS display_source,
           CASE WHEN r.kind='Create' THEN w.creation_cost ELSE w.upgrade_cost END AS mhgu_stored_zenny,
           cr.pattern AS difference_pattern,
           CASE WHEN cr.pattern IS NOT NULL THEN cr.resolution
                WHEN w._id IS NULL THEN 'no_upstream_identity'
                WHEN r.money IS NULL THEN 'site_cost_missing'
                ELSE 'raw_values_agree; game_price_unverified' END AS review_status
    FROM site_recipes r LEFT JOIN weapon_matches m ON m.page=r.page
    LEFT JOIN weapons w ON w.family=m.family AND w._id%256=r.level
    LEFT JOIN cost_reviews cr ON cr.recipe_id=r.id;
