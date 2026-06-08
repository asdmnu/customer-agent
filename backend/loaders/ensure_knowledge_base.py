from backend.loaders.pgvector_ingest import (
    ingest_documents,
    load_source_documents,
    should_reset_vector_store,
    split_documents,
)
from backend.stores.pgvector_store import PGVectorStore


def main() -> None:
    vector_store = PGVectorStore()
    documents = load_source_documents()
    if not should_reset_vector_store():
        documents = vector_store.filter_uningested_documents(documents)
    if not documents:
        print("No new knowledge files found, skip ingest.")
        return

    chunks = split_documents(documents)
    ingest_documents(chunks, vector_store)
    print(f"Ingested {len(documents)} documents and {len(chunks)} chunks.")


if __name__ == "__main__":
    main()
