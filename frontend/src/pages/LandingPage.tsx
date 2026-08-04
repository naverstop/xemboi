/** 첫 화면(랜딩) — 6개 기능을 이미지+설명 섹션으로. 클릭 시 해당 기능으로. */
import { useEffect, useState, type ReactNode } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { api, useMe, type TrustStats } from "../api";
import { entryCost, type EntryMenu } from "../lib/entryFee";
import { fmtMoney } from "../lib/money";
import { Ic, type IcName } from "../components/icons";
import { zodiacStripKeys } from "../lib/zodiacAvatar";
import MyeongriWheel from "../components/MyeongriWheel";
import ReviewStrip from "../components/ReviewStrip";

// 기능별 고급 일러스트(실사 이미지 없을 때 폴백) — 320×200 장면형 ──────
const defs = (id: string, c0 = "#1fbfa8", c1 = "#0d9488") => (
  <defs>
    <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stopColor={c0} /><stop offset="100%" stopColor={c1} />
    </linearGradient>
  </defs>
);
const SVG = ({ children, bg = "#eaf7fe" }: { children: ReactNode; bg?: string }) => (
  <svg viewBox="0 0 320 200" className="fs-svg" preserveAspectRatio="xMidYMid slice">
    <rect width="320" height="200" fill={bg} />
    {children}
  </svg>
);

const Sang = () => (<SVG>{defs("s")}
  <circle cx="262" cy="44" r="40" fill="url(#s)" opacity=".12" />
  <rect x="48" y="40" width="224" height="120" rx="16" fill="#fff" stroke="#d6ecfb" strokeWidth="2" />
  <circle cx="66" cy="58" r="3" fill="#ffb4ab" /><circle cx="78" cy="58" r="3" fill="#ffd591" /><circle cx="90" cy="58" r="3" fill="#a5d6a7" />
  <rect x="66" y="74" width="96" height="22" rx="11" fill="#eef3f7" /><rect x="74" y="82" width="64" height="6" rx="3" fill="#c2cfd9" />
  <rect x="150" y="104" width="104" height="26" rx="13" fill="url(#s)" /><rect x="162" y="114" width="72" height="6" rx="3" fill="#fff" opacity=".85" />
  <rect x="66" y="138" width="70" height="14" rx="7" fill="#eef3f7" />
  <circle cx="250" cy="150" r="20" fill="url(#s)" /><text x="250" y="157" textAnchor="middle" fontSize="20" fontWeight="800" fill="#fff">命</text>
</SVG>);

const Gung = () => (<SVG bg="#fdeef4">{defs("g", "#f48fb1", "#ec407a")}{defs("g2")}
  <circle cx="124" cy="100" r="58" fill="url(#g2)" opacity=".16" />
  <circle cx="196" cy="100" r="58" fill="url(#g)" opacity=".16" />
  <circle cx="124" cy="86" r="20" fill="url(#g2)" /><path d="M96 150c0-18 12-28 28-28s28 10 28 28z" fill="url(#g2)" opacity=".85" />
  <circle cx="196" cy="86" r="20" fill="url(#g)" /><path d="M168 150c0-18 12-28 28-28s28 10 28 28z" fill="url(#g)" opacity=".85" />
  <path d="M160 70c-5-7-18-6-18 5 0 9 18 18 18 18s18-9 18-18c0-11-13-12-18-5z" fill="#fff" stroke="#ec407a" strokeWidth="2" />
  <text x="160" y="44" textAnchor="middle" fontSize="16" fontWeight="800" fill="#c2185b">合</text>
</SVG>);

