
"""
company.py  —  EVERYTHING ABOUT OUR COMPANY, IN ONE PLACE.

This is the only file that knows about motors, suppliers and prices.
To use the system for another business, you rewrite THIS file only.

It says 5 things:
  1. GRAPH      - how database tables become the knowledge graph
  2. QUESTIONS  - the menu of database questions the AI may ask for (it never writes SQL)
  3. ACTIONS    - the only changes that may be written, and how code measures each one
  4. RULES      - hard company rules, checked by CODE (the AI cannot skip them)
  5. GUIDANCE   - soft advice for the AI (not checked by code)
"""

COMPANY_NAME = "Kitchen appliance maker (demo)"


# ---------------------------------------------------------------- 1. GRAPH
# Each line: run this SQL, and turn every row into an arrow  FROM --LINK--> TO
GRAPH_LINKS = [
    ("USES",          "SELECT p.name AS a, c.name AS b FROM bom x JOIN products p ON p.id = x.product_id JOIN components c ON c.id = x.component_id"),
    ("SUPPLIED_BY",   "SELECT c.name AS a, s.name AS b FROM offers o JOIN components c ON c.id = o.component_id JOIN suppliers s ON s.id = o.supplier_id"),
    ("COMPETES_WITH", "SELECT x.name AS a, p.name AS b FROM competitor_prices x JOIN products p ON p.id = x.product_id"),
]
# The things the AI can talk about (shown to it so it knows the ids)
THINGS = {
    "product":   "SELECT id, name, short_name FROM products",
    "component": "SELECT id, name, short_name FROM components",
    "supplier":  "SELECT id, name, short_name FROM suppliers",
}


# ------------------------------------------------------------ 2. QUESTIONS
# The AI picks from this menu by name. Each question takes one :id.
QUESTIONS = {
    "product": {
        "about": "price, cost, stock and daily sales of a product (id = product id)",
        "sql": "SELECT id, name, price, unit_cost, stock, daily_sales FROM products WHERE id = :id",
    },
    "rival_price": {
        "about": "competitor prices for a product, now and before (id = product id)",
        "sql": "SELECT name, price, previous_price FROM competitor_prices WHERE product_id = :id ORDER BY price",
    },
    "supplier": {
        "about": "a supplier and its current delay in days (id = supplier id)",
        "sql": "SELECT id, name, current_delay_days FROM suppliers WHERE id = :id",
    },
    "parts_from_supplier": {
        "about": "components a supplier sells us, with our stock, daily use, cost and normal lead time (id = supplier id)",
        "sql": """SELECT c.id, c.name, c.stock, c.daily_use, o.unit_cost, o.lead_time_days
                  FROM offers o JOIN components c ON c.id = o.component_id
                  WHERE o.supplier_id = :id ORDER BY c.stock * 1.0 / c.daily_use""",
    },
    "other_suppliers": {
        "about": "other suppliers for the components of a supplier, with cost and total lead days including delays (id = supplier id)",
        "sql": """SELECT o2.component_id, s.id AS supplier_id, s.name AS supplier_name, o2.unit_cost,
                         o2.lead_time_days + s.current_delay_days AS lead_days
                  FROM offers o1
                  JOIN offers o2 ON o2.component_id = o1.component_id AND o2.supplier_id <> o1.supplier_id
                  JOIN suppliers s ON s.id = o2.supplier_id
                  WHERE o1.supplier_id = :id ORDER BY o2.unit_cost""",
    },
    "component": {
        "about": "stock and daily use of a component (id = component id)",
        "sql": "SELECT id, name, stock, daily_use FROM components WHERE id = :id",
    },
    "offers_for_component": {
        "about": "every supplier offer for a component, with cost and total lead days including delays (id = component id)",
        "sql": """SELECT s.id AS supplier_id, s.name AS supplier_name, o.unit_cost, o.is_primary,
                         o.lead_time_days + s.current_delay_days AS lead_days
                  FROM offers o JOIN suppliers s ON s.id = o.supplier_id
                  WHERE o.component_id = :id ORDER BY o.unit_cost""",
    },
}


# -------------------------------------------------------------- 3. ACTIONS
# The AI may PROPOSE one action. Code then MEASURES it with fresh numbers from the
# database, checks the RULES, and writes only after a person approves.
# The measure functions get `sql(query, **values)` and the values the AI filled in.

