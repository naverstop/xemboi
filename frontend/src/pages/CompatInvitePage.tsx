/** B-10 궁합 초대 랜딩 — 초대받은 사람이 자기 생일만 입력하면 종합 등급 티저를 보여준다.
 * 본 풀이(펜타곤·해설)는 궁합 메뉴(입장료)로 유도 — 초대는 신규 가입 동선. */
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type CompatInviteInfo, type CompatTeaser } from "../api";
import { resolveBirthTime } from "../lib/birthTime";
import BirthFields, { type BirthValue } from "../components/BirthFields";
import RememberBirthToggle, { useBirthMemory } from "../components/RememberBirth";
import PrivacyNotice from "../components/PrivacyNotice";

export default function CompatInvitePage() {
  const { token = "" } = useParams();
  const [info, setInfo] = useState<CompatInviteInfo | null>(null);
  const [b, setB] = useState<BirthValue>({ birth_date: "", birth_time: "", unknown_time: false, gender: "female", calendar: "solar", is_leap_month: false, apply_true_solar_time: true, birth_longitude: 126.98 });
  // 수락자 '본인' 생일 — 공통 기억하기(운영자 원칙: 한 번이라도 입력하면 매칭). 이전 저장본 있으면 자동 채움.
  const { remember, toggleRemember } = useBirthMemory(
    b, (patch) => setB((prev) => ({ ...prev, ...patch })),
  );
  const [teaser, setTeaser] = useState<CompatTeaser | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.compatInviteInfo(token)
      .then((r) => { setInfo(r); if (r.teaser) setTeaser(r.teaser); })
      .catch((e) => setErr(e?.message || "초대를 찾을 수 없어요."));
  }, [token]);

  async function accept() {
    if (busy || !b.birth_date) return;
    setBusy(true); setErr(null);
    try {
      const r = await api.compatInviteAccept(token, {
        birth_date: b.birth_date, birth_time: resolveBirthTime(b.birth_time, b.unknown_time),
        calendar: b.calendar, gender: b.gender, is_leap_month: b.calendar === "lunar" ? b.is_leap_month : false,
        apply_true_solar_time: !!b.apply_true_solar_time, night_zi_mode: b.night_zi_mode ?? "yaja",
        birth_longitude: b.birth_longitude ?? null, apply_equation_of_time: !!b.apply_equation_of_time,
      });
      setTeaser(r.teaser);
    } catch (e: any) {
      setErr(e?.message || "궁합 계산에 실패했어요.");
    } finally { setBusy(false); }
  }

  return (
    <div className="compat-page">
      <PrivacyNotice variant="tool" />
      <header className="compat-hero">
        <div className="compat-hero-badge">宮合</div>
        <h1>궁합 초대장</h1>
        {info && !teaser && (
          <p><b>{info.inviter_name}</b>님이 궁합을 확인하고 싶어 해요. <b>내 생년월일만</b> 입력하면 두 분의 궁합 등급을 바로 볼 수 있어요. 무료!</p>
        )}
        {teaser && <p>두 분의 궁합 결과가 나왔어요 👇</p>}
      </header>

      {err && <div className="compat-err">{err}</div>}

      {info?.status === "expired" && (
        <div className="compat-err">이 초대는 만료됐어요(7일). 상대방에게 새 초대를 부탁해 보세요.</div>
      )}

      {info && info.status === "pending" && !teaser && (
        <div className="tool-form">
          <RememberBirthToggle remember={remember} onToggle={toggleRemember} />
          <BirthFields value={b} onChange={(patch) => setB((prev) => ({ ...prev, ...patch }))} remembered={remember} />
          <p className="am-disc" style={{ margin: "8px 0" }}>
            입력한 생년월일은 궁합 계산과 초대자에게 결과를 이어 보여주는 데에만 쓰여요.
          </p>
          <button className="compat-cta" disabled={!b.birth_date || busy} onClick={accept}>
            {busy ? "궁합 보는 중…" : "💞 우리 궁합 확인하기 (무료)"}
          </button>
        </div>
      )}

      {teaser && (
        <section className="civ-teaser">
          <div className="civ-grade">{teaser.grade}</div>
          <div className="civ-total">{teaser.total}점</div>
          <p className="civ-line">{teaser.line}</p>

          {/* 5축 미리보기 그래프 — 페이드로 가림(맛보기). 정확 수치·근거·해설은 사이트(궁합 메뉴)에서(운영자 지시) */}
          {teaser.axes && teaser.axes.length > 0 && (
            <div className="civ-axes-wrap" aria-hidden>
              <div className="civ-axes">
                {teaser.axes.map((ax) => (
                  <div key={ax.key} className="civ-axis">
                    <span className="lb">{ax.label}</span>
                    <span className="bar"><i style={{ width: `${Math.max(6, Math.min(100, ax.score))}%` }} /></span>
                  </div>
                ))}
              </div>
              <div className="civ-fade">
                <span className="civ-lock">🔒 여기까지는 맛보기</span>
              </div>
            </div>
          )}

          <div className="civ-cta">
            <p><b>자세한 점수와 다섯 영역 풀이, AI 해설</b>은 사이트(궁합 메뉴)에서 제공돼요 —
              합·충·오행·십성·신살을 <b>세 관점</b>으로 깊이 있게 풀어드립니다.</p>
            <Link className="am-dl" to="/compatibility">🔮 사이트에서 전체 궁합 풀이 보기</Link>
          </div>
        </section>
      )}
    </div>
  );
}
