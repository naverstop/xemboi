# 사주 답변 검증기 전수감사 로드맵 (2026-07 워크플로우 117-에이전트)

환각을 "터지고 고치는" 후행 대응에서 "터지기 전 검증기"로 전환하기 위한 전수감사 결과.
9개 도메인 인벤토리 → 클래스별 적대검증 → 우선순위 종합. 아래는 종합 로드맵 원문.

---

# 사주 환각 검증기 구축 로드맵

> 대상 파일: `D:\saju_agent\backend\app\services\chat_service.py` (브랜치 `feat/claude-refine-and-compatibility` — main은 화석, 코드 검증 완료). 궁합/작명/택일은 `compat_service.py` / `tool_service.py` 경로.
> 감사의 모든 라인 참조(`_verify_branches:650`, `_verify_daewoon:740`, `_verify_myeongsik:863`, `_bad:943`, `_scrub_stale_year_ganji:1101`)를 실파일에서 확인함. 아래는 그 위에 바로 얹는 설계다.

---

## 0. 정정 사항 (착수 전 필독)

감사 전반의 두 전제가 반복적으로 **오류**로 판명됐다. 로드맵은 이를 반영한다.

1. **`chart_json`에 `birth_date`가 있다.** 여러 클래스가 "검증기 시그니처가 `(answer, chart_json)`뿐이라 나이 계산 불가 → 불가능"이라 판정했으나, `chart.model_dump()` 결과에 `input.birth_date` / `solar_date`가 실려온다. 즉 나이·현재대운은 시그니처 확장 없이 계산 가능. (다만 만/세는나이 ±1은 여전히 톨러런스로 흡수)
2. **`_verify_daewoon`은 나이를 전혀 안 본다.** 간지 집합(`_daewoon_ganji_set`) 멤버십만 검사 → **나이구간↔간지 페어링은 완전 미검증**. 이게 이 로드맵의 최대 갭이다.

---

## 1. 중복/유사 클래스 병합

감사에는 같은 결정값을 겨냥한 클래스가 여러 도메인에 흩어져 중복 판정돼 있다. 실제 구축 단위로 병합한다.

| 병합 검증기 | 흡수한 원본 클래스들 | 결정값 |
|---|---|---|
| **V1. `_verify_daewoon_age_range`** (대운 나이구간↔간지) | "현재 대운 나이구간 매핑"(P2×2), "Next Great Luck…(A)"(P0), "대운 나이구간(범위)"(P1×2), "현재나이↔대운 나이구간"(P1×2) | `daewoon.entries[i].start_age ~ entries[i+1].start_age-1` |
| **V2. `_verify_current_daewoon`** (현재나이→현재대운 간지) | "Age→Current Great Luck"(P0), "현재대운 나이구간(현재나이부)"(P1) | `birth_date`→age→`ci=max(i: start_age≤age)`→`entries[ci].pillar` |
| **V3. `_verify_pillar_ganji`** (주柱어+간지 재서술) | "명식 4주 지지 재서술 — 일주/월주/년주/시주"(P0) | `chart_json.pillars[key].{stem,branch}` |
| **V4. `_verify_gongmang`** (공망 2지지) | "공망 지지 주장"(P1), "운성·신살·공망·납음(공망부)"(P1) | `chart_json.gongmang` (2지지) |
| **V5. `_scrub` 일반화** (명시연도↔세운 간지) | "연도↔간지 매핑"(P1), "특정연도 세운 간지"(P1), "세운↔간지"(P2) | `sxtwl.getYearGZ(year)` = `_year_ko_hj(y)` |
| **V6. `_verify_daewoon_start_age`** (대운수) | "Starting Age 대운수"(P0), "대운수 값 정확성"(P1) | `daewoon.start_age` |
| **V7. `_verify_daewoon_direction`** (순/역행) | "대운 순행/역행"(P2), "대운 방향↔성별·년간"(P1) | `daewoon.direction ∈ {forward,backward}` |
| **V8. `_verify_ganji_element` 앵커 확장** | "간지 오행 속성"(P1 보강), "간지→오행 일치"(drop=이미 커버) | `ganji_allowed_elements` (기존 로직 재사용) |
| **V9. `_verify_current_age`** (현재 만나이 재서술) | "verify_current_age"(P1), "현재나이↔대운(나이부)"(P1) | `int((today-birth_date).days/365.25)` |
| **V10. 궁합 관계 검증기 3종** | "일지 육합/삼합/충 라벨"(P1), "일간 천간합/충"(P1), "궁합 상호십성"(P1) | `compatibility._score_day_branch/_score_day_stem/compute_ten_god` |
| **V11. 택일 황도/건제 검증기** | "택일 황도흑도+건제십이신"(P1) | `taekil._hwangdo/_geonje` → `result_json.best/avoid` |
| **V12. 작명 수리 4격 길흉** | "작명 수리 81수 4격 길흉"(P1) | `naming._four_pillars`→`_suri_grade` (brief 파싱) |
| **V13. 작명 자원오행** | "작명 후보 자원오행"(P1) | `result_json.candidates[*].{given,elements}` |
| **P2 신살/운성/납음/지장간 묶음** | 십이운성·십이신살·납음·지장간 위치별 (전부 P2) | `chart_json.{twelve_life,twelve_sinsal,napeum,hidden_stems}` |

