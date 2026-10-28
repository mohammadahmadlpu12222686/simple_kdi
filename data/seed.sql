-- Synthetic (fake) data for a small kitchen-appliance company.
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS components;
DROP TABLE IF EXISTS suppliers;
DROP TABLE IF EXISTS bom;
DROP TABLE IF EXISTS offers;
DROP TABLE IF EXISTS competitor_prices;
DROP TABLE IF EXISTS price_history;
DROP TABLE IF EXISTS price_changes;
DROP TABLE IF EXISTS purchase_orders;

CREATE TABLE products (id TEXT PRIMARY KEY, name TEXT, short_name TEXT,
  price INTEGER, unit_cost INTEGER, stock INTEGER, daily_sales INTEGER);
INSERT INTO products VALUES ('P-MIX', 'Mixer Grinder', 'Mixer',   1000, 750, 200, 20);
INSERT INTO products VALUES ('P-BLD', 'Hand Blender',  'Blender',  600, 420, 150, 10);

CREATE TABLE components (id TEXT PRIMARY KEY, name TEXT, short_name TEXT,
  stock INTEGER, daily_use INTEGER);
INSERT INTO components VALUES ('C-MOTOR',  'Motor',        'Motor',  300, 30);
INSERT INTO components VALUES ('C-JAR',    'Jar',          'Jar',    240, 20);
INSERT INTO components VALUES ('C-BLADE',  'Blade Set',    'Blade',  900, 30);
INSERT INTO components VALUES ('C-SWITCH', 'Speed Switch', 'Switch', 400, 20);

CREATE TABLE suppliers (id TEXT PRIMARY KEY, name TEXT, short_name TEXT,
  current_delay_days INTEGER);
INSERT INTO suppliers VALUES ('S-APEX',   'Apex Motors',        'Apex',     14);
INSERT INTO suppliers VALUES ('S-BHARAT', 'Bharat Electricals', 'Bharat',    0);
INSERT INTO suppliers VALUES ('S-CLEAR',  'ClearJar Plastics',  'ClearJar',  0);

-- bom = "bill of materials": which product uses which component
CREATE TABLE bom (product_id TEXT, component_id TEXT);
INSERT INTO bom VALUES ('P-MIX', 'C-MOTOR');
INSERT INTO bom VALUES ('P-MIX', 'C-JAR');
INSERT INTO bom VALUES ('P-MIX', 'C-BLADE');
INSERT INTO bom VALUES ('P-MIX', 'C-SWITCH');
INSERT INTO bom VALUES ('P-BLD', 'C-MOTOR');
INSERT INTO bom VALUES ('P-BLD', 'C-BLADE');

-- offers = which supplier can sell us which component, at what cost and speed
CREATE TABLE offers (component_id TEXT, supplier_id TEXT, unit_cost INTEGER,
  lead_time_days INTEGER, is_primary INTEGER);
INSERT INTO offers VALUES ('C-MOTOR',  'S-APEX',   310, 7, 1);
INSERT INTO offers VALUES ('C-MOTOR',  'S-BHARAT', 330, 7, 0);
INSERT INTO offers VALUES ('C-JAR',    'S-CLEAR',   60, 5, 1);
INSERT INTO offers VALUES ('C-JAR',    'S-BHARAT',  66, 7, 0);
INSERT INTO offers VALUES ('C-BLADE',  'S-BHARAT',  45, 6, 1);
INSERT INTO offers VALUES ('C-SWITCH', 'S-BHARAT',  25, 6, 1);

CREATE TABLE competitor_prices (id TEXT PRIMARY KEY, name TEXT, product_id TEXT,
  price INTEGER, previous_price INTEGER, observed_on TEXT);
INSERT INTO competitor_prices VALUES ('X-ZEN',  'Zenith Mixer Pro', 'P-MIX', 900, 1000, '2026-10-01');
INSERT INTO competitor_prices VALUES ('X-NOVA', 'Nova Blend Stick', 'P-BLD', 580,  580, '2026-09-15');

CREATE TABLE price_history (product_id TEXT, month TEXT, price INTEGER);
INSERT INTO price_history VALUES ('P-MIX', '2026-05', 1050);
INSERT INTO price_history VALUES ('P-MIX', '2026-06', 1050);
INSERT INTO price_history VALUES ('P-MIX', '2026-07', 1020);
INSERT INTO price_history VALUES ('P-MIX', '2026-08', 1000);
INSERT INTO price_history VALUES ('P-MIX', '2026-09', 1000);
INSERT INTO price_history VALUES ('P-MIX', '2026-10', 1000);
INSERT INTO price_history VALUES ('P-BLD', '2026-05', 620);
INSERT INTO price_history VALUES ('P-BLD', '2026-06', 620);
INSERT INTO price_history VALUES ('P-BLD', '2026-07', 600);
INSERT INTO price_history VALUES ('P-BLD', '2026-08', 600);
INSERT INTO price_history VALUES ('P-BLD', '2026-09', 600);
INSERT INTO price_history VALUES ('P-BLD', '2026-10', 600);

-- Two tables that our ACTIONS are allowed to write into
CREATE TABLE price_changes (decision_id TEXT, product_id TEXT, old_price INTEGER, new_price INTEGER);
CREATE TABLE purchase_orders (decision_id TEXT, component_id TEXT, supplier_id TEXT,
  quantity INTEGER, unit_cost INTEGER);
