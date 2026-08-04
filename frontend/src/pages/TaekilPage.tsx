/** 택일 — 생년월일 + 용도 + 기간 → 길일 추천. */
import { useState, useEffect, type ReactNode } from "react";
import { api, useMe, refreshMe, PURPOSE_LABELS, type Birth, type TaekilPurpose, type ToolResponse } from "../api";
import PrivacyNotice from "../components/PrivacyNotice";
import { useEnsureEntry, EntryFeeNotice } from "../components/ChargeModal";
import { resolveBirthTime } from "../lib/birthTime";
import ExplainChat from "../components/ExplainChat";
import PastResultsDrawer, { fmtWhen, type PastItem } from "../components/PastResultsDrawer";
import { usePremiumRestore, usePastList } from "../lib/usePastResults";
import BirthFields, { type BirthValue } from "../components/BirthFields";
import RememberBirthToggle, { useBirthMemory } from "../components/RememberBirth";
import ConsultBanner from "../components/ConsultBanner";
import { displayName } from "../lib/displayName";

const PURPOSES = Object.keys(PURPOSE_LABELS) as TaekilPurpose[];

// 상담서 PDF 본문 상단 요약 — 추천 길일 목록
function taekilPdfHeader(r: any): string {
  const best = (r?.best || []).slice(0, 8);
  if (!best.length) return "";
  const lines = best.map((d: any) => `- ${d.date} (${d.ganzhi}) · ${d.score}점 · ${d.grade}`);
  return "[추천 길일]\n" + lines.join("\n");
}

// 사람 입력 구간 라벨 — 아이콘 + 굵은 제목 + 잘 보이는 설명(작은 회색 라벨이 안 보인다는 운영자 지적 반영).
function PersonHd({ icon, label, sub }: { icon: string; label: string; sub?: ReactNode }) {
  return (
    <div className="person-hd">
      <span className="person-hd-ic" aria-hidden>{icon}</span>
      <span className="person-hd-main">{label}</span>
      {sub && <div className="person-hd-sub">{sub}</div>}
    </div>
  );
}

// 용도별 아이콘 (럭셔리 칩 그리드)
const PURPOSE_ICONS: Record<TaekilPurpose, string> = {
  wedding: "💍", birth: "👶", moving: "📦", opening: "🎉", contract: "🤝",
  ceremony: "🕯️", surgery: "🏥", travel: "✈️", general: "🗓️",
};

// 용도별 한 줄 설명(선택 시 안내).
// ※ 엔진은 황도흑도·사주(충형회피/출산은 궁합)·손없는날 3요소만 계산하고
//    용도별로 '가중치'만 다름 → 설명은 가중치 강조점을 그대로 반영(과장 금지).
const PURPOSE_DESC: Record<TaekilPurpose, string> = {
  wedding: "혼례에 좋은 날 — 남자는 재(배우자)·일지, 여자는 관(배우자)·일지가 깨지지 않는 날을 중시하고, 천덕·월덕 길신일엔 가점, 황도길일·손없는날을 함께 봅니다. 아래에 상대(배우자) 명식을 입력하면 신랑·신부 양측을 동시에 보는 정밀 판정으로 바뀝니다(미입력 시 본인 명식만).",
  birth: "그날 태어날 아이의 사주와 부모(입력자)의 궁합을 참고용으로 계산합니다. 출산일은 함부로 정할 수 없어, 추천일은 참고만 하시고 상담사 님과 1:1 상담으로 정하시길 권합니다.",
  moving: "이사·입택에 좋은 날 — 재물(財)·일지(거주)·월지(환경)가 깨지지 않는 날을 중시하고, 그 달 자체가 흉월인지(월운)도 함께 보며, 천덕·월덕 길신일엔 가점, 손없는날·황도길일을 반영합니다.",
  opening: "개업에 좋은 날 — 재물(財)·일지가 깨지지 않는 날을 보고, 돈(財)이 식상(활동)과 합(合)되는 날을 돈을 끌어오는 길일로 봅니다. 황도길일·손없는날도 함께 봅니다.",
  contract: "계약·서명에 좋은 날 — 문서(인수)가 깨지지 않는 날을 보고, 그날의 기운이 문서(인수)와 합(合)되는 날을 계약 길일로 봅니다. 황도길일도 함께 봅니다.",
  ceremony: "고사·제사에 좋은 날 — 황도길일을 가장 중시하고, 사주 조화를 함께 봅니다.",
  surgery: "수술·시술에 좋은 날 — 본인 사주의 충·형 회피를 가장 중시하고, 황도길일을 함께 봅니다.",
  travel: "여행·출행에 좋은 날 — 황도길일을 가장 중시하고, 사주 조화를 함께 봅니다.",
  general: "일반 길일 — 황도길일·사주·손없는날을 고루 반영합니다.",
};

