# Rebuilds ./lancedb from scratch from data/dense_rag_memories.txt:
# wipes any existing vector data, chunks + embeds the corpus, and
# rebuilds the full-text index. See README for the expected file format.

import db

path_to_data = "data/dense_rag_memories.txt"


def init(text_data: str):
    # mode="overwrite" drops any existing "documents" table first.
    # (db.db.drop_database() is a NO-OP on lancedb >= 0.17 — it warns and does
    # nothing, which corrupts the table on rebuild.)
    db.table = db.db.create_table("documents", schema=db.Messages, mode="overwrite")
    return db.vectorization(db.chunk(text_data), init=True)


if __name__ == "__main__":
    with open(path_to_data, encoding="utf-8") as file:
        text_data = file.read()
    init(text_data)
    print(db.search_docs("test"))