const Taek = () => (<SVG bg="#eaf7fe">{defs("t")}
  <circle cx="58" cy="48" r="20" fill="#ffd54f" /><path d="M30 100a18 18 0 0136 0z" fill="#fff" opacity=".0" />
  <rect x="84" y="44" width="152" height="120" rx="14" fill="#fff" stroke="#d6ecfb" strokeWidth="2" />
  <rect x="84" y="44" width="152" height="28" rx="14" fill="url(#t)" />
  {[0, 1, 2, 3, 4].flatMap((c) => [0, 1, 2].map((r) => (
    <rect key={`${c}-${r}`} x={100 + c * 26} y={84 + r * 26} width="16" height="16" rx="4"
      fill={c === 2 && r === 1 ? "url(#t)" : "#eef3f7"} />
  )))}
  <path d="M178 102l3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1z" fill="#fff" />
  <circle cx="262" cy="150" r="22" fill="url(#t)" opacity=".9" /><path d="M262 138a12 12 0 100 24 12 12 0 01-8-20" fill="#fff" />
</SVG>);

const Jak = () => (<SVG bg="#eef9f1">{defs("j", "#34c98a", "#10a06a")}
  <rect x="78" y="36" width="120" height="132" rx="10" fill="#fff" stroke="#d3ead9" strokeWidth="2" transform="rotate(-4 138 102)" />
  <rect x="100" y="58" width="80" height="80" rx="6" fill="#f3faf5" transform="rotate(-4 138 102)" />
  <text x="140" y="116" textAnchor="middle" fontSize="56" fontWeight="800" fill="url(#j)" transform="rotate(-4 138 102)">名</text>
  <rect x="206" y="40" width="10" height="92" rx="5" fill="#8d6e63" transform="rotate(18 211 86)" />
  <path d="M232 150c6-8 8-18 6-26-6 4-12 12-14 22z" fill="url(#j)" transform="rotate(18 226 140)" />
  {["#10B981", "#E11D2E", "#F2C200", "#6B7280", "#1D4ED8"].map((c, i) => (
    <circle key={i} cx={92 + i * 17} cy={182} r="6" fill={c} />
  ))}
</SVG>);

const Gae = () => (<SVG bg="#eaf7fe">{defs("ga")}
  <rect x="34" y="78" width="96" height="48" rx="10" fill="#fff" stroke="#d6ecfb" strokeWidth="2" />
  <text x="82" y="110" textAnchor="middle" fontSize="26" fontWeight="700" fill="#9fb3c2">舊</text>
  <rect x="190" y="74" width="96" height="56" rx="12" fill="url(#ga)" />
  <text x="238" y="111" textAnchor="middle" fontSize="30" fontWeight="800" fill="#fff">新</text>
  <path d="M138 100h44m0 0l-12-9m12 9l-12 9" stroke="url(#ga)" strokeWidth="6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
  <circle cx="160" cy="56" r="4" fill="url(#ga)" opacity=".5" /><circle cx="160" cy="146" r="6" fill="url(#ga)" opacity=".4" />
</SVG>);

const Aho = () => (<SVG bg="#fdeef4">{defs("a", "#f06292", "#c2185b")}
  <circle cx="250" cy="60" r="34" fill="url(#a)" opacity=".12" />
  <rect x="96" y="48" width="92" height="104" rx="10" fill="#d81b60" />
  <rect x="108" y="60" width="68" height="80" rx="6" fill="#fff" />
  <text x="142" y="112" textAnchor="middle" fontSize="44" fontWeight="800" fill="#d81b60">號</text>
  <rect x="206" y="40" width="9" height="84" rx="4.5" fill="#6d4c41" transform="rotate(20 210 82)" />
  <path d="M230 138c5-7 7-16 5-23-6 4-11 11-13 19z" fill="url(#a)" transform="rotate(20 224 128)" />
</SVG>);

