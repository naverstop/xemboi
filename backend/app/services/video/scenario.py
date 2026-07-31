"""시나리오 생성 — exaone 단일 결합 호출(PoC 검증: ~6s).

3인칭 답변 → 1인칭 압축 스토리 + 장면 JSON을 한 번에. 외부 LLM 금지(로컬 only).
출력 후 _strip_md 재적용(LLM이 마크다운 재삽입하므로). 부록 B-7.
"""
from __future__ import annotations

import json
import re
import urllib.request

from backend.app.core.config import get_settings
from backend.app.services.pdf_service import _strip_md
from backend.app.services.video.source import VideoSource

_SYS = (
    "너는 '이 사람의 실제 사주 상담답변'을 {sec}초 영상용 1인칭 자전 내레이션으로 충실히 옮기는 작가다. "
    "장면마다 감정이 자연스럽게 흐르되(과장·신파 금지, 진솔하게), 내용은 반드시 아래 [상담답변]에서 가져온다. "
    "듣는 이가 '내 사주 이야기다'라고 느끼게, 답변의 구체 분석을 1인칭으로 생생히 전한다. "
    "출력은 JSON 객체 하나만(마크다운/설명/주석 절대 금지). 키는 정확히 5개: "
    "\"초년\"(0~7세 아기·유아), \"유년\"(8~19세 학창), \"청년\"(20~39세), \"장년\"(40~59세), \"노년\"(60세 이상). "
    "각 키의 값은 그 나이대의 일만 1인칭으로 쓴 객체 "
    "{{\"line\":\"감정이 살아있는 1인칭 내레이션\",\"emotion\":\"설렘|기쁨|희망|벅참|평온|회상|아쉬움|결연|위트\","
    "\"mood\":\"밝음|차분|희망|회상\",\"seconds\":정수,\"bgm_mood\":\"calm|hopeful|reflective|playful\"}}. "
    "★각 line은 반드시 그 키의 나이대 이야기만 — '초년' 값엔 아기 시절만, '노년' 값엔 노년만(다른 나이 언급 금지). "
    "★★시제 정확(매우 중요): 사용자에게 주어진 [현재 단계]보다 앞선 단계는 '이미 산 과거'이니 과거형(~했어, ~였지)으로, "
    "[현재 단계]는 '지금'이니 현재형(~하고 있어, ~해)으로, [현재 단계]보다 뒤 단계는 '아직 안 온 미래'이니 미래형(~할 거야, ~일 것 같아)으로 쓴다. "
    "이미 지난 일을 미래로 말하거나(예: 60대인데 '청년이 되면'), 아직 안 온 일을 과거로 말하지 마라. "
    "emotion은 그 장면의 핵심 감정을, mood는 화면 색감을 가리킨다. "
    "★★★이 영상의 핵심·경쟁력은 '실제 상담답변을 충실히 영상화'하는 것이다. [상담답변]에 적힌 구체 분석(성향·운의 강약·특징), "
    "시기(지금/올해/앞으로 등), 조언을 1인칭으로 그대로 전달하라. 누구에게나 해당하는 일반론('꿈을 향해 달렸어','도전했어','평온해' "
    "같은 막연한 말)은 금지 — 반드시 그 답변의 구체 내용으로 채운다. 답변 포인트를 생애 단계에 자연스럽게 배치: "
    "타고난 성향·기질→초년/유년, 답변의 현재~가까운 운과 조언→청년/장년, 앞날의 흐름·정리→노년. "
    "예: 재물운 답변이면 '나는 재물 욕심과 기회가 많은 사주라, 지금은 새 투자에 운이 트이는 시기야. 다만 욕심이 과하면 분산되니 신중히…'처럼 "
    "답변의 실제 분석을 옮긴다. 각 line은 2~3문장으로 내용 충실히 — ★5단계 모두 비슷한 분량으로(현재 단계만 길게, "
    "나머지를 한 줄로 때우지 말 것). 글자수 합 {lo}~{hi}자, seconds 합 약 {sec}. "
    "★사주 전문용어(식신·정관·겁재 등 십성, 지지·천간·월지·일간·대운 등)는 그대로 쓰지 말고 그 '의미'만 일상어로 풀어 표현. "
    "★괄호·태그·메모·이모지를 절대 넣지 말 것(예: '(육신: ..)','(★십성: ..)','(emotion: ..)' 전부 금지) — 깔끔한 구어체 문장만. "
    "★'여러분'·'안녕하세요' 같은 청중 호칭/인사 금지 — 오직 나 자신의 인생 독백(1인칭)으로. "
    "문어체·번역투·작위적 표현 금지, 친구에게 담담히 들려주듯 자연스러운 구어체. "
    "원답변 근거 안에서만, 없는 사실은 지어내지 말 것. '나는~'으로 시작."
)


