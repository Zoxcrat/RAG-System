"""Retrieval evaluation: vector-only vs hybrid search on a curated gold set.

Metrics (over in_domain items):
  - recall@k : fraction of questions where a correct page appears in the top-k.
  - MRR@k    : mean of 1/(rank of the first chunk on a correct page), 0 if none in top-k.
Out_of_domain items check the relevance gate actually refuses.

Run inside the container (needs the DB + OPENAI_API_KEY for query embeddings):
  docker compose run --rm --entrypoint python app -m eval.evaluate
"""
import json

from src.db import get_connection
from src.rag import ask
from src.retrieve import retrieve, retrieve_hybrid

K_VALUES = (5, 10)
GOLD = json.load(open("eval/gold_set.json", encoding="utf-8"))["items"]


def _first_hit_rank(chunks: list[dict], gold_pages: set) -> int | None:
    """1-based rank of the first retrieved chunk whose page is a correct page."""
    for rank, chunk in enumerate(chunks, start=1):
        if chunk.get("page_number") in gold_pages:
            return rank
    return None


def _score_arm(retrieve_top10: dict[str, list[dict]]) -> dict:
    """Compute recall@k and MRR@k for every k in K_VALUES from cached top-10 lists."""
    out = {}
    for k in K_VALUES:
        hits = 0
        rr = 0.0
        n = 0
        for item in GOLD:
            if item["type"] != "in_domain":
                continue
            n += 1
            rank = _first_hit_rank(retrieve_top10[item["question"]][:k], set(item["pages"]))
            if rank is not None:
                hits += 1
                rr += 1.0 / rank
        out[k] = {"recall": hits / n, "mrr": rr / n, "n": n}
    return out


def main() -> None:
    conn = get_connection()
    try:
        # Retrieve top-10 once per arm per question; top-5 is just a slice.
        vec_top10, hyb_top10 = {}, {}
        for item in GOLD:
            if item["type"] != "in_domain":
                continue
            q = item["question"]
            vec_top10[q] = retrieve(conn, q, top_k=10)
            hyb_top10[q] = retrieve_hybrid(conn, q, top_k=10)

        vec = _score_arm(vec_top10)
        hyb = _score_arm(hyb_top10)

        n = vec[K_VALUES[0]]["n"]
        print(f"\n=== Retrieval quality on {n} in-domain questions ===")
        print(f"{'metric':<12}{'vector-only':>14}{'hybrid':>12}{'Δ':>10}")
        for k in K_VALUES:
            for m in ("recall", "mrr"):
                v, h = vec[k][m], hyb[k][m]
                print(f"{m+'@'+str(k):<12}{v:>14.3f}{h:>12.3f}{h-v:>+10.3f}")

        # Per-question detail: where hybrid rescues a miss.
        print("\n=== per-question (rank of first correct page; '-' = miss in top-10) ===")
        print(f"{'question':<52}{'vec':>5}{'hyb':>5}")
        for item in GOLD:
            if item["type"] != "in_domain":
                continue
            q = item["question"]
            gp = set(item["pages"])
            rv = _first_hit_rank(vec_top10[q], gp) or "-"
            rh = _first_hit_rank(hyb_top10[q], gp) or "-"
            flag = "  <-- rescued" if (rv == "-" and rh != "-") else ""
            print(f"{q[:50]:<52}{str(rv):>5}{str(rh):>5}{flag}")

        # Out-of-domain: the gate must refuse (no LLM call).
        print("\n=== out-of-domain (gate must refuse) ===")
        for item in GOLD:
            if item["type"] != "out_of_domain":
                continue
            answer = ask(conn, item["question"])["answer"].lower()
            refused = "not enough information" in answer or "don't have enough" in answer
            print(f"  {'PASS' if refused else 'FAIL'}  {item['question']}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