---

## 2. 티어별 정렬

### ★ P0 — 즉시 구축 (고심각·저오탐·결정적·실측 관측)

| # | 검증기 | 심각도 | 오탐 | 왜 P0 |
|---|---|---|---|---|
| V1 | 대운 나이구간↔간지 페어링 | high | low | 실측 관측('11~20 갑오/21~30 계사'), 기존 검증기 **완전 미커버**, `start_age`만으로 결정적, 앵커 좁음 |
| V3 | 주柱어+간지 재서술 (`일주 신미`) | high | low | 실측 지배 패턴(62·63·117·174·179행), `_verify_branches`가 '지지 위치어'만 봐서 **100% MISS**, 정방향 앵커 오탐 ≈0 |
| V2 | 현재나이→현재대운 간지 | high | med | 실측 관측('19세→갑오 대운'), `birth_date`로 결정적, 대운 프레임 오염이 커 신뢰 훼손 큼 |

### ● P1 — 차상위 (결정적이나 발생빈도↓ 또는 오탐 튜닝 필요)

| # | 검증기 | 심각도 | 오탐 | 비고 |
|---|---|---|---|---|
| V5 | `_scrub` 일반화(명시연도↔세운) | med | low | **기존 스크러버 버그 수정 포함** — 먼 미래 정답 간지를 '올해'로 파괴하는 능동 손상 |
| V8 | `_verify_ganji_element` 앵커 확장 | med | low | 기존 검증기 커버리지가 실측의 일부만 잡음('화기운이 강하게' MISS) → 앵커 확장 |
| V9 | 현재 만나이 재서술 | med | med | `birth_date` 결정적, '현재 N세' 좁은 앵커 + ±1 톨러런스 |
| V4 | 공망 2지지 | med | med | OCR 코퍼스 1급 개념, 종합풀이서 등장 개연성(likely), '공망+계사+2지지' 좁은 앵커 |
| V7 | 대운 순/역행 | med | low | `direction` 직접 대조(성별 재계산 불요), 구현 5줄 |
| V11 | 택일 황도/건제 | med | med | `result_json.best/avoid` 조인, 날짜 근접 이중조건 |
| V12 | 작명 수리 4격 길흉(개명 전용) | med | med | 격라벨+획수+길흉 3요소 동시근접, brief 파싱 |
| V13 | 작명 자원오행 | med | high | '자원오행' 문맥 앵커 + **발음오행 배제 필수**(최대 오탐원) |
| V10 | 궁합 관계 3종(육합/충·천간합충·상호십성) | high(궁합) | med | 위치어 게이트+두 일지/일간 공출현 이중 앵커, 궁합 경로 한정 |
| V6 | 대운수 값 | low | low | 저비용 백스톱, '대운수' 전용어 앵커 |

### ○ P2 — 여력 시 (결정적이나 프롬프트 미주입→실측 0건, ROI 낮음)

- **위치별 십이운성/십이신살/납음/지장간** — 전부 결정적이나 `_build_saju_summary`에 미주입되어 LLM이 거의 언급 안 함(실측 0건). **선행조건: 프롬프트에 주입하면 즉시 P1 승격.** 프론트 SajuChart 표엔 이미 노출되므로 주입 시 화면-답변 시각적 모순 위험.
- **위치별 십성(천간 슬롯만)** — 년간/월간만, 지지는 지장간 도피처로 오탐 폭발이라 제외.
- **궁합 원진/귀문/등급** — 궁합 truth 먼저 계산해 '성립 pair 무조건 통과' 게이트 후 '비성립인데 단정'만 잡는 초협소 버전.

