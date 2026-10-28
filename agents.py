"""
agents.py  —  THE AGENTS. Har soch-samajh wala kaam AI karta hai.

Har sawaal in steps se guzarta hai:
  1. PLAN      AI batata hai ki use kya info chahiye (company.py ke menu se chun kar)
  2. FETCH     code wo info laata hai: database, documents (RAG) aur knowledge graph se
  3. DECIDE    AI info padh kar jawab deta hai, aur zarurat ho to EK action suggest karta hai
  4. RULES     code action ke asli number database se naapta hai aur company ke rules lagata hai
  5. EXPLAIN   AI sab kuch user ke liye seedhi, insaani bhasha mein likhta hai
  6. APPROVE   insaan "haan" bolta hai -> database mein sirf EK baar likha jaata hai

Learning agent: AI naya document padh kar naye graph rishte dhoondhta hai (insaan approve karta hai).
"""
import json   # AI ka JSON jawab <-> Python dict
import time   # free AI limit par thoda rukne ke liye
import uuid   # har decision ko unique id dene ke liye, jaise DEC-a3f9c1

from huggingface_hub.errors import HfHubHTTPError
from sqlalchemy import text

import company                                                  # menu, actions, rules
from connect import run_sql, search, read_file, build_vectors   # connect.py ke tools


# =====================================================================
# ask_ai
# AI model (Anthropic Claude) se baat karne ka EKLAUTA darwaza.
# Prompt bhejta hai, aur JSON jawab Python dict bana kar wapas deta hai.
# =====================================================================
AI_MODEL = "claude-haiku-4-5-20251001"


def ask_ai(prompt):
    from huggingface_hub import InferenceClient

    client = InferenceClient(base_url="https://api.anthropic.com/v1", api_key="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")

    # system message -> jawab sirf JSON mein aaye
    messages = [{"role": "system", "content": "Reply with one valid JSON object only. No markdown, no extra text."},
                {"role": "user", "content": prompt}]

    # rate limit -> 429 aaye to thoda ruk kar dobara try karo
    for attempt in range(6):
        try:
            reply = client.chat_completion(model=AI_MODEL, messages=messages, max_tokens=2000)
            break
        except HfHubHTTPError as e:
            if e.response is None or e.response.status_code != 429 or attempt == 5:
                raise
            wait = float(e.response.headers.get("retry-after", 20)) + 1
            print(f"        (AI rate limit reached, waiting {wait:.0f} seconds ...)")
            time.sleep(wait)
    answer = reply.choices[0].message.content

    # kabhi-kabhi model JSON ke aage-peeche ```json ya text likh deta hai -> sirf {...} wala hissa lo
    return json.loads(answer[answer.find("{"): answer.rfind("}") + 1])


# =====================================================================
# show
# Python data ko saaf text banata hai, taaki prompt mein AI ko bheja ja sake.
# =====================================================================
def show(data):
    return json.dumps(data, indent=1, default=str)


# =====================================================================
# STEP 1: plan  (AI)
# AI ko menu dikhate hain: cheezon ke naam/id, database sawaal, graph ke naam, document files.
# AI batata hai: "mujhe ye-ye chahiye".
# Return: {"database": [...], "graph": [...], "documents": [...]}
# =====================================================================
def plan(system, question):

    # things: company ki saari cheezein (product, component, supplier) -> sirf id aur naam
    # Kaam: user "Jars" bolta hai, AI isse samajhta hai ki id "C-JAR" hai.
    things = []
    for kind, sql in company.THINGS.items():
        for row in run_sql(system["db"], sql):
            thing = {"kind": kind}
            thing.update(row)
            things.append(thing)

    # menu: database sawaalon ka menu (sirf naam + description, SQL nahi)
    menu = {}
    for name, question_info in company.QUESTIONS.items():
        menu[name] = question_info["about"]

    # graph_names: graph ke saare naam (Jar, Motor, Apex Motors, ...)
    graph_names = sorted(system["graph"].nodes)

    # document_names: humare paas kaun-kaun si files hain, taaki AI sahi search words de
    document_names = []
    for doc in system["docs"]:
        document_names.append(doc["name"])

    prompt = f"""You plan what information is needed to answer a question for {company.COMPANY_NAME}.
You cannot see any data yet. Choose ONLY from the menus below.

EARLIER IN THIS CONVERSATION (use it to understand words like "it" or "this"): {show(system["history"][-3:])}

QUESTION: {question}

THINGS WE KNOW: {show(things)}

DATABASE QUESTIONS you may ask for (each needs one id): {show(menu)}

GRAPH: you may ask for the links of any of these names: {show(graph_names)}

DOCUMENTS we have: {show(document_names)}
You may give short search phrases to find the right parts of these documents.

TASK:
- "learn_documents" ONLY if the user tells you to read documents and update / add to the knowledge graph
  (an instruction like "read the documents and update the graph", "update it based on the documents").
  Put the file names they mean in "files" (from DOCUMENTS we have), or [] for all documents.
- "answer" for everything else, including questions ABOUT the graph or documents (like "is the graph updated?").

Ask for everything a careful manager would want to see. If the question is not about our business, return empty lists.
Reply with JSON only:
{{"task": "answer" or "learn_documents", "files": ["<file name>"],
 "database": [{{"query": "<name from the menu>", "id": "<id>"}}], "graph": ["<name>"], "documents": ["<search phrase>"]}}"""

    return ask_ai(prompt)