def measure_price_change(sql, v):
    """Numbers for a price change, straight from the database."""
    rows = sql("SELECT price, unit_cost FROM products WHERE id = :id", id=v["product_id"])
    if not rows or v["new_price"] <= 0:
        return None
    old, cost, new = rows[0]["price"], rows[0]["unit_cost"], v["new_price"]
    return {"old_price": old, "new_price": new, "unit_cost": cost,
            "margin": round((new - cost) / new, 3),
            "price_cut": round((old - new) / old, 3)}


def measure_purchase_order(sql, v):
    """Numbers for a purchase order, straight from the database."""
    part = sql("SELECT stock, daily_use FROM components WHERE id = :id", id=v["component_id"])
    offer = sql("""SELECT o.unit_cost, o.lead_time_days + s.current_delay_days AS lead_days
                   FROM offers o JOIN suppliers s ON s.id = o.supplier_id
                   WHERE o.component_id = :c AND o.supplier_id = :s""", c=v["component_id"], s=v["supplier_id"])
    usual = sql("SELECT unit_cost FROM offers WHERE component_id = :c AND is_primary = 1", c=v["component_id"])
    if not part or not offer or not usual or v["quantity"] <= 0:
        return None                                   # unknown part, or this supplier does not sell it
    part, offer, usual_cost = part[0], offer[0], usual[0]["unit_cost"]
    days_left = part["stock"] / part["daily_use"]
    return {"days_of_stock_now": round(days_left, 1),
            "days_of_stock_after": round((part["stock"] + v["quantity"]) / part["daily_use"], 1),
            "arrives_in_days": offer["lead_days"],
            "late_by_days": round(offer["lead_days"] - days_left, 1),
            "unit_cost": offer["unit_cost"],
            "extra_cost": round((offer["unit_cost"] - usual_cost) / usual_cost, 3),
            "order_value": v["quantity"] * offer["unit_cost"]}


# "values": what the AI must fill in  ->  (type, description)
ACTIONS = {
    "update_price": {
        "about": "change the selling price of a product",
        "values": {"product_id": (str, "product id"), "new_price": (int, "new price in Rs")},
        "measure": measure_price_change,
        "rules": ["min_margin", "big_price_cut"],
        "sql": "UPDATE products SET price = :new_price WHERE id = :product_id",
    },
    "create_purchase_order": {
        "about": "order a quantity of a component from a supplier",
        "values": {"component_id": (str, "component id"), "supplier_id": (str, "supplier id"),
                   "quantity": (int, "number of units")},
        "measure": measure_purchase_order,
        "rules": ["min_cover", "arrives_in_time", "alternate_cost", "large_order"],
        # unit_cost is taken from the database, never from the AI
        "sql": """INSERT INTO purchase_orders (decision_id, component_id, supplier_id, quantity, unit_cost)
                  SELECT :decision_id, :component_id, :supplier_id, :quantity, unit_cost FROM offers
                  WHERE component_id = :component_id AND supplier_id = :supplier_id""",
    },
}


# ---------------------------------------------------------------- 4. RULES
# FAIL      = never allowed, nobody can approve it
# APPROVAL  = allowed only if a manager says yes
RULES = {
    "min_margin":      {"broken_if": lambda m: m["margin"] < 0.20,              "result": "FAIL",     "why": "margin below 20%"},
    "big_price_cut":   {"broken_if": lambda m: m["price_cut"] > 0.10,           "result": "APPROVAL", "why": "price cut above 10% needs a manager"},
    "min_cover":       {"broken_if": lambda m: m["days_of_stock_after"] < 15,   "result": "FAIL",     "why": "less than 15 days of stock after the order"},
    "arrives_in_time": {"broken_if": lambda m: m["late_by_days"] > 0,           "result": "FAIL",     "why": "delivery arrives after our stock runs out"},
    "alternate_cost":  {"broken_if": lambda m: m["extra_cost"] > 0.08,          "result": "APPROVAL", "why": "more than 8% dearer than the usual supplier needs a manager"},
    "large_order":     {"broken_if": lambda m: m["order_value"] > 250000,       "result": "APPROVAL", "why": "orders above Rs 2,50,000 need a manager"},
}


# ------------------------------------------------------------- 5. GUIDANCE
# Soft advice. The AI reads it, but code does not check it.
GUIDANCE = [
    "When we order, we order enough stock for about 30 days of use, rounded up to the nearest 10.",
    "Prefer the cheapest choice that passes every rule.",
]
