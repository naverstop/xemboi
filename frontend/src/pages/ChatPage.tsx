/** Gemini 풍의 사주 채팅 UI.
 * - 좌측: 내 세션 사이드바 (회원만), 새 대화 버튼
 * - 우측: 생일 입력 → 세션 → SajuChart + 배너 + 채팅
 * - 미리보기 메시지에는 더보기(500P) 버튼
 */
import { useEffect, useRef, useState } from "react";
import AdvancedBirthSettings from "../components/AdvancedBirthSettings";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, Birth, useMe, getToken, setCachedMe, notifySessionExpired, Source } from "../api";
import { fmtKSTDate } from "../lib/datetime";
import SajuChart, { Chart } from "../components/SajuChart";
import { zodiacAvatar } from "../lib/zodiacAvatar";
import TimeSelect from "../components/TimeSelect";
import BannerSlot from "../components/BannerSlot";
import AdSlot from "../components/AdSlot";
import LoginForm from "../components/LoginForm";
import AnswerActions from "../components/AnswerActions";
import ConsultationReportButton, { type ReportReq } from "../components/ConsultationReportButton";
import { renderRich, stripMarkdown } from "../lib/format";
import { resolveBirthTime, DEFAULT_BIRTH_TIME } from "../lib/birthTime";
import { useCharge } from "../components/ChargeModal";

// 철학관 상호(항목 D) — 운영 설정값 연동은 P3, 우선 환경값으로 표시.
const STUDIO_NAME = (import.meta.env.VITE_STUDIO_NAME as string | undefined) || "";

