/** B-4 부적(符籍) 발행 — 목적 6종 선택 + 생년월일 → 결정적 룰 발행(LLM 아님) + PNG 다운로드.
 * 과금: 생성 시점 amulet_cost_p 차감(관리자 설정, 기본 3,000P) · 실패 시 무과금.
 * 면책: 전통 문화 콘텐츠·오락 목적 — 효험 단정 금지. */
import { useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import i18n from "../i18n";
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

const PURPOSES: { key: AmuletPurpose; emoji: string }[] = [
  { key: "wealth", emoji: "💰" },
  { key: "love", emoji: "💞" },
  { key: "exam", emoji: "📜" },
  { key: "health", emoji: "🌿" },
  { key: "protect", emoji: "🐯" },
  { key: "biz", emoji: "🌅" },
];
// 목적 라벨·설명 — locales/amulet.ts(p_*/pd_*)에서 로케일별 해석
const purposeLabel = (k: AmuletPurpose): string => i18n.t(`amulet.p_${k}`);
const purposeDesc = (k: AmuletPurpose): string => i18n.t(`amulet.pd_${k}`);

export default function AmuletPage() {
  const { t: tr } = useTranslation();
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
    api.listTools(["amulet"]).then((r) => r.items.map((it) => {
      const p = PURPOSES.find((pp) => pp.key === it.kind);
      return {
        id: it.tool_id,
        title: tr("amulet.past_title", { label: p ? purposeLabel(p.key) : tr("amulet.fallback_label") }),
        subtitle: it.birth_date || undefined, when: fmtWhen(it.created_at),
      };
    })),
  );

  async function issue() {
    if (busy) return;
    // 미충족 조건은 비활성 대신 '알림'으로 안내 — 왜 안 되는지 모르는 문제 방지(운영자 지적)
    if (!purpose) {
      window.alert(tr("amulet.alert_pick_purpose"));
      setFlashPurpose(true);
      document.querySelector(".am-purposes")?.scrollIntoView({ behavior: "smooth", block: "center" });
      window.setTimeout(() => setFlashPurpose(false), 2600);
      return;
    }
    if (!b.birth_date) { window.alert(tr("amulet.alert_birth")); return; }
    if (!me) { setErr(tr("amulet.err_login_only")); return; }
    // 잔액 사전검사 — confirm까지 갔다가 402로 되돌아오는 헛걸음 방지(패스 무료면 통과)
    if (freeLeft <= 0 && (me.balance ?? 0) < cost) {
      openCharge(tr("amulet.need_charge", { cost: cost.toLocaleString() }));
      return;
    }
    const ok = window.confirm(
      `${tr("amulet.confirm_title", { label: purposeLabel(purpose) })}\n\n` +
      (freeLeft > 0
        ? tr("amulet.confirm_pass") + "\n"
        : tr("amulet.confirm_cost", { cost: cost.toLocaleString() }) + "\n") +
      tr("amulet.confirm_basis") + "\n" +
      tr("amulet.confirm_disc"),
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
      window.dispatchEvent(new CustomEvent("saju:gen-error", { detail: { id: genId, message: tr("amulet.gen_fail") } }));
      if (e?.status === 402) openCharge(tr("amulet.need_charge", { cost: cost.toLocaleString() }));
      else if (e?.status === 401) setErr(tr("err.login_required"));
      else setErr(e?.message || tr("amulet.fail_retry"));
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
          label={tr("amulet.past_label")} emptyText={tr("amulet.past_empty")}
          note={tr("amulet.past_note")}
        />
      )}
      <header className="compat-hero">
        <div className="compat-hero-badge">{tr("amulet.hero_badge")}</div>
        <h1>{tr("amulet.hero_title")}</h1>
        <p>
          <Trans i18nKey="amulet.hero_desc" components={{ b: <b /> }} />
          {freeLeft > 0
            ? <b> {tr("amulet.hero_free", { n: freeLeft })}</b>
            : <> <Trans i18nKey="amulet.hero_cost" values={{ cost: cost.toLocaleString() }} components={{ b: <b /> }} /></>}
        </p>
      </header>

      <h3 className="am-step">{tr("amulet.step1")}</h3>
      <div className={`am-purposes${flashPurpose ? " flash" : ""}`}>
        {PURPOSES.map((p) => (
          <button
            key={p.key}
            className={`am-purpose${purpose === p.key ? " on" : ""}`}
            onClick={() => setPurpose(p.key)}
          >
            <span className="am-emoji" aria-hidden>{p.emoji}</span>
            <b>{purposeLabel(p.key)}</b>
            <span className="am-desc">{purposeDesc(p.key)}</span>
          </button>
        ))}
      </div>

      <h3 className="am-step">{tr("amulet.step2")}</h3>
      <div className="tool-form">
        {!me && (
          <div className="cta-hint"><Trans i18nKey="amulet.member_only" components={{ b: <b /> }} /></div>
        )}
        <RememberBirthToggle remember={remember} onToggle={toggleRemember} />
        <BirthFields value={b} onChange={(patch) => setB((prev) => ({ ...prev, ...patch }))} remembered={remember} />
      </div>

      <div className="compat-actions">
        <button className="compat-cta" disabled={busy} onClick={issue}>
          {busy ? tr("amulet.busy") : freeLeft > 0 ? tr("amulet.cta_free") : tr("amulet.cta_paid", { cost: cost.toLocaleString() })}
        </button>
        {!purpose && <div className="cta-hint">{tr("amulet.hint_pick")}</div>}
        {purpose && !b.birth_date && <div className="cta-hint">{tr("amulet.hint_birth")}</div>}
      </div>
      {err && <div className="compat-err">{err}</div>}

      {res && (
        <section id="amulet-result" className="am-result">
          {res.credits_charged > 0 && (
            <div className="charge-receipt">{tr("amulet.receipt", { n: res.credits_charged.toLocaleString() })}</div>
          )}
          <div className="am-paper">
            <img src={res.url} alt={tr("amulet.img_alt", { name: res.amulet.name })} />
          </div>
          <div className="am-info">
            <h2>{res.amulet.name} <small>{res.amulet.hanja}</small></h2>
            <p className="am-line">
              {tr("amulet.boost_label")} <b style={{ color: res.amulet.color }}>{res.amulet.element} {res.amulet.obang}</b>
              {res.amulet.samjae && <> · {tr("amulet.year_label")} <b>{res.amulet.samjae}</b></>}
            </p>
            <div className="am-reasons">
              <div className="am-reasons-title">{tr("amulet.reasons_title")}</div>
              <ul>
                {res.amulet.reasons.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </div>
            <div className="am-actions">
              <DownloadGuard className="am-dl" href={res.download_url} doneLabel={tr("amulet.save_done")}>{tr("amulet.save_btn")}</DownloadGuard>
            </div>
            {/* 공용 액션바 — 발행 근거를 복사·공유·상담서 PDF로(6메뉴 표준. 피드백은 message_id 없어 자동 미노출) */}
            <AnswerActions
              text={
                tr("amulet.txt_head", { name: res.amulet.name, hanja: res.amulet.hanja, purpose: res.amulet.purpose_label }) + "\n" +
                tr("amulet.txt_boost", { elem: res.amulet.element, obang: res.amulet.obang }) +
                (res.amulet.samjae ? tr("amulet.txt_year", { samjae: res.amulet.samjae }) : "") + "\n\n" +
                `${tr("amulet.txt_reasons_head")}\n${res.amulet.reasons.map((r) => `· ${r}`).join("\n")}\n\n${res.amulet.disclaimer}`
              }
              source="tool"
              pdf={{
                docTitle: tr("amulet.pdf_doc", { who, purpose: res.amulet.purpose_label }),
                personLine: tr("amulet.pdf_person", { who }),
                item: tr("amulet.pdf_item", { name: res.amulet.name }),
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
              docTitle: tr("amulet.pdf_doc", { who, purpose: res.amulet.purpose_label }),
              personLine: tr("amulet.pdf_person", { who }),
              item: tr("amulet.pdf_item", { name: res.amulet.name }),
            }}
            pdfHeader={tr("amulet.txt_head", { name: res.amulet.name, hanja: res.amulet.hanja, purpose: res.amulet.purpose_label }) + "\n" +
              tr("amulet.txt_boost", { elem: res.amulet.element, obang: res.amulet.obang })}
            feedbackSource="tool"
            feedbackSessionId={res.tool_id}
            suggestFetch={() => api.getToolSuggestions(res.tool_id!).then((r) => r.suggestions || [])}
          />
        </div>
      )}
    </div>
  );
}
