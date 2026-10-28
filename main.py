"""
main.py  —  THE CONTROL ROOM. Run this file.

    python main.py          -> start the system and ask your own questions
    python main.py demo     -> start the system and run the full demo by itself

It does 4 steps, in order, then waits for questions.
"""
import os
import shutil
import subprocess
import sys

import agents
import connect

# ---------------------------------------------------------------- SETTINGS
# Change these to connect to your own systems.
DATABASE_URL     = os.environ.get("DATABASE_URL", "sqlite:///company.db")   # e.g. postgresql://user:pass@host:5432/db
DOCUMENTS_FOLDER = "documents"          # put your PDF, Word, TXT files here
DEMO_DATA        = "data/seed.sql"      # sample company data (used only if the database is empty)


def start():
    print("\n=== STARTING THE SYSTEM ===")

    print("Step 1. Connecting to the database ...")
    db = connect.connect_database(DATABASE_URL)
    print("        connected:", DATABASE_URL.split("@")[-1], "|", connect.load_demo_data_if_empty(db, DEMO_DATA))

    print("Step 2. Reading documents from the folder ...")
    docs = connect.load_documents(DOCUMENTS_FOLDER)
    print("        read", len(docs), "files:", ", ".join(d["name"] for d in docs))

    print("Step 3. Building the vector index (RAG) ...")
    index = connect.build_vectors(docs)
    print("        ", len(index["pieces"]), "pieces of text turned into vectors")

    print("Step 4. Building the knowledge graph ...")
    graph = connect.build_graph(db)
    print("        ", graph.number_of_nodes(), "things,", graph.number_of_edges(), "links |  picture saved:", connect.save_graph_picture(graph))

    print("=== READY ===\n")
    return {"db": db, "docs": docs, "index": index, "graph": graph, "decisions": {}, "history": []}


def ask(system, question, approve_as=None, write_twice=False):
    """Ask one question and show the assistant's reply in plain language.
    If approve_as is given, also approve it (used by the demo)."""
    print("\n" + "-" * 78)
    print("You:", question)
    print("-" * 78)
    result = agents.decision_agent(system, question)
    if result["kind"] == "learn":
        learn(system, result["files"], auto_approve=approve_as is not None)
        return result
    print("Assistant:", result["answer"])
    if result["kind"] == "decision" and approve_as:
        print(f"\n[{approve_as} clicks Approve] ", agents.approve_and_write(system, result["id"], approve_as))
        if write_twice:
            print(f"[{approve_as} clicks Approve again] ", agents.approve_and_write(system, result["id"], approve_as))
    return result


def link_in_words(frm, link, to):
    """Turn  Motor --REQUIRES--> Copper  into  'Motor requires Copper'."""
    return f"{frm} {link.lower().replace('_', ' ')} {to}"


def learn(system, file_names, auto_approve=False):
    """Learning agent reads each document in the documents folder, summarises it and suggests new graph links.
    The graph only changes after approval (auto_approve is used by the demo)."""
    proposal = []
    for name in file_names:
        print("\n" + "-" * 78)
        print("Reading document:", name)
        print("-" * 78)
        summary, links = agents.learning_agent(system, os.path.join(DOCUMENTS_FOLDER, name))
        print("Summary:", summary)
        new_links = [l for l in links if {l[0], l[2]} not in [{p[0], p[2]} for p in proposal]]
        if new_links:
            print("Suggested additions to the knowledge graph:")
            for frm, link, to in new_links:
                print("  -", link_in_words(frm, link, to))
        else:
            print("Nothing new for the knowledge graph in this document.")
        proposal += new_links

    if not proposal:
        return proposal
    if auto_approve:
        print("\n[approved] ", end="")
    elif not input(f"\nAdd these {len(proposal)} connections to the knowledge graph? (yes/no): ").lower().startswith("y"):
        print("OK, the knowledge graph was not changed.")
        return proposal
    print(agents.apply_learning(system, proposal), "| picture updated:", connect.save_graph_picture(system["graph"]))
    return proposal


def choose_file():
    """Open the computer's file picker window. Returns the chosen path, or "" if cancelled."""
    print("A file picker window has opened. Choose a PDF, Word (.docx), .txt or .md file ...")
    if sys.platform == "darwin":
        picked = subprocess.run(["osascript", "-e", 'POSIX path of (choose file with prompt "Choose a document to upload")'],
                                capture_output=True, text=True)
        if picked.returncode == 0 or "User canceled" in picked.stderr:
            return picked.stdout.strip()
    try:
        import tkinter
        from tkinter import filedialog
        window = tkinter.Tk()
        window.withdraw()
        window.attributes("-topmost", True)
        path = filedialog.askopenfilename(title="Choose a document to upload",
                                          filetypes=[("Documents", "*.pdf *.docx *.txt *.md")])
        window.destroy()
        return path
    except Exception:
        return input("Could not open a file picker. Type the file's full path: ").strip().strip("'\"").replace("\\ ", " ")


def upload(system):
    """Copy a new file into the documents folder, make it searchable, and let the learning agent read it."""
    path = choose_file()
    if not path:
        print("No file chosen.")
        return
    if not os.path.isfile(path):
        print("I could not find that file:", path)
        return
    if not path.endswith((".pdf", ".docx", ".txt", ".md")):
        print("Please upload a PDF, Word (.docx), .txt or .md file.")
        return
    name = os.path.basename(path)
    target = os.path.join(DOCUMENTS_FOLDER, name)
    if os.path.abspath(path) != os.path.abspath(target):
        shutil.copy(path, target)
    agents.add_document(system, target)
    print(f"Saved {name} in the {DOCUMENTS_FOLDER} folder. It can now be used to answer questions.")
    system["history"].append({"question": "I uploaded " + name, "answer": "Saved " + name + " in the documents folder."})
    learn(system, [name])


def demo(system):
    ask(system, "Apex Motors has told us the motor delivery will be 14 days late. What should we do?",
        approve_as="manager", write_twice=True)
    ask(system, "Zenith cut the price of its mixer to Rs 900. What price should our Mixer Grinder have?")
    ask(system, "Should we reorder Jars?", approve_as="analyst")
    big = ask(system, "We want to order 5000 jars. Is that ok?", approve_as="analyst")
    print("[manager clicks Approve] ", agents.approve_and_write(system, big["id"], "manager"))
    ask(system, "What do we know about the Motor?")
    ask(system, "Which documents do we have?")
    ask(system, "What is the weather today?")
    ask(system, "Read all the documents in the documents folder and update the knowledge graph.", approve_as="manager")
    ask(system, "What do we know about Copper?")


def chat(system):
    print("What would you like to do?")
    print("  - Type a question, or ask me to read the documents and update the knowledge graph")
    print("  - Type 'upload' to choose a new document from your computer")
    print("  - Type 'quit' to stop")
    while True:
        q = input("\nYou: ").strip()
        if q.lower() in ("quit", "exit", ""):
            break
        if q.lower() == "upload":
            upload(system)
            continue
        result = ask(system, q)
        if result["kind"] == "decision" and result["status"] in ("PASS", "NEEDS MANAGER"):
            if input("\nDo you want to approve this? (yes/no): ").lower().startswith("y"):
                role = input("Your role (manager/analyst): ").strip().lower()
                print(agents.approve_and_write(system, result["id"], role))


if __name__ == "__main__":
    system = start()
    demo(system) if "demo" in sys.argv else chat(system)