// 추천 질문 칩 (suggestion chips)
// 상담 시작 시 자동 전송하는 '종합 풀이' 질문(칩 클릭 없이 기본으로 풍부하게). 첫 답변=이 종합 풀이.
const COMPREHENSIVE_READING =
  "내 사주를 종합적으로 풀어주세요 — 성격·육친·건강운과, 올해 일어날 수 있는 일, 그리고 이번 달부터 월별로 생길 수 있는 일(직업·재물·인연 포함)을 알차고 풍부하게.";
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
  const { openCharge } = useCharge();
  // 상담서(PDF) 제목/대상에 쓰는 회원 표시명 — 닉네임 → 이메일 아이디 → "고객"
  const memberName = me?.nickname?.trim() || (me?.email ? me.email.split("@")[0] : "") || "고객";
  const [birth, setBirth] = useState<Birth>({
    birth_date: "1990-03-15",
    birth_time: "",          // 비워두면 제출 시 00:30 기본('시 모름'이면 시주 제외)
    calendar: "solar",
    gender: "male",
    is_leap_month: false,
    apply_true_solar_time: true,
    birth_longitude: 126.98,
    night_zi_mode: "yaja",
  });
  const [dateText, setDateText] = useState("1990-03-15");  // 생년월일 직접 입력 텍스트
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

  // P4: 세션 수 제한 정리 모달
  const [showSessionLimit, setShowSessionLimit] = useState(false);
  const [maxSessions, setMaxSessions] = useState(30);

  // 빠른 숫자 입력(YYYYMMDDHHMM) + 사주정보 기억하기
  const [quick, setQuick] = useState("");
  const [quickInfo, setQuickInfo] = useState<string | null>(null);
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
  }, [me]);

  // 로그인: 서버에 저장된 본인 사주 자동 채움 + 기억하기 기본 ON (사용자별 1회)
  const profileLoadedFor = useRef<number | null>(null);
  useEffect(() => {
    if (!me || profileLoadedFor.current === me.id) return;
    profileLoadedFor.current = me.id;
    if (me.saju_profile && me.saju_profile.birth_date) {
      setBirth((b) => ({ ...b, ...me.saju_profile }));
      setUnknownTime(!String(me.saju_profile.birth_time || "").trim());
    }
    setRemember(true);   // 로그인 사용자는 본인 사주 재사용이 기본 → 저장 ON
  }, [me]);

  // 외부에서 birth_date가 바뀌면(자동채움·달력선택·프로필 로드) 생년월일 텍스트칸 동기화.
  // 빠른입력(parseQuick)은 자체적으로 setDateText 하지만, 자동채움 경로는 birth만 바꾸므로 필요.
  useEffect(() => { setDateText(birth.birth_date || ""); }, [birth.birth_date]);

  // 기억하기 ON 상태에서 사주정보가 바뀌면 저장(로그인=서버, 비로그인=localStorage). 서버는 디바운스.
  // 저장 응답(최신 saju_profile 포함 MeResp)을 캐시에 반영해야 재입장 시 자동 채움이 작동한다.
  useEffect(() => {
    if (!remember || !birth.birth_date) return;
    // '시 모름'은 null로 저장돼야 재입장 시 시주 제외가 그대로 복원된다.
    const toSave: Birth = { ...birth, birth_time: resolveBirthTime(birth.birth_time, unknownTime) };
    if (me) {
      const t = setTimeout(() => { api.saveSajuProfile(toSave).then(setCachedMe).catch(() => {}); }, 900);
      return () => clearTimeout(t);
    }
    localStorage.setItem("saju_birth_saved", JSON.stringify(toSave));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [birth, remember, unknownTime]);

  const toggleRemember = (checked: boolean) => {
    setRemember(checked);
    if (me) {
      api.saveSajuProfile(checked ? birth : null).then(setCachedMe).catch(() => {});
    } else if (checked) {
      localStorage.setItem("saju_birth_remember", "1");
      localStorage.setItem("saju_birth_saved", JSON.stringify(birth));
    } else {
      localStorage.removeItem("saju_birth_remember");
      localStorage.removeItem("saju_birth_saved");
    }
  };

  // "197503210430" → 1975-03-21 04:30 자동 분해 입력
  const applyQuick = (raw: string) => {
    setQuick(raw);
    const d = raw.replace(/\D/g, "");
    if (d.length === 0) {
      setQuickInfo(null);
      return;
    }
    if (d.length !== 8 && d.length !== 10 && d.length !== 12) {
      setQuickInfo("8자리(생년월일) 또는 12자리(생년월일+시분)를 입력해 주세요.");
      return;
    }
    const y = d.slice(0, 4), mo = d.slice(4, 6), da = d.slice(6, 8);
    const yi = +y, moi = +mo, dai = +da;
    if (yi < 1900 || yi > 2100 || moi < 1 || moi > 12 || dai < 1 || dai > 31) {
      setQuickInfo("생년월일 숫자를 다시 확인해 주세요.");
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
        setQuickInfo("시각(시·분) 숫자를 다시 확인해 주세요.");
        return;
      }
    } else if (!unknownTime && !String(next.birth_time || "").trim()) {
      // 시각 미입력 → 자동으로 00:30 채워 매끄럽게 진행('시 모름'이면 제외 유지)
      next.birth_time = DEFAULT_BIRTH_TIME;
      timeLabel = ` ${DEFAULT_BIRTH_TIME}`;
    }
    setBirth(next);
    setDateText(next.birth_date);
    setQuickInfo(`✓ ${yi}년 ${moi}월 ${dai}일${timeLabel} 자동 입력됨`);
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
    if (!window.confirm(`"${label}" 상담을 삭제할까요?\n삭제한 상담 기록은 복구할 수 없어요.`)) return;
    try {
      await api.deleteChatSession(id);
      await refreshSessions();
      window.dispatchEvent(new Event("saju:sessions-changed"));
      if (sid === id) newChat();
    } catch (e: any) {
      setErr(String(e?.message || e));
    }
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
    setRefineStage(null);
    setTurns((t) => [...t, { role: "assistant", content: "" }]);
    const url = `/api/chat/sessions/${sid}/messages/stream`;
    const tok = getToken();
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(tok ? { Authorization: `Bearer ${tok}` } : {}),
      },
      body: JSON.stringify({ message: msg, top_k: 4, depth, explain_level: explainLevel }),
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
        } else if (event === "stage" && data) {
          try {
            const j = JSON.parse(data);
            // draft_done / refining / refine_done
            setRefineStage(j.phase || null);
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
            setRefineStage(null);
            setTurns((cur) => {
              const copy = [...cur];
              copy[copy.length - 1] = {
                ...copy[copy.length - 1],
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
              setErr("⚠️ 일시적으로 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
            } else {
              setErr(d);
            }
          } catch {}
        }
      }
    }
    setRefineStage(null);
    if (isLoggedIn) {
      try {
        const me2 = await api.me();
        setCachedMe(me2);
      } catch {}
    }
    setStreaming(false);
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
        setErr("⚠️ 일시적으로 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
      } else {
        setErr(m);
      }
    } finally {
      setBusy(false);
      setStreaming(false);
      // 답변 완료 후 그 맥락 기반 후속 추천질문 로드(실패해도 무시 → 정적 폴백은 서버가 처리)
      const s = sid;
      if (s) api.getSuggestions(s).then((r) => setDynamicSuggests(r.suggestions || [])).catch(() => {});
    }
  };

  // 상담 시작 직후(sid 확정) '종합 풀이'를 자동 전송 — 칩 클릭 없이 기본으로 풍부한 분석을 먼저 보여준다.
  // (이후 질문은 기존 빌링대로 무료한도→건별 차감. 빈 세션에서 1회만.)
  useEffect(() => {
    if (autoRead && sid && turns.length === 0) {
      setAutoRead(false);
      void doSend(COMPREHENSIVE_READING);
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
        openCharge("포인트가 부족해요. 충전하면 전체보기로 바로 이어집니다.");
      } else {
        setErr(m);
      }
    } finally {
      setRevealing(false);
    }
  };

  const showBanners = !me?.ads_hidden;

  // 질문 전 과금 안내 (현재 선택한 depth 기준)
  function billingHint(): string {
    if (!me) return "비로그인 — 답변의 50%만 미리보기. 로그인하면 무료 질문/크레딧이 적용돼요.";
    if ((me.level ?? 9) <= 1) return "관리자 계정 · 무과금 (무제한)";
    if (me.is_member)
      return `연간회원 · 무과금 · 잔여 ${(me.membership_remaining ?? 0).toLocaleString()}/${(me.membership_quota ?? 0).toLocaleString()}회`;
    const cost = depth === "deep" ? (me.credit_cost_deep ?? 0) : (me.credit_cost_basic ?? 0);
    if ((me.free_remaining ?? 0) > 0)
      return `이번 질문은 무료 👍 · 남은 무료 ${me.free_remaining}/${me.free_quota_count ?? 3}회${depth === "deep" ? " (심화도 무료로 사용)" : ""}`;
    return `${depth === "deep" ? "심화" : "기본"} 질문 · 크레딧 ${cost.toLocaleString()}P 차감 예정 · 잔액 ${me.balance.toLocaleString()}P`;
  }

  // 답변 완료 후 적용된 과금 표시
  function billingApplied(t: Turn): string | null {
    switch (t.billing_mode) {
      case "free_quota":
      case "free_daily":
        return "✓ 무료 질문 사용됨";
      case "membership_full":
        return "✓ 연간회원 무과금";
      case "admin_full":
        return "✓ 관리자 무과금";
      case "paid_full":
        return `✓ 크레딧 ${(t.credits_charged ?? 0).toLocaleString()}P 차감됨`;
      case "anonymous_preview":
        return "비로그인 미리보기(50%)";
      default:
        return null;
    }
  }

  return (
    <div className="chat-layout">
      <main className="chat-main">
        {STUDIO_NAME && (
          <div className="studio-header">
            <span className="studio-name">{STUDIO_NAME}</span>
          </div>
        )}
        {showBanners && <BannerSlot slot="top" height={90} />}

        {!sid && (
          <>
            <header className="compat-hero saju-hero">
              <div className="compat-hero-badge">四柱</div>
              <h1>사주상담</h1>
              <p>
                중국·일본·한국의 명리 <b>고서(古書)</b>를 토대로, 한국 전통 관법에 맞춰
                풀어내는 정통 AI 사주 상담입니다.
              </p>
            </header>

            {/* 신뢰 스트립 — 실제 구현된 계산 로직을 그대로 노출(과장 없음) */}
            <div className="trust-strip" aria-label="사주 분석 방식">
              <div className="trust-item">
                <span className="ti-ico" aria-hidden="true">🕰️</span>
                <span className="ti-title">진태양시 보정</span>
                <span className="ti-desc">출생지 경도로 실제 태양시를 교정해 정확한 시주(時柱)를 세웁니다</span>
              </div>
              <div className="trust-item">
                <span className="ti-ico" aria-hidden="true">📐</span>
                <span className="ti-title">정통 명식 산출</span>
                <span className="ti-desc">천간·지지·지장간·십성·신살·십이운성·대운까지 빠짐없이 계산</span>
              </div>
              <div className="trust-item">
                <span className="ti-ico" aria-hidden="true">🧭</span>
                <span className="ti-title">조후·억부 용신</span>
                <span className="ti-desc">궁통보감(窮通寶鑑) 조후표 기반의 결정적 산식 — 그때그때 지어내지 않습니다</span>
              </div>
              <div className="trust-item">
                <span className="ti-ico" aria-hidden="true">📚</span>
                <span className="ti-title">고서 근거 인용</span>
                <span className="ti-desc">신뢰등급으로 검증된 명리 원전만 근거로 삼아 풀이합니다</span>
              </div>
            </div>

            <div className="gemini-greeting">
              <p className="hello">{me?.nickname ? `${me.nickname}님, 안녕하세요` : "안녕하세요"}</p>
              <p className="sub">생년월일시를 입력하면, 바로 사주를 풀어 드릴게요.</p>
            </div>
          </>
        )}

        {needBirth && (
          <div className="card saju-input-card">
            <div className="card-head-row">
              <h3 style={{ margin: 0 }}>사주 입력</h3>
              <label className="remember-check" title="체크하면 입력한 사주정보를 저장하고, 다시 로그인하거나 새 창으로 들어와도 그대로 불러옵니다.">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(e) => toggleRemember(e.target.checked)}
                />
                내 사주정보 기억하기
              </label>
            </div>
            <p className="card-sub">생년월일·시각·성별만 입력하면 됩니다. 태어난 시각을 모르면 비워 두어도 괜찮아요.</p>

            {/* 빠른 입력 — 숫자만 입력하면 자동 완성(가장 빠른 길) */}
            <div className="bf-quick">
              <div className="bf-quick-top">
                <span className="bf-quick-label">⚡ 빠른 입력</span>
                <span className="bf-quick-sub">생년월일시를 숫자로 — 자동 완성</span>
              </div>
              <div className="bf-quick-row">
                <input
                  ref={quickRef}
                  className="bf-quick-input"
                  type="text" inputMode="numeric" maxLength={14}
                  placeholder="예: 197503210430  →  1975-03-21 04:30"
                  value={quick}
                  onChange={(e) => applyQuick(e.target.value)}
                />
                {/* 적용은 React state(quick)가 아니라 실제 DOM 값을 읽는다 — 자동완성·붙여넣기·
                    IME 등 onChange가 안 걸린 채 값이 들어와도 항상 화면의 값을 반영(무반응 버그 차단). */}
                <button type="button" className="bf-quick-btn"
                        onClick={() => applyQuick(quickRef.current?.value ?? quick)}>적용</button>
              </div>
              <div className={`bf-quick-hint${quickInfo && quickInfo.startsWith("✓") ? " ok" : quickInfo ? " warn" : ""}`}>
                {quickInfo || "8자리(YYYYMMDD) 또는 12자리(YYYYMMDDHHMM)"}
              </div>
            </div>

            <div className="bf-or"><span>또는 직접 입력</span></div>

            {/* 직접 입력 — 전 메뉴 공통 프리미엄 그리드(생년월일·시각은 한 줄, 성별·달력은 토글) */}
            <div className="bf-grid">
              <div className="bf-field bf-field-wide">
                <label>📅 생년월일</label>
                <div className="bf-datebox">
                  <input
                    className="bf-input"
                    type="text" inputMode="numeric" maxLength={10}
                    placeholder="예: 1990-03-15 (직접 입력)"
                    value={dateText}
                    onChange={(e) => typeDate(e.target.value)}
                  />
                  <button type="button" className="bf-cal-btn" title="달력에서 선택"
                          onClick={() => { const el = dateRef.current; if (!el) return; (el as any).showPicker ? (el as any).showPicker() : el.focus(); }}>📅</button>
                  <input ref={dateRef} type="date" className="bf-date-native" tabIndex={-1} aria-hidden
                         value={birth.birth_date}
                         onChange={(e) => setBirth({ ...birth, birth_date: e.target.value })} />
                </div>
              </div>
              <div className="bf-field bf-field-wide">
                <label>🕐 태어난 시각 <span className="bf-opt">선택</span></label>
                <div className="bf-time">
                  <TimeSelect
                    value={birth.birth_time || ""}
                    disabled={unknownTime}
                    onChange={(v) => setBirth({ ...birth, birth_time: v || null })}
                  />
                  <button type="button" className={`bf-chip ${unknownTime ? "on" : ""}`}
                          onClick={() => setUnknownTime((u) => !u)}>시 모름</button>
                </div>
                <div className="bf-time-hint" style={{ fontSize: 12, color: "#8a8f98", marginTop: 4 }}>
                  {unknownTime ? "시주 없이 3기둥으로 분석해요." : "비워두면 자동으로 00:30로 진행돼요 · 태어난 시를 모르면 ‘시 모름’"}
                </div>
              </div>
              <div className="bf-field">
                <label>성별</label>
                <div className="bf-seg">
                  <button type="button" className={birth.gender === "male" ? "on" : ""}
                          onClick={() => setBirth({ ...birth, gender: "male" })}>♂ 남자</button>
                  <button type="button" className={birth.gender === "female" ? "on" : ""}
                          onClick={() => setBirth({ ...birth, gender: "female" })}>♀ 여자</button>
                </div>
              </div>
              <div className="bf-field">
                <label>양/음력</label>
                <div className="bf-seg">
                  <button type="button" className={birth.calendar === "solar" ? "on" : ""}
                          onClick={() => setBirth({ ...birth, calendar: "solar", is_leap_month: false })}>양력</button>
                  <button type="button" className={birth.calendar === "lunar" ? "on" : ""}
                          onClick={() => setBirth({ ...birth, calendar: "lunar" })}>음력</button>
                </div>
              </div>
            </div>

            <AdvancedBirthSettings value={birth} onChange={(patch) => setBirth((prev) => ({ ...prev, ...patch }))} />

            {!isLoggedIn && (
              <div style={{ marginTop: 8, fontSize: 12, color: "#aa6600" }}>
                비로그인은 답변의 50%만 미리보기로 제공됩니다. 전체 보기는{" "}
                <Link to="/login">로그인</Link> 후 1일 무료질문 또는 크레딧 차감.
              </div>
            )}
            {/* 메인 CTA — 입력을 마치면 자연히 시선이 닿는 폼 하단 중앙 큰 버튼 */}
            <div className="chat-start-actions">
              <button className="chat-cta" onClick={startSession} disabled={busy || !dateText}>
                {busy ? "준비 중…" : "🔮 상담 시작"}
              </button>
            </div>
            {!dateText && <div className="cta-hint">생년월일을 입력하면 상담을 시작할 수 있어요</div>}
            <p className="saju-assure">
              🔒 입력 정보는 사주 풀이에만 쓰여요 · <b>명식(천간·지지)</b>을 먼저 세운 뒤, 그 위에서 풀이가 진행됩니다
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
                return av ? <img className="chart-zodiac" src={av.src} alt={`${av.zodiac}띠`} width={46} height={46} loading="lazy" /> : null;
              })()}
              <h3 style={{ marginTop: 0 }}>사주 명식</h3>
            </div>
            <SajuChart chart={chart} />
            {/* 명식 요약 원문(오행분포·억부·조후용신·대운·계산기준 등 내부 데이터)은 관리자에게만 노출.
               일반 사용자는 위의 시각적 명식표만 본다. (백엔드도 비관리자에겐 saju_summary 미전송) */}
            {summary && me?.role === "admin" && (
              <details style={{ marginTop: 8 }}>
                <summary style={{ cursor: "pointer", fontSize: 12, color: "#888" }}>내부 명식 데이터 (관리자 전용)</summary>
                <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", fontSize: 12, color: "#555", marginTop: 6 }}>{summary}</pre>
              </details>
            )}
          </div>
        )}

        {sid && (
          <div className="card">
            <h3 style={{ marginTop: 0 }}>상담</h3>
            {showBanners && <BannerSlot slot="chat_top_1" height={60} />}
            {turns.map((t, i) => (
              <div key={i} className={`msg ${t.role}${t.flash ? " done-flash" : ""}`}>
                <div className="role">{t.role === "user" ? "나" : "상담친구"}</div>
                <div
                  className={t.refined ? "refine-fade" : undefined}
                  style={{ whiteSpace: "pre-wrap" }}
                >
                  {renderRich(t.content)}
                </div>
                {t.role === "assistant" && streaming && i === turns.length - 1 && (
                  <div className="thinking-indicator">
                    <span className="dot-pulse" aria-hidden="true"></span>
                    <span>
                      {refineStage === "verifying"
                        ? "🔍 명식(천간·지지)과 풀이가 정확히 일치하는지 확인하는 중이에요"
                        : refineStage === "refining"
                        ? "🔮 저보다 똑똑한, 사주에 통달한 AI와 사주를 한 번 더 풀이하고 있어요"
                        : refineStage === "draft_done"
                        ? "초안을 마치고, 더 깊이 한 번 더 풀이하는 중이에요"
                        : refineStage === "refine_done"
                        ? "풀이를 마무리하는 중이에요"
                        : !t.content
                        ? "🔮 천간·지지와 대운을 짚어 정통 관법으로 사주를 풀이하는 중이에요"
                        : "✍️ 풀이를 정성껏 작성하는 중이에요"}
                      <span className="thinking-dots" aria-hidden="true"></span>
                    </span>
                  </div>
                )}
                {t.role === "assistant" && t.refined && (
                  <span className="refined-badge" title="심화 검증·보강됨">
                    ✦ 심화 보강됨
                  </span>
                )}
                {t.role === "assistant" &&
                  !(streaming && i === turns.length - 1) &&
                  billingApplied(t) && (
                    <div className="billing-applied">{billingApplied(t)}</div>
                  )}
                {t.role === "assistant" && t.content && !(streaming && i === turns.length - 1) && (
                  <AnswerActions
                    text={stripMarkdown(t.content)}
                    messageId={t.message_id}
                    sessionId={sid || undefined}
                    initialFeedback={t.feedback}
                    isLast={i === turns.length - 1 && !streaming}
                    pdf={{
                      docTitle: `${memberName} 님의 사주`,
                      personLine: `${memberName} 님`,
                      item:
                        (turns[i - 1]?.role === "user" ? turns[i - 1].content : "").slice(0, 40) ||
                        "사주 종합 풀이",
                    }}
                  />
                )}
                {t.role === "assistant" && t.is_preview && !t.preview_revealed && t.message_id && (
                  <div className="reveal-cta">
                    <span className="reveal-cta-lock">🔒 여기까지는 <b>미리보기</b>예요 — 뒷부분 풀이가 더 있어요</span>
                    <button className="reveal-cta-btn" onClick={() => reveal(t.message_id!, i)} disabled={revealing}>
                      {revealing ? "여는 중…" : <>전체 보기 <b>{(t.reveal_cost ?? 500).toLocaleString()}P</b></>}
                    </button>
                  </div>
                )}
                {t.role === "assistant" &&
                  me?.role === "admin" &&  /* 풀이 근거(명식근거·자료출처)는 영업비밀 → 관리자만 */
                  ((t.evidence && t.evidence.length > 0) || (t.sources && t.sources.length > 0)) &&
                  !(streaming && i === turns.length - 1) && (
                    <details className="sources evidence-block" style={{ marginTop: 6 }}>
                      <summary><strong>이 풀이의 근거</strong></summary>
                      {t.evidence && t.evidence.length > 0 && (
                        <div style={{ marginTop: 4 }}>
                          <div className="evi-head">사주명식 근거</div>
                          <ul style={{ margin: "2px 0 0 16px", padding: 0 }}>
                            {t.evidence.map((e, j) => (
                              <li key={j}>{e}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {t.sources && t.sources.length > 0 && (
                        <div style={{ marginTop: 6 }}>
                          <div className="evi-head">자료 근거 ({t.sources.length})</div>
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
                  <div className="suggest-label">💡 이어서 물어보세요</div>
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
                        doc_title: `${memberName} 님 사주 종합 감정서`,
                        person_line: `${memberName} 님`,
                        item: "사주 종합 감정",
                        conversation,
                        topic: "사주 상담",
                        session_id: sid || undefined,   // 명식 패널(한지 위 본인 사주) 포함
                      };
                    }}
                  />
                  <span className="report-hint">여러 질문·답변을 하나의 감정서로 정리해 PDF로 만듭니다.</span>
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
                  placeholder="질문을 입력하세요 (Enter 전송, Shift+Enter 줄바꿈)"
                  disabled={busy}
                />
                <button
                  className="send-btn"
                  onClick={send}
                  disabled={busy || !input.trim()}
                  title="전송"
                  aria-label="전송"
                >
                  {streaming ? "⋯" : "➤"}
                </button>
              </div>
              <div className="composer-stream">
                {streaming ? (
                  <span className="alive-status" title="응답 생성 중">
                    <span className="dot-pulse" aria-hidden="true"></span> 상담친구가 답변을 작성하고 있어요…
                  </span>
                ) : (
                  <span className="alive-status idle">● 대기 중 — 질문을 입력하세요</span>
                )}
                <label style={{ marginLeft: "auto" }}>
                  <input type="checkbox" checked={useSSE} onChange={(e) => setUseSSE(e.target.checked)} /> 스트리밍
                </label>
                <label style={{ marginLeft: 12 }} title="100단어 이내로 핵심만 간단히 답변받습니다.">
                  <input type="checkbox" checked={brief} onChange={(e) => toggleBrief(e.target.checked)} /> 핵심만
                </label>
              </div>
            </div>
            <div className="depth-bar">
              <span className="depth-label">질문 방식</span>
              <label className={`depth-opt${depth === "basic" ? " on" : ""}`}>
                <input
                  type="radio"
                  name="depth"
                  checked={depth === "basic"}
                  onChange={() => setDepth("basic")}
                />
                기본 <span className="depth-desc">내부 AI 단독</span>
                <span className="depth-cost">{(me?.credit_cost_basic ?? 1000).toLocaleString()}P</span>
              </label>
              <label className={`depth-opt${depth === "deep" ? " on" : ""}`}>
                <input
                  type="radio"
                  name="depth"
                  checked={depth === "deep"}
                  onChange={() => setDepth("deep")}
                />
                심화 <span className="depth-desc">내부+외부 AI 보강·근거강화</span>
                <span className="depth-cost">{(me?.credit_cost_deep ?? 3000).toLocaleString()}P</span>
              </label>
              <label
                className={`easy-toggle${easy ? " on" : ""}`}
                title="체크하면 전문용어 대신 이야기하듯 쉬운 말로 풀어 드립니다."
              >
                <input type="checkbox" checked={easy} onChange={(e) => toggleEasy(e.target.checked)} />
                <span className="easy-ico" aria-hidden="true">🌿</span>
                쉽게 풀어 주세요
              </label>
            </div>
            {/* 질문창 아래 과금 안내 (현재 depth 기준 무료/차감/잔여) */}
            <div className="billing-hint">
              <span className="bh-main">💳 {billingHint()}</span>
              {me && (me.level ?? 9) > 1 && !me.is_member && (
                <span className="bh-sub">
                  · 심화는 외부 AI 보강(근거 강화){
                    typeof me.credit_cost_deep === "number" && typeof me.credit_cost_basic === "number"
                      ? `, 크레딧 ${me.credit_cost_deep.toLocaleString()}P (기본 ${me.credit_cost_basic.toLocaleString()}P)`
                      : ""
                  }
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
            <h3 style={{ marginTop: 0 }}>답변을 어떻게 풀어 드릴까요?</h3>
            <p style={{ color: "var(--ink-600, #555)", fontSize: 14, marginBottom: 16 }}>
              처음이시네요! 풀이 방식을 한 번만 골라 주세요. <br />
              이후에는 질문창의 <b>🌿 쉽게 풀어 주세요</b> 버튼으로 언제든 바꿀 수 있어요.
            </p>
            <div className="explain-choices">
              <button className="explain-choice easy" onClick={() => chooseExplain("easy")}>
                <span className="ec-ico">🌿</span>
                <span className="ec-title">쉽게 풀어 주세요</span>
                <span className="ec-desc">전문용어 대신 이야기하듯 쉽게</span>
              </button>
              <button className="explain-choice pro" onClick={() => chooseExplain("normal")}>
                <span className="ec-ico">📘</span>
                <span className="ec-title">전문용어로 풀어 주세요</span>
                <span className="ec-desc">명리 용어 그대로 깊이 있게</span>
              </button>
            </div>
            <button className="ghost" style={{ marginTop: 12 }} onClick={laterExplainPopup}>
              나중에 결정할게요 — 일단 표준 풀이로 받기
            </button>
          </div>
        </div>
      )}

      {showPaywall && (
        <div className="pwa-overlay" onClick={() => setShowPaywall(false)}>
          <div className="pwa-modal" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginTop: 0 }}>무료 질문을 모두 사용했어요</h3>
            <p style={{ color: "var(--ink-soft, #555)", fontSize: 14 }}>
              {isLoggedIn
                ? "충전 또는 멤버십으로 계속 이용하실 수 있어요. 심화(외부 AI 보강) 답변은 더 깊이 있는 풀이를 제공합니다."
                : "로그인하면 무료 질문과 전체 답변을 이용할 수 있어요."}
            </p>
            <div className="pwa-actions">
              {isLoggedIn ? (
                <button onClick={() => openCharge()}>충전하기</button>
              ) : (
                <button onClick={() => navigate("/login")}>로그인</button>
              )}
              <button className="ghost" onClick={() => setShowPaywall(false)}>
                닫기
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
                <h3>상담함이 가득 찼어요</h3>
                <p className="sl-sub">지금까지 나눈 소중한 상담을 모두 보관하고 있어요</p>
              </div>
            </div>
            <p className="sl-desc">
              상담은 최대 <b>{maxSessions}개</b>까지 보관돼요. 다시 보지 않을 상담을
              정리하면 새로운 상담을 바로 이어갈 수 있어요. 정리한 상담 기록은 복구할 수 없으니
              한 번 더 살펴봐 주세요.
            </p>
            <div className="sl-gauge" role="img" aria-label={`상담 ${sessions.length}개 중 ${maxSessions}개 사용`}>
              <div className="sl-gauge-track">
                <span className={`sl-gauge-fill${full ? " full" : ""}`} style={{ width: `${pct}%` }} />
              </div>
              <span className="sl-gauge-num">{sessions.length} / {maxSessions}</span>
            </div>
            <div className="sl-list">
              {sessions.map((s) => (
                <div key={s.session_id} className={`sl-row${sid === s.session_id ? " current" : ""}`}>
                  <span className="sl-body">
                    <span className="sl-title">
                      {s.title || "(제목 없는 상담)"}
                      {sid === s.session_id && <span className="sl-badge">보는 중</span>}
                    </span>
                    <span className="sl-meta">
                      {shortDate(s.created_at)} · 생년월일 {s.birth_date} · 메시지 {s.message_count}개
                    </span>
                  </span>
                  <button
                    className="sl-del"
                    onClick={() => removeSession(s.session_id, s.title || s.birth_date)}
                  >
                    삭제
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
                {full ? "정리 후 시작할 수 있어요" : "새 상담 시작"}
              </button>
              <button className="ghost" onClick={() => setShowSessionLimit(false)}>
                나중에 할게요
              </button>
            </div>
          </div>
        </div>
        );
      })()}
    </div>
  );
}
