/** 사주 명식(결정적 계산값)에서 시각화용 지표를 산출 — 십성 분포·오행 균형·현재 대운.
 *  LLM/환각 없이 chart_json(ten_gods·wuxing·daewoon·solar_date)만으로 계산한다(참고용 경향치).
 */
import type { Chart } from "../components/SajuChart";

export type TenGodGroup = "비겁" | "식상" | "재성" | "관성" | "인성";

// 십성(한자/한글) → 5분류. day_stem(일간=본인)은 ten_gods에 없음(=비견 기준).
const GROUP: Record<string, TenGodGroup> = {
  比肩: "비겁", 劫財: "비겁", 食神: "식상", 傷官: "식상",
  正財: "재성", 偏財: "재성", 正官: "관성", 偏官: "관성", 正印: "인성", 偏印: "인성",
  비견: "비겁", 겁재: "비겁", 식신: "식상", 상관: "식상",
  정재: "재성", 편재: "재성", 정관: "관성", 편관: "관성", 정인: "인성", 편인: "인성",
};

/** 명식 표면 7자리(년·월·시 천간 + 년·월·일·시 지지)의 십성 5분류 개수. */
export function tenGodGroups(chart: Chart): Record<TenGodGroup, number> {
  const g = chart.ten_gods;
  const out: Record<TenGodGroup, number> = { 비겁: 0, 식상: 0, 재성: 0, 관성: 0, 인성: 0 };
  if (!g) return out;
  [g.year_stem, g.month_stem, g.hour_stem, g.year_branch, g.month_branch, g.day_branch, g.hour_branch]
    .forEach((v) => { const k = v ? GROUP[v] : undefined; if (k) out[k] += 1; });
  return out;
}

// 개수(0~5+) → 0~100 점수(읽기 좋은 스프레드, 결정적). 0→25, 1→43, 2→61, 3→79, 4→97.
const sc = (n: number) => Math.max(0, Math.min(100, Math.round(25 + n * 18)));

export type Trait = { key: string; label: string; value: number };

/** 십성 분포로 본 6가지 기질 축(0~100).
 *  label 은 ko 내부값(참고용) — 화면 표기는 SajuChart(TraitRadar)가 key 로 chart.trait_{key} 로케일 매핑. */
export function traits(chart: Chart): Trait[] {
  const c = tenGodGroups(chart);
  return [
    { key: "drive", label: "자기주도", value: sc(c.비겁) },
    { key: "express", label: "표현력", value: sc(c.식상) },
    { key: "money", label: "재물감각", value: sc(c.재성) },
    { key: "duty", label: "책임감", value: sc(c.관성) },
    { key: "learn", label: "배움", value: sc(c.인성) },
    { key: "social", label: "관계유연", value: sc((c.비겁 + c.식상) / 2) },
  ];
}

/** 오행 균형도(0~1) — 변동계수가 작을수록(고를수록) 1에 가깝다. */
function wuxingBalance(chart: Chart): number {
  const w = chart.wuxing;
  const arr = [w.wood, w.fire, w.earth, w.metal, w.water];
  const mean = arr.reduce((a, b) => a + b, 0) / 5;
  if (mean <= 0) return 0.5;
  const sd = Math.sqrt(arr.reduce((a, b) => a + (b - mean) ** 2, 0) / 5);
  return Math.max(0, Math.min(1, 1 - sd / mean / 1.4));
}

export type Domain = { label: string; value: number };

/** 영역별 운세 비중(0~100, 높은 순). 백엔드가 보낸 '올해 세운 반영' 값이 있으면 그걸 쓰고,
 *  없으면(옛 세션 등) natal 분포로 폴백 계산.
 *  label 은 한국어 데이터 키(백엔드 계약) — 화면 표기는 SajuChart 가 chart.domain 으로 로케일 매핑. */
export function domains(chart: Chart): Domain[] {
  if (chart.domain_scores && chart.domain_scores.length) return chart.domain_scores;
  const c = tenGodGroups(chart);
  const health = Math.round(35 + wuxingBalance(chart) * 60);
  return [
    { label: "직업운", value: sc(c.관성 + c.인성 * 0.5) },
    { label: "재물운", value: sc(c.재성) },
    { label: "대인운", value: sc((c.비겁 + c.식상) / 2) },
    { label: "연애운", value: sc((c.재성 + c.관성) / 2) },
    { label: "건강운", value: Math.max(0, Math.min(100, health)) },
  ].sort((a, b) => b.value - a.value);
}

// (구) seunLabel 은 ko 하드코딩이라 제거 — 세운 소제목은 SajuChart 가 chart.seun_label 로케일 키로 직접 구성.

/** 현재 대운 인덱스(entries 중) — 생일(solar_date)로 만 나이 산출. 없으면 -1. */
export function currentDaewoonIndex(chart: Chart): number {
  const entries = chart.daewoon?.entries || [];
  if (!entries.length || !chart.solar_date) return -1;
  const b = new Date(`${chart.solar_date}T00:00:00`);
  if (isNaN(b.getTime())) return -1;
  const age = (Date.now() - b.getTime()) / (365.25 * 24 * 3600 * 1000);
  let idx = -1;
  entries.forEach((e, i) => { if (e.start_age <= age) idx = i; });
  return idx;
}