_STAGE_ORDER = ["초년", "유년", "청년", "장년", "노년"]

# 60갑자(천간+지지). 일상어와 겹치는 것은 SKIP(안 지움). 단독 토큰만 안전 제거.
_GJ_STEM, _GJ_BR = "갑을병정무기경신임계", "자축인묘진사오미신유술해"
_GANJA60 = {_GJ_STEM[k % 10] + _GJ_BR[k % 12] for k in range(60)}
_GJ_SKIP = {"기사", "임신", "신사", "병자", "신축", "무술", "경신",
            "임자", "정유", "무신", "경인", "갑인", "을사", "병신", "신묘", "임술"}
_GANJA_RE = re.compile(
    r"(?<![가-힣])['\"‘’“”]?(?:" +
    "|".join(sorted(_GANJA60 - _GJ_SKIP, key=len, reverse=True)) +
    r")['\"‘’“”]?(?:년|생)?(?:은|는|이|가|을|를|의|에|와|과|로)?"
    r"(?=$|[\s,.!?)])"   # 간지+조사까지 소비, 뒤는 경계(orphan 조사 방지)
)
_AGE_KW = [
    (("아기", "갓난", "태어", "유아", "돌 무렵", "포대기", "초년"), "초년"),
    (("어릴", "어렸", "유년", "어린 시절", "학교", "초등", "소년", "소녀", "십 대", "십대", "꼬마", "학창"), "유년"),
    (("스무", "스물", "이십", "대학", "청년", "서른", "삼십", "젊", "첫 직장", "사회 초년", "이십 대", "삼십 대", "취업"), "청년"),
    (("마흔", "사십", "쉰", "오십", "중년", "장년", "사십 대", "오십 대"), "장년"),
    (("예순", "육십", "일흔", "칠십", "여든", "팔십", "노년", "은퇴", "황혼", "말년", "늘그막", "노후", "백발"), "노년"),
]


def infer_stage(line: str) -> str | None:
    """대사 속 '나이 단서'로 생애단계 추론(가장 확실한 근거). 없으면 None."""
    t = line or ""
    for kws, st in _AGE_KW:
        if any(k in t for k in kws):
            return st
    import re as _re
    m = _re.search(r"(\d{1,3})\s*세", t)
    if m:
        a = int(m.group(1))
        return "초년" if a < 8 else "유년" if a < 20 else "청년" if a < 40 else "장년" if a < 60 else "노년"
    return None


# 육신(십성) → 내레이션에 등장할 만한 동의어들(주입 매칭용). 명식에 있는 육신만 사용.
# 동의어는 '단어 내부 부분일치'를 피하려고 충분히 구별되는 2자+만(끼·경쟁·책임 등 짧은 일반어 배제).
_YUKSIN_SYN = {
    "식신": ["창의력", "창의성", "표현하는", "즐거움", "여유로움"],
    "상관": ["표현력", "재치", "톡톡 튀는"],
    "정관": ["책임감", "규율", "명예", "원칙"],
    "편관": ["추진력", "결단력", "도전 정신", "카리스마"],
    "정인": ["배움", "학문", "지혜", "탐구심"],
    "편인": ["직관", "아이디어", "독창성"],
    "정재": ["재물복", "안정적인 재물", "알뜰함"],
    "편재": ["재물운", "사업 수완", "통 큰"],
    "비견": ["동료복", "독립심", "뚝심"],
    "겁재": ["경쟁심", "승부욕", "패기"],
}


