/** 타로 페이지 — 미드나잇 골드 아틀리에 (승인 디자인 v3.1 이식).
 *
 *  흐름: 섹션+질문 → POST /api/tarot(입장료) → 셔플 연출 → 78장 부채꼴에서 직접 뽑기
 *       → POST /picks(서버 확정 셔플·역방향에 매핑, 멱등) → 스프레드 정렬(뒷면)
 *       → 한 장씩 플립 → 전부 플립 시 최초 해석 SSE 스트리밍(무과금, 입장료 포함)
 *       → 추가질문(기본/심화 차감, 402 시 충전 모달) → AnswerActions(복사/공유/PDF/피드백).
 *
 *  ⚠️ 데모 검증 교훈 반영:
 *   - 카드 비행/착지/플립 진행은 rAF 에 의존하지 않음(탭 비활성 시 멈춤)
 *     → 강제 리플로우 + setTimeout + transitionend 이중화.
 *   - 씬 레이어는 전부 페이지 내부 absolute(fixed + blend mode 금지).
 *  카드명/방향/포지션은 서버 결정 데이터를 그대로 렌더(클라 창작 금지).
 */
import ReviewStrip from "../components/ReviewStrip";
import TypingDots from "../components/TypingDots";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type MouseEvent as ReactMouseEvent } from "react";
import {
  api,
  useMe,
  refreshMe,
  ApiError,
  type TarotCreateResp,
  type TarotCard,
  type TarotSnapshot,
  type TarotSessionItem,
} from "../api";
import { streamSSE } from "../lib/sse";
import { renderRich, stripMarkdown } from "../lib/format";
import AnswerActions from "../components/AnswerActions";
import PrivacyNotice from "../components/PrivacyNotice";
import FollowupBilling from "../components/FollowupBilling";
import { useEnsureEntry, EntryFeeNotice, useCharge } from "../components/ChargeModal";
import { displayName } from "../lib/displayName";
import { useBulkSelect } from "../lib/useBulkSelect";
import { useTranslation, Trans } from "react-i18next";
import { fmtNum } from "../lib/money";
import "./tarot.css";

/* ══════════════ 정적 데이터 ══════════════ */

type SectionDef = { key: string; nm: string; n: 7 | 11; exs: string[] };
/* 섹션 구성(백엔드 key + 스프레드 장수). 표시 문구(nm/예시질문 exs)는 로케일(tarot.sec.*)에서
   컴포넌트 내부에서 합성한다. exs[0]은 대표 예시(placeholder에도 사용). */
const SECTION_META: { key: string; n: 7 | 11 }[] = [
  { key: "love", n: 7 },
  { key: "money", n: 7 },
  { key: "career", n: 7 },
  { key: "study", n: 7 },
  { key: "choice", n: 7 },
  { key: "life", n: 11 },
];

const ROMAN = ["Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ", "Ⅵ", "Ⅶ", "Ⅷ", "Ⅸ", "Ⅹ", "Ⅺ"];
/* 7장 말굽(∩) 좌표 — % 단위 (데모 원본) */
/* 가장자리 슬롯(①⑦)은 라벨(고정폭 ~164px, 슬롯 중심 정렬)이 스프레드 영역을 넘지
   않도록 8/92%→11/89%로 안쪽 배치. 라벨 clamp(tarot.css)와 이중 안전. */
/* 상단 아치 y는 카드가 스프레드 박스(440px) 안에 '완전히' 들어오게 잡는다(운영자 보고: 3·4·5번 위 잘림).
   경계식: y%·440 ≥ 카드 절반높이(--cw 92px 기준 79px) + 착지 스케일 1.07(+5.5px) + 기울기(±1.4°, +2px).
   구 y=13%는 카드가 박스 위로 22px 튀어나가 스크롤러 마진(34px)에 의존 — 환경 편차에 잘림. */
const COORD7: [number, number][] = [[11, 68], [22, 44], [36, 26], [50, 20], [64, 26], [78, 44], [89, 68]];
/* 11장 켈틱 크로스 — ②는 ① 위 90도 교차, ⑦~⑩ 스태프 열, ⑪ 종합 조언 */
const COORD11: [number, number][] = [
  [30, 48], [30, 48], [30, 80], [13, 48], [30, 12], [46, 48],
  [74, 82], [74, 60], [74, 38], [74, 16], [90, 49],
];

const FAN_R = 560;       // 부채꼴 반지름(px)
const FAN_SPREAD = 128;  // 부채꼴 전개각(deg)
const DECK_N = 78;

const reduced = typeof window !== "undefined"
  && !!window.matchMedia
  && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ══════════════ 섹션 엠블럼 — 아르데코 골드 라인워크(데모 원본 이식) ══════════════ */
const G = "#D9BC77", GH = "#F0DCA0", GD = "rgba(201,164,85,.45)";
function Emb({ id, children }: { id: string; children: ReactNode }) {
  return (
    <svg viewBox="0 0 160 84" preserveAspectRatio="xMidYMid meet" aria-hidden>
      <radialGradient id={id} cx=".5" cy=".62" r=".6">
        <stop offset="0" stopColor="#C9A455" stopOpacity=".22" />
        <stop offset="1" stopColor="#C9A455" stopOpacity="0" />
      </radialGradient>
      <rect x="10" y="74" width="140" height="1" fill={GD} />
      <ellipse cx="80" cy="58" rx="56" ry="26" fill={`url(#${id})`} />
      {children}
    </svg>
  );
}
const ART: Record<string, JSX.Element> = {
  love: (
    <Emb id="tr-eg-love">
      <g fill="none" stroke={G} strokeWidth="1.3">
        <circle cx="70" cy="48" r="16" /><circle cx="90" cy="48" r="16" />
        <circle cx="70" cy="48" r="12.5" strokeOpacity=".4" strokeWidth=".7" />
        <circle cx="90" cy="48" r="12.5" strokeOpacity=".4" strokeWidth=".7" />
      </g>
      <path d="M80 12 L82 18.5 L88.5 20.5 L82 22.5 L80 29 L78 22.5 L71.5 20.5 L78 18.5 Z" fill={GH} />
      <circle cx="47" cy="30" r="1.3" fill={G} /><circle cx="114" cy="27" r="1.1" fill={G} />
    </Emb>
  ),
  money: (
    <Emb id="tr-eg-money">
      <g fill="none" stroke={G} strokeWidth="1.3">
        <circle cx="80" cy="46" r="20" /><circle cx="80" cy="46" r="15" strokeOpacity=".55" strokeWidth=".8" />
        <path d="M80 18 V24 M80 68 V74 M52 46 H58 M102 46 H108 M60.2 26.2 L64.5 30.5 M95.5 61.5 L99.8 65.8 M99.8 26.2 L95.5 30.5 M64.5 61.5 L60.2 65.8" strokeOpacity=".85" />
      </g>
      <path d="M80 38 L86 46 L80 54 L74 46 Z" fill={GH} />
    </Emb>
  ),
  career: (
    <Emb id="tr-eg-career">
      <g fill="none" stroke={G} strokeWidth="1.3">
        <path d="M56 70 V48 H63 V36 H70 V24 H90 V36 H97 V48 H104 V70" />
        <path d="M76 24 V16 M84 24 V16 M80 16 V9" strokeOpacity=".9" />
        <path d="M63 48 H97 M70 36 H90" strokeOpacity=".4" strokeWidth=".7" />
      </g>
      <path d="M80 3 L81.6 7.4 L86 9 L81.6 10.6 L80 15 L78.4 10.6 L74 9 L78.4 7.4 Z" fill={GH} />
    </Emb>
  ),
  study: (
    <Emb id="tr-eg-study">
      <g fill="none" stroke={G} strokeWidth="1.3">
        <path d="M38 62 Q56 52 80 60 Q104 52 122 62 V34 Q104 24 80 32 Q56 24 38 34 Z" />
        <path d="M80 32 V60" strokeOpacity=".7" />
        <path d="M46 40 Q60 33 74 38 M46 48 Q60 41 74 46 M86 38 Q100 33 114 40 M86 46 Q100 41 114 48" strokeOpacity=".4" strokeWidth=".7" />
      </g>
      <path d="M80 8 L81.8 13.2 L87 15 L81.8 16.8 L80 22 L78.2 16.8 L73 15 L78.2 13.2 Z" fill={GH} />
    </Emb>
  ),
  choice: (
    <Emb id="tr-eg-choice">
      <g fill="none" stroke={G} strokeWidth="1.3">
        <path d="M80 72 V54 Q80 44 66 38 L56 30" />
        <path d="M80 54 Q80 44 94 38 L104 30" />
        <path d="M60 36 L56 30 L63 29" strokeOpacity=".9" /><path d="M100 36 L104 30 L97 29" strokeOpacity=".9" />
      </g>
      <path d="M52 18 L53.6 22 L58 23.5 L53.6 25 L52 29 L50.4 25 L46 23.5 L50.4 22 Z" fill={GH} />
      <path d="M108 18 L109.6 22 L114 23.5 L109.6 25 L108 29 L106.4 25 L102 23.5 L106.4 22 Z" fill={GH} />
    </Emb>
  ),
  life: (
    <Emb id="tr-eg-life">
      <g fill="none" stroke={G} strokeWidth="1.1">
        <circle cx="80" cy="44" r="24" /><circle cx="80" cy="44" r="18" strokeOpacity=".5" strokeWidth=".7" />
        <circle cx="80" cy="44" r="30" strokeOpacity=".3" strokeWidth=".6" strokeDasharray="1 4" />
        <path d="M80 20 V26 M80 62 V68 M56 44 H62 M98 44 H104 M63 27 L67.3 31.3 M92.7 56.7 L97 61 M97 27 L92.7 31.3 M67.3 56.7 L63 61" />
      </g>
      <path d="M87 36 A9.5 9.5 0 1 0 87 52 A7.5 7.5 0 1 1 87 36 Z" fill={GH} />
      <circle cx="90" cy="42" r="1.2" fill={G} />
    </Emb>
  ),
};

