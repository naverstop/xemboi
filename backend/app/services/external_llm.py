"""외부 LLM 2차 보강 — 듀얼 LLM(계획 3.6 / 항목 F).

1차 내부 LLM(Ollama) 답변을 받아 사주명식 근거 + RAG 출처를 바탕으로
검증/보강한 최종 본문을 생성한다. 실패/타임아웃/쿼터 초과 시 None 반환(graceful fallback).

프로바이더는 config로 전환 가능(`external_llm_provider`):
  - "claude" (기본) : Anthropic Claude. 모델은 `claude_model`("auto"면 최신 Opus 동적 선택).
  - "gemini"        : Google Gemini(레거시). 모델은 `gemini_model`.
  - "off"           : 보강 비활성.

각 SDK는 선택 설치(미설치/키 없음이면 해당 프로바이더는 is_enabled()=False).
"""
from __future__ import annotations

import logging
import re

from backend.app.core.config import get_settings

_log = logging.getLogger("saju.external_llm")

# ---- SDK 선택 설치 감지 ----
try:  # Anthropic Claude
    import anthropic  # type: ignore

    _HAS_ANTHROPIC = True
except Exception:  # noqa: BLE001
    anthropic = None  # type: ignore
    _HAS_ANTHROPIC = False

try:  # Google Gemini (레거시)
    import google.generativeai as genai  # type: ignore

    _HAS_GENAI = True
except Exception:  # noqa: BLE001
    genai = None  # type: ignore
    _HAS_GENAI = False


# ============================================================
# 공통: 보강 시스템 프롬프트
# ============================================================
_REFINE_SYSTEM = (
    "당신은 한국 명리학(사주팔자) 전문 감수자입니다. "
    "주어진 1차 답변을 사주명식 근거와 참고자료에 비추어 검증·보강하세요.\n"
    "원칙:\n"
    "1. 사실과 다르거나 근거 없는 단정은 수정/완화합니다.\n"
    "2. 사주명식 근거(일간 강약·오행·십성·대운)와 참고자료에 부합하도록 보강합니다.\n"
    "3. 길흉 단정은 피하고 흐름/가능성으로 설명합니다.\n"
    "4. 한국어로, 한자 술어는 한글(한자) 형식으로 표기합니다.\n"
    "5. 마크다운(헤더 #/##/###, 굵게 **, 목록 -·*, 번호 1., 표)을 쓰지 말고, 상담가가 말하듯 "
    "자연스러운 줄글 문단으로만 쓰세요. 1차 답변에 마크다운이 있으면 줄글로 풀어 고치세요.\n"
    "6. [현재 질문 집중] 반드시 지금의 [사용자 질문] 주제에 답하세요. 1차 답변이나 직전 대화가 다른 "
    "주제(예: 취업·재물)였더라도, 지금 질문이 다른 주제(예: 연애·결혼·이성운)이면 그 주제로 새로 풀이하고 "
    "이전 주제로 흘러가지 마세요.\n"
    "7. [날짜·간지] 특정 연도·날짜의 간지(세운·월운·일진)를 직접 계산·추측하지 말고 '[현재 시점 간지]'에 "
    "제공된 올해 세운만 그대로 인용하세요. 지나간 과거 연도(작년·재작년 등)는 회고하지 말고 올해·앞으로(미래) "
    "중심으로 답하세요. 제공 안 된 연도의 간지·한자를 지어내지 말고, 간지의 한글과 한자는 반드시 "
    "일치시키세요(예: 계묘=癸卯, 병오=丙午).\n"
    "8. 최종 '완성된 답변 본문'만 출력하세요. 메타설명·머리말·코드블록 없이 본문만.\n"
)

