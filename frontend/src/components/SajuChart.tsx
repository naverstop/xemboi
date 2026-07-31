/** 사주명식 시각화 (원광만세력 v4.0.0 스타일 단순화). 라벨·독음은 로케일(ko/vi). */
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

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
  const { t: tr } = useTranslation();
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
        <div className="ch">{pillar.stem}</div>
        <div className="ko">{stemR[pillar.stem]}</div>
      </div>
      <div className="pillar-branch" style={{ background: WX_COLOR[bWx], color: WX_TEXT[bWx], border: WX_BORDER[bWx] }}>
        <div className="ch">{pillar.branch}</div>
        <div className="ko">{branchR[pillar.branch]}</div>
      </div>
      <div className="pillar-god bot">{branchGod || ""}</div>
      <div className="pillar-hidden">{(hidden || []).join(" ")}</div>
      <div className="pillar-extra" title={tr("chart.life_tip")}>{lifeStage ? (lifeR[lifeStage] || lifeStage) : ""}</div>
      <div className="pillar-extra sinsal" title={tr("chart.sinsal_tip")}>{sinsal ? (sinsalR[sinsal] || sinsal) : ""}</div>
    </div>
  );
}

export default function SajuChart({ chart }: { chart: Chart }) {
  const { t: tr } = useTranslation();
  const stemR = tr("chart.stem", { returnObjects: true }) as StrMap;
  const wuxingR = tr("chart.wuxing", { returnObjects: true }) as StrMap;
  const tengodR = tr("chart.tengod", { returnObjects: true }) as StrMap;
  const napeumR = tr("chart.napeum", { returnObjects: true }) as StrMap;
  const strengthR = tr("chart.strength", { returnObjects: true }) as StrMap;
  // 십성 한자 → 로케일 독음
  const tg = (v: string | null | undefined) => (v ? tengodR[v] || v : "");

  const wxArr = useMemo(() => {
    const w = chart.wuxing;
    const total = Math.max(1, w.wood + w.fire + w.earth + w.metal + w.water);
    return [
      { el: "木", v: w.wood, pct: (w.wood / total) * 100 },
      { el: "火", v: w.fire, pct: (w.fire / total) * 100 },
      { el: "土", v: w.earth, pct: (w.earth / total) * 100 },
      { el: "金", v: w.metal, pct: (w.metal / total) * 100 },
      { el: "水", v: w.water, pct: (w.water / total) * 100 },
    ];
  }, [chart.wuxing]);

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
        <div className="chart-gongmang">{tr("chart.saryeong_label")} <b>{chart.saryeong}({stemR[chart.saryeong] || ""})</b></div>
      )}
      {chart.gongmang && chart.gongmang.length > 0 && (
        <div className="chart-gongmang">{tr("chart.gongmang_label")} <b>{chart.gongmang.join("·")}</b></div>
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
        {tr("chart.day_master_label")} <strong>{chart.pillars.day.stem}({stemR[chart.pillars.day.stem]})</strong> ·
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
              {ys.primary}({stemR[ys.primary] || ""})
            </b>
            {ys.supporting.length > 0 && (
              <span className="ys-sup">{tr("chart.yongsin_support")} {ys.supporting.map((s) => `${s}(${stemR[s] || ""})`).join("·")}</span>
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
            {chart.daewoon.entries.slice(0, 9).map((d) => {
              const sWx = STEM_WX[d.pillar.stem] || "土";
              const bWx = BRANCH_WX[d.pillar.branch] || "土";
              return (
                <div key={d.start_age} className="dw-cell">
                  <div className="dw-age">{d.start_age}</div>
                  <div className="dw-stem" style={{ background: WX_COLOR[sWx], color: WX_TEXT[sWx], border: WX_BORDER[sWx] }}>{d.pillar.stem}</div>
                  <div className="dw-branch" style={{ background: WX_COLOR[bWx], color: WX_TEXT[bWx], border: WX_BORDER[bWx] }}>{d.pillar.branch}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
