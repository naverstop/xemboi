/** 사주명식 시각화 (원광만세력 v4.0.0 스타일 단순화). */
import { useMemo } from "react";

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

// 전통 오행 5색 (하늘도마뱀 만세력 기준): 木녹·火적·土황·金백·水흑.
const WX_COLOR: Record<string, string> = {
  목: "#2fa84f",   // 木 = 청/녹
  화: "#E11D2E",   // 火 = 적
  토: "#F2C200",   // 土 = 황
  금: "#ffffff",   // 金 = 백
  수: "#33373d",   // 水 = 흑(가독 위해 약간 누그러뜨림)
};
// 배경 대비 글자색 (土·金=어둡게, 나머지 흰색)
const WX_TEXT: Record<string, string> = {
  목: "#ffffff",
  화: "#ffffff",
  토: "#1f2937",
  금: "#1f2937",
  수: "#ffffff",
};
// 흰 배경(金)은 배경과 섞이므로 또렷한 실선 박스로 구분
const WX_BORDER: Record<string, string> = { 금: "1.5px solid #8b94a0" };

// 십성 한자 → 한글
const TEN_GOD_KO: Record<string, string> = {
  正財: "정재", 偏財: "편재", 正官: "정관", 偏官: "편관", 正印: "정인", 偏印: "편인",
  比肩: "비견", 劫財: "겁재", 食神: "식신", 傷官: "상관",
};
const tg = (v: string | null | undefined) => (v ? TEN_GOD_KO[v] || v : "");

const STEM_WX: Record<string, string> = {
  甲: "목", 乙: "목", 丙: "화", 丁: "화", 戊: "토", 己: "토",
  庚: "금", 辛: "금", 壬: "수", 癸: "수",
};
const BRANCH_WX: Record<string, string> = {
  寅: "목", 卯: "목", 巳: "화", 午: "화", 辰: "토", 戌: "토", 丑: "토", 未: "토",
  申: "금", 酉: "금", 亥: "수", 子: "수",
};

const STEM_KO: Record<string, string> = {
  甲: "갑", 乙: "을", 丙: "병", 丁: "정", 戊: "무", 己: "기",
  庚: "경", 辛: "신", 壬: "임", 癸: "계",
};
const BRANCH_KO: Record<string, string> = {
  子: "자", 丑: "축", 寅: "인", 卯: "묘", 辰: "진", 巳: "사",
  午: "오", 未: "미", 申: "신", 酉: "유", 戌: "술", 亥: "해",
};

function PillarCell({ label, pillar, stemGod, branchGod, hidden, lifeStage, sinsal }: {
  label: string; pillar: Pillar | null;
  stemGod?: string; branchGod?: string; hidden?: string[];
  lifeStage?: string; sinsal?: string;
}) {
  if (!pillar) {
    return (
      <div className="pillar empty">
        <div className="pillar-label">{label}</div>
        <div className="pillar-god">시 미상</div>
        <div className="pillar-stem">?</div>
        <div className="pillar-branch">?</div>
        <div className="pillar-god" />
        <div className="pillar-hidden" />
        <div className="pillar-extra" />
        <div className="pillar-extra" />
      </div>
    );
  }
  const sWx = STEM_WX[pillar.stem] || "토";
  const bWx = BRANCH_WX[pillar.branch] || "토";
  return (
    <div className="pillar">
      <div className="pillar-label">{label}</div>
      <div className="pillar-god top">{stemGod || ""}</div>
      <div className="pillar-stem" style={{ background: WX_COLOR[sWx], color: WX_TEXT[sWx], border: WX_BORDER[sWx] }}>
        <div className="ch">{pillar.stem}</div>
        <div className="ko">{STEM_KO[pillar.stem]}</div>
      </div>
      <div className="pillar-branch" style={{ background: WX_COLOR[bWx], color: WX_TEXT[bWx], border: WX_BORDER[bWx] }}>
        <div className="ch">{pillar.branch}</div>
        <div className="ko">{BRANCH_KO[pillar.branch]}</div>
      </div>
      <div className="pillar-god bot">{branchGod || ""}</div>
      <div className="pillar-hidden">{(hidden || []).join(" ")}</div>
      <div className="pillar-extra" title="십이운성">{lifeStage || ""}</div>
      <div className="pillar-extra sinsal" title="십이신살">{sinsal || ""}</div>
    </div>
  );
}