// 타로 — 미드나잇 골드 아틀리에 감성(네이비 밤하늘 + 아르데코 골드 라인 카드백)
const Taro = () => (<SVG bg="#0d1130">{defs("tr", "#F0DCA0", "#C9A455")}
  {/* 별가루 */}
  {[[28, 30, 1.2], [58, 18, .9], [246, 26, 1.1], [284, 58, .9], [40, 130, .8], [292, 140, 1], [206, 14, .8]].map(([x, y, r], i) => (
    <circle key={i} cx={x} cy={y} r={r} fill="#F0DCA0" opacity=".75" />
  ))}
  {/* 초승달 */}
  <path d="M266 34 A16 16 0 1 0 266 62 A12.5 12.5 0 1 1 266 34 Z" fill="url(#tr)" opacity=".9" />
  {/* 좌우 보조 카드(뒷면) */}
  <g transform="rotate(-14 96 118)">
    <rect x="70" y="70" width="52" height="90" rx="7" fill="#131a42" stroke="#C9A455" strokeOpacity=".55" strokeWidth="1.4" />
    <rect x="76" y="76" width="40" height="78" rx="4" fill="none" stroke="#C9A455" strokeOpacity=".35" strokeWidth=".8" />
    <circle cx="96" cy="115" r="11" fill="none" stroke="#C9A455" strokeOpacity=".6" strokeWidth="1" />
  </g>
  <g transform="rotate(14 224 118)">
    <rect x="198" y="70" width="52" height="90" rx="7" fill="#131a42" stroke="#C9A455" strokeOpacity=".55" strokeWidth="1.4" />
    <rect x="204" y="76" width="40" height="78" rx="4" fill="none" stroke="#C9A455" strokeOpacity=".35" strokeWidth=".8" />
    <circle cx="224" cy="115" r="11" fill="none" stroke="#C9A455" strokeOpacity=".6" strokeWidth="1" />
  </g>
  {/* 중앙 카드 — 선버스트 + 별 */}
  <rect x="130" y="56" width="60" height="104" rx="8" fill="#10142F" stroke="url(#tr)" strokeWidth="2" />
  <rect x="136" y="62" width="48" height="92" rx="5" fill="none" stroke="#C9A455" strokeOpacity=".45" strokeWidth=".8" />
  {[0, 30, 60, 90, 120, 150].map((a) => (
    <line key={a} x1="160" y1="92" x2="160" y2="124" stroke="#C9A455" strokeOpacity=".5" strokeWidth=".9" transform={`rotate(${a} 160 108)`} />
  ))}
  <circle cx="160" cy="108" r="13" fill="#0d1130" stroke="url(#tr)" strokeWidth="1.4" />
  <path d="M160 100l2.2 5 5.3.8-3.8 3.7.9 5.3-4.6-2.4-4.6 2.4.9-5.3-3.8-3.7 5.3-.8z" fill="#F0DCA0" />
</SVG>);

// B-1 신년운세 폴백 아트(이미지 없을 때) — 해돋이+말 실루엣
const Sinny = () => (<SVG bg="#fdf3e7">{defs("sy", "#F6B352", "#E2574C")}
  <circle cx="160" cy="150" r="64" fill="url(#sy)" opacity=".85" />
  <rect x="0" y="150" width="320" height="50" fill="#fff" opacity=".55" />
  <path d="M120 150c8-26 22-38 40-40 12-2 18-10 22-18 4 10 2 20-4 26 14 4 24 14 28 32z" fill="#B03A2E" />
  {[46, 82, 250, 282].map((x, i) => (
    <circle key={i} cx={x} cy={40 + (i % 2) * 18} r="3.5" fill="#E2574C" opacity=".6" />
  ))}
  <text x="160" y="66" textAnchor="middle" fontSize="26" fontWeight="800" fill="#B03A2E">新年</text>
</SVG>);

// B-2 오늘의 운세 폴백 아트 — 아침 해 + 일진 카드
const TodayArt = () => (<SVG bg="#fff7e8">{defs("td", "#F6B352", "#0d9488")}
  <circle cx="160" cy="128" r="52" fill="#F6B352" opacity=".9" />
  <rect x="0" y="128" width="320" height="72" fill="#fff" opacity=".6" />
  {[0, 1, 2, 3, 4].map((i) => (
    <line key={i} x1={160} y1={128} x2={160 + Math.cos((i * 36 - 90) * Math.PI / 180) * 78} y2={128 + Math.sin((i * 36 - 90) * Math.PI / 180) * 78} stroke="#F6B352" strokeWidth="3" opacity=".45" strokeLinecap="round" transform={`rotate(${i * 8 - 16} 160 128)`} />
  ))}
  <rect x="118" y="60" width="84" height="104" rx="10" fill="#fff" stroke="#e8dcc4" strokeWidth="2" transform="rotate(-4 160 112)" />
  <text x="158" y="106" textAnchor="middle" fontSize="30" fontWeight="800" fill="#0d9488" transform="rotate(-4 160 112)">今日</text>
  <text x="158" y="140" textAnchor="middle" fontSize="14" fontWeight="700" fill="#B03A2E" transform="rotate(-4 160 112)">壬午</text>
</SVG>);

