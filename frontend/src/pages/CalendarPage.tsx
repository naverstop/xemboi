/** B-8 운세 캘린더 — 월별 일진표(무료·무저장). 일별 간지 + 개인 길흉 4색 배지
 * + 충·형·해 경고 + 손없는날 + 절기. 점수는 택일 엔진(일반 기준) 셀 재사용. */
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, useMe, type Birth, type FortuneCalendar, type CalendarDay } from "../api";
import { resolveBirthTime } from "../lib/birthTime";
import BirthFields, { type BirthValue } from "../components/BirthFields";
import PrivacyNotice from "../components/PrivacyNotice";
import RememberBirthToggle, { useBirthMemory } from "../components/RememberBirth";
import AnswerActions from "../components/AnswerActions";
import ExplainChat from "../components/ExplainChat";
import { displayName } from "../lib/displayName";

const GRADE_COLORS: Record<string, string> = {
  대길: "#0b72c4", 길: "#3aa4e8", 평: "#9a917f", 흉: "#d64545",
};

// 월 캘린더를 복사/공유/PDF용 plain text로 직렬화(공용 액션바 규약)
function monthText(res: FortuneCalendar): string {
  const lines = [`[운세 캘린더] ${res.year}년 ${res.month}월 — 일별 일진·길흉`];
  res.days.forEach((d) => {
    const marks = [
      d.sonless ? "손없는날" : "",
      d.warnings.length ? `⚡${d.warnings.join("·")}` : "",
      d.jieqi ? `절기 ${d.jieqi}` : "",
    ].filter(Boolean).join(" · ");
    lines.push(`${d.day}일 ${d.ganzhi} · ${d.grade} ${d.score}점${marks ? " · " + marks : ""}`);
  });
  if (res.note) lines.push(`\n${res.note}`);
  return lines.join("\n");
}