def _parse_keyed(raw: str) -> list[dict]:
    """단계 키 JSON 객체({"초년":{...},...}) → [초년→노년] 순서 scenes. 단계=키라서 100% 정확.
    JSON 우선, 실패 시 키별 정규식 폴백(절단/펜스 내성)."""
    data = None
    s = raw.find("{")
    if s >= 0:
        try:
            data = json.loads(raw[s:raw.rfind("}") + 1])
        except Exception:
            data = None
    scenes: list[dict] = []
    for st in _STAGE_ORDER:
        v = data.get(st) if isinstance(data, dict) else None
        if isinstance(v, dict) and str(v.get("line", "")).strip():
            scenes.append({"stage": st, "line": v.get("line", ""), "emotion": v.get("emotion", ""),
                           "mood": v.get("mood", ""), "seconds": v.get("seconds", 0), "bgm_mood": v.get("bgm_mood", "calm")})
        elif isinstance(v, str) and v.strip():
            scenes.append({"stage": st, "line": v, "emotion": "", "mood": "", "seconds": 0, "bgm_mood": "calm"})
    if scenes:
        return scenes
    # 폴백: 키별 정규식
    for st in _STAGE_ORDER:
        m = re.search(rf'"{st}"\s*:\s*\{{[^{{}}]*?"line"\s*:\s*"([^"]+)"', raw, re.S) or \
            re.search(rf'"{st}"\s*:\s*"([^"]+)"', raw, re.S)
        if m:
            scenes.append({"stage": st, "line": m.group(1), "emotion": "", "mood": "", "seconds": 0, "bgm_mood": "calm"})
    return scenes


def _parse_scenes(raw: str) -> list[dict]:
    """```json 펜스/절단에 내성. 균형 잡힌 {...} scene 객체만 추출해 살린다."""
    s = raw.find("[")
    body = raw[s + 1:] if s >= 0 else raw
    objs: list[dict] = []
    depth = 0
    start: int | None = None
    for i, ch in enumerate(body):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    objs.append(json.loads(body[start:i + 1]))
                except json.JSONDecodeError:
                    pass
                start = None
    return objs


