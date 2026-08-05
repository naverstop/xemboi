/** 사주명식 시각화 (원광만세력 v4.0.0 스타일 단순화). 라벨·독음은 로케일(ko/vi). */
import { useMemo } from "react";
import { traits, domains, currentDaewoonIndex, type Trait } from "../lib/sajuMetrics";
import { useTranslation, Trans } from "react-i18next";

type Pillar = { stem: string; branch: string };
type Wuxing = { wood: number; fire: number; earth: number; metal: number; water: number };
type DaewoonEntry = { start_age: number; pillar: Pillar; direction: string };
type Daewoon = { direction: string; start_age: number; entries: DaewoonEntry[] };

type TenGods = {
  year_stem: string; month_stem: string; hour_stem: string | null;
  year_branch: string; month_branch: string; day_branch: string; hour_branch: string | null;
};

export type Chart = {
  pillars: { year: Pillar; month: Pillar; day: Pillar; hour: Pillar | null };
  wuxing: Wuxing;
  day_master_element: string;
  day_master_strength: string;
  daewoon: Daewoon | null;
  hidden_stems?: Record<string, string[]>;
  ten_gods?: TenGods;
  twelve_life?: Record<string, string>;     // 위치(년/월/일/시) → 십이운성
  twelve_sinsal?: Record<string, string>;   // 위치 → 십이신살
  gongmang?: string[];                       // 공망 2지지
  napeum?: Record<string, string>;           // 위치 → 납음(納音)
  saryeong?: string;                          // 사령(司令) 천간
  johu_yongsin?: JohuYongsin | null;          // 조후용신(궁통보감 일간×월지)
  solar_date?: string;
  lunar_date?: string;
  // 영역별 운세 비중(올해 세운 반영) — 백엔드 결정적 계산값. 없으면 프론트가 natal로 폴백.
  domain_scores?: { label: string; value: number }[];
  seun?: { stem: string; branch: string; stem_ko: string; branch_ko: string; year: number };
};

type JohuYongsin = {
  primary: string;            // 정조후용신 천간 한자
  supporting: string[];       // 보조용신 천간들
  season: string;             // 봄/여름/가을/겨울
  climate: string;            // 寒(겨울)/暖(여름)/평
  is_climate_priority: boolean;
  note: string;               // 근거 한 줄
  source: string;
};

// 로케일 무관 내부 코드는 오행 한자(木火土金水)로 통일 — 표시 독음은 로케일 매핑(chart.wuxing).
// 전통 오행 5색 (하늘도마뱀 만세력 기준): 木녹·火적·土황·金백·水흑.
const WX_COLOR: Record<string, string> = {
  木: "#2fa84f",   // 木 = 청/녹
  火: "#E11D2E",   // 火 = 적
  土: "#F2C200",   // 土 = 황
  金: "#ffffff",   // 金 = 백
  水: "#33373d",   // 水 = 흑(가독 위해 약간 누그러뜨림)
};
// 배경 대비 글자색 (土·金=어둡게, 나머지 흰색)
const WX_TEXT: Record<string, string> = {
  木: "#ffffff",
  火: "#ffffff",
  土: "#1f2937",
  金: "#1f2937",
  水: "#ffffff",
};
// 흰 배경(金)은 배경과 섞이므로 또렷한 실선 박스로 구분
const WX_BORDER: Record<string, string> = { 金: "1.5px solid #8b94a0" };

const STEM_WX: Record<string, string> = {
  甲: "木", 乙: "木", 丙: "火", 丁: "火", 戊: "土", 己: "土",
  庚: "金", 辛: "金", 壬: "水", 癸: "水",
};
const BRANCH_WX: Record<string, string> = {
  寅: "木", 卯: "木", 巳: "火", 午: "火", 辰: "土", 戌: "土", 丑: "土", 未: "土",
  申: "金", 酉: "金", 亥: "水", 子: "水",
};
// 백엔드 day_master_element(영문) → 오행 한자 코드
const EL_FROM_EN: Record<string, string> = {
  wood: "木", fire: "火", earth: "土", metal: "金", water: "水",
};

