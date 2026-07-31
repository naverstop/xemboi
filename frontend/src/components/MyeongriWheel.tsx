import { useEffect, useState } from "react";
import { useTranslation, Trans } from "react-i18next";

/* 명리 기초 도감 — 천간(十干)·지지(十二支) 인터랙티브 휠 (랜딩 히어로 우측)
 * 래스터 이미지 대신 SVG/HTML로 재구축: 한자가 항상 선명(웹폰트), 라이트/다크 테마 자동 일치.
 * 12지지 동물은 영상·스트립과 동일한 12띠 아바타(청년) 재사용 — 스트립(초년)과 중복 회피.
 * 독음·설명·띠·계절·방위는 로케일 매핑(chart.*) — ko 한글 / vi 한월음(Hán-Việt). */

type El = "木" | "火" | "土" | "金" | "水";
type Stem = { hanja: string; el: El; yy: "yang" | "yin" };
type Branch = { hanja: string; el: El };
type StrMap = Record<string, string>;

const EL_COLOR: Record<El, string> = {
  木: "#2f9e44", 火: "#e03131", 土: "#c07d2a", 金: "#7a8691", 水: "#1971c2",
};

const STEMS: Stem[] = [
  { hanja: "甲", el: "木", yy: "yang" },
  { hanja: "乙", el: "木", yy: "yin" },
  { hanja: "丙", el: "火", yy: "yang" },
  { hanja: "丁", el: "火", yy: "yin" },
  { hanja: "戊", el: "土", yy: "yang" },
  { hanja: "己", el: "土", yy: "yin" },
  { hanja: "庚", el: "金", yy: "yang" },
  { hanja: "辛", el: "金", yy: "yin" },
  { hanja: "壬", el: "水", yy: "yang" },
  { hanja: "癸", el: "水", yy: "yin" },
];

const BRANCHES: Branch[] = [
  { hanja: "子", el: "水" },
  { hanja: "丑", el: "土" },
  { hanja: "寅", el: "木" },
  { hanja: "卯", el: "木" },
  { hanja: "辰", el: "土" },
  { hanja: "巳", el: "火" },
  { hanja: "午", el: "火" },
  { hanja: "未", el: "土" },
  { hanja: "申", el: "金" },
  { hanja: "酉", el: "金" },
  { hanja: "戌", el: "土" },
  { hanja: "亥", el: "水" },
];

/* i번째 항목의 원둘레 좌표(%) — 12시 방향부터 시계방향, CSS %포지션이라 크기에 자동 비례 */
function pos(i: number, n: number, r: number) {
  const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
  return { left: `${50 + r * Math.cos(a)}%`, top: `${50 + r * Math.sin(a)}%` };
}

