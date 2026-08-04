"""택일(擇日) 엔진 — 기간 내 날짜별 길흉 점수 → 길일 추천.

요소(관법 중립):
  ① 황도흑도(黃道黑道) — 월지·일지 기준 12신 중 황도6(길)/흑도6(흉)
  ② 본인 사주 회피     — 그날 일지 vs 본인 일지의 충/원진/형 (기존 합충테이블 재사용)
  ③ 손없는날           — 음력 끝자리 9·0 (이사·개업 민속)
용도(7종+)는 가중치(관법)로 반영. 정밀 생기복덕(팔택유년)은 후속 정제.
"""
from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, Field

from .constants import (
    BRANCH_CONFLICTS,
    BRANCH_PUNISH,
    BRANCH_SELF_PUNISH,
    BRANCH_WONJIN,
    EARTHLY_BRANCHES,
    HIDDEN_STEMS,
    STEM_COMBINATIONS,
    STEM_TO_WUXING,
    WUXING_OVERCOMES,
    branch_korean,
    compute_ten_god,
    stem_korean,
    Locale,
    branch_reading,
    stem_reading,
)
from .engine import build_chart
from .gwanbeop import STAR_GROUP
from .relations import pair_branch_relations_ext
from .types import BirthInput, SajuChart

# 황도흑도 12신 (청룡부터). (이름, 황/흑)
_SHIN = [
    ("청룡", "황"), ("명당", "황"), ("천형", "흑"), ("주작", "흑"),
    ("금궤", "황"), ("천덕", "황"), ("백호", "흑"), ("옥당", "황"),
    ("천뢰", "흑"), ("현무", "흑"), ("사명", "황"), ("구진", "흑"),
]
# 12신 이름 한월음(vi) — _SHIN 의 ko 이름 → Hán-Việt.
_SHIN_VI = {
    "청룡": "Thanh Long", "명당": "Minh Đường", "천형": "Thiên Hình", "주작": "Chu Tước",
    "금궤": "Kim Quỹ", "천덕": "Thiên Đức", "백호": "Bạch Hổ", "옥당": "Ngọc Đường",
    "천뢰": "Thiên Lao", "현무": "Huyền Vũ", "사명": "Tư Mệnh", "구진": "Câu Trần",
    "미상": "Không rõ",
}
# 월지 → 청룡(시작) 일지
_CHEONGYONG_START = {
    "寅": "子", "申": "子", "卯": "寅", "酉": "寅", "辰": "辰", "戌": "辰",
    "巳": "午", "亥": "午", "午": "申", "子": "申", "未": "戌", "丑": "戌",
}

# 건제십이신(建除十二神/십이직성) — 중단(中段) 택일의 핵심.
# 월지와 같은 일지인 날이 建, 이후 일지 순서대로 除滿平定執破危成收開閉 배당.
# 길흉(고전 구결): "建滿平收黑, 除危定執黃, 成開可用, 閉破不可當"
#   → 길: 除·危·定·執·成·開 / 흉: 建·滿·平·收·閉·破 (破·閉 大凶, 成·開·定 大吉)
# ※ 절입일에 신이 겹치는(重) 정밀 보정은 미반영(월지-일지 차로 근사).
_GEONJE_ORDER = ["建", "除", "滿", "平", "定", "執", "破", "危", "成", "收", "開", "閉"]
_GEONJE_KO = {
    "建": "건", "除": "제", "滿": "만", "平": "평", "定": "정", "執": "집",
    "破": "파", "危": "위", "成": "성", "收": "수", "開": "개", "閉": "폐",
}
# 건제12신 한월음(vi) — Hán-Việt.
_GEONJE_VI = {
    "建": "Kiến", "除": "Trừ", "滿": "Mãn", "平": "Bình", "定": "Định", "執": "Chấp",
    "破": "Phá", "危": "Nguy", "成": "Thành", "收": "Thu", "開": "Khai", "閉": "Bế",
}
# (점수0~100, 한 줄 의미)
_GEONJE_INFO: dict[str, tuple[int, str]] = {
    "成": (92, "이룸 — 혼인·개업·입학 등 만사 대길"),
    "開": (90, "열림 — 개업·입주·개통에 대길(장례는 피함)"),
    "定": (82, "안정 — 결혼·계약·입주에 길(소송·이동은 흉)"),
    "除": (78, "묵은 것 제거 — 치료·청소·제사에 길"),
    "危": (70, "황도 길신 — 대체로 길(등산·승선은 주의)"),
    "執": (68, "잡음 — 결혼·건축·계약에 길(이사·재물은 흉)"),
    "平": (52, "평탄 — 무난(도로·담장에 길)"),
    "收": (48, "거둠 — 수금·매입에 길(장례·개업은 흉)"),
    "滿": (45, "가득참 — 창고·연못엔 길이나 복약·매장은 흉"),
    "建": (42, "세움 — 우두머리 기운이나 동토·매장은 흉"),
    "閉": (28, "닫음 — 매장·둑막이 외 대체로 흉"),
    "破": (20, "깨짐 — 만사 대흉(파옥·치료만 길)"),
}
# 건제12신 한 줄 의미(vi).
_GEONJE_NOTE_VI: dict[str, str] = {
    "成": "Thành tựu — hôn nhân·khai trương·nhập học đều đại cát",
    "開": "Khai mở — đại cát cho khai trương·nhập trạch·thông xe (tránh tang lễ)",
    "定": "Ổn định — tốt cho cưới hỏi·ký kết·nhập trạch (kiện tụng·di chuyển thì xấu)",
    "除": "Trừ bỏ cũ kỹ — tốt cho chữa bệnh·dọn dẹp·cúng tế",
    "危": "Cát thần hoàng đạo — phần lớn tốt (leo núi·lên thuyền cần lưu ý)",
    "執": "Nắm giữ — tốt cho cưới hỏi·xây dựng·ký kết (chuyển nhà·tiền tài thì xấu)",
    "平": "Bằng phẳng — ổn (tốt cho đường sá·tường rào)",
    "收": "Thu hoạch — tốt cho thu tiền·mua vào (tang lễ·khai trương thì xấu)",
    "滿": "Đầy đủ — tốt cho kho·ao hồ nhưng uống thuốc·an táng thì xấu",
    "建": "Dựng lập — khí đứng đầu nhưng động thổ·an táng thì xấu",
    "閉": "Đóng lại — phần lớn xấu, trừ an táng·đắp đê",
    "破": "Đổ vỡ — vạn sự đại hung (chỉ tốt cho phá dỡ·chữa bệnh)",
}