---

## 3. P0/P1 상세 설계

### V1. `_verify_daewoon_age_range` — 대운 나이구간↔간지 【P0】

**검증 대상:** 답변의 'N~M세: 간지' 또는 '간지(N~M세)' 페어가 엔진 대운 구간과 일치하는지.

**정답 계산:**
```python
entries = chart_json["daewoon"]["entries"]  # [{pillar:{stem,branch}, start_age:int}, ...]
# 간지 g의 기대구간: [e.start_age, next_e.start_age - 1], 마지막은 개구간
```

**anchor_strategy:**
```python
# 양방향, '세' 단위 필수
_AGE_RANGE_FWD = re.compile(rf"(\d{{1,2}})\s*[~∼\-]\s*(\d{{1,2}})\s*세[^가-힣\n]{{0,6}}[:：·\s(（]{{0,3}}({_DW_GANJI})")
_AGE_RANGE_REV = re.compile(rf"({_DW_GANJI})\s*(?:\([一-鿿]{{1,2}}\))?\s*[,、(（]?\s*(\d{{1,2}})\s*[~∼\-]\s*(\d{{1,2}})\s*세")
```
매칭된 `(lo, hi, ganji)`마다: ① ganji를 한자로 정규화(위치기준, 중의성 없음) → entries에서 그 pillar 찾기 → `expected=[start_age, next_start-1]`. ② `lo != start_age` 또는 `hi != next_start-1`이면 플래그.

**오탐 가드:**
1. **`세` 단위 토큰 필수** — 순수 숫자('11~20') 배제, 구어체 십의자리('20대','30대')는 `~`가 없어 자연 배제.
2. **간지가 대운목록에 없으면 skip** — `_verify_daewoon`이 먼저 잡으므로 이중보고 회피.
3. **±1세 경계 톨러런스** — `int(round())` 반올림·만나이 흡수. `abs(lo-start)<=1 and abs(hi-(next-1))<=1`이면 통과.
4. **과거문맥 필터** — 앞 10자에 `_MONTH_PAST_CTX`(작년/지난/당시/과거) 있으면 skip.
5. **전이화법 제외** — 범위-간지 사이 10자 내 '전환/끝자락/초반부터/점차' 있으면 skip.
6. `entries` 없거나 2개 미만이면 즉시 `return []`.

**배선:** `_verify_myeongsik`(863) + `_bad`(943, `chart_json is not None` 블록)에 추가.

---

### V3. `_verify_pillar_ganji` — 주柱어+간지 재서술 【P0】

**검증 대상:** '일주 신미(辛未)', '월주 병신', '년주 병술' 등 柱어+간지가 명식 4주와 일치하는지. 기존 `_POS_WORDS`(624)는 년지/월지 등 '**지**' 위치어만 앵커 → 柱어를 100% 놓침(실증됨).

**정답 계산:** `chart_json["pillars"][{year|month|day|hour}].{stem,branch}`.

**anchor_strategy:**
```python
_PILLAR_WORDS = {"년주":"year","연주":"year","월주":"month","일주":"day","시주":"hour"}
# 정방향(오탐≈0, 우선 구현):
_PILLAR_FWD = re.compile(rf"(년주|연주|월주|일주|시주)[은는이가의:\s(（]*({_DW_GANJI})")
```
매칭 `(주어, 간지)` → `_PILLAR_WORDS[주어]`의 pillars와 stem+branch 전체 대조. 불일치 시 플래그. **간지 전체(천간+지지) 비교**가 지지만 비교보다 강하고 오탐도 낮음.

**오탐 가드:**
1. **역방향('신미 일주')은 조건부** — '갑오일주'(생일 유형 일반명사, 프롬프트룰 162행에 존재)가 FP. → 역방향은 (a)간지 뒤 한자병기 `()` 있을 때만, 또는 (b)간지 앞 경계/조사 있을 때만. **정방향만으로 실측 갭 대부분 커버되므로 역방향은 후순위.**
2. 스트레스 통과 확인: '대운은 갑오'·'2027 정미 대운'·'7월 병신'(주어 없음) 모두 no-match.
3. `_myeongsik_truth`(887) 헤더에 년주/월주 간지 병기(현재 지지만 출력).