/* ══════════════ 유틸 ══════════════ */

function cardbackDom(): HTMLDivElement {
  const d = document.createElement("div");
  d.className = "tr-cardback";
  return d;
}
function fanAngle(i: number): number {
  return -FAN_SPREAD / 2 + FAN_SPREAD * (i / (DECK_N - 1));
}

type QaTurn = { role: "user" | "assistant"; content: string; refined?: boolean; is_preview?: boolean; charged?: number; message_id?: number };

const STORAGE_KEY = "tarot_last_id";

/* ══════════════ 앰비언트 캔버스(별가루·유성) — 장식 전용 ══════════════ */
function useAmbient(canvasRef: React.RefObject<HTMLCanvasElement>, hostRef: React.RefObject<HTMLDivElement>) {
  useEffect(() => {
    const cv = canvasRef.current, host = hostRef.current;
    if (!cv || !host || !cv.getContext) return;
    const cx = cv.getContext("2d");
    if (!cx) return;
    let W = 0, H = 0;
    const DPR = Math.min(window.devicePixelRatio || 1, 2);
    type Star = { x: number; y: number; r: number; a: number; f: number; p: number; vy: number; vx: number; gold: boolean; big: boolean };
    let stars: Star[] = [];
    let t = 0, running = false, disposed = false;
    function resize() {
      if (!host || !cv || !cx) return;
      W = host.clientWidth; H = host.clientHeight;
      cv.width = W * DPR; cv.height = H * DPR;
      cv.style.width = W + "px"; cv.style.height = H + "px";
      cx.setTransform(DPR, 0, 0, DPR, 0, 0);
    }
    function seed() {
      stars = [];
      const n = Math.min(130, Math.floor((W * H) / 11000));
      for (let i = 0; i < n; i++) {
        const gold = Math.random() < 0.24;
        stars.push({
          x: Math.random() * W, y: Math.random() * H,
          r: 0.4 + Math.random() * (gold ? 1.1 : 1.3),
          a: 0.12 + Math.random() * 0.5,
          f: 0.4 + Math.random() * 1.4,
          p: Math.random() * Math.PI * 2,
          vy: 0.02 + Math.random() * 0.09,
          vx: -0.008 - Math.random() * 0.02,
          gold, big: Math.random() < 0.07,
        });
      }
    }
    let meteor: { x: number; y: number; life: number } | null = null;
    let nextMeteor = 400;
    function draw() {
      if (!cx) return;
      cx.clearRect(0, 0, W, H);
      for (const s of stars) {
        const tw = 0.55 + 0.45 * Math.sin(t * s.f + s.p);
        const al = s.a * tw;
        cx.fillStyle = s.gold ? `rgba(233,205,140,${al})` : `rgba(200,215,245,${al})`;
        cx.beginPath();
        cx.arc(s.x, s.y, s.r, 0, 6.2832);
        cx.fill();
        if (s.big && tw > 0.8) {
          cx.strokeStyle = s.gold ? `rgba(233,205,140,${al * 0.5})` : `rgba(200,215,245,${al * 0.5})`;
          cx.lineWidth = 0.6;
          const L = s.r * 5 * tw;
          cx.beginPath();
          cx.moveTo(s.x - L, s.y); cx.lineTo(s.x + L, s.y);
          cx.moveTo(s.x, s.y - L); cx.lineTo(s.x, s.y + L);
          cx.stroke();
        }
        s.y -= s.vy; s.x += s.vx;
        if (s.y < -4) { s.y = H + 4; s.x = Math.random() * W; }
        if (s.x < -4) { s.x = W + 4; }
      }
      if (!meteor && --nextMeteor <= 0) {
        meteor = { x: W * (0.3 + Math.random() * 0.6), y: H * 0.05 + Math.random() * H * 0.2, life: 1 };
        nextMeteor = 600 + Math.floor(Math.random() * 900);
      }
      if (meteor) {
        const m = meteor;
        const g = cx.createLinearGradient(m.x, m.y, m.x - 90, m.y - 42);
        g.addColorStop(0, `rgba(240,232,210,${0.7 * m.life})`);
        g.addColorStop(1, "rgba(240,232,210,0)");
        cx.strokeStyle = g; cx.lineWidth = 1.2;
        cx.beginPath(); cx.moveTo(m.x, m.y); cx.lineTo(m.x - 90, m.y - 42); cx.stroke();
        m.x += 7.5; m.y += 3.5; m.life -= 0.022;
        if (m.life <= 0) meteor = null;
      }
      t += 0.016;
    }
    function loop() {
      if (!running || disposed) return;
      draw();
      requestAnimationFrame(loop);
    }
    resize(); seed();
    const onVis = () => {
      const was = running;
      running = !document.hidden;
      if (running && !was) loop();
    };
    if (reduced) { t = 4; draw(); }
    else {
      running = true; loop();
      document.addEventListener("visibilitychange", onVis);
    }
    let rto = 0;
    const onResize = () => {
      window.clearTimeout(rto);
      rto = window.setTimeout(() => { resize(); seed(); if (reduced) draw(); }, 180);
    };
    window.addEventListener("resize", onResize);
    return () => {
      disposed = true; running = false;
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("resize", onResize);
      window.clearTimeout(rto);
    };
  }, [canvasRef, hostRef]);
}

/* ══════════════ 메인 페이지 ══════════════ */

type Phase = "question" | "shuffle" | "table";

/* 섹션별 예시질문 5개(운영자 승인 문안 2026-07-04). exs[0]은 대표 예시(placeholder에도 사용). */
const SECTIONS: SectionDef[] = [
  { key: "love", nm: "연애 · 재회", n: 7, exs: [
    "이번에 새로 만난 사람, 저와 잘 이어질까요?",
    "헤어진 그 사람과 다시 만날 가능성이 있을까요?",
    "지금 사귀는 사람과 결혼까지 갈 수 있을까요?",
    "그 사람은 지금 저를 어떻게 생각하고 있을까요?",
    "마음에 둔 상대에게 먼저 다가가도 될까요?",
  ] },
  { key: "money", nm: "금전 · 재물", n: 7, exs: [
    "지금 고민 중인 투자, 진행해도 괜찮을까요?",
    "올해 안에 목돈이 들어올 운이 있을까요?",
    "빌려준 돈을 돌려받을 수 있을까요?",
    "지금 시작하려는 부업, 수익이 날까요?",
    "집·차 같은 큰 지출, 지금 해도 될까요?",
  ] },
  { key: "career", nm: "직업 · 사업", n: 7, exs: [
    "준비 중인 이직, 올해 안에 결실이 있을까요?",
    "지금 회사에 남을까요, 옮기는 게 나을까요?",
    "새로 시작한 사업, 자리를 잡을 수 있을까요?",
    "곧 있을 승진·평가 결과가 좋을까요?",
    "지금 하는 일이 저와 잘 맞는 길일까요?",
  ] },
  { key: "study", nm: "학업 · 시험", n: 7, exs: [
    "이번 시험, 지금 방식대로 준비하면 합격할까요?",
    "어느 전공·진로가 저에게 맞을까요?",
    "자격증 공부, 올해 안에 마칠 수 있을까요?",
    "지금의 슬럼프를 어떻게 넘기면 좋을까요?",
    "유학·편입을 지금 준비해도 될까요?",
  ] },
  { key: "choice", nm: "선택의 기로", n: 7, exs: [
    "지금 사는 집을 팔까요, 계속 둘까요?",
    "A와 B 두 제안 중 어느 쪽을 택해야 할까요?",
    "이 관계를 정리할까요, 이어갈까요?",
    "낯선 곳으로 이사·이직을 결정해도 될까요?",
    "지금은 결정을 미룰까요, 밀어붙일까요?",
  ] },
  { key: "life", nm: "인생 종합 · 심층", n: 11, exs: [
    "지금 제 인생의 큰 흐름이 어디로 가고 있나요?",
    "올 한 해 제가 집중해야 할 것은 무엇일까요?",
    "요즘 반복되는 고민, 그 뿌리는 무엇일까요?",
    "제가 지금 놓치고 있는 기회가 있을까요?",
    "앞으로 1년, 제 삶의 가장 큰 변화는 무엇일까요?",
  ] },
];

