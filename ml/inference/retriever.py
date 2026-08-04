"""RAG 검색기: Qdrant + BGE-m3."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm


@dataclass
class RetrievedChunk:
    source: str
    chunk_id: int
    text: str
    score: float


@lru_cache(maxsize=1)
def _load_embedder(device: str | None = None):
    from sentence_transformers import SentenceTransformer
    import torch

    dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
    return SentenceTransformer("BAAI/bge-m3", device=dev)


@lru_cache(maxsize=1)
def _load_reranker(model_name: str, device: str = "cuda"):
    """Cross-encoder 리랭커(BGE-reranker-v2-m3). predict()→sigmoid 관련도(0~1)."""
    from sentence_transformers import CrossEncoder
    import torch

    dev = device if (device != "cuda" or torch.cuda.is_available()) else "cpu"
    kw = {"model_kwargs": {"torch_dtype": torch.float16}} if dev == "cuda" else {}
    # max_length 512: 질문+청크 관련도 판단엔 충분, 긴 청크 잘라 지연 단축.
    return CrossEncoder(model_name, device=dev, max_length=512, **kw)


class SajuRetriever:
    def __init__(
        self,
        url: str = "http://127.0.0.1:6333",
        collection: str = "saju_corpus",
        device: str | None = None,
        pdf_boost: float = 0.0,
        over_fetch: int = 4,
        reranker_model: str | None = None,
        reranker_device: str = "cuda",
    ):
        """pdf_boost: 스캔본 책(category!=youtube)에 가산하는 점수 보너스.
        유튜브 자막보다 책을 우선 노출시키기 위한 재랭킹용. 0이면 순수 코사인.
        over_fetch: 재랭킹 후보를 top_k*over_fetch 만큼 더 가져옴.
        reranker_model: 주면 cross-encoder 리랭커 사용(search rerank=True 시). None이면 미사용.
        """
        # gRPC 전송: httpx(HTTP)는 같은 프로세스에 CUDA 모델(리랭커) 로드 시 요청당 ~2초로
        # 느려지는 간섭이 있음(실측 httpx 2050ms vs gRPC ~10ms). gRPC로 회피 + 본래 더 빠름.
        self.client = QdrantClient(url=url, timeout=30.0, prefer_grpc=True)
        self.collection = collection
        self.embedder = _load_embedder(device)
        self.pdf_boost = pdf_boost
        self.over_fetch = max(1, over_fetch)
        self.reranker_model = reranker_model
        self.reranker_device = reranker_device
        self._reranker_obj = None  # lazy load

    def _reranker(self):
        if not self.reranker_model:
            return None
        if self._reranker_obj is None:
            self._reranker_obj = _load_reranker(self.reranker_model, self.reranker_device)
        return self._reranker_obj

    @staticmethod
    def _is_book(payload: dict) -> bool:
        """스캔본 책/문서(=유튜브가 아닌 모든 출처)면 True."""
        return (payload.get("category") or "") != "youtube"

    @staticmethod
    def _tier(payload: dict) -> int:
        """payload의 신뢰등급. 미태깅 폴백: youtube=3, 그 외=2(=책>유튜브 보존)."""
        t = (payload or {}).get("trust_tier")
        if t is None:
            return 3 if (payload or {}).get("category") == "youtube" else 2
        return int(t)

    def search(
        self,
        query: str,
        top_k: int = 5,
        source: str | None = None,
        *,
        min_score: float = 0.0,
        exclude_low_quality: bool = False,
        exclude_examples: bool = False,
        exclude_youtube: bool = False,
        tier_boosts: dict[int, float] | None = None,
        rerank: bool = False,
        rerank_top_n: int = 24,
        rerank_min_score: float = 0.0,
    ) -> list[RetrievedChunk]:
        """RAG 검색 + 신뢰성 게이트 (+ 선택적 cross-encoder 리랭킹).

        - min_score: 코사인 점수 미만 청크 제거(저관련 노이즈 차단). 0이면 미적용.
        - exclude_low_quality: OCR 깨짐 등 low_quality=true 청크 제외.
        - exclude_examples: 예시명식(is_example=true) 청크 제외(사주상담 오염 방지).
        - tier_boosts: {1:..,2:..,3:..} 신뢰등급 가산 재랭킹. None이면 pdf_boost(책>유튜브) 사용.
        - rerank: True면 dense top_n 후보를 cross-encoder로 재점수→top_k(코사인 압축 해결).
          rerank_min_score(sigmoid 0~1) 미만은 드롭. 신뢰등급은 동점 보정(2차 정렬).
        """
        vec = self.embedder.encode(
            [query], normalize_embeddings=True, convert_to_numpy=True
        )[0].tolist()
        must = []
        must_not = []
        if source:
            must.append(qm.FieldCondition(key="source", match=qm.MatchValue(value=source)))
        if exclude_low_quality:
            must_not.append(qm.FieldCondition(key="low_quality", match=qm.MatchValue(value=True)))
        if exclude_examples:
            must_not.append(qm.FieldCondition(key="is_example", match=qm.MatchValue(value=True)))
        if exclude_youtube:
            # 유튜브 자막(잡담·타인 사주)은 키워드로 오검색돼 답변을 오염 → 검색 근거에서 완전 배제.
            must_not.append(qm.FieldCondition(key="category", match=qm.MatchValue(value="youtube")))
        flt = qm.Filter(must=must or None, must_not=must_not or None) if (must or must_not) else None

        do_rerank = rerank and not source and self._reranker() is not None
        tier_rerank = (tier_boosts is not None or self.pdf_boost > 0) and not source
        if do_rerank:
            limit = max(rerank_top_n, top_k)            # dense 후보 넉넉히 → 리랭커가 선별
        elif tier_rerank or min_score > 0 or exclude_low_quality or exclude_examples:
            limit = top_k * self.over_fetch
        else:
            limit = top_k
        res = self.client.query_points(
            collection_name=self.collection,
            query=vec,
            limit=limit,
            query_filter=flt,
            with_payload=True,
        ).points

        if do_rerank and res:
            # [RAG 전수감사 2026-07-22] 이 분기에 min_score·tier_boosts 가 없어 두 설정이
            # 죽어 있었다 — min_score 를 0.45→0.99 로 올려도 결과가 완전히 동일했고,
            # tier1 boost 를 9.9 로 줘도 상위 4건이 그대로였다(감수 자료 우대가 무효).
            # → dense 하한을 리랭커 앞에서 적용하고, 신뢰등급 가중치를 리랭커 점수에 실제로 더한다.
            if min_score > 0:
                res = [h for h in res if h.score >= min_score]
            scores = self._reranker().predict(
                [(query, h.payload["text"]) for h in res]) if res else []
            ranked = []
            for h, p in zip(res, scores):
                p = float(p)
                if p < rerank_min_score:
                    continue            # 관련도 임계는 원점수로 판정(가중치로 통과시키지 않는다)
                if tier_boosts is not None:   # 통과한 것들 사이에서만 감수 자료를 우대
                    p += tier_boosts.get(self._tier(h.payload), tier_boosts.get(2, 0.0))
                ranked.append((h, p))
            ranked.sort(key=lambda hp: (hp[1], -self._tier(hp[0].payload)), reverse=True)
            res = [h for h, _p in ranked][:top_k]
        else:
            if min_score > 0:
                res = [h for h in res if h.score >= min_score]
            if tier_rerank:
                def _boost(h) -> float:
                    if tier_boosts is not None:
                        return tier_boosts.get(self._tier(h.payload), tier_boosts.get(2, 0.0))
                    return self.pdf_boost if self._is_book(h.payload) else 0.0
                res = sorted(res, key=lambda h: h.score + _boost(h), reverse=True)
            res = res[:top_k]

        return [
            RetrievedChunk(
                source=hit.payload["source"],
                chunk_id=hit.payload["chunk_id"],
                text=hit.payload["text"],
                score=hit.score,  # 표시용은 원본 코사인 점수(리랭커 점수는 정렬·필터에만)
            )
            for hit in res
        ]
