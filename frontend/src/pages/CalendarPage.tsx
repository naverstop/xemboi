/** B-8 운세 캘린더 — 월별 일진표(무료·무저장). 일별 간지 + 개인 길흉 4색 배지
 * + 충·형·해 경고 + 손없는날 + 절기. 점수는 택일 엔진(일반 기준) 셀 재사용. */
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation, Trans } from "react-i18next";
import i18n from "../i18n";
import { api, useMe, type Birth, type FortuneCalendar, type CalendarDay } from "../api";
import { resolveBirthTime } from "../lib/birthTime";
import BirthFields, { type BirthValue } from "../components/BirthFields";
import PrivacyNotice from "../components/PrivacyNotice";
import RememberBirthToggle, { useBirthMemory } from "../components/RememberBirth";
import AnswerActions from "../components/AnswerActions";
import ExplainChat from "../components/ExplainChat";
import { displayName } from "../lib/displayName";

// 등급 색상 — 키는 백엔드 grade 값(ko) 그대로(조회용 내부 식별자). 표시 라벨은 gradeLabel()로 번역.
const GRADE_COLORS: Record<string, string> = {
  대길: "#0b72c4", 길: "#3aa4e8", 평: "#9a917f", 흉: "#d64545",
};
const GRADE_I18N: Record<string, string> = {
  대길: "fcal.grade_daegil", 길: "fcal.grade_gil", 평: "fcal.grade_pyeong", 흉: "fcal.grade_hyung",
};
const gradeLabel = (g: string): string => (GRADE_I18N[g] ? i18n.t(GRADE_I18N[g]) : g);

// 월 캘린더를 복사/공유/PDF용 plain text로 직렬화(공용 액션바 규약)
function monthText(res: FortuneCalendar): string {
  const lines = [i18n.t("fcal.txt_title", { y: res.year, m: res.month })];
  res.days.forEach((d) => {
    const marks = [
      d.sonless ? i18n.t("fcal.sonless") : "",
      d.warnings.length ? `⚡${d.warnings.join("·")}` : "",
      d.jieqi ? i18n.t("fcal.txt_jieqi", { j: d.jieqi }) : "",
    ].filter(Boolean).join(" · ");
    lines.push(i18n.t("fcal.txt_day", { d: d.day, ganzhi: d.ganzhi, grade: gradeLabel(d.grade), score: d.score }) + (marks ? " · " + marks : ""));
  });
  if (res.note) lines.push(`\n${res.note}`);
  return lines.join("\n");
}

export default function CalendarPage() {
  const { t: tr } = useTranslation();
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
      setErr(e?.message || tr("fcal.load_fail"));
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
        <div className="compat-hero-badge">{tr("fcal.hero_badge")}</div>
        <h1>{tr("fcal.hero_title")}</h1>
        <p><Trans i18nKey="fcal.hero_desc" components={{ b: <b /> }} /></p>
      </header>

      <div className="tool-form">
        <RememberBirthToggle remember={remember} onToggle={toggleRemember} />
        <BirthFields value={b} onChange={(patch) => setB((prev) => ({ ...prev, ...patch }))} remembered={remember} />
      </div>

      <div className="compat-actions">
        <button className="compat-cta" disabled={!b.birth_date || loading} onClick={() => run(b, ym.y, ym.m, true)}>
          {loading ? tr("fcal.loading") : tr("fcal.cta")}
        </button>
        {!b.birth_date && <div className="cta-hint">{tr("fcal.cta_hint")}</div>}
      </div>
      {err && <div className="compat-err">{err}</div>}

      {res && (
        <section id="tool-result" className="compat-result">
          <div className="fc-nav">
            <button onClick={() => move(-1)} aria-label={tr("fcal.prev_month")}>◀</button>
            <b>{tr("fcal.ym", { y: res.year, m: res.month })}</b>
            <button onClick={() => move(1)} aria-label={tr("fcal.next_month")}>▶</button>
          </div>
          <div className="fc-legend">
            {Object.entries(GRADE_COLORS).map(([g, c]) => (
              <span key={g}><i style={{ background: c }} />{gradeLabel(g)}</span>
            ))}
            <span><i className="fc-son">{tr("fcal.son_marker")}</i>{tr("fcal.sonless")}</span>
            <span>{tr("fcal.legend_warn")}</span>
          </div>
          <div className="fc-grid">
            {tr("fcal.weekdays").split(",").map((w, i) => (
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
                  <span className="fc-badge" style={{ background: GRADE_COLORS[d.grade] }}>{gradeLabel(d.grade)}</span>
                  <span className="fc-marks">
                    {d.sonless && <i className="fc-son">{tr("fcal.son_marker")}</i>}
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
                <b>{tr("fcal.detail_date", { m: res.month, d: sel.day, ganzhi: sel.ganzhi })}</b>
                <span className="fc-badge lg" style={{ background: GRADE_COLORS[sel.grade] }}>{tr("fcal.score_grade", { grade: gradeLabel(sel.grade), score: sel.score })}</span>
              </div>
              <ul>
                {sel.jieqi && <li>{tr("fcal.jieqi_label")} <b>{sel.jieqi}</b></li>}
                {sel.sonless && <li>{tr("fcal.sonless_note")}</li>}
                {sel.warnings.length > 0
                  ? <li>{tr("fcal.warn_note", { list: sel.warnings.join(" · ") })}</li>
                  : <li>{tr("fcal.no_conflict")}</li>}
              </ul>
              <Link className="fc-detail-link" to="/taekil">{tr("fcal.taekil_link")}</Link>
            </div>
          )}
          <p className="td-note">{res.note}</p>

          {/* 공용 액션바 — 복사·공유·PDF (6메뉴 표준. 무저장이라 피드백은 자동 미노출) */}
          <AnswerActions
            text={monthText(res)}
            source="tool"
            pdf={{
              docTitle: tr("fcal.pdf_doc", { who: displayName(me), y: res.year, m: res.month }),
              personLine: tr("fcal.pdf_person", { who: displayName(me) }),
              item: tr("fcal.pdf_item"),
            }}
          />

          {/* 해설(무과금)·추가질문(기존 정책: 기본 1,000P/심화 3,000P, 부족 시 충전유도) — 공용 tools 스트림 */}
          {res.tool_id && (
            <ExplainChat
              streamPath={`/api/tools/${res.tool_id}/messages/stream`}
              isPreview={!!res.is_preview}
              autoStart={false}
              pdf={{
                docTitle: tr("fcal.pdf_doc", { who: displayName(me), y: res.year, m: res.month }),
                personLine: tr("fcal.pdf_person", { who: displayName(me) }),
                item: tr("fcal.pdf_item"),
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