export default function TarotPage() {
  const me = useMe();
  const { t: tr, i18n } = useTranslation();
  const vi = i18n.language === "vi";
  // 카드명·포지션명 로케일 선택 — vi 는 vi명(없으면 영문/한글 폴백), ko 는 기존 한글 그대로.
  // 백엔드가 name_vi/position_name_vi 를 병기(구 세션엔 없을 수 있어 폴백 유지).
  const cardMainName = (c: TarotCard) => (vi ? (c.name_vi || c.name_en) : c.name_kr);
  const posMainName = (c: TarotCard) => (vi ? (c.position_name_vi || c.position_name) : c.position_name);
  const ensureEntry = useEnsureEntry();
  const { openCharge } = useCharge();
  const memberName = displayName(me, "회원");  // ⚠️ 호칭=이메일 아이디 고정(운영자 결정) — lib/displayName.ts

  const pageRef = useRef<HTMLDivElement>(null);
  const ambientRef = useRef<HTMLCanvasElement>(null);
  useAmbient(ambientRef, pageRef);

  /* 진행 단계 */
  const [phase, setPhase] = useState<Phase>("question");
  const [sec, setSec] = useState<SectionDef | null>(null);
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sess, setSess] = useState<TarotCreateResp | null>(null);
  const [nudgeSec, setNudgeSec] = useState(false);  // 섹션 미선택 상태로 카드섞기 시도 → 섹션 흔들기
  const [nudgeQ, setNudgeQ] = useState(false);       // 질문 미입력 상태로 카드섞기 시도 → 입력창 맥동
  const qInputRef = useRef<HTMLInputElement>(null);
  const readingRef = useRef<HTMLDivElement>(null);   // 보강 완료 시 상단 정렬 대상

  /* 부채꼴/뽑기 */
  const [dealt, setDealt] = useState(false);       // 딜링 애니메이션 시작
  const [dealDone, setDealDone] = useState(false); // 딜레이 제거(호버 반응 복원)
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const pickedRef = useRef<number[]>([]);          // 부채꼴 인덱스(0~77), 뽑은 순서 = 포지션 순서
  const [pickedCount, setPickedCount] = useState(0);
  const [hidden, setHidden] = useState<Set<number>>(() => new Set());
  const [fanGone, setFanGone] = useState(false);

  /* 스프레드/플립 */
  const slotRefs = useRef<(HTMLDivElement | null)[]>([]);
  const tiltsRef = useRef<number[]>([]);
  const [landed, setLanded] = useState<boolean[]>([]);
  const [cards, setCards] = useState<TarotCard[] | null>(null);
  const [picksErr, setPicksErr] = useState<string | null>(null);
  const [flipped, setFlipped] = useState<boolean[]>([]);

  /* 해석/추가질문 (궁합 미러) */
  const [explainStarted, setExplainStarted] = useState(false);
  const [explainText, setExplainText] = useState("");
  const [explainStreaming, setExplainStreaming] = useState(false);
  const [explainFailed, setExplainFailed] = useState(false);
  // 익명 미리보기(마스킹) 상태 — 운영자 보고: 안내 없이 문장 중간에 끊겨 '잘림 버그'처럼 보였고,
  // 액션바(PDF)까지 노출돼 잘린 PDF가 만들어짐. 미리보기면 잠금 안내 + 액션바 숨김(추가질문과 동일 정책).
  const [explainPreview, setExplainPreview] = useState(false);
  const [explainMsgId, setExplainMsgId] = useState<number | undefined>(undefined);
  const [refineStage, setRefineStage] = useState<string | null>(null);
  const [suggests, setSuggests] = useState<string[]>([]);
  const [qaTurns, setQaTurns] = useState<QaTurn[]>([]);
  const [qInput, setQInput] = useState("");
  const [qDepth, setQDepth] = useState<"basic" | "deep">("basic");   // 추가질문 등급(전 메뉴 공통 FollowupBilling)
  const [qStreaming, setQStreaming] = useState(false);
  const explainingRef = useRef(false);
  const acRef = useRef<AbortController | null>(null);
  const timersRef = useRef<number[]>([]);
  const restoredRef = useRef(false);

  const need = sess?.need ?? 0;
  const isCeltic = sess?.spread_type === "celtic11";
  const coords = isCeltic ? COORD11 : COORD7;
  const allPicked = !!sess && pickedCount >= need;
  const allFlipped = !!sess && flipped.length === need && flipped.every(Boolean) && !!cards;
  const spreadLabel = isCeltic ? tr("tarot.spread_celtic") : tr("tarot.spread_horse");

  function timer(fn: () => void, ms: number) {
    const id = window.setTimeout(fn, ms);
    timersRef.current.push(id);
    return id;
  }

  /* 진입 정렬: 다른(스크롤된) 페이지에서 넘어오면 window 스크롤이 남아 타로 헤더가 뷰포트 위로
     밀려 보인다 → 마운트 시 최상단으로 리셋(페인트 전에 처리해 깜빡임 방지). */
  useLayoutEffect(() => {
    window.scrollTo(0, 0);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, []);

  /* 이탈 시: 스트림 취소(GPU 중단) + 타이머 정리 + 비행 카드 제거 */
  useEffect(() => () => {
    try { acRef.current?.abort(); } catch { /* noop */ }
    timersRef.current.forEach((id) => window.clearTimeout(id));
    document.querySelectorAll(".tr-flycard").forEach((el) => el.remove());
  }, []);

  /* 세션 스냅샷으로 화면 재구성(새로고침 복원 + 이력 재열람 공용) */
  function restoreFrom(id: string) {
    api.getTarot(id).then((snap: TarotSnapshot) => {
      if (!snap) return;
      if (!Array.isArray(snap.cards) || snap.cards.length === 0) {
        // 카드 뽑기 전 이탈 — 입장료가 이미 차감된 세션이므로 뽑기 단계부터 이어간다
        const secDef0 = SECTIONS.find((s) => s.key === snap.section) || null;
        const n0 = (snap.need ?? (snap.spread_type === "celtic11" ? 11 : 7)) as number;
        if (!snap.positions || snap.positions.length === 0) return; // 정보 부족 시 새로 시작
        restoredRef.current = false; // 딜링(부채꼴 전개)부터 진행
        setSec(secDef0);
        setQ(snap.question || "");
        setSess({
          tarot_id: snap.tarot_id || id,
          spread_type: snap.spread_type,
          need: n0,
          positions: snap.positions,
          section: snap.section,
          question: snap.question,
        });
        pickedRef.current = [];
        setPickedCount(0);
        setHidden(new Set());
        setFanGone(false);
        setDealt(false); setDealDone(false);
        tiltsRef.current = [];
        setLanded(Array(n0).fill(false));
        setCards(null);
        setFlipped(Array(n0).fill(false));
        setPhase("table");
        return;
      }
      restoredRef.current = true;
      const sorted = [...snap.cards].sort((a, b) => a.position_index - b.position_index);
      const n = (snap.need ?? sorted.length) as number;
      const secDef = SECTIONS.find((s) => s.key === snap.section) || null;
      setSec(secDef);
      setQ(snap.question || "");
      setSess({
        tarot_id: snap.tarot_id || id,
        spread_type: snap.spread_type,
        need: n,
        positions: snap.positions && snap.positions.length ? snap.positions : sorted.map((c) => posMainName(c)),
        section: snap.section,
        question: snap.question,
      });
      pickedRef.current = Array.from({ length: n }, (_, i) => i); // 서버 확정 완료 — 자리 채움용
      setPickedCount(n);
      setFanGone(true);
      setDealt(true); setDealDone(true);
      // 켈틱 ②(장애물)는 90도 교차 — 복원 시에도 재적용(미적용 시 현재 카드 위에 수직으로 겹쳐 1장처럼 보임)
      tiltsRef.current = Array.from({ length: n }, (_, i) =>
        (snap.spread_type === "celtic11" && i === 1 ? 90 : 0) + Math.round((Math.random() * 2.8 - 1.4) * 10) / 10);
      setLanded(Array(n).fill(true));
      setCards(sorted);
      setFlipped(Array(n).fill(true));
      setPhase("table");
      // 메시지 이력 복원: 첫 assistant = 최초 해석, 이후 user/assistant 쌍 = 추가질문
      const msgs = snap.messages || [];
      const firstA = msgs.findIndex((m) => m.role === "assistant" && (m.content || "").trim());
      if (firstA >= 0) {
        setExplainStarted(true);
        setExplainText(msgs[firstA].content);
        // 익명 미리보기 마스킹 복원 — 안내 없이 중간에 끊긴 것처럼 보이지 않게 잠금 상태 반영
        setExplainPreview(!!(msgs[firstA].is_preview && !msgs[firstA].preview_revealed));
        if (typeof msgs[firstA].id === "number") setExplainMsgId(msgs[firstA].id);
        const rest: QaTurn[] = [];
        for (let i = firstA + 1; i < msgs.length; i++) {
          const m = msgs[i];
          if (!m.content || !m.content.trim()) continue;
          if (m.role === "user" || m.role === "assistant") rest.push({ role: m.role, content: m.content });
        }
        setQaTurns(rest);
        loadSuggests(snap.tarot_id || id);
      }
      // 해석 전 이탈이면 explainStarted=false → 전부 플립 상태라 자동으로 최초 해석 재요청
    }).catch(() => { sessionStorage.removeItem(STORAGE_KEY); });
  }

  /* ── 새로고침 복원: 마지막 세션 재구성 ── */
  useEffect(() => {
    const id = sessionStorage.getItem(STORAGE_KEY);
    if (id) restoreFrom(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ── 세션 이력(항목8·9) — 로그인 사용자만 목록/삭제 ── */
  const [sessions, setSessions] = useState<TarotSessionItem[]>([]);
  const [maxSessions, setMaxSessions] = useState(20);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const sel = useBulkSelect<string>();          // 기록 드로어 다중선택(체크 → 일괄삭제)
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const loggedIn = !!me;

  async function refreshSessions() {
    if (!loggedIn) return;
    try {
      const r = await api.listTarot();
      setSessions(r.items || []);
      setMaxSessions(r.max_sessions || 20);
    } catch { /* 무시 */ }
  }
  useEffect(() => { if (loggedIn) refreshSessions(); /* eslint-disable-next-line */ }, [loggedIn]);

  function openSession(id: string) {
    if (id === sess?.tarot_id) { setDrawerOpen(false); return; }
    try { acRef.current?.abort(); } catch { /* noop */ }
    timersRef.current.forEach((t) => window.clearTimeout(t));
    document.querySelectorAll(".tr-flycard").forEach((el) => el.remove());
    // 상태 초기화 후 재구성
    setExplainStarted(false); setExplainText(""); setExplainStreaming(false); setExplainPreview(false);
    setExplainMsgId(undefined); setRefineStage(null);
    setSuggests([]); setQaTurns([]); setQInput(""); setQStreaming(false);
    setCards(null); setFlipped([]); setLanded([]); setPicksErr(null);
    sessionStorage.setItem(STORAGE_KEY, id);
    restoreFrom(id);
    setDrawerOpen(false);
    scrollTop();
  }

  async function removeSession(id: string, e: ReactMouseEvent) {
    e.stopPropagation();
    if (!window.confirm(tr("tarot.del_confirm"))) return;
    try {
      await api.deleteTarot(id);
      setSessions((cur) => cur.filter((s) => s.tarot_id !== id));
      if (id === sess?.tarot_id) newReading();  // 현재 열람 중 세션 삭제 → 새 리딩
    } catch { alert(tr("tarot.del_fail")); }
  }

  // 체크한 기록 일괄삭제 — 서버 단일 요청(개별 DELETE 반복의 레이트리밋·부분실패 회피). 한 번만 확인.
  async function bulkDeleteSessions() {
    const ids = [...sel.selected];
    if (ids.length === 0 || bulkDeleting) return;
    if (!window.confirm(`선택한 ${ids.length}개 타로 기록을 삭제할까요?\n삭제한 기록은 복구할 수 없어요.`)) return;
    setBulkDeleting(true);
    try {
      await api.bulkDeleteTarot(ids);
    } catch { alert("일부 기록을 삭제하지 못했어요. 잠시 후 다시 시도해 주세요."); }
    setBulkDeleting(false);
    sel.clear();
    setSessions((cur) => cur.filter((s) => !ids.includes(s.tarot_id)));
    if (sess?.tarot_id && ids.includes(sess.tarot_id)) newReading();
  }

  function scrollTop() {
    // 마운트 시 리셋(window.scrollTo(0,0))과 동일 기준으로 통일 — pageRef.scrollIntoView(block:"start")는
    // .container 상단 여백(20px)을 지나쳐 패널이 뷰포트 상단에 붙어 진입 화면과 레이아웃이 달라진다.
    window.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
  }
  /* 보강/해석 완료 시 리딩 패널 상단으로 정렬(리플로우 후 실행) — 화면이 아래로 밀려 재확인해야 하는 문제 방지.
     단, 무조건 이동하면 안 된다(운영자 보고: 카드 아치가 뷰포트 상단에 잘린 채 멈춤):
     ① 사용자가 스프레드(카드)를 보는 중(리딩이 화면 밖 아래)이면 강제로 끌어내리지 않는다.
     ② 스트리밍 중 문서가 아직 짧아 목표까지 못 올라가면(스크롤 캡핑) 스킵 — 완료 시 재호출이 정렬한다.
     둘 다 어기면 자동 스크롤이 최대치/사용자 휠과 경합해 3·4·5번 카드 상단이 잘린 화면에서 정지한다. */
  function scrollToReading() {
    timer(() => {
      const el = readingRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      if (r.top > window.innerHeight - 80) return;                       // ① 리딩이 시야 밖(카드 보는 중)
      const want = r.top + window.scrollY - 70;                          // scroll-margin-top(70px) 반영 목표
      const max = document.documentElement.scrollHeight - window.innerHeight;
      if (want > max + 4) return;                                        // ② 캡핑 — 완전 정렬 불가면 이동 안 함
      el.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
    }, 60);
  }

  /* ── 1. 질문 → 세션 생성(입장료) → 셔플 ── */
  const canGo = !!sec && q.trim().length >= 5 && !creating;
  async function submit() {
    if (creating) return;
    // 미충족 사유별 안내(항목2): 하드 disabled 대신 눌러도 왜 안 되는지 알린다.
    if (!sec) {
      setNudgeSec(true);
      timer(() => setNudgeSec(false), 1600);
      pageRef.current?.querySelector(".tr-secgrid")?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "center" });
      return;
    }
    if (q.trim().length < 5) {
      setNudgeQ(true);
      timer(() => setNudgeQ(false), 2400);
      qInputRef.current?.focus();
      qInputRef.current?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "center" });
      return;
    }
    if (!(await ensureEntry("tarot"))) return;
    setErr(null);
    setCreating(true);
    try {
      const out = await api.createTarot(sec.key, q.trim());
      sessionStorage.setItem(STORAGE_KEY, out.tarot_id);
      refreshMe();   // 입장료 차감 후 사이드바·FAB 잔액 즉시 반영(패턴 B)
      // 상태 초기화
      restoredRef.current = false;
      pickedRef.current = [];
      setPickedCount(0);
      setHidden(new Set());
      setFanGone(false);
      setDealt(false); setDealDone(false);
      tiltsRef.current = [];
      setLanded(Array(out.need).fill(false));
      setCards(null); setPicksErr(null);
      setFlipped(Array(out.need).fill(false));
      setExplainStarted(false); setExplainText(""); setExplainMsgId(undefined); setExplainPreview(false);
      setSuggests([]); setQaTurns([]); setQInput("");
      setSess(out);
      setPhase("shuffle");
      scrollTop();
      if (loggedIn) refreshSessions();  // 방금 만든 세션을 기록 목록에 반영
      timer(() => { setPhase("table"); scrollTop(); }, reduced ? 250 : 2700);
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 402) {
        openCharge(tr("tarot.charge_entry"));
      } else if (e instanceof ApiError && e.status === 409) {
        // 세션 20개 상한(입장료는 차감되지 않음) — 기록 정리 안내
        setDrawerOpen(true);
        refreshSessions();
        alert(tr("tarot.sessions_full", { max: maxSessions }));
      } else if (e?.message === "SESSION_EXPIRED") {
        /* notifySessionExpired 가 처리 */
      } else {
        setErr(e?.message || tr("tarot.create_fail"));
      }
    } finally {
      setCreating(false);
    }
  }

  /* 셔플 카드 연출 파라미터(세션마다 고정 랜덤) */
  const shufCards = useMemo(
    () => Array.from({ length: 15 }, (_, i) => ({
      i,
      dur: 0.55 + Math.random() * 0.35,
      del: Math.random() * 0.9,
    })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sess?.tarot_id],
  );

  /* 테이블 진입 시 딜링(부채꼴 전개) 시작 */
  useEffect(() => {
    if (phase !== "table" || dealt || restoredRef.current) return;
    const t1 = timer(() => setDealt(true), 40);
    const t2 = timer(() => setDealDone(true), reduced ? 100 : 120 + DECK_N * 9 + 500);
    return () => { window.clearTimeout(t1); window.clearTimeout(t2); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase]);

  /* ── 3. 뽑기 → 슬롯 비행(강제 리플로우 + setTimeout, rAF 미사용) ── */
  function pick(fanIdx: number, el: HTMLElement) {
    if (!sess || cards) return; // 서버 확정 후에는 재선택 불가
    if (pickedRef.current.length >= sess.need) return;
    if (pickedRef.current.includes(fanIdx)) return;
    const slotIdx = pickedRef.current.length;
    pickedRef.current.push(fanIdx);
    setPickedCount(pickedRef.current.length);
    setHidden((prev) => { const nx = new Set(prev); nx.add(fanIdx); return nx; });
    setHoverIdx(null);

    const r1 = el.getBoundingClientRect();
    const th = fanAngle(fanIdx);
    const base = isCeltic && slotIdx === 1 ? 90 : 0; // 켈틱 ②: 90도 교차
    const tilt = base + Math.round((Math.random() * 2.8 - 1.4) * 10) / 10;
    tiltsRef.current[slotIdx] = tilt;

    const sx = window.scrollX || 0, sy = window.scrollY || 0;
    const fly = document.createElement("div");
    fly.className = "tr-flycard";
    fly.appendChild(cardbackDom());
    fly.style.width = r1.width + "px"; fly.style.height = r1.height + "px";
    fly.style.left = (r1.left + r1.width / 2 + sx) + "px";
    fly.style.top = (r1.top + r1.height / 2 + sy) + "px";
    fly.style.transform = `translate(-50%,-50%) rotate(${th}deg)`;
    document.body.appendChild(fly);

    let done = false;
    const settle = () => {
      if (done) return;
      done = true;
      fly.remove();
      setLanded((arr) => { const nx = [...arr]; nx[slotIdx] = true; return nx; });
    };
    fly.addEventListener("transitionend", (e) => {
      if (e.propertyName === "left" || e.propertyName === "top") settle();
    });

    // 강제 리플로우 후 목적지 지정 — rAF 의존 제거(탭 비활성에도 타이머로 진행 보장)
    void fly.offsetWidth;
    const slot = slotRefs.current[slotIdx];
    if (slot) {
      const r2 = slot.getBoundingClientRect();
      fly.classList.add("aloft");
      fly.style.left = (r2.left + r2.width / 2 + (window.scrollX || 0)) + "px";
      fly.style.top = (r2.top + r2.height / 2 + (window.scrollY || 0)) + "px";
      fly.style.width = r2.width + "px"; fly.style.height = r2.height + "px";
      fly.style.transform = `translate(-50%,-50%) rotate(${tilt}deg)`;
    }
    timer(() => { fly.classList.remove("aloft"); fly.classList.add("landing"); }, reduced ? 0 : 400);
    timer(settle, reduced ? 30 : 700);

    if (pickedRef.current.length === sess.need) onAllPicked();
  }

  function onAllPicked() {
    setFanGone(true);
    submitPicks();
    scrollTop();
    // 안전망: 남은 비행 카드 정리 + 모든 슬롯 착지 보장
    timer(() => {
      document.querySelectorAll(".tr-flycard").forEach((el) => el.remove());
      setLanded((arr) => arr.map(() => true));
    }, reduced ? 80 : 900);
  }

  async function submitPicks() {
    if (!sess) return;
    setPicksErr(null);
    try {
      const r = await api.tarotPicks(sess.tarot_id, pickedRef.current.slice());
      const sorted = [...r.cards].sort((a, b) => a.position_index - b.position_index);
      setCards(sorted);
    } catch (e: any) {
      setPicksErr(e?.message || tr("tarot.picks_fail"));
    }
  }

  /* ── 4. 플립 ── */
  function flip(idx: number) {
    if (!sess || !cards) return;                       // 서버 확정 전 잠금
    if (pickedRef.current.length < sess.need) return;  // 다 뽑기 전 잠금
    setFlipped((arr) => {
      if (arr[idx]) return arr;
      const nx = [...arr];
      nx[idx] = true;
      return nx;
    });
  }
  function flipAll() {
    if (!sess || !cards) return;                       // 서버 확정 전 잠금
    if (pickedRef.current.length < sess.need) return;  // 다 뽑기 전 잠금
    setFlipped((arr) => arr.map(() => true));
  }
  const flippedCount = flipped.filter(Boolean).length;

  /* 전부 플립 → 최초 해석 자동 시작(입장료 포함 무과금) */
  useEffect(() => {
    if (!sess || !cards || explainStarted) return;
    if (flipped.length === sess.need && flipped.every(Boolean)) {
      const t = timer(() => startExplain(sess.tarot_id), reduced ? 100 : 900);
      return () => window.clearTimeout(t);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flipped, cards, sess, explainStarted]);

  async function loadSuggests(tid: string) {
    try { setSuggests((await api.getTarotSuggestions(tid)).suggestions || []); } catch { /* 무시 */ }
  }

  /* 스트림이 'done' 없이 끊긴 경우(모바일 절전·네트워크) — 서버는 이어서 완성·저장했을 수
     있으므로(실사례: 화면은 "펜타클 5 (Fiv"에서 잘렸는데 서버 저장본은 5,873자 완본) 저장본을
     폴링 재동기화한다. 성공 시 전체 텍스트로 교체. */
  async function resyncExplain(tid: string): Promise<boolean> {
    for (let i = 0; i < 8; i++) {
      try {
        const snap = await api.getTarot(tid);
        const m = (snap.messages || []).find((x) => x.role === "assistant" && (x.content || "").trim());
        if (m) {
          setExplainText(m.content);
          setExplainPreview(!!(m.is_preview && !m.preview_revealed));  // 익명 미리보기면 잠금 안내 유지
          if (typeof m.id === "number") setExplainMsgId(m.id);
          return true;
        }
      } catch { /* 일시 오류 — 다음 폴링 */ }
      await new Promise((r) => setTimeout(r, 5000)); // 서버가 아직 생성 중일 수 있음(보강 포함 수십 초)
    }
    return false;
  }

  async function startExplain(tid: string, isRetry = false) {
    if (explainingRef.current) return;
    setExplainStarted(true);
    setExplainFailed(false);
    setExplainStreaming(true); explainingRef.current = true;
    setExplainText(""); setExplainMsgId(undefined); setSuggests([]); setExplainPreview(false);
    const ac = new AbortController(); acRef.current = ac;
    // 무청크 hang 워치독(ExplainChat parity): 60초간 첫 청크도 안 오면 스트림을 끊어
    // '카드를 읽어 해석하고 있어요'가 영원히 남는 고착을 막고 재시도 UI로 넘긴다.
    let firstChunk = false;
    let hungTimeout = false;
    const hungTo = window.setTimeout(() => {
      if (!firstChunk) { hungTimeout = true; try { ac.abort(); } catch { /* noop */ } }
    }, 60000);
    try {
      // 최초 해석은 입장료에 포함된 핵심 상품 — deep(외부 보강 포함)으로 생성
      const gotDone = await streamSSE(`/api/tarot/${tid}/messages/stream`, { message: "", depth: "deep" }, {
        onChunk: (full) => { firstChunk = true; setExplainText(full); },
        // 보강본이 도착하면 텍스트를 교체하고, 화면이 아래로 밀리지 않게 리딩 상단으로 정렬(항목6)
        onRefine: (full) => { firstChunk = true; setExplainText(full); scrollToReading(); },
        onStage: setRefineStage,
        onCut: () => setExplainPreview(true),   // 익명 미리보기 컷 → 잠금 안내 + 액션바 숨김
        onDone: (d) => {
          if (d?.assistant_message_id) setExplainMsgId(d.assistant_message_id);
          if (d?.is_preview && !d?.preview_revealed) setExplainPreview(true);
        },
      }, ac.signal);
      // 잘림 방어(운영자 보고): done 없이 끊겼으면 ①저장본 재동기화 → ②1회 자동 재시도(무과금:
      // 최초 해석은 assistant 미저장 상태에서만 재생성됨) → ③둘 다 실패 시 재시도 버튼.
      if (!gotDone && !ac.signal.aborted) {
        const synced = await resyncExplain(tid);
        if (!synced) {
          if (!isRetry) {
            // 자동 재시도 1회 — finally 의 플래그 정리가 끝난 뒤 재진입(직접 호출하면 finally 가
            // 재시도 스트림의 explainingRef/streaming 을 되돌려 이중 스트림·표시 꼬임 발생)
            timer(() => { void startExplain(tid, true); }, 80);
            return;
          }
          setExplainFailed(true);          // 부분 텍스트 유지 + 재시도 버튼
        }
      }
    } catch (e: any) {
      // 부분 스트리밍 텍스트는 유지, 이탈(abort)이 아닌 실패면 재시도 UI 노출.
      // 단, 워치독 타임아웃으로 인한 abort 는 '무청크 고착'이므로 재시도 UI 를 띄운다.
      if (e?.name !== "AbortError" || hungTimeout) setExplainFailed(true);
    } finally {
      window.clearTimeout(hungTo);
      setExplainStreaming(false); explainingRef.current = false;
      setRefineStage(null);
      loadSuggests(tid);
      scrollToReading();  // 완료 시 리딩 상단 정렬(보강으로 리플로우된 뒤 재정렬)
    }
  }

  /* ── 추가질문(기본/심화 차감 — 궁합과 동일 빌링 흐름) ── */
  async function askFollowup(depth: "basic" | "deep", preset?: string) {
    const text = (preset ?? qInput).trim();
    if (!text || qStreaming || !sess) return;
    setQInput("");
    setQStreaming(true);
    setSuggests([]);
    while (explainingRef.current) await new Promise((r) => setTimeout(r, 250)); // 동시 스트림 방지
    setQaTurns((t) => [...t, { role: "user", content: text }, { role: "assistant", content: "" }]);
    const upd = (patch: Partial<QaTurn>) =>
      setQaTurns((t) => { const c = [...t]; c[c.length - 1] = { ...c[c.length - 1], ...patch }; return c; });
    const ac = new AbortController(); acRef.current = ac;
    try {
      await streamSSE(`/api/tarot/${sess.tarot_id}/messages/stream`, { message: text, depth }, {
        onChunk: (full) => upd({ content: full }),
        onRefine: (full) => upd({ content: full, refined: true }),
        onStage: setRefineStage,
        onDone: (d) => {
          upd({ is_preview: d.is_preview, charged: d.credits_charged, message_id: d.assistant_message_id });  // 답변별 공유/피드백 연결
          if (d?.credits_charged > 0) refreshMe();   // 추가질문 차감 후 잔액 즉시 반영(패턴 B)
        },
      }, ac.signal);
    } catch (e: any) {
      if (e?.name === "AbortError") { /* 이탈 취소 */ }
      else if (e?.message === "PAYWALL") {
        setQaTurns((t) => t.slice(0, -2)); // 방금 넣은 user + 빈 assistant 턴 제거
        setQInput(text); // 입력 복원 — 충전 후 그대로 재전송 가능
        openCharge(tr("tarot.charge_followup"));
      } else {
        upd({ content: tr("tarot.answer_fail") });
      }
    } finally {
      setQStreaming(false);
      setRefineStage(null);
      loadSuggests(sess.tarot_id);
    }
  }

  /* ── 새 리딩(질문 단계로) — 입장료는 카드 섞기(submit) 시점에만 차감되므로 여기선 무과금 ── */
  function newReading() {
    try { acRef.current?.abort(); } catch { /* noop */ }
    timersRef.current.forEach((t) => window.clearTimeout(t));
    document.querySelectorAll(".tr-flycard").forEach((el) => el.remove());
    sessionStorage.removeItem(STORAGE_KEY);
    restoredRef.current = false;
    pickedRef.current = [];
    tiltsRef.current = [];
    setSess(null); setSec(null); setQ("");
    setErr(null); setCreating(false); setNudgeSec(false); setNudgeQ(false);
    setPickedCount(0); setHidden(new Set()); setFanGone(false);
    setDealt(false); setDealDone(false); setHoverIdx(null);
    setLanded([]); setCards(null); setPicksErr(null); setFlipped([]);
    setExplainStarted(false); setExplainText(""); setExplainStreaming(false); setExplainFailed(false);
    setExplainMsgId(undefined); setRefineStage(null); setExplainPreview(false);
    setSuggests([]); setQaTurns([]); setQInput(""); setQStreaming(false);
    setDrawerOpen(false);
    setPhase("question");
    scrollTop();
    if (loggedIn) refreshSessions();
  }
  const restart = newReading;  // 리딩 하단 '새 리딩 시작' 버튼도 동일 동작

  /* ── 헤더 스텝 ── */
  const step = phase === "question" ? 1 : phase === "shuffle" ? 2 : !allPicked ? 3 : 4;

  /* PDF 메타 + 헤더(카드 목록) */
  const pdfHeader = useMemo(() => {
    if (!cards || !sess) return "";
    const lines = [
      tr("tarot.pdf_q", { q: sess.question }),
      tr("tarot.pdf_spread", { spread: spreadLabel, sec: sec?.nm || sess.section }),
    ];
    cards.forEach((c, i) => {
      lines.push(tr("tarot.pdf_card", {
        n: i + 1,
        pos: posMainName(c),
        kr: cardMainName(c),
        en: c.name_en,
        ori: c.orientation === "reversed" ? tr("tarot.reversed") : tr("tarot.upright"),
      }));
    });
    return lines.join("\n");
  }, [cards, sess, sec, spreadLabel, tr, vi]);

  /* 리딩 본문 강조 구절(항목5) — 백엔드가 평문화해도 화면에서 카드명·방향·포지션을 금색 강조 */
  const richHighlight = useMemo<string[]>(() => {
    if (!cards) return [];
    const hl: string[] = [tr("tarot.upright"), tr("tarot.reversed")];
    cards.forEach((c) => {
      const nm = cardMainName(c);
      if (nm) hl.push(nm);
      if (c.name_en) hl.push(c.name_en);   // 본문이 영문명을 쓰는 경우도 강조(vi 공통)
      const pos = posMainName(c);
      if (pos) hl.push(pos);
    });
    return hl;
  }, [cards, tr, vi]);

  const basicCost = me?.credit_cost_basic ?? 1900;
  const deepCost = me?.credit_cost_deep ?? 3900;
  const freeLeft = me?.free_remaining ?? 0;
  const feeNote = !me
    ? tr("tarot.fee_guest")
    : freeLeft > 0
    ? tr("tarot.fee_free", { n: fmtNum(freeLeft) })
    : tr("tarot.fee_paid", {
        basic: fmtNum(basicCost),
        deep: fmtNum(deepCost),
        bal: fmtNum(me.balance ?? 0),
        pt: tr("pay.pt"),
      });

  /* ══════════════ 렌더 ══════════════ */
  return (
    <div className="tarotpg" ref={pageRef}>
      <PrivacyNotice variant="answer" what="질문·카드 리딩 대화" />
      {/* 앰비언트 씬 레이어(전부 absolute — fixed·blend 미사용) */}
      <canvas className="tr-ambient" ref={ambientRef} aria-hidden />
      <div className="tr-moon" aria-hidden />
      <div className="tr-velvet" aria-hidden />

      {/* 항목8·9: 좌측상단 상시 플로팅 — 새롭게 타로보기 + 내 기록(로그인만) */}
      <div className="tr-float">
        <button className="tr-float-new" onClick={newReading} title={tr("tarot.float_new_title")}>
          {tr("tarot.float_new")}
        </button>
        {loggedIn && (
          <button className="tr-float-hist" onClick={() => { refreshSessions(); setDrawerOpen((v) => !v); }} title={tr("tarot.float_hist_title")}>
            {tr("tarot.float_hist")}{sessions.length > 0 && <em> {sessions.length}/{maxSessions}</em>}
          </button>
        )}
      </div>
      {drawerOpen && loggedIn && (
        <>
          <div className="tr-drawer-back" onClick={() => setDrawerOpen(false)} aria-hidden />
          <aside className="tr-drawer" role="dialog" aria-label={tr("tarot.drawer_title")}>
            <div className="tr-drawer-head">
              <span>{tr("tarot.drawer_title")} <em>{sessions.length}/{maxSessions}</em></span>
              <button className="tr-drawer-x" onClick={() => setDrawerOpen(false)} aria-label={tr("tarot.drawer_close")}>✕</button>
            </div>
            <div className="tr-drawer-note"><Trans i18nKey="tarot.drawer_note" components={{ b: <b /> }} /></div>
            {sessions.length === 0 ? (
              <div className="tr-drawer-empty">{tr("tarot.drawer_empty")}</div>
            ) : (
              <>
                <div className="tr-drawer-toolbar">
                  <label className="tr-selall">
                    <input
                      type="checkbox"
                      checked={sessions.length > 0 && sel.count === sessions.length}
                      ref={(el) => { if (el) el.indeterminate = sel.count > 0 && sel.count < sessions.length; }}
                      onChange={(e) => sel.setAll(sessions.map((s) => s.tarot_id), e.target.checked)}
                    />
                    전체 선택
                  </label>
                  <button
                    className="tr-bulk-del"
                    disabled={sel.count === 0 || bulkDeleting}
                    onClick={bulkDeleteSessions}
                  >
                    {bulkDeleting ? "삭제 중…" : `🗑 선택 삭제${sel.count ? ` (${sel.count})` : ""}`}
                  </button>
                </div>
                <ul className="tr-sesslist">
                  {sessions.map((s) => (
                    <li
                      key={s.tarot_id}
                      className={`tr-sessitem${s.tarot_id === sess?.tarot_id ? " on" : ""}${sel.has(s.tarot_id) ? " sel" : ""}`}
                      onClick={() => openSession(s.tarot_id)}
                    >
                      <input
                        type="checkbox"
                        className="tr-sess-check"
                        checked={sel.has(s.tarot_id)}
                        onChange={() => sel.toggle(s.tarot_id)}
                        onClick={(e) => e.stopPropagation()}
                        aria-label="선택"
                      />
                      <div className="tr-sess-main">
                        <div className="tr-sess-title">{s.title}</div>
                        <div className="tr-sess-meta">
                          {SECTIONS.find((x) => x.key === s.section)?.nm || s.section}
                          {" · "}{new Date(s.created_at).toLocaleDateString("ko-KR", { month: "long", day: "numeric" })}
                          {!s.has_reading && <span className="tr-sess-pending"> · 해석 전</span>}
                        </div>
                      </div>
                      <button className="tr-sess-del" onClick={(e) => removeSession(s.tarot_id, e)} aria-label="삭제">✕</button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </aside>
        </>
      )}

      <div className="tr-app">
        <header className="tr-header">
          <h1 className="tr-brand" style={{ margin: 0 }}>
            <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden>
              <g fill="none" stroke="#D9BC77" strokeWidth="1">
                <circle cx="13" cy="13" r="11.5" />
                <circle cx="13" cy="13" r="8" strokeOpacity=".55" />
                <path d="M13 1.5 V6 M13 20 V24.5 M1.5 13 H6 M20 13 H24.5 M4.9 4.9 L8 8 M18 18 L21.1 21.1 M21.1 4.9 L18 8 M8 18 L4.9 21.1" strokeOpacity=".8" />
              </g>
              <path d="M16.2 8.6 A5.4 5.4 0 1 0 16.2 17.4 A4.3 4.3 0 1 1 16.2 8.6 Z" fill="#E3C87F" />
            </svg>
            TAROT<small>{tr("tarot.brand_sub")}</small>
          </h1>
          <nav className="tr-steps" aria-label={tr("tarot.steps_aria")}>
            {(tr("tarot.steps", { returnObjects: true }) as string[]).map((nm, i) => (
              <span key={nm} style={{ display: "contents" }}>
                {i > 0 && <span className="tr-sep">·</span>}
                <span className={`tr-st${step === i + 1 ? " on" : ""}`}>{nm}</span>
              </span>
            ))}
          </nav>
        </header>
        <svg className="tr-decorule" viewBox="0 0 1048 22" preserveAspectRatio="none" aria-hidden>
          <line x1="0" y1="11" x2="496" y2="11" stroke="url(#tr-hrL)" strokeWidth="1" />
          <line x1="552" y1="11" x2="1048" y2="11" stroke="url(#tr-hrR)" strokeWidth="1" />
          <path d="M524 4 L531 11 L524 18 L517 11 Z" fill="none" stroke="#C9A455" strokeOpacity=".8" strokeWidth="1" />
          <path d="M524 8 L527 11 L524 14 L521 11 Z" fill="#D9BC77" />
          <defs>
            <linearGradient id="tr-hrL" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#C9A455" stopOpacity="0" /><stop offset="1" stopColor="#C9A455" stopOpacity=".55" /></linearGradient>
            <linearGradient id="tr-hrR" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#C9A455" stopOpacity=".55" /><stop offset="1" stopColor="#C9A455" stopOpacity="0" /></linearGradient>
          </defs>
        </svg>

        {phase === "question" && <ReviewStrip source="tarot" title="이용자 후기" limit={8} />}
        {phase === "question" && <EntryFeeNotice menu="tarot" />}
        {phase === "question" && (
          <div className="tr-storenote">
            {loggedIn ? tr("tarot.storenote_in") : tr("tarot.storenote_guest")}
          </div>
        )}

        {/* ── 1. 질문 ── */}
        <section className={`tr-phase${phase === "question" ? " on" : ""}`}>
          <h2 className="tr-h2">{tr("tarot.q_h2")}</h2>
          <p className="tr-sub">{tr("tarot.q_sub")}</p>
          <div className="tr-secgrid">
            {SECTIONS.map((s) => (
              <button
                key={s.key}
                type="button"
                className={`tr-sec${sec?.key === s.key ? " sel" : ""}${nudgeSec && !sec ? " nudge" : ""}`}
                onClick={() => { setSec(s); setNudgeSec(false); }}
              >
                <span className="tr-art">{ART[s.key]}</span>
                <span className="tr-bd">
                  <span className="tr-nm">{s.nm}</span>
                  <span className="tr-sp">{s.n === 11 ? tr("tarot.sub_celtic") : tr("tarot.sub_horse")}</span>
                </span>
              </button>
            ))}
          </div>
          {/* 섹션별 예시질문 5개 — 부각 라벨 + 칩(클릭 시 입력창 채움) */}
          {sec && (
            <div className="tr-examples">
              <div className="tr-suggest-label">{tr("tarot.examples_label", { sec: sec.nm })}</div>
              <div className="tr-chips">
                {sec.exs.map((t) => (
                  <button key={t} type="button" className="tr-chip" onClick={() => { setQ(t); setNudgeQ(false); }}>{t}</button>
                ))}
              </div>
            </div>
          )}
          <div className={`tr-qrow${nudgeQ ? " nudge" : ""}`}>
            <input
              ref={qInputRef}
              type="text"
              maxLength={120}
              placeholder={nudgeQ ? tr("tarot.q_ph_nudge") : (sec ? tr("tarot.q_ph_sec", { ex: sec.exs[0] }) : tr("tarot.q_ph_default"))}
              aria-label={tr("tarot.q_aria")}
              value={q}
              onChange={(e) => { setQ(e.target.value); if (nudgeQ) setNudgeQ(false); }}
              onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
            />
          </div>
          <button className="tr-cta" onClick={submit}>
            {creating ? tr("tarot.cta_prep") : tr("tarot.cta_shuffle")}
          </button>
          {err && <div className="tr-err">{err}</div>}
        </section>

        {/* ── 2. 셔플 ── */}
        <section className={`tr-phase${phase === "shuffle" ? " on" : ""}`}>
          <h2 className="tr-h2">{tr("tarot.shuf_h2")}</h2>
          <p className="tr-sub">{tr("tarot.shuf_sub")}</p>
          <div className="tr-well">
            {phase === "shuffle" && shufCards.map((c) => (
              <div
                key={c.i}
                className="tr-shufcard"
                style={{
                  animation: `${c.i % 2 ? "trRiffR" : "trRiffL"} ${c.dur}s ${c.del}s ease-in-out ${reduced ? 1 : 3}`,
                  zIndex: c.i,
                  transform: `translateY(${c.i * -0.8}px)`,
                }}
              >
                <div className="tr-cardback" />
              </div>
            ))}
          </div>
          <p className="tr-shufnote"><b>{tr("tarot.shuf_q")}</b> — {q}{sec ? `  (${sec.nm})` : ""}</p>
        </section>

        {/* ── 3·4. 테이블: 부채꼴 뽑기 + 스프레드 + 해석 ── */}
        <section className={`tr-phase${phase === "table" ? " on" : ""}`}>
          <h2 className="tr-h2">
            {!allPicked ? tr("tarot.table_pick") : !allFlipped ? tr("tarot.table_flip") : tr("tarot.table_done")}
          </h2>

          <div className={`tr-fanblock${fanGone ? " away" : ""}`}>
            <div className="tr-pickbar">
              <p className="tr-sub" style={{ margin: 0 }}>
                <Trans i18nKey="tarot.pickbar" values={{ n: need }} components={{ b: <b style={{ color: "var(--tr-gold-hi)" }} /> }} />
              </p>
              <div className="tr-cnt">{pickedCount} / {need}<small>{tr("tarot.pick_count")}</small></div>
            </div>
            <div className="tr-fanscroll">
              <div className="tr-fanarea">
                <div className="tr-fanwrap">
                  {phase === "table" && Array.from({ length: DECK_N }, (_, i) => {
                    const th = fanAngle(i);
                    const lift = hoverIdx === i ? FAN_R + 16 : FAN_R;
                    return (
                      <div
                        key={i}
                        className={`tr-fancard${hidden.has(i) ? " hide" : ""}`}
                        style={{
                          zIndex: i,
                          opacity: dealt ? undefined : 0,
                          transform: dealt
                            ? `rotate(${th}deg) translateY(-${lift}px)`
                            : `rotate(0deg) translateY(-${FAN_R - 140}px)`,
                          transitionDelay: dealDone ? "0ms" : `${120 + i * 9}ms`,
                        }}
                        onPointerEnter={() => { if (!hidden.has(i)) setHoverIdx(i); }}
                        onPointerLeave={() => setHoverIdx((cur) => (cur === i ? null : cur))}
                        onClick={(e) => pick(i, e.currentTarget)}
                      >
                        <div className="tr-cardback" />
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>

          {picksErr && (
            <div className="tr-err" style={{ textAlign: "center" }}>
              {picksErr}{" "}
              <button className="tr-chip" onClick={submitPicks}>{tr("tarot.retry")}</button>
            </div>
          )}
          {fanGone && !allFlipped && !picksErr && (
            cards ? (
              <div className="tr-flipguide">
                <p className="tr-flipguide-msg">
                  <span className="tr-flipguide-hand" aria-hidden>👆</span>
                  아래 카드를 <b>한 장씩 손으로 눌러</b> 뒤집어 주세요 · <b>{Math.max(0, need - flippedCount)}</b>장 남음
                </p>
                {isCeltic && (
                  <p className="tr-flipguide-celtic">
                    🃏 가운데 <b>겹쳐 놓인 두 장</b>은 위에 얹힌 카드부터 각각 눌러 주세요.
                    헷갈리면 아래 <b>한 번에 뒤집기</b>를 눌러 한꺼번에 여셔도 됩니다.
                  </p>
                )}
                <button type="button" className="tr-flipall-btn" onClick={flipAll}>
                  ✨ 한 번에 뒤집기
                </button>
              </div>
            ) : (
              <p className="tr-spreadhint">카드를 확정하는 중…</p>
            )
          )}

          {/* 스프레드(황금 성좌도) */}
          <div className="tr-spreadscroll">
            <div className={`tr-spread${isCeltic ? " celtic" : ""}`}>
              <svg className="tr-constel" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
                {isCeltic ? (
                  <>
                    {[
                      "12,48 48,48", "30,18 30,78", "72,16 72,82", "48,48 72,60", "72,38 90,49",
                    ].map((pts, i) => (
                      <g key={i}>
                        <polyline className="cglow" points={pts} pathLength={1} />
                        <polyline className="cline" points={pts} pathLength={1} />
                      </g>
                    ))}
                  </>
                ) : (
                  <>
                    <polyline className="cbase" points={`${COORD7[0][0]},${COORD7[0][1]} ${COORD7[6][0]},${COORD7[6][1]}`} pathLength={1} />
                    <polyline className="cglow" points={COORD7.map((xy) => xy.join(",")).join(" ")} pathLength={1} />
                    <polyline className="cline" points={COORD7.map((xy) => xy.join(",")).join(" ")} pathLength={1} />
                  </>
                )}
              </svg>
              {sess && coords.slice(0, need).map((xy, i) => {
                const c = cards?.[i];
                const cls = [
                  "tr-slot",
                  landed[i] ? "lit" : "",
                  flipped[i] ? "revealed" : "",
                  isCeltic && i === 1 ? "alt cross" : "",
                  isCeltic && i === 4 ? "toparm" : "",
                  isCeltic && i >= 6 && i <= 9 ? "side" : "",
                ].filter(Boolean).join(" ");
                return (
                  <div
                    key={i}
                    className={cls}
                    style={{ left: `${xy[0]}%`, top: `${xy[1]}%` }}
                    ref={(el) => { slotRefs.current[i] = el; }}
                  >
                    <div className="tr-ring">{ROMAN[i]}</div>
                    <div className="tr-plabel">
                      {i + 1}. {sess.positions[i] || (c ? posMainName(c) : "") || ""}
                      <span className="tr-cardnm">
                        {c && flipped[i] && (
                          <>
                            {cardMainName(c)} <span style={{ opacity: .65 }}>({c.name_en})</span> ·{" "}
                            {c.orientation === "reversed" ? <span className="tr-revtag">{tr("tarot.reversed")}</span> : tr("tarot.upright")}
                          </>
                        )}
                      </span>
                    </div>
                    {landed[i] && (
                      <div
                        className={`tr-flip${flipped[i] ? " flipped" : ""}${!reduced && !restoredRef.current ? " land" : ""}`}
                        style={{ ["--tilt" as any]: `${tiltsRef.current[i] ?? 0}deg` }}
                        role="button"
                        tabIndex={0}
                        aria-label={tr("tarot.flip_aria", { n: i + 1 })}
                        onClick={() => flip(i)}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); flip(i); } }}
                      >
                        <div className="tr-inner">
                          <div className="tr-face back"><div className="tr-cardback" /></div>
                          <div className="tr-face front">
                            {c && (
                              <img
                                src={c.image_url}
                                alt={`${cardMainName(c)} (${c.name_en})`}
                                className={c.orientation === "reversed" ? "rev" : undefined}
                                loading="lazy"
                              />
                            )}
                            <span className="tr-fx" />
                            <span className="tr-sheen" />
                          </div>
                        </div>
                        {/* 각 미공개 카드에 '눌러서 뒤집기' 손 모양 큐 — 사용자가 뒤집는 걸 놓치지 않게(운영자 지시) */}
                        {!flipped[i] && <span className="tr-taphint" aria-hidden>👆</span>}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* 카드 배치 범례 — 겹침(켈틱 크로스 중앙)에도 자리·카드를 100% 식별 */}
          {sess && cards && cards.length > 0 && (
            <ol className="tr-legend" aria-label="카드 배치">
              {cards.slice(0, need).map((c, i) => (
                <li key={i}>
                  <span className="tr-legnum">{i + 1}</span>
                  <span className="tr-legpos">{sess.positions[i] || c.position_name}</span>
                  {flipped[i] ? (
                    <span className="tr-legcard">
                      {c.name_kr} <span className="tr-legen">({c.name_en})</span>
                      <span className={c.orientation === "reversed" ? "tr-legrev" : "tr-legup"}>
                        {c.orientation === "reversed" ? "역방향" : "정방향"}
                      </span>
                    </span>
                  ) : (
                    <span className="tr-legwait">뒤집기 전</span>
                  )}
                </li>
              ))}
            </ol>
          )}

          {/* A-1: 이 카드 그대로 상담사에게 — 접수 시 스프레드가 자동 전달돼 중복 설명 불필요.
              럭셔리 CTA(운영자 지시): FLUX 엠블럼 + 의미 설명("상담사와 이 카드로 상담합니다") + 강조 */}
          {me && sess && cards && cards.length > 0 && (
            <div className="tr-consult-cta">
              <button
                type="button"
                className="tr-consult-btn"
                title="지금 뽑은 카드가 타로 상담사에게 그대로 전달됩니다"
                onClick={() =>
                  window.dispatchEvent(
                    new CustomEvent("saju:consult-open", {
                      detail: { kind: "tarot", refId: sess.tarot_id, label: spreadLabel },
                    })
                  )
                }
              >
                <img
                  className="tcb-emblem" src="/tarot/consult-badge.webp" alt="" width={52} height={52}
                  onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
                />
                <span className="tcb-text">
                  <b className="tcb-title">이 카드로 1:1 상담</b>
                  <small className="tcb-desc">방금 뽑은 카드가 그대로 전해져요 — 타로 상담사와 이 카드로 상담합니다</small>
                </span>
                <span className="tcb-arrow" aria-hidden>➤</span>
              </button>
            </div>
          )}

          {/* ── 5. 해석(리딩 패널) ── */}
          {explainStarted && sess && (
            <div className="tr-reading" ref={readingRef}>
              {typeof sess.credits_charged === "number" && sess.credits_charged > 0 && (
                <div className="charge-receipt">✓ 타로 입장료 {sess.credits_charged.toLocaleString()} P 차감됨</div>
              )}
              <h3>THE READING</h3>
              <p className="tr-rdsub">{tr("tarot.reading_sub")}</p>
              <p className="tr-qecho">{tr("tarot.reading_qecho", { q: sess.question, sec: sec?.nm || sess.section, spread: spreadLabel })}</p>
              <svg className="tr-rdrule" viewBox="0 0 600 14" preserveAspectRatio="none" aria-hidden>
                <line x1="0" y1="7" x2="284" y2="7" stroke="#C9A455" strokeOpacity=".35" />
                <line x1="316" y1="7" x2="600" y2="7" stroke="#C9A455" strokeOpacity=".35" />
                <path d="M300 2 L305 7 L300 12 L295 7 Z" fill="none" stroke="#D9BC77" strokeOpacity=".8" />
              </svg>
              <div className="tr-rdbody">
                {explainText ? renderRich(explainText, { highlight: richHighlight }) : (
                  explainStreaming
                    ? <span className="gen-live" role="status" aria-live="polite">🔮 <b>카드를 읽어 해석하고 있어요</b> <TypingDots /></span>
                    : (explainFailed ? "" : "해석을 불러오는 중…")
                )}
                {explainStreaming && explainText && <span className="tr-caret" />}
                {refineStage === "refining" && <span className="tr-refinetag">✨ 보강 중…</span>}
                {explainFailed && !explainStreaming && (
                  <div className="tr-rdretry">
                    {tr("tarot.reading_fail")}
                    <button type="button" className="tr-depthbtn" onClick={() => sess && startExplain(sess.tarot_id)}>
                      {tr("tarot.retry_free")}
                    </button>
                  </div>
                )}
              </div>

              {/* 익명 미리보기 잠금 안내 — 마스킹이 '잘림 버그'처럼 보이지 않게 명시(운영자 보고) */}
              {explainPreview && !explainStreaming && explainText && (
                <div className="tr-preview-note" role="note">
                  {me ? (
                    <>🔒 <b>미리보기</b>로 앞부분만 보여드렸어요. <b>새 리딩</b>으로 전체 풀이(복사·공유·PDF 포함)를 받아보세요.</>
                  ) : (
                    <>🔒 <b>미리보기</b>로 앞부분만 보여드렸어요. 비로그인 리딩은 전체 해석이 잠깁니다 —
                    <b> 로그인 후 새 리딩</b>으로 전체 풀이(복사·공유·PDF 포함)를 받아보세요.</>
                  )}
                </div>
              )}
              {/* 미리보기(마스킹) 상태에선 액션바 숨김 — 잘린 본문으로 PDF·공유가 만들어지는 사고 방지 */}
              {explainText && !explainStreaming && !explainPreview && (
                <AnswerActions
                  text={(pdfHeader ? pdfHeader.trim() + "\n\n" : "") + stripMarkdown(explainText)}
                  pdfContent={`${tr("tarot.pdf_q")} ${sess.question}\n${tr("tarot.pdf_spread")} ${spreadLabel} (${sec?.nm || sess.section})\n\n${stripMarkdown(explainText)}`}
                  tarotCards={(cards || []).map((c) => ({
                    position_name: posMainName(c), name_kr: cardMainName(c), name_en: c.name_en,
                    orientation: c.orientation, image_url: c.image_url,
                  }))}
                  pdf={{
                    docTitle: tr("tarot.pdf_doc", { name: memberName }),
                    personLine: tr("tarot.pdf_person", { name: memberName }),
                    item: tr("tarot.pdf_item", { sec: sec?.nm || sess.section }),
                  }}
                  messageId={explainMsgId}
                  source="tarot"
                  sessionId={sess.tarot_id}
                  isLast
                />
              )}

              {/* 추가질문 */}
              <div className="tr-qa">
                {qaTurns.map((t, i) => (
                  <div key={i} className={`tr-qaturn ${t.role}`}>
                    <div className="tr-qabubble">
                      {t.content ? renderRich(t.content, t.role === "assistant" ? { highlight: richHighlight } : undefined) : (
                        <span className="gen-live" role="status" aria-live="polite"><b>답변을 생성하고 있어요</b> <TypingDots /></span>
                      )}
                      {t.refined && <span className="tr-qacharged">✨ 보강됨</span>}
                      {t.role === "assistant" && typeof t.charged === "number" && t.charged > 0 && (
                        <span className="tr-qacharged">{tr("tarot.qa_charged", { n: fmtNum(t.charged), pt: tr("pay.pt") })}</span>
                      )}
                    </div>
                    {/* 추가질문 답변에도 공유/복사/PDF·피드백 — 전 메뉴 표준. 미리보기·스트리밍 중 미노출 */}
                    {t.role === "assistant" && t.content && !t.is_preview &&
                      !(qStreaming && i === qaTurns.length - 1) && (
                      <AnswerActions
                        text={`${tr("tarot.pdf_q")} ${qaTurns[i - 1]?.role === "user" ? qaTurns[i - 1].content : ""}

${stripMarkdown(t.content)}`}
                        pdf={{
                          docTitle: tr("tarot.pdf_doc", { name: memberName }),
                          personLine: memberName,
                          item: ((qaTurns[i - 1]?.role === "user" ? qaTurns[i - 1].content : "") || tr("tarot.pdf_item_q")).slice(0, 40),
                        }}
                        messageId={t.message_id}
                        source="tarot"
                        sessionId={sess.tarot_id}
                        isLast={i === qaTurns.length - 1}
                      />
                    )}
                  </div>
                ))}
              </div>
              {suggests.length > 0 && !qStreaming && !explainStreaming && (
                <div className="tr-chips" style={{ marginTop: 14, marginBottom: 0 }}>
                  <div className="tr-suggest-label">{tr("tarot.suggest_more")}</div>
                  {suggests.map((sg) => (
                    <button key={sg} type="button" className="tr-chip" disabled={qStreaming} onClick={() => askFollowup("basic", sg)}>
                      {sg}
                    </button>
                  ))}
                </div>
              )}
              <div className="tr-followup">
                {/* 추가질문 기본/심화 + 차감 배지 — 전 메뉴 공통 FollowupBilling(운영자 지적: UI 동일·차감 분명히).
                    타로는 입장료 결제라 추가질문 항상 차감(freeNote 없음). */}
                <FollowupBilling me={me} depth={qDepth} onDepth={setQDepth} />
                <div className="tr-followup-row">
                  <input
                    type="text"
                    placeholder="이어서 궁금한 점을 물어보세요…"
                    aria-label="추가 질문"
                    value={qInput}
                    disabled={qStreaming}
                    onChange={(e) => setQInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && qInput.trim()) askFollowup(qDepth); }}
                  />
                  <button
                    className="tr-depthbtn"
                    disabled={qStreaming || !qInput.trim()}
                    onClick={() => askFollowup(qDepth)}
                    title={`${qDepth === "deep" ? "심화" : "기본"} 질문 · ${(qDepth === "deep" ? deepCost : basicCost).toLocaleString()}P`}
                  >
                    {qStreaming ? "…" : "질문하기"}
                  </button>
                </div>
              </div>

              {!explainStreaming && !qStreaming && (
                <button className="tr-restart" onClick={restart}>{tr("tarot.restart")}</button>
              )}
            </div>
          )}
        </section>

        {/* ── 하단 저작권 고지(전 단계 상시 노출) ── */}
        <footer className="tr-legal">
          <Trans i18nKey="tarot.legal" components={{ b: <b /> }} />
        </footer>
      </div>

      <div className="tr-vignette" aria-hidden />
      <div className="tr-grain" aria-hidden />
    </div>
  );
}
