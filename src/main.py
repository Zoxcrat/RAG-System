from src.db import get_connection, init_schema
from src.ingestion.ingest import ingest_file
from src.answer.rag import ask

SAMPLE_DOCS_PATH = "data/sample_docs.txt"


def _print_result(result: dict) -> None:
    print("\n" + "-" * 70)
    print(result["answer"])
    print("-" * 70)
    md = result["min_distance"]
    print(f"min_distance: {md:.4f}" if md is not None else "min_distance: n/a")
    if result.get("pages"):
        print(f"pages: {', '.join(str(p) for p in result['pages'])}")
    if result["sources"]:
        print("sources:")
        for s in result["sources"]:
            dist = s["distance"]
            dist_str = f"{dist:.4f}" if dist is not None else "n/a"
            page = s.get("page_number")
            page_str = f"p.{page}" if page is not None else "p.n/a"
            print(
                f"  [{s['id']}] {s['source']} ({page_str}, chunk {s['chunk_index']}) "
                f"distance={dist_str}"
            )
    print()


def run_demo() -> None:
    conn = get_connection()
    try:
        init_schema(conn)

        choice = input(
            f"Reingest documents from {SAMPLE_DOCS_PATH}? [y/N]: "
        ).strip().lower()
        if choice in ("y", "yes", "s", "si"):
            try:
                n = ingest_file(conn, SAMPLE_DOCS_PATH)
                print(f"Ingested {n} chunks from {SAMPLE_DOCS_PATH}.")
            except Exception as e:
                print(f"Ingestion failed: {e}")

        print("\nAsk questions about the documents. Type 'exit' or 'quit' to leave.\n")

        while True:
            try:
                query = input("> ").strip()
                if not query:
                    continue
                if query.lower() in ("exit", "quit"):
                    break
                result = ask(conn, query)
                _print_result(result)
            except (EOFError, KeyboardInterrupt):
                break
            except Exception as e:
                print(f"Error: {e}\n")
                continue

        print("\nBye!")
    finally:
        conn.close()


if __name__ == "__main__":
    run_demo()