**배선:** `_verify_myeongsik` + `_bad`.

---

### V2. `_verify_current_daewoon` — 현재나이→현재대운 간지 【P0】

**검증 대상:** '현재 대운은 갑오' / '약 19세…대운 갑오' 단정이 birth_date로 계산한 현재대운과 일치하는지. **대운 목록 나열('11~20 갑오')에는 절대 발화 금지** — 나열은 정상, V1 관할.

**정답 계산:**
```python
from datetime import date
bd = date.fromisoformat(chart_json["input"]["birth_date"])   # 또는 solar_date
age = (date.today() - bd).days / 365.25
ci = max(i for i,e in enumerate(entries) if e["start_age"] <= age)
expected = entries[ci]["pillar"]  # {stem,branch}
```

**anchor_strategy:** 두 정규식, 반드시 '현재'/'약 N세' 문맥어가 40자 이내 선행:
```python
# (1) 현재대운 직접형
r"현재\s*(?:의\s*)?대운[은는이가:\s·,()（）]*(" + _DW_GANJI + r")"
# (2) age→ganji 페어형
r"(?:현재\s*)?(?:약\s*)?(\d{1,3})\s*세[^\n]{0,40}?대운[^\n]{0,8}?(" + _DW_GANJI + r")"
```

**오탐 가드:**
1. **'현재'/'약 N세' 근접(40자) 필수** — 'range:ganji 콜론 나열'은 이 문맥어가 없어 자동 제외(V1과 분리).
2. `birth_date` 없으면 skip.
3. (2)형에서 N이 start_age 구간에 안 맞으면 별도 플래그(나이 자체 오류).
4. 간지가 대운목록에 없으면 `_verify_daewoon`이 먼저 잡음 → skip.

**배선:** `_bad`의 `chart_json is not None` 블록.

---

### V5. `_scrub_stale_year_ganji` 일반화 — 명시연도↔세운 간지 【P1】

**이것은 신규 검증기가 아니라 기존 스크러버(1101) 버그 수정이다.** 재생성 트리거 불필요(순수 달력조회에 LLM 재롤은 과함).

**현재 결함(실측 재현):**
- (C) '2028년 계축'(오답, 년접미 없음) → **완전 무검증 통과** [갭]
- (D) '2030년은 경술년'(정답) → '2030년은 올해이라'로 **오파괴** [능동 손상 버그]
- 원인: allowed 집합을 `{올해, 내년}` 2개로 하드코딩(`_allowed_year_ganji`:1047).

**수정:** allowlist 방식 → **매치된 실제 연도의 세운을 계산해 결정적 교정**:
```python
for m in re.finditer(r"((?:19|20)\d{2})\s*년[^0-9]{0,6}?(" + _KO_GANJI + r")", text):
    y, claimed = int(m.group(1)), m.group(2)
    canon = _year_ko_hj(y)[0]           # 그 연도의 진짜 세운(한글)
    if normalize(claimed) != canon:
        text = replace(claimed → canon) # '올해' 중화가 아니라 정답 간지로 교정
```

**오탐 가드:** 간지 charset은 일반어와 disjoint('자축인묘…'), '숫자4+년' 앵커가 강해 오탐 ≈0. 과거연도(`y<cur`)는 회고차단 정책 유지. '월' 동반은 `_verify_month_ganji` 관할이므로 '연 전용'으로 스코프 분리.

**주의:** 이건 '연도↔간지' 축만 담당. 실측의 '2027 정미 대운'은 **세운↔대운 라벨 혼동**이며 `_verify_daewoon`이 이미 잡음(정미∉대운목록). 별개.

---

### V8. `_verify_ganji_element` 앵커 확장 — 간지 오행 【P1】

**신규 아님 — 기존 정규식(784-789) 확장.** 실측 8문구 중 케이스 #3만 매칭, 나머지 MISS(실증). 원인:
- `_ELEM_CLAIM = ([목화토금수])기`가 '화기**운**(火氣運)'의 '운'+괄호에서 인접성 깨짐.
- '화(火)의 기운이 강합니다' 형태 미커버.
- `_STRONG_WORD`에 '강하게/강화' 없음.

