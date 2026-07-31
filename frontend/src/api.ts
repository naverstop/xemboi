import { useSyncExternalStore } from "react";
import i18n from "./i18n";

const BASE = "/api";
const TOKEN_KEY = "saju_token";
const ME_KEY = "saju_me";
const LANG_KEY = "saju_lang";  // 로케일(ko|vi). LanguageSwitch/setLocale 가 기록.

/** 인증 상태(토큰/내 정보)가 바뀔 때 발생하는 전역 이벤트. */
const AUTH_EVENT = "saju:auth-changed";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string | null): void {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
  window.dispatchEvent(new Event(AUTH_EVENT));
}
export function getCachedMe(): MeResp | null {
  const raw = localStorage.getItem(ME_KEY);
  return raw ? (JSON.parse(raw) as MeResp) : null;
}
export function setCachedMe(me: MeResp | null): void {
  if (me) localStorage.setItem(ME_KEY, JSON.stringify(me));
  else { localStorage.removeItem(ME_KEY); invalidateGetCache(); }  // 로그아웃: 다른 사용자에 캐시 누수 방지
  window.dispatchEvent(new Event(AUTH_EVENT));
}

// ---- 반응형 인증 상태 훅 (useSyncExternalStore) ----
// getCachedMe()는 비반응형이라 같은 화면에서 로그인/로그아웃/잔액변경 시
// 컴포넌트가 갱신되지 않는다. useMe()는 AUTH_EVENT와 multi-tab storage
// 이벤트를 구독해 인증 상태 변화를 즉시 반영한다.
let _meRaw: string | null = null;
let _meParsed: MeResp | null = null;
function meSnapshot(): MeResp | null {
  const raw = localStorage.getItem(ME_KEY);
  if (raw !== _meRaw) {
    _meRaw = raw;
    _meParsed = raw ? (JSON.parse(raw) as MeResp) : null;
  }
  return _meParsed; // 동일 raw이면 동일 참조 반환(useSyncExternalStore 요구사항)
}
function meSubscribe(cb: () => void): () => void {
  window.addEventListener(AUTH_EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(AUTH_EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}
export function useMe(): MeResp | null {
  return useSyncExternalStore(meSubscribe, meSnapshot, meSnapshot);
}

function authHeaders(extra?: HeadersInit): HeadersInit {
  const h: Record<string, string> = { ...(extra as any) };
  const t = getToken();
  if (t) h["Authorization"] = `Bearer ${t}`;
  // 로케일 헤더 — 백엔드 deps.get_locale 가 응답언어/역법 결정. 빈값이면 서버 default_locale.
  const loc = localStorage.getItem(LANG_KEY);
  if (loc) h["X-Locale"] = loc;
  return h;
}

// 서버가 보내는 영어 detail/코드 → i18n 에러 카탈로그 키(err.*) 매핑(안전망, 로케일 반영).
const ERR_KEYS: Record<string, string> = {
  "invalid credentials": "err.invalid_credentials",
  "login required": "err.login_required",
  "admin only": "err.admin_only",
  "email already registered": "err.email_registered",
  "invalid refresh token": "err.invalid_refresh",
  "user not found": "err.user_not_found",
  "share_quota_exceeded": "err.share_quota",
  "not your session": "err.not_your_session",
  "login required to share": "err.login_to_share",
};

// HTTP 상태코드별 기본 친화 메시지(i18n 로케일 반영).
function statusFallback(status: number): string {
  if (status === 401) return i18n.t("err.s401");
  if (status === 403) return i18n.t("err.s403");
  if (status === 404) return i18n.t("err.s404");
  if (status === 409) return i18n.t("err.s409");
  if (status === 429) return i18n.t("err.s429");
  if (status >= 500) return i18n.t("err.s500");
  return i18n.t("err.s_other", { status });
}

// 백엔드가 이미 로케일 언어로 보낸 detail(한국어 한글 / 베트남어 라틴+성조부호)은 그대로 노출.
// 내부 영어 코드/식별자는 전부 ASCII → 비-ASCII 문자가 있으면 사람이 읽는 로케일 메시지로 판단(ko·vi 공통).
const LOCALIZED_DETAIL = /[^\x00-\x7F]/;

// jfetch가 던지는 에러. 친화 메시지(message) 외에 HTTP status와 서버 원본 detail
// 코드(code)를 보존한다. 친화 메시지로 치환하는 과정에서 status/code를 통째로 잃어
// 호출부가 한도 초과(409, session_limit_reached) 같은 케이스를 식별하지 못하던 문제
// (잘못된 "이미 존재하는 정보예요" 표시) 때문에 추가.
export class ApiError extends Error {
  status: number;
  code: string | null;
  constructor(message: string, status: number, code: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

// 응답 본문은 한 번만 읽을 수 있으므로 친화 메시지와 원본 코드를 함께 산출한다.
async function parseError(r: Response): Promise<{ message: string; code: string | null }> {
  let detail: unknown = null;
  try {
    const j = await r.json();
    detail = (j as any)?.detail ?? (j as any)?.message ?? null;
  } catch {
    /* 본문이 JSON이 아니면 상태코드 기반 메시지로 */
  }
  // FastAPI 검증 오류: detail이 배열 형태
  if (Array.isArray(detail) && detail.length) {
    const msgs = detail.map((d: any) => d?.msg).filter(Boolean);
    return {
      message: msgs.length ? i18n.t("err.validation", { msgs: msgs.join(", ") }) : statusFallback(r.status),
      code: null,
    };
  }
  if (typeof detail === "string" && detail.trim()) {
    const raw = detail.trim();
    const key = raw.toLowerCase();
    if (ERR_KEYS[key]) return { message: i18n.t(ERR_KEYS[key]), code: raw }; // 알려진 영어 코드 → 로케일 메시지
    if (LOCALIZED_DETAIL.test(detail)) return { message: detail, code: raw }; // 이미 로케일 언어(ko/vi)면 그대로
    return { message: statusFallback(r.status), code: raw }; // 알 수 없는 영어/코드는 숨기되 코드는 보존
  }
  return { message: statusFallback(r.status), code: null };
}

const REFRESH_KEY = "saju_refresh";

/** refresh 토큰 저장(없으면 제거). OAuth 로그인 등에서 무음 갱신을 쓰려면 함께 저장해야 한다. */
export function setRefreshToken(t: string | null): void {
  if (t) localStorage.setItem(REFRESH_KEY, t);
  else localStorage.removeItem(REFRESH_KEY);
}

// 로그인/가입/refresh/oauth 는 401 자동처리 대상에서 제외(자격증명 오류 등 정상 흐름).
function isAuthEndpoint(url: string): boolean {
  return /^\/auth\/(login|register|refresh|oauth)/.test(url);
}

// 동시 401 시 refresh 가 중복 회전(토큰 무효화)되지 않도록 단일 in-flight 로 공유.
let _refreshing: Promise<boolean> | null = null;
async function _doRefresh(rt: string): Promise<boolean> {
  try {
    const r = await fetch(BASE + "/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: rt }),
    });
    if (!r.ok) return false;
    const j: any = await r.json();
    if (j?.access_token) setToken(j.access_token);
    if (j?.refresh_token) localStorage.setItem(REFRESH_KEY, j.refresh_token);
    return !!j?.access_token;
  } catch {
    return false;
  }
}
function tryRefreshToken(): Promise<boolean> {
  if (_refreshing) return _refreshing;
  const rt = localStorage.getItem(REFRESH_KEY);
  if (!rt) return Promise.resolve(false);
  _refreshing = _doRefresh(rt).finally(() => { _refreshing = null; });
  return _refreshing;
}

// 세션 만료 처리(1회) — 토큰/캐시 정리 후 로그인 화면으로 안내(만료 사유 쿼리 첨부).
// 캐시된 me 때문에 UI가 '로그인 상태'로 남아 사용자가 인지 못하던 문제를 차단한다.
let _sessionExpiredHandled = false;
/** 세션 만료/무효(401·토큰소실) 시 1회 — 토큰·캐시 정리 후 로그인 화면으로 보낸다.
 *  REST(jfetch) 외에 SSE 스트림(생 fetch) 401·앱로드 토큰소실에서도 호출해 '조용한 먹통'을 막는다. */
export function notifySessionExpired(): void {
  if (_sessionExpiredHandled) return;
  _sessionExpiredHandled = true;
  setToken(null);
  setCachedMe(null);
  try { localStorage.removeItem(REFRESH_KEY); } catch { /* noop */ }
  if (!location.pathname.startsWith("/login")) {
    location.href = "/login?expired=1";
  }
}

async function jfetch<T>(url: string, init?: RequestInit, _retried = false): Promise<T> {
  const headers = authHeaders(init?.headers);
  const r = await fetch(BASE + url, { ...init, headers });
  if (!r.ok) {
    // 세션 만료(401): 토큰이 있던 경우에 한해 refresh 1회 시도 → 성공하면 재요청,
    // 실패하면 로그아웃 안내 후 로그인 화면으로 이동.
    if (r.status === 401 && !_retried && !isAuthEndpoint(url) && getToken()) {
      if (await tryRefreshToken()) return jfetch<T>(url, init, true);
      notifySessionExpired();
    }
    const { message, code } = await parseError(r);
    throw new ApiError(message, r.status, code);
  }
  if (r.status === 204) return undefined as unknown as T;
  return (await r.json()) as T;
}

export type MeResp = {
  id: number;
  email: string;
  nickname?: string | null;
  role: "user" | "admin";
  balance: number;
  must_change_password: boolean;
  daily_free_available: boolean;
  ads_hidden: boolean;
  level?: number;
  answer_dialect?: string;
  free_used_count?: number;
  free_quota_count?: number;
  free_remaining?: number;
  credit_cost_basic?: number;
  credit_cost_deep?: number;
  preview_reveal_cost?: number;
  video_gen_cost?: number;                        // 사주 영상 생성 차감 P(관리자 설정값)
  premium_entry_costs?: Record<string, number>;  // 프리미엄 5개 메뉴 입장료(할인반영)
  premium_entry_discount_pct?: number;           // 공통 행사 할인%
  premium_entry_free?: boolean;                  // 이 사용자 입장 무료(관리자/멤버십)
  is_member?: boolean;
  membership_remaining?: number;
  membership_quota?: number;
  saju_profile?: Partial<Birth> | null;   // 저장된 본인 사주(자동 채움)
  disclaimer_agreed?: boolean;             // 면책고지 동의(최초 1회) 완료 여부
  terms_agreed?: boolean;                  // 약관 3종 동의 완료 여부(SNS 가입자 게이트용)
};

export type AnswerTemplate = {
  id: number;
  name: string;
  body: string;
  version: number;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type AppSettings = {
  free_quota_count: number;
  free_quota_reset: string;
  credit_cost_basic: number;
  credit_cost_deep: number;
  preview_reveal_cost: number;
  preview_max_chars: number;
  feedback_reward_pct: number;
  feedback_reward_daily_cap: number;
  external_llm_enabled: boolean;
  // 프리미엄 5개 메뉴 입장료(메뉴별) + 공통 행사 할인%
  entry_cost_compat: number;
  entry_cost_taekil: number;
  entry_cost_jakmyeong: number;
  entry_cost_gaemyeong: number;
  entry_cost_aho: number;
  entry_cost_tarot: number;
  premium_entry_discount_pct: number;
};

// ---- 1:1 인적 상담(입점업체) ----
export type ConsultantPresence = "offline" | "online" | "busy";
export type ConsultantSpecialty = "saju" | "tarot" | "both";

export type ConsultantPublic = {
  id: number;
  business_name: string;
  specialty: ConsultantSpecialty;
  signboard_image_url?: string | null;
  intro?: string | null;
  price_p: number;
  duration_min: number;
  presence: ConsultantPresence;
  session_count: number;          // 누적 상담건수(완료)
  rating_avg?: number | null;     // 평균 만족도(1~5, 없으면 null)
  rating_count: number;           // 평점 참여 수
};

export type ConsultantStats = {
  sessions: number;
  revenue_p: number;
  payout_pending_p: number;
  payout_settled_p: number;
};

export type ConsultantAdmin = {
  id: number;
  login_email: string;
  user_id?: number | null;
  linked: boolean;
  business_name: string;
  specialty: ConsultantSpecialty;
  signboard_image_url?: string | null;
  intro?: string | null;
  rate_p?: number | null;
  duration_min_raw?: number | null;
  commission_pct_raw?: number | null;
  eff_price_p: number;
  eff_duration_min: number;
  eff_commission_pct: number;
  is_active: boolean;
  presence: ConsultantPresence;
  sort_order: number;
  created_at?: string | null;
  stats: ConsultantStats;
  session_count: number;
  rating_avg?: number | null;
  rating_count: number;
};

export type ConsultationConfig = {
  retention_days: number;
  no_show_timeout_sec: number;
  extend_warn_sec: number;
  default_price_p: number;
  default_duration_min: number;
};

export type ConsultationSettings = {
  consultation_default_price_p: number;
  consultation_default_duration_min: number;
  consultation_commission_pct: number;
  consultation_tax_pct: number;
  consultation_no_show_timeout_sec: number;
  consultation_extend_warn_sec: number;
  consultation_retention_days: number;
};

export type ConsultationSettlementRow = {
  id: number;
  session_id: string;
  consultant_id: number;
  consultant_name?: string | null;
  revenue_p: number;       // 매출(원)
  commission_pct: number;
  commission_p: number;    // 플랫폼 수수료(원)
  taxable_p: number;       // 과세대상(원)
  tax_pct: number;
  tax_p: number;           // 원천징수(원)
  payout_p: number;        // 실지급(원)
  status: "pending" | "settled";
  settled_at?: string | null;
  created_at?: string | null;
};

export type SettlementTotals = {
  revenue_p: number;
  payout_pending_p: number;
  payout_settled_p: number;
};

export type ConsultantCreateBody = {
  login_email: string;
  business_name: string;
  specialty: ConsultantSpecialty;
  intro?: string | null;
  rate_p?: number | null;
  duration_min?: number | null;
  commission_pct?: number | null;
  is_active?: boolean;
  sort_order?: number;
};

export type ConsultationStatus =
  | "requested" | "accepted" | "active" | "completed" | "cancelled" | "no_show" | "expired";

export type ConsultationSession = {
  id: string;
  status: ConsultationStatus;
  specialty: ConsultantSpecialty;
  consultant_id: number;
  consultant_name?: string | null;
  user_id?: number | null;
  price_p: number;
  duration_min: number;
  extended_min: number;
  total_min: number;
  remaining_sec?: number | null;
  started_at?: string | null;
  ended_at?: string | null;
  consent_at?: string | null;
  pdf_token?: string | null;
};

export type ConsultationChatMessage = {
  id: number;
  sender: "user" | "consultant" | "system";
  content: string;
  created_at: string;
};

/** 상담 WebSocket URL (세션 채팅 / 상담사 콘솔). 같은 오리진, 토큰은 쿼리로 전달(브라우저 WS 헤더 불가). */
export function consultationSessionWsUrl(sessionId: string): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/api/consultation/ws?session_id=${encodeURIComponent(sessionId)}&token=${encodeURIComponent(getToken() || "")}`;
}
export function consultantConsoleWsUrl(): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/api/consultation/consultant/ws?token=${encodeURIComponent(getToken() || "")}`;
}

export const DIALECTS: { value: string; label: string }[] = [
  { value: "standard", label: "표준어" },
  { value: "gyeongsang", label: "경상도" },
  { value: "jeolla", label: "전라도" },
  { value: "gangwon", label: "강원도" },
  { value: "jeju", label: "제주도" },
];

export type SajuProfileInput = {
  label: string;
  birth_date: string;
  birth_time?: string | null;
  calendar?: "solar" | "lunar";
  is_leap_month?: boolean;
  gender?: "male" | "female";
  apply_true_solar_time?: boolean;
  birth_longitude?: number | null;
  apply_equation_of_time?: boolean;
  night_zi_mode?: "yaja" | "jeongja";
  is_default?: boolean;
};

export type SajuProfile = {
  id: number;
  label: string;
  birth_date: string;
  birth_time: string | null;
  calendar: "solar" | "lunar";
  is_leap_month: boolean;
  gender: "male" | "female";
  apply_true_solar_time: boolean;
  birth_longitude?: number | null;
  apply_equation_of_time?: boolean;
  night_zi_mode?: "yaja" | "jeongja";
  is_default: boolean;
  created_at: string;
};

export type TokenResp = {
  access_token: string;
  refresh_token?: string | null;
  token_type: string;
  must_change_password: boolean;
  role: "user" | "admin";
};

export type AdminUser = {
  id: number;
  email: string;
  nickname?: string | null;
  role: "user" | "admin";
  balance: number;
  paid_krw: number;        // 결제금액(원, 승인)
  refunded_krw: number;    // 환불금액(원)
  granted_free: number;    // 기본제공 포인트(무료 지급 합)
  spent: number;           // 사용금액(차감 포인트 합)
  usage_count: number;     // 유료 사용 횟수
  free_used: number;       // 무료 사용 누적
  is_premium: boolean;
  ads_hidden: boolean;
  must_change_password: boolean;
  daily_free_used_at?: string | null;
  created_at: string;
  last_login_at?: string | null;
};

export type AdminPayment = {
  id: number;
  order_id: string;
  amount: number;          // 원
  credit_granted: number;
  status: "pending" | "approved" | "failed" | "cancelled" | "refunded";
  toss_payment_key?: string | null;
  refundable: boolean;     // status==approved
  refunded_recovered?: number | null;
  refunded_krw?: number | null;   // 실제 환불액(부분환불 반영)
  refund_partial?: boolean;
  created_at?: string | null;
  approved_at?: string | null;
};

export type AdminRefundResult = {
  status: string;
  order_id: string;
  recovered_credits: number;
  refunded_krw: number;    // 실제 환불 현금(미사용 결제분만)
  partial: boolean;        // 부분환불 여부
  mock: boolean;
};

export type AdminTx = {
  id: number;
  delta: number;
  reason: string;
  ref_id?: string | null;
  balance_after: number;
  created_at: string;
};

export type AdminStats = {
  total_users: number;
  today_signups: number;
  yesterday_signups: number;
  today_questions: number;
  today_credits_spent: number;
  total_revenue_krw: number;
  total_outstanding_credits: number;
};

export type Banner = {
  id: number;
  slot: string;
  image_url: string;
  link_url?: string | null;
  title?: string | null;
  weight: number;
  active: boolean;
  created_at: string;
};

export const BANNER_SLOTS = [
  "top",
  "chat_top_1",
  "chat_top_2",
  "side_1",
  "side_2",
  "answer_bottom",
] as const;

export type Birth = {
  birth_date: string;
  birth_time?: string | null;
  calendar?: "solar" | "lunar";
  gender?: "male" | "female" | "unknown";
  is_leap_month?: boolean;
  apply_true_solar_time?: boolean;
  birth_longitude?: number | null;
  apply_equation_of_time?: boolean;
  night_zi_mode?: "yaja" | "jeongja";
};

export type CreateSessionResp = {
  session_id: string;
  saju_summary?: string;
  chart?: any;
  has_saju: boolean;
};

export type Source = { source: string; category?: string; score: number; chunk_id?: number; text_preview?: string };
export type ChatTurnResp = {
  answer: string;
  sources: Source[];
  total_messages: number;
};

export type UploadDTO = {
  id: number;
  title: string;
  category: string;
  file_kind: string;
  original_name: string;
  size_bytes: number;
  status: string;
  submitter?: string | null;
  note?: string | null;
  submitted_at: string;
  reviewed_at?: string | null;
  reviewer?: string | null;
  review_comment?: string | null;
  indexed_at?: string | null;
  indexed_source?: string | null;
  chunks_count?: number | null;
};

export type UploadStats = {
  total: number;
  by_status: Record<string, number>;
  by_kind: Record<string, number>;
  total_size_bytes: number;
  sum_chunks: number;
  indexed_count: number;
  corpus_chunks: number | null;       // Qdrant 코퍼스 청크(실제 색인량)
  trend: { date: string; indexed: number; chunks?: number }[];   // 최근 14일 일별 색인 건수 + 청크 수
  monthly_chunks: { month: string; chunks: number; delta: number | null }[];  // 월별 코퍼스 청크 + 증가량
};

export type LearningProgress = {
  stage: string;            // start|ocr|index|archive|uploads|mp4|snapshot|done|error
  stage_label: string;      // 한글 단계명
  message: string;
  current: number | null;   // 현재 단계 내 진척(파일 N)
  total: number | null;     // 현재 단계 내 전체(파일 M)
  current_file: string | null;   // 처리 중 파일명
  stage_index: number | null;    // 단계 순번(예: 2)
  stage_count: number | null;    // 총 단계 수(6)
  overall_pct: number | null;    // 전 단계 가중 전체 진행율(0~100)
  chunks: number | null;    // 누적 색인 청크
  started_at: string | null;
  updated_at: string | null;
  done: boolean;
  error: string | null;
};

export type LearningStatus = {
  running: boolean;
  progress: LearningProgress | null;
};

export type EvalRun = {
  ts: string;
  tag?: string;
  dataset?: string;
  n_questions: number;
  top_k: number;
  collection: string;
  keyword_hit_rate_mean: number;
  top1_score_mean: number;
  topk_mean_score_mean: number;
  pass_at_60: number;
  latency_ms_mean: number;
};

export type EvalStatus = {
  running: boolean;
  started_at: string | null;
  finished_at: string | null;
  last_tag: string | null;
  last_error: string | null;
  last_summary: Record<string, unknown> | null;
};

// ---- 궁합(宮合) ----
export type CompatFactorItem = { type: string; detail: string; sign: number };
export type CompatFactor = { key: string; label: string; score: number; items: CompatFactorItem[] };
export type CompatPenalty = { type: string; detail: string };
export type CompatPerspective = {
  key: string;
  label: string;
  weights: Record<string, number>;
  contributions: Record<string, number>;
  total: number;
  grade: string;                 // 로케일 표시 라벨(백엔드 산출)
  grade_key?: string;            // 로케일 무관 stable key: soulmate|good|fair|effort|caution
  interpretation: string;
};
export type CompatResult = {
  factors: Record<string, CompatFactor>;
  penalties: CompatPenalty[];
  perspectives: Record<string, CompatPerspective>;
  dohwa_readings: string[];
};
export type CompatResponse = {
  compat_id: string;
  person_a: { label: string; chart: any };
  person_b: { label: string; chart: any };
  result: CompatResult;
  explain: string;
  is_preview: boolean;
  billing_mode: string;
  credits_charged: number;
  balance_after: number | null;
};
export type CompatAverage = {
  count: number;
  min_samples: number;
  average: { factors: Record<string, number | null>; totals: Record<string, number | null> } | null;
};
export type CompatPersonReq = { label?: string; profile_id?: number; birth?: Birth };

// 펜타곤 축 순서 + i18n 키 (프론트 공용). 라벨은 compat 카탈로그(axis_*)에서 로케일별로 렌더.
export const COMPAT_AXES: { key: string; tkey: string }[] = [
  { key: "day_branch", tkey: "compat.axis_ilji" },
  { key: "day_stem", tkey: "compat.axis_ilgan" },
  { key: "wuxing", tkey: "compat.axis_ohaeng" },
  { key: "ten_god", tkey: "compat.axis_sipseong" },
  { key: "sinsal", tkey: "compat.axis_sinsal" },
];

// ---- 타로 ----
export type TarotSection = "love" | "money" | "career" | "study" | "choice" | "life";
export type TarotSpread = "horseshoe7" | "celtic11";
export type TarotCreateResp = {
  tarot_id: string;
  spread_type: TarotSpread;
  need: number;
  positions: string[];
  section: string;
  question: string;
};
export type TarotCard = {
  position_index: number;
  position_name: string;
  code: string;
  name_kr: string;
  name_en: string;
  orientation: "upright" | "reversed";
  image_url: string;
  keywords: string[];
};
export type TarotMessage = { id?: number; role: string; content: string };
export type TarotSnapshot = {
  tarot_id: string;
  section: string;
  question: string;
  spread_type: TarotSpread;
  need?: number;
  positions?: string[];
  cards?: TarotCard[] | null;
  messages?: TarotMessage[];
};

export type TarotSessionItem = {
  tarot_id: string;
  title: string;
  section: string;
  spread_type: TarotSpread;
  created_at: string;
  message_count: number;
  has_reading: boolean;
};
export type TarotSessionList = { items: TarotSessionItem[]; total: number; max_sessions: number };

// ---- 명리 도구(작명/개명/아호/택일) ----
export type NamingKind = "jakmyeong" | "gaemyeong" | "aho";
export type TaekilPurpose =
  | "wedding" | "birth" | "moving" | "opening" | "contract"
  | "ceremony" | "surgery" | "travel" | "general";

export type ToolResponse = {
  tool_id: string;
  tool: "naming" | "taekil";
  kind: string;
  result: any;
  is_preview: boolean;
  billing_mode: string;
  credits_charged: number;
  balance_after: number | null;
};

export const PURPOSE_LABELS: Record<TaekilPurpose, string> = {
  wedding: "혼인", birth: "출산", moving: "이사", opening: "개업", contract: "계약",
  ceremony: "고사·제사", surgery: "수술", travel: "여행", general: "일반",
};

// ---- 고객센터(CONTACT US) ----
export type SupportCategory = "refund" | "payment" | "account" | "etc";
export type SupportStatus = "received" | "in_progress" | "resolved" | "rejected";
export type SupportTicket = {
  id: number;
  user_id: number | null;
  category: SupportCategory;
  category_label: string;
  contact_email: string;
  contact_name: string | null;
  order_id: string | null;
  amount: number | null;
  title: string;
  message: string;
  status: SupportStatus;
  status_label: string;
  admin_note: string | null;
  created_at: string | null;
  updated_at: string | null;
};
export type SupportRecipient = { id: number; email: string; active: boolean };

// ---- 운영/법무 설정 ----
export type LegalBusiness = {
  name: string; ceo: string; reg_no: string; mailorder_no: string;
  address: string; tel: string; hours: string; email: string; privacy_officer: string; hosting: string;
};
export type LegalInfo = {
  terms: string; privacy: string; refund: string; min_age_years: number;
  service_name: string; business: LegalBusiness;
  bodies: { terms: string; privacy: string; refund: string; disclaimer: string };
};
export type SiteSettings = {
  service_name: string; biz_name: string; biz_ceo: string; biz_reg_no: string;
  biz_mailorder_no: string; biz_address: string; biz_tel: string; biz_hours: string; biz_email: string;
  biz_privacy_officer: string; biz_hosting: string;
  terms_version: string; privacy_version: string; refund_version: string; min_age_years: string;
  legal_body_terms: string; legal_body_privacy: string; legal_body_refund: string; legal_body_disclaimer: string;
  smtp_enabled: string; smtp_host: string; smtp_port: string; smtp_user: string;
  smtp_password: string; smtp_from: string; smtp_use_tls: string;
};

// ---- 짧은 TTL GET 캐시 ----
// 메뉴 왕복 시 동일 목록/통계 GET 재요청을 억제(기본 30초). 진행 중인 동일 요청은 공유되어
// React StrictMode(개발) 2회 호출도 1회로 합쳐진다. 데이터 변경/로그아웃 시 invalidateGetCache 로 무효화.
type _GetCacheEntry = { at: number; promise: Promise<unknown> };
const _getCache = new Map<string, _GetCacheEntry>();
const GET_CACHE_TTL = 30_000;
function cachedGet<T>(key: string, fetcher: () => Promise<T>, ttlMs = GET_CACHE_TTL): Promise<T> {
  const hit = _getCache.get(key);
  if (hit && Date.now() - hit.at < ttlMs) return hit.promise as Promise<T>;
  const promise = fetcher().catch((e) => {
    _getCache.delete(key); // 실패는 캐시하지 않음 → 다음 호출에서 즉시 재시도
    throw e;
  });
  _getCache.set(key, { at: Date.now(), promise });
  return promise as Promise<T>;
}
export function invalidateGetCache(prefix?: string): void {
  if (!prefix) { _getCache.clear(); return; }
  for (const k of [..._getCache.keys()]) if (k.startsWith(prefix)) _getCache.delete(k);
}

export type VideoJobResp = {
  job_token: string;
  status: "queued" | "running" | "done" | "failed" | "expired";
  stage?: string | null;
  progress_pct: number;
  detail?: string | null;
  aspect: string;
  title?: string | null;
  download_url?: string;
  expires_at?: string | null;
};

export type TarotAdminCard = {
  id: number;
  code: string;
  name_kr: string;
  name_en: string;
  arcana: string;
  suit: string | null;
  image_url: string;
  seed_keywords_up: string[];
  seed_keywords_rev: string[];
  seed_interp_up: string;
  seed_interp_rev: string;
  keywords_up: string[];
  keywords_rev: string[];
  interp_up: string;
  interp_rev: string;
  overridden: boolean;
  updated_at: string | null;
  updated_by: number | null;
};

export const api = {
  createSession: (birth: Birth, top_k = 4) =>
    jfetch<CreateSessionResp>("/chat/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ birth, top_k }),
    }).then((r) => { invalidateGetCache("sessions"); return r; }),
  postMessage: (
    sid: string,
    message: string,
    top_k = 4,
    depth: "basic" | "deep" = "basic",
    explain_level: "normal" | "easy" | "brief" = "normal",
  ) =>
    jfetch<ChatTurnResp>(`/chat/sessions/${sid}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, top_k, depth, explain_level }),
    }),
  getSession: (sid: string) => jfetch<any>(`/chat/sessions/${sid}`),
  // 최근 Q&A 맥락 기반 후속 추천질문(로컬 LLM 생성). 매 답변 후 호출.
  getSuggestions: (sid: string) =>
    jfetch<{ suggestions: string[] }>(`/chat/sessions/${sid}/suggestions`),
  // 택일/작명/개명/아호 후속 추천질문 (도구 세션 맥락)
  getToolSuggestions: (toolId: string) =>
    jfetch<{ suggestions: string[] }>(`/tools/${toolId}/suggestions`),
  // 궁합 후속 추천질문
  getCompatSuggestions: (compatId: string) =>
    jfetch<{ suggestions: string[] }>(`/compatibility/${compatId}/suggestions`),
  // ── 사주 답변 → 1분 쇼츠 영상 ──
  createVideoJob: (messageId: number, sessionId?: string) =>
    jfetch<VideoJobResp>("/video/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id: messageId, session_id: sessionId }),
    }),
  getVideoJob: (token: string) => jfetch<VideoJobResp>(`/video/jobs/${token}`),
  myVideoJobs: (active = true) =>
    jfetch<{ items: VideoJobResp[]; total: number }>(`/video/jobs?active=${active ? 1 : 0}`),
  // 다운로드는 인증 헤더 필요(소유 검증) → fetch+blob 저장(직링크 401 회피)
  // onProgress: 수신 진척률(0~100) 콜백. 14MB 영상이라 LTE에서 수 초 걸림 →
  //   스트리밍으로 받아 진행바를 보여줘야 사용자가 "멈춘 줄 알고" 다시 누르지 않는다.
  //   Content-Length 없거나 스트림 미지원이면 통짜 blob 으로 폴백(진척률 없이 동작만).
  downloadVideo: async (
    token: string,
    filename = "saju_video.mp4",
    onProgress?: (pct: number) => void,
  ) => {
    const r = await fetch(BASE + `/video/jobs/${token}/download`, { headers: authHeaders() });
    if (!r.ok) {
      const { message, code } = await parseError(r);
      throw new ApiError(message, r.status, code);
    }
    const total = Number(r.headers.get("Content-Length") || 0);
    let blob: Blob;
    if (r.body && total > 0 && onProgress) {
      const reader = r.body.getReader();
      const chunks: Uint8Array[] = [];
      let received = 0;
      onProgress(0);
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        if (value) {
          chunks.push(value);
          received += value.length;
          onProgress(Math.min(99, Math.round((received / total) * 100)));  // 99%까지만(100은 저장 시점)
        }
      }
      blob = new Blob(chunks as BlobPart[], { type: r.headers.get("Content-Type") || "video/mp4" });
    } else {
      blob = await r.blob();
    }
    onProgress?.(100);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
  listUploads: (status?: string, limit = 500) => {
    const qs = new URLSearchParams();
    if (status) qs.set("status_filter", status);
    qs.set("limit", String(limit));
    return jfetch<UploadDTO[]>(`/uploads?${qs.toString()}`);
  },
  uploadStats: () => jfetch<UploadStats>("/uploads/stats"),
  // 단일 파일 등록. FormData 라 jfetch(인증헤더 자동·Content-Type 자동·401 자동갱신) 사용.
  // (과거 생 fetch 라 Authorization 누락 → POST /api/uploads 로그인 필수화 후 401 "login required" 발생했던 버그)
  submitUpload: (form: FormData) =>
    jfetch<UploadDTO>("/uploads", { method: "POST", body: form }),
  // zip 일괄 업로드(관리자) — 서버가 압축 해제 후 pdf/이미지/txt 를 학습 파이프라인에
  // 투입하고 학습 배치를 자동 시작. FormData 라 jfetch(인증헤더, Content-Type 자동) 사용.
  submitUploadZip: (form: FormData) =>
    jfetch<{
      extracted: number;
      duplicates: number;
      skipped: number;
      rejected: number;
      total_in_zip: number;
      learning_started: boolean;
      message: string;
    }>("/uploads/zip", { method: "POST", body: form }),
  approve: (id: number, reviewer: string, comment: string) =>
    jfetch<UploadDTO>(`/uploads/${id}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer, comment }),
    }),
  reject: (id: number, reviewer: string, comment: string) =>
    jfetch<UploadDTO>(`/uploads/${id}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer, comment }),
    }),
  // 관리자 수동 학습 실행(야간 배치 대기 없이 즉시) + 실행 상태
  runManualLearning: () =>
    jfetch<{ status: string; message: string }>("/uploads/run-learning", { method: "POST" }),
  learningStatus: () => jfetch<LearningStatus>("/uploads/learning-status"),
  runs: () => jfetch<{ runs: EvalRun[]; count: number }>("/eval/runs"),
  // RAG 검색 품질 평가를 지금 1회 실행(백그라운드, 관리자) + 실행 상태 폴링
  evalRun: (tag?: string) =>
    jfetch<{ status: string; tag: string; message: string }>("/eval/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(tag ? { tag } : {}),
    }),
  evalStatus: () => jfetch<EvalStatus>("/eval/status"),

  // ---- auth ----
  login: (email: string, password: string) =>
    jfetch<TokenResp>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),
  register: (body: {
    email: string;
    password: string;
    nickname?: string;
    birth_date: string;
    marketing_opt_in?: boolean;
    agree_terms: boolean;
    agree_privacy: boolean;
    agree_refund: boolean;
    agree_disclaimer?: boolean;
  }) =>
    jfetch<TokenResp>("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  refresh: (refresh_token: string) =>
    jfetch<TokenResp>("/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token }),
    }),
  authLogout: (refresh_token: string) =>
    fetch("/api/auth/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token }),
    }).catch(() => {}),
  legalVersions: () => jfetch<LegalInfo>("/auth/legal"),
  me: () => jfetch<MeResp>("/auth/me"),
  saveSajuProfile: (profile: Partial<Birth> | null) =>
    jfetch<MeResp>("/auth/me/saju", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile }),
    }),
  agreeDisclaimer: () =>
    jfetch<MeResp>("/auth/me/agree-disclaimer", { method: "POST" }),
  agreeTerms: (body: { agree_terms: boolean; agree_privacy: boolean; agree_refund: boolean; marketing_opt_in?: boolean }) =>
    jfetch<MeResp>("/auth/me/agree-terms", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteMe: () =>
    fetch("/api/auth/me", {
      method: "DELETE",
      headers: { Authorization: `Bearer ${getToken() || ""}` },
    }).then(async (r) => {
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        throw new Error(j?.detail || `HTTP ${r.status}`);
      }
    }),
  changePassword: (current_password: string, new_password: string) =>
    jfetch<MeResp>("/auth/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password, new_password }),
    }),
  updateProfile: (body: { nickname?: string; answer_dialect?: string }) =>
    jfetch<MeResp>("/auth/me", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  submitFeedback: (body: { message_id: number; session_id?: string; rating: 1 | -1; comment?: string; source?: "chat" | "tool" | "compat" | "tarot" }) =>
    jfetch<{ id: number; message_id: number; rating: number; reward_granted?: number; balance?: number }>("/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  // ---- admin: 과금/한도 설정 + 답변양식 ----
  adminGetSettings: () => jfetch<{ settings: AppSettings }>("/admin/settings"),
  adminPatchSettings: (body: Partial<AppSettings>) =>
    jfetch<{ settings: AppSettings }>("/admin/settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  // 운영/법무 설정(사업자 정보·약관 버전/본문·SMTP)
  adminGetSiteSettings: () => jfetch<{ settings: SiteSettings }>("/admin/site-settings"),
  adminPatchSiteSettings: (body: Record<string, string | number | boolean>) =>
    jfetch<{ settings: SiteSettings }>("/admin/site-settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  adminTemplates: () => jfetch<{ items: AnswerTemplate[] }>("/admin/templates"),
  adminCreateTemplate: (body: { name: string; body: string; active?: boolean }) =>
    jfetch<AnswerTemplate>("/admin/templates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  adminUpdateTemplate: (id: number, body: { name?: string; body?: string; active?: boolean }) =>
    jfetch<AnswerTemplate>(`/admin/templates/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  adminActivateTemplate: (id: number) =>
    jfetch<AnswerTemplate>(`/admin/templates/${id}/activate`, { method: "POST" }),
  adminDeleteTemplate: (id: number) =>
    jfetch<void>(`/admin/templates/${id}`, { method: "DELETE" }),

  // ---- admin ----
  adminStats: () => jfetch<AdminStats>("/admin/stats"),
  adminUsers: (q?: string, limit = 50, offset = 0) =>
    jfetch<{ items: AdminUser[]; total: number; limit: number; offset: number }>(
      `/admin/users?${new URLSearchParams({
        ...(q ? { q } : {}),
        limit: String(limit),
        offset: String(offset),
      }).toString()}`
    ),
  adminUserTransactions: (user_id: number, limit = 50) =>
    jfetch<{ items: AdminTx[] }>(`/admin/users/${user_id}/transactions?limit=${limit}`),
  adminUserPayments: (user_id: number, limit = 50) =>
    jfetch<{ items: AdminPayment[] }>(`/admin/users/${user_id}/payments?limit=${limit}`),
  adminRefundPayment: (order_id: string, reason = "admin refund") =>
    jfetch<AdminRefundResult>(`/admin/payments/${encodeURIComponent(order_id)}/refund`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    }),
  adminGrantCredit: (user_id: number, delta: number, reason = "admin_grant") =>
    jfetch<{ user_id: number; balance: number }>(`/admin/users/${user_id}/grant`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ delta, reason }),
    }),
  adminSetUserAds: (user_id: number, ads_hidden: boolean) =>
    jfetch<{ user_id: number; ads_hidden: boolean }>(`/admin/users/${user_id}/ads`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ads_hidden }),
    }),
  adminBanners: (slot?: string) =>
    jfetch<{ items: Banner[] }>(`/admin/banners${slot ? `?slot=${slot}` : ""}`),
  adminCreateBanner: (b: Partial<Banner> & { slot: string; image_url: string }) =>
    jfetch<Banner>("/admin/banners", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(b),
    }),
  adminUpdateBanner: (id: number, b: Partial<Banner>) =>
    jfetch<Banner>(`/admin/banners/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(b),
    }),
  adminDeleteBanner: (id: number) =>
    jfetch<void>(`/admin/banners/${id}`, { method: "DELETE" }),

  // ---- 타로 카드 해석/키워드 편집 ----
  adminTarotCards: () =>
    jfetch<{ items: TarotAdminCard[] }>("/admin/tarot/cards"),
  adminUpdateTarotCard: (
    code: string,
    body: { keywords_up: string[]; keywords_rev: string[]; interp_up: string; interp_rev: string },
  ) =>
    jfetch<TarotAdminCard>(`/admin/tarot/cards/${code}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  adminResetTarotCard: (code: string) =>
    jfetch<TarotAdminCard>(`/admin/tarot/cards/${code}/reset`, { method: "POST" }),

  // ---- 1:1 인적 상담(입점업체) ----
  consultants: (specialty?: "saju" | "tarot") =>
    jfetch<{ items: ConsultantPublic[] }>(
      `/consultation/consultants${specialty ? `?specialty=${specialty}` : ""}`
    ),
  consultationConfig: () => jfetch<ConsultationConfig>("/consultation/config"),
  myConsultantProfile: () =>
    jfetch<{ consultant: ConsultantAdmin | null }>("/consultation/consultant/me"),
  // admin
  adminConsultants: () => jfetch<{ items: ConsultantAdmin[] }>("/admin/consultants"),
  adminCreateConsultant: (body: ConsultantCreateBody) =>
    jfetch<ConsultantAdmin>("/admin/consultants", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  adminUpdateConsultant: (id: number, body: Partial<ConsultantCreateBody>) =>
    jfetch<ConsultantAdmin>(`/admin/consultants/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  adminDeleteConsultant: (id: number) =>
    jfetch<void>(`/admin/consultants/${id}`, { method: "DELETE" }),
  // 회원관리에서 상담사 지정(회원→입점업체 생성/연결) + 분야(사주/타로/둘다)
  adminDesignateConsultant: (user_id: number, specialty: ConsultantSpecialty = "saju") =>
    jfetch<ConsultantAdmin>("/admin/consultants/from-user", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id, specialty }),
    }),
  // 간판 이미지 업로드 — FormData(인증헤더·Content-Type 자동)
  adminUploadSignboard: (id: number, form: FormData) =>
    jfetch<ConsultantAdmin>(`/admin/consultants/${id}/signboard`, { method: "POST", body: form }),
  adminGetConsultationSettings: () =>
    jfetch<{ settings: ConsultationSettings }>("/admin/consultants/settings"),
  adminPatchConsultationSettings: (body: Partial<ConsultationSettings>) =>
    jfetch<{ settings: ConsultationSettings }>("/admin/consultants/settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  // 상담 세션 lifecycle
  requestConsultation: (consultant_id: number, consent: boolean) =>
    jfetch<ConsultationSession>("/consultation/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ consultant_id, consent }),
    }),
  consultationSession: (id: string) =>
    jfetch<ConsultationSession>(`/consultation/sessions/${id}`),
  consultationMessages: (id: string) =>
    jfetch<{ items: ConsultationChatMessage[] }>(`/consultation/sessions/${id}/messages`),
  myConsultations: () =>
    jfetch<{ items: ConsultationSession[] }>("/consultation/sessions/mine"),
  acceptConsultation: (id: string) =>
    jfetch<ConsultationSession>(`/consultation/sessions/${id}/accept`, { method: "POST" }),
  declineConsultation: (id: string) =>
    jfetch<ConsultationSession>(`/consultation/sessions/${id}/decline`, { method: "POST" }),
  endConsultation: (id: string) =>
    jfetch<ConsultationSession>(`/consultation/sessions/${id}/end`, { method: "POST" }),
  extendConsultation: (id: string) =>
    jfetch<ConsultationSession>(`/consultation/sessions/${id}/extend`, { method: "POST" }),
  cancelConsultation: (id: string) =>
    jfetch<ConsultationSession>(`/consultation/sessions/${id}/cancel`, { method: "POST" }),
  rateConsultation: (id: string, rating: number) =>
    jfetch<ConsultationSession>(`/consultation/sessions/${id}/rating`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating }),
    }),
  consultationReport: (id: string) =>
    jfetch<{ token: string; url: string; download_url: string; filename: string }>(
      `/consultation/sessions/${id}/report`, { method: "POST" }
    ),
  // 상담사 콘솔
  consultantRequests: () =>
    jfetch<{ items: ConsultationSession[] }>("/consultation/consultant/requests"),
  setConsultantAvailability: (online: boolean) =>
    jfetch<ConsultantAdmin>("/consultation/consultant/availability", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ online }),
    }),
  // 관리자 정산 실지급 뷰
  adminSettlements: (consultant_id?: number, status?: "pending" | "settled") => {
    const qs = new URLSearchParams();
    if (consultant_id != null) qs.set("consultant_id", String(consultant_id));
    if (status) qs.set("status", status);
    const q = qs.toString();
    return jfetch<{ items: ConsultationSettlementRow[]; totals: SettlementTotals }>(
      `/admin/consultants/settlements${q ? `?${q}` : ""}`
    );
  },
  adminSettleSettlement: (id: number) =>
    jfetch<ConsultationSettlementRow>(`/admin/consultants/settlements/${id}/settle`, { method: "POST" }),
  adminUnsettleSettlement: (id: number) =>
    jfetch<ConsultationSettlementRow>(`/admin/consultants/settlements/${id}/unsettle`, { method: "POST" }),
  adminSettleAllConsultant: (consultant_id: number) =>
    jfetch<{ settled: number; total_payout_p: number }>(
      `/admin/consultants/${consultant_id}/settle-all`, { method: "POST" }
    ),

  // ---- payments ----
  paymentPackages: () =>
    jfetch<{ items: { amount: number; credits: number; label: string }[] }>(
      "/payments/packages"
    ),
  paymentCreateOrder: (amount: number) =>
    jfetch<{
      order_id: string;
      amount: number;
      credits: number;
      client_key: string;
      success_url: string;
      fail_url: string;
      order_name: string;
      customer_email: string;
      customer_name: string;
    }>("/payments/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount }),
    }),
  paymentConfirm: (payment_key: string, order_id: string, amount: number) =>
    jfetch<{
      status: string;
      order_id: string;
      amount: number;
      credits_granted: number;
      balance: number;
      already: boolean;
      mock?: boolean;
    }>("/payments/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payment_key, order_id, amount }),
    }),
  paymentMyHistory: () =>
    jfetch<{
      items: {
        id: number;
        order_id: string;
        amount: number;
        credit_granted: number;
        status: string;
        created_at: string;
        approved_at: string | null;
      }[];
    }>("/payments/me"),
  refundPayment: (order_id: string, reason = "admin refund") =>
    jfetch<{
      order_id: string;
      status: string;
      credits_recovered: number;
      balance: number;
    }>("/payments/refund", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ order_id, reason }),
    }),

  // ---- 공유(계획 K) ----
  shareQuota: () =>
    jfetch<{ used: number; limit: number; remaining: number; unlimited: boolean }>(
      "/share/quota"
    ),
  submitShare: (body: {
    channel: "kakao" | "email" | "link";
    message_id?: number;
    session_id?: string;
    target?: string;
  }) =>
    jfetch<{ ok: boolean; used: number; remaining: number; unlimited: boolean }>(
      "/share",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    ),

  // ---- 상담서 PDF(상장 양식+관인) 생성 → 토큰 URL ----
  // 6개 메뉴 공통. doc_title/person_line/item/content 를 받아 백엔드가 PDF 를 만들어
  // data/pdf 에 저장하고 토큰 URL 을 돌려준다. 공유/다운로드는 이 URL 을 사용.
  generatePdf: (body: {
    doc_title: string;
    person_line?: string;
    item?: string;
    content: string;
    when?: string;
    session_id?: string;   // 사주 세션 — 있으면 명식 패널(한지 위 본인 사주) 포함
  }) =>
    jfetch<{ token: string; url: string; download_url: string; filename: string }>(
      "/pdf/consultation",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    ),

  // ---- 종합 감정서: 상담 전체(여러 Q&A)를 로컬 LLM이 하나의 글로 재구성 → PDF ----
  generateReport: (body: {
    doc_title: string;
    person_line?: string;
    item?: string;
    conversation: { role: string; content: string }[];
    topic?: string;
    when?: string;
    session_id?: string;   // 사주 세션 — 있으면 명식 패널(한지 위 본인 사주) 포함
  }) =>
    jfetch<{ token: string; url: string; download_url: string; filename: string }>(
      "/pdf/consultation-report",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    ),

  // ---- 다중 사주 프로필(계획 7-D.2) ----
  listSajuProfiles: () =>
    cachedGet("profiles", () => jfetch<{ items: SajuProfile[] }>("/profiles")),
  createSajuProfile: (body: SajuProfileInput) =>
    jfetch<SajuProfile>("/profiles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => { invalidateGetCache("profiles"); return r; }),
  updateSajuProfile: (id: number, body: Partial<SajuProfileInput>) =>
    jfetch<SajuProfile>(`/profiles/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => { invalidateGetCache("profiles"); return r; }),
  deleteSajuProfile: (id: number) =>
    jfetch<void>(`/profiles/${id}`, { method: "DELETE" }).then(() => { invalidateGetCache("profiles"); }),

  // ---- 궁합(宮合) ----
  createCompatibility: (
    person_a: CompatPersonReq,
    person_b: CompatPersonReq,
    depth: "basic" | "deep" = "deep",
    explain_level: "normal" | "easy" | "brief" = "normal",
  ) =>
    jfetch<CompatResponse>("/compatibility", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ person_a, person_b, depth, explain_level }),
    }).then((r) => { invalidateGetCache("compat:average"); return r; }),
  compatibilityAverage: () => cachedGet("compat:average", () => jfetch<CompatAverage>("/compatibility/average")),
  getCompatibility: (id: string) => jfetch<CompatResponse>(`/compatibility/${id}`),

  // ---- 타로 ----
  createTarot: (section: string, question: string) =>
    jfetch<TarotCreateResp>("/tarot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ section, question }),
    }),
  // picks 는 세션당 1회 확정(서버 멱등) — 재호출 시 저장된 동일 결과 반환
  tarotPicks: (id: string, indices: number[]) =>
    jfetch<{ cards: TarotCard[] }>(`/tarot/${id}/picks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ indices }),
    }),
  getTarot: (id: string) => jfetch<TarotSnapshot>(`/tarot/${id}`),
  getTarotSuggestions: (id: string) =>
    jfetch<{ suggestions: string[] }>(`/tarot/${id}/suggestions`),
  // 세션 이력(로그인 필수) — 목록/삭제. 20개 상한·1주 보관은 서버 정책.
  listTarot: () => jfetch<TarotSessionList>("/tarot"),
  deleteTarot: (id: string) => jfetch<void>(`/tarot/${id}`, { method: "DELETE" }),

  // ---- 명리 도구 ----
  createNaming: (body: { kind: NamingKind; birth: Birth; surname?: string; current_name?: string; reading?: string }) =>
    jfetch<ToolResponse>("/tools/naming", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  createTaekil: (body: { birth: Birth; birth2?: Birth | null; purpose: TaekilPurpose; start_date: string; days: number }) =>
    jfetch<ToolResponse>("/tools/taekil", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  getTool: (id: string) => jfetch<ToolResponse>(`/tools/${id}`),
  lookupHanja: (reading: string) =>
    jfetch<{ reading: string; items: { char: string; strokes: number; defn: string; is_surname: boolean }[] }>(
      `/tools/hanja?reading=${encodeURIComponent(reading)}`,
    ),
  lookupSurname: (reading: string) =>
    jfetch<{ reading: string; items: { char: string; strokes: number; defn: string; is_compound: boolean }[] }>(
      `/tools/surname?reading=${encodeURIComponent(reading)}`,
    ),

  // ---- 내 채팅 세션 ----
  myChatSessions: (limit = 50) =>
    cachedGet(`sessions:${limit}`, () => jfetch<{
      items: {
        session_id: string;
        title: string;
        created_at: string;
        birth_date: string;
        gender: string;
        message_count: number;
      }[];
      total: number;
      max_sessions: number;
    }>(`/chat/sessions?limit=${limit}`)),
  deleteChatSession: (sid: string) =>
    jfetch<void>(`/chat/sessions/${sid}`, { method: "DELETE" }).then(() => { invalidateGetCache("sessions"); }),
  revealMessage: (sid: string, mid: number) =>
    jfetch<{
      message_id: number;
      content: string;
      preview_revealed: boolean;
      credits_charged: number;
      balance_after: number;
    }>(`/chat/sessions/${sid}/messages/${mid}/reveal`, { method: "POST" }),

  // ---- 공개 배너 ----
  publicBanners: (slot?: string, pickOne = false) =>
    jfetch<{
      items: {
        id: number;
        slot: string;
        image_url: string;
        link_url?: string | null;
        title?: string | null;
        weight: number;
      }[];
    }>(`/banners?${new URLSearchParams({
      ...(slot ? { slot } : {}),
      ...(pickOne ? { pick_one: "true" } : {}),
    }).toString()}`),

  // ---- OAuth ----
  oauthStart: (provider: "kakao" | "google") =>
    jfetch<{ provider: string; authorize_url: string; state: string; mock: boolean; redirect_uri: string }>(
      `/auth/oauth/${provider}/start`
    ),
  oauthTestLogin: (provider: "kakao" | "google") =>
    jfetch<{ access_token: string; refresh_token?: string | null; token_type: string; role: "user" | "admin"; email: string; provider: string; mock: boolean }>(
      `/auth/oauth/${provider}/test-login`,
      { method: "POST" }
    ),

  // ---- Web Push (PWA) ----
  pushSubscribe: (body: { endpoint: string; p256dh: string; auth: string }) =>
    jfetch<{ ok: boolean }>(`/push/subscribe`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  pushUnsubscribe: (endpoint: string) =>
    jfetch<{ ok: boolean }>(`/push/unsubscribe`, {
      method: "DELETE",
      body: JSON.stringify({ endpoint }),
    }),

  // ---- 고객센터(CONTACT US) ----
  supportCreateTicket: (body: {
    category: SupportCategory;
    contact_email: string;
    contact_name?: string;
    order_id?: string;
    amount?: number;
    title: string;
    message: string;
  }) =>
    jfetch<SupportTicket>("/support/tickets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  supportMyTickets: () => jfetch<{ items: SupportTicket[] }>("/support/tickets/mine"),
  // 관리자: 문의 게시판 + 수신자 CRUD
  adminSupportTickets: (status?: SupportStatus, limit = 50, offset = 0) =>
    jfetch<{ items: SupportTicket[]; total: number; limit: number; offset: number }>(
      `/admin/support/tickets?${new URLSearchParams({
        ...(status ? { status } : {}),
        limit: String(limit),
        offset: String(offset),
      }).toString()}`
    ),
  adminSupportUpdateTicket: (id: number, body: { status?: SupportStatus; admin_note?: string }) =>
    jfetch<SupportTicket>(`/admin/support/tickets/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  // 환불 요청 승인 → 실제 환불 자동 실행(주문번호 연결분). 처리완료로 전환 + 메모 자동 기록.
  adminSupportRefundTicket: (id: number, reason?: string) =>
    jfetch<{ ticket: SupportTicket; refund: AdminRefundResult }>(`/admin/support/tickets/${id}/refund`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reason ? { reason } : {}),
    }),
  adminSupportRecipients: () =>
    jfetch<{ items: SupportRecipient[] }>("/admin/support/recipients"),
  adminSupportAddRecipient: (email: string) =>
    jfetch<SupportRecipient>("/admin/support/recipients", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    }),
  adminSupportSetRecipient: (id: number, active: boolean) =>
    jfetch<SupportRecipient>(`/admin/support/recipients/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active }),
    }),
  adminSupportDeleteRecipient: (id: number) =>
    jfetch<void>(`/admin/support/recipients/${id}`, { method: "DELETE" }),
};