export default function CalendarPage() {
  const me = useMe();
  const now = new Date();
  const [b, setB] = useState<BirthValue>({ birth_date: "", birth_time: "", unknown_time: false, gender: "male", calendar: "solar", is_leap_month: false, apply_true_solar_time: true, birth_longitude: 126.98 });
  const [ym, setYm] = useState<{ y: number; m: number }>({ y: now.getFullYear(), m: now.getMonth() + 1 });
  const [res, setRes] = useState<FortuneCalendar | null>(null);
  const [sel, setSel] = useState<CalendarDay | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const autoRan = useRef(false);

  async function run(bv: BirthValue, y: number, m: number, scroll = false) {
    if (!bv.birth_date) return;
    setLoading(true); setErr(null); setSel(null);
    const birth: Birth = {
      birth_date: bv.birth_date, birth_time: resolveBirthTime(bv.birth_time, bv.unknown_time),
      calendar: bv.calendar, gender: bv.gender, is_leap_month: bv.calendar === "lunar" ? bv.is_leap_month : false,
      apply_true_solar_time: !!bv.apply_true_solar_time, night_zi_mode: bv.night_zi_mode ?? "yaja",
      birth_longitude: bv.birth_longitude ?? null, apply_equation_of_time: !!bv.apply_equation_of_time,
    };
    try {
      setRes(await api.fortuneCalendar(birth, y, m));
      // 첫 조회만 결과로 스크롤(표준 UX) — 월 이동(◀▶) 시엔 위치 유지
      if (scroll) setTimeout(() => document.getElementById("tool-result")?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
    } catch (e: any) {
      setErr(e?.message || "캘린더를 불러오지 못했어요.");
    } finally { setLoading(false); }
  }

  // 공통 '기억하기' — 저장본 자동 채움 + 최초 1회 자동 조회
  const { remember, toggleRemember } = useBirthMemory(
    b, (patch) => setB((prev) => ({ ...prev, ...patch })),
    { onPrefill: (patch) => { if (!autoRan.current) { autoRan.current = true; run({ ...b, ...patch }, ym.y, ym.m); } } },
  );

  function move(delta: number) {
    let { y, m } = ym;
    m += delta;
    if (m < 1) { m = 12; y -= 1; }
    if (m > 12) { m = 1; y += 1; }
    setYm({ y, m });
    run(b, y, m);
  }

  // 그리드 앞 공백(일요일 시작)
  const firstPad = res ? (new Date(res.year, res.month - 1, 1).getDay()) : 0;

  return (
    <div className="compat-page">
      <PrivacyNotice variant="tool" />
      <header className="compat-hero">
        <div className="compat-hero-badge">曆</div>
        <h1>운세 캘린더</h1>
        <p>한 달의 <b>일진(日辰)</b>과 내 사주 기준 <b>길흉</b>을 한눈에 봐요. 손없는날·절기·충형해 경고까지 표시해 드려요. <b>무료</b>입니다.</p>
      </header>

      <div className="tool-form">
        <RememberBirthToggle remember={remember} onToggle={toggleRemember} />
        <BirthFields value={b} onChange={(patch) => setB((prev) => ({ ...prev, ...patch }))} remembered={remember} />
      </div>

      <div className="compat-actions">
        <button className="compat-cta" disabled={!b.birth_date || loading} onClick={() => run(b, ym.y, ym.m, true)}>
          {loading ? "계산 중…" : "📅 이번 달 운세 보기 (무료)"}
        </button>
        {!b.birth_date && <div className="cta-hint">생년월일을 입력해 주세요</div>}
      </div>
      {err && <div className="compat-err">{err}</div>}

      {res && (
        <section id="tool-result" className="compat-result">
          <div className="fc-nav">
            <button onClick={() => move(-1)} aria-label="이전 달">◀</button>
            <b>{res.year}년 {res.month}월</b>
            <button onClick={() => move(1)} aria-label="다음 달">▶</button>
          </div>
          <div className="fc-legend">
            {Object.entries(GRADE_COLORS).map(([g, c]) => (
              <span key={g}><i style={{ background: c }} />{g}</span>
            ))}
            <span><i className="fc-son">손</i>손없는날</span>
            <span>⚡ 충·형·해</span>
          </div>
          <div className="fc-grid">
            {["일", "월", "화", "수", "목", "금", "토"].map((w, i) => (
              <div key={w} className={`fc-w${i === 0 ? " sun" : i === 6 ? " sat" : ""}`}>{w}</div>
            ))}
            {Array.from({ length: firstPad }, (_, i) => <div key={`p${i}`} className="fc-cell empty" />)}
            {res.days.map((d) => {
              const isToday = d.date === res.today;
              return (
                <button
                  key={d.date}
                  className={`fc-cell${isToday ? " today" : ""}${sel?.date === d.date ? " sel" : ""}`}
                  onClick={() => setSel(d)}
                >
                  <span className={`fc-day${d.weekday === 6 ? " sun" : d.weekday === 5 ? " sat" : ""}`}>{d.day}</span>
                  <span className="fc-ganzhi">{d.ganzhi.slice(0, 2)}</span>
                  <span className="fc-badge" style={{ background: GRADE_COLORS[d.grade] }}>{d.grade}</span>
                  <span className="fc-marks">
                    {d.sonless && <i className="fc-son">손</i>}
                    {d.warnings.length > 0 && <em title={d.warnings.join(" · ")}>⚡</em>}
                    {d.jieqi && <b className="fc-jieqi">{d.jieqi}</b>}
                  </span>
                </button>
              );
            })}
          </div>

          {sel && (
            <div className="fc-detail">
              <div className="fc-detail-head">
                <b>{res.month}월 {sel.day}일 · {sel.ganzhi}</b>
                <span className="fc-badge lg" style={{ background: GRADE_COLORS[sel.grade] }}>{sel.grade} {sel.score}점</span>
              </div>
              <ul>
                {sel.jieqi && <li>🌱 절기 <b>{sel.jieqi}</b></li>}
                {sel.sonless && <li>🏠 손없는날 — 이사·이동에 부담 없는 날로 봐요</li>}
                {sel.warnings.length > 0
                  ? <li>⚡ 내 사주와 {sel.warnings.join(" · ")} — 큰 결정은 신중히</li>
                  : <li>😊 내 사주와 특별한 충돌이 없어요</li>}
              </ul>
              <Link className="fc-detail-link" to="/taekil">🎯 결혼·이사 등 목적별 정밀 택일 보러 가기 →</Link>
            </div>
          )}
          <p className="td-note">{res.note}</p>

          {/* 공용 액션바 — 복사·공유·PDF (6메뉴 표준. 무저장이라 피드백은 자동 미노출) */}
          <AnswerActions
            text={monthText(res)}
            source="tool"
            pdf={{
              docTitle: `${displayName(me)} 님의 ${res.year}년 ${res.month}월 운세 캘린더`,
              personLine: `${displayName(me)} 님`,
              item: "운세 캘린더(월별 일진)",
            }}
          />

          {/* 해설(무과금)·추가질문(기존 정책: 기본 1,000P/심화 3,000P, 부족 시 충전유도) — 공용 tools 스트림 */}
          {res.tool_id && (
            <ExplainChat
              streamPath={`/api/tools/${res.tool_id}/messages/stream`}
              isPreview={!!res.is_preview}
              autoStart={false}
              pdf={{
                docTitle: `${displayName(me)} 님의 ${res.year}년 ${res.month}월 운세 캘린더`,
                personLine: `${displayName(me)} 님`,
                item: "운세 캘린더(월별 일진)",
              }}
              pdfHeader={monthText(res)}
              feedbackSource="tool"
              feedbackSessionId={res.tool_id}
              suggestFetch={() => api.getToolSuggestions(res.tool_id!).then((r) => r.suggestions || [])}
            />
          )}
        </section>
      )}
    </div>
  );
}
