# Simple Decision Assistant (demo)

4 Python files. No classes. Run it in 2 minutes.

| File | What it is |
|---|---|
| `company.py` | **Everything about the company**: the graph links, the menu of database questions, the allowed actions (and how code measures them), the hard rules, the soft guidance. For another business, change only this file. |
| `connect.py` | **Connections**: PostgreSQL, the documents folder (PDF / Word / TXT), the vector index (RAG), the knowledge graph. |
| `agents.py` | **The agents**: the decision agent (plan -> fetch -> context -> decide -> verify), approve & write (once only), the learning agent (reads new documents). |
| `main.py` | **Control room**: runs the 4 start-up steps, then answers questions. |

Folders: `data/seed.sql` (sample company data), `documents/` (all documents: searched to answer questions, and read by the learning agent).

## Run

```bash
pip install -r requirements.txt
python main.py demo      # runs the full demo by itself
python main.py           # ask your own questions
```

## Connect your own systems

- **PostgreSQL / Neon**: `export DATABASE_URL="postgresql://user:password@host:5432/dbname"` (Windows: `set DATABASE_URL=...`).
  Without it, a local file `company.db` is used. Demo data is loaded only if the database is empty.
- **Documents**: put PDF, Word (.docx), .txt or .md files in `documents/`.
- **Groq (default, free)**: the key is written directly in `agents.py` (`ask_ai`). To use your own, make a free key at https://console.groq.com/keys (no credit card) and replace it there.
  The default model is `openai/gpt-oss-120b`. The free plan has a per-minute limit; the system waits and retries automatically.

## What happens when you start

1. Connect to the database
2. Read every document in the folder
3. Cut documents into pieces and turn them into vectors (RAG search)
4. Build the knowledge graph from the database (picture saved as `graph.png`)

## What you can ask

- "Apex Motors has told us the motor delivery will be 14 days late. What should we do?"
- "Zenith cut the price of its mixer to Rs 900. What price should our Mixer Grinder have?"
- "Should we reorder Jars?"  /  "We want to order 5000 jars. Is that ok?"
- "What do we know about the Motor?"
- "Which documents do we have?"
- "Read all the documents and update the knowledge graph."  then  "What do we know about Copper?"
- Type `upload` to add a new file: it is copied into `documents/`, summarised, and the learning agent suggests new graph links for you to approve.

## How a question is answered

1. **Plan**: the AI says what it needs, picked from menus in `company.py`
2. **Fetch**: code gets it from the database, documents and graph
3. **Context**: every piece gets an ID (F1 fact, D1 document, L1 link)
4. **Decide**: the AI answers using only that context and may propose one allowed action
5. **Verify**: code checks the citations, re-measures the action from the database, applies the rules
6. **Approve**: a person says yes, and the change is written once

## Safety in one line

The AI proposes, the code checks, a person approves. The AI never writes SQL, its maths is
re-done from the database, and the same write never happens twice.
