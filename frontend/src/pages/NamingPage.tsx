/** 작명/개명/아호 — route param kind로 분기. */
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api, useMe, type Birth, type NamingKind, type ToolResponse } from "../api";
import { type EntryMenu } from "../lib/entryFee";
import { useEnsureEntry, EntryFeeNotice } from "../components/ChargeModal";
import { resolveBirthTime } from "../lib/birthTime";
import { glossKo } from "../lib/naming-data";
import ExplainChat from "../components/ExplainChat";
import HanjaSyllablePicker from "../components/HanjaSyllablePicker";
import BirthFields, { profileToBirthValue, type BirthValue } from "../components/BirthFields";

const META: Record<NamingKind, { title: string; badge: string; desc: string; needs: "surname" | "current_name" | "none" }> = {
  jakmyeong: { title: "작명", badge: "作名", desc: "사주의 부족한 기운을 보완하는 이름을 추천합니다.", needs: "surname" },
  gaemyeong: { title: "개명", badge: "改名", desc: "현재 이름을 진단하고 개선 방향을 제안합니다.", needs: "current_name" },
  aho: { title: "아호", badge: "雅號", desc: "사주에 어울리는 호(號)를 추천합니다.", needs: "none" },
};

const _ELEM_KO: Record<string, string> = { "木": "목", "火": "화", "土": "토", "金": "금", "水": "수" };

// 상담서 PDF 본문 상단 요약 — 추천 이름(작명/아호) 또는 진단(개명)
function namingPdfHeader(kind: NamingKind, r: any): string {
  if (kind === "gaemyeong") {
    const a = r?.analysis;
    if (!a) return "";
    const persp = Object.values(a.perspectives || {})
      .map((p: any) => `${p.label} ${p.total}점(${p.grade})`)
      .join(" · ");
    return `[이름 진단] ${a.name || ""}${a.reading ? ` (${a.reading})` : ""}${persp ? "\n" + persp : ""}`.trim();
  }
  const cands = (r?.candidates || []).slice(0, 8);
  if (!cands.length) return "";
  const def = (r?.deficient || []).map((e: string) => _ELEM_KO[e] || e).join("·");
  const lines = cands.map(
    (c: any) =>
      `- ${c.given}${c.reading ? `(${c.reading})` : ""} · ${c.score}점${c.elements ? ` · 오행 ${(c.elements || []).join("·")}` : ""}`
  );
  return (def ? `보완 오행: ${def}\n` : "") + "[추천 이름]\n" + lines.join("\n");
}