# ── 이십팔수(二十八宿) ──────────────────────────────────────────
# 매일 1수씩 +1 순환(28일). 칠요(요일)와 위상이 고정 → 자가검증 가능.
# 표준 순서(角부터). 앵커: 2026-06-09 = 室(index 12).
#   출처: 일본 코요미 2곳(koyominote·rekichu) 6/8危·6/9室·6/10壁·6/11奎 일치 +
#         한국 위키백과 '이십팔수' 칠요표와 요일·순서 교차검증.
#   ※ 잔여: 한·일 위상 동일성(7/14/21일 어긋남)은 한국 만세력 1회 스팟확인 권장.
_SU28 = "角亢氐房心尾箕斗牛女虛危室壁奎婁胃昴畢觜參井鬼柳星張翼軫"
_SU28_KO = "각항저방심미기두우여허위실벽규루위묘필자삼정귀류성장익진"
# 28수 한월음(vi) — _SU28 위치 병렬(角부터).
_SU28_VI = (
    "Giác", "Cang", "Đê", "Phòng", "Tâm", "Vĩ", "Cơ", "Đẩu", "Ngưu", "Nữ",
    "Hư", "Nguy", "Thất", "Bích", "Khuê", "Lâu", "Vị", "Mão", "Tất", "Chủy",
    "Sâm", "Tỉnh", "Quỷ", "Liễu", "Tinh", "Trương", "Dực", "Chẩn",
)
_SU28_ANCHOR_ORD = date(2026, 6, 9).toordinal()
_SU28_ANCHOR_IDX = 12  # 室
# 길흉 한 줄(출처: 歳事暦 saijigoyomi). good=True 길수 / False 흉 비중 큰 수.
_SU28_NOTE: dict[str, str] = {
    "角": "길 · 혼인·건축·개점(장례 흉)", "亢": "길 · 혼인·파종(건축·이사·여행 흉)",
    "氐": "길 · 혼인·농경·개축(물가 흉)", "房": "길 · 혼인·여행·상량(소송 흉)",
    "心": "혼인·장례 흉 · 제사·이사·여행엔 길", "尾": "길 · 혼인·개점·여행(재단·장례 흉)",
    "箕": "혼인·장례 흉 · 양조·매입엔 길", "斗": "길 · 혼인·부동산·조작",
    "牛": "大吉 · 만사에 길(길상숙)", "女": "공무·학예엔 길(혼인·장례·신축 흉)",
    "虛": "건축·혼인 흉, 상담 大凶 · 입학엔 길", "危": "혼인·이사 흉, 등산·고소 大凶",
    "室": "길 · 제사·혼인·조작(장례·원행 흉)", "壁": "길 · 신축·혼인(남향 진출 흉)",
    "奎": "길 · 혼인·상량·벌목(개점·소송 흉)", "婁": "大吉 · 혼인·여행·재단(소송 흉)",
    "胃": "취직·혼인엔 길(장례 大凶)", "昴": "길 · 기원·축하·개점(재단 흉)",
    "畢": "길 · 제사·혼인·신축·부동산(투자·구설 흉)", "觜": "혼인 흉일 · 입학·건축엔 길",
    "參": "길 · 상거래·개업·혼인·취직(장례·이사 흉)", "井": "길 · 제사·혼인·건축·부동산(장례 흉)",
    "鬼": "大吉 · 공적 식전 최고(혼인만 흉)", "柳": "혼인 흉, 장송 大凶 · 강맹사엔 길",
    "星": "혼인·축하 흉 · 운전·요양·파종엔 길", "張": "大吉 · 혼인·개업·파종·양잠(재단 흉)",
    "翼": "혼인 大凶(이혼) · 경작·식목엔 길", "軫": "길 · 혼인·상량·부동산(재단·여행 흉)",
}
# 28수 길흉 한 줄(vi).
_SU28_NOTE_VI: dict[str, str] = {
    "角": "Cát · cưới hỏi·xây dựng·khai trương (tang lễ xấu)",
    "亢": "Cát · cưới hỏi·gieo trồng (xây dựng·chuyển nhà·du lịch xấu)",
    "氐": "Cát · cưới hỏi·nông vụ·sửa nhà (gần nước xấu)",
    "房": "Cát · cưới hỏi·du lịch·thượng lương (kiện tụng xấu)",
    "心": "Cưới hỏi·tang lễ xấu · tốt cho cúng tế·chuyển nhà·du lịch",
    "尾": "Cát · cưới hỏi·khai trương·du lịch (cắt may·tang lễ xấu)",
    "箕": "Cưới hỏi·tang lễ xấu · tốt cho nấu ủ·mua vào",
    "斗": "Cát · cưới hỏi·bất động sản·tạo tác",
    "牛": "Đại cát · tốt cho vạn sự (tú cát tường)",
    "女": "Tốt cho việc công·học nghệ (cưới hỏi·tang lễ·xây mới xấu)",
    "虛": "Xây dựng·cưới hỏi xấu, thương lượng đại hung · tốt cho nhập học",
    "危": "Cưới hỏi·chuyển nhà xấu, leo núi·lên cao đại hung",
    "室": "Cát · cúng tế·cưới hỏi·tạo tác (tang lễ·đi xa xấu)",
    "壁": "Cát · xây mới·cưới hỏi (tiến về hướng Nam xấu)",
    "奎": "Cát · cưới hỏi·thượng lương·đốn gỗ (khai trương·kiện tụng xấu)",
    "婁": "Đại cát · cưới hỏi·du lịch·cắt may (kiện tụng xấu)",
    "胃": "Tốt cho xin việc·cưới hỏi (tang lễ đại hung)",
    "昴": "Cát · cầu nguyện·chúc mừng·khai trương (cắt may xấu)",
    "畢": "Cát · cúng tế·cưới hỏi·xây mới·bất động sản (đầu tư·thị phi xấu)",
    "觜": "Ngày xấu cho cưới hỏi · tốt cho nhập học·xây dựng",
    "參": "Cát · buôn bán·khai trương·cưới hỏi·xin việc (tang lễ·chuyển nhà xấu)",
    "井": "Cát · cúng tế·cưới hỏi·xây dựng·bất động sản (tang lễ xấu)",
    "鬼": "Đại cát · tốt nhất cho nghi lễ công (chỉ cưới hỏi xấu)",
    "柳": "Cưới hỏi xấu, tang lễ đại hung · tốt cho việc mạnh mẽ cứng rắn",
    "星": "Cưới hỏi·chúc mừng xấu · tốt cho lái xe·dưỡng bệnh·gieo trồng",
    "張": "Đại cát · cưới hỏi·khai trương·gieo trồng·nuôi tằm (cắt may xấu)",
    "翼": "Cưới hỏi đại hung (ly hôn) · tốt cho canh tác·trồng cây",
    "軫": "Cát · cưới hỏi·thượng lương·bất động sản (cắt may·du lịch xấu)",
}


# 28수 일반 길흉(0~100) — 歳事暦. 大吉宿(牛婁鬼張)>일반 吉>주의(흉 요소 큰 수).
_SU28_SCORE: dict[str, int] = {
    "牛": 90, "婁": 90, "鬼": 90, "張": 88,                       # 大吉宿
    "室": 74, "角": 72, "房": 72, "尾": 72, "斗": 72, "壁": 72,    # 吉
    "昴": 72, "畢": 72, "參": 72, "井": 72,
    "亢": 70, "氐": 70, "奎": 70, "軫": 70, "女": 68, "胃": 68,
    "星": 60, "心": 60, "箕": 58, "虛": 58, "危": 58, "柳": 58,    # 주의(흉 요소 큼)
    "觜": 56, "翼": 56,
}
# 혼인·출산엔 '婚礼凶'인 수를 강하게 감점 (歳事暦): 心箕虛危觜鬼柳星翼
_SU28_WEDDING_BAD = set("心箕虛危觜鬼柳星翼")


def _su28_score(su_ch: str, purpose: str) -> int:
    s = _SU28_SCORE.get(su_ch, 68)
    if purpose in ("wedding", "birth") and su_ch in _SU28_WEDDING_BAD:
        s = min(s, 35)   # 혼인·출산엔 婚礼凶 수 강한 감점
    return s


def _su28_index(d: date) -> int:
    """그 날의 28수 인덱스(0=角..27=軫). 칠요(요일) 자가검증 포함."""
    idx = (_SU28_ANCHOR_IDX + (d.toordinal() - _SU28_ANCHOR_ORD)) % 28
    # 칠요 잠금(위키): (i+3)%7 == 파이썬 요일(월0..일6). 어긋나면 앵커/계산 오류.
    assert (idx + 3) % 7 == d.weekday(), f"28수 칠요 불일치: {d.isoformat()} idx={idx}"
    return idx


def _su28(d: date, locale: Locale = "ko") -> tuple[str, str, str]:
    """(한자, 독음, 길흉 한 줄). 예: ('室','실','길 · 제사·혼인·조작…') / ('室','Thất','Cát · …')."""
    i = _su28_index(d)
    ch = _SU28[i]
    if locale == "vi":
        return ch, _SU28_VI[i], _SU28_NOTE_VI.get(ch, "")
    return ch, _SU28_KO[i], _SU28_NOTE.get(ch, "")