# vi 보강 시스템 — ko _REFINE_SYSTEM 의 의도(사실검증·근거보강·현재질문집중·간지인용·마크다운금지·본문만)를 vi 로.
# ko 는 '한국어로만/한글(한자)'을 강제하지만 vi 는 자연스러운 베트남어 + Hán-Việt 라틴 표기(Giáp/Ất, Tý/Sửu/Mão).
_REFINE_SYSTEM_VI = (
    "Bạn là chuyên gia thẩm định Tứ Trụ (Bát Tự). "
    "Hãy kiểm chứng và bổ sung bản luận giải sơ bộ dựa trên lá số và tư liệu tham khảo.\n"
    "Chỉ viết bằng tiếng Việt (chữ Quốc ngữ có dấu); thuật ngữ dùng Hán-Việt Latinh "
    "(Giáp/Ất, Tý/Sửu/Mão, Chính quan...). TUYỆT ĐỐI không dùng chữ Hán / tiếng Trung.\n"
    "Nguyên tắc:\n"
    "1. Sửa hoặc làm dịu những khẳng định sai sự thật hoặc vô căn cứ.\n"
    "2. Bám sát lá số (nhật can vượng/nhược, ngũ hành, thập thần, đại vận) và tư liệu tham khảo.\n"
    "3. Tránh khẳng định hung/cát tuyệt đối; diễn đạt theo xu hướng/khả năng.\n"
    "4. Không dùng markdown (tiêu đề #/##/###, in đậm **, danh sách -·*, đánh số 1., bảng); "
    "chỉ viết thành đoạn văn tự nhiên như đang tư vấn trực tiếp. Nếu bản nháp có markdown thì gỡ bỏ.\n"
    "5. [Tập trung câu hỏi hiện tại] Nhất định phải trả lời đúng chủ đề của [Câu hỏi] hiện tại. Dù bản "
    "nháp hay hội thoại trước đó nói về chủ đề khác (ví dụ công việc·tài lộc), nếu câu hỏi hiện tại là "
    "chủ đề khác (ví dụ tình duyên·hôn nhân), hãy luận giải lại theo chủ đề đó, không trôi về chủ đề cũ.\n"
    "6. [Ngày·Can Chi] Không tự tính hay đoán can chi (lưu niên·nguyệt vận·nhật thần) của năm/ngày cụ thể; "
    "chỉ trích dẫn đúng lưu niên năm nay được cung cấp ở '[Can Chi thời điểm hiện tại]'. Không hồi tưởng "
    "các năm đã qua; tập trung vào năm nay và tương lai. Không bịa can chi cho năm không được cung cấp.\n"
    "7. Chỉ xuất ra phần 'trả lời hoàn chỉnh', không lời dẫn/meta/khối mã.\n"
)


def _refine_system(locale: str = "ko") -> str:
    """보강 시스템 프롬프트 선택 — vi 는 베트남어, 그 외(ko)는 기존 한국어 원문 그대로."""
    return _REFINE_SYSTEM_VI if locale == "vi" else _REFINE_SYSTEM


def _build_user_block(
    *,
    question: str,
    draft: str,
    saju_summary: str | None,
    evidence: str | None,
    rag_context: str | None,
    dialect_instruction: str | None,
) -> str:
    parts: list[str] = []
    if saju_summary:
        parts.append(saju_summary)
    if evidence:
        parts.append(f"[사주명식 근거]\n{evidence}")
    if rag_context:
        parts.append(f"[참고자료]\n{rag_context}")
    parts.append(f"[사용자 질문]\n{question}")
    parts.append(f"[1차 답변(보강 대상)]\n{draft}")
    if dialect_instruction:
        parts.append(dialect_instruction)
    return "\n\n".join(parts)


# ============================================================
# 프로바이더 가용성
# ============================================================
def _provider() -> str:
    return (get_settings().external_llm_provider or "claude").strip().lower()


def is_enabled() -> bool:
    """외부 LLM 보강 사용 가능 여부(provider + SDK + 키 + config 토글)."""
    s = get_settings()
    if not s.external_llm_enabled:
        return False
    prov = _provider()
    if prov == "claude":
        return bool(_HAS_ANTHROPIC and s.anthropic_api_key)
    if prov == "gemini":
        return bool(_HAS_GENAI and s.google_api_key)
    return False  # "off" 또는 알 수 없는 값


# ============================================================
# Claude (Anthropic) — 기본 프로바이더
# ============================================================
_CLAUDE_FALLBACK = "claude-opus-4-8"  # 신모델 출시 시 갱신; auto 실패 시 폴백
_resolved_claude: str | None = None   # "auto" 결과 캐시


