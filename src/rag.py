from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

from src.db import get_connection
from src.retrieve import retrieve

load_dotenv()

LLM_MODEL = "gpt-4o-mini"
DEFAULT_TOP_K = 5
TEMPERATURE = 0
MAX_TOKENS = 800
RELEVANCE_THRESHOLD = 0.5

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def build_prompt(query: str, chunks: list[dict]) -> tuple[str, str]:
    system_prompt = (
        "You are a precise assistant that answers questions using ONLY the "
        "context provided in the <context> block. Follow these rules strictly:\n"
        "1. Use only information found in the context. Do not rely on prior knowledge.\n"
        "2. If the context does not contain enough information to answer, say so "
        "explicitly and state that you don't have enough information.\n"
        "3. Cite the chunks you use with bracketed numbers like [1], [2], matching "
        "the chunk ids given in the context.\n"
        "4. Never invent facts, sources, or citations."
    )

    lines: list[str] = ["<context>"]
    for i, chunk in enumerate(chunks, start=1):
        source = chunk.get("source", "unknown")
        chunk_index = chunk.get("chunk_index", "")
        content = chunk.get("content", "")
        lines.append(f'<chunk id="{i}" source="{source}" chunk_index="{chunk_index}">')
        lines.append(content)
        lines.append("</chunk>")
    lines.append("</context>")
    context_block = "\n".join(lines)

    user_prompt = f"{context_block}\n\nQuestion: {query}"
    return system_prompt, user_prompt


def _min_distance(chunks: list[dict]) -> Optional[float]:
    if not chunks:
        return None
    return min(chunk["distance"] for chunk in chunks)


def generate_answer(query: str, chunks: list[dict]) -> str:
    min_dist = _min_distance(chunks)

    if not chunks or (min_dist is not None and min_dist > RELEVANCE_THRESHOLD):
        best = "n/a" if min_dist is None else f"{min_dist:.4f}"
        return (
            "I don't have enough information in the context to answer that "
            f"question. (best distance: {best}, threshold: {RELEVANCE_THRESHOLD})"
        )

    system_prompt, user_prompt = build_prompt(query, chunks)

    try:
        response = _get_client().chat.completions.create(
            model=LLM_MODEL,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        return f"There was an error generating the answer: {e}"


def ask(conn, query: str, top_k: int = DEFAULT_TOP_K) -> dict:
    chunks = retrieve(conn, query, top_k)
    answer = generate_answer(query, chunks)

    sources = [
        {
            "id": i,
            "source": chunk.get("source"),
            "chunk_index": chunk.get("chunk_index"),
            "distance": chunk.get("distance"),
        }
        for i, chunk in enumerate(chunks, start=1)
    ]

    return {
        "query": query,
        "answer": answer,
        "sources": sources,
        "min_distance": _min_distance(chunks),
    }


if __name__ == "__main__":
    # Ajusta las 2 primeras para que coincidan con el contenido de tus sample_docs.
    queries = [
        "What is PGVector and what is it used for?",
        "How does retrieval-augmented generation work?",
        "How do I make a pizza from scratch?",
    ]

    conn = get_connection()
    try:
        for query in queries:
            result = ask(conn, query)
            print("=" * 70)
            print(f"Q: {result['query']}")
            print("-" * 70)
            print(f"A: {result['answer']}")
            print("-" * 70)
            md = result["min_distance"]
            print(f"min_distance: {md:.4f}" if md is not None else "min_distance: n/a")
            print("sources:")
            for s in result["sources"]:
                dist = s["distance"]
                dist_str = f"{dist:.4f}" if dist is not None else "n/a"
                print(
                    f"  [{s['id']}] {s['source']} (chunk {s['chunk_index']}) "
                    f"distance={dist_str}"
                )
        print("=" * 70)
    finally:
        conn.close()
