"""Retrieval evaluation: vector-only vs hybrid vs hybrid+rerank on a gold set.

Metrics (over in_domain items):
  - recall@k : fraction of questions where a correct page appears in the top-k.
  - MRR@k    : mean of 1/(rank of the first chunk on a correct page), 0 if none in top-k.
Out_of_domain items check the relevance gate actually refuses.

All three arms are compared on the SAME candidate pool: vector top-10, the hybrid
fusion's top-10, and that same fused pool reranked down to 10.

Run inside the container (needs the DB + OPENAI_API_KEY for embeddings + reranking):
  docker compose run --rm --entrypoint python app -m eval.evaluate     # or: make eval
"""
import json

from src import config
from src.db import get_connection
from src.rag import ask
from src.rerank import rerank
from src.retrieve import retrieve, retrieve_hybrid, retrieve_multi

K_VALUES = (5, 10)
ARMS = ("vector", "hybrid", "hybrid+rerank", "expand+rerank")
GOLD = json.load(open("eval/gold_set.json", encoding="utf-8"))["items"]
IN_DOMAIN = [i for i in GOLD if i["type"] == "in_domain"]


def _first_hit_rank(chunks: list[dict], gold_pages: set) -> int | None:
    """1-based rank of the first retrieved chunk whose page is a correct page."""
    for rank, chunk in enumerate(chunks, start=1):
        if chunk.get("page_number") in gold_pages:
            return rank
    return None


def _score_arm(top10: dict[str, list[dict]]) -> dict:
    """recall@k and MRR@k for every k in K_VALUES from cached top-10 lists."""
    out = {}
    for k in K_VALUES:
        hits = rr = 0.0
        for item in IN_DOMAIN:
            rank = _first_hit_rank(top10[item["question"]][:k], set(item["pages"]))
            if rank is not None:
                hits += 1
                rr += 1.0 / rank
        out[k] = {"recall": hits / len(IN_DOMAIN), "mrr": rr / len(IN_DOMAIN)}
    return out


def main() -> None:
    conn = get_connection()
    try:
        # Same candidate pool for every arm: vector top-10, the hybrid fusion's
        # top-10, and that fused pool reranked down to 10.
        top10 = {arm: {} for arm in ARMS}
        for item in IN_DOMAIN:
            q = item["question"]
            top10["vector"][q] = retrieve(conn, q, top_k=10)
            fused = retrieve_hybrid(conn, q, top_k=config.RERANK_CANDIDATES)
            top10["hybrid"][q] = fused[:10]
            top10["hybrid+rerank"][q] = rerank(q, fused, top_k=10)
            expanded = retrieve_multi(conn, q, top_k=config.RERANK_CANDIDATES)
            top10["expand+rerank"][q] = rerank(q, expanded, top_k=10)

        scores = {arm: _score_arm(top10[arm]) for arm in ARMS}

        print(f"\n=== Retrieval quality on {len(IN_DOMAIN)} in-domain questions ===")
        header = f"{'metric':<12}" + "".join(f"{a:>16}" for a in ARMS)
        print(header)
        for k in K_VALUES:
            for m in ("recall", "mrr"):
                row = f"{m + '@' + str(k):<12}"
                row += "".join(f"{scores[a][k][m]:>16.3f}" for a in ARMS)
                print(row)

        print("\n=== per-question (rank of first correct page; '-' = miss in top-10) ===")
        print(f"{'question':<50}" + "".join(f"{a:>16}" for a in ARMS))
        for item in IN_DOMAIN:
            q = item["question"]
            gp = set(item["pages"])
            cells = "".join(
                f"{str(_first_hit_rank(top10[a][q], gp) or '-'):>16}" for a in ARMS
            )
            print(f"{q[:48]:<50}{cells}")

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