def _ollama_chat(system: str, user: str, num_predict: int = 768, temperature: float = 0.5) -> str:
    s = get_settings()
    body = json.dumps({
        "model": s.ollama_model,
        "stream": False,
        "keep_alive": -1,  # 정수(문자열 "-1"은 400)
        "options": {"temperature": temperature, "num_ctx": 8192, "num_predict": num_predict},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{s.ollama_url}/api/chat", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=float(getattr(s, "ollama_timeout_sec", 180.0))) as r:
        return json.loads(r.read().decode("utf-8"))["message"]["content"]


def generate_scenario(src: VideoSource, seconds: int = 60) -> dict:
    """VideoSource → {character:{zodiac}, scenes:[...]} (검증된 JSON 계약)."""
    chars = max(420, int(seconds * 5.5))   # 구체적 내용 충실 위해 분량↑(품질>시간)
    lo, hi = chars - 70, chars + 90
    system = _SYS.format(sec=seconds, lo=lo, hi=hi)
    _yuksin = ", ".join(getattr(src, "ten_gods", []) or []) or "(미상)"
    _cur = getattr(src, "cur_stage", "") or "청년"
    _age = getattr(src, "age", None)
    _ord = ["초년", "유년", "청년", "장년", "노년"]
    _ci = _ord.index(_cur) if _cur in _ord else 2
    _past = _ord[:_ci] or ["(없음)"]
    _fut = _ord[_ci + 1:] or ["(없음)"]
    user = (f"[현재 단계]{_cur}(약 {_age}세) — 이 단계가 '지금'. "
            f"과거(이미 산 시기, 과거형): {_past} / 미래(아직 안 온 시기, 미래형): {_fut}\n"
            f"[띠]{src.zodiac}띠\n[명식 육신(이것만 사용, 다른 육신 금지)]{_yuksin}\n"
            f"[명식요약]\n{src.summary or ''}\n\n[상담답변]\n{src.narration_src}")
    raw = _ollama_chat(system, user)
    scenes = _parse_keyed(raw)
    _att = 0
    while len({s.get("stage") for s in scenes} & set(_STAGE_ORDER)) < 5 and _att < 2:  # 5단계 다 모일 때까지 재시도
        raw = _ollama_chat(system, user, temperature=0.3 + 0.1 * _att)
        new = _parse_keyed(raw)
        if len(new) > len(scenes):
            scenes = new
        _att += 1
    # 그래도 누락된 단계는 폴백 라인으로 채워 '5단계(캐릭터) 누락'을 절대 방지
    _FILL = {"초년": "어린 시절, 세상이 마냥 신기하고 따뜻하게 느껴졌어.",
             "유년": "학창 시절엔 친구들과 어울리며 꿈을 키워 갔지.",
             "청년": "청년이 되어 세상에 첫발을 내디디며 부딪혀 봤어.",
             "장년": "중년에 접어들며 삶의 무게와 보람을 함께 느꼈어.",
             "노년": "이제 노년이 되어 지나온 길을 돌아보며 평온을 느껴."}
    _have = {s.get("stage") for s in scenes}
    for _st in _STAGE_ORDER:
        if _st not in _have:
            scenes.append({"stage": _st, "line": _FILL[_st], "emotion": "", "mood": "", "seconds": 0, "bgm_mood": "calm"})

    # 사주 전문용어 결정적 제거(LLM이 프롬프트를 무시하므로 출력단에서 보장)
    _JARGON = {
        "식신": "창의력", "상관": "표현력", "정관": "책임감", "편관": "추진력",
        "정인": "배움", "편인": "직관", "정재": "재물복", "편재": "재물복",
        "비견": "동료복", "겁재": "경쟁심",
    }

    def _batchim(ch: str) -> bool:
        return "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 != 0

    _PAR_B = {"와": "과", "과": "과", "이": "이", "가": "이", "은": "은", "는": "은", "을": "을", "를": "을"}
    _PAR_N = {"와": "와", "과": "와", "이": "가", "가": "가", "은": "는", "는": "는", "을": "를", "를": "를"}

    _ARTIFACT = {"스무스": "스무 살", "삼십대": "삼십 대", "사십대": "사십 대", "오십대": "오십 대"}

    def _dejargon(t: str) -> str:
        for _a, _b in _ARTIFACT.items():   # exaone 반복 비문 결정적 교정
            t = t.replace(_a, _b)
        # LLM이 흘린 모든 괄호 주석/메타/태그 완전 제거(육신 괄호는 이후 결정적 주입단계서 다시 붙임)
        t = re.sub(r"\s*[\(（][^)）]*[\)）]", "", t)   # 괄호쌍(내용 포함) 제거
        t = re.sub(r"[\(（\)）★]", "", t)             # 짝 안 맞는 잔여 괄호·★ 제거
        # LLM이 붙인 '십성 식신'·', 육신 경쟁심' 같은 꼬리표 제거(앞 구두점·조사 포함)
        t = re.sub(r"\s*[,·]?\s*(?:십성|육신)\s*[가-힣]{1,5}", "", t)
        # 간지(병오년·병오의 등) → '올해/내년'만 남기고 제거(년 없이 의/에 붙어도).
        # ※bare 간지 일반 제거는 '임신/신사/기사/갑자기' 등 일상어를 깨므로 금지 — 올해/내년 앵커로만 안전 제거.
        t = re.sub(r"(올해|내년|작년|이번\s*해)\s*[갑을병정무기경신임계][자축인묘진사오미신유술해](?:년|의|에)?", r"\1", t)
        # 간지/대운/세운/일주(환각 위험 + 잡스러움) 제거 — 결정적 검증된 육신만 남김
        t = re.sub(r"[갑을병정무기경신임계][자축인묘진사오미신유술해]\s*(?:일주|대운|세운|년|월)\s*"
                   r"(?:이라서|이라|이고|라서|때문에|덕분에|에서|에|의|이|가|은|는|도|로|으로)?\s*", "", t)
        # 간지 없이 단독으로 나온 구조 용어도 일상어로/제거(대운·세운·일주 등)
        t = t.replace("대운", "운의 흐름").replace("세운", "운세")
        t = re.sub(r"(일주|월주|년주|시주)\s*", "", t)
        # 단독 토큰 간지(60갑자) 안전 제거 — 한글경계 가드로 일상어(임신·갑자기·무인도 등) 보호
        t = _GANJA_RE.sub("", t)
        # 오행 잡어 제거('토기운','금기운','무토' 등) — 일상어만
        t = re.sub(r"[갑을병정무기경신임계]?(?:목|화|토|금|수)\s?기운[가-힣]*\s*", "", t)
        t = re.sub(r"[갑을병정무기경신임계](?:목|화|토|금|수)(?=\s|덕분|때문|의|은|는|이|가|$)\s*", "", t)
        # 위치어 삭제(단, '시간'=time·'월간'=monthly 등 흔한 일상어는 제외해 오삭제 방지)
        t = re.sub(r"(월지|일간|일지|시지|년간|년지)\s*", "", t)
        # (육신=십성은 이제 살린다 — 사용자 요청. 치환/삭제하지 않음)
        t = re.sub(r"(\S+?)의 \1", r"\1", t)        # 'X의 X' 중복 → X
        return re.sub(r"\s{2,}", " ", t).strip()

    def _trim_line(t: str, max_sent: int = 3, max_chars: int = 135) -> str:
        # 1~2문장·최대 글자수로 제한(과도한 길이 → 영상 과길이/과슬로우 방지)
        parts = re.split(r"(?<=[.!?。])\s+", t.strip())
        out = " ".join(parts[:max_sent]).strip()
        return (out[:max_chars].rstrip() + "…") if len(out) > max_chars else out

    def _polish(lines: list[str]) -> list[str]:
        sysp = (
            "다음 1인칭 영상 내레이션 문장들을 자연스럽게 다듬어 순수 JSON 문자열 배열로만 반환(설명·코드펜스 금지). "
            "규칙: 문법 오류·어색한 조사·중복·★끊긴 조각이나 꼬리 단어(예: '생겼지과 적응력','늘렸지, 십성 식신')를 "
            "완결되고 매끄러운 문장으로 고친다. 비문·중간에 잘린 표현은 뜻이 통하게 자연스럽게 재작성. "
            "간지(병오·갑자 등 60갑자)는 일상어로 풀되, ★육신(식신·정관·겁재 등)과 괄호 설명(예: 식신(창의력))은 그대로 유지. "
            "내용(상담답변 분석)·감정·길이는 유지, 문장 개수 동일, 친구에게 말하듯 1인칭 구어체."
        )
        raw2 = _ollama_chat(sysp, json.dumps(lines, ensure_ascii=False), num_predict=500, temperature=0.3)
        m2 = re.search(r"\[.*\]", raw2, re.S)
        arr = json.loads(m2.group(0)) if m2 else None
        if isinstance(arr, list) and len(arr) == len(lines):
            return [str(x) for x in arr]
        return lines

    cleaned = []
    for s in scenes:
        line = _dejargon(_trim_line(_strip_md(str(s.get("line", "")).strip())))
        if not line:
            continue
        cleaned.append({
            "stage": s.get("stage", ""),
            "line": line,
            "emotion": s.get("emotion", "") or s.get("mood", "평온"),  # 감정선(더빙 이입)
            "mood": s.get("mood", "차분"),                              # 화면 색감
            "seconds": int(s.get("seconds", 0) or 0),
            "bgm_mood": s.get("bgm_mood", "calm"),
        })
    if not cleaned:
        raise ValueError("scenario produced no scenes")
    # 자연스러움 보정(문법·간지·중복) — best effort, 실패 시 원문 유지
    try:
        polished = _polish([c["line"] for c in cleaned])
        for i, c in enumerate(cleaned):
            c["line"] = _dejargon(_trim_line(_strip_md(polished[i])))
    except Exception:
        pass
    # ★육신(십성) 주입 — 명식·답변에 '실제 있는' 육신만, 뜻 단어에 '육신(뜻)'으로(근거 기반·1회씩).
    #  (LLM이 육신명을 빠뜨리고 뜻만 쓰므로 출력단에서 결정적으로 보장. 차트에 없는 육신은 넣지 않음.)
    _chart_yuksin = list(getattr(src, "ten_gods", []) or [])
    _chart_set = set(_chart_yuksin)
    for c in cleaned:
        line = c["line"]
        # 1) 차트에 없는 육신을 LLM이 썼다면 → 의미어로 대체(환각 표기 제거)
        for _y, _mean in _JARGON.items():
            if _y not in _chart_set:
                line = line.replace(_y, _mean)
        # 2) 차트에 있는 육신: 동의어를 찾아 '육신(동의어)'로 주입(근거 기반, 육신당 1회)
        for _y in _chart_yuksin:
            if f"{_y}(" in line:
                continue
            for _syn in _YUKSIN_SYN.get(_y, []):
                _m = re.search(r"(?<![가-힣])" + re.escape(_syn), line)   # 단어경계(앞 한글 아님) → 부분일치 방지
                if _m:
                    line = line[:_m.start()] + f"{_y}({_syn})" + line[_m.end():]
                    break
        # 끝에 매달린 육신/단어 조각 제거('…깨달았어., 재성' → '…깨달았어.')
        line = re.sub(r"([.!?])\s*[,·]\s*[가-힣]{1,6}\.?\s*$", r"\1", line)
        c["line"] = re.sub(r"\s{2,}", " ", line).strip()
    # 3) 본문에 못 녹인 차트 육신은 초년('타고난 기운')에 명시 — 누락 방지(정확·결정적)
    _present = {_y for c in cleaned for _y in _chart_yuksin if f"{_y}(" in c["line"]}
    _missing = [(_y, _JARGON.get(_y, "")) for _y in _chart_yuksin if _y not in _present and _JARGON.get(_y)]
    if _missing and cleaned:
        _clause = "타고나길 " + ", ".join(f"{_y}({_m})" for _y, _m in _missing) + " 기운을 품고 났어."
        # 초년이 없을 수도 있으니 초년 우선, 없으면 첫 장면에
        _c0 = next((c for c in cleaned if c.get("stage") == "초년"), cleaned[0])
        _c0["line"] = (_c0["line"].rstrip() + " " + _clause).strip()
    # 시간순 정렬(초년→노년) — fill 추가/순서 뒤섞임 보정
    _rk = {s: i for i, s in enumerate(_STAGE_ORDER)}
    cleaned.sort(key=lambda c: _rk.get(c.get("stage", ""), 9))
    # seconds 정규화(합계를 목표 길이에 맞춤)
    tot = sum(c["seconds"] for c in cleaned) or len(cleaned)
    for c in cleaned:
        c["seconds"] = max(3, round(c["seconds"] / tot * seconds))
    return {"character": {"zodiac": src.zodiac, "gender": src.gender}, "scenes": cleaned}