export default function NamingPage() {
  const params = useParams();
  const kind = (["jakmyeong", "gaemyeong", "aho"].includes(params.kind || "") ? params.kind : "jakmyeong") as NamingKind;
  const meta = META[kind];

  const [b, setB] = useState<BirthValue>({ birth_date: "", birth_time: "", unknown_time: false, gender: "male", calendar: "solar", is_leap_month: false , apply_true_solar_time: true, birth_longitude: 126.98 });
  const [surnameKo, setSurnameKo] = useState("");        // 한글 성
  const [surnameHanja, setSurnameHanja] = useState("");  // 선택한 성 한자(복성=2자)
  const [surnameCands, setSurnameCands] = useState<{ char: string; strokes: number; defn: string; is_compound: boolean }[]>([]);
  const [givenKo, setGivenKo] = useState("");            // 개명: 한글 이름
  const [givenSel, setGivenSel] = useState<Record<number, string>>({}); // 음절별 선택 한자
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<ToolResponse | null>(null);

  const needsSurname = meta.needs === "surname" || meta.needs === "current_name";

  // 개명·아호는 '본인' 사주 → 저장된 사주 자동 채움. 작명은 새 인물이라 제외.
  const me = useMe();
  const ensureEntry = useEnsureEntry();
  const filledFor = useRef<number | null>(null);
  useEffect(() => {
    if (kind === "jakmyeong") return;
    if (!me?.saju_profile?.birth_date || filledFor.current === me.id) return;
    filledFor.current = me.id;
    setB((prev) => ({ ...prev, ...profileToBirthValue(me.saju_profile) }));
  }, [me, kind]);

  // 한글 성씨(1~2자, 복성 포함) → 전용 한자 조회
  useEffect(() => {
    const ko = surnameKo.trim();
    setSurnameHanja("");
    if (!/^[가-힣]{1,2}$/.test(ko)) { setSurnameCands([]); return; }
    let alive = true;
    api.lookupSurname(ko).then((r) => {
      if (!alive) return;
      setSurnameCands(r.items);
      if (r.items.length === 1) setSurnameHanja(r.items[0].char); // 후보 1개면 자동 선택
    }).catch(() => { if (alive) setSurnameCands([]); });
    return () => { alive = false; };
  }, [surnameKo]);

  const givenSyllables = useMemo(() => [...givenKo.trim()].filter((c) => /[가-힣]/.test(c)), [givenKo]);
  const givenHanja = givenSyllables.map((_, i) => givenSel[i] || "").join("");
  const givenComplete = givenSyllables.length >= 1 && givenSyllables.every((_, i) => !!givenSel[i]);

  const canSubmit = useMemo(() => {
    if (!b.birth_date) return false;
    if (meta.needs === "surname") return !!surnameHanja;
    if (meta.needs === "current_name") return !!surnameHanja && givenComplete;
    return true;
  }, [b.birth_date, surnameHanja, givenComplete, meta.needs]);

  const reason = !b.birth_date ? "생년월일을 입력해 주세요"
    : (needsSurname && !surnameHanja) ? "성씨의 한자를 선택해 주세요"
    : (meta.needs === "current_name" && !givenComplete) ? "이름의 한자를 모두 선택해 주세요"
    : null;

  async function submit() {
    if (!ensureEntry(kind as EntryMenu)) return;
    setErr(null); setLoading(true); setRes(null);
    const birth: Birth = {
      birth_date: b.birth_date,
      birth_time: resolveBirthTime(b.birth_time, b.unknown_time),
      calendar: b.calendar, gender: b.gender, is_leap_month: b.calendar === "lunar" ? b.is_leap_month : false,
      apply_true_solar_time: !!b.apply_true_solar_time, night_zi_mode: b.night_zi_mode ?? "yaja",
      birth_longitude: b.birth_longitude ?? null, apply_equation_of_time: !!b.apply_equation_of_time,
    };
    try {
      const out = await api.createNaming({
        kind, birth,
        surname: meta.needs === "surname" ? surnameHanja : undefined,
        current_name: meta.needs === "current_name" ? surnameHanja + givenHanja.trim() : undefined,
        reading: meta.needs === "current_name" ? (surnameKo.trim() + givenKo.trim()) : undefined,
      });
      setRes(out);
      setTimeout(() => document.getElementById("tool-result")?.scrollIntoView({ behavior: "smooth" }), 80);
    } catch (e: any) {
      setErr(e?.message || "분석에 실패했어요.");
    } finally { setLoading(false); }
  }

  return (
    <div className="compat-page" key={kind}>
      <header className="compat-hero">
        <div className="compat-hero-badge">{meta.badge}</div>
        <h1>{meta.title}</h1>
        <p>{meta.desc} {kind === "gaemyeong"
          ? <>관법은 정답이 없기에 <b>세 관점(수리·균형·사주보완)</b>으로 진단해요.</>
          : <>수리(81수)·자원오행·발음오행·음양을 종합해 추천해요.</>}</p>
      </header>

      <div className="tool-form">
        {needsSurname && (
          <div className="birth-card" style={{ paddingTop: 18 }}>
            <label className="pc-flabel">성씨 (한글로 입력 → 한자 선택 · 복성 가능)</label>
            <input className="bf-input" placeholder="성을 한글로 · 예: 김 / 사공" maxLength={2}
                   value={surnameKo} onChange={(e) => setSurnameKo(e.target.value)} />
            {surnameCands.length > 0 && (
              <div className="hanja-pick" style={{ marginTop: 8 }}>
                {surnameCands.map((h) => (
                  <button key={h.char} type="button"
                          className={`hanja-chip ${surnameHanja === h.char ? "on" : ""}`}
                          title={glossKo(h.defn) || h.defn}
                          onClick={() => setSurnameHanja(h.char)}>
                    <span className="hc-char">{h.char}</span>
                    <span className="hc-sub">{h.strokes}획{h.is_compound ? "·복성" : ""}</span>
                  </button>
                ))}
              </div>
            )}
            {/^[가-힣]{1,2}$/.test(surnameKo.trim()) && surnameCands.length === 0 && (
              <div className="pc-hint">등록된 성씨가 아니에요.</div>
            )}
            {meta.needs === "current_name" && (
              <>
                <label className="pc-flabel" style={{ marginTop: 12 }}>현재 이름 (한글로 입력 → 한자 선택)</label>
                <input className="bf-input" placeholder="이름을 한글로 · 예: 수현" maxLength={3}
                       value={givenKo} onChange={(e) => { setGivenKo(e.target.value); setGivenSel({}); }} />
                {givenSyllables.map((syl, i) => (
                  <HanjaSyllablePicker key={i} syllable={syl} selected={givenSel[i] || ""}
                                       onPick={(han) => setGivenSel((m) => ({ ...m, [i]: han }))} />
                ))}
                {givenComplete && <div className="pc-hint">선택한 이름: <b>{surnameHanja}{givenHanja}</b></div>}
              </>
            )}
          </div>
        )}
        <EntryFeeNotice menu={kind as EntryMenu} />
        <BirthFields value={b} onChange={(patch) => setB((prev) => ({ ...prev, ...patch }))} />
      </div>

      <div className="compat-actions">
        <button className="compat-cta" disabled={!canSubmit || loading} onClick={submit}>
          {loading
            ? "분석 중…"
            : `${meta.needs === "current_name" ? "이름 진단받기" : "이름 추천받기"}`}
        </button>
        {!canSubmit && reason && <div className="cta-hint">{reason}</div>}
      </div>
      {err && <div className="compat-err">{err}</div>}

      {res && (
        <div id="tool-result" className="compat-result">
          {kind === "gaemyeong" ? <Diagnosis res={res} /> : <Candidates res={res} />}
          <ExplainChat
            streamPath={`/api/tools/${res.tool_id}/messages/stream`}
            isPreview={res.is_preview}
            autoStart={false}
            pdf={{
              docTitle: `인생상담 친구의 ${meta.title}`,
              item: `${meta.title}`,
            }}
            pdfHeader={namingPdfHeader(kind, res.result)}
            feedbackSource="tool"
            feedbackSessionId={res.tool_id}
            suggestFetch={() => api.getToolSuggestions(res.tool_id).then((r) => r.suggestions || [])}
          />
        </div>
      )}
    </div>
  );
}