export default function MyeongriWheel() {
  const { t: tr } = useTranslation();
  const stemR = tr("chart.stem", { returnObjects: true }) as StrMap;
  const branchR = tr("chart.branch", { returnObjects: true }) as StrMap;
  const wuxingR = tr("chart.wuxing", { returnObjects: true }) as StrMap;
  const zodiacR = tr("chart.zodiac", { returnObjects: true }) as StrMap;
  const descR = tr("chart.mw_stem_desc", { returnObjects: true }) as StrMap;
  const yyR = tr("chart.mw_yy", { returnObjects: true }) as StrMap;
  const seasonR = tr("chart.mw_season", { returnObjects: true }) as StrMap;
  const dirR = tr("chart.mw_dir", { returnObjects: true }) as StrMap;
  const timeR = tr("chart.mw_time", { returnObjects: true }) as StrMap;
  const imgR = tr("chart.mw_img", { returnObjects: true }) as StrMap;

  const [tab, setTab] = useState<"gan" | "ji">("gan");
  const [sel, setSel] = useState(0);
  const [hover, setHover] = useState(false);

  const n = tab === "gan" ? STEMS.length : BRANCHES.length;

  // 자동 순환(2초) — 마우스 올리면 일시정지, 클릭으로 직접 선택
  useEffect(() => {
    if (hover) return;
    const t = setInterval(() => setSel((s) => (s + 1) % n), 2000);
    return () => clearInterval(t);
  }, [hover, n]);

  const switchTab = (t: "gan" | "ji") => { setTab(t); setSel(0); };

  const st = STEMS[sel % STEMS.length];
  const br = BRANCHES[sel % BRANCHES.length];
  const cur = tab === "gan" ? st : br;
  const color = EL_COLOR[cur.el];

  return (
    <div className="mw-card" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
         role="group" aria-label={tr("chart.mw_aria")}>
      <div className="mw-tabs">
        <button type="button" className={tab === "gan" ? "on" : ""} onClick={() => switchTab("gan")}>
          {tr("chart.mw_tab_gan")} <span className="mw-tab-hj">十干</span>
        </button>
        <button type="button" className={tab === "ji" ? "on" : ""} onClick={() => switchTab("ji")}>
          {tr("chart.mw_tab_ji")} <span className="mw-tab-hj">十二支</span>
        </button>
      </div>

      <div className="mw-wheel">
        <div className="mw-ring" aria-hidden />
        {tab === "gan"
          ? STEMS.map((s, i) => (
              <button key={s.hanja} type="button" onClick={() => setSel(i)}
                      className={`mw-item mw-stem ${i === sel ? "sel" : ""}`}
                      style={{ ...pos(i, STEMS.length, 40), "--el": EL_COLOR[s.el] } as React.CSSProperties}
                      aria-label={`${stemR[s.hanja]}(${s.hanja}) — ${descR[s.hanja]}`}>
                <span className="mw-hj">{s.hanja}</span>
                <span className="mw-ko">{stemR[s.hanja]}</span>
              </button>
            ))
          : BRANCHES.map((b, i) => (
              <button key={b.hanja} type="button" onClick={() => setSel(i)}
                      className={`mw-item mw-branch ${i === sel ? "sel" : ""}`}
                      style={{ ...pos(i, BRANCHES.length, 41), "--el": EL_COLOR[b.el] } as React.CSSProperties}
                      aria-label={`${branchR[b.hanja]}(${b.hanja}) — ${zodiacR[b.hanja]}, ${timeR[b.hanja]}`}>
                <img src={imgR[b.hanja]} alt="" loading="lazy" width={44} height={44} />
                <span className="mw-bj">{b.hanja}<em>{branchR[b.hanja]}</em></span>
              </button>
            ))}

        {/* 중앙 허브 — 선택 항목 상세 */}
        <div className="mw-hub" style={{ "--el": color } as React.CSSProperties}>
          {tab === "gan" ? (
            <>
              <span className="mw-hub-hj">{st.hanja}</span>
              <span className="mw-hub-name">{stemR[st.hanja]} · {tr("chart.mw_hub_stem_name", { yy: yyR[st.yy], el: wuxingR[st.el] })}({st.el})</span>
              <span className="mw-hub-desc">{descR[st.hanja]}</span>
            </>
          ) : (
            <>
              <img className="mw-hub-av" src={imgR[br.hanja]} alt="" width={52} height={52} />
              <span className="mw-hub-name">{br.hanja} {branchR[br.hanja]} · {tr("chart.mw_hub_zodiac", { animal: zodiacR[br.hanja] })}</span>
              <span className="mw-hub-desc">{timeR[br.hanja]} · {seasonR[br.hanja]} · {dirR[br.hanja]}</span>
              <span className="mw-hub-el">{wuxingR[br.el]}({br.el})</span>
            </>
          )}
        </div>
      </div>

      <div className="mw-legend">
        {tab === "gan"
          ? <Trans i18nKey="chart.mw_legend_gan" components={{ b: <b /> }} />
          : tr("chart.mw_legend_ji")}
      </div>
    </div>
  );
}
