/** B-11 무료 스낵 테스트(바이럴 V3) — 사주 기반 유형 테스트. 무과금·비로그인.
 * /snack = 허브(테스트 2종 카드), /snack/:testId = 개별 테스트(생일 입력→유형 결과→공유). */
import { useEffect, useRef, useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { useTranslation, Trans } from "react-i18next";
import { api, useMe, type Birth, type SnackTest, type SnackResult } from "../api";
import { resolveBirthTime } from "../lib/birthTime";
import BirthFields, { type BirthValue } from "../components/BirthFields";
import RememberBirthToggle, { useBirthMemory } from "../components/RememberBirth";
import DownloadGuard from "../components/DownloadGuard";
import ShareQuotaNote from "../components/ShareQuotaNote";
import PrivacyNotice from "../components/PrivacyNotice";

function Hub() {
  const { t: tr } = useTranslation();
  const [tests, setTests] = useState<SnackTest[]>([]);
  useEffect(() => { api.snackTests().then((r) => setTests(r.tests)).catch(() => {}); }, []);
  return (
    <div className="compat-page">
      <header className="compat-hero">
        <div className="compat-hero-badge">{tr("snack.badge")}</div>
        <h1>{tr("snack.hub_title")}</h1>
        <p><Trans i18nKey="snack.hub_desc" components={{ b: <b /> }} /></p>
      </header>
      <div className="sn-hub">
        {tests.map((t) => (
          <Link key={t.test_id} to={`/snack/${t.test_id}`} className="sn-hub-card">
            {/* 허브 엠블럼(FLUX) — 이모지보다 격을 맞춤. 로드 실패 시 이모지로 폴백. */}
            {t.icon ? (
              <img
                className="sn-hub-art" src={t.icon} alt="" aria-hidden
                onError={(e) => {
                  const el = e.currentTarget;
                  el.style.display = "none";
                  const sib = el.nextElementSibling as HTMLElement | null;
                  if (sib) sib.style.display = "";
                }}
              />
            ) : null}
            <span className="sn-hub-emoji" aria-hidden style={t.icon ? { display: "none" } : undefined}>{t.emoji}</span>
            <b>{t.title}</b>
            <span className="sn-hub-desc">{t.desc}</span>
            <span className="sn-hub-cta">{tr("snack.hub_cta")}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

export default function SnackPage() {
  const { testId } = useParams();
  if (!testId) return <Hub />;
  return <SnackTestView testId={testId} />;
}

function SnackTestView({ testId }: { testId: string }) {
  const { t: tr } = useTranslation();
  const me = useMe();
  const navigate = useNavigate();
  const [meta, setMeta] = useState<SnackTest | null>(null);
  const [b, setB] = useState<BirthValue>({ birth_date: "", birth_time: "", unknown_time: false, gender: "male", calendar: "solar", is_leap_month: false, apply_true_solar_time: true, birth_longitude: 126.98 });
  const [res, setRes] = useState<SnackResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const shareLock = useRef(false);   // 공유 버튼 동기 연타 잠금(state 로는 같은 틱 연타를 못 막음)

  useEffect(() => {
    api.snackTests().then((r) => {
      const m = r.tests.find((t) => t.test_id === testId);
      if (!m) navigate("/snack", { replace: true });
      else setMeta(m);
    }).catch(() => {});
  }, [testId, navigate]);

  // 공통 '기억하기' — 저장본 자동 채움 + 자동 저장(운영자 원칙: 한 번이라도 입력하면 매칭)
  const { remember, toggleRemember } = useBirthMemory(
    b, (patch) => setB((prev) => ({ ...prev, ...patch })),
  );

  async function run() {
    if (busy || !b.birth_date) return;
    setBusy(true); setErr(null);
    const birth: Birth = {
      birth_date: b.birth_date, birth_time: resolveBirthTime(b.birth_time, b.unknown_time),
      calendar: b.calendar, gender: b.gender, is_leap_month: b.calendar === "lunar" ? b.is_leap_month : false,
      apply_true_solar_time: !!b.apply_true_solar_time, night_zi_mode: b.night_zi_mode ?? "yaja",
      birth_longitude: b.birth_longitude ?? null, apply_equation_of_time: !!b.apply_equation_of_time,
    };
    try {
      setRes(await api.runSnack(testId, birth, true));
      setTimeout(() => document.getElementById("sn-result")?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
    } catch (e: any) {
      setErr(e?.message || tr("snack.err_load"));
    } finally { setBusy(false); }
  }

  // [운영자 결정 2026-07-23] 이 공유도 무료 쿼터 집계 대상에 포함한다.
  //   이전엔 /api/share 를 전혀 호출하지 않아, 같은 성격의 '결과 카드 공유'인데도 오늘의 운세는
  //   차감되고 여기만 무제한이었다(관리자 사용통계에서도 누락됐다).
  //   규약은 다른 화면과 동일: **사전 확인 → 공유 → 성공 시에만 집계**.
  async function share() {
    if (!res?.card) return;
    if (shareLock.current) return;      // 동기 연타 잠금(1회 공유에 2회 차감 방지)
    shareLock.current = true;
    try {
      try {
        const q = await api.shareQuota();
        if (!q.unlimited && q.remaining <= 0) {
          alert(tr("snack.share_quota"));
          return;
        }
      } catch (e: any) {
        if (e?.status === 401 || String(e?.code || "") === "login required to share") {
          alert(tr("snack.share_login"));
          return;
        }
        /* 그 외 장애는 공유를 막지 않는다(가용성 우선) */
      }
      const count = async (channel: "kakao" | "link") => {
        try {
          await api.submitShare({ channel });
          window.dispatchEvent(new Event("saju:share-counted"));   // 잔여 배지 즉시 갱신
        } catch { /* 이미 나간 공유는 되돌릴 수 없다 */ }
      };
      try {
        const blob = await fetch(res.card.url).then((r) => r.blob());
        const file = new File([blob], res.card.filename || tr("snack.card_filename"), { type: "image/png" });
        const nav: any = navigator;
        if (nav.canShare?.({ files: [file] })) {
          try {
            await nav.share({ files: [file], title: res.title });
            await count("link");        // 성공 확정 후 집계(취소=AbortError 시 미집계)
          } catch (e: any) {
            if (e?.name !== "AbortError") alert(tr("snack.share_fail"));
          }
          return;
        }
      } catch { /* 폴백 */ }
      try {
        await navigator.clipboard.writeText(window.location.origin + `/snack/${testId}`);
        await count("link");            // 복사 성공이 확인된 뒤에만 집계
        alert(tr("snack.link_copied"));
      } catch { alert(tr("snack.share_hold_save")); }
    } finally {
      shareLock.current = false;
    }
  }

  return (
    <div className="compat-page">
      <PrivacyNotice variant="nostore" />
      <header className="compat-hero">
        <div className="compat-hero-badge">{meta?.badge || tr("snack.badge")}</div>
        <h1>{meta?.title || tr("snack.title_fallback")}</h1>
        <p>{meta?.desc} <Trans i18nKey="snack.free_suffix" components={{ b: <b /> }} /></p>
      </header>

      <div className="tool-form">
        <RememberBirthToggle remember={remember} onToggle={toggleRemember} />
        <BirthFields value={b} onChange={(patch) => setB((prev) => ({ ...prev, ...patch }))} remembered={remember} />
      </div>

      <div className="compat-actions">
        <button className="compat-cta" disabled={!b.birth_date || busy} onClick={run}>
          {busy ? tr("snack.analyzing") : tr("snack.cta_result", { emoji: meta?.emoji || "✨" })}
        </button>
        {!b.birth_date && <div className="cta-hint">{tr("snack.hint_birth")}</div>}
      </div>
      {err && <div className="compat-err">{err}</div>}

      {res && (
        <section id="sn-result" className="sn-result">
          {/* 결과 캐릭터 일러스트(FLUX) — 이모지 원형은 싸구려로 보여 교체(운영자 지적).
              이미지 로드 실패 시에만 이모지로 폴백해 항상 뭔가는 보이게 한다. */}
          <div className={`sn-badge${res.icon ? " sn-badge-art" : ""}`} style={res.icon ? undefined : { background: res.color }}>
            {res.icon ? (
              <img
                src={res.icon}
                alt=""
                aria-hidden
                onError={(e) => {
                  const el = e.currentTarget;
                  const box = el.parentElement;
                  el.style.display = "none";
                  if (box) { box.classList.remove("sn-badge-art"); box.style.background = res.color; }
                }}
              />
            ) : null}
            <span className="sn-badge-emoji" aria-hidden>{res.emoji}</span>
          </div>
          <div className="sn-label" style={{ color: res.color }}>{res.label}</div>
          <p className="sn-headline">{res.headline}</p>
          <p className="sn-body">{res.body}</p>
          {res.meter && (
            <div className="sn-meter" aria-label={`${res.meter.label} ${res.meter.value}/${res.meter.max}`}>
              <span className="sn-meter-label">{res.meter.label}</span>
              <span className="sn-meter-bar">
                <span className="sn-meter-fill" style={{ width: `${Math.round(res.meter.value / Math.max(1, res.meter.max) * 100)}%`, background: res.color }} />
              </span>
              <span className="sn-meter-val">{res.meter.value}/{res.meter.max}</span>
            </div>
          )}
          {res.card && (
            <div className="sn-card-box">
              <img src={res.card.url} alt={tr("snack.card_alt")} />
              <div className="sn-card-actions">
                <button onClick={share}>{tr("snack.share_btn")}</button>
                <DownloadGuard href={res.card.download_url} doneLabel={tr("snack.saved_done")}>{tr("snack.save_btn")}</DownloadGuard>
              </div>
              <ShareQuotaNote className="share-quota-note inline" />
            </div>
          )}
          <p className="am-disc">{res.disclaimer}</p>
          <div className="sn-more">
            <Link to="/snack">{tr("snack.more_tests")}</Link>
            <Link to="/chat">{tr("snack.see_saju")}</Link>
          </div>
        </section>
      )}
    </div>
  );
}