# 용도(8종+). '출산'은 혼인 다음(자식과의 관계)으로 배치.
PURPOSES = {
    "wedding": "혼인", "birth": "출산", "moving": "이사", "opening": "개업", "contract": "계약",
    "ceremony": "고사·제사", "surgery": "수술", "travel": "여행", "general": "일반",
}
# 용도 라벨(purpose_label) 로케일 표. ko 는 PURPOSES 와 동일.
_PURPOSE_LABEL: dict[str, dict[str, str]] = {
    "ko": PURPOSES,
    "vi": {
        "wedding": "Cưới hỏi", "birth": "Sinh con", "moving": "Chuyển nhà", "opening": "Khai trương",
        "contract": "Ký kết", "ceremony": "Cúng tế", "surgery": "Phẫu thuật", "travel": "Du lịch",
        "general": "Chung",
    },
}
# 종합 등급: stable key(best|good|normal|bad) + 로케일 라벨.
_GRADE_LABEL: dict[str, dict[str, str]] = {
    "ko": {"best": "대길일", "good": "길일", "normal": "보통", "bad": "흉일"},
    "vi": {"best": "Đại cát nhật", "good": "Cát nhật", "normal": "Bình thường", "bad": "Hung nhật"},
}
# 관법(P/H/B/M) 라벨 — PERSPECTIVES 키와 동기(P=뽀 본인사주 중시 신설).
_PERSP_LABEL: dict[str, dict[str, str]] = {
    "ko": {"P": "본인 사주 중시", "H": "황도·중단 중시", "B": "균형", "M": "민속(손없는날) 중시"},
    "vi": {"P": "Trọng mệnh chủ (lá số bản thân)", "H": "Trọng hoàng đạo·trung đoạn", "B": "Cân bằng",
           "M": "Trọng dân gian (ngày không sát chủ)"},
}
# 사주 회피/경고 배지 유형명(warnings). ko 는 항등, vi 만 치환.
_WARN_VI: dict[str, str] = {"일지충": "Xung địa chi ngày", "원진": "Oán sân", "형": "Hình"}


def _geonje_badge(ch: str, locale: Locale) -> str:
    """건제신 배지 문자열 '성(成)' / 'Thành(成)'."""
    return _GEONJE_VI[ch] if locale == "vi" else f"{_GEONJE_KO[ch]}({ch})"


def _fmt_hwangdo(shin_ko: str, hb: str, locale: Locale) -> str:
    """황도흑도 표시 '청룡(황도)' / 'Thanh Long (hoàng đạo)'."""
    if locale == "vi":
        hd = "hoàng đạo" if hb == "황" else "hắc đạo" if hb == "흑" else "?"
        return f"{_SHIN_VI.get(shin_ko, shin_ko)} ({hd})"
    return f"{shin_ko}({hb}도)"

# 용도별 다관법 가중치(합 100): 황도흑도/사주조화/손없는날/건제십이신/이십팔수/생기복덕
# ⑥ 뽀-정합 재조정(2026-07-30, 학파조사 wf_wqlmz9ssc 권고 P가중표, 델타검증 통과):
#   채택관법=뽀(A설, 택일을 원국 재/관/일지/월지로만 판단) → saju 최상위, 코퍼스 택일근거 0인
#   신살축(hwangdo/geonje/su28/saenggi)은 학파 존중용 최소 유지로 축소. ceremony·travel은 뽀 택일이
#   다루지 않는 영역이라 황도/신살축 상대비중 유지(학파 중립). 하드배제·大凶 배지는 가중과 무관하게 불변.
_PURPOSE_WEIGHTS = {
    "wedding": {"hwangdo": 12, "saju": 50, "sonless": 12, "geonje": 10, "su28": 8, "saenggi": 8},
    # 출산: 아이-부모 궁합을 가장 중시 → saju 비중 최상.
    "birth": {"hwangdo": 12, "saju": 58, "sonless": 8, "geonje": 8, "su28": 8, "saenggi": 6},
    # 이사·개업: 손없는날 실수요가 커 sonless 유지하되 saju를 최상위로.
    "moving": {"hwangdo": 12, "saju": 42, "sonless": 25, "geonje": 8, "su28": 7, "saenggi": 6},
    "opening": {"hwangdo": 12, "saju": 42, "sonless": 22, "geonje": 10, "su28": 8, "saenggi": 6},
    "contract": {"hwangdo": 14, "saju": 50, "sonless": 12, "geonje": 10, "su28": 8, "saenggi": 6},
    # 고사·제사·여행: 뽀 택일 문헌이 다루지 않는 영역 → 개인 재/관 근거 약해 황도/신살축 비중 유지(중립).
    "ceremony": {"hwangdo": 24, "saju": 34, "sonless": 10, "geonje": 14, "su28": 10, "saenggi": 8},
    "surgery": {"hwangdo": 14, "saju": 55, "sonless": 8, "geonje": 10, "su28": 7, "saenggi": 6},
    "travel": {"hwangdo": 24, "saju": 34, "sonless": 12, "geonje": 12, "su28": 10, "saenggi": 8},
    "general": {"hwangdo": 16, "saju": 40, "sonless": 16, "geonje": 12, "su28": 8, "saenggi": 8},
}
# 공통 제시용 다관법(용도 무관 비교용) — 택일은 정답이 없어 관점별 추천 1위를 함께 보여준다.
#   P=본인 사주 중시: 채택관법(A설) 정합 관점(saju 최상위). ⑥ 학파조사 권고로 신설.
#   ⚠️ 라벨은 손님 노출 문자열 — 내부 전문가 이름('뽀') 등 내부 표현 금지.
PERSPECTIVES = {
    "P": {"label": "본인 사주 중시", "weights": {"hwangdo": 12, "saju": 50, "sonless": 14, "geonje": 10, "su28": 7, "saenggi": 7}},
    "H": {"label": "황도·중단 중시", "weights": {"hwangdo": 30, "saju": 16, "sonless": 9, "geonje": 23, "su28": 13, "saenggi": 9}},
    "B": {"label": "균형", "weights": {"hwangdo": 22, "saju": 24, "sonless": 14, "geonje": 20, "su28": 12, "saenggi": 8}},
    "M": {"label": "민속(손없는날) 중시", "weights": {"hwangdo": 18, "saju": 18, "sonless": 30, "geonje": 15, "su28": 11, "saenggi": 8}},
}

# ── 택일 관법 옵션(학파선택 기본값) ────────────────────────────────
# 2026-07-30 학파별 조사(wf_wqlmz9ssc) 권고 1안 반영. 택일은 정답 없음 → 관법별 토글로 노출.
# 후속으로 settings_service(관리자 과금/한도 탭 패턴)에서 덮어쓸 수 있게 설계(지금은 결정적 기본값).
# ⚠️ 값 변경 시 결과 랭킹이 바뀌므로 관법 결정(승인) 없이 임의 변경 금지.
TAEKIL_OPTIONS: dict[str, object] = {
    # ③b 결혼 비겁일: 현 단일명식 API로는 A설 배제트리거(남·여 동시 비겁)를 원리상 판정 불가하고,
    #    문헌은 '한쪽이면 대체일 없을 때 허용'이라 배제 대신 어드바이저리(소폭 감점·비배제)가 기본.
    "wedding_bigyeop_mode": "advisory",   # advisory(기본·비배제) | penalize(구 -30 배제형) | off
    # ② 이사 인수(印) 보호: 코퍼스 근거 0(통설만) → 기본 OFF. 켜도 財는 hard 유지, 印은 soft.
    "moving_protect_insu": False,
    # ① 십악대패일(택일일 일진 기준, C설): 택일 전용 산출표 코퍼스 부재(통설만) → 라벨만 기본.
    "sibak_taepae_mode": "label",         # off | label(기본·감점0·주의배지) | penalize(소폭 감점)
    # ④ 다층운 월운 층: 후보일 절기월 간지가 원국(월간·월지·일지·재)을 깨면 그 달 감점.
    "month_luck_mode": "soft",            # off | soft(기본·감점) | strict(월지 깨진 달 하드배제)
    # ⑤ 天德·月德귀인 소폭 길신 가점(결혼·이사 한정, 그날 형충 시 취소).
    "cheonwoldeok_bonus": True,
    # ⑥ 세운 자문(무점수): 올해 세운이 원국 월지를 깨/합하면 '이사運/결혼運 든 해' 안내 1줄.
    "sewoon_advisory": True,
    # ③a 커플 정밀택일: 결혼에 상대 명식 제공 시 A설(양측 명식 동시조건) 적용. 미제공 시 편법(단인) 폴백.
    #   토글 OFF면 상대명식을 받아도 단인으로만 판정(관리자가 기능 자체를 끔).
    "wedding_couple_mode": True,
}
_MONTH_LUCK_PENALTY = 12       # ④ soft 월운 흉월 감점폭(월 단위 상수 → 같은 달 내 랭킹 불변)
_SIBAK_PENALTY = 8             # ① penalize 모드 감점폭
_CHEONWOLDEOK_BONUS = 4        # ⑤ 천월덕 길신 애드온(소폭)


