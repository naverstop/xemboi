/** B-4 부적(符籍) 발행 — 목적 6종 선택 + 생년월일 → 결정적 룰 발행(LLM 아님) + PNG 다운로드.
 * 과금: 생성 시점 amulet_cost_p 차감(관리자 설정, 기본 3,000P) · 실패 시 무과금.
 * 면책: 전통 문화 콘텐츠·오락 목적 — 효험 단정 금지. */
import { useState } from "react";
import { api, useMe, setCachedMe, type Birth, type AmuletPurpose, type AmuletResult } from "../api";
import { resolveBirthTime } from "../lib/birthTime";
import BirthFields, { type BirthValue } from "../components/BirthFields";
import PrivacyNotice from "../components/PrivacyNotice";
import RememberBirthToggle, { useBirthMemory } from "../components/RememberBirth";
import { useCharge } from "../components/ChargeModal";
import AnswerActions from "../components/AnswerActions";
import ExplainChat from "../components/ExplainChat";
import PastResultsDrawer, { fmtWhen, type PastItem } from "../components/PastResultsDrawer";
import { usePremiumRestore, usePastList } from "../lib/usePastResults";
import { displayName } from "../lib/displayName";
import DownloadGuard from "../components/DownloadGuard";

const PURPOSES: { key: AmuletPurpose; emoji: string; label: string; desc: string }[] = [
  { key: "wealth", emoji: "💰", label: "재물", desc: "금전·재수의 기운을 북돋아요" },
  { key: "love", emoji: "💞", label: "애정", desc: "인연·화합의 기운을 열어요" },
  { key: "exam", emoji: "📜", label: "합격·시험", desc: "학업·시험 성취를 기원해요" },
  { key: "health", emoji: "🌿", label: "건강", desc: "무병장수의 기운을 지켜요" },
  { key: "protect", emoji: "🐯", label: "액막이", desc: "삼재·액운을 막아내요" },
  { key: "biz", emoji: "🌅", label: "개업·사업", desc: "사업 번창의 문을 열어요" },
];

