import { useEffect, useState } from "react";

/* 명리 기초 도감 — 천간(十干)·지지(十二支) 인터랙티브 휠 (랜딩 히어로 우측)
 * 래스터 이미지 대신 SVG/HTML로 재구축: 한글·한자가 항상 선명(웹폰트), 라이트/다크 테마 자동 일치.
 * 12지지 동물은 영상·스트립과 동일한 12띠 아바타(청년) 재사용 — 스트립(초년)과 중복 회피. */

type Stem = { hanja: string; ko: string; el: El; yy: "양" | "음"; desc: string };
type Branch = { hanja: string; ko: string; animal: string; time: string; el: El; season: string; dir: string };
type El = "목" | "화" | "토" | "금" | "수";

const EL_COLOR: Record<El, string> = {
  목: "#2f9e44", 화: "#e03131", 토: "#c07d2a", 금: "#7a8691", 수: "#1971c2",
};
const EL_HANJA: Record<El, string> = { 목: "木", 화: "火", 토: "土", 금: "金", 수: "水" };

const STEMS: Stem[] = [
  { hanja: "甲", ko: "갑", el: "목", yy: "양", desc: "큰나무 · 시작" },
  { hanja: "乙", ko: "을", el: "목", yy: "음", desc: "덩굴나무 · 유연함" },
  { hanja: "丙", ko: "병", el: "화", yy: "양", desc: "태양 · 밝음" },
  { hanja: "丁", ko: "정", el: "화", yy: "음", desc: "촛불 · 빛 · 정성" },
  { hanja: "戊", ko: "무", el: "토", yy: "양", desc: "큰산 · 중심" },
  { hanja: "己", ko: "기", el: "토", yy: "음", desc: "밭 · 토양 · 양육" },
  { hanja: "庚", ko: "경", el: "금", yy: "양", desc: "쇠 · 강함 · 결단" },
  { hanja: "辛", ko: "신", el: "금", yy: "음", desc: "보석 · 정밀함" },
  { hanja: "壬", ko: "임", el: "수", yy: "양", desc: "바다 · 큰물 · 지혜" },
  { hanja: "癸", ko: "계", el: "수", yy: "음", desc: "비 · 작은물 · 스며듦" },
];

const BRANCHES: Branch[] = [
  { hanja: "子", ko: "자", animal: "쥐", time: "23~01시", el: "수", season: "겨울", dir: "북" },
  { hanja: "丑", ko: "축", animal: "소", time: "01~03시", el: "토", season: "겨울", dir: "북북동" },
  { hanja: "寅", ko: "인", animal: "호랑이", time: "03~05시", el: "목", season: "봄", dir: "동북동" },
  { hanja: "卯", ko: "묘", animal: "토끼", time: "05~07시", el: "목", season: "봄", dir: "동" },
  { hanja: "辰", ko: "진", animal: "용", time: "07~09시", el: "토", season: "봄", dir: "동남동" },
  { hanja: "巳", ko: "사", animal: "뱀", time: "09~11시", el: "화", season: "여름", dir: "남남동" },
  { hanja: "午", ko: "오", animal: "말", time: "11~13시", el: "화", season: "여름", dir: "남" },
  { hanja: "未", ko: "미", animal: "양", time: "13~15시", el: "토", season: "여름", dir: "남남서" },
  { hanja: "申", ko: "신", animal: "원숭이", time: "15~17시", el: "금", season: "가을", dir: "서남서" },
  { hanja: "酉", ko: "유", animal: "닭", time: "17~19시", el: "금", season: "가을", dir: "서" },
  { hanja: "戌", ko: "술", animal: "개", time: "19~21시", el: "토", season: "가을", dir: "서북서" },
  { hanja: "亥", ko: "해", animal: "돼지", time: "21~23시", el: "수", season: "겨울", dir: "북북서" },
];

/* i번째 항목의 원둘레 좌표(%) — 12시 방향부터 시계방향, CSS %포지션이라 크기에 자동 비례 */
function pos(i: number, n: number, r: number) {
  const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
  return { left: `${50 + r * Math.cos(a)}%`, top: `${50 + r * Math.sin(a)}%` };
}

export default function MyeongriWheel() {
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
         role="group" aria-label="명리 기초 도감 — 천간과 지지">
      <div className="mw-tabs">
        <button type="button" className={tab === "gan" ? "on" : ""} onClick={() => switchTab("gan")}>
          천간 <span className="mw-tab-hj">十干</span>
        </button>
        <button type="button" className={tab === "ji" ? "on" : ""} onClick={() => switchTab("ji")}>
          지지 <span className="mw-tab-hj">十二支</span>
        </button>
      </div>

      <div className="mw-wheel">
        <div className="mw-ring" aria-hidden />
        {tab === "gan"
          ? STEMS.map((s, i) => (
              <button key={s.hanja} type="button" onClick={() => setSel(i)}
                      className={`mw-item mw-stem ${i === sel ? "sel" : ""}`}
                      style={{ ...pos(i, STEMS.length, 40), "--el": EL_COLOR[s.el] } as React.CSSProperties}
                      aria-label={`${s.ko}(${s.hanja}) — ${s.desc}`}>
                <span className="mw-hj">{s.hanja}</span>
                <span className="mw-ko">{s.ko}</span>
              </button>
            ))
          : BRANCHES.map((b, i) => (
              <button key={b.hanja} type="button" onClick={() => setSel(i)}
                      className={`mw-item mw-branch ${i === sel ? "sel" : ""}`}
                      style={{ ...pos(i, BRANCHES.length, 41), "--el": EL_COLOR[b.el] } as React.CSSProperties}
                      aria-label={`${b.ko}(${b.hanja}) — ${b.animal}, ${b.time}`}>
                <img src={`/zodiac/${b.animal}_청년.jpg`} alt="" loading="lazy" width={44} height={44} />
                <span className="mw-bj">{b.hanja}<em>{b.ko}</em></span>
              </button>
            ))}

        {/* 중앙 허브 — 선택 항목 상세 */}
        <div className="mw-hub" style={{ "--el": color } as React.CSSProperties}>
          {tab === "gan" ? (
            <>
              <span className="mw-hub-hj">{st.hanja}</span>
              <span className="mw-hub-name">{st.ko} · {st.yy}의 {st.el}({EL_HANJA[st.el]})</span>
              <span className="mw-hub-desc">{st.desc}</span>
            </>
          ) : (
            <>
              <img className="mw-hub-av" src={`/zodiac/${br.animal}_청년.jpg`} alt="" width={52} height={52} />
              <span className="mw-hub-name">{br.hanja} {br.ko} · {br.animal}띠</span>
              <span className="mw-hub-desc">{br.time} · {br.season} · {br.dir}</span>
              <span className="mw-hub-el">{br.el}({EL_HANJA[br.el]})</span>
            </>
          )}
        </div>
      </div>

      <div className="mw-legend">
        {tab === "gan"
          ? <>상생 <b>목→화→토→금→수→목</b> · 상극 <b>목↘토↘수↘화↘금↘목</b></>
          : <>지지는 시간·방향·계절·띠 동물로 이어져요 — 눌러서 살펴보세요</>}
      </div>
    </div>
  );
}
