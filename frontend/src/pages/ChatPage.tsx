/** Gemini 풍의 사주 채팅 UI.
 * - 좌측: 내 세션 사이드바 (회원만), 새 대화 버튼
 * - 우측: 생일 입력 → 세션 → SajuChart + 배너 + 채팅
 * - 미리보기 메시지에는 더보기(500P) 버튼
 */
import ReviewStrip from "../components/ReviewStrip";
import { useEffect, useRef, useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import AdvancedBirthSettings from "../components/AdvancedBirthSettings";
import PrivacyNotice from "../components/PrivacyNotice";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, Birth, useMe, ensureFreshToken, setCachedMe, notifySessionExpired, Source } from "../api";
import { fmtKSTDate } from "../lib/datetime";
import SajuChart, { Chart } from "../components/SajuChart";
import { zodiacAvatar, zodiacLabel } from "../lib/zodiacAvatar";
import TimeSelect from "../components/TimeSelect";
import BannerSlot from "../components/BannerSlot";
import AdSlot from "../components/AdSlot";
import LoginForm from "../components/LoginForm";
import AnswerActions from "../components/AnswerActions";
import TypingDots from "../components/TypingDots";
import ConsultBanner from "../components/ConsultBanner";
import ConsultationReportButton, { type ReportReq } from "../components/ConsultationReportButton";
import { renderRich, stripMarkdown } from "../lib/format";
import { resolveBirthTime, DEFAULT_BIRTH_TIME } from "../lib/birthTime";
import { useCharge } from "../components/ChargeModal";
import { displayName } from "../lib/displayName";
import { useBulkSelect } from "../lib/useBulkSelect";
import { readableBirth, type BirthValue } from "../components/BirthFields";
import FollowupBilling from "../components/FollowupBilling";
import { fmtNum } from "../lib/money";
import { DEFAULT_LON } from "../lib/regions";

// 철학관 상호(항목 D) — 운영 설정값 연동은 P3, 우선 환경값으로 표시.
const STUDIO_NAME = (import.meta.env.VITE_STUDIO_NAME as string | undefined) || "";

// 추천 질문 칩 (suggestion chips)
// 상담 시작 시 자동 전송하는 '종합 풀이' 질문(칩 클릭 없이 기본으로 풍부하게). 첫 답변=이 종합 풀이.
const COMPREHENSIVE_READING =
  "내 사주를 종합적으로 풀어주세요 — 성격·육친·건강운과, 올해 일어날 수 있는 일, 그리고 이번 달부터 월별로 생길 수 있는 일(직업·재물·인연 포함)을 알차고 풍부하게.";
// 상담 시작 시 '요즘 고민 한 줄'이 있으면 종합풀이를 그 고민에 정조준(판정 먼저)한다.
// COMPREHENSIVE_READING에 '종합'이 들어 있어 백엔드 라우팅은 종합구조를 그대로 유지(고민 키워드로 집중모드에 안 빠짐).
function comprehensiveMsg(worry: string): string {
  const w = (worry || "").trim();
  if (!w) return COMPREHENSIVE_READING;
  return `${COMPREHENSIVE_READING} 특히 요즘 제 가장 큰 고민은 「${w}」입니다. 이 고민부터 짚어 주시고, 종합 풀이 전체를 이 고민과 연결해 주세요.`;
}
const SUGGEST_CHIPS = [
  "🔮 내 사주 종합 풀이 — 성격·육친·건강운, 올해와 월별로 생길 수 있는 일을 알차게 풀어주세요.",
  "내 성격과 육친(가족·인연) 풀이를 해주세요.",
  "올해 전체 운세가 어떤가요?",
  "직업·적성은 어떤 분야가 맞나요?",
  "재물운과 금전운을 알려주세요.",
  "연애·결혼운은 어떤가요?",
  "건강에서 주의할 점은?",
  "대운 흐름을 짚어주세요.",
];
// 종합 풀이 프롬프트·추천 칩은 로케일별(tr("chat.comprehensive"|"chat.chips")) — 컴포넌트 내부에서 정의.

type Turn = {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  is_preview?: boolean;
  preview_revealed?: boolean;
  message_id?: number;
  full_length?: number;
  preview_length?: number;
  credits_charged?: number;
  reveal_cost?: number;
  billing_mode?: string;
  evidence?: string[];
  refined?: boolean;
  flash?: boolean;
  feedback?: 1 | -1;
  clarify?: { question: string; options: string[]; key?: string }; // 답변 전 사전 선택질문(Track B)
};

type SessionItem = {
  session_id: string;
  title: string;
  created_at: string;
  birth_date: string;
  message_count: number;
};