**수정:**
```python
_ELEM_CLAIM = r"([목화토금수])(?:기운|기|\([木火土金水]\)\s*의\s*기운)"  # '화기운','화(火)의 기운' 흡수
_STRONG_WORD = r"...|강하게|강화"                                       # 추가
```
정답출처 `ganji_allowed_elements`는 그대로. `_POS_GAP`(궁위어·조사만, 문장경계 차단)은 유지해 '화기운이 강하게 작용하여…갑오 대운'(문장 넘어감)은 확장 후에도 unmatched → FP 낮음.

---

### V9. `_verify_current_age` — 현재 만나이 재서술 【P1】

**정답:** `int((date.today() - birth_date).days / 365.25)`.

**anchor_strategy(현재나이 단정에만):**
```python
r"현재\s*(?:약\s*)?(\d{1,3})\s*세"                     # '현재 약 19세'
r"(\d{1,3})\s*세\s*(?:의\s*)?(?:고등학생|중학생|대학생|직장인|미취학|청년|중년|노년)"  # 생애단계 동반
```

**오탐 가드(필수):**
1. 매치 직전 30자에 '대운수' 있으면 skip.
2. `N~M세`/`N세부터`/`N세까지`/`N세에 시작` 범위·경계 문맥이면 skip(부정 룩어라운드).
3. **±1 톨러런스** — '약 N세' 근사 + int 절삭 → `abs(claimed-truth)<=1`이면 통과. (없으면 오탐 급증)
4. 소수점 포함 숫자('0.7세'=대운수) skip.

---

### V4. `_verify_gongmang` — 공망 2지지 【P1】

**정답:** `set(chart_json["gongmang"])` (한자 2개).

**anchor_strategy — '식별 단정'에만 좁게:**
- '공망' 뒤 10~14자 창에서 계사(은/는/:/에 해당) 뒤 **지지 2개 연접**(한글 또는 한자, 연결어 와/과/·/, 허용, 괄호형 포함) 포착.
- **지지 2개 모두 포착될 때만 판정**(0/1개는 수식어 용법 → skip, 1차 FP 방어선).
- 포착 `{A,B}` vs `set(gongmang)` 순서무관 비교, 불일치 플래그.

**오탐 가드:** 'X가 공망이면→효과'(신살8.txt 다수) 수식어 문장 배제 — 앵커 좌측 8자에 궁위·신살어(장성/반안/역마/화개/일지/식신) 있으면 skip. '~세 공망'·'인묘 대운은 공망' 구간주장 skip(대운 검증 관할).

---

### V7. `_verify_daewoon_direction` — 대운 순/역행 【P1】

**정답:** `chart_json["daewoon"]["direction"]` (forward↔순행, backward↔역행). **성별 재계산 불요** — 직렬화값 직접 대조.

**anchor_strategy(구현 5줄):**
```python
r"대운[은는이가의\s:·,，()（）]*(순행|역행)"          # 대운→방향
r"(순행|역행)\s*(?:하[며면고는]|합?니?다)?[^。.\n]{0,6}대운"  # 방향→대운
```
**오탐 가드:** '대운' 앵커 필수('일이 역행' 은유 제외), 방향어-대운 사이 문장부호 없이 6자 이내, 부정어('아니라/아닌') 창 스킵, '세운/월운'에 붙은 방향 제외. 방향은 명식 고정값이라 과거필터 불필요.

---

### V10. 궁합 관계 검증기 3종 【P1】 (`compat_service.py`)

궁합 경로(compat_service:479)는 `_verify_branches`+`_verify_day_stem_multi`만 돌아 **관계 라벨(합/충/삼합)은 전혀 미검증**. `a_chart_json`/`b_chart_json`에서 두 일지/일간 확보 가능.

- **V10a 일지 관계:** `_score_day_branch` → 육합/삼합(반합)/충 5클래스. 앵커=**위치어(일지/부부궁/배우자궁) 게이트 + 두 일지 글자 공출현 + 관계어**. 세 조건 동시. 육합↔충, 육합↔삼합 뒤바뀌면 플래그. 정답이면 통과(엔진이 프롬프트 주입). 午未 화/토 학설분기는 오행값이라 **관계클래스만 검증**.
- **V10b 일간 천간합/충:** `STEM_COMBINATIONS`/`STEM_CONFLICTS`. 앵커=**두 일간 동시등장 문장 + 합/충 주장어**. 지지 문맥어(지지/일지/육합/삼합) 있으면 skip(오행합 혼동 차단).
- **V10c 상호 십성:** `compute_ten_god(a,b)`/`(b,a)`. 앵커=**궁합 경로 게이트 + 방향표지(상대를 보는/서로/A→B) + 십성어**. bare 십성어 금지(단일명식 육친서술이 십성어로 도배됨). 방향 불명이면 두 값 union 대조.