export default function TaekilPage() {
  const [b, setB] = useState<BirthValue>({ birth_date: "", birth_time: "", unknown_time: false, gender: "male", calendar: "solar", is_leap_month: false , apply_true_solar_time: true, birth_longitude: 126.98 });
  const [b2, setB2] = useState<BirthValue>({ birth_date: "", birth_time: "", unknown_time: false, gender: "female", calendar: "solar", is_leap_month: false, apply_true_solar_time: true, birth_longitude: 126.98 });
  const [purpose, setPurpose] = useState<TaekilPurpose>("wedding");
  const [startDate, setStartDate] = useState("");
  const [days, setDays] = useState(60);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<ToolResponse | null>(null);

  // 로그인 사용자: 저장된 본인 사주 자동 채움(사용자별 1회)
  const me = useMe();
  const ensureEntry = useEnsureEntry();
  // 상담서 제목/대상 표기 — ⚠️ 호칭=이메일 아이디 고정(운영자 결정) — lib/displayName.ts
  const who = displayName(me, "접속자");
  // 공통 '기억하기' — 저장본(회원 프로필/비회원 LS) 자동 채움 + 자동 저장
  const { remember, toggleRemember } = useBirthMemory(b, (patch) => setB((prev) => ({ ...prev, ...patch })));
  // 이탈→복귀/새로고침 시 마지막 결과 자동 복원(무차감) + '지난 결과' 목록
  const { restore, remember: rememberResult } = usePremiumRestore<ToolResponse>({
    storageKey: "taekil_last_id",
    getOne: api.getTool,
    apply: (r) => { setRes(r); setTimeout(() => document.getElementById("tool-result")?.scrollIntoView({ behavior: "smooth" }), 80); },
  });
  const past = usePastList<PastItem>(() =>
    api.listTools(["taekil"]).then((r) => r.items.map((it) => ({
      id: it.tool_id,
      title: (PURPOSE_LABELS as Record<string, string>)[it.kind] ? `${(PURPOSE_LABELS as Record<string, string>)[it.kind]} 택일` : "택일",
      subtitle: it.birth_date || undefined, when: fmtWhen(it.created_at),
    }))),
  );

  // 결혼(커플) 택일: 상대 성별 기본값을 본인 성별의 반대로 맞춘다(양측 성별 동일 오입력 축소).
  //   운영자가 원하면 상대 성별을 직접 다시 바꿀 수 있다(본인 성별을 다시 바꾸기 전까지 유지).
  useEffect(() => {
    if (purpose === "wedding") {
      setB2((prev) => ({ ...prev, gender: b.gender === "male" ? "female" : "male" }));
    }
  }, [purpose, b.gender]);

  async function submit() {
    if (!(await ensureEntry("taekil"))) return;
    setErr(null); setLoading(true); setRes(null);
    const birth: Birth = {
      birth_date: b.birth_date, birth_time: resolveBirthTime(b.birth_time, b.unknown_time),
      calendar: b.calendar, gender: b.gender, is_leap_month: b.calendar === "lunar" ? b.is_leap_month : false,
      apply_true_solar_time: !!b.apply_true_solar_time, night_zi_mode: b.night_zi_mode ?? "yaja",
      birth_longitude: b.birth_longitude ?? null, apply_equation_of_time: !!b.apply_equation_of_time,
    };
    // 출산=두 번째 부모(궁합), 결혼=상대(배우자) 명식(③a 커플 정밀택일). 둘 다 선택 입력.
    const usePartner = (purpose === "birth" || purpose === "wedding") && !!b2.birth_date;
    const birth2: Birth | null = usePartner ? {
      birth_date: b2.birth_date, birth_time: resolveBirthTime(b2.birth_time, b2.unknown_time),
      calendar: b2.calendar, gender: b2.gender, is_leap_month: b2.calendar === "lunar" ? b2.is_leap_month : false,
      apply_true_solar_time: !!b2.apply_true_solar_time, night_zi_mode: b2.night_zi_mode ?? "yaja",
      birth_longitude: b2.birth_longitude ?? null, apply_equation_of_time: !!b2.apply_equation_of_time,
    } : null;
    try {
      const out = await api.createTaekil({
        birth, birth2, purpose,
        start_date: startDate || new Date().toISOString().slice(0, 10),
        days,
      });
      setRes(out);
      if (out.tool_id) rememberResult(out.tool_id);   // 재열람 복원용 id 기억(재차감 없이 다시 보기)
      refreshMe();   // 입장료 차감 후 사이드바·FAB 잔액 즉시 반영(패턴 B)
      setTimeout(() => document.getElementById("tool-result")?.scrollIntoView({ behavior: "smooth" }), 80);
    } catch (e: any) {
      setErr(e?.message || "택일에 실패했어요.");
    } finally { setLoading(false); }
  }

  return (
    <div className="compat-page">
      <PrivacyNotice variant="tool" />
      {me && (
        <PastResultsDrawer
          items={past.items} loading={past.loading}
          onOpen={past.refresh} onPick={(id) => restore(id)}
          label="지난 택일" emptyText="아직 저장된 택일 결과가 없어요."
        />
      )}
      <header className="compat-hero">
        <div className="compat-hero-badge">擇日</div>
        <h1>택일</h1>
        <p>사주 조화(재·관·일지·월지)를 중심으로 황도흑도·건제십이신·이십팔수·생기복덕·손없는날을 <b>용도별 비중</b>으로 가중해 가립니다. 관법은 정답이 없어 <b>여러 관점</b>의 추천 1위도 함께 보여드려요.</p>
      </header>

      <div className="tool-form">
        <div className="bf-field">
          <label>용도</label>
          <div className="purpose-grid" role="radiogroup" aria-label="택일 용도">
            {PURPOSES.map((p) => (
              <button key={p} type="button" role="radio" aria-checked={purpose === p}
                      className={`purpose-chip ${purpose === p ? "on" : ""}`}
                      onClick={() => setPurpose(p)}>
                <span className="pp-icon">{PURPOSE_ICONS[p]}</span>
                <span className="pp-label">{PURPOSE_LABELS[p]}</span>
              </button>
            ))}
          </div>
          <div className="pc-hint" style={{ marginTop: 8 }}>
            {purpose === "birth"
              ? <>아래 입력하신 분(부모)을 기준으로, 그날 태어날 <b>아이의 사주와 부모의 궁합</b>이 좋은 날을 찾아드려요.</>
              : PURPOSE_DESC[purpose]}
          </div>
        </div>
        <EntryFeeNotice menu="taekil" />
        {purpose === "birth" && <PersonHd icon="🙋" label="부모 ①" sub="입력하시는 본인(부모)이에요." />}
        {purpose === "wedding" && <PersonHd icon="🙋" label="본인" sub="결혼 당사자 본인의 사주예요." />}
        <RememberBirthToggle remember={remember} onToggle={toggleRemember} />
        <BirthFields value={b} onChange={(patch) => setB((prev) => ({ ...prev, ...patch }))} remembered={remember} />
        {purpose === "birth" && (
          <>
            <PersonHd icon="👪" label="부모 ②"
                      sub={<><b>(선택)</b> 출산 택일의 경우, 부모님의 사주와 연계하여 출산일을 계산하여 최적의 날짜를 추천드립니다.</>} />
            <BirthFields value={b2} onChange={(patch) => setB2((prev) => ({ ...prev, ...patch }))} />
          </>
        )}
        {purpose === "wedding" && (
          <>
            <PersonHd icon="💑" label="상대(배우자)"
                      sub={<><b>(선택)</b> 입력 시 신랑·신부 <b>양측 명식</b>으로 정밀 판정해요 — 성별을 꼭 확인하세요.</>} />
            <BirthFields value={b2} onChange={(patch) => setB2((prev) => ({ ...prev, ...patch }))} />
          </>
        )}
        <div className="bf-field">
          <label>검색 기간</label>
          <div className="bf-time">
            <input className="bf-input" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            <select className="bf-input" style={{ flex: "0 0 110px" }} value={days} onChange={(e) => setDays(Number(e.target.value))}>
              <option value={30}>30일</option><option value={60}>60일</option><option value={90}>90일</option>
            </select>
          </div>
        </div>
      </div>

      <div className="compat-actions">
        <button className="compat-cta" disabled={!b.birth_date || loading} onClick={submit}>
          {loading ? "분석 중…" : "📅 길일 찾기"}
        </button>
        {!b.birth_date && <div className="cta-hint">{purpose === "birth" ? "부모 ① 생년월일을 입력해 주세요" : "생년월일을 입력해 주세요"}</div>}
      </div>
      {err && <div className="compat-err">{err}</div>}

      {res && (
        <div id="tool-result" className="compat-result">
          {res.credits_charged > 0 && (
            <div className="charge-receipt">✓ 입장료 {res.credits_charged.toLocaleString()} P 차감됨</div>
          )}
          <div className="cr-headline">
            <span className="cr-names">{res.result.purpose_label}</span>
            <span className="cr-grade" style={{ background: "var(--brand-grad)" }}>{purpose === "birth" ? "부모" : "본인"} 일지 {res.result.user_day_branch}</span>
          </div>
          {res.result.rule_note && (
            <p style={{ fontSize: 13, lineHeight: 1.55, color: "var(--muted,#5b6472)",
                        background: "var(--soft,#f3f5f8)", padding: "9px 13px", borderRadius: 10, margin: "8px 0 12px" }}>
              💡 {res.result.rule_note}
            </p>
          )}
          {res.result.applied_rule && (
            <div style={{ fontSize: 12.5, margin: "0 0 12px", display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
              <span style={{ fontSize: 11.5, padding: "2px 9px", borderRadius: 999, fontWeight: 700,
                      background: res.result.applied_rule.startsWith("정식") ? "var(--brand-soft,#efe7d6)" : "var(--soft,#f3f5f8)",
                      color: res.result.applied_rule.startsWith("정식") ? "var(--brand,#8a6d3b)" : "var(--muted,#5b6472)",
                      border: "1px solid var(--line,#e6e0d5)" }}>
                적용 관법: {res.result.applied_rule}
              </span>
              <span style={{ color: "var(--ink-400,#8a93a3)" }}>택일은 정답이 없어 적용 관법을 함께 표기합니다.</span>
            </div>
          )}
          {res.result.sewoon_note && (
            <p style={{ fontSize: 12.5, lineHeight: 1.5, color: "var(--muted,#5b6472)",
                        background: "var(--soft,#f3f5f8)", padding: "8px 13px", borderRadius: 10, margin: "0 0 12px",
                        borderLeft: "3px solid var(--brand,#8a6d3b)" }}>
              🗓️ {res.result.sewoon_note}
            </p>
          )}
          {res.result.no_gil ? (
            <div style={{ fontSize: 13, lineHeight: 1.55, color: "var(--danger,#c0392b)",
                          background: "var(--danger-soft,#fdecea)", padding: "10px 13px", borderRadius: 10, margin: "8px 0 10px" }}>
              ⚠ 이 기간에는 뚜렷한 <b>길일이 없어요</b>. 아래는 그나마 나은 <b>차선(참고)</b>일 뿐 ‘추천 길일’이 아닙니다 — 검색 기간을 넓혀 다시 찾아보시길 권합니다.
            </div>
          ) : (
            <div className="cr-sub">추천 길일</div>
          )}
          <div className="taekil-grid">
            {((res.result.no_gil ? res.result.alt : res.result.best) || []).map((d: any, i: number) => (
              <div key={i} className={`day-card ${d.grade === "대길일" ? "best" : ""}`}>
                <div className="dc-date">{d.date}</div>
                <div className="dc-ganzhi">{d.ganzhi}</div>
                <div className="dc-tags">
                  <span className="dc-hwangdo">{d.hwangdo}</span>
                  {d.geonje && <span className="dc-geonje" title={d.geonje_note}>{d.geonje}</span>}
                  {d.su28 && <span className="dc-su28" title={d.su28_note}>{d.su28}</span>}
                  {d.saenggi && <span className={`dc-saenggi ${["생기", "천의", "복덕"].includes(d.saenggi) ? "gil" : ["절체", "화해", "절명"].includes(d.saenggi) ? "hyung" : ""}`} title="생기복덕(본명괘 기준)">{d.saenggi}</span>}
                  {d.sonless && <span className="dc-son">손없는날</span>}
                </div>
                <div className="dc-score">{d.score}점 · {d.grade}</div>
                {(() => {
                  // 차선(흉일) 카드는 모든 경고를, 추천 길일 카드는 어드바이저리(십악대패·월운 흉월·비겁일)만 배지로.
                  const show = (w: string) => res.result.no_gil || /십악대패|월운 흉월|비겁일/.test(w);
                  const ws = (d.warnings || []).filter(show);
                  return ws.length > 0 && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 5 }}>
                      {ws.map((w: string, wi: number) => (
                        <span key={wi} style={{ fontSize: 11, padding: "1px 7px", borderRadius: 999,
                                background: "var(--warn-soft,#fdf3e3)", color: "var(--warn,#9a6b16)",
                                border: "1px solid var(--warn-line,#e6d3a8)" }}>⚠ {w}</span>
                      ))}
                    </div>
                  );
                })()}
                {d.reason && (
                  <div style={{ fontSize: 12, lineHeight: 1.4, marginTop: 5,
                                color: d.reason.startsWith("회피") ? "var(--danger,#c0392b)" : "var(--muted,#5b6472)" }}>
                    {d.reason}
                  </div>
                )}
                {d.best_hours && d.best_hours.length > 0 && (
                  <div className="dc-hours" title="아이-부모 궁합이 좋은 시(時)">
                    🕐 {d.best_hours.map((h: any) => `${h.sijin}(${h.ganzhi})`).join(" · ")}
                  </div>
                )}
              </div>
            ))}
          </div>

          {res.result.perspectives && (
            <div className="taekil-persp">
              <div className="cr-sub">관법별 추천 1위 <span>(정답 없음 — 관점별 비교)</span></div>
              <div className="tp-chips">
                {Object.values(res.result.perspectives).map((p: any) => (
                  <div key={p.label} className="tp-chip">
                    <div className="tp-label">{p.label}</div>
                    {p.locked ? (
                      <div className="tp-date" style={{ color: "var(--muted,#8a93a3)" }}>🔒 로그인 후 공개</div>
                    ) : (
                      <>
                        <div className="tp-date">{p.top_date}</div>
                        <div className="tp-meta">{p.top_ganzhi} · {p.top_score}점</div>
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {(res.result.avoid || []).length > 0 && (
            <div className="taekil-avoid">
              <span className="cr-sub">피하면 좋은 날</span>
              {res.result.avoid.map((d: any, i: number) => (
                <span key={i} className="avoid-chip">{d.date} ({(d.warnings || []).join("/") || d.grade})</span>
              ))}
            </div>
          )}
          <ExplainChat
            streamPath={`/api/tools/${res.tool_id}/messages/stream`}
            isPreview={res.is_preview}
            autoStart={false}
            initialExplain={res.explain}
            entryPaid
            onBeforeExplain={async () => {
              // [운영자 지시] 미결제(프리뷰) '설명' 클릭 → 차감 동의 팝업 → 동의 시 재생성(차감·풀버전)
              if (!res.is_preview) return true;
              if (!me) return true;                 // 비로그인 — 종전 미리보기 정책
              void submit();                        // submit() 이 입장 동의(ensureEntry)·차감·재생성까지 처리 — 이중 팝업 제거
              return false;
            }}
            pdf={{
              docTitle: `${who} 님이 확인한 택일`,
              personLine: `${who} 님`,
              item: `${res.result.purpose_label || PURPOSE_LABELS[purpose]} 택일`,
            }}
            pdfHeader={taekilPdfHeader(res.result)}
            feedbackSource="tool"
            feedbackSessionId={res.tool_id}
            suggestFetch={() => api.getToolSuggestions(res.tool_id).then((r) => r.suggestions || [])}
          />
          {/* 출산 택일: 자동 추천은 참고용 — 상담사 연결 유도(뽀 지시 2026-08-03: '애 낳는데 막 짓게 할 수 없다').
              양 부모 명식이 상담사에게 전달됨(kind=birth). 위치=답변설명(해설) 아래(운영자 지정). */}
          {purpose === "birth" && me && res.tool_id && (
            <ConsultBanner
              title="출산일은 함부로 정할 수 없어 상담사 님과 1:1 상담을 권합니다"
              desc="부모님 두 분의 사주 명식이 상담사에게 그대로 전해져요 — 추천일은 참고만 하시고 함께 정하세요"
              onClick={() =>
                window.dispatchEvent(
                  new CustomEvent("saju:consult-open", {
                    detail: { kind: "birth", refId: res.tool_id, label: "출산 택일 상담" },
                  })
                )
              }
            />
          )}
        </div>
      )}
    </div>
  );
}