type StrMap = Record<string, string>;

function PillarCell({ label, pillar, stemGod, branchGod, hidden, lifeStage, sinsal }: {
  label: string; pillar: Pillar | null;
  stemGod?: string; branchGod?: string; hidden?: string[];
  lifeStage?: string; sinsal?: string;
}) {
  const { t: tr, i18n } = useTranslation();
  const vi = i18n.language.startsWith("vi");
  const stemR = tr("chart.stem", { returnObjects: true }) as StrMap;
  const branchR = tr("chart.branch", { returnObjects: true }) as StrMap;
  const lifeR = tr("chart.life", { returnObjects: true }) as StrMap;
  const sinsalR = tr("chart.sinsal", { returnObjects: true }) as StrMap;
  if (!pillar) {
    return (
      <div className="pillar empty">
        <div className="pillar-label">{label}</div>
        <div className="pillar-god">{tr("chart.hour_unknown")}</div>
        <div className="pillar-stem">?</div>
        <div className="pillar-branch">?</div>
        <div className="pillar-god" />
        <div className="pillar-hidden" />
        <div className="pillar-extra" />
        <div className="pillar-extra" />
      </div>
    );
  }
  const sWx = STEM_WX[pillar.stem] || "土";
  const bWx = BRANCH_WX[pillar.branch] || "土";
  return (
    <div className="pillar">
      <div className="pillar-label">{label}</div>
      <div className="pillar-god top">{stemGod || ""}</div>
      <div className="pillar-stem" style={{ background: WX_COLOR[sWx], color: WX_TEXT[sWx], border: WX_BORDER[sWx] }}>
        <div className="ch">{vi ? (stemR[pillar.stem] || pillar.stem) : pillar.stem}</div>
        <div className="ko">{vi ? "" : stemR[pillar.stem]}</div>
      </div>
      <div className="pillar-branch" style={{ background: WX_COLOR[bWx], color: WX_TEXT[bWx], border: WX_BORDER[bWx] }}>
        <div className="ch">{vi ? (branchR[pillar.branch] || pillar.branch) : pillar.branch}</div>
        <div className="ko">{vi ? "" : branchR[pillar.branch]}</div>
      </div>
      <div className="pillar-god bot">{branchGod || ""}</div>
      <div className="pillar-hidden">{(hidden || []).map((s) => (vi ? (stemR[s] || s) : s)).join(" ")}</div>
      <div className="pillar-extra" title={tr("chart.life_tip")}>{lifeStage ? (lifeR[lifeStage] || lifeStage) : ""}</div>
      <div className="pillar-extra sinsal" title={tr("chart.sinsal_tip")}>{sinsal ? (sinsalR[sinsal] || sinsal) : ""}</div>
    </div>
  );
}

/** 기질 6축 레이더(십성 분포 기반, 결정적). SVG 인라인 — 외부 의존 0, 테마색은 CSS 변수. */
function TraitRadar({ data }: { data: Trait[] }) {
  const { t: tr } = useTranslation();
  const cx = 100, cy = 92, R = 60, n = data.length;
  const ang = (i: number) => ((-90 + (360 / n) * i) * Math.PI) / 180;
  const pt = (i: number, r: number): [number, number] => [cx + Math.cos(ang(i)) * r, cy + Math.sin(ang(i)) * r];
  const poly = (r: number) => data.map((_, i) => pt(i, r).join(",")).join(" ");
  const valPoly = data.map((d, i) => pt(i, (R * d.value) / 100).join(",")).join(" ");
  return (
    <svg className="tr-radar" viewBox="0 0 200 190" role="img" aria-label={tr("chart.trait_aria")}>
      {[0.25, 0.5, 0.75, 1].map((f) => <polygon key={f} className="tr-ring" points={poly(R * f)} />)}
      {data.map((_, i) => { const [x, y] = pt(i, R); return <line key={i} className="tr-axis" x1={cx} y1={cy} x2={x} y2={y} />; })}
      <polygon className="tr-val" points={valPoly} />
      {data.map((d, i) => {
        const [lx, ly] = pt(i, R + 15);
        return (
          <text key={d.key} className="tr-label" x={lx} y={ly - 3} textAnchor="middle">
            {/* label(ko 내부값) 대신 key 기반 로케일 라벨 — chart.trait_{key} */}
            {tr(`chart.trait_${d.key}`)}<tspan className="tr-num" x={lx} dy="12">{d.value}</tspan>
          </text>
        );
      })}
    </svg>
  );
}