def _pick_latest_opus() -> str | None:
    """models.list에서 최신 Opus 모델 ID를 버전 내림차순으로 선택.

    Anthropic은 Gemini식 자동갱신 별칭(-latest)이 없으므로,
    Gemini의 _pick_latest_stable_flash와 동일하게 동적 조회로 '항상 최신'을 구현."""
    try:
        client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)  # type: ignore[union-attr]
        cands: list[str] = []
        for m in client.models.list():
            mid = getattr(m, "id", "") or ""
            if "opus" in mid.lower():
                cands.append(mid)

        def _ver(name: str) -> tuple[int, int]:
            # 날짜 스냅샷 접미사(-YYYYMMDD) 제거 후 major-minor 파싱.
            # (안 하면 'opus-4-20250514'의 날짜를 minor로 오인해 'opus-4-8'보다 높게 정렬됨)
            base = re.sub(r"-\d{8}$", "", name)
            mm = re.search(r"opus-(\d+)(?:-(\d+))?", base)
            return (int(mm.group(1)), int(mm.group(2) or 0)) if mm else (0, 0)

        cands.sort(key=_ver, reverse=True)
        return cands[0] if cands else None
    except Exception as e:  # noqa: BLE001
        _log.warning("claude models.list failed: %s: %s", type(e).__name__, e)
        return None


def resolve_claude_model() -> str:
    """사용할 Claude 모델명 결정.

    - "auto"        → models.list로 최신 Opus 동적 조회(캐시), 실패 시 폴백
    - "" (미설정)    → 폴백(claude-opus-4-8)
    - 그 외(명시 ID) → 그대로 사용
    """
    global _resolved_claude
    name = (get_settings().claude_model or "").strip()
    if name.lower() == "auto":
        if _resolved_claude is None:
            _resolved_claude = _pick_latest_opus() or _CLAUDE_FALLBACK
            _log.info("claude model auto-resolved: %s", _resolved_claude)
        return _resolved_claude
    return name or _CLAUDE_FALLBACK


def _refine_claude(user_block: str, locale: str = "ko") -> str | None:
    s = get_settings()
    try:
        # 긴 본문(2,000자+) 보강 생성은 실측 55~80초 — 기본 25s 타임아웃이면 항상 실패(조용히 폴백)
        # 하던 결함을 타로 QC(2026-07-03)에서 확인. SSE는 하트비트로 유지되므로 긴 대기 무해.
        client = anthropic.Anthropic(  # type: ignore[union-attr]
            api_key=s.anthropic_api_key,
            timeout=max(120.0, float(s.external_llm_timeout_sec)),
            max_retries=2,
        )
        # 긴 출력(A4 70%≈1.5~2.5K토큰) 대비 넉넉히. Opus 4.8: temperature/budget_tokens 미사용.
        resp = client.messages.create(
            model=resolve_claude_model(),
            max_tokens=8000,
            system=_refine_system(locale),
            messages=[{"role": "user", "content": user_block}],
        )
        text = "".join(
            getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text"
        ).strip()
        return text or None
    except Exception as e:  # noqa: BLE001
        _log.warning("claude refine failed: %s: %s", type(e).__name__, e)
        return None


_VISION_OCR_SYSTEM = (
    "당신은 정밀 OCR 전사기입니다. 주어진 이미지(스캔·손글씨 문서)에 보이는 한국어/한자/숫자 "
    "텍스트를 보이는 그대로 정확히 전사하세요. 줄바꿈·문단 구조를 유지하고, 도저히 읽을 수 없는 "
    "글자는 생략합니다. 설명·해석·머리말·코드블록 없이 '문서 본문 텍스트만' 출력하세요. "
    "표는 자연스러운 문장/목록으로 풀어 적습니다."
)