export default function AmuletPage() {
  const me = useMe();
  const { openCharge } = useCharge();
  const [b, setB] = useState<BirthValue>({ birth_date: "", birth_time: "", unknown_time: false, gender: "male", calendar: "solar", is_leap_month: false, apply_true_solar_time: true, birth_longitude: 126.98 });
  const [purpose, setPurpose] = useState<AmuletPurpose | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<AmuletResult | null>(null);
  const [flashPurpose, setFlashPurpose] = useState(false);   // 목적 미선택 알림 시 ①번 강조

  const cost = me?.amulet_cost_p ?? 3900;
  // B-7 플러스 패스 — 월 1회 부적 무료(있으면 차감 없음). 표기·사전검사에 반영.
  const freeLeft = me?.active_pass?.amulet_free_remaining ?? 0;
  const who = displayName(me);   // ⚠️ 호칭=이메일 아이디 고정(운영자 결정) — lib/displayName.ts

  // 공통 '기억하기' — 저장본(회원 프로필/비회원 LS) 자동 채움 + 자동 저장
  const { remember, toggleRemember } = useBirthMemory(b, (patch) => setB((prev) => ({ ...prev, ...patch })));
  // 이탈→복귀/새로고침 시 마지막 부적 자동 복원(무차감) + '내 부적' 목록. getTool→AmuletResult 매핑.
  const { restore, remember: rememberResult } = usePremiumRestore<AmuletResult>({
    storageKey: "amulet_last_id",
    getOne: (id) => api.getTool(id).then((t: any) => ({
      ...(t.result || {}),
      tool_id: t.tool_id,
      filename: (t.result && t.result.filename) || "",
      credits_charged: 0,
    } as AmuletResult)),
    apply: (r) => { setRes(r); setTimeout(() => document.getElementById("amulet-result")?.scrollIntoView({ behavior: "smooth", block: "start" }), 80); },
  });
  const past = usePastList<PastItem>(() =>
    api.listTools(["amulet"]).then((r) => r.items.map((it) => ({
      id: it.tool_id,
      title: `${PURPOSES.find((p) => p.key === it.kind)?.label ?? "부적"} 부적`,
      subtitle: it.birth_date || undefined, when: fmtWhen(it.created_at),
    }))),
  );

  async function issue() {
    if (busy) return;
    // 미충족 조건은 비활성 대신 '알림'으로 안내 — 왜 안 되는지 모르는 문제 방지(운영자 지적)
    if (!purpose) {
      window.alert("부적의 목적을 먼저 골라 주세요!\n\n위의 ①번에서 재물·애정·액막이 등 원하는 목적을 선택하면 발행할 수 있어요.");
      setFlashPurpose(true);
      document.querySelector(".am-purposes")?.scrollIntoView({ behavior: "smooth", block: "center" });
      window.setTimeout(() => setFlashPurpose(false), 2600);
      return;
    }
    if (!b.birth_date) { window.alert("생년월일을 입력해 주세요."); return; }
    if (!me) { setErr("부적 발행은 로그인 후 이용할 수 있어요."); return; }
    // 잔액 사전검사 — confirm까지 갔다가 402로 되돌아오는 헛걸음 방지(패스 무료면 통과)
    if (freeLeft <= 0 && (me.balance ?? 0) < cost) {
      openCharge(`부적 발행에는 ${cost.toLocaleString()}P가 필요해요. 충전하면 바로 발행해 드려요.`);
      return;
    }
    const ok = window.confirm(
      `${PURPOSES.find((p) => p.key === purpose)?.label} 부적을 발행할까요?\n\n` +
      (freeLeft > 0
        ? "· 플러스 패스 무료 발행권을 사용합니다 (차감 없음)\n"
        : `· ${cost.toLocaleString()}P가 차감됩니다 (발행 실패 시 무과금)\n`) +
      "· 내 사주와 올해 기운을 규칙으로 읽어 발행 근거를 함께 드려요\n" +
      "· 전통 문화 콘텐츠(오락 목적)로, 특정 효험을 보장하지 않아요",
    );
    if (!ok) return;
    setBusy(true); setErr(null);
    // 이미지 생성물 진행표시는 하단 공통 dock(ProgressDock) — 운영자 결정(인라인 금지)
    const genId = `amulet-${Date.now()}`;
    window.dispatchEvent(new CustomEvent("saju:gen-start", { detail: { id: genId, kind: "amulet" } }));
    const birth: Birth = {
      birth_date: b.birth_date, birth_time: resolveBirthTime(b.birth_time, b.unknown_time),
      calendar: b.calendar, gender: b.gender, is_leap_month: b.calendar === "lunar" ? b.is_leap_month : false,
      apply_true_solar_time: !!b.apply_true_solar_time, night_zi_mode: b.night_zi_mode ?? "yaja",
      birth_longitude: b.birth_longitude ?? null, apply_equation_of_time: !!b.apply_equation_of_time,
    };
    try {
      const r = await api.issueAmulet({ ...birth, purpose });
      setRes(r);
      if (r.tool_id) rememberResult(r.tool_id);   // 재열람 복원용 id 기억(재발행=재차감 없이 다시 보기)
      window.dispatchEvent(new CustomEvent("saju:gen-done", { detail: { id: genId, url: r.url, filename: r.filename } }));
      api.me().then(setCachedMe).catch(() => {});  // 잔액·패스 잔여횟수 갱신
      setTimeout(() => document.getElementById("amulet-result")?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
    } catch (e: any) {
      window.dispatchEvent(new CustomEvent("saju:gen-error", { detail: { id: genId, message: "부적 발행에 실패했어요." } }));
      if (e?.status === 402) openCharge(`부적 발행에는 ${cost.toLocaleString()}P가 필요해요. 충전하면 바로 발행해 드려요.`);
      else if (e?.status === 401) setErr("로그인이 필요해요. 먼저 로그인해 주세요.");
      else setErr(e?.message || "부적 발행에 실패했어요. 잠시 후 다시 시도해 주세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="compat-page">
      <PrivacyNotice variant="tool" />
      {me && (
        <PastResultsDrawer
          items={past.items} loading={past.loading}
          onOpen={past.refresh} onPick={(id) => restore(id)}
          label="내 부적" emptyText="아직 발행한 부적이 없어요."
          note="🕰 발행한 부적은 언제든 다시 볼 수 있어요 — 재열람은 포인트가 차감되지 않아요."
        />
      )}
      <header className="compat-hero">
        <div className="compat-hero-badge">符籍</div>
        <h1>부적 발행</h1>
        <p>
          내 사주의 <b>용신(보강 기운)</b>과 올해의 <b>충·형·해·삼재</b>를 정해진 규칙으로 읽어,
          목적에 맞는 부적을 발행해 드려요. 발행 근거를 함께 보여 드립니다.
          {freeLeft > 0
            ? <b> 이번 주기 무료 발행 {freeLeft}회 남음(플러스 패스)</b>
            : <><b> {cost.toLocaleString()}P</b> · 실패 시 무과금.</>}
        </p>
      </header>

      <h3 className="am-step">1. 목적을 골라 주세요</h3>
      <div className={`am-purposes${flashPurpose ? " flash" : ""}`}>
        {PURPOSES.map((p) => (
          <button
            key={p.key}
            className={`am-purpose${purpose === p.key ? " on" : ""}`}
            onClick={() => setPurpose(p.key)}
          >
            <span className="am-emoji" aria-hidden>{p.emoji}</span>
            <b>{p.label}</b>
            <span className="am-desc">{p.desc}</span>
          </button>
        ))}
      </div>

      <h3 className="am-step">2. 생년월일을 확인해 주세요</h3>
      <div className="tool-form">
        {!me && (
          <div className="cta-hint">🔒 부적 발행은 <b>회원 전용</b>이에요. 로그인하면 저장된 내 사주로 바로 발행할 수 있어요.</div>
        )}
        <RememberBirthToggle remember={remember} onToggle={toggleRemember} />
        <BirthFields value={b} onChange={(patch) => setB((prev) => ({ ...prev, ...patch }))} remembered={remember} />
      </div>

      <div className="compat-actions">
        <button className="compat-cta" disabled={busy} onClick={issue}>
          {busy ? "발행 중…" : freeLeft > 0 ? "🧧 부적 발행 (패스 무료 1회)" : `🧧 부적 발행 (${cost.toLocaleString()}P)`}
        </button>
        {!purpose && <div className="cta-hint">① 위에서 부적의 목적을 먼저 골라 주세요</div>}
        {purpose && !b.birth_date && <div className="cta-hint">생년월일을 입력해 주세요</div>}
      </div>
      {err && <div className="compat-err">{err}</div>}

      {res && (
        <section id="amulet-result" className="am-result">
          {res.credits_charged > 0 && (
            <div className="charge-receipt">✓ 부적 발행 {res.credits_charged.toLocaleString()} P 차감됨</div>
          )}
          <div className="am-paper">
            <img src={res.url} alt={`${res.amulet.name} 부적`} />
          </div>
          <div className="am-info">
            <h2>{res.amulet.name} <small>{res.amulet.hanja}</small></h2>
            <p className="am-line">
              보강 기운 <b style={{ color: res.amulet.color }}>{res.amulet.element} {res.amulet.obang}</b>
              {res.amulet.samjae && <> · 올해 <b>{res.amulet.samjae}</b></>}
            </p>
            <div className="am-reasons">
              <div className="am-reasons-title">발행 근거 (규칙 기반)</div>
              <ul>
                {res.amulet.reasons.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </div>
            <div className="am-actions">
              <DownloadGuard className="am-dl" href={res.download_url} doneLabel="✅ 저장 완료">⤓ 부적 저장 (PNG)</DownloadGuard>
            </div>
            {/* 공용 액션바 — 발행 근거를 복사·공유·상담서 PDF로(6메뉴 표준. 피드백은 message_id 없어 자동 미노출) */}
            <AnswerActions
              text={
                `${res.amulet.name}(${res.amulet.hanja}) 부적 — ${res.amulet.purpose_label}\n` +
                `보강 기운: ${res.amulet.element} ${res.amulet.obang}${res.amulet.samjae ? ` · 올해 ${res.amulet.samjae}` : ""}\n\n` +
                `[발행 근거]\n${res.amulet.reasons.map((r) => `· ${r}`).join("\n")}\n\n${res.amulet.disclaimer}`
              }
              source="tool"
              pdf={{
                docTitle: `${who} 님의 ${res.amulet.purpose_label} 부적`,
                personLine: `${who} 님`,
                item: `부적 발행 (${res.amulet.name})`,
              }}
            />
            <p className="am-disc">{res.amulet.disclaimer}</p>
          </div>
        </section>
      )}

      {/* 해설(무과금)·추가질문(기존 정책: 기본 1,000P/심화 3,000P, 부족 시 충전유도) — 공용 tools 스트림 */}
      {res?.tool_id && (
        <div className="compat-result">
          <ExplainChat
            streamPath={`/api/tools/${res.tool_id}/messages/stream`}
            isPreview={false}
            autoStart={false}
            pdf={{
              docTitle: `${who} 님의 ${res.amulet.purpose_label} 부적`,
              personLine: `${who} 님`,
              item: `부적 발행 (${res.amulet.name})`,
            }}
            pdfHeader={`${res.amulet.name}(${res.amulet.hanja}) 부적 — ${res.amulet.purpose_label}
보강 기운: ${res.amulet.element} ${res.amulet.obang}`}
            feedbackSource="tool"
            feedbackSessionId={res.tool_id}
            suggestFetch={() => api.getToolSuggestions(res.tool_id!).then((r) => r.suggestions || [])}
          />
        </div>
      )}
    </div>
  );
}
