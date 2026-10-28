"""
connect.py  —  CONNECT TO EVERYTHING AND GET READY.

  Step 1. connect_database()   -> PostgreSQL (or a local SQLite file for a quick demo)
  Step 2. load_documents()     -> read every PDF, Word, TXT and MD file in a folder
  Step 3. build_vectors()      -> cut documents into pieces and turn each piece into numbers (RAG)
  Step 4. build_graph()        -> build the knowledge graph from the database tables

No classes. Just functions.
"""
from pathlib import Path

import networkx as nx
from sqlalchemy import create_engine, text
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import company


# ------------------------------------------------------------ Step 1: database
def connect_database(url):
    """Connect to the database with one URL.
    PostgreSQL / Neon:  postgresql://user:password@host:5432/dbname
    Quick local demo:   sqlite:///company.db
    """
    url = url.replace("postgres://", "postgresql://", 1).replace("postgresql://", "postgresql+psycopg2://", 1)
    db = create_engine(url)
    with db.begin() as c:   # our own small table: remembers every write, so nothing is written twice
        c.execute(text("CREATE TABLE IF NOT EXISTS done_actions (key TEXT PRIMARY KEY, done_at TEXT)"))
    return db


def run_sql(db, sql, **values):
    """Run one SQL query and return the rows as a list of dicts."""
    with db.connect() as c:
        return [dict(r) for r in c.execute(text(sql), values).mappings()]


def load_demo_data_if_empty(db, seed_file):
    """Fill the database with demo data, but only if it has no products table yet."""
    try:
        run_sql(db, "SELECT 1 FROM products LIMIT 1")
        return "already has data"
    except Exception:
        sql = "\n".join(l for l in Path(seed_file).read_text().splitlines() if not l.strip().startswith("--"))
        with db.begin() as c:
            for statement in sql.split(";"):
                if statement.strip():
                    c.execute(text(statement))
        return "demo data loaded"


# ----------------------------------------------------------- Step 2: documents
def read_file(path):
    """Read the text of one file: PDF, Word (.docx), .txt or .md"""
    path = Path(path)
    if path.suffix == ".pdf":
        from pypdf import PdfReader
        return "\n\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    if path.suffix == ".docx":
        from docx import Document
        return "\n\n".join(p.text for p in Document(path).paragraphs if p.text.strip())
    return path.read_text(encoding="utf-8")


def load_documents(folder):
    """Read every supported file in the folder. Returns [{name, text}]"""
    docs = []
    for f in sorted(Path(folder).iterdir()):
        if f.suffix in (".pdf", ".docx", ".txt", ".md"):
            docs.append({"name": f.name, "text": read_file(f)})
    return docs


# -------------------------------------------------------- Step 3: vectors (RAG)
def cut_into_pieces(text, size=300):
    """Split text into pieces of about `size` letters, at paragraph breaks."""
    pieces, current = [], ""
    for para in [p.strip() for p in text.split("\n\n") if p.strip()]:
        if current and len(current) + len(para) > size:
            pieces.append(current)
            current = ""
        current = (current + "\n" + para).strip()
    return pieces + ([current] if current else [])


def build_vectors(docs):
    """Turn every piece of every document into a list of numbers (a vector).
    Here we use TF-IDF (free, offline). In production: Hugging Face embeddings + pgvector or Qdrant."""
    pieces = [{"doc": d["name"], "text": p} for d in docs for p in cut_into_pieces(d["text"])]
    model = TfidfVectorizer(stop_words="english")
    vectors = model.fit_transform([p["text"] for p in pieces])
    return {"pieces": pieces, "model": model, "vectors": vectors}


def search(index, question, top=2, min_score=0.08):
    """RAG search: find the pieces of text closest in meaning to the question."""
    q = index["model"].transform([question])
    scores = cosine_similarity(q, index["vectors"])[0]
    best = scores.argsort()[::-1][:top]
    return [{**index["pieces"][i], "score": round(float(scores[i]), 2)} for i in best if scores[i] >= min_score]


# ------------------------------------------------------------- Step 4: graph
def build_graph(db):
    """Knowledge graph: every row of the GRAPH_LINKS queries becomes an arrow A --LINK--> B."""
    graph = nx.DiGraph()
    for link, sql in company.GRAPH_LINKS:
        for row in run_sql(db, sql):
            graph.add_edge(row["a"], row["b"], link=link)
    return graph


def save_graph_picture(graph, path="graph.png"):
    """Optional: draw the graph so you can show it."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.figure(figsize=(11, 6))
    pos = nx.spring_layout(graph, seed=4, k=1.2)
    nx.draw(graph, pos, with_labels=True, node_color="#cfe0f5", node_size=2200, font_size=8, arrowsize=14, edge_color="#888")
    nx.draw_networkx_edge_labels(graph, pos, edge_labels=nx.get_edge_attributes(graph, "link"), font_size=7)
    plt.savefig(path, dpi=120, bbox_inches="tight")
    plt.close()
    return path
