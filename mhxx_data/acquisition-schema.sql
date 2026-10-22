CREATE TABLE site_maps (
    page TEXT PRIMARY KEY REFERENCES site_pages(path), name TEXT NOT NULL,
    images_json TEXT NOT NULL, notes_json TEXT NOT NULL, issues_json TEXT NOT NULL
);
CREATE TABLE site_map_sections (
    id INTEGER PRIMARY KEY, page TEXT NOT NULL REFERENCES site_maps(page), ordinal INTEGER NOT NULL,
    area TEXT NOT NULL, area_anchor TEXT, rank TEXT NOT NULL CHECK(rank IN ('LR','HR','G')),
    empty_text TEXT, source_xpath TEXT NOT NULL, table_json TEXT NOT NULL,
    UNIQUE(page,ordinal), UNIQUE(page,area,rank)
);
CREATE TABLE site_gathering_nodes (
    id INTEGER PRIMARY KEY, section_id INTEGER NOT NULL REFERENCES site_map_sections(id),
    ordinal INTEGER NOT NULL, point INTEGER NOT NULL, point_label TEXT NOT NULL, icon_path TEXT NOT NULL,
    fixed INTEGER NOT NULL CHECK(fixed IN (0,1)), rare INTEGER NOT NULL CHECK(rare IN (0,1)),
    attempts_min INTEGER, attempts_max INTEGER, attempts_infinite INTEGER NOT NULL CHECK(attempts_infinite IN (0,1)),
    attempts_raw TEXT NOT NULL, source_xpath TEXT NOT NULL, UNIQUE(section_id,ordinal),
    CHECK((attempts_infinite=1 AND attempts_min IS NULL AND attempts_max IS NULL) OR
          (attempts_infinite=0 AND attempts_min>0 AND attempts_max>=attempts_min))
);
CREATE TABLE site_gathering (
    id INTEGER PRIMARY KEY, node_id INTEGER NOT NULL REFERENCES site_gathering_nodes(id), ordinal INTEGER NOT NULL,
    item_page TEXT REFERENCES site_items(page), label TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity>0), percentage INTEGER NOT NULL CHECK(percentage BETWEEN 0 AND 100),
    row_anchor TEXT, source_xpath TEXT NOT NULL, raw_text TEXT NOT NULL, UNIQUE(node_id,ordinal)
);
CREATE TABLE site_combining_catalog (
    page TEXT PRIMARY KEY REFERENCES site_pages(path), tables_json TEXT NOT NULL, issues_json TEXT NOT NULL
);
CREATE TABLE site_combining (
    id INTEGER PRIMARY KEY, page TEXT NOT NULL REFERENCES site_combining_catalog(page), ordinal INTEGER NOT NULL,
    category TEXT NOT NULL, result_item_page TEXT REFERENCES site_items(page), result_label TEXT NOT NULL,
    amount_min INTEGER NOT NULL CHECK(amount_min>0), amount_max INTEGER NOT NULL CHECK(amount_max>=amount_min),
    percentage INTEGER NOT NULL CHECK(percentage BETWEEN 0 AND 100),
    row_anchor TEXT, source_xpath TEXT NOT NULL, raw_cells_json TEXT NOT NULL, UNIQUE(page,ordinal)
);
CREATE TABLE site_combining_inputs (
    recipe_id INTEGER NOT NULL REFERENCES site_combining(id), slot INTEGER NOT NULL CHECK(slot IN (1,2)),
    item_page TEXT REFERENCES site_items(page), label TEXT NOT NULL, source_xpath TEXT NOT NULL,
    PRIMARY KEY(recipe_id,slot)
);
CREATE TABLE location_candidates (
    page TEXT NOT NULL REFERENCES site_maps(page), location_id INTEGER NOT NULL REFERENCES locations(_id),
    status TEXT NOT NULL, supporting_quests INTEGER NOT NULL, evidence_json TEXT NOT NULL,
    PRIMARY KEY(page,location_id)
);
CREATE TABLE gathering_checks (
    gathering_id INTEGER PRIMARY KEY REFERENCES site_gathering(id),
    status TEXT NOT NULL, evidence_json TEXT NOT NULL
);
CREATE TABLE combining_matches (
    recipe_id INTEGER PRIMARY KEY REFERENCES site_combining(id),
    combining_id INTEGER UNIQUE REFERENCES combining(_id), status TEXT NOT NULL, evidence_json TEXT NOT NULL
);
CREATE INDEX site_gathering_item_lookup ON site_gathering(item_page);
CREATE INDEX site_gathering_section_lookup ON site_map_sections(page,area,rank);
CREATE INDEX site_gathering_node_lookup ON site_gathering_nodes(section_id);
CREATE INDEX site_gathering_entry_lookup ON site_gathering(node_id);
CREATE INDEX site_combining_result_lookup ON site_combining(result_item_page);
CREATE INDEX site_combining_input_lookup ON site_combining_inputs(item_page);
CREATE VIEW site_item_gathering_sources AS
    SELECT g.*,s.page,m.name AS map_name,s.area,s.area_anchor,s.rank,
           n.point,n.point_label,n.icon_path,n.fixed,n.rare,n.attempts_min,n.attempts_max,
           n.attempts_infinite,n.attempts_raw
    FROM site_gathering g JOIN site_gathering_nodes n ON n.id=g.node_id
    JOIN site_map_sections s ON s.id=n.section_id JOIN site_maps m ON m.page=s.page;