class DayScore(BaseModel):
    date: str
    ganzhi: str                 # 일진 간지(한글(한자))
    hwangdo: str                # 황/흑 + 신 이름
    sonless: bool
    warnings: list[str] = Field(default_factory=list)  # 충/원진/형
    factors: dict[str, int]     # hwangdo/saju/sonless/geonje raw 0~100
    geonje: str = ""            # 건제신 "성(成)"
    geonje_note: str = ""       # 건제신 한 줄 의미
    su28: str = ""              # 이십팔수 "실(室)"
    su28_note: str = ""         # 28수 길흉 한 줄
    saenggi: str = ""           # 생기복덕 라벨(생기/복덕/절명… / Sinh khí…)
    saenggi_gil: str = ""       # 로케일 무관 stable 길흉키: gil|ban|hyung (프론트 색상 분기용)
    reason: str = ""            # 사용자 설명 — 왜 좋은지/나쁜지 한 줄(뽀 관법 근거)
    best_hours: list[dict] = Field(default_factory=list)   # 출산: 추천 시(時)
    score: int                  # 용도 가중 종합
    grade: str                  # 로케일 표시 라벨
    grade_key: str = ""         # 로케일 무관 stable key: best|good|normal|bad


# 용도별 관법 안내(사용자 이해용 — 이 택일이 무엇을 보는지). 뽀 관법·문헌 근거.
_RULE_NOTE = {
    "moving": "이사 택일은 그날 일진이 본인 사주의 재물(財)·일지(사는 자리)·월지(환경)를 충·형·파·해로 "
              "깨뜨리지 않는 날을 고릅니다. 깨진 날은 재물 손실·거주 불안으로 피합니다(월지는 이사 다음날 기준).",
    "wedding": "결혼 택일은 남자는 재(財=배우자)·일지가, 여자는 관(官=배우자)·일지가 깨지지 않는 날을 봅니다. "
               "비겁(연적·경쟁)이 드는 날은 피합니다. 상대(배우자) 명식을 함께 입력하면 신랑·신부 양측을 "
               "동시에 보아, 두 사람 모두 비겁이 드는 날만 배제하고 두 사람의 재·관이 함께 합(合)되는 날에 가점합니다.",
    "opening": "개업 택일은 재물(財)·일지가 충·형·파·해로 깨지지 않는 날을 보고, "
               "돈(財)이 식상(활동·표현)과 합(合)되는 날을 돈을 끌어오는 좋은 날로 봅니다.",
    "contract": "계약 택일은 문서(인수)가 충·형·파·해로 깨지지 않는 날을 보고, "
                "그날의 기운이 문서(인수)와 합(合)되는 날을 계약에 좋은 날로 봅니다.",
    "birth": "출산 택일은 그날 태어날 아이의 사주와 부모님의 궁합을 참고용으로 계산합니다. "
             "출산일은 함부로 정할 수 없는 큰일이니, 추천일은 참고만 하시고 상담사 님과 1:1 상담으로 정하시길 권합니다.",
}


class TaekilResult(BaseModel):
    purpose: str
    purpose_label: str
    user_day_branch: str
    rule_note: str = ""         # 이 택일이 무엇을 보는지(관법 안내) — 사용자 이해용
    applied_rule: str = ""      # ③a 결혼 커플 정밀택일 적용 관법(정식 양측 / 편법 단인) — 단정 회피 라벨
    sewoon_note: str = ""       # ⑥ 세운 자문(올해 이사運/결혼運 든 해 여부) — 무점수 안내
    best: list[DayScore]        # 추천 길일(보통 이상만 — 하드배제/흉일 제외)
    alt: list[DayScore] = Field(default_factory=list)  # 차선(기간 내 길일 없을 때만) — '추천' 아님
    no_gil: bool = False        # 조회 기간에 길일(보통 이상)이 없음 — 기간 확대 권고
    avoid: list[DayScore]       # 회피일
    perspectives: dict[str, dict]  # 관법별 라벨 + 추천 1위(다관법 비교)


def _bidx(b: str) -> int:
    return EARTHLY_BRANCHES.index(b)


def _geonje(month_branch: str, day_branch: str, locale: Locale = "ko") -> tuple[str, int, str]:
    """건제십이신 (한자기호, 점수0~100, 로케일 의미). 월지와 같은 일지 = 建."""
    idx = (_bidx(day_branch) - _bidx(month_branch)) % 12
    ch = _GEONJE_ORDER[idx]
    score, note = _GEONJE_INFO[ch]
    if locale == "vi":
        note = _GEONJE_NOTE_VI.get(ch, note)
    return ch, score, note


def _hwangdo(month_branch: str, day_branch: str) -> tuple[str, str, bool]:
    """(신이름, 황/흑, 길여부)."""
    start = _CHEONGYONG_START.get(month_branch)
    if not start:
        return ("미상", "?", False)
    pos = (_bidx(day_branch) - _bidx(start)) % 12
    name, hb = _SHIN[pos]
    return (name, hb, hb == "황")


def _compat_avg(parent_chart: SajuChart, baby_chart: SajuChart, locale: Locale = "ko") -> tuple[int, list[str]]:
    """아이-부모 궁합(5요소 A/B/C 평균)과 주의 신살. penalty type 은 로케일화되어 반환."""
    from .compatibility import compute_compatibility
    compat = compute_compatibility(parent_chart, baby_chart, locale=locale)
    score = round(sum(p.total for p in compat.perspectives.values()) / max(1, len(compat.perspectives)))
    return score, [p.type for p in compat.penalties[:3]]


# 12시진 대표 시각(자시 모호 회피용 중간값)
_SIJIN = [("子", "00:30"), ("丑", "02:30"), ("寅", "04:30"), ("卯", "06:30"),
          ("辰", "08:30"), ("巳", "10:30"), ("午", "12:30"), ("未", "14:30"),
          ("申", "16:30"), ("酉", "18:30"), ("戌", "20:30"), ("亥", "22:30")]


def _best_hours(d: date, parent_chart: SajuChart, parent2_chart: SajuChart | None,
                top: int = 3, locale: Locale = "ko") -> list[dict]:
    """출산 후보일의 12시진별 아이-부모 궁합 → 추천 시(時) 상위."""
    from datetime import time as _time
    vi = locale == "vi"
    out = []
    for branch, label in _SIJIN:
        hh, mm = int(label[:2]), int(label[3:])
        baby = build_chart(BirthInput(birth_date=d, birth_time=_time(hh, mm)), with_daewoon=False)
        s1, _ = _compat_avg(parent_chart, baby, locale)
        score = s1 if parent2_chart is None else round((s1 + _compat_avg(parent2_chart, baby, locale)[0]) / 2)
        hp = baby.pillars.hour
        if vi:
            sijin = f"Giờ {branch_reading(branch, locale)}"
            ganzhi = f"{stem_reading(hp.stem, locale)} {branch_reading(hp.branch, locale)}" if hp else ""
        else:
            sijin = f"{branch}시"
            ganzhi = f"{hp.stem}{hp.branch}" if hp else ""
        out.append({"sijin": sijin, "time": label, "ganzhi": ganzhi, "score": score})
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:top]