export default function SajuChart({ chart }: { chart: Chart }) {
  const { t: tr, i18n } = useTranslation();
  const vi = i18n.language.startsWith("vi");
  const stemR = tr("chart.stem", { returnObjects: true }) as StrMap;
  const branchR = tr("chart.branch", { returnObjects: true }) as StrMap;
  const wuxingR = tr("chart.wuxing", { returnObjects: true }) as StrMap;
  const tengodR = tr("chart.tengod", { returnObjects: true }) as StrMap;
  const napeumR = tr("chart.napeum", { returnObjects: true }) as StrMap;
  const strengthR = tr("chart.strength", { returnObjects: true }) as StrMap;
  const domainR = tr("chart.domain", { returnObjects: true }) as StrMap;   // 영역 라벨(직업운…) → 로케일
  // 십성 한자 → 로케일 독음
  const tg = (v: string | null | undefined) => (v ? tengodR[v] || v : "");

  const traitData = useMemo(() => traits(chart), [chart]);
  const domainData = useMemo(() => domains(chart), [chart]);
  const curDw = useMemo(() => currentDaewoonIndex(chart), [chart]);
  // 세운 소제목 — ko " (2026 세운 병오)" / vi " (2026 Tuế vận Bính Ngọ)". 언어 전환 즉시 반영되게 렌더 시 계산.
  const seunTxt = chart.seun
    ? tr("chart.seun_label", {
        year: chart.seun.year,
        ganji: vi
          ? `${stemR[chart.seun.stem] || chart.seun.stem_ko} ${branchR[chart.seun.branch] || chart.seun.branch_ko}`
          : `${chart.seun.stem_ko}${chart.seun.branch_ko}`,
      })
    : "";
  // 오행 개수는 사용자가 눈으로 읽는 '팔자 8글자'(천간4+지지4) 기준으로 센다.
  // [2026-07-22 운영자 지적] 종전엔 chart.wuxing(지장간까지 합산한 full, 합 14)을 그려 명식표와
  //   어긋났다 — pillars 에서 직접 세므로 옛 세션(저장 chart_json)도 바로 맞는 값이 나온다.
  //   ⚠️ 신강/신약은 지장간 통근 반영이라 백엔드가 계속 full 로 판정한다.
  //   (vi 렌더 호환: ko·el 두 키 모두 제공 — el은 한자, 라벨은 wuxingR[el]로 로케일 독음)
  const wxArr = useMemo(() => {
    const cnt: Record<string, number> = { 목: 0, 화: 0, 토: 0, 금: 0, 수: 0 };
    const p = chart.pillars;
    for (const pil of [p.year, p.month, p.day, p.hour]) {
      if (!pil) continue;                       // '시 모름'이면 시주 제외(합 6)
      const s = STEM_WX[pil.stem];
      const b = BRANCH_WX[pil.branch];
      if (s) cnt[s] += 1;
      if (b) cnt[b] += 1;
    }
    const total = Math.max(1, cnt.목 + cnt.화 + cnt.토 + cnt.금 + cnt.수);
    const HJ: Record<string, string> = { 목: "木", 화: "火", 토: "土", 금: "金", 수: "水" };
    return (["목", "화", "토", "금", "수"] as const).map((ko) => ({
      ko, el: HJ[ko], v: cnt[ko], pct: (cnt[ko] / total) * 100,
    }));
  }, [chart.pillars]);

  const g = chart.ten_gods;
  const lf = chart.twelve_life;
  const ss = chart.twelve_sinsal;
  // 지장간은 위치 라벨(년지/월지/일지/시지) 키로 제공됨 (백엔드 데이터 키)
  const h = (label: string) => (chart.hidden_stems?.[label] || []);
  const dmEl = EL_FROM_EN[chart.day_master_element] || "土";

  return (
    <div className="saju-chart">
      <div className="pillar-row">
        {/* 위치 키("시"/"일"/"월"/"년", "시지"…)는 백엔드 데이터 키라 그대로 사용 */}
        <PillarCell label={tr("chart.pillar_hour")} pillar={chart.pillars.hour}
          stemGod={tg(g?.hour_stem)} branchGod={tg(g?.hour_branch)} hidden={h("시지")}
          lifeStage={lf?.["시"]} sinsal={ss?.["시"]} />
        <PillarCell label={tr("chart.pillar_day")} pillar={chart.pillars.day}
          stemGod={tr("chart.day_master_god")} branchGod={tg(g?.day_branch)} hidden={h("일지")}
          lifeStage={lf?.["일"]} sinsal={ss?.["일"]} />
        <PillarCell label={tr("chart.pillar_month")} pillar={chart.pillars.month}
          stemGod={tg(g?.month_stem)} branchGod={tg(g?.month_branch)} hidden={h("월지")}
          lifeStage={lf?.["월"]} sinsal={ss?.["월"]} />
        <PillarCell label={tr("chart.pillar_year")} pillar={chart.pillars.year}
          stemGod={tg(g?.year_stem)} branchGod={tg(g?.year_branch)} hidden={h("년지")}
          lifeStage={lf?.["년"]} sinsal={ss?.["년"]} />
      </div>

      {chart.napeum && (chart.napeum["시"] || chart.napeum["일"] || chart.napeum["월"] || chart.napeum["년"]) && (
        <div className="chart-napeum">{tr("chart.napeum_label")}
          {["시", "일", "월", "년"].map((k) => chart.napeum?.[k] ? <span key={k} className="np">{napeumR[chart.napeum[k]] || chart.napeum[k]}</span> : null)}
        </div>
      )}
      {chart.saryeong && (
        <div className="chart-gongmang">{tr("chart.saryeong_label")} <b>{vi ? (stemR[chart.saryeong] || chart.saryeong) : `${chart.saryeong}(${stemR[chart.saryeong] || ""})`}</b></div>
      )}
      {chart.gongmang && chart.gongmang.length > 0 && (
        <div className="chart-gongmang">{tr("chart.gongmang_label")} <b>{chart.gongmang.map((c) => (vi ? (branchR[c] || c) : c)).join("·")}</b></div>
      )}

      <div className="wx-bars">
        {wxArr.map((w) => (
          <div key={w.el} className="wx-bar">
            <span className="wx-label" style={{ color: WX_COLOR[w.el] }}>{wuxingR[w.el]}</span>
            <div className="wx-fill-wrap">
              <div className="wx-fill" style={{ width: `${w.pct}%`, background: WX_COLOR[w.el] }} />
            </div>
            <span className="wx-num">{w.v}</span>
          </div>
        ))}
      </div>

      <div className="day-master-info">
        {tr("chart.day_master_label")} <strong>{vi ? stemR[chart.pillars.day.stem] : `${chart.pillars.day.stem}(${stemR[chart.pillars.day.stem]})`}</strong> ·
        {tr("chart.wuxing_label")} <span style={{ color: WX_COLOR[dmEl] }}>{wuxingR[dmEl]}</span> ·
        {tr("chart.strength_label")} <strong>{strengthR[chart.day_master_strength] || chart.day_master_strength}</strong>
      </div>

      {chart.johu_yongsin && (() => {
        const ys = chart.johu_yongsin!;
        const pWx = STEM_WX[ys.primary] || "土";
        return (
          <div className="chart-yongsin" title={ys.note}>
            {tr("chart.yongsin_label")}
            <b className="ys-chip" style={{ background: WX_COLOR[pWx], color: WX_TEXT[pWx], border: WX_BORDER[pWx] }}>
              {vi ? (stemR[ys.primary] || ys.primary) : `${ys.primary}(${stemR[ys.primary] || ""})`}
            </b>
            {ys.supporting.length > 0 && (
              <span className="ys-sup">{tr("chart.yongsin_support")} {ys.supporting.map((s) => (vi ? (stemR[s] || s) : `${s}(${stemR[s] || ""})`)).join("·")}</span>
            )}
            {ys.is_climate_priority && <span className="ys-badge">{tr("chart.yongsin_climate")}</span>}
          </div>
        );
      })()}

      {chart.daewoon && chart.daewoon.entries.length > 0 && (
        <div className="daewoon-strip">
          <div className="daewoon-title">
            {tr("chart.daewoon_title", {
              dir: chart.daewoon.direction === "forward" ? tr("chart.daewoon_forward") : tr("chart.daewoon_backward"),
              age: chart.daewoon.start_age.toFixed(1),
            })}
          </div>
          <div className="daewoon-row">
            {chart.daewoon.entries.slice(0, 9).map((d, i) => {
              const sWx = STEM_WX[d.pillar.stem] || "土";
              const bWx = BRANCH_WX[d.pillar.branch] || "土";
              const now = i === curDw;   // 현재 대운 강조('지금' 마커)
              return (
                <div key={d.start_age} className={`dw-cell${now ? " now" : ""}`}>
                  {now && <div className="dw-now">{tr("chart.dw_now")}</div>}
                  <div className="dw-age">{d.start_age}</div>
                  <div className="dw-stem" style={{ background: WX_COLOR[sWx], color: WX_TEXT[sWx], border: WX_BORDER[sWx] }}>{vi ? (stemR[d.pillar.stem] || d.pillar.stem) : d.pillar.stem}</div>
                  <div className="dw-branch" style={{ background: WX_COLOR[bWx], color: WX_TEXT[bWx], border: WX_BORDER[bWx] }}>{vi ? (branchR[d.pillar.branch] || d.pillar.branch) : d.pillar.branch}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 기질 6축 레이더 + 영역별 운세 비중 — 십성·오행 분포 기반(결정적 계산, 참고 경향치) */}
      {chart.ten_gods && (
        <div className="chart-metrics">
          <div className="cm-block">
            <div className="cm-title">{tr("chart.metrics_traits_title")} <span className="cm-sub">{tr("chart.metrics_traits_sub")}</span></div>
            <TraitRadar data={traitData} />
          </div>
          <div className="cm-block">
            <div className="cm-title">{tr("chart.metrics_domains_title")}{seunTxt} <span className="cm-sub">{tr("chart.metrics_domains_sub")}</span></div>
            <div className="dom-bars">
              {domainData.map((d, i) => (
                <div key={d.label} className={`dom-bar${i === 0 ? " top" : ""}`}>
                  {/* label은 백엔드/폴백의 한국어 키 — 표시만 로케일 매핑(미매핑 값은 원값) */}
                  <span className="dom-label">{domainR[d.label] || d.label}</span>
                  <div className="dom-fill-wrap"><div className="dom-fill" style={{ width: `${d.value}%` }} /></div>
                  <span className="dom-num">{d.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 신뢰 배지(Phase4) — 우리의 실제 차별점: 결정적 계산·환각 차단 */}
      <div className="chart-trust">
        <span className="ct-badge">{tr("chart.trust_badge")}</span>
        <span className="ct-tx"><Trans i18nKey="chart.trust_tx" components={{ b: <b /> }} /></span>
      </div>
    </div>
  );
}