def vision_ocr_image(png_bytes: bytes, *, media_type: str = "image/png") -> str | None:
    """이미지 1장을 Claude 비전으로 전사(손글씨/저화질 스캔 대응). 비활성/실패 시 None.

    PaddleOCR이 못 읽는 손글씨·저화질 스캔의 폴백 전사용. 외부 API라 GPU 경합 없음.
    """
    if not is_enabled() or _provider() != "claude" or anthropic is None:
        return None
    import base64 as _b64
    s = get_settings()
    try:
        # 비전은 이미지 업로드·처리로 텍스트보다 오래 걸림 → 전용 긴 타임아웃.
        client = anthropic.Anthropic(  # type: ignore[union-attr]
            api_key=s.anthropic_api_key, timeout=max(120.0, float(s.external_llm_timeout_sec)),
            max_retries=2,
        )
        resp = client.messages.create(
            model=resolve_claude_model(),
            max_tokens=4000,
            system=_VISION_OCR_SYSTEM,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type,
                    "data": _b64.b64encode(png_bytes).decode("ascii"),
                }},
                {"type": "text", "text": "위 이미지의 텍스트를 전사하세요."},
            ]}],
        )
        text = "".join(
            getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text"
        ).strip()
        return text or None
    except Exception as e:  # noqa: BLE001
        _log.warning("claude vision ocr failed: %s: %s", type(e).__name__, e)
        return None


_VERIFY_KNOWLEDGE_SYSTEM = (
    "당신은 명리 지식 큐레이터입니다. 사용자에게 높은 평가(👍)를 받은 사주 상담 [질문]과 [답변]에서 "
    "'일반화 가능한 명리 지식·해석 원리'만 추출해 재사용 가능한 학습자료로 정리하세요.\n"
    "규칙:\n"
    "1. 개인정보·특정 명식 제거 — 이름·생년월일·나이·특정 사주팔자 간지·특정 연도 예언은 모두 빼고, "
    "'어떤 구성이면 어떤 해석'이라는 일반 원리로 환원합니다.\n"
    "2. 근거 있는 명리 원리(합·충·오행·십성·신살·용신·격국 등)와 해석 방법만 남깁니다.\n"
    "3. 일반화할 지식이 없으면(개인 잡담·인사뿐) 빈 출력(아무 글자도 쓰지 않음).\n"
    "4. 머리말·설명·코드블록 없이 정리된 지식 본문만. 2~6문장 권장."
)


def generalize_verified_knowledge(question: str, answer: str) -> str | None:
    """👍 받은 상담 Q&A에서 '개인정보·특정 명식을 제거한 일반 명리 지식'을 추출(검증 코퍼스용).

    개인 사주 유출·명식 특이성 문제를 차단하면서, 검증된 해석 원리만 학습자료로 환원한다.
    일반화할 게 없으면 None(건너뜀).
    """
    if not is_enabled() or _provider() != "claude" or anthropic is None:
        return None
    s = get_settings()
    try:
        client = anthropic.Anthropic(  # type: ignore[union-attr]
            api_key=s.anthropic_api_key, timeout=max(60.0, float(s.external_llm_timeout_sec)),
        )
        resp = client.messages.create(
            model=resolve_claude_model(),
            max_tokens=900,
            system=_VERIFY_KNOWLEDGE_SYSTEM,
            messages=[{"role": "user", "content": f"[질문]\n{question}\n\n[답변(👍)]\n{answer}"}],
        )
        text = "".join(
            getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text"
        ).strip()
        return text if (text and len(text) >= 20) else None
    except Exception as e:  # noqa: BLE001
        _log.warning("claude generalize failed: %s: %s", type(e).__name__, e)
        return None


# ============================================================
# Gemini (Google) — 레거시 프로바이더
# ============================================================
_GEMINI_FALLBACK = "gemini-flash-latest"
_resolved_gemini: str | None = None


def _pick_latest_stable_flash() -> str | None:
    """list_models에서 미리보기/특수목적(preview·tts·image·exp·lite)을 제외한
    최신 stable flash 모델명을 버전 내림차순으로 선택."""
    try:
        cands: list[str] = []
        for m in genai.list_models():  # type: ignore[union-attr]
            if "generateContent" not in getattr(m, "supported_generation_methods", []):
                continue
            n = m.name.replace("models/", "")
            low = n.lower()
            if "flash" not in low:
                continue
            if any(x in low for x in ("preview", "-tts", "-image", "-exp", "lite")):
                continue
            cands.append(n)

        def _ver(name: str) -> tuple[int, int]:
            mm = re.search(r"gemini-(\d+)(?:\.(\d+))?-flash", name)
            return (int(mm.group(1)), int(mm.group(2) or 0)) if mm else (0, 0)

        cands.sort(key=_ver, reverse=True)
        return cands[0] if cands else None
    except Exception as e:  # noqa: BLE001
        _log.warning("gemini list_models failed: %s: %s", type(e).__name__, e)
        return None