# ─────────────────────────────────────────────────────────────────────────
# 뽀 택일 관법(문헌 교차확증 2026-07-29, data/ocr S25C-1i2606091*·명리전 등):
#   이사   = 일진 vs 원국의 재(財)·일지·월지가 깨지지(충·형·파·해(申-亥)·천간극) 않는 날
#            (월지는 '이사 다음날' 일진 기준). 원진은 택일 흉에 근거 없어 제외.
#   결혼   = 남자→재(=처)·일지, 여자→관(=남편)·일지 깨짐 회피 + 관(官) 깨진 날 남녀 공통 흉
#            + 비겁(연적) 드는 날 배제. 재/관은 지장간까지 전수 판정('지장간까지 다 본다').
#   재/관/일지/월지 깨짐 = 문헌 '절대 잡지 마라' → 하드 배제(길일 제외).
# ─────────────────────────────────────────────────────────────────────────
_HAI_TAEKIL = frozenset({"申", "亥"})          # 택일 해(害)는 申-亥 쌍만 흉으로 취급(문헌)
_STAR_KO = {"재": "재(돈)", "관": "관(직위·배우자)", "비겁": "비겁(경쟁·연적)",
            "인수": "인수(문서·거주)"}

# ── ① 십악대패일(十惡大敗日) — C설(택일일 일진 기준) 10간지 ─────────
# 학파조사(wf_wqlmz9ssc): 코퍼스엔 원국/일주 기준 표만 실존(택일 전용 산출표 부재=통설).
# 문헌은 '길신 제화 시 무해'한 하위 흉신으로 규정 → 하드배제 금지, 주의 라벨(±소폭 감점)만.
_SIBAK_TAEPAE = frozenset({"甲辰", "乙巳", "丙申", "丁亥", "戊戌",
                           "己丑", "庚辰", "辛巳", "壬申", "癸亥"})

# ── ⑤ 天德·月德귀인(擇日 길신) — 코퍼스 값표 완전일치(214210:853-859) ──
# ⚠️ 위 황도12신의 '천덕(天德黃道, _SHIN)'과는 전혀 다른 신살 → 이름을 gwiin으로 분리.
# 天德귀인: 월지 → 글자. 4왕지월(卯午酉子)은 '지지', 나머지 8개월은 '천간'.
_CHEONDEOK_GWIIN = {
    "寅": "丁", "卯": "申", "辰": "壬", "巳": "辛", "午": "亥", "未": "甲",
    "申": "癸", "酉": "寅", "戌": "丙", "亥": "乙", "子": "巳", "丑": "庚",
}
# 月德귀인: 월지 삼합국 → 양간(寅午戌→丙·亥卯未→甲·申子辰→壬·巳酉丑→庚). 卯월=甲(코퍼스 OCR 교정).
_WOLDEOK_GWIIN = {
    "寅": "丙", "午": "丙", "戌": "丙",
    "亥": "甲", "卯": "甲", "未": "甲",
    "申": "壬", "子": "壬", "辰": "壬",
    "巳": "庚", "酉": "庚", "丑": "庚",
}
_CHEON_STEMS = frozenset("甲乙丙丁戊己庚辛壬癸")


def _cheon_wol_deok(month_branch: str, day_stem: str, day_branch: str) -> list[str]:
    """후보일이 天德·月德귀인일이면 라벨 목록. 天德 글자가 천간이면 일간과, 지지면 일지와 대조."""
    out: list[str] = []
    cd = _CHEONDEOK_GWIIN.get(month_branch)
    if cd and ((cd in _CHEON_STEMS and cd == day_stem) or (cd not in _CHEON_STEMS and cd == day_branch)):
        out.append("천덕귀인")
    if _WOLDEOK_GWIIN.get(month_branch) == day_stem:
        out.append("월덕귀인")
    return out


def _day_breaks_branch(day_branch: str, target_branch: str) -> set[str]:
    """일진 지지가 대상 지지를 '깨는' 관계 — 충·형·파 + 해(申-亥만). 원진·합·반합은 깨짐 아님."""
    rels = pair_branch_relations_ext(day_branch, target_branch)
    out = {r for r in rels if r in ("충", "형", "파")}
    if frozenset({day_branch, target_branch}) == _HAI_TAEKIL:
        out.add("해")
    return out


def _stem_geuk(day_stem: str, target_stem: str) -> bool:
    """일진 천간이 대상 천간(재/관이 실린 천간)을 극하는가."""
    de, te = STEM_TO_WUXING.get(day_stem), STEM_TO_WUXING.get(target_stem)
    return bool(de and te and WUXING_OVERCOMES.get(de) == te)


def _user_star_positions(user_chart: SajuChart, group: str) -> list[tuple[str, str, str, str]]:
    """원국에서 특정 십성 그룹(재/관/비겁)이 실린 (자리, stem|branch, 글자, 소속지지) 목록.
    지지는 지장간 전수(정기만이 아니라 HIDDEN_STEMS 전체)로 탐색 — 문헌 '지장간까지 다 본다'."""
    uds = user_chart.pillars.day.stem
    out: list[tuple[str, str, str, str]] = []
    for pos, ko in (("year", "년"), ("month", "월"), ("day", "일"), ("hour", "시")):
        p = getattr(user_chart.pillars, pos, None)
        if p is None:
            continue
        if pos != "day" and p.stem and STAR_GROUP.get(compute_ten_god(uds, p.stem)) == group:
            out.append((ko, "stem", p.stem, ""))
        if p.branch:
            for hs in HIDDEN_STEMS.get(p.branch, ()):
                if STAR_GROUP.get(compute_ten_god(uds, hs)) == group:
                    out.append((ko, "branch", hs, p.branch))
                    break
    return out


def _day_combines_star(ds: str, db: str, user_chart: SajuChart, group: str,
                       day_groups: frozenset[str] | None = None) -> bool:
    """그날 일진(천간·지지)이 원국의 재/관/인수 글자와 합(천간합·지지육합)하는가 — 합 가점용.
    문헌: '남자는 財와 合되는 일진이면 제일 좋은 날, 여자는 官과 合'(u00475·910480). 재/관을 '끌어옴'.

    day_groups: 합해 오는 '그날 글자'의 십성 그룹 제한(뽀 2026-08-03: 개업=돈이 '식상'과 합되는 날).
    미지정=무제한. 천간합은 그날 천간의 십성, 지지육합은 그날 지지 정기의 십성으로 판정."""
    uds = user_chart.pillars.day.stem
    if day_groups is not None:
        ds_grp = STAR_GROUP.get(compute_ten_god(uds, ds))
        hid = HIDDEN_STEMS.get(db) or (ds,)
        db_grp = STAR_GROUP.get(compute_ten_god(uds, hid[-1]))
    for _ko, kind, chstem, br in _user_star_positions(user_chart, group):
        if kind == "stem" and frozenset({ds, chstem}) in STEM_COMBINATIONS:
            if day_groups is None or ds_grp in day_groups:
                return True
        if kind == "branch" and br and "합" in pair_branch_relations_ext(db, br):
            if day_groups is None or db_grp in day_groups:
                return True
    return False


def _month_luck_hits(ch: SajuChart, user_chart: SajuChart) -> set[str]:
    """④ 다층운 '월운 층' — 후보일의 절기월 간지가 원국(월간·월지·일지·재)을 형충파해(申亥)극하는가.
    반환=깨진 대상 토큰 집합({월지,일지,재,월간}, 빈=무해). 월 단위 상수라 같은 절기월 내 랭킹 불변."""
    mstem, mbr = ch.pillars.month.stem, ch.pillars.month.branch
    um = user_chart.pillars.month.branch
    ub = user_chart.pillars.day.branch
    ums = user_chart.pillars.month.stem
    hits: set[str] = set()
    for tgt, ko in ((um, "월지"), (ub, "일지")):
        if _day_breaks_branch(mbr, tgt):
            hits.add(ko)
    for _ko, kind, chstem, br in _user_star_positions(user_chart, "재"):
        if (kind == "branch" and br and _day_breaks_branch(mbr, br)) or \
                (kind == "stem" and _stem_geuk(mstem, chstem)):
            hits.add("재"); break
    if ums and _stem_geuk(mstem, ums):
        hits.add("월간")
    return hits