---

### V11. 택일 황도/건제 【P1】 (`tool_service.py`)

**정답:** 테이블 재구현 금지. `row.result_json.best/avoid`의 각 date에 `hwangdo`/`geonje` 문자열이 이미 결정계산됨 → **조인**.

**anchor:** ① 답변에서 result_json에 존재하는 날짜 토큰 찾기 → ② 그 토큰 뒤 40자 창에서만 신이름(청룡/명당/…/구진)+황흑, 또는 건제(한자 `[建除滿平定執破危成收開閉]` 또는 한자병기)만 포획 → ③ result_json 값과 불일치 시 플래그.

**오탐 가드:** result_json 날짜에 근접한 경우만(떠도는 '명당'·'개운' 일반어 배제), 신이름은 황/흑·길/흉 술어 동반 시만, 건제는 한자병기 형태만.

---

### V12·V13. 작명 【P1】 (`tool_service.py`)

- **V12 수리 4격(개명 전용):** brief에 '원격(元) 22(흉)…' 주입됨. 앵커=`(원격|형격|이격|정격)…(\d+)획`+같은 문장 40자 내 `(길|흉|평)`. brief의 격별 num/grade와 대조. 격라벨 3요소 동시근접일 때만. 작명/아호는 등급만 주입(격↔획수 못 맞춤)이라 **초기 제외**.
- **V13 자원오행:** `result_json.candidates[*].{given,elements}`로 `{글자:정답오행}` 사전. 앵커=**'자원오행' 문맥(40자)** 안에서 `한자…[목화토금수]`. **발음오행 배제 필수**(같은 문장에 '발음/소리/초성' 있으면 skip — 潤 자원=수 vs 발음=토, 최대 오탐원). '부족/보완/사주오행/수리'도 배제. 후보에 없는 한자·성씨는 미검증.

---

## 4. Drop 처리 — 왜 안 하는가 (기록)

| 클래스 | drop 사유 |
|---|---|
| **세운→대운 혼동** (2027 정미 대운) | 이미 `_verify_daewoon` 역방향 앵커가 잡음(정미∉대운목록). 잔여 갭('대운' 토큰 없는 서술)은 좁은 앵커 불가·정상 세운 언급에 오탐 폭증 |
| **오행 개수/강약/부재/균형/조화** (전부) | 엔진은 count만 알고 '강/약/부족' 임계값이 코드에 없음(비결정). `determine_strength`는 일간 하나만. count==0은 '없다'의 관용적 미약용법과 겹쳐 오탐. 결정적 부분(간지→오행)은 `_verify_ganji_element` 관할 |
| **오행-장부 건강 연결** | 오행-장부 매핑(金=肺)은 엔진 미계산 외부지식(비결정). '없다'→count==0만 좁게 가능하나 실측 환각은 대부분 '부족/약' 형태라 못 잡음 |
| **성별별 육친 매핑, 지지 정기 십성** | 정답표는 결정적이나 실측이 '궁위론' 산문('일지의 편인이 배우자에 영향')이라 정체성 단정과 처소서술 정규분리 불가. 지지는 지장간 여기/중기 십성도 정당 → 정기-only 대조는 정상서술 오탐 |
| **나이→연도 역산, 생애단계 라벨, 세운↔나이 역검증** | 만/세는나이 ±1로 결정성 부재(해석성). `_life_stage_ko` 경계 오분류(19세→고등학생인데 대학2학년) → 엔진 라벨을 정답 삼으면 LLM 정답을 오탐 |
| **띠(년지→동물)** | 결정적이나 프롬프트 미주입·실측 0건, 동물 한글자(용/말/소) 오탐 폭발, 캐주얼 비유라 severity 낮음 |
| **억부방향·득령실령·월지본기·조후용신·보조용신·사령천간** | 정용신은 `_verify_yongsin`이 이미 full 커버. 나머지는 프롬프트로 주입돼 LLM 복사(독립환각 드묾) 또는 코퍼스 인용 오탐 |
| **궁합 점수/등급/기여도/신살 감점 델타** | 대부분 프롬프트에 정답 그대로 주입돼 재서술 드묾. 점수 숫자 대조는 반올림·우연일치로 FP high. contributions/weights는 LLM에 주입조차 안 됨 |
| **궁합 형/파/해/도화/암합** | 엔진이 '있을 때만' 주입(없음 신호 없음). 산문이 지지쌍을 안 밝혀 대조불가. '충/파/해' 토큰 일반어와 과부하 충돌 |
| **택일 손없는날/28수/회피일** | 날짜별 결정값이 brief에 불리언/배지로 주입돼 LLM 전사(환각 희박). 프론트 배지로 노출. date-attribution 오탐 지뢰밭 |
| **일진(오늘) 간지, 발음오행** | 프롬프트 가드로 억제·실측 0건. birth 일주/메타문구/택일 후보와 앵커 충돌, 산문 패러프레이즈로 좁은 앵커 불가 |