export default function SajuChart({ chart }: { chart: Chart }) {
  const wxArr = useMemo(() => {
    const w = chart.wuxing;
    const total = Math.max(1, w.wood + w.fire + w.earth + w.metal + w.water);
    return [
      { ko: "목", v: w.wood, pct: (w.wood / total) * 100 },
      { ko: "화", v: w.fire, pct: (w.fire / total) * 100 },
      { ko: "토", v: w.earth, pct: (w.earth / total) * 100 },
      { ko: "금", v: w.metal, pct: (w.metal / total) * 100 },
      { ko: "수", v: w.water, pct: (w.water / total) * 100 },
    ];
  }, [chart.wuxing]);

  const g = chart.ten_gods;
  const lf = chart.twelve_life;
  const ss = chart.twelve_sinsal;
  // 지장간은 위치 라벨(년지/월지/일지/시지) 키로 제공됨
  const h = (label: string) => (chart.hidden_stems?.[label] || []);

  return (
    <div className="saju-chart">
      <div className="pillar-row">
        <PillarCell label="시" pillar={chart.pillars.hour}
          stemGod={tg(g?.hour_stem)} branchGod={tg(g?.hour_branch)} hidden={h("시지")}
          lifeStage={lf?.["시"]} sinsal={ss?.["시"]} />
        <PillarCell label="일" pillar={chart.pillars.day}
          stemGod="일원" branchGod={tg(g?.day_branch)} hidden={h("일지")}
          lifeStage={lf?.["일"]} sinsal={ss?.["일"]} />
        <PillarCell label="월" pillar={chart.pillars.month}
          stemGod={tg(g?.month_stem)} branchGod={tg(g?.month_branch)} hidden={h("월지")}
          lifeStage={lf?.["월"]} sinsal={ss?.["월"]} />
        <PillarCell label="년" pillar={chart.pillars.year}
          stemGod={tg(g?.year_stem)} branchGod={tg(g?.year_branch)} hidden={h("년지")}
          lifeStage={lf?.["년"]} sinsal={ss?.["년"]} />
      </div>

      {chart.napeum && (chart.napeum["시"] || chart.napeum["일"] || chart.napeum["월"] || chart.napeum["년"]) && (
        <div className="chart-napeum">납음(納音)
          {["시", "일", "월", "년"].map((k) => chart.napeum?.[k] ? <span key={k} className="np">{chart.napeum[k]}</span> : null)}
        </div>
      )}
      {chart.saryeong && (
        <div className="chart-gongmang">사령(司令) <b>{chart.saryeong}({STEM_KO[chart.saryeong] || ""})</b></div>
      )}
      {chart.gongmang && chart.gongmang.length > 0 && (
        <div className="chart-gongmang">공망(空亡) <b>{chart.gongmang.join("·")}</b></div>
      )}

      <div className="wx-bars">
        {wxArr.map((w) => (
          <div key={w.ko} className="wx-bar">
            <span className="wx-label" style={{ color: WX_COLOR[w.ko] }}>{w.ko}</span>
            <div className="wx-fill-wrap">
              <div className="wx-fill" style={{ width: `${w.pct}%`, background: WX_COLOR[w.ko] }} />
            </div>
            <span className="wx-num">{w.v}</span>
          </div>
        ))}
      </div>

      <div className="day-master-info">
        일간 <strong>{chart.pillars.day.stem}({STEM_KO[chart.pillars.day.stem]})</strong> ·
        오행 <span style={{ color: WX_COLOR[chart.day_master_element === "wood" ? "목" : chart.day_master_element === "fire" ? "화" : chart.day_master_element === "earth" ? "토" : chart.day_master_element === "metal" ? "금" : "수"] }}>
          {{ wood: "목", fire: "화", earth: "토", metal: "금", water: "수" }[chart.day_master_element] || chart.day_master_element}
        </span> · 강약 <strong>{chart.day_master_strength}</strong>
      </div>

      {chart.johu_yongsin && (() => {
        const ys = chart.johu_yongsin!;
        const pWx = STEM_WX[ys.primary] || "토";
        return (
          <div className="chart-yongsin" title={ys.note}>
            조후용신(調候)
            <b className="ys-chip" style={{ background: WX_COLOR[pWx], color: WX_TEXT[pWx], border: WX_BORDER[pWx] }}>
              {ys.primary}({STEM_KO[ys.primary] || ""})
            </b>
            {ys.supporting.length > 0 && (
              <span className="ys-sup">보조 {ys.supporting.map((s) => `${s}(${STEM_KO[s] || ""})`).join("·")}</span>
            )}
            {ys.is_climate_priority && <span className="ys-badge">조후 우선</span>}
          </div>
        );
      })()}

      {chart.daewoon && chart.daewoon.entries.length > 0 && (
        <div className="daewoon-strip">
          <div className="daewoon-title">
            대운 ({chart.daewoon.direction === "forward" ? "순행" : "역행"}, 대운수 {chart.daewoon.start_age.toFixed(1)}세)
          </div>
          <div className="daewoon-row">
            {chart.daewoon.entries.slice(0, 9).map((d) => {
              const sWx = STEM_WX[d.pillar.stem] || "토";
              const bWx = BRANCH_WX[d.pillar.branch] || "토";
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
