import { useEffect, useState } from "react";
import { api, type ConsultantPublic, type ConsultationConfig } from "../api";
import { useConsultation } from "./ConsultationProvider";

/**
 * 1:1 상담 진입 오버레이 — 사주/타로 2갈래 선택 → 입점 상담사 카드 리스트 → 동의 후 상담 요청.
 *
 * 시스템 위에 별도 오버레이(.pwa-overlay 패턴)로 떠, 하부 라우팅/화면에 영향 없음(요건 9).
 * "상담 신청" → 대화 저장·7일 파기 고지 동의 게이트 → startRequest → 실시간 채팅(ConsultationProvider).
 */

type Branch = "saju" | "tarot";

const PRESENCE: Record<string, { txt: string; cls: string }> = {
  online: { txt: "대기중", cls: "on" },
  busy: { txt: "상담중", cls: "busy" },
  offline: { txt: "오프라인", cls: "off" },
};

export default function ConsultationOverlay({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
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
      .catch((e) => { if (alive) setErr(e?.message || "상담사 목록을 불러오지 못했어요."); })
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
      setErr(e?.message || "상담 신청에 실패했어요.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) return null;

  return (
    <div className="pwa-overlay csl-ov" role="dialog" aria-modal="true" aria-label="1:1 상담" onClick={onClose}>
      <div className="pwa-modal csl-modal" onClick={(e) => e.stopPropagation()}>
        <button className="csl-x" onClick={onClose} aria-label="닫기">×</button>

        {!branch ? (
          <div className="csl-branch">
            <h3 className="csl-title">1:1 상담하기</h3>
            <p className="csl-sub">전문 상담사와 직접 채팅으로 상담하세요.</p>
            <div className="csl-branch-grid">
              <button className="csl-branch-card saju" onClick={() => setBranch("saju")}>
                <span className="csl-branch-ic" aria-hidden>🔮</span>
                <span className="csl-branch-nm">사주 상담하기</span>
                <span className="csl-branch-dc">사주·운세 전문 상담사</span>
              </button>
              <button className="csl-branch-card tarot" onClick={() => setBranch("tarot")}>
                <span className="csl-branch-ic" aria-hidden>🃏</span>
                <span className="csl-branch-nm">타로 상담하기</span>
                <span className="csl-branch-dc">타로 리딩 전문 상담사</span>
              </button>
            </div>
          </div>
        ) : (
          <div className="csl-list-wrap">
            <div className="csl-list-head">
              <button className="csl-back" onClick={() => setBranch(null)} aria-label="뒤로">‹ 뒤로</button>
              <h3 className="csl-title">{branch === "saju" ? "사주 상담" : "타로 상담"}</h3>
            </div>
            {loading && <p className="csl-empty">불러오는 중…</p>}
            {err && <p className="csl-empty csl-err">{err}</p>}
            {items && items.length === 0 && !loading && (
              <p className="csl-empty">현재 상담 가능한 상담사가 없어요.</p>
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
              {pending.price_p.toLocaleString()}P · {pending.duration_min}분 (신청 시 수락 후 차감)
            </p>
            <p className="csl-consent-note">
              원활한 상담과 <b>상담서 발급</b>을 위해 대화 내용이 서버에 저장되며,
              <b> {cfg?.retention_days ?? 7}일 후 자동·완전 파기</b>됩니다. 동의하셔야 상담이 시작돼요.
            </p>
            {err && <p className="csl-consent-err">{err}</p>}
            <div className="csl-consent-actions">
              <button className="csl-consent-ok" onClick={confirmRequest} disabled={submitting}>
                {submitting ? "신청 중…" : "동의하고 상담 신청"}
              </button>
              <button className="csl-consent-cancel" onClick={() => setPending(null)} disabled={submitting}>취소</button>
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
          <span className={`csl-badge ${p.cls}`}>{p.txt}</span>
        </div>
        {c.intro && <p className="csl-intro">{c.intro}</p>}
        <div className="csl-rating">
          {c.rating_avg != null ? (
            <span className="csl-stars" title={`만족도 ${c.rating_avg}/5 · ${c.rating_count}명 평가`}>
              <Stars avg={c.rating_avg} />
              <b>{c.rating_avg.toFixed(1)}</b>
              <span className="csl-rc">({c.rating_count})</span>
            </span>
          ) : (
            <span className="csl-norate">평가 없음</span>
          )}
          <span className="csl-dot" aria-hidden>·</span>
          <span className="csl-scount">상담 {c.session_count.toLocaleString()}건</span>
        </div>
        <div className="csl-meta">
          <span className="csl-price">{c.price_p.toLocaleString()}P</span>
          <span className="csl-dot" aria-hidden>·</span>
          <span className="csl-dur">{c.duration_min}분</span>
        </div>
      </div>
      <button className="csl-start" disabled={!canStart} onClick={onStart}>
        {c.presence === "busy" ? "상담중" : c.presence === "offline" ? "부재중" : "상담 신청"}
      </button>
    </div>
  );
}
