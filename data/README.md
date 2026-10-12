# data/

This folder holds your private memory data for the RAG feature.

Put your conversation history in `dense_rag_memories.txt` here, then run:

```bash
python db_firsttime_init.py
```

from the repo root to (re)build the vector database in `../lancedb/`.

Files in this folder are gitignored. 
See the main [README](../README.md) for the expected file format.