const FEATURES: { key: string; to: string; art: JSX.Element; icon: IcName; menu?: EntryMenu }[] = [
  { key: "today", to: "/today", art: <TodayArt />, icon: "calendar" },
  { key: "sang", to: "/chat", art: <Sang />, icon: "chat" },
  { key: "gunghap", to: "/compatibility", art: <Gung />, icon: "heart", menu: "compat" },
  { key: "taekil", to: "/taekil", art: <Taek />, icon: "calendar", menu: "taekil" },
  { key: "tarot", to: "/tarot", art: <Taro />, icon: "tarot", menu: "tarot" },
];

const FAQ = [
  { q: "정확한가요?", a: "합·충·오행·십성·신살을 규칙으로 계산한 근거에 AI 해설을 더합니다. 관법은 정답이 없어 여러 관점을 함께 보여드립니다." },
  { q: "무료인가요?", a: "비로그인은 답변의 50% 미리보기를 제공하고, 로그인하면 무료 질문과 전체 보기를 이용할 수 있어요." },
  { q: "태어난 시를 몰라요.", a: "‘시 모름’으로도 분석할 수 있어요(시주 제외)." },
];

// 살아있는 카드(1~3초 자연 모션 루프) — SVD로 베이크한 webm이 있는 키. 영상→이미지→SVG 3단 폴백.
// ⚠️ 운영자 결정(2026-07-07): SVD 모션은 프레임 후반 캐릭터 표정이 깨져 사용 보류 — 비워 둠(정지 이미지 사용).
const VIDEO_KEYS = new Set<string>([]);

function FeatImg({ k, art }: { k: string; art: JSX.Element }) {
  const [err, setErr] = useState(false);
  const [vidErr, setVidErr] = useState(false);
  if (err) return <div className="fs-img fs-fallback">{art}</div>;
  if (VIDEO_KEYS.has(k) && !vidErr) {
    return (
      <video
        className="fs-video"
        autoPlay
        muted
        loop
        playsInline
        poster={`/features/${k}.jpg`}
        onError={() => setVidErr(true)}
        aria-hidden
      >
        <source src={`/features/${k}.webm`} type="video/webm" />
      </video>
    );
  }
  return <img className="fs-img" src={`/features/${k}.jpg`} alt="" loading="lazy" onError={() => setErr(true)} />;
}

/** B-5 신뢰 지표 — 전부 DB 실측값. 표본이 작으면(콜드스타트) 항목/전체를 숨긴다.
 *  운영자 결정(2026-07): 히어로 본문의 외딴 카드 → 우하단 1:1 상담 버튼 '위' 플로팅 배지로 이동. */
function TrustStrip() {
  const { t } = useTranslation();
  const [s, setS] = useState<TrustStats | null>(null);
  useEffect(() => {
    api.trustStats().then(setS).catch(() => {});
  }, []);
  if (!s) return null;
  const items: { num: string; label: string }[] = [];
  if (s.consultations >= 50) items.push({ num: s.consultations.toLocaleString(), label: t("landing.trust_consult") });
  if (s.satisfaction_pct != null && s.feedback_votes >= 20)
    items.push({ num: `${s.satisfaction_pct}%`, label: t("landing.trust_sat") });
  if (s.reviews >= 5) items.push({ num: s.reviews.toLocaleString(), label: t("landing.trust_reviews") });
  if (!items.length) return null;
  return (
    <div className="lp-trust-float" aria-label={t("landing.trust_aria")}>
      {items.map((it) => (
        <div className="lp-trust-item" key={it.label}>
          <b>{it.num}</b>
          <span>{it.label}</span>
        </div>
      ))}
    </div>
  );
}