def resolve_gemini_model() -> str:
    """사용할 Gemini 모델명 결정(별칭/동적조회)."""
    global _resolved_gemini
    name = (get_settings().gemini_model or "").strip()
    if name.lower() == "auto":
        if _resolved_gemini is None:
            _resolved_gemini = _pick_latest_stable_flash() or _GEMINI_FALLBACK
            _log.info("gemini model auto-resolved: %s", _resolved_gemini)
        return _resolved_gemini
    return name or _GEMINI_FALLBACK


def _refine_gemini(user_block: str, locale: str = "ko") -> str | None:
    s = get_settings()
    try:
        genai.configure(api_key=s.google_api_key)  # type: ignore[union-attr]
        model = genai.GenerativeModel(  # type: ignore[union-attr]
            model_name=resolve_gemini_model(),
            system_instruction=_refine_system(locale),
        )
        resp = model.generate_content(
            user_block,
            request_options={"timeout": s.external_llm_timeout_sec},
        )
        text = (getattr(resp, "text", None) or "").strip()
        return text or None
    except Exception as e:  # noqa: BLE001
        _log.warning("gemini refine failed: %s: %s", type(e).__name__, e)
        return None


# ============================================================
# 공개 진입점
# ============================================================
# 로컬 엔진(Ollama) 전체 다운 시, 초안 없이 처음부터 본문을 생성하는 폴백용 시스템 프롬프트
_GENERATE_SYSTEM = (
    "당신은 한국 명리학(사주팔자) 전문 상담사입니다. "
    "사주명식 근거와 참고자료에 기반해 사용자 질문에 답하세요.\n"
    "원칙:\n"
    "1. 한국어로만 작성하고, 한자 술어는 한글(한자) 형식으로 병기합니다. 예: 정관(正官).\n"
    "2. 참고자료에 근거하고, 자료가 부족하면 솔직히 밝힙니다.\n"
    "3. 길흉 단정은 피하고 흐름/가능성으로 설명합니다.\n"
    "4. 근거→해석→조언 흐름으로 단락을 나눠 충분히(최소 1,200자) 설명합니다.\n"
    "5. 마크다운(헤더 #/##/###, 굵게 **, 목록 -·*, 번호 1., 표)을 쓰지 말고, 상담가가 말하듯 "
    "자연스러운 줄글 문단으로만 작성하세요.\n"
    "6. 최종 답변 본문만 출력하세요. 머리말·메타설명·코드블록 없이.\n"
)

# vi 생성 시스템 — ko _GENERATE_SYSTEM 의 의도(근거기반·흐름·분량·마크다운금지·본문만)를 vi 로.
_GENERATE_SYSTEM_VI = (
    "Bạn là chuyên gia tư vấn Tứ Trụ (Bát Tự). "
    "Hãy trả lời câu hỏi của người dùng dựa trên lá số và tư liệu tham khảo.\n"
    "Nguyên tắc:\n"
    "1. Chỉ viết bằng tiếng Việt (chữ Quốc ngữ có dấu); thuật ngữ dùng Hán-Việt Latinh "
    "(Giáp/Ất, Tý/Sửu/Mão, Chính quan...). TUYỆT ĐỐI không dùng chữ Hán / tiếng Trung.\n"
    "2. Dựa trên tư liệu tham khảo; nếu tư liệu thiếu thì nói thẳng.\n"
    "3. Tránh khẳng định hung/cát tuyệt đối; diễn đạt theo xu hướng/khả năng.\n"
    "4. Trình bày theo mạch căn cứ → luận giải → lời khuyên, chia đoạn đầy đủ (tối thiểu khoảng 1.200 ký tự).\n"
    "5. Không dùng markdown (tiêu đề #/##/###, in đậm **, danh sách -·*, đánh số 1., bảng); "
    "chỉ viết thành đoạn văn tự nhiên như đang tư vấn trực tiếp.\n"
    "6. Chỉ xuất ra phần trả lời hoàn chỉnh, không lời dẫn/meta/khối mã.\n"
)