# =====================================================================
# STEP 2: fetch  (code)
# AI ne jo maanga, code wo asli data laata hai.
# Return: {"facts": [...], "documents": [...], "links": [...]}
# =====================================================================
def fetch(system, needs):

    facts = []       # database se aaye numbers
    documents = []   # documents ke milte-julte tukde
    links = []       # graph ke rishte

    # (a) DATABASE: menu ka SQL code chalata hai, AI ki di hui id ke saath
    for need in needs.get("database", []):
        query = company.QUESTIONS.get(need.get("query"))
        if query is None:
            continue                                  # menu mein nahi hai -> chhod do
        rows = run_sql(system["db"], query["sql"], id=need.get("id"))
        facts.append({"query": need.get("query"), "id": need.get("id"), "rows": rows})

    # (b) DOCUMENTS: har search phrase ke top tukde lao (duplicate nahi)
    for phrase in needs.get("documents", []):
        for piece in search(system["index"], phrase):
            already_have = False
            for doc in documents:
                if doc["text"] == piece["text"]:
                    already_have = True
            if not already_have:
                documents.append({"file": piece["doc"], "text": piece["text"]})

    # (c) GRAPH: har naam ke rishte lao (duplicate nahi)
    for name in needs.get("graph", []):
        for line in graph_links(system["graph"], name):
            if line not in links:
                links.append(line)

    document_files = []   # saari files ke naam, taaki "kaun se documents hain?" ka jawab mil sake
    for doc in system["docs"]:
        document_files.append(doc["name"])

    return {"facts": facts, "documents": documents, "links": links, "document_files": document_files}


# =====================================================================
# graph_links  (code)
# Graph par ek cheez se kya-kya juda hai, aur ek kadam aage bhi.
# Example "Jar":  "Mixer Grinder --USES--> Jar",  "Jar --SUPPLIED_BY--> ClearJar Plastics", ...
# =====================================================================
def graph_links(graph, name):

    if name not in graph:
        return []

    lines = []

    # Jo iski taraf arrow karte hain (a --> name), aur jo unki taraf (x --> a)
    for a, b, info in graph.in_edges(name, data=True):
        for x, y, info2 in graph.in_edges(a, data=True):
            lines.append(x + " --" + info2["link"] + "--> " + y)
        lines.append(a + " --" + info["link"] + "--> " + b)

    # Jinki taraf ye arrow karta hai (name --> b), aur jinki taraf wo (b --> y)
    for a, b, info in graph.out_edges(name, data=True):
        lines.append(a + " --" + info["link"] + "--> " + b)
        for x, y, info2 in graph.out_edges(b, data=True):
            lines.append(x + " --" + info2["link"] + "--> " + y)

    # Duplicate hatao, order wahi rakho
    unique_lines = []
    for line in lines:
        if line not in unique_lines:
            unique_lines.append(line)
    return unique_lines