def _sewoon_advisory(user_chart: SajuChart, year_branch: str, purpose: str, year: int) -> str:
    """⑥ 세운 자문(무점수) — 그해 세운 지지가 원국 월지를 깨/합하면 '이사運/결혼運 든 해' 안내."""
    um = user_chart.pillars.month.branch
    kind = "이사" if purpose == "moving" else "결혼"
    brk = _day_breaks_branch(year_branch, um)
    if brk:
        return (f"올해({year}) 세운이 원국 월지를 {'·'.join(sorted(brk))}해 "
                f"{kind}運이 발동한 해로 봅니다(변동·이동 시기).")
    if "합" in pair_branch_relations_ext(year_branch, um):
        return (f"올해({year}) 세운이 원국 월지와 합해 {kind}運이 있으나 "
                f"서두를 필요는 없는 해로 봅니다(가도 되고 안 가도 되는 운).")
    return ""


def _broken_star(ds: str, db: str, chart: SajuChart, group: str) -> str:
    """그날 일진이 명식의 해당 십성(전지장간·천간)을 깨면 관계명, 아니면 ''."""
    for _ko, kind, chstem, br in _user_star_positions(chart, group):
        if kind == "branch":
            rel = _day_breaks_branch(db, br)
            if rel:
                return "·".join(sorted(rel))
        elif _stem_geuk(ds, chstem):
            return "극"
    return ""


def _is_bigyeop_day(ds: str, db: str, chart: SajuChart) -> bool:
    """그날 일진(천간·지지 정기)이 명식 일간 기준 비겁(연적·경쟁)인가."""
    cds = chart.pillars.day.stem
    g_stem = STAR_GROUP.get(compute_ten_god(cds, ds))
    hid = HIDDEN_STEMS.get(db) or (ds,)
    g_br = STAR_GROUP.get(compute_ten_god(cds, hid[-1]))
    return "비겁" in (g_stem, g_br)


def _ppo_saju(purpose: str, ch: SajuChart, next_ch: SajuChart | None,
              user_chart: SajuChart, is_male: bool,
              partner_chart: SajuChart | None = None,
              partner_is_male: bool | None = None) -> tuple[int, list[str], list[str], bool, list[str]]:
    """뽀 택일 관법 사주팩터. → (점수0~100, 경고, 이유(나쁨), 하드배제여부, 이유(좋음)).
    ③a 커플 정밀택일: 결혼에 상대 명식(partner_chart) 제공 시 A설 — 배우자궁(일지)·배우자star를 양측
    각 명식으로 판정, 비겁은 '양측 동시=하드배제·한쪽=허용(어드바이저리)', 양측 동시 合은 최고 길일 가점."""
    ds, db = ch.pillars.day.stem, ch.pillars.day.branch
    ub = user_chart.pillars.day.branch
    f, warns, bad, disq, good = 70, [], [], False, []
    couple = (purpose == "wedding" and partner_chart is not None
              and bool(TAEKIL_OPTIONS.get("wedding_couple_mode")))

    # (공통) 일지(자기·배우자궁) 깨짐 — 본인 명식
    ilji = _day_breaks_branch(db, ub)
    if ilji:
        f -= 45; disq = True
        warns.append(f"일지{'·'.join(sorted(ilji))}")
        bad.append(f"일지(자기·배우자궁) {'·'.join(sorted(ilji))}")

    _bigyeop_block = False   # 合 가점 억제(penalize 모드에서만 — 뺏김 방어)
    if purpose in ("wedding", "moving", "opening", "contract"):
        # 보호 대상: 결혼=성별(남 재/여 관)·이사/개업=재(돈)·계약=인수(문서 — 뽀 2026-08-03: 계약은
        # 문서(印) 중심, 코퍼스 '인성운에 매매계약' 정합). (그룹, 하드배제, 감점폭).
        checks: list[tuple[str, bool, int]] = (
            [("재" if is_male else "관", True, 40)] if purpose == "wedding"
            else [("인수", True, 40)] if purpose == "contract"
            else [("재", True, 40)])
        if purpose == "wedding" and is_male:
            checks.append(("관", False, 40))       # 남자도 官 깨진 날 공통 흉(하드배제는 아님)
        # ② 이사 인수(印) 보호 — 옵션 ON일 때만 soft 감점(재는 hard 유지, 印은 근거 통설).
        if purpose == "moving" and TAEKIL_OPTIONS.get("moving_protect_insu"):
            checks.append(("인수", False, 15))
        for grp, hard, pen in checks:
            rel = _broken_star(ds, db, user_chart, grp)
            if rel:
                f -= pen
                if hard:
                    disq = True
                warns.append(f"{_STAR_KO[grp]}{rel}")
                bad.append(f"{_STAR_KO[grp]} {rel}")

        # ③a 커플 정밀(A설): 상대 명식의 배우자궁(일지)·배우자star(상대 성별)도 각 명식 기준 하드 판정.
        if couple:
            p_ilji = _day_breaks_branch(db, partner_chart.pillars.day.branch)
            if p_ilji:
                f -= 45; disq = True
                warns.append(f"상대 일지{'·'.join(sorted(p_ilji))}")
                bad.append(f"상대 배우자궁(일지) {'·'.join(sorted(p_ilji))}")
            p_star = "재" if partner_is_male else "관"
            p_rel = _broken_star(ds, db, partner_chart, p_star)
            if p_rel:
                f -= 40; disq = True
                warns.append(f"상대 {_STAR_KO[p_star]}{p_rel}")
                bad.append(f"상대 {_STAR_KO[p_star]} {p_rel}")

        # ③ 비겁(연적) 드는 날 — 문헌(911010:257-259): '남·여 둘 다 비겁이면 배제, 한쪽만이면 대체일
        #   없을 때 허용'. 커플(상대명식)=양측 AND 하드배제·한쪽 허용(A설). 단인=어드바이저리(소폭).
        #   ⚠️ 양측 동시 배제는 A설 핵심(문헌 근거)이라 커플 게이트에만 종속 — 단인용 advisory 토글
        #      (wedding_bigyeop_mode='off')이 이를 함께 끄지 않게 mode 가드 밖에 둔다.
        if purpose == "wedding":
            mode = TAEKIL_OPTIONS.get("wedding_bigyeop_mode", "advisory")
            u_big = _is_bigyeop_day(ds, db, user_chart)
            p_big = couple and _is_bigyeop_day(ds, db, partner_chart)
            if couple and u_big and p_big:                         # 양측 동시 → 하드배제(mode 무관)
                f -= 30; disq = True; _bigyeop_block = True
                warns.append("양측 비겁일")
                bad.append("양측(신랑·신부) 비겁 — 연적·경쟁 겹침(문헌 배제)")
            elif (u_big or p_big) and mode != "off":               # 한쪽 비겁 → 단인 advisory 토글 적용
                if mode == "penalize" and not couple:              # 구 동작(단인 배제형)
                    f -= 30; _bigyeop_block = True
                    warns.append("비겁일"); bad.append("비겁(연적·경쟁) 드는 날")
                else:                                              # 한쪽 비겁 → 허용(어드바이저리)
                    f -= 6
                    warns.append("한쪽 비겁일(대체일 없으면 허용)" if couple
                                 else "비겁일(상대 명식 확인 요망)")

        # 이사 월지 — '이사 다음날' 일진 기준(문헌)
        if purpose == "moving" and next_ch is not None:
            um = user_chart.pillars.month.branch
            mz = _day_breaks_branch(next_ch.pillars.day.branch, um)
            if mz:
                f -= 25; disq = True
                warns.append(f"월지{'·'.join(sorted(mz))}")
                bad.append(f"이사 다음날 월지(거주·환경) {'·'.join(sorted(mz))}")

        # 合 가점 — '끌어오는' 길일(문헌 '제일 좋은 날'). 단 깨짐(disq)·비겁일 배제모드면 '뺏김'이라 가점 없음.
        #   결혼=남財/여官(커플이면 양측 동시 合 최길) · 이사=財 · 개업=財가 '식상'과 합(뽀 2026-08-03:
        #   '돈이 식상과 합되는 날' — 비겁이 財와 합하면 뺏김이라 식상 합만 가점) · 계약=인수(문서) 합
        #   (뽀: '관이랑·식상이랑·재랑 인수가 합되는 날' — 인수와 합해 오는 글자는 구조상 관/식상/재뿐).
        if not disq and not _bigyeop_block and purpose in ("wedding", "moving", "opening", "contract"):
            if purpose == "wedding":
                star = "재" if is_male else "관"
                u_hap = _day_combines_star(ds, db, user_chart, star)
                if couple:
                    p_star = "재" if partner_is_male else "관"
                    p_hap = _day_combines_star(ds, db, partner_chart, p_star)
                    if u_hap and p_hap:
                        f += 18
                        good.append("양측 재·관 동시 합(合) — 두 사람 모두 끌어오는 최고 길일")
                    elif u_hap:
                        f += 12
                        good.append(f"{_STAR_KO[star]} 합(合) — 매우 좋은 날")
                elif u_hap:
                    f += 12
                    good.append(f"{_STAR_KO[star]} 합(合) — 매우 좋은 날")
            elif purpose == "moving":
                if _day_combines_star(ds, db, user_chart, "재"):
                    f += 12
                    good.append(f"{_STAR_KO['재']} 합(合) — 매우 좋은 날")
            elif purpose == "opening":
                if _day_combines_star(ds, db, user_chart, "재", day_groups=frozenset({"식상"})):
                    f += 12
                    good.append("재(돈)-식상 합(合) — 돈을 끌어오는 개업 길일")
            else:  # contract — 인수(문서) 합
                if _day_combines_star(ds, db, user_chart, "인수"):
                    f += 12
                    good.append("인수(문서) 합(合) — 계약에 좋은 날")

    return max(0, min(100, f)), warns, bad, disq, good