def _generate_system(locale: str = "ko") -> str:
    """생성 시스템 프롬프트 선택 — vi 는 베트남어, 그 외(ko)는 기존 한국어 원문 그대로."""
    return _GENERATE_SYSTEM_VI if locale == "vi" else _GENERATE_SYSTEM


def _build_generate_block(
    *,
    question: str,
    saju_summary: str | None,
    evidence: str | None,
    rag_context: str | None,
    dialect_instruction: str | None,
) -> str:
    parts: list[str] = []
    if saju_summary:
        parts.append(saju_summary)
    if evidence:
        parts.append(f"[사주명식 근거]\n{evidence}")
    if rag_context:
        parts.append(f"[참고자료]\n{rag_context}")
    parts.append(f"[사용자 질문]\n{question}")
    if dialect_instruction:
        parts.append(dialect_instruction)
    return "\n\n".join(parts)


def generate_answer(
    *,
    question: str,
    saju_summary: str | None,
    evidence: str | None,
    rag_context: str | None,
    dialect_instruction: str | None = None,
    locale: str = "ko",
) -> str | None:
    """로컬 엔진(qwen3:14b) 전체 다운 시 외부 LLM으로 본문을 '처음부터' 생성하는 폴백.

    locale='vi' 면 베트남어 시스템 프롬프트로 생성(ko 는 기존 한국어 원문 그대로).
    성공 시 본문(str), 비활성/실패 시 None."""
    if not is_enabled():
        return None
    user_block = _build_generate_block(
        question=question, saju_summary=saju_summary, evidence=evidence,
        rag_context=rag_context, dialect_instruction=dialect_instruction,
    )
    system = _generate_system(locale)
    prov = _provider()
    try:
        if prov == "claude":
            s = get_settings()
            client = anthropic.Anthropic(  # type: ignore[union-attr]
                api_key=s.anthropic_api_key, timeout=s.external_llm_timeout_sec,
            )
            resp = client.messages.create(
                model=resolve_claude_model(), max_tokens=8000,
                system=system,
                messages=[{"role": "user", "content": user_block}],
            )
            text = "".join(
                getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text"
            ).strip()
            return text or None
        if prov == "gemini":
            s = get_settings()
            genai.configure(api_key=s.google_api_key)  # type: ignore[union-attr]
            model = genai.GenerativeModel(  # type: ignore[union-attr]
                model_name=resolve_gemini_model(), system_instruction=system,
            )
            resp = model.generate_content(
                user_block, request_options={"timeout": s.external_llm_timeout_sec},
            )
            return (getattr(resp, "text", None) or "").strip() or None
    except Exception as e:  # noqa: BLE001
        _log.warning("external generate failed: %s: %s", type(e).__name__, e)
    return None


def refine_answer(
    *,
    question: str,
    draft: str,
    saju_summary: str | None,
    evidence: str | None,
    rag_context: str | None,
    dialect_instruction: str | None = None,
    locale: str = "ko",
) -> str | None:
    """1차 답변을 외부 LLM으로 보강. 성공 시 최종 본문(str), 실패 시 None.

    locale='vi' 면 베트남어 시스템 프롬프트로 보강(ko 는 기존 한국어 원문 그대로).
    프로바이더는 config(`external_llm_provider`)에 따라 Claude/Gemini로 분기."""
    if not is_enabled():
        return None
    user_block = _build_user_block(
        question=question,
        draft=draft,
        saju_summary=saju_summary,
        evidence=evidence,
        rag_context=rag_context,
        dialect_instruction=dialect_instruction,
    )
    prov = _provider()
    if prov == "claude":
        return _refine_claude(user_block, locale)
    if prov == "gemini":
        return _refine_gemini(user_block, locale)
    return None