# =====================================================================
# STEP 3: decide  (AI)
# AI ko asli data dikhate hain, aur poochte hain "kya karna chahiye?"
# AI jawab deta hai, aur zarurat ho to EK allowed action suggest karta hai.
# Return: {"answer": "...", "action": null ya "<naam>", "values": {...}}
# =====================================================================
def decide(system, question, context):

    # actions: AI kaun se kaam suggest kar sakta hai (sirf naam, description, values)
    actions = {}
    for action_name, action in company.ACTIONS.items():
        values_needed = {}
        for value_name, (value_type, description) in action["values"].items():
            values_needed[value_name] = description
        actions[action_name] = {"about": action["about"], "values": values_needed}

    # rules: company ke rules, plain English mein
    rules = []
    for rule in company.RULES.values():
        rules.append(rule["why"])

    prompt = f"""You are the decision assistant of {company.COMPANY_NAME}.

- Use the facts, document extracts and graph links below to answer.
- Propose AT MOST ONE action, and only from ALLOWED ACTIONS.
- Propose an action ONLY if the user asks for a pricing or ordering decision
  (for example "what should we do?", "should we reorder X?", "what price should Y have?", "order 500 X").
- Use null if the question only asks for information, or asks for something that is not an allowed action
  (for example updating the knowledge graph). Never pick an unrelated action instead.

EARLIER IN THIS CONVERSATION: {show(system["history"][-3:])}

QUESTION: {question}

FACTS (from the database): {show(context["facts"])}

DOCUMENT FILES WE HAVE: {show(context["document_files"])}

DOCUMENT EXTRACTS: {show(context["documents"])}

GRAPH LINKS: {show(context["links"])}

ALLOWED ACTIONS: {show(actions)}

COMPANY RULES (code will check your action against these): {show(rules)}

GUIDANCE: {show(company.GUIDANCE)}

Reply with JSON only:
{{"answer": "<short answer>", "action": null or "<action name>", "values": {{...}}}}"""

    return ask_ai(prompt)


# =====================================================================
# check_rules  (code)
# Naape hue numbers par company ke rules lagata hai. Sabse bura result jeetta hai:
#   koi FAIL toota -> "FAIL",  sirf APPROVAL wale -> "NEEDS MANAGER",  kuch nahi -> "PASS"
# Return: (result, toote rules ki list)
# =====================================================================
def check_rules(measures, rule_names):

    broken = []
    for rule_name in rule_names:
        rule = company.RULES[rule_name]
        if rule["broken_if"](measures):
            broken.append(rule)

    fail_reasons = []
    for rule in broken:
        if rule["result"] == "FAIL":
            fail_reasons.append(rule["why"])
    if fail_reasons:
        return "FAIL", fail_reasons

    if broken:
        reasons = []
        for rule in broken:
            reasons.append(rule["why"])
        return "NEEDS MANAGER", reasons

    return "PASS", []


# =====================================================================
# STEP 4: check_action  (code)
# AI ke suggest kiye action ke asli number database se naapta hai, phir rules lagata hai.
# Ye sirf rules ka check hai. Rules check karne ke liye number chahiye, isliye agar action
# ya uski values se number naape hi na ja sakein, to "CANNOT CHECK" aata hai.
# Return: (status, reasons, values, measures)
# =====================================================================
def check_action(system, decision):

    action_name = decision.get("action")
    if not action_name:
        return "NO ACTION", [], {}, {}                     # sirf jaankari wala sawaal

    action = company.ACTIONS.get(action_name)
    if action is None:
        return "CANNOT CHECK", ["'" + str(action_name) + "' is not one of our actions"], {}, {}

    # Values ko sahi type mein badlo, jaise quantity "360" -> 360
    values = {}
    try:
        for value_name, (value_type, description) in action["values"].items():
            values[value_name] = value_type(decision["values"][value_name])
    except (KeyError, TypeError, ValueError):
        return "CANNOT CHECK", ["the action needs " + ", ".join(action["values"])], {}, {}

    # Database se asli number naapo (company.py ka measure function)
    def sql_helper(sql, **v):
        return run_sql(system["db"], sql, **v)

    measures = action["measure"](sql_helper, values)
    if measures is None:
        return "CANNOT CHECK", ["we have no data for these values"], values, {}

    # Rules lagao
    status, reasons = check_rules(measures, action["rules"])
    return status, reasons, values, measures