def _score_day(d: date, parent_chart: SajuChart, purpose: str, bonmyeong: str = "",
               parent2_chart: SajuChart | None = None, locale: Locale = "ko") -> DayScore:
    vi = locale == "vi"
    ch = build_chart(BirthInput(birth_date=d), with_daewoon=False)
    mb = ch.pillars.month.branch
    db = ch.pillars.day.branch
    ds = ch.pillars.day.stem
    user_branch = parent_chart.pillars.day.branch
    pair = frozenset({db, user_branch})

    # ① 황도흑도
    shin, hb, is_hwangdo = _hwangdo(mb, db)
    f_hwangdo = 85 if is_hwangdo else 30

    warns: list[str] = []
    _bad: list[str] = []       # 뽀 관법 '나쁜 이유'(설명 기능용)
    _good: list[str] = []      # 뽀 관법 '좋은 이유'(합 가점 등)
    _disq = False              # 재/관/일지/월지 깨짐 → 하드 배제
    _month_pen = 0             # ④ 월운(흉월) soft 감점
    if purpose == "birth":
        # ② 출산: 그날 태어날 아이와 부모의 궁합. 양부모면 둘의 평균. (warns 는 로케일화된 신살명)
        s1, w1 = _compat_avg(parent_chart, ch, locale)
        if parent2_chart is not None:
            s2, w2 = _compat_avg(parent2_chart, ch, locale)
            f_saju = round((s1 + s2) / 2)
            warns = list(dict.fromkeys(w1 + w2))[:3]
        else:
            f_saju, warns = s1, w1
    else:
        # ② 본인 사주 회피 — 뽀 관법(문헌 교차확증): 재/관/일지/월지·비겁을 형충파해(申亥)극으로 회피.
        #    원진은 택일 흉에 문헌 근거 없어 제외(감사 wf_5f52bbc9). 이사 월지는 '이사 다음날' 기준.
        from .types import Gender
        _is_male = parent_chart.input.gender == Gender.MALE
        _next_ch = (build_chart(BirthInput(birth_date=d + timedelta(days=1)), with_daewoon=False)
                    if purpose == "moving" else None)
        # ③a 커플 정밀택일 — 결혼에 상대 명식(parent2_chart) 제공 시 양측 판정.
        _partner = parent2_chart if purpose == "wedding" else None
        _p_male = (_partner.input.gender == Gender.MALE) if _partner is not None else None
        f_saju, _pw, _bad, _disq, _good = _ppo_saju(
            purpose, ch, _next_ch, parent_chart, _is_male, _partner, _p_male)
        warns.extend(_pw)
        # ④ 다층운 '월운 층' — 후보일 절기월 간지가 원국(월간·월지·일지·재)을 깨면 흉월.
        #   soft(기본)=월 단위 감점(같은 달 내 랭킹 불변, 흉월 전체 하향) / strict=월지 깨진 달 하드배제.
        if purpose in ("moving", "wedding", "opening", "contract") and \
                TAEKIL_OPTIONS.get("month_luck_mode") != "off":
            _ml = _month_luck_hits(ch, parent_chart)
            if _ml:
                _ml_txt = "·".join(t for t in ("월지", "일지", "재", "월간") if t in _ml)
                warns.append(f"월운 흉월({_ml_txt} 깨짐)")
                if TAEKIL_OPTIONS.get("month_luck_mode") == "strict" and "월지" in _ml:
                    _disq = True
                    _bad.append("월운 흉월(월지 깨짐) — 이 달 회피")
                else:
                    _month_pen = _MONTH_LUCK_PENALTY
    f_saju = max(0, min(100, f_saju))

    # ③ 손없는날 (음력 끝자리 9·0)
    lday = ch.lunar_date.day
    sonless = (lday % 10) in (9, 0)
    f_sonless = 90 if sonless else 55

    # ④ 건제십이신 (중단 택일)
    gj_ch, f_geonje, gj_note = _geonje(mb, db, locale)
    if f_geonje <= 28:  # 破·閉 = 大凶 → 경고 배지
        warns.append(_geonje_badge(gj_ch, locale))

    # ⑤ 이십팔수(28수) 길흉 (歳事暦)
    su_ch, su_read, su_note = _su28(d, locale)
    f_su28 = _su28_score(su_ch, purpose)

    # ⑥ 생기복덕 (본명괘 + 그날 일지 → 생기/복덕/절명…). sb_key=gil|ban|hyung(로케일 무관)
    from .sinsal import saenggi_bokdeok
    sb_label, sb_gil, sb_key = saenggi_bokdeok(bonmyeong, db, locale) if bonmyeong else ("", "", "")
    f_saenggi = {"길": 85, "반": 55, "흉": 28}.get(sb_gil, 60)
    if sb_gil == "흉":
        warns.append(sb_label)

    factors = {"hwangdo": f_hwangdo, "saju": f_saju, "sonless": f_sonless,
               "geonje": f_geonje, "su28": f_su28, "saenggi": f_saenggi}
    w = _PURPOSE_WEIGHTS.get(purpose, _PURPOSE_WEIGHTS["general"])
    score = round(sum(factors[k] * w[k] / 100 for k in w))
    score -= _month_pen                        # ④ 월운(흉월) soft 감점
    # 뽀 관법 하드 배제 — 재/관/일지/월지가 깨진 날은 문헌상 '절대 잡지 마라' → 길일 불가(회피일로).
    if _disq:
        score = min(score, 44)
    # ⑤ 天德·月德귀인 소폭 길신 가점(결혼·이사 한정, 그날 형충(하드배제) 없을 때만 — 문헌 '형충되면 무력').
    if TAEKIL_OPTIONS.get("cheonwoldeok_bonus") and purpose in ("wedding", "moving") and not _disq:
        _deok = _cheon_wol_deok(mb, ds, db)
        if _deok:
            score += _CHEONWOLDEOK_BONUS
            _good.insert(0, "·".join(_deok) + " 길신")
    # ① 십악대패일(택일일 일진, C설) — 하드배제 금지. 라벨만(기본) 또는 소폭 감점.
    _sibak_mode = TAEKIL_OPTIONS.get("sibak_taepae_mode", "label")
    if _sibak_mode != "off" and f"{ds}{db}" in _SIBAK_TAEPAE:
        warns.append("십악대패일(옛 흉일설)")
        if _sibak_mode == "penalize":
            score -= _SIBAK_PENALTY
    score = max(0, min(100, score))
    grade_key = "best" if score >= 80 else "good" if score >= 65 else "normal" if score >= 50 else "bad"
    grade = _GRADE_LABEL[locale][grade_key]
    # ⑦ 설명(사용자 이해용) — 나쁜 이유가 있으면 그것, 없으면 좋은 근거 요약(결정적)
    if _bad:
        reason = "회피 — " + ", ".join(_bad[:3])
    else:
        goods: list[str] = list(_good)   # 재/관 合 가점(있으면 맨 앞)
        if is_hwangdo:
            goods.append("황도 길신")
        if sonless:
            goods.append("손없는날")
        if sb_gil == "길" and sb_label:
            goods.append(sb_label)
        goods.append({"moving": "재물·거주궁(일지·월지) 온전",
                      "wedding": "배우자궁(일지)·재관 온전"}.get(purpose, "일지 온전"))
        reason = "좋음 — " + ", ".join(goods[:3])
        # ④ 월운 흉월이면 '좋은 일진이라도 이 달은 순위 하향' 단서를 붙여 모순 표기 방지.
        if _month_pen:
            reason += " · 단, 이 달은 월운 흉월이라 순위 하향"

    sr, br = stem_reading(ds, locale), branch_reading(db, locale)
    ganzhi = f"{sr} {br}" if vi else f"{sr}{br}({ds}{db})"

    return DayScore(
        date=d.isoformat(),
        ganzhi=ganzhi,
        hwangdo=_fmt_hwangdo(shin, hb, locale),
        sonless=sonless,
        warnings=warns,
        factors=factors,
        geonje=_geonje_badge(gj_ch, locale),
        geonje_note=gj_note,
        su28=su_read if vi else f"{su_read}({su_ch})",
        su28_note=su_note,
        saenggi=sb_label,
        saenggi_gil=sb_key,
        score=score,
        grade=grade,
        grade_key=grade_key,
        reason=reason,
    )