export default function ChatPage() {
  const me = useMe();
  const navigate = useNavigate();
  const { t: tr } = useTranslation();
  const { openCharge } = useCharge();
  // 상담서(PDF) 제목/대상에 쓰는 회원 표시명 — ⚠️ 호칭은 이메일 아이디 고정(운영자 결정 2026-07).
  //    정책·잠금 주석은 lib/displayName.ts 에 일원화 — 전 메뉴 공통 헬퍼를 쓸 것(닉네임 우선 금지).
  const memberName = displayName(me);
  // 종합 풀이 자동전송 프롬프트 + 추천 칩(로케일별) — LLM에 그대로 전달된다.
  const COMPREHENSIVE_READING = tr("chat.comprehensive");
  const SUGGEST_CHIPS = tr("chat.chips", { returnObjects: true }) as string[];

  function billingHint(): string {
    if (!me) return tr("chat.bh_guest");
    if ((me.level ?? 9) <= 1) return tr("chat.bh_admin");
    if (me.is_member)
      return tr("chat.bh_member", { rem: fmtNum(me.membership_remaining ?? 0), quota: fmtNum(me.membership_quota ?? 0) });
    const cost = depth === "deep" ? (me.credit_cost_deep ?? 0) : (me.credit_cost_basic ?? 0);
    if ((me.free_remaining ?? 0) > 0)
      return tr("chat.bh_free", { rem: me.free_remaining, quota: me.free_quota_count ?? 3, deepNote: depth === "deep" ? tr("chat.bh_free_deep") : "" });
    return tr("chat.bh_paid", { level: depth === "deep" ? tr("chat.lvl_deep") : tr("chat.lvl_basic"), cost: fmtNum(cost), bal: fmtNum(me.balance) });
  }
  const [birth, setBirth] = useState<Birth>({
    birth_date: "1990-03-15",
    birth_time: "",          // 비워두면 제출 시 00:30 기본('시 모름'이면 시주 제외)
    calendar: "solar",
    gender: "male",
    is_leap_month: false,
    apply_true_solar_time: true,
    birth_longitude: DEFAULT_LON,
    night_zi_mode: "yaja",
  });
  const [dateText, setDateText] = useState("1990-03-15");  // 생년월일 직접 입력 텍스트
  const [worry, setWorry] = useState("");                  // (선택) 요즘 가장 큰 고민 한 줄 — 종합풀이 정조준용
  const worryRef = useRef("");                             // 자동 종합풀이 전송 시점의 고민값(클로저 스테일 방지)
  const [unknownTime, setUnknownTime] = useState(false);   // '시 모름' = 시주 제외(null). 끄면 빈 시각은 00:30 기본
  const dateRef = useRef<HTMLInputElement>(null);          // 달력 팝업 전용(숨김) native date
  const quickRef = useRef<HTMLInputElement>(null);         // 빠른입력 실제 DOM 값 소스(자동완성/붙여넣기/IME 대응)
  const [sid, setSid] = useState<string | null>(null);
  const [dynamicSuggests, setDynamicSuggests] = useState<string[]>([]);  // 답변 후 맥락 추천질문
  const [summary, setSummary] = useState<string>("");
  const [chart, setChart] = useState<Chart | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [revealing, setRevealing] = useState(false);  // 전체보기 차감 중 — 더블클릭 방지
  const [autoRead, setAutoRead] = useState(false);     // 상담 시작 직후 종합 풀이 자동 전송 대기
  const [err, setErr] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [needBirth, setNeedBirth] = useState(true);
  const [useSSE, setUseSSE] = useState(true);
  const taRef = useRef<HTMLTextAreaElement | null>(null);

  // P3: 질문 비용 선택(기본/심화) + 결제 유도 + 보강 단계 표시
  const [depth, setDepth] = useState<"basic" | "deep">("basic");
  // 쉬운 말투 옵션(기본=전문). localStorage로 선택 유지.
  const [easy, setEasy] = useState<boolean>(() => localStorage.getItem("saju_explain_easy") === "1");
  // 핵심만(100단어) 옵션
  const [brief, setBrief] = useState<boolean>(() => localStorage.getItem("saju_explain_brief") === "1");
  const toggleBrief = (v: boolean) => {
    setBrief(v);
    if (v) localStorage.setItem("saju_explain_brief", "1");
    else localStorage.removeItem("saju_explain_brief");
  };
  const explainMode = (): "brief" | "easy" | "normal" => (brief ? "brief" : easy ? "easy" : "normal");
  const toggleEasy = (v: boolean) => {
    setEasy(v);
    if (v) localStorage.setItem("saju_explain_easy", "1");
    else localStorage.removeItem("saju_explain_easy");
  };
  // 첫 질문 1회 안내 팝업(쉽게/전문 선택). 이후엔 인라인 토글로 변경.
  const [explainAsked, setExplainAsked] = useState<boolean>(() => localStorage.getItem("saju_explain_asked") === "1");
  const [showExplainPopup, setShowExplainPopup] = useState(false);
  const [pendingMsg, setPendingMsg] = useState<string | null>(null);
  const [showPaywall, setShowPaywall] = useState(false);
  const [refineStage, setRefineStage] = useState<string | null>(null);
  const [verifyElapsed, setVerifyElapsed] = useState<number | null>(null); // 검증·교정 경과초(백엔드 stage.elapsed)

  // P4: 세션 수 제한 정리 모달
  const [showSessionLimit, setShowSessionLimit] = useState(false);
  const [maxSessions, setMaxSessions] = useState(30);
  const sel = useBulkSelect<string>();          // 한도 정리 모달 다중선택(체크 → 일괄삭제)
  const [bulkDeleting, setBulkDeleting] = useState(false);

  // 빠른 숫자 입력(YYYYMMDDHHMM) + 사주정보 기억하기
  const [quick, setQuick] = useState("");
  const [quickInfo, setQuickInfo] = useState<string | null>(null);
  // 사용자가 빠른입력창에 '직접' 값을 넣었는지(타이핑/적용) — 자동채움 sync가 사용자 입력을 덮지 않게.
  // ⚠️ birth 초기값이 하드코딩 기본("1990-03-15")이라 길이 기반 가드로는 기본값을 '사용자 입력'으로
  //    오인해 복원값 반영을 막았다(운영자 지적: 상담 빠른입력에 기억값 대신 기본값 표시). ref로 정확히 구분.
  const quickDirty = useRef(false);
  const [remember, setRemember] = useState(false);

  const isLoggedIn = !!me;

  // 비로그인: localStorage 기반 복원(최초 1회)
  const localLoadedRef = useRef(false);
  useEffect(() => {
    if (me || localLoadedRef.current) return;
    localLoadedRef.current = true;
    if (localStorage.getItem("saju_birth_remember") === "1") {
      setRemember(true);
      const saved = localStorage.getItem("saju_birth_saved");
      if (saved) { try { const sb = JSON.parse(saved); setBirth((b) => ({ ...b, ...sb })); setUnknownTime(!String(sb.birth_time || "").trim()); } catch { /* 무시 */ } }
    }
  }, [me, me?.saju_profile?.birth_date]);

  // 로그인: 서버에 저장된 본인 사주 자동 채움 + 기억하기 기본 ON (사용자별 1회)
  // ⚠️ me 캐시에 프로필이 아직 없으면 도장을 찍지 않는다 — 늦게 도착해도 채움(공용 훅과 동일 규약)
  const profileLoadedFor = useRef<string | null>(null);   // 'id|birth|time' 서명 — 서버본 갱신 시 재반영
  const chatPendingSave = useRef<Birth | null>(null);   // 디바운스 이탈 유실 방지
  useEffect(() => {
    const sig = me ? `${me.id}|${me.saju_profile?.birth_date || ""}|${me.saju_profile?.birth_time || ""}` : null;
    if (!me || profileLoadedFor.current === sig) return;
    if (!me.saju_profile?.birth_date) {
      // 서버 프로필 도착 전 — LS 사본이 있으면 우선 채움(도장 보류 → 도착 시 서버본으로 갱신)
      if (localStorage.getItem("saju_birth_remember") !== "0") {
        try {
          const sb = JSON.parse(localStorage.getItem("saju_birth_saved") || "null");
          if (sb?.birth_date && !birth.birth_date) {
            setBirth((b) => ({ ...b, ...sb }));
            setUnknownTime(!String(sb.birth_time || "").trim());
            setRemember(true);
          }
        } catch { /* 무시 */ }
      }
      return;
    }
    profileLoadedFor.current = sig;
    if (me.saju_profile && me.saju_profile.birth_date) {
      setBirth((b) => ({ ...b, ...me.saju_profile }));
      setUnknownTime(!String(me.saju_profile.birth_time || "").trim());
    }
    setRemember(true);   // 로그인 사용자는 본인 사주 재사용이 기본 → 저장 ON
  }, [me]);

  // 외부에서 birth_date가 바뀌면(자동채움·달력선택·프로필 로드) 생년월일 텍스트칸 동기화.
  // 빠른입력(parseQuick)은 자체적으로 setDateText 하지만, 자동채움 경로는 birth만 바꾸므로 필요.
  useEffect(() => { setDateText(birth.birth_date || ""); }, [birth.birth_date]);

  // 빠른입력창(quick)도 실제 값과 동기화 — '기억하기' 자동채움 경로는 birth만 바꾸므로, 이게 없으면
  // 빠른입력칸이 빈 채 '예: 199909…' 플레이스홀더만 떠서 저장정보가 없는 것처럼 오해된다(운영자 지적:
  // 상담 진입 시 빠른입력에 기억값 미표시 — 타 메뉴는 공용 BirthFields가 이미 동기화해 정상).
  // 사용자가 이미 8자리 이상 타이핑했으면 그대로 둔다(타이핑 방해 X).
  useEffect(() => {
    if (!birth.birth_date) return;
    setQuick((cur) => {
      if (quickDirty.current) return cur;   // 사용자가 직접 입력한 값 — 유지(타이핑 방해 X)
      const vd = birth.birth_date.replace(/\D/g, "");
      const vt = (!unknownTime && (birth.birth_time || "").trim())
        ? String(birth.birth_time).replace(/\D/g, "").slice(0, 4) : "";
      return vd + vt;
    });
  }, [birth.birth_date, birth.birth_time, unknownTime]);

  // 기억하기 ON 상태에서 사주정보가 바뀌면 저장(로그인=서버, 비로그인=localStorage). 서버는 디바운스.
  // 저장 응답(최신 saju_profile 포함 MeResp)을 캐시에 반영해야 재입장 시 자동 채움이 작동한다.
  useEffect(() => {
    if (!remember || !birth.birth_date) return;
    // '시 모름'은 null로 저장돼야 재입장 시 시주 제외가 그대로 복원된다.
    const toSave: Birth = { ...birth, birth_time: resolveBirthTime(birth.birth_time, unknownTime) };
    if (me) {
      const p0 = me.saju_profile;
      if (p0 && p0.birth_date === toSave.birth_date && (p0.birth_time || "") === (toSave.birth_time || "")
          && p0.calendar === toSave.calendar && p0.gender === toSave.gender) return;  // 에코 저장 차단
      chatPendingSave.current = toSave;
      const t = setTimeout(() => { chatPendingSave.current = null; api.saveSajuProfile(toSave).then(setCachedMe).catch(() => {}); }, 900);
      return () => {
        clearTimeout(t);
        if (chatPendingSave.current) { const p = chatPendingSave.current; chatPendingSave.current = null; api.saveSajuProfile(p).then(setCachedMe).catch(() => {}); }
      };
    }
    localStorage.setItem("saju_birth_remember", "1");   // 자동 ON 경로에서도 다음 방문 복원되게
    localStorage.setItem("saju_birth_saved", JSON.stringify(toSave));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [birth, remember, unknownTime]);

  // '한 번이라도 입력하면 기본 활성화'(운영자 결정) — 명시적으로 끈 적 없으면 생년월일 입력 시 자동 ON
  const rememberOffRef = useRef(localStorage.getItem("saju_birth_remember") === "0");
  useEffect(() => {
    if (!remember && !rememberOffRef.current && birth.birth_date) setRemember(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [birth.birth_date]);

  const toggleRemember = (checked: boolean) => {
    setRemember(checked);
    rememberOffRef.current = !checked;   // 명시적 끔이면 자동 ON 재발동 방지
    if (me) {
      api.saveSajuProfile(checked ? birth : null).then(setCachedMe).catch(() => {});
    }
    if (checked) {
      localStorage.setItem("saju_birth_remember", "1");
      if (!me) localStorage.setItem("saju_birth_saved", JSON.stringify(birth));
    } else {
      localStorage.setItem("saju_birth_remember", "0");   // '명시적 끔' 마커(공용 훅과 동일 규약)
      localStorage.removeItem("saju_birth_saved");
    }
  };

  // "199909300530" → 1999-09-30 05:30 자동 분해 입력 (예시는 익명값 — 실제 개인정보 금지)
  const applyQuick = (raw: string) => {
    quickDirty.current = true;   // 사용자 직접 입력/적용 — 이후 자동 sync가 이 값을 덮지 않음
    setQuick(raw);
    const d = raw.replace(/\D/g, "");
    if (d.length === 0) {
      setQuickInfo(null);
      return;
    }
    if (d.length !== 8 && d.length !== 10 && d.length !== 12) {
      setQuickInfo(tr("chat.q_len"));
      return;
    }
    const y = d.slice(0, 4), mo = d.slice(4, 6), da = d.slice(6, 8);
    const yi = +y, moi = +mo, dai = +da;
    if (yi < 1900 || yi > 2100 || moi < 1 || moi > 12 || dai < 1 || dai > 31) {
      setQuickInfo(tr("chat.q_date_bad"));
      return;
    }
    const next: Birth = { ...birth, birth_date: `${y}-${mo}-${da}` };
    let timeLabel = "";
    if (d.length >= 10) {
      const hh = d.slice(8, 10);
      const mm = d.length >= 12 ? d.slice(10, 12) : "00";
      if (+hh <= 23 && +mm <= 59) {
        next.birth_time = `${hh}:${mm}`;
        timeLabel = ` ${hh}:${mm}`;
        setUnknownTime(false);
      } else {
        setQuickInfo(tr("chat.q_time_bad"));
        return;
      }
    } else if (!unknownTime && !String(next.birth_time || "").trim()) {
      // 시각 미입력 → 자동으로 00:30 채워 매끄럽게 진행('시 모름'이면 제외 유지)
      next.birth_time = DEFAULT_BIRTH_TIME;
      timeLabel = ` ${DEFAULT_BIRTH_TIME}`;
    }
    setBirth(next);
    setDateText(next.birth_date);
    setQuickInfo(tr("chat.q_ok", { y: yi, mo: moi, da: dai, time: timeLabel }));
  };

  // 생년월일 직접 타이핑 — 숫자만 받아 YYYY-MM-DD 자동 포맷, 8자리 완성 시 반영
  const typeDate = (raw: string) => {
    const dig = raw.replace(/\D/g, "").slice(0, 8);
    let f = dig;
    if (dig.length > 6) f = `${dig.slice(0, 4)}-${dig.slice(4, 6)}-${dig.slice(6)}`;
    else if (dig.length > 4) f = `${dig.slice(0, 4)}-${dig.slice(4)}`;
    setDateText(f);
    if (dig.length === 8) {
      const y = +dig.slice(0, 4), mo = +dig.slice(4, 6), da = +dig.slice(6, 8);
      if (y >= 1900 && y <= 2100 && mo >= 1 && mo <= 12 && da >= 1 && da <= 31) {
        setBirth((b) => ({ ...b, birth_date: `${dig.slice(0, 4)}-${dig.slice(4, 6)}-${dig.slice(6, 8)}` }));
      }
    }
  };

  // 입력창 자동 높이(항목 C): scrollHeight 기반, 최대 200px 후 내부 스크롤.
  const autoGrow = () => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  };
  useEffect(autoGrow, [input]);

  const onChipClick = (q: string) => {
    setInput(q);
    taRef.current?.focus();
  };

  const refreshSessions = async () => {
    if (!isLoggedIn) return;
    try {
      const r = await api.myChatSessions(50);
      setSessions(r.items);
      setMaxSessions(r.max_sessions ?? 30);
    } catch {}
  };

  // 한도 정리 화면에서 상담 삭제 — 복구 불가라 한 번 확인. 현재 보던 상담이면 새 상담으로.
  const removeSession = async (id: string, label: string) => {
    if (!window.confirm(tr("chat.del_confirm", { label }))) return;
    try {
      await api.deleteChatSession(id);
      await refreshSessions();
      window.dispatchEvent(new Event("saju:sessions-changed"));
      if (sid === id) newChat();
    } catch (e: any) {
      setErr(String(e?.message || e));
    }
  };

  // 체크한 상담 일괄삭제 — 서버 단일 요청(개별 DELETE 반복의 레이트리밋·부분실패 회피). 한 번만 확인.
  const bulkDeleteSessions = async () => {
    const ids = [...sel.selected];
    if (ids.length === 0 || bulkDeleting) return;
    if (!window.confirm(`선택한 ${ids.length}개 상담을 삭제할까요?\n삭제한 상담 기록은 복구할 수 없어요.`)) return;
    setBulkDeleting(true);
    try {
      await api.bulkDeleteChatSessions(ids);
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setBulkDeleting(false);
    }
    sel.clear();
    await refreshSessions();
    window.dispatchEvent(new Event("saju:sessions-changed"));
    if (sid && ids.includes(sid)) newChat();   // 보던 상담이 삭제됐으면 새 상담으로
  };

  // 날짜를 짧게(KST YYYY-MM-DD) — 어떤 상담을 정리할지 빠르게 식별하도록.
  const shortDate = (iso?: string) => fmtKSTDate(iso);

  const [searchParams, setSearchParams] = useSearchParams();
  useEffect(() => {
    refreshSessions();
    const onNew = () => { newChat(); setSearchParams({}, { replace: true }); };
    window.addEventListener("saju:new-chat", onNew);
    return () => window.removeEventListener("saju:new-chat", onNew);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const urlSession = searchParams.get("s");
  useEffect(() => {
    if (!isLoggedIn) return;
    if (urlSession) {
      if (urlSession !== sid) loadSession(urlSession);
    } else if (sid !== null) {
      newChat();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlSession, isLoggedIn]);

  const startSession = async () => {
    setErr(null);
    setBusy(true);
    try {
      // 시각 미입력 정책(전 메뉴 공통): '시 모름'=시주 제외(null), 그 외 빈 값=00:30 기본
      const payload: Birth = { ...birth, birth_time: resolveBirthTime(birth.birth_time, unknownTime) };
      const r: any = await api.createSession(payload, 4);
      setSid(r.session_id);
      setSummary(r.saju_summary || "");
      setChart((r.saju_chart || r.chart) as Chart);
      setTurns([]);
      setNeedBirth(false);
      await refreshSessions();
      setSearchParams({ s: r.session_id }, { replace: true });
      window.dispatchEvent(new Event("saju:sessions-changed"));
      worryRef.current = worry.trim();   // 자동 종합풀이가 정조준할 고민 스냅샷(전송 시점 값 고정)
      setAutoRead(true);   // 상담 시작 즉시 '종합 풀이'를 자동 생성(sid 반영 후 effect에서 전송)
    } catch (e: any) {
      // 상담 보관함 한도(409) → 정리 안내 팝업. status/code로 정확히 식별한다.
      // (이전엔 친화 메시지 문자열을 매칭해 항상 빗나가 "이미 존재하는 정보예요"가 떴음)
      const isLimit =
        e?.status === 409 ||
        e?.code === "session_limit_reached" ||
        String(e?.code || "").startsWith("session_limit_reached");
      if (isLimit) {
        await refreshSessions();
        setShowSessionLimit(true);
      } else {
        setErr(String(e?.message || e));
      }
    } finally {
      setBusy(false);
    }
  };

  const loadSession = async (sessionId: string) => {
    setErr(null);
    setBusy(true);
    try {
      const r: any = await api.getSession(sessionId);
      setSid(sessionId);
      const msgs: Turn[] = (r.messages || []).map((m: any) => ({
        role: m.role,
        content: m.content,
        sources: m.sources,
        is_preview: m.is_preview,
        preview_revealed: m.preview_revealed,
        reveal_cost: (m as any).reveal_cost,
        message_id: m.id,
      }));
      setTurns(msgs);
      setNeedBirth(false);
      setChart(null);
      setSummary("");
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const newChat = () => {
    setSid(null);
    setTurns([]);
    setChart(null);
    setSummary("");
    setNeedBirth(true);
    setErr(null);
  };

  const sendNonStream = async (msg: string, explainLevel: "easy" | "normal" | "brief" = explainMode()) => {
    const r: any = await api.postMessage(sid!, msg, 4, depth, explainLevel);
    setTurns((t) => [
      ...t,
      {
        role: "assistant",
        content: r.answer,
        sources: r.sources,
        is_preview: r.is_preview,
        preview_revealed: r.preview_revealed,
        reveal_cost: (r as any).reveal_cost,
        message_id: r.assistant_message_id,
        full_length: r.full_length,
        preview_length: r.preview_length,
        credits_charged: r.credits_charged,
        billing_mode: r.billing_mode,
      },
    ]);
    if (isLoggedIn) {
      try {
        const me2 = await api.me();
        setCachedMe(me2);
      } catch {}
    }
  };

  const sendStream = async (msg: string, explainLevel: "easy" | "normal" | "brief" = explainMode()) => {
    setStreaming(true);
    setRefineStage(null); setVerifyElapsed(null);
    setTurns((t) => [...t, { role: "assistant", content: "" }]);
    const url = `/api/chat/sessions/${sid}/messages/stream`;
    const tok = await ensureFreshToken();   // 만료 토큰 → 익명 미리보기 방지(무음 갱신)
    // 무데이터 hang / 무청크 종료 감지 — 첫 콘텐츠가 60초 안 오면 끊고 실패 처리한다.
    // (서버가 연결만 잡고 무데이터일 때 '천간·지지…풀이하는 중' 이 영원히 남던 고착 차단.)
    const ac = new AbortController();
    let gotContent = false;
    let stalled = false;
    const watchdog = window.setTimeout(() => {
      if (!gotContent) { stalled = true; try { ac.abort(); } catch { /* noop */ } }
    }, 60000);
    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(tok ? { Authorization: `Bearer ${tok}` } : {}),
        },
        body: JSON.stringify({ message: msg, top_k: 4, depth, explain_level: explainLevel }),
        signal: ac.signal,
      });
      if (!resp.ok || !resp.body) {
        const t = await resp.text().catch(() => "");
        setTurns((cur) => cur.slice(0, -1));
        if (resp.status === 401) {
          // 세션 만료 → 조용한 먹통(답 안나옴) 대신 로그인 화면으로 안내
          notifySessionExpired();
          return;
        }
        if (resp.status === 402) {
          // 무료 한도 소진 / 크레딧 부족 → 결제 유도 팝업
          setShowPaywall(true);
          return;
        }
        throw new Error(`stream ${resp.status}: ${t}`);
      }
      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      let acc = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() || "";
        for (const part of parts) {
          const lines = part.split("\n");
          let event = "message";
          let data = "";
          for (const line of lines) {
            if (line.startsWith("event:")) event = line.slice(6).trim();
            if (line.startsWith("data:")) data = line.slice(5).trim();
          }
          // 실제 콘텐츠/종료/에러 이벤트 도착 → 워치독 해제(meta/stage 는 콘텐츠 전 단계라 제외)
          if (["chunk", "refine", "cut", "clarify", "done", "error"].includes(event)) {
            gotContent = true; window.clearTimeout(watchdog);
          }
          if (event === "chunk" && data) {
          try {
            const j = JSON.parse(data);
            acc += j.text;
            setTurns((cur) => {
              const copy = [...cur];
              copy[copy.length - 1] = { ...copy[copy.length - 1], content: acc };
              return copy;
            });
          } catch {}
        } else if (event === "meta" && data) {
          try {
            const j = JSON.parse(data);
            setTurns((cur) => {
              const copy = [...cur];
              copy[copy.length - 1] = {
                ...copy[copy.length - 1],
                sources: j.sources,
                billing_mode: j.billing_mode,
                is_preview: j.is_preview,
              };
              return copy;
            });
          } catch {}
        } else if (event === "clarify" && data) {
          // 답변 전 사전 선택질문(Track B): 애매한 질문 → 카드로 선택지 노출(과금·생성 없음).
          try {
            const j = JSON.parse(data);
            setTurns((cur) => {
              const copy = [...cur];
              copy[copy.length - 1] = {
                ...copy[copy.length - 1],
                clarify: { question: j.question, options: j.options || [], key: j.key },
              };
              return copy;
            });
          } catch {}
        } else if (event === "stage" && data) {
          try {
            const j = JSON.parse(data);
            // draft_done / refining / refine_done / verifying(+elapsed: 교정 진행초)
            setRefineStage(j.phase || null);
            setVerifyElapsed(j.phase === "verifying" && typeof j.elapsed === "number" ? j.elapsed : null);
          } catch {}
        } else if (event === "refine" && data) {
          try {
            const j = JSON.parse(data);
            // 외부 LLM 보강 본문으로 페이드 교체
            acc = j.text || acc;
            setTurns((cur) => {
              const copy = [...cur];
              copy[copy.length - 1] = {
                ...copy[copy.length - 1],
                content: acc,
                refined: true,
                evidence: j.evidence,
              };
              return copy;
            });
          } catch {}
        } else if (event === "cut") {
          // 미리보기 한도 도달 — 이후 토큰은 전송되지 않음. 컷 표시 + 미리보기 플래그.
          acc += " …";
          setTurns((cur) => {
            const copy = [...cur];
            copy[copy.length - 1] = {
              ...copy[copy.length - 1],
              content: acc,
              is_preview: true,
              preview_revealed: false,
            };
            return copy;
          });
        } else if (event === "done" && data) {
          try {
            const j = JSON.parse(data);
            setRefineStage(null); setVerifyElapsed(null);
            setTurns((cur) => {
              const copy = [...cur];
              copy[copy.length - 1] = {
                ...copy[copy.length - 1],
                // 서버 최종본으로 화면 재동기화 — 스트림 중 표시는 정리(_tidy_markdown) 전 텍스트라
                // '---'가 남았다. done.content(검증·정리 완료본)로 교체해 화면=저장본 일치(운영자 지적).
                ...(typeof j.content === "string" && j.content ? { content: j.content } : {}),
                is_preview: j.is_preview,
                preview_revealed: j.preview_revealed,
                reveal_cost: j.reveal_cost,
                message_id: j.assistant_message_id,
                full_length: j.full_length,
                preview_length: j.preview_length,
                credits_charged: j.credits_charged,
                billing_mode: j.billing_mode,
                evidence: j.evidence,
                refined: j.refined,
                flash: !!j.flash,
              };
              return copy;
            });
            if (j.flash) {
              // 완료 강조효과(번쩍) — 잠시 후 해제
              setTimeout(() => {
                setTurns((cur) => {
                  const copy = [...cur];
                  const last = copy.length - 1;
                  if (copy[last]) copy[last] = { ...copy[last], flash: false };
                  return copy;
                });
              }, 1400);
            }
          } catch {}
        } else if (event === "error" && data) {
          try {
            const j = JSON.parse(data);
            const d = String(j.detail || "");
            if (
              d.includes("quota_exceeded") ||
              d.includes("insufficient_credits") ||
              d.includes("membership_quota_exhausted")
            ) {
              setShowPaywall(true);
            } else if (j.code === "service_unavailable" || d.includes("연결할 수 없습니다")) {
              setErr(tr("chat.svc_unavailable"));
            } else {
              setErr(d);
            }
          } catch {}
        }
      }
    }
      // 스트림이 콘텐츠 0개로 끝남(무청크 clean-close) → 실패로 처리(빈 말풍선/침묵 방지)
      if (!gotContent) throw new Error("STREAM_STALLED");
      setRefineStage(null); setVerifyElapsed(null);
      if (isLoggedIn) {
        try {
          const me2 = await api.me();
          setCachedMe(me2);
        } catch {}
      }
    } catch (e: any) {
      // 무데이터 hang(abort) / 무청크 종료 → 빈 assistant 말풍선 제거 후 실패 전파(doSend 가 안내)
      setTurns((cur) => {
        const last = cur[cur.length - 1];
        return last && last.role === "assistant" && !last.content ? cur.slice(0, -1) : cur;
      });
      throw (stalled || e?.name === "AbortError") ? new Error("STREAM_STALLED") : e;
    } finally {
      window.clearTimeout(watchdog);
      setRefineStage(null); setVerifyElapsed(null);
      setStreaming(false);
    }
  };

  // 답변 복사/공유/PDF/피드백은 공통 컴포넌트 <AnswerActions/> 가 담당한다.

  const doSend = async (msg: string, explainLevel?: "easy" | "normal" | "brief") => {
    setInput("");
    setDynamicSuggests([]);   // 새 질문 시작 → 이전 추천칩 숨김
    setTurns((t) => [...t, { role: "user", content: msg }]);
    setBusy(true);
    setErr(null);
    try {
      if (useSSE) await sendStream(msg, explainLevel);
      else await sendNonStream(msg, explainLevel);
    } catch (e: any) {
      // 스트림 중도 실패로 빈 답변 말풍선이 남으면 제거(부분 생성분은 유지).
      setTurns((cur) => {
        const last = cur[cur.length - 1];
        return last && last.role === "assistant" && !last.content ? cur.slice(0, -1) : cur;
      });
      const m = String(e?.message || e);
      if (m.includes("402") || m.includes("quota_exceeded") || m.includes("insufficient_credits")) {
        setShowPaywall(true);
      } else if (m.includes("503") || m.includes("연결할 수 없습니다")) {
        setErr(tr("chat.svc_unavailable"));
      } else {
        setErr(m);
      }
    } finally {
      setBusy(false);
      setStreaming(false);
      // 답변 완료 후 그 맥락 기반 후속 추천질문 로드(실패해도 무시 → 정적 폴백은 서버가 처리)
      const s = sid;
      if (s) api.getSuggestions(s).then((r) => setDynamicSuggests(r.suggestions || [])).catch(() => {});
      // [운영자 지시 — 전 메뉴 공통] 검증·보강까지 끝난 최종 답변이 확정되면 그 답변의 '시작점'으로
      // 스크롤 — 스트리밍으로 밑까지 내려간 화면을 되돌려 처음부터 읽게 한다.
      scrollLastAnswerTop();
    }
  };

  function scrollLastAnswerTop() {
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    window.setTimeout(() => {
      const msgs = document.querySelectorAll(".msg.assistant");
      const last = msgs[msgs.length - 1] as HTMLElement | undefined;
      if (last && last.textContent && last.textContent.trim().length > 0) {
        last.style.scrollMarginTop = "64px";
        last.scrollIntoView({ block: "start", behavior: reduced ? "auto" : "smooth" });
      }
    }, 120);
  }

  // 사전 선택질문(Track B) 응답 — 원질문에 맥락을 붙여 답변 생성(새 사용자 말풍선 없이 카드 자리를 답변으로 교체).
  const answerWithContext = async (origMsg: string, ctx: string) => {
    setTurns((cur) => cur.slice(0, -1)); // 사전질문 카드(마지막 assistant 턴) 제거 → sendStream이 답변 placeholder 새로 생성
    setBusy(true);
    setErr(null);
    try {
      await sendStream(`${origMsg}\n\n[상담맥락] ${ctx}`);
    } catch (e: any) {
      setTurns((cur) => {
        const last = cur[cur.length - 1];
        return last && last.role === "assistant" && !last.content ? cur.slice(0, -1) : cur;
      });
      const m = String(e?.message || e);
      if (m.includes("402") || m.includes("quota_exceeded") || m.includes("insufficient_credits")) {
        setShowPaywall(true);
      } else if (m.includes("503") || m.includes("연결할 수 없습니다")) {
        setErr("⚠️ 일시적으로 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
      } else if (m.includes("STREAM_STALLED")) {
        setErr("⚠️ 답변 생성이 지연되고 있어요. 잠시 후 다시 질문해 주세요. (포인트는 차감되지 않았어요)");
      } else {
        setErr(m);
      }
    } finally {
      setBusy(false);
      setStreaming(false);
      const s = sid;
      if (s) api.getSuggestions(s).then((r) => setDynamicSuggests(r.suggestions || [])).catch(() => {});
      scrollLastAnswerTop();   // 최종 답변 확정 → 시작점으로(운영자 지시)
    }
  };

  // 상담 시작 직후(sid 확정) '종합 풀이'를 자동 전송 — 칩 클릭 없이 기본으로 풍부한 분석을 먼저 보여준다.
  // (이후 질문은 기존 빌링대로 무료한도→건별 차감. 빈 세션에서 1회만.)
  useEffect(() => {
    if (autoRead && sid && turns.length === 0) {
      setAutoRead(false);
      void doSend(comprehensiveMsg(worryRef.current));   // 고민 있으면 그 고민에 정조준(판정 먼저)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRead, sid]);

  const send = async () => {
    if (!sid || !input.trim()) return;
    const msg = input.trim();
    // 첫 질문이면 쉽게/전문 한 번 물어본다(이후엔 토글로 변경).
    if (!explainAsked) {
      setPendingMsg(msg);
      setShowExplainPopup(true);
      return;
    }
    await doSend(msg);
  };

  // 안내 팝업에서 선택 → 기억하고 대기 중이던 질문 전송
  const chooseExplain = (mode: "easy" | "normal") => {
    toggleEasy(mode === "easy");
    localStorage.setItem("saju_explain_asked", "1");
    setExplainAsked(true);
    setShowExplainPopup(false);
    const msg = pendingMsg;
    setPendingMsg(null);
    if (msg) doSend(msg, mode); // 선택값을 명시 전달(상태 반영 지연 방지)
  };

  // 팝업 밖 클릭(보류) → 입력창에 질문 복원. 이번 세션에선 다시 묻지 않아
  // 재전송 시 모달이 또 떠 전송이 무한 차단되는 문제를 막는다(저장은 안 함 → 다음 방문 땐 다시 안내).
  const cancelExplainPopup = () => {
    setShowExplainPopup(false);
    setExplainAsked(true);
    if (pendingMsg) setInput(pendingMsg);
    setPendingMsg(null);
  };

  // "나중에 결정할게요" → 질문을 삼키지 않고 표준 풀이로 그대로 전송
  const laterExplainPopup = () => {
    setShowExplainPopup(false);
    setExplainAsked(true);
    const msg = pendingMsg;
    setPendingMsg(null);
    if (msg) doSend(msg, "normal");
  };

  const reveal = async (mid: number, idx: number) => {
    if (!isLoggedIn) {
      navigate("/login");
      return;
    }
    if (!sid || revealing) return;  // 차감 중 더블클릭 방지
    setRevealing(true);
    try {
      const r = await api.revealMessage(sid, mid);
      setTurns((cur) => {
        const copy = [...cur];
        copy[idx] = { ...copy[idx], content: r.content, preview_revealed: true };
        return copy;
      });
      const me2 = await api.me();
      setCachedMe(me2);
    } catch (e: any) {
      const m = String(e?.message || "");
      if (m.includes("insufficient_credits") || m.includes("quota_exceeded") || m.includes("402")) {
        openCharge(tr("chat.need_points"));
      } else {
        setErr(m);
      }
    } finally {
      setRevealing(false);
    }
  };

  const showBanners = !me?.ads_hidden;

  // 공통 FollowupBilling 의 freeNote — 무료/무과금 상태면 안내 문자열, 유료 차감이면 null(→ 차감 배지 표시).
  //   사주상담만 일일무료 한도가 있어 여기서 판단(다른 메뉴는 입장료 결제라 추가질문 항상 차감).
  function followupFreeNote(): string | null {
    if (!me) return null;   // 비로그인은 FollowupBilling 이 자체 안내(🔒)
    if ((me.level ?? 9) <= 1) return "관리자 · 무과금 (무제한)";
    if (me.is_member)
      return `연간회원 · 무과금 · 잔여 ${(me.membership_remaining ?? 0).toLocaleString()}/${(me.membership_quota ?? 0).toLocaleString()}회`;
    if ((me.free_remaining ?? 0) > 0)
      return `이번 질문 무료 · 남은 무료 ${me.free_remaining}/${me.free_quota_count ?? 3}회${depth === "deep" ? " (심화도 무료)" : ""}`;
    return null;   // 유료 차감 → FollowupBilling 차감 배지(💳 N P 차감)
  }

  // 답변 완료 후 적용된 과금 표시
  function billingApplied(t: Turn): string | null {
    switch (t.billing_mode) {
      case "free_quota":
      case "free_daily":
        return tr("chat.ba_free");
      case "membership_full":
        return tr("chat.ba_member");
      case "admin_full":
        return tr("chat.ba_admin");
      case "paid_full":
        return tr("chat.ba_paid", { cost: fmtNum(t.credits_charged ?? 0) });
      case "anonymous_preview":
        return tr("chat.ba_anon");
      default:
        return null;
    }
  }

  return (
    <div className="chat-layout">
      <main className="chat-main">
        <PrivacyNotice variant="answer" />
        {STUDIO_NAME && (
          <div className="studio-header">
            <span className="studio-name">{STUDIO_NAME}</span>
          </div>
        )}
        {showBanners && <BannerSlot slot="top" height={90} />}

        {!sid && (
          <>
            <header className="compat-hero saju-hero">
              <div className="compat-hero-badge">{tr("chat.hero_badge")}</div>
              <h1>{tr("chat.hero_title")}</h1>
              <p>{tr("chat.hero_desc")}</p>
            </header>

            {/* 신뢰 스트립 — 실제 구현된 계산 로직을 그대로 노출(과장 없음) */}
            <div className="trust-strip" aria-label={tr("chat.trust_aria")}>
              <div className="trust-item">
                <span className="ti-ico" aria-hidden="true">🕰️</span>
                <span className="ti-title">{tr("chat.t1_title")}</span>
                <span className="ti-desc">{tr("chat.t1_desc")}</span>
              </div>
              <div className="trust-item">
                <span className="ti-ico" aria-hidden="true">📐</span>
                <span className="ti-title">{tr("chat.t2_title")}</span>
                <span className="ti-desc">{tr("chat.t2_desc")}</span>
              </div>
              <div className="trust-item">
                <span className="ti-ico" aria-hidden="true">🧭</span>
                <span className="ti-title">{tr("chat.t3_title")}</span>
                <span className="ti-desc">{tr("chat.t3_desc")}</span>
              </div>
              <div className="trust-item">
                <span className="ti-ico" aria-hidden="true">📚</span>
                <span className="ti-title">{tr("chat.t4_title")}</span>
                <span className="ti-desc">{tr("chat.t4_desc")}</span>
              </div>
            </div>

            <ReviewStrip source="chat" title="이용자 후기" limit={8} />

            <div className="gemini-greeting">
              <p className="hello">{me?.nickname ? tr("chat.hello_named", { name: me.nickname }) : tr("chat.hello")}</p>
              <p className="sub">{tr("chat.greet_sub")}</p>
            </div>
          </>
        )}

        {needBirth && (
          <div className="card saju-input-card">
            <div className="card-head-row">
              <h3 style={{ margin: 0 }}>{tr("chat.input_title")}</h3>
              <label className="remember-check" title={tr("chat.remember_title")}>
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(e) => toggleRemember(e.target.checked)}
                />
                <span className="rc-switch" aria-hidden><i /></span>
                <span className="rc-txt">
                  💾 내 사주정보 기억하기
                  <em>{remember ? "다음부터 자동 입력돼요" : "켜면 매번 입력 안 해도 돼요"}</em>
                </span>
              </label>
            </div>
            <p className="card-sub">{tr("chat.card_sub")}</p>

            {/* 기억된 내 정보 — 표준 화면(공용 BirthFields)과 동일한 강조 카드.
                운영자 지적: 상담(사주상담)만 이 카드가 없어 '저장됨'이 안 보였다 → 동일 마크업/클래스로 통일. */}
            {remember && birth.birth_date && (
              <div className="bf-remembered" role="status">
                <span className="bfr-badge">🔖 기억된 내 정보</span>
                <span className="bfr-main">
                  {readableBirth({ ...birth, birth_time: birth.birth_time || "", unknown_time: unknownTime } as BirthValue)}
                </span>
                <span className="bfr-sub">자동으로 불러왔어요 · 바꾸려면 아래에서 수정하세요</span>
              </div>
            )}

            {/* 빠른 입력 — 숫자만 입력하면 자동 완성(가장 빠른 길) */}
            <div className="bf-quick">
              <div className="bf-quick-top">
                <span className="bf-quick-label">{tr("chat.quick_label")}</span>
                <span className="bf-quick-sub">{tr("chat.quick_sub")}</span>
              </div>
              <div className="bf-quick-row">
                <input
                  ref={quickRef}
                  className="bf-quick-input"
                  type="text" inputMode="numeric" maxLength={14}
                  placeholder={tr("chat.quick_ph")}
                  value={quick}
                  onChange={(e) => applyQuick(e.target.value)}
                />
                {/* 적용은 React state(quick)가 아니라 실제 DOM 값을 읽는다 — 자동완성·붙여넣기·
                    IME 등 onChange가 안 걸린 채 값이 들어와도 항상 화면의 값을 반영(무반응 버그 차단). */}
                <button type="button" className="bf-quick-btn"
                        onClick={() => applyQuick(quickRef.current?.value ?? quick)}>{tr("chat.apply")}</button>
              </div>
              <div className={`bf-quick-hint${quickInfo && quickInfo.startsWith("✓") ? " ok" : quickInfo ? " warn" : ""}`}>
                {quickInfo || tr("chat.quick_hint")}
              </div>
            </div>

            <div className="bf-or"><span>{tr("chat.or_manual")}</span></div>

            {/* 직접 입력 — 전 메뉴 공통 프리미엄 그리드(생년월일·시각은 한 줄, 성별·달력은 토글) */}
            <div className="bf-grid">
              <div className="bf-field bf-field-wide">
                <label>{tr("chat.f_birth")}</label>
                <div className="bf-datebox">
                  <input
                    className="bf-input"
                    type="text" inputMode="numeric" maxLength={10}
                    placeholder={tr("chat.birth_ph")}
                    value={dateText}
                    onChange={(e) => typeDate(e.target.value)}
                  />
                  <button type="button" className="bf-cal-btn" title={tr("chat.cal_title")}
                          onClick={() => { const el = dateRef.current; if (!el) return; (el as any).showPicker ? (el as any).showPicker() : el.focus(); }}>📅</button>
                  <input ref={dateRef} type="date" className="bf-date-native" tabIndex={-1} aria-hidden
                         value={birth.birth_date}
                         onChange={(e) => setBirth({ ...birth, birth_date: e.target.value })} />
                </div>
              </div>
              <div className="bf-field bf-field-wide">
                <label>{tr("chat.f_time")} <span className="bf-opt">{tr("chat.opt")}</span></label>
                <div className="bf-time">
                  <TimeSelect
                    value={birth.birth_time || ""}
                    disabled={unknownTime}
                    onChange={(v) => setBirth({ ...birth, birth_time: v || null })}
                  />
                  <button type="button" className={`bf-chip ${unknownTime ? "on" : ""}`}
                          onClick={() => setUnknownTime((u) => !u)}>{tr("chat.unknown_time")}</button>
                </div>
                <div className="bf-time-hint" style={{ fontSize: 12, color: "#8a8f98", marginTop: 4 }}>
                  {unknownTime ? tr("chat.time_hint_unknown") : tr("chat.time_hint_default")}
                </div>
              </div>
              <div className="bf-field">
                <label>{tr("chat.f_gender")}</label>
                <div className="bf-seg">
                  <button type="button" className={birth.gender === "male" ? "on" : ""}
                          onClick={() => setBirth({ ...birth, gender: "male" })}>{tr("chat.male")}</button>
                  <button type="button" className={birth.gender === "female" ? "on" : ""}
                          onClick={() => setBirth({ ...birth, gender: "female" })}>{tr("chat.female")}</button>
                </div>
              </div>
              <div className="bf-field">
                <label>{tr("chat.f_calendar")}</label>
                <div className="bf-seg">
                  <button type="button" className={birth.calendar === "solar" ? "on" : ""}
                          onClick={() => setBirth({ ...birth, calendar: "solar", is_leap_month: false })}>{tr("chat.solar")}</button>
                  <button type="button" className={birth.calendar === "lunar" ? "on" : ""}
                          onClick={() => setBirth({ ...birth, calendar: "lunar" })}>{tr("chat.lunar")}</button>
                </div>
              </div>
            </div>

            <AdvancedBirthSettings value={birth} onChange={(patch) => setBirth((prev) => ({ ...prev, ...patch }))} />

            {/* (선택) 요즘 가장 큰 고민 — 있으면 종합풀이를 이 고민에 정조준해 '한 줄 판정'부터 시작한다. */}
            <div className="bf-field bf-worry">
              <label>💬 요즘 가장 큰 고민 <span className="bf-opt">선택 · 적으면 이 고민에 맞춰 풀이</span></label>
              <input
                className="bf-input"
                type="text" maxLength={100}
                placeholder="예: 내년에 이직할지, 지금 회사에 남을지 고민이에요"
                value={worry}
                onChange={(e) => setWorry(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && dateText && !busy) startSession(); }}
              />
            </div>

            {!isLoggedIn && (
              <div style={{ marginTop: 8, fontSize: 12, color: "#aa6600" }}>
                <Trans i18nKey="chat.guest_hint" components={{ a: <Link to="/login" /> }} />
              </div>
            )}
            {/* 메인 CTA — 입력을 마치면 자연히 시선이 닿는 폼 하단 중앙 큰 버튼 */}
            <div className="chat-start-actions">
              <button className="chat-cta" onClick={startSession} disabled={busy || !dateText}>
                {busy ? tr("chat.cta_prep") : tr("chat.cta_start")}
              </button>
            </div>
            {!dateText && <div className="cta-hint">{tr("chat.cta_hint")}</div>}
            <p className="saju-assure">
              <Trans i18nKey="chat.assure" components={{ b: <b /> }} />
            </p>
            {err && <div className="err">{err}</div>}
          </div>
        )}

        {/* 비로그인 사용자: 사주입력 하단에 로그인/회원가입 인라인 표시 (좌측 로그인 버튼은 유지) */}
        {!me && (
          <div className="card guest-login-card">
            <LoginForm variant="inline" />
          </div>
        )}

        {chart && (
          <div className="card">
            <div className="chart-head">
              {(() => {
                const av = zodiacAvatar(chart.pillars?.year?.branch, birth.birth_date);
                return av ? <img className="chart-zodiac" src={av.src} alt={zodiacLabel(av.zodiac)} width={46} height={46} loading="lazy" /> : null;
              })()}
              <h3 style={{ marginTop: 0 }}>{tr("chat.chart_title")}</h3>
            </div>
            <SajuChart chart={chart} />
            {/* A-1: 이 명식 그대로 상담사에게 — 접수 시 명식이 자동 전달돼 중복 설명 불필요.
                타로 '이 카드로 1:1 상담'과 동일한 강조 배너(FLUX 엠블럼) — 눈에 잘 띄게(운영자 지시) */}
            {me && sid && (
              <ConsultBanner
                title="이 명식으로 1:1 상담"
                desc="방금 본 사주 명식이 그대로 전해져요 — 사주 상담사와 이 명식으로 상담합니다"
                onClick={() =>
                  window.dispatchEvent(
                    new CustomEvent("saju:consult-open", {
                      detail: { kind: "saju", refId: sid, label: `${birth.birth_date} 명식` },
                    })
                  )
                }
              />
            )}
            {/* 명식 요약 원문(오행분포·억부·조후용신·대운·계산기준 등 내부 데이터)은 관리자에게만 노출.
               일반 사용자는 위의 시각적 명식표만 본다. (백엔드도 비관리자에겐 saju_summary 미전송) */}
            {summary && me?.role === "admin" && (
              <details style={{ marginTop: 8 }}>
                <summary style={{ cursor: "pointer", fontSize: 12, color: "#888" }}>{tr("chat.internal_data")}</summary>
                <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", fontSize: 12, color: "#555", marginTop: 6 }}>{summary}</pre>
              </details>
            )}
          </div>
        )}

        {sid && (
          <div className="card">
            <h3 style={{ marginTop: 0 }}>{tr("chat.consult")}</h3>
            {showBanners && <BannerSlot slot="chat_top_1" height={60} />}
            {turns.map((t, i) => (
              <div key={i} className={`msg ${t.role}${t.flash ? " done-flash" : ""}`}>
                <div className="role">{t.role === "user" ? tr("chat.role_me") : tr("chat.role_friend")}</div>
                <div
                  className={t.refined ? "refine-fade" : undefined}
                  style={{ whiteSpace: "pre-wrap" }}
                >
                  {renderRich(t.role === "user" ? t.content.split("\n\n[상담맥락]")[0] : t.content)}
                </div>
                {t.role === "assistant" && t.clarify && !t.content && (
                  <div
                    style={{
                      marginTop: 8, padding: "12px 14px", borderRadius: 12,
                      background: "rgba(124,92,255,0.06)", border: "1px solid rgba(124,92,255,0.28)",
                    }}
                  >
                    <div style={{ fontWeight: 600, marginBottom: 10, lineHeight: 1.5 }}>
                      🔎 {t.clarify.question}
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      {t.clarify.options.map((opt, k) => (
                        <button
                          key={k}
                          disabled={busy}
                          onClick={() => answerWithContext(turns[i - 1]?.content || "", opt)}
                          style={{
                            padding: "8px 14px", borderRadius: 20, cursor: busy ? "default" : "pointer",
                            border: "1px solid rgba(124,92,255,0.5)", background: "#fff", color: "#5b3fd6",
                            fontSize: 14, fontWeight: 500,
                          }}
                        >
                          {opt}
                        </button>
                      ))}
                      <button
                        disabled={busy}
                        onClick={() =>
                          answerWithContext(turns[i - 1]?.content || "", "(선택 안 함 — 전체적으로 봐주세요)")
                        }
                        style={{
                          padding: "8px 14px", borderRadius: 20, cursor: busy ? "default" : "pointer",
                          border: "1px solid #ddd", background: "transparent", color: "#888", fontSize: 13,
                        }}
                      >
                        그냥 전체적으로 봐주세요
                      </button>
                    </div>
                  </div>
                )}
                {t.role === "assistant" && streaming && !t.clarify && i === turns.length - 1 && (
                  <div className="thinking-indicator">
                    <span className="dot-pulse" aria-hidden="true"></span>
                    <span>
                      {refineStage === "verifying"
                        ? tr("chat.think_verify")
                        : refineStage === "refining"
                        ? tr("chat.think_refine")
                        : refineStage === "draft_done"
                        ? tr("chat.think_draft")
                        : refineStage === "refine_done"
                        ? tr("chat.think_refine_done")
                        : !t.content
                        ? tr("chat.think_start")
                        : tr("chat.think_writing")}
                      <span className="thinking-dots" aria-hidden="true"></span>
                    </span>
                  </div>
                )}
                {t.role === "assistant" && t.refined && (
                  <span className="refined-badge" title={tr("chat.refined_title")}>
                    {tr("chat.refined_badge")}
                  </span>
                )}
                {t.role === "assistant" &&
                  !(streaming && i === turns.length - 1) &&
                  billingApplied(t) && (
                    <div className="billing-applied">{billingApplied(t)}</div>
                  )}
                {t.role === "assistant" && t.content && !(streaming && i === turns.length - 1) &&
                  !(t.is_preview && !t.preview_revealed) && (   /* 미리보기(결제 전 잘린 답변)엔 공유/PDF/영상 숨김 */
                  <AnswerActions
                    text={stripMarkdown(t.content)}
                    pdfContent={t.content}
                    messageId={t.message_id}
                    sessionId={sid || undefined}
                    initialFeedback={t.feedback}
                    isLast={i === turns.length - 1 && !streaming}
                    pdf={{
                      docTitle: tr("chat.pdf_doc", { name: memberName }),
                      personLine: tr("chat.pdf_person", { name: memberName }),
                      item:
                        (turns[i - 1]?.role === "user" ? turns[i - 1].content : "").slice(0, 40) ||
                        tr("chat.pdf_item"),
                    }}
                  />
                )}
                {t.role === "assistant" && t.is_preview && !t.preview_revealed && t.message_id && (
                  <div className="reveal-cta">
                    <span className="reveal-cta-lock"><Trans i18nKey="chat.reveal_lock" components={{ b: <b /> }} /></span>
                    <button className="reveal-cta-btn" onClick={() => reveal(t.message_id!, i)} disabled={revealing}>
                      {revealing ? tr("chat.revealing") : <>{tr("chat.reveal_btn")} <b>{fmtNum(t.reveal_cost ?? 10000)}{tr("pay.pt")}</b></>}
                    </button>
                  </div>
                )}
                {t.role === "assistant" &&
                  me?.role === "admin" &&  /* 풀이 근거(명식근거·자료출처)는 영업비밀 → 관리자만 */
                  ((t.evidence && t.evidence.length > 0) || (t.sources && t.sources.length > 0)) &&
                  !(streaming && i === turns.length - 1) && (
                    <details className="sources evidence-block" style={{ marginTop: 6 }}>
                      <summary><strong>{tr("chat.evidence_summary")}</strong></summary>
                      {t.evidence && t.evidence.length > 0 && (
                        <div style={{ marginTop: 4 }}>
                          <div className="evi-head">{tr("chat.evi_saju")}</div>
                          <ul style={{ margin: "2px 0 0 16px", padding: 0 }}>
                            {t.evidence.map((e, j) => (
                              <li key={j}>{e}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {t.sources && t.sources.length > 0 && (
                        <div style={{ marginTop: 6 }}>
                          <div className="evi-head">{tr("chat.evi_source", { n: t.sources.length })}</div>
                          <ul style={{ margin: "2px 0 0 16px", padding: 0 }}>
                            {t.sources.map((s, j) => (
                              <li key={j}>
                                <code>{s.source}</code> · score={s.score.toFixed(3)}
                                {s.text_preview && <div style={{ color: "#666" }}>{s.text_preview}</div>}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </details>
                  )}
                {t.role === "assistant" && showBanners && !(streaming && i === turns.length - 1) && (
                  <AdSlot slot="answer_bottom" height={60} />
                )}
              </div>
            ))}
            {turns.length === 0 && (
              <div className="suggest-chips">
                {SUGGEST_CHIPS.map((q) => (
                  <button key={q} className="chip" onClick={() => onChipClick(q)} disabled={busy}>
                    {q}
                  </button>
                ))}
              </div>
            )}
            {/* 답변 완료 후: 그 답변 맥락에 이어지는 추천질문(동적). 추가 상담 유도 */}
            {turns.length > 0 && !streaming && !busy && dynamicSuggests.length > 0 &&
              turns[turns.length - 1].role === "assistant" && (
                <div className="suggest-chips followup">
                  <div className="suggest-label">{tr("chat.followup_label")}</div>
                  {dynamicSuggests.map((q) => (
                    <button key={q} className="chip" onClick={() => onChipClick(q)} disabled={busy}>
                      {q}
                    </button>
                  ))}
                </div>
              )}
            {/* 상담 전체 종합 감정서 — 답변이 2건 이상이면 노출(여러 Q&A를 하나로 정리) */}
            {!streaming && !busy &&
              turns.filter((t) => t.role === "assistant" && t.content).length >= 2 && (
                <div className="report-row">
                  <ConsultationReportButton
                    build={(): ReportReq | null => {
                      const conversation = turns
                        .filter((t) => t.content)
                        .map((t) => ({ role: t.role, content: stripMarkdown(t.content) }));
                      return {
                        doc_title: tr("chat.report_doc", { name: memberName }),
                        person_line: tr("chat.report_person", { name: memberName }),
                        item: tr("chat.report_item"),
                        conversation,
                        topic: tr("chat.report_topic"),
                        session_id: sid || undefined,   // 명식 패널(한지 위 본인 사주) 포함
                      };
                    }}
                  />
                  <span className="report-hint">{tr("chat.report_hint")}</span>
                </div>
              )}
            <div className="composer">
              <div className="composer-pill">
                <textarea
                  ref={taRef}
                  className="chat-input"
                  rows={1}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      if (!busy) send();
                    }
                  }}
                  placeholder={tr("chat.composer_ph")}
                  disabled={busy}
                />
                <button
                  className="send-btn"
                  onClick={send}
                  disabled={busy || !input.trim()}
                  title={tr("chat.send")}
                  aria-label={tr("chat.send")}
                >
                  {streaming ? "⋯" : "➤"}
                </button>
              </div>
              <div className="composer-stream">
                {streaming ? (
                  <span className="alive-status alive-live" title="응답 생성 중">
                    <TypingDots /> 상담친구가 답변을 작성하고 있어요
                  </span>
                ) : (
                  <span className="alive-status idle">{tr("chat.idle")}</span>
                )}
                <label style={{ marginLeft: "auto" }}>
                  <input type="checkbox" checked={useSSE} onChange={(e) => setUseSSE(e.target.checked)} /> {tr("chat.streaming")}
                </label>
                <label style={{ marginLeft: 12 }} title={tr("chat.brief_title")}>
                  <input type="checkbox" checked={brief} onChange={(e) => toggleBrief(e.target.checked)} /> {tr("chat.brief")}
                </label>
              </div>
            </div>
            {/* 추가질문 기본/심화 + 차감 배지 — 전 메뉴 공통 FollowupBilling(운영자 지적: UI 동일·차감 분명히).
                사주상담은 일일무료 한도가 있어 freeNote 로 무료 상태를 넘긴다. easy 토글은 상담 전용이라 옆에 유지. */}
            <div className="depth-bar">
              <FollowupBilling me={me} depth={depth} onDepth={setDepth} freeNote={followupFreeNote()} />
              <label
                className={`easy-toggle${easy ? " on" : ""}`}
                title={tr("chat.easy_title")}
              >
                <input type="checkbox" checked={easy} onChange={(e) => toggleEasy(e.target.checked)} />
                <span className="easy-ico" aria-hidden="true">🌿</span>
                {tr("chat.easy")}
              </label>
            </div>
            {/* 질문창 아래 과금 안내 (현재 depth 기준 무료/차감/잔여) */}
            <div className="billing-hint">
              <span className="bh-main">💳 {billingHint()}</span>
              {me && (me.level ?? 9) > 1 && !me.is_member && (
                <span className="bh-sub">
                  {tr("chat.bh_sub_deep", {
                    creditNote:
                      typeof me.credit_cost_deep === "number" && typeof me.credit_cost_basic === "number"
                        ? tr("chat.bh_sub_credit", { deep: fmtNum(me.credit_cost_deep), basic: fmtNum(me.credit_cost_basic) })
                        : "",
                  })}
                </span>
              )}
            </div>
            {err && <div className="err">{err}</div>}
          </div>
        )}
      </main>

      {showExplainPopup && (
        <div className="pwa-overlay" onClick={cancelExplainPopup}>
          <div className="pwa-modal explain-modal" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginTop: 0 }}>{tr("chat.explain_title")}</h3>
            <p style={{ color: "var(--ink-600, #555)", fontSize: 14, marginBottom: 16 }}>
              <Trans i18nKey="chat.explain_desc" components={{ br: <br />, b: <b /> }} />
            </p>
            <div className="explain-choices">
              <button className="explain-choice easy" onClick={() => chooseExplain("easy")}>
                <span className="ec-ico">🌿</span>
                <span className="ec-title">{tr("chat.ec_easy_title")}</span>
                <span className="ec-desc">{tr("chat.ec_easy_desc")}</span>
              </button>
              <button className="explain-choice pro" onClick={() => chooseExplain("normal")}>
                <span className="ec-ico">📘</span>
                <span className="ec-title">{tr("chat.ec_pro_title")}</span>
                <span className="ec-desc">{tr("chat.ec_pro_desc")}</span>
              </button>
            </div>
            <button className="ghost" style={{ marginTop: 12 }} onClick={laterExplainPopup}>
              {tr("chat.explain_later")}
            </button>
          </div>
        </div>
      )}

      {showPaywall && (
        <div className="pwa-overlay" onClick={() => setShowPaywall(false)}>
          <div className="pwa-modal" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginTop: 0 }}>{tr("chat.pw_title")}</h3>
            <p style={{ color: "var(--ink-soft, #555)", fontSize: 14 }}>
              {isLoggedIn ? tr("chat.pw_desc_in") : tr("chat.pw_desc_guest")}
            </p>
            <div className="pwa-actions">
              {isLoggedIn ? (
                <button onClick={() => openCharge()}>{tr("chat.pw_charge")}</button>
              ) : (
                <button onClick={() => navigate("/login")}>{tr("chat.pw_login")}</button>
              )}
              <button className="ghost" onClick={() => setShowPaywall(false)}>
                {tr("chat.close")}
              </button>
            </div>
          </div>
        </div>
      )}

      {showSessionLimit && (() => {
        const full = sessions.length >= maxSessions;
        const pct = Math.min(100, Math.round((sessions.length / Math.max(1, maxSessions)) * 100));
        return (
        <div className="pwa-overlay" onClick={() => setShowSessionLimit(false)}>
          <div className="pwa-modal sl-modal" onClick={(e) => e.stopPropagation()}>
            <div className="sl-head">
              <span className="sl-head-ico" aria-hidden="true">🗂️</span>
              <div>
                <h3>{tr("chat.sl_title")}</h3>
                <p className="sl-sub">{tr("chat.sl_sub")}</p>
              </div>
            </div>
            <p className="sl-desc">
              <Trans i18nKey="chat.sl_desc" values={{ max: maxSessions }} components={{ b: <b /> }} />
            </p>
            <div className="sl-gauge" role="img" aria-label={tr("chat.sl_gauge_aria", { cur: sessions.length, max: maxSessions })}>
              <div className="sl-gauge-track">
                <span className={`sl-gauge-fill${full ? " full" : ""}`} style={{ width: `${pct}%` }} />
              </div>
              <span className="sl-gauge-num">{sessions.length} / {maxSessions}</span>
            </div>
            <div className="sl-toolbar">
              <label className="sl-selall">
                <input
                  type="checkbox"
                  checked={sessions.length > 0 && sel.count === sessions.length}
                  ref={(el) => { if (el) el.indeterminate = sel.count > 0 && sel.count < sessions.length; }}
                  onChange={(e) => sel.setAll(sessions.map((s) => s.session_id), e.target.checked)}
                />
                전체 선택
              </label>
              <button
                className="sl-bulk-del"
                disabled={sel.count === 0 || bulkDeleting}
                onClick={bulkDeleteSessions}
              >
                {bulkDeleting ? "삭제 중…" : `🗑 선택 삭제${sel.count ? ` (${sel.count})` : ""}`}
              </button>
            </div>
            <div className="sl-list">
              {sessions.map((s) => (
                <div
                  key={s.session_id}
                  className={`sl-row${sid === s.session_id ? " current" : ""}${sel.has(s.session_id) ? " sel" : ""}`}
                  onClick={() => sel.toggle(s.session_id)}
                  role="checkbox"
                  aria-checked={sel.has(s.session_id)}
                >
                  <input
                    type="checkbox"
                    className="sl-check"
                    checked={sel.has(s.session_id)}
                    readOnly
                    tabIndex={-1}
                    style={{ pointerEvents: "none" }}
                  />
                  <span className="sl-body">
                    <span className="sl-title">
                      {s.title || tr("chat.sl_untitled")}
                      {sid === s.session_id && <span className="sl-badge">{tr("chat.sl_current")}</span>}
                    </span>
                    <span className="sl-meta">
                      {tr("chat.sl_meta", { date: shortDate(s.created_at), birth: s.birth_date, n: s.message_count })}
                    </span>
                  </span>
                  <button
                    className="sl-del"
                    onClick={(e) => { e.stopPropagation(); removeSession(s.session_id, s.title || s.birth_date); }}
                  >
                    {tr("chat.sl_delete")}
                  </button>
                </div>
              ))}
            </div>
            <div className="pwa-actions">
              <button
                className="primary"
                disabled={full}
                onClick={() => {
                  setShowSessionLimit(false);
                  startSession();
                }}
              >
                {full ? tr("chat.sl_start_full") : tr("chat.sl_start")}
              </button>
              <button className="ghost" onClick={() => setShowSessionLimit(false)}>
                {tr("chat.sl_later")}
              </button>
            </div>
          </div>
        </div>
        );
      })()}
    </div>
  );
}