# =====================================================================
# STEP 5: explain  (AI)
# Saari baat ko user ke liye seedhi, insaani bhasha mein likhta hai:
# kya hua, kya karna chahiye, kyun, aur rules ka result kya hai.
# Return: ek message (text)
# =====================================================================
def explain(question, context, decision, status, reasons, measures):

    prompt = f"""You are a friendly assistant talking to a manager at {company.COMPANY_NAME}.
Write the reply the manager will read. Use plain, natural, human language, like a helpful colleague.
No JSON, no ids like F1 or C-JAR, no field names like days_of_stock_after, no arrows like -->.
Keep it short: a few sentences, or a few simple bullet points if that is clearer.
Mention the important numbers in words a manager understands (for example "about 12 days of stock left").
All money is in Indian Rupees: write amounts like "Rs 21,600", never "$".

How to talk about the RULE CHECK RESULT:
- PASS: the suggestion follows all company rules and is ready for approval.
- NEEDS MANAGER: it is allowed, but a manager must approve it, and say why.
- FAIL: it breaks a company rule and cannot be done, say which rule, and suggest what could work instead.
- CANNOT CHECK: we could not check the suggestion against our rules, say so honestly.
- NO ACTION: just answer the question. If we have no information about it, say so politely.

QUESTION: {question}

INFORMATION WE FOUND: {show(context)}

SUGGESTION: {show(decision)}

NUMBERS MEASURED FROM OUR DATABASE: {show(measures)}

RULE CHECK RESULT: {status}
RULES BROKEN: {show(reasons)}

Reply with JSON only:
{{"message": "<the reply for the manager>"}}"""

    reply = ask_ai(prompt)
    return reply.get("message", "")


# =====================================================================
# AGENT 1: decision_agent
# Ek sawaal ke liye saare steps chalata hai aur insaani jawab deta hai.
# Result system["decisions"] mein save hota hai, taaki baad mein approve ho sake.
# =====================================================================
def decision_agent(system, question):

    needs = plan(system, question)                                       # 1. AI: kya chahiye

    # User ne documents padh kar graph update karne ko kaha -> learning agent ka kaam (main.py chalata hai)
    if needs.get("task") == "learn_documents":
        all_files = [doc["name"] for doc in system["docs"]]
        files = [f for f in needs.get("files", []) if f in all_files] or all_files
        system["history"].append({"question": question, "answer": "Read " + ", ".join(files) + " to update the knowledge graph."})
        return {"kind": "learn", "files": files}

    context = fetch(system, needs)                                       # 2. code: data lao
    decision = decide(system, question, context)                         # 3. AI: kya karein
    status, reasons, values, measures = check_action(system, decision)   # 4. code: rules
    message = explain(question, context, decision, status, reasons, measures)   # 5. AI: insaani jawab

    if decision.get("action"):
        kind = "decision"      # kuch badalna hai -> approve karna padega
    else:
        kind = "answer"        # sirf jawab hai

    decision_id = "DEC-" + uuid.uuid4().hex[:6]

    result = {
        "kind": kind,
        "id": decision_id,
        "action": decision.get("action"),
        "values": values,
        "status": status,
        "answer": message,                                    # ye user ko dikhta hai
        "details": {"plan": needs, "context": context,        # andar ki jaankari (debug ke liye)
                    "decision": decision, "measures": measures, "reasons": reasons},
    }
    system["decisions"][decision_id] = result
    system["history"].append({"question": question, "answer": message})
    return result


# =====================================================================
# STEP 6: approve_and_write  (code)
# Insaan approve karta hai. Rules ka result dekh kar change database mein EK HI BAAR likha jaata hai.
# =====================================================================
def approve_and_write(system, decision_id, role):

    d = system["decisions"].get(decision_id)

    if not d or not d["action"]:
        return "There is nothing to approve here."

    if d["status"] == "FAIL":
        return "Sorry, this can't be done because it breaks a company rule."
    if d["status"] not in ("PASS", "NEEDS MANAGER"):
        return "Sorry, this can't be approved because we could not check it against our rules."

    if d["status"] == "NEEDS MANAGER" and role != "manager":
        return "This one needs a manager's approval, so it has not been saved yet."

    # "with db.begin()" = sab ya kuch nahi
    with system["db"].begin() as c:

        # Diary (done_actions) mein decision_id likho. Pehle se hai -> rowcount 0.
        result = c.execute(
            text("INSERT INTO done_actions (key, done_at) VALUES (:k, CURRENT_TIMESTAMP) ON CONFLICT (key) DO NOTHING"),
            {"k": decision_id},
        )
        if not result.rowcount:
            return "This was already saved earlier, so nothing was saved again."

        # Pehli baar -> action ka SQL (company.py se) chalao
        sql_values = dict(d["values"])
        sql_values["decision_id"] = decision_id
        c.execute(text(company.ACTIONS[d["action"]]["sql"]), sql_values)

    return "Done! " + describe_action(system, d["action"], d["values"]) + " has been saved."