def recommend_dates(
    user_chart: SajuChart,
    start: date,
    days: int = 60,
    purpose: str = "general",
    top: int = 10,
    user_chart2: SajuChart | None = None,
    locale: Locale = "ko",
) -> TaekilResult:
    """기간(start~start+days) 내 날짜 점수화 → 길일 top / 회피일.
    user_chart2: 출산택일의 두 번째 부모(선택).
    locale='ko'(기본)은 한국 서비스와 동일. 'vi'는 라벨·간지·신살을 한월음 기반 베트남어로."""
    purpose = purpose if purpose in PURPOSES else "general"
    ub = user_chart.pillars.day.branch
    # 본명괘(구성 본명성, 생년·성별) → 생기복덕용. 출산은 부모 기준.
    from .sinsal import bonmyeong_gwae
    from .types import Gender
    bonmyeong = bonmyeong_gwae(user_chart.input.birth_date.year, user_chart.input.gender == Gender.MALE)
    # 출산=두 번째 부모(궁합 평균), 결혼=상대 명식(③a 커플 정밀택일). 그 외 용도는 미사용.
    p2 = user_chart2 if purpose in ("birth", "wedding") else None
    scored = [_score_day(start + timedelta(days=i), user_chart, purpose, bonmyeong, p2, locale) for i in range(max(1, days))]

    # ③a 결혼 커플 정밀택일 — 적용 관법 라벨(단정 회피). 상대 명식 유무 + 관리자 토글로 결정.
    applied_rule = ""
    if purpose == "wedding":
        applied_rule = ("정식(신랑·신부 양측 명식)"
                        if (p2 is not None and TAEKIL_OPTIONS.get("wedding_couple_mode"))
                        else "편법(본인 명식만 — 상대 명식 입력 시 양측 정밀 판정)")

    # ⑥ 세운 자문(무점수) — 조회 시작연도의 세운이 원국 월지를 깨/합하는지(이사·결혼만).
    #   ⚠️ 세운 지지는 '입춘 기준'(pillars getYearGZ)이라, 입춘 전 시작일(1~2월초)로 차트를 지으면
    #   전년 사주해 지지가 잡혀 라벨연도(start.year)와 어긋난다 → 라벨연도의 입춘 이후(6/1)로 세운을 뽑는다.
    sewoon_note = ""
    if TAEKIL_OPTIONS.get("sewoon_advisory") and purpose in ("moving", "wedding"):
        _ych = build_chart(BirthInput(birth_date=date(start.year, 6, 1)), with_daewoon=False)
        sewoon_note = _sewoon_advisory(user_chart, _ych.pillars.year.branch, purpose, start.year)
    _desc = sorted(scored, key=lambda x: x.score, reverse=True)
    # '추천 길일'에는 반드시 '보통(50)' 이상만 담는다 — 재/관/일지/월지 하드배제일(_disq→score≤44)과
    #   흉일(<50)이 top-N 슬라이스로 '추천'에 오르던 결함(재검증 wwh751a42) 차단.
    #   month_luck=soft 등으로 후보가 얇아져 아무 날도 50 이상이 아니면 best는 빈 리스트가 된다.
    best = [s for s in _desc if s.score >= 50][:top]
    # 이 기간에 길일이 없으면 '차선(참고)'으로 상위 몇 개만 명시적 라벨과 함께 노출(추천 길일 아님).
    alt: list[DayScore] = [] if best else _desc[:min(top, 5)]
    no_gil = not best
    # 회피일에서 추천 길일·차선 제외(전수감사): 소창(days≤10)에선 같은 날이 '대길일'이자 '회피일'로
    # 동시 주입돼 자기모순 brief가 됐다(실측 확정 발생). 경고는 best 라인에 함께 표기(_render).
    _used = {b.date for b in best} | {a.date for a in alt}
    avoid = [s for s in sorted(scored, key=lambda x: x.score)
             if (s.warnings or s.grade == "흉일") and s.date not in _used][:5]

    # 출산: 추천 길일별 최적 시(時) 산출(상위 일자만 — 12시진×궁합). 길일 없으면 차선에 산출.
    if purpose == "birth":
        from datetime import date as _d
        for ds_ in (best or alt):
            ds_.best_hours = _best_hours(_d.fromisoformat(ds_.date), user_chart, p2, locale=locale)

    # 관법별 추천 1위(다관법 비교) — 같은 기간을 관법마다 다르게 가중해 1위가 갈림
    persp: dict[str, dict] = {}
    for k, v in PERSPECTIVES.items():
        w = v["weights"]
        ranked = sorted(
            scored, key=lambda s: sum(s.factors[fk] * w[fk] / 100 for fk in w), reverse=True
        )
        topday = ranked[0]
        persp[k] = {
            "label": _PERSP_LABEL[locale][k],
            "top_date": topday.date,
            "top_ganzhi": topday.ganzhi,
            "top_score": round(sum(topday.factors[fk] * w[fk] / 100 for fk in w)),
        }

    return TaekilResult(
        purpose=purpose,
        purpose_label=_PURPOSE_LABEL[locale][purpose],
        user_day_branch=(branch_reading(ub, locale) if locale == "vi" else f"{branch_reading(ub, locale)}({ub})"),
        rule_note=_RULE_NOTE.get(purpose, ""),
        applied_rule=applied_rule,
        sewoon_note=sewoon_note,
        best=best,
        alt=alt,
        no_gil=no_gil,
        avoid=avoid,
        perspectives=persp,
    )
