import { useEffect, useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import { api, type ConsultantPublic, type ConsultationConfig } from "../api";
import { fmtNum } from "../lib/money";
import { useConsultation } from "./ConsultationProvider";

/**
 * 1:1 상담 진입 오버레이 — 사주/타로 2갈래 선택 → 입점 상담사 카드 리스트 → 동의 후 상담 요청.
 *
 * 시스템 위에 별도 오버레이(.pwa-overlay 패턴)로 떠, 하부 라우팅/화면에 영향 없음(요건 9).
 * "상담 신청" → 대화 저장·7일 파기 고지 동의 게이트 → startRequest → 실시간 채팅(ConsultationProvider).
 */

type Branch = "saju" | "tarot";

// 접속 상태 → 배지 라벨 키(consult.*)·CSS 클래스. 라벨은 컴포넌트에서 tr 로 해석.
const PRESENCE: Record<string, { key: string; cls: string }> = {
  online: { key: "presence_online", cls: "on" },
  busy: { key: "presence_busy", cls: "busy" },
  offline: { key: "presence_offline", cls: "off" },
};

export default function ConsultationOverlay({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { t: tr } = useTranslation();
  const { startRequest } = useConsultation();
  const [branch, setBranch] = useState<Branch | null>(null);
  const [items, setItems] = useState<ConsultantPublic[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [pending, setPending] = useState<ConsultantPublic | null>(null); // 동의 게이트 대상
  const [cfg, setCfg] = useState<ConsultationConfig | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) {
      setBranch(null); setItems(null); setErr(null); setPending(null);
    } else if (!cfg) {
      api.consultationConfig().then(setCfg).catch(() => {});
    }
  }, [open]);

  useEffect(() => {
    if (!branch) return;
    let alive = true;
    setLoading(true); setErr(null); setItems(null);
    api.consultants(branch)
      .then((r) => { if (alive) setItems(r.items); })
      .catch((e) => { if (alive) setErr(e?.message || tr("consult.err_list")); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [branch]);

  async function confirmRequest() {
    if (!pending) return;
    setSubmitting(true); setErr(null);
    try {
      await startRequest(pending.id, true);
      setPending(null);
      onClose(); // 진입 오버레이 닫고 채팅 오버레이로 전환
    } catch (e: any) {
      setErr(e?.message || tr("consult.err_request"));
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) return null;

  return (
    <div className="pwa-overlay csl-ov" role="dialog" aria-modal="true" aria-label={tr("consult.dialog_aria")} onClick={onClose}>
      <div className="pwa-modal csl-modal" onClick={(e) => e.stopPropagation()}>
        <button className="csl-x" onClick={onClose} aria-label={tr("consult.close")}>×</button>

        {!branch ? (
          <div className="csl-branch">
            <h3 className="csl-title">{tr("consult.entry_title")}</h3>
            <p className="csl-sub">{tr("consult.entry_sub")}</p>
            <div className="csl-branch-grid">
              <button className="csl-branch-card saju" onClick={() => setBranch("saju")}>
                <span className="csl-branch-ic" aria-hidden>🔮</span>
                <span className="csl-branch-nm">{tr("consult.branch_saju")}</span>
                <span className="csl-branch-dc">{tr("consult.branch_saju_desc")}</span>
              </button>
              <button className="csl-branch-card tarot" onClick={() => setBranch("tarot")}>
                <span className="csl-branch-ic" aria-hidden>🃏</span>
                <span className="csl-branch-nm">{tr("consult.branch_tarot")}</span>
                <span className="csl-branch-dc">{tr("consult.branch_tarot_desc")}</span>
              </button>
            </div>
          </div>
        ) : (
          <div className="csl-list-wrap">
            <div className="csl-list-head">
              <button className="csl-back" onClick={() => setBranch(null)} aria-label={tr("consult.back_aria")}>{tr("consult.back")}</button>
              <h3 className="csl-title">{branch === "saju" ? tr("consult.list_title_saju") : tr("consult.list_title_tarot")}</h3>
            </div>
            {loading && <p className="csl-empty">{tr("consult.loading")}</p>}
            {err && <p className="csl-empty csl-err">{err}</p>}
            {items && items.length === 0 && !loading && (
              <p className="csl-empty">{tr("consult.empty_consultants")}</p>
            )}
            <div className="csl-cards">
              {items?.map((c) => (
                <ConsultantCard key={c.id} c={c} onStart={() => { setErr(null); setPending(c); }} />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 동의 게이트 — 대화 저장·7일 파기 고지 (입장 전 필수) */}
      {pending && (
        <div className="csl-consent-ov" onClick={(e) => { e.stopPropagation(); if (!submitting) setPending(null); }}>
          <div className="csl-consent" onClick={(e) => e.stopPropagation()}>
            <h4>{pending.business_name}</h4>
            <p className="csl-consent-price">
              {tr("consult.consent_price", {
                price: `${fmtNum(pending.price_p)}${tr("pay.pt")}`,
                min: fmtNum(pending.duration_min),
              })}
            </p>
            <p className="csl-consent-note">
              <Trans
                i18nKey="consult.consent_note"
                values={{ days: cfg?.retention_days ?? 7 }}
                components={{ b: <b /> }}
              />
            </p>
            {err && <p className="csl-consent-err">{err}</p>}
            <div className="csl-consent-actions">
              <button className="csl-consent-ok" onClick={confirmRequest} disabled={submitting}>
                {submitting ? tr("consult.consent_submitting") : tr("consult.consent_submit")}
              </button>
              <button className="csl-consent-cancel" onClick={() => setPending(null)} disabled={submitting}>{tr("consult.consent_cancel")}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Stars({ avg }: { avg: number }) {
  const r = Math.round(avg);
  return (
    <span className="csl-stars-ic" aria-hidden>
      {Array.from({ length: 5 }, (_, i) => (
        <span key={i} className={i < r ? "on" : "off"}>★</span>
      ))}
    </span>
  );
}

function ConsultantCard({ c, onStart }: { c: ConsultantPublic; onStart: () => void }) {
  const { t: tr } = useTranslation();
  const p = PRESENCE[c.presence] || PRESENCE.offline;
  const canStart = c.presence === "online";
  return (
    <div className="csl-card">
      <div className="csl-sign">
        {c.signboard_image_url ? (
          <img src={c.signboard_image_url} alt={c.business_name} loading="lazy" />
        ) : (
          <span className="csl-sign-ph" aria-hidden>🪧</span>
        )}
      </div>
      <div className="csl-info">
        <div className="csl-card-top">
          <span className="csl-nm">{c.business_name}</span>
          <span className={`csl-badge ${p.cls}`}>{tr(`consult.${p.key}`)}</span>
        </div>
        {c.intro && <p className="csl-intro">{c.intro}</p>}
        <div className="csl-rating">
          {c.rating_avg != null ? (
            <span className="csl-stars" title={tr("consult.rating_title", { avg: c.rating_avg, count: fmtNum(c.rating_count) })}>
              <Stars avg={c.rating_avg} />
              <b>{c.rating_avg.toFixed(1)}</b>
              <span className="csl-rc">({c.rating_count})</span>
            </span>
          ) : (
            <span className="csl-norate">{tr("consult.no_rating")}</span>
          )}
          <span className="csl-dot" aria-hidden>·</span>
          <span className="csl-scount">{tr("consult.session_count", { count: fmtNum(c.session_count) })}</span>
        </div>
        <div className="csl-meta">
          <span className="csl-price">{fmtNum(c.price_p)}{tr("pay.pt")}</span>
          <span className="csl-dot" aria-hidden>·</span>
          <span className="csl-dur">{tr("consult.dur_min", { n: fmtNum(c.duration_min) })}</span>
        </div>
      </div>
      <button className="csl-start" disabled={!canStart} onClick={onStart}>
        {c.presence === "busy" ? tr("consult.card_busy") : c.presence === "offline" ? tr("consult.card_offline") : tr("consult.card_start")}
      </button>
    </div>
  );
}