function Candidates({ res }: { res: ToolResponse }) {
  const r = res.result;
  const cands = r.candidates || [];
  const def = (r.deficient || []).map((e: string) => ({ "木": "목", "火": "화", "土": "토", "金": "금", "水": "수" } as any)[e] || e);
  const [shownCount, setShownCount] = useState(6);   // 처음 6개, '더 보기'로 6개씩 추가
  const shown = cands.slice(0, shownCount);
  return (
    <>
      <div className="cr-headline">
        <span className="cr-grade" style={{ background: "var(--brand-grad)" }}>
          보완 오행: {def.join("·")}
        </span>
        {cands.length > 0 && <span className="cr-count">추천 {cands.length}개</span>}
      </div>
      <div className="name-grid">
        {shown.map((c: any, i: number) => (
          <div key={i} className="name-card">
            <div className="nc-han">{c.given}</div>
            <div className="nc-ko">{c.reading}</div>
            <div className="nc-meta">
              <span className="nc-score">{c.score}점</span>
              <span className="nc-elem">오행 {(c.elements || []).join("·")}</span>
            </div>
            <div className="nc-mean">{glossKo(c.meaning) || "—"}</div>
          </div>
        ))}
        {cands.length === 0 && <div className="compat-err">추천 후보를 찾지 못했어요. 입력을 확인해 주세요.</div>}
      </div>
      {shownCount < cands.length && (
        <div className="name-more">
          <button className="more-btn" onClick={() => setShownCount((n) => n + 6)}>
            더 보기 (+{Math.min(6, cands.length - shownCount)}개 · 점수 높은순)
          </button>
        </div>
      )}
    </>
  );
}

function Diagnosis({ res }: { res: ToolResponse }) {
  const a = res.result.analysis;
  if (!a) return null;
  return (
    <>
      <div className="cr-headline">
        <span className="cr-names">{a.name}</span>
        <span className="cr-grade" style={{ background: "var(--brand-grad)" }}>{a.reading}</span>
      </div>
      <div className="cr-gauges" style={{ maxWidth: 560, margin: "0 auto 20px" }}>
        <div className="cr-sub">관법별 종합</div>
        {Object.values(a.perspectives || {}).map((p: any) => (
          <div key={p.key} className="compat-gauge">
            <div className="cg-head"><span className="cg-label">{p.label}</span>
              <span className="cg-grade" style={{ background: "var(--brand-grad)" }}>{p.grade}</span></div>
            <div className="cg-bar"><div className="cg-fill" style={{ width: `${p.total}%` }} /></div>
            <div className="cg-foot"><strong className="cg-total">{p.total}점</strong></div>
          </div>
        ))}
      </div>
      <div className="cr-factors">
        {Object.values(a.factors || {}).map((f: any) => (
          <div key={f.key} className="factor-card">
            <div className="fc-body">
              <div className="fc-label">{f.label} · {f.score}점</div>
              <div className="fc-item">{f.detail}</div>
            </div>
          </div>
        ))}
      </div>
      <div className="taekil-note">
        4격: {Object.values(a.four_pillars || {}).map((v: any) => `${v.label} ${v.num}(${v.grade})`).join(" · ")}
      </div>
    </>
  );
}