---

## 5. 가장 먼저 구축할 3개

### ① V1 `_verify_daewoon_age_range` — 대운 나이구간↔간지
- **근거:** 감사에서 **가장 자주 반복 지목된 진짜 갭**(7개 클래스가 이걸 가리킴). `_verify_daewoon`은 간지 멤버십만 봐 나이구간을 **버린다**(코드 확인). 정답이 `entries[].start_age`만으로 **완전 결정적**(birth_date조차 불요), 앵커가 좁고(세 단위+대운목록 존재+±1 톨러런스), 실측 관측됨('11~20 갑오'). 심각도 high(대운은 10년 인생 프레임 → 틀리면 이후 시기별 서술 연쇄오염).

### ② V3 `_verify_pillar_ganji` — 주柱어+간지 재서술
- **근거:** 실측 답변의 **지배적 명식 재서술 패턴**('일주 신미', '월주 병신' 62·63·117·174·179행)을 기존 `_verify_branches`가 **100% MISS**(테스트 실증 — '지지' 위치어만 앵커). 정방향 앵커(柱어→간지)는 스트레스테스트에서 오탐 ≈0. 명식 4주는 화면 표와 정면 대조되는 헤드라인 값이라 심각도 high. 구현 저렴(기존 `_DW_GANJI`·`pillars` 재사용).

### ③ V2 `_verify_current_daewoon` — 현재나이→현재대운 간지
- **근거:** 실측 최초 관측 환각('현재 약 19세→갑오 대운')의 정중앙. 정답이 `birth_date`(chart_json에 실존 — 감사의 '불가' 판정은 오류)로 **완전 결정적**. '현재/약 N세' 40자 근접 앵커로 V1의 '목록 나열'과 깔끔히 분리돼 오탐 통제됨. 대운 오라벨은 이후 모든 진로/시험 조언의 근거라 사용자 신뢰 직접 훼손.

**공통 착수 메모:** 세 검증기 모두 `chart_json`만으로 동작(V2만 `input.birth_date` 사용) → 시그니처 확장 없이 `_verify_myeongsik`(863)과 `_correct_branches._bad`(943, `chart_json is not None` 블록)에 그대로 편입. `_myeongsik_truth`(887)에 년주/월주 간지 + 현재대운 `X(N~M세)`를 병기하면 교정 프롬프트가 강해진다. 병행 권장: `_build_saju_summary`에 **전체 `entries[]`를 주입**(현재 first 엔트리만)하면 환각 자체가 줄어 재생성 빈도가 낮아진다.

---

**참고 — 대상 파일 경로(절대):**
- 단일명식 검증기: `D:\saju_agent\backend\app\services\chat_service.py` (feat 브랜치, 2818줄)
- 궁합: `D:\saju_agent\backend\app\services\compat_service.py`
- 작명/택일: `D:\saju_agent\backend\app\services\tool_service.py`
- 엔진 결정값: `D:\saju_agent\backend\app\saju\{daewoon,yongsin,sinsal,compatibility,taekil,naming,constants}.py`

⚠️ **주의:** 현재 워크트리(`elated-chaplygin-392075`)의 `chat_service.py`는 594줄짜리 화석(stub)이다. 실제 작업은 `feat/claude-refine-and-compatibility` 브랜치의 2818줄 파일에서 해야 한다(메모리 `ui-redesign-2030`·`tarot-menu-plan`의 "main은 화석, 실코드는 feat 브랜치" 경고와 일치). 착수 전 브랜치 확인 필수.