export default function LandingPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const me = useMe();
  return (
    <div className="landing">
      {/* 히어로 */}
      <section className="lp-hero">
        <div className="lp-hero-inner">
          <div className="lp-hero-text">
            <span className="lp-eyebrow">{t("landing.eyebrow")}</span>
            <h1>{t("landing.hero_title")}</h1>
            <p>{t("landing.hero_sub")}</p>
            <div className="lp-hero-cta">
              <button className="lp-btn-primary lp-btn-hero" onClick={() => navigate("/chat")}>
                <span className="lp-btn-ic" aria-hidden><Ic name="chat" size={19} /></span> {t("landing.cta_start")}
              </button>
            </div>
            {me ? (
              <div className="lp-hero-note lp-hero-note-in">
                <Trans i18nKey="landing.note_in" components={{ b: <b /> }} />
              </div>
            ) : (
              <div className="lp-hero-note">
                <Trans i18nKey="landing.note_guest" components={{ b: <b /> }} />
              </div>
            )}
            <TrustStrip />
            {/* 12띠 3D 캐릭터 스트립 (장식) — 애기(초년) 버전, 영상 파이프라인과 동일 에셋 */}
            <div className="lp-zodiac-strip" aria-hidden>
              {zodiacStripKeys().map((z) => (
                <img key={z} src={`/zodiac/${z}_초년.jpg`} alt="" loading="lazy" width={44} height={44} />
              ))}
            </div>
          </div>
          {/* 명리 기초 도감(천간·지지 휠) — 정적 命 만다라를 인터랙티브 위젯으로 교체 */}
          <div className="lp-hero-art">
            <MyeongriWheel />
          </div>
        </div>
      </section>

      {/* 6대 기능 섹션 (이미지+설명, 좌우 교차) */}
      <div className="lp-feats-wrap">
        {FEATURES.map((f, i) => (
          <Link key={f.key} to={f.to} className={`feat-section ${i % 2 ? "reverse" : ""}`}>
            <FeatImg k={f.key} art={f.art} />
            <div className="fs-text">
              <span className="fs-badge">{t(`landing.fc.${f.key}.badge`)}</span>
              <h3>{t(`landing.fc.${f.key}.title`)}</h3>
              <p>{t(`landing.fc.${f.key}.desc`)}</p>
              <ul className="fs-bullets">
                {(t(`landing.fc.${f.key}.bullets`, { returnObjects: true }) as string[]).map((b, j) => <li key={j}>{b}</li>)}
              </ul>
              {f.menu ? (
                <span className="fs-fee">{t("landing.fee_entry", { cost: fmtMoney(entryCost(me, f.menu)) })} <em>{t("landing.fee_extra")}</em></span>
              ) : (
                <span className="fs-fee fs-fee-free">{t("landing.fee_free")}</span>
              )}
              <span className="fs-cta"><span className="fs-cta-ic" aria-hidden><Ic name={f.icon} size={17} /></span>{t(`landing.fc.${f.key}.cta`)} →</span>
            </div>
          </Link>
        ))}
      </div>

      {/* B-3 이용 후기 — 승인된 후기가 있을 때만 렌더 */}
      <section className="lp-section">
        <ReviewStrip title={t("landing.reviews_title")} limit={12} />
      </section>

      {/* 무료 안내 CTA */}
      <section className="lp-cta-band">
        <h2>{t("landing.cta2_title")}</h2>
        <p>{t("landing.cta2_sub")}</p>
        <button className="lp-btn-primary lg" onClick={() => navigate("/chat")}>{t("landing.cta2_btn")}</button>
      </section>

      {/* FAQ */}
      <section className="lp-section">
        <h2 className="lp-h2">{t("landing.faq_title")}</h2>
        <div className="lp-faq">
          {(t("landing.faq", { returnObjects: true }) as { q: string; a: string }[]).map((f, i) => (
            <details key={i} className="lp-faq-item">
              <summary>{f.q}</summary>
              <div className="lp-faq-a">{f.a}</div>
            </details>
          ))}
        </div>
      </section>
    </div>
  );
}