# =====================================================================
# describe_action
# Action ko ek seedhi line mein likhta hai, jaise "A purchase order for 360 x Jar from ClearJar Plastics".
# =====================================================================
def describe_action(system, action_name, values):

    # id se naam nikaalo, jaise "C-JAR" -> "Jar". Na mile to id hi dikhao.
    def name_of(table, thing_id):
        rows = run_sql(system["db"], "SELECT name FROM " + table + " WHERE id = :id", id=thing_id)
        if rows:
            return rows[0]["name"]
        return str(thing_id)

    if action_name == "create_purchase_order":
        return ("A purchase order for " + str(values["quantity"]) + " x " + name_of("components", values["component_id"])
                + " from " + name_of("suppliers", values["supplier_id"]))
    if action_name == "update_price":
        return "The new price of Rs " + str(values["new_price"]) + " for " + name_of("products", values["product_id"])
    return "The change"


# =====================================================================
# AGENT 2: learning_agent  (AI)
# AI document padh kar ek chhota summary likhta hai aur naye rishte (graph links) dhoondhta hai.
# Sirf SUGGEST karta hai. Graph tab badalta hai jab insaan approve kare (apply_learning).
# Return: ("<summary>", [("Delta Windings", "DEPENDS_ON", "Kolar Metals"), ...])
# =====================================================================
def learning_agent(system, file_path):

    file_text = read_file(file_path)

    # Graph mein abhi kaun se naam aur kaun se rishton ke type hain (AI ko example ke liye)
    graph_names = sorted(system["graph"].nodes)
    link_types = []
    for a, b, info in system["graph"].edges(data=True):
        if info["link"] not in link_types:
            link_types.append(info["link"])

    prompt = f"""You read a business document for {company.COMPANY_NAME}. Write a short summary of it (2-3 sentences),
and find relationships between companies, products, components and raw materials, to add to our knowledge graph.

THINGS ALREADY IN OUR GRAPH (use exactly these names when the document means the same thing): {show(graph_names)}
LINK TYPES WE USE (you may add new ones in the same UPPER_CASE style, like DEPENDS_ON, SUPPLIES, REQUIRES): {show(link_types)}

Direction of links:
- "<component> --SUPPLIED_BY--> <supplier>"
- "<company> --DEPENDS_ON--> <sub-supplier>"
- "<supplier> --SUPPLIES--> <raw material>"
- "<component> --REQUIRES--> <raw material>"

Only include relationships the document clearly states. Use short names (no "the", no "component").
Give each relationship only once, in one direction.

DOCUMENT:
{file_text}

Reply with JSON only:
{{"summary": "<2-3 sentences>", "links": [{{"from": "<name>", "link": "<LINK_TYPE>", "to": "<name>"}}]}}"""

    reply = ask_ai(prompt)

    # Sirf naye rishte rakho (jo graph mein pehle se hain, kisi bhi direction mein, wo nahi)
    proposal = []
    pairs = set()
    for item in reply.get("links", []):
        from_thing = str(item.get("from", "")).strip()
        link = str(item.get("link", "")).strip().upper().replace(" ", "_")
        to_thing = str(item.get("to", "")).strip()
        if not from_thing or not link or not to_thing:
            continue
        if system["graph"].has_edge(from_thing, to_thing) or system["graph"].has_edge(to_thing, from_thing):
            continue
        if frozenset((from_thing, to_thing)) in pairs:
            continue
        pairs.add(frozenset((from_thing, to_thing)))
        proposal.append((from_thing, link, to_thing))

    return reply.get("summary", ""), proposal


# =====================================================================
# apply_learning  (code)
# Insaan ke approve karne ke BAAD: naye rishte graph mein jodo.
# =====================================================================
def apply_learning(system, proposal):

    for from_thing, link, to_thing in proposal:
        system["graph"].add_edge(from_thing, to_thing, link=link)

    return "Got it! I added " + str(len(proposal)) + " new connections to the knowledge graph."


# =====================================================================
# add_document  (code)
# Naya (upload kiya hua) document search (RAG) mein daalo, taaki sawaalon ke jawab mein kaam aaye.
# =====================================================================
def add_document(system, file_path):

    file_name = file_path.split("/")[-1]
    system["docs"] = [doc for doc in system["docs"] if doc["name"] != file_name]
    system["docs"].append({"name": file_name, "text": read_file(file_path)})
    system["index"] = build_vectors(system["docs"])
