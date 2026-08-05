import { useSyncExternalStore } from "react";
import i18n from "./i18n";

const BASE = "/api";
const TOKEN_KEY = "saju_token";
const ME_KEY = "saju_me";

/** 인증 상태(토큰/내 정보)가 바뀔 때 발생하는 전역 이벤트. */
const AUTH_EVENT = "saju:auth-changed";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string | null): void {
  if (t) {
    localStorage.setItem(TOKEN_KEY, t);
    _sessionExpiredHandled = false;  // 새 세션(로그인·무음갱신 성공) → 만료 가드 리셋: SPA 재로그인 후 다음 만료도 잡히게(전체 리로드 없이 발동)
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
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
  const loc = localStorage.getItem("saju_lang");
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

/** SSE 스트림 등 '생 fetch' 직전 호출 — 액세스 토큰이 만료(임박)면 refresh 로 미리 갱신해 유효 토큰 반환.
 *  스트림은 만료 토큰에 401 대신 get_optional_user 가 조용히 익명(None) 처리 →
 *  '로그인 상태(캐시 잔액)인데 미리보기'로 나오던 사고(운영자 지적: 꿈해몽·신년 등)를 차단한다. */
export async function ensureFreshToken(): Promise<string | null> {
  const t = getToken();
  if (!t) return null;
  let exp = 0;
  try { exp = (JSON.parse(atob(t.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).exp || 0) * 1000; } catch { exp = 0; }
  if (exp && exp - Date.now() > 20000) return t;   // 20s 이상 유효 — 그대로 사용
  const ok = await tryRefreshToken();               // 만료·임박(또는 exp 파싱 실패) → 무음 갱신 시도
  if (ok) return getToken();                         // 성공 → 새 토큰
  // 갱신 실패 + 토큰이 실제로 만료·임박(exp 확인됨) → 만료 토큰을 그대로 흘려 익명 미리보기로 강등되게 두지 말고
  // 즉시 세션 정리(강제 로그아웃). exp 파싱 실패 등 애매한 경우만 기존값 유지(백엔드 401이 최종 판단).
  if (exp) { notifySessionExpired(); return null; }
  return getToken();
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
  amulet_cost_p?: number;                         // B-4 부적 발행 차감 P(관리자 설정값)
  active_pass?: PassMine | null;                  // B-7 월 패스 상태
  // 플러스 추가질문 할인% — 화면이 '실제 차감액'을 서버와 같은 식으로 계산하는 데 쓴다.
  // 이게 없어서 플러스에게 정가(1,900P)를 안내하고 실제로는 1,330P 를 차감하고 있었다.
  pass_followup_discount_pct?: number;
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
  review_reward_p: number;
  amulet_cost_p: number;
  video_gen_cost: number;
  external_llm_enabled: boolean;
  // 프리미엄 5개 메뉴 입장료(메뉴별) + 공통 행사 할인%
  entry_cost_compat: number;
  entry_cost_taekil: number;
  entry_cost_jakmyeong: number;
  entry_cost_gaemyeong: number;
  entry_cost_aho: number;
  entry_cost_tarot: number;
  entry_cost_sinnyeon: number;
  premium_entry_discount_pct: number;
  pricing_survey_enabled?: boolean;
  pricing_auto_apply_enabled?: boolean;
};

/** 마케팅 가격 에이전트(2026-07-13) */
export type CompetitorPrice = {
  id: number; competitor_name: string; menu_key: string; label: string;
  price_krw: number; note?: string | null; verified_at?: string | null; stale: boolean;
};
export type PricingGuardrail = {
  menu_key: string; label: string; floor_p: number; ceiling_p: number;
  max_change_pct: number; undercut_pct: number; round_unit: number; round_tail: number; enabled: boolean;
};
export type PricingRecommendation = {
  id: number; batch_id: string; menu_key: string; label: string; current_price: number;
  competitor_min?: number | null; competitor_median?: number | null; recommended_price: number;
  rationale?: string | null; status: "pending" | "applied" | "dismissed" | "skipped";
  applied_from?: number | null; decided_at?: string | null; decided_by?: string | null; created_at?: string | null;
};
export type PricingOverview = {
  competitors: CompetitorPrice[];
  guardrails: PricingGuardrail[];
  pending: PricingRecommendation[];
  history: PricingRecommendation[];
  sync_diff: { menu_key: string; label: string; live: number; code_default: number }[];
  survey_enabled: boolean;
};

// ---- 1:1 인적 상담(입점업체) ----
export type ConsultantPresence = "offline" | "online" | "busy";
export type ConsultantSpecialty = "saju" | "tarot" | "both";

export type ConsultantPriceUnit = "session" | "minute" | "hour";
export type ConsultantStatus = "active" | "coming_soon" | "hidden";

/** 요일별 영업시간(KST). 키 "0"=월 … "6"=일. 값 없는 요일=휴무. */
export type BusinessHours = Record<string, { open: string; close: string }>;

export type ConsultantPublic = {
  id: number;
  business_name: string;
  specialty: ConsultantSpecialty;
  signboard_image_url?: string | null;
  intro?: string | null;
  keywords?: string[];            // #전문영역 칩
  price_p: number;                // 1회(블록) 실제 차감가
  duration_min: number;
  price_unit?: ConsultantPriceUnit;  // 표시용(session|minute|hour)
  per_min_p?: number | null;      // 분당 요금(표시)
  per_hour_p?: number | null;     // 시간당 요금(표시)
  status?: ConsultantStatus;      // active | coming_soon(입점예정)
  business_hours?: BusinessHours | null;  // 요일별 영업시간(안내용, 없으면 상시)
  presence: ConsultantPresence;
  session_count: number;          // 누적 상담건수(완료)
  rating_avg?: number | null;     // 평균 만족도(1~5, 없으면 null)
  rating_count: number;           // 평점 참여 수
};

/** 상담사 본인 설정 화면용(GET /consultation/consultant/me). PII·정산 통계 미포함. */
export type ConsultantSelf = {
  id: number;
  business_name: string;          // 읽기전용(관리자 통제)
  specialty: ConsultantSpecialty; // 읽기전용
  signboard_image_url?: string | null;
  intro?: string | null;
  keywords: string[];
  price_unit: ConsultantPriceUnit;
  rate_p?: number | null;
  per_min_p?: number | null;
  per_hour_p?: number | null;
  duration_min: number;           // 유효 블록(분)
  eff_duration_min: number;
  duration_min_raw?: number | null;
  eff_price_p: number;            // 1회 예상 차감가(하한 반영)
  min_price_p: number;            // 요금 하한(0=없음)
  status: ConsultantStatus;
  business_hours?: BusinessHours;   // 요일별 영업시간(0=월~6=일) — 편집용
  presence: ConsultantPresence;
  is_active: boolean;
  self_managed: boolean;
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
  keywords?: string[];
  rate_p?: number | null;
  duration_min_raw?: number | null;
  commission_pct_raw?: number | null;
  price_unit?: ConsultantPriceUnit;
  per_min_p?: number | null;
  per_hour_p?: number | null;
  eff_price_p: number;
  eff_duration_min: number;
  eff_commission_pct: number;
  is_active: boolean;
  status?: ConsultantStatus;
  business_hours?: BusinessHours;   // 요일별 영업시간(0=월~6=일) — 편집용
  self_managed?: boolean;
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
  /** A-2 예약 정책(고지용) */
  reserve_full_refund_hours?: number;
  reserve_late_refund_pct?: number;
  reserve_grace_min?: number;
};

/** A-2 예약 슬롯 — 상담사 등록 시간. status: open|booked|converted|cancelled */
export type ConsultationSlot = {
  id: string;
  consultant_id: number;
  start_at: string; // UTC ISO(Z) — new Date()로 로컬 표기
  duration_min: number;
  status: "open" | "booked" | "converted" | "cancelled" | "done";
  price_p: number;
  charged_p: number;
  refund_p: number;
  session_id?: string | null;
  user_id?: number | null;
  booked_at?: string | null;
  consultant_name?: string | null;
};

export type ConsultationSettings = {
  consultation_default_price_p: number;
  consultation_default_duration_min: number;
  consultation_min_price_p: number;
  consultation_commission_pct: number;
  consultation_tax_pct: number;
  consultation_no_show_timeout_sec: number;
  consultation_extend_warn_sec: number;
  consultation_retention_days: number;
  // A-2 예약 취소/환불/유예 정책(N2)
  consultation_reserve_full_refund_hours?: number;
  consultation_reserve_late_refund_pct?: number;
  consultation_reserve_grace_min?: number;
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
  commission_p?: number;   // 관리자(플랫폼) 수수료 수익 합계
  tax_p?: number;
};

/** 상담사 본인 수익 요약(GET /consultation/consultant/earnings) — 기간별 건수·매출·수익(실지급). */
export type EarningsPeriod = {
  count: number;       // 상담 건수
  revenue_p: number;   // 매출(원)
  payout_p: number;    // 수익=실지급(원)
};
export type ConsultantEarnings = {
  currency: string;
  today: EarningsPeriod;
  month: EarningsPeriod;
  year: EarningsPeriod;
  total: EarningsPeriod;
  payout_pending_p: number;  // 지급대기(현재 받을 예정 금액)
  payout_settled_p: number;  // 지급완료 누계
};

export type ConsultantCreateBody = {
  login_email: string;
  business_name: string;
  specialty: ConsultantSpecialty;
  intro?: string | null;
  keywords?: string[];
  rate_p?: number | null;
  duration_min?: number | null;
  commission_pct?: number | null;
  price_unit?: ConsultantPriceUnit;
  per_min_p?: number | null;
  per_hour_p?: number | null;
  is_active?: boolean;
  status?: ConsultantStatus;
  self_managed?: boolean;
  sort_order?: number;
};

/** 상담사 셀프 편집 바디(PATCH /consultation/consultant/me). */
export type ConsultantSelfBody = {
  business_name?: string;
  intro?: string | null;
  keywords?: string[];
  price_unit?: ConsultantPriceUnit;
  rate_p?: number | null;
  per_min_p?: number | null;
  per_hour_p?: number | null;
  status?: "active" | "coming_soon";
  business_hours?: BusinessHours | null;   // 요일별 영업시간(0=월~6=일, 없는 요일=휴무)
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
  /** A-2 예약 전환 세션이면 슬롯 id(선결제 여부·환불정책 판정용). 즉시 상담은 null. */
  reservation_id?: string | null;
  /** A-1 상담 컨텍스트 — 접수 시 서버가 뜬 스냅샷(사주 명식/타로 카드). 상담사 채팅방 패널 렌더용 */
  source_kind?: "saju" | "tarot" | "birth" | null;   // birth=출산 택일(양 부모 명식)
  source_context?: {
    chart?: unknown;
    birth_date?: string | null;
    birth_time?: string | null;
    calendar?: string | null;
    gender?: string | null;
    /** birth(출산 택일): 부모② 명식 — 상담사에게 양 부모 사주 전달 */
    parent2?: { chart?: unknown; birth_date?: string | null; birth_time?: string | null;
                calendar?: string | null; gender?: string | null } | null;
    question?: string | null;
    spread_type?: string | null;
    cards?: {
      position_index: number;
      position_name: string;
      name_kr: string;
      name_en?: string;
      orientation: "upright" | "reversed";
      code?: string;
      keywords?: string[];
    }[];
  } | null;
};

/** A-1: 상담 접수에 실어 보낼 소스 컨텍스트 참조(사주 채팅 세션/타로 세션) */
export type ConsultSource = { kind: "saju" | "tarot" | "birth"; refId: string; label?: string };  // birth=출산 택일(양 부모 명식)

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

// 답변 말투(사투리) 선택지 — value는 서버 전송 enum(불변), label은 로케일 표시용(err.dialect_*).
// label을 getter로 두어 언어 전환 시점의 로케일 문자열을 항상 반환한다(모듈 상수 고정 방지).
export const DIALECTS: { value: string; label: string }[] = [
  { value: "standard", get label() { return i18n.t("err.dialect_standard"); } },
  { value: "gyeongsang", get label() { return i18n.t("err.dialect_gyeongsang"); } },
  { value: "jeolla", get label() { return i18n.t("err.dialect_jeolla"); } },
  { value: "gangwon", get label() { return i18n.t("err.dialect_gangwon"); } },
  { value: "jeju", get label() { return i18n.t("err.dialect_jeju"); } },
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
  revenue_today_krw: number;
  revenue_week_krw: number;
  revenue_month_krw: number;
  revenue_year_krw: number;
  total_outstanding_credits: number;
};

export type AdminUsageSummary = {
  online_now: number;
  today_visitors: number;
  pwa: { total: number; ios?: number; android?: number; desktop?: number; other?: number };
  menus: { key: string; today: number; week: number }[];
  clicks: { key: string; today: number; week: number }[];
  /** 메뉴별 세부 기능 '실사용' — 백엔드 DB 실측(클릭이 아니라 실제 실행 완료 수) */
  features: { menu: string; feature: string; today: number; week: number; total: number }[];
  as_of: string;
};

// 관리자 통계 '전 회원 결제 리스트'용(회원 이메일 포함). 환불용 AdminPayment(회원별)와 별개.
export type AdminPaymentRow = {
  order_id: string;
  email: string;
  amount: number;
  credit_granted: number;
  status: string;
  created_at: string | null;
  approved_at: string | null;
};

/** 포인트 원장 한 줄 — delta 부호로 적립(+)/사용(−) 구분. balance_after=그 시점 잔액. */
export type CreditTxn = {
  id: number;
  delta: number;
  reason: string;
  ref_id: string | null;
  balance_after: number;
  created_at: string;
};

/** 포인트 원장 정합성 요약 — 사용자가 '충전+적립−사용=잔액'을 직접 대조. consistent=원장합==표시잔액. */
export type CreditSummary = {
  purchased: number;   // 실제 결제 충전
  rewarded: number;    // 보너스·환불·리워드·지급
  used: number;        // 사용(차감) 합
  balance: number;     // 현재 잔액
  computed_balance: number;  // 원장 합(Σdelta)
  consistent: boolean;
  count: number;
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
  /** 'aligned' = 운영과 동일한 게이트(리랭커·임계·top_k)로 측정 / 'legacy'(또는 없음) = 옛 방식.
   *  둘은 재는 대상이 달라 점수를 이어서 비교하면 안 된다(P3-D2). */
  eval_mode?: "aligned" | "legacy";
  /** 0건 회수 비율 — 운영의 최악 케이스. 옛 방식은 게이트가 없어 구조적으로 항상 0이었다. */
  zero_hit_rate?: number;
  mean_chunks_returned?: number;
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
  credits_charged?: number;        // 입장료 차감액(신규 생성 응답에만; 복원 스냅샷엔 없음) — 즉석 영수증용
  balance_after?: number | null;
};
export type TarotCard = {
  position_index: number;
  position_name: string;
  position_name_vi?: string;   // vi 포지션명(로케일 렌더용 병기)
  code: string;
  name_kr: string;
  name_en: string;
  name_vi?: string;            // vi 카드명(로케일 렌더용 병기)
  orientation: "upright" | "reversed";
  image_url: string;
  keywords: string[];
};
export type TarotMessage = {
  id?: number; role: string; content: string;
  is_preview?: boolean; preview_revealed?: boolean;  // 익명 미리보기 마스킹 상태(복원 시 잠금 안내용)
};
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

// '지난 결과' 목록 항목(프리미엄 도구·궁합 재열람용, 무차감)
export type ToolSessionItem = {
  tool_id: string;
  tool: string;   // sinnyeon | naming | taekil | amulet
  kind: string;   // jakmyeong|gaemyeong|aho | wedding|... | 연도 | wealth|love|...
  created_at: string;
  input: Record<string, any>;
  birth_date: string | null;
  is_preview: boolean;
};
export type ToolSessionList = { items: ToolSessionItem[]; total: number };
export type CompatSessionItem = {
  compat_id: string;
  created_at: string;
  a_label: string | null;
  b_label: string | null;
  a_birth_date: string | null;
  b_birth_date: string | null;
};
export type CompatSessionList = { items: CompatSessionItem[]; total: number };

// ---- 명리 도구(작명/개명/아호/택일) ----
export type NamingKind = "jakmyeong" | "gaemyeong" | "aho";
export type TaekilPurpose =
  | "wedding" | "birth" | "moving" | "opening" | "contract"
  | "ceremony" | "surgery" | "travel" | "general";

/** B-7 월 패스 */
export type PassMine = {
  tier: "lite" | "plus";
  label: string;
  price_p: number;
  auto_renew: boolean;
  current_start: string;
  next_renewal_at: string;
  free_basic_remaining: number;
  amulet_free_remaining: number;
};
export type PassInfo = {
  products: Record<"lite" | "plus", {
    label: string; price_p: number; period_days: number; benefits: string[];
    worth_note?: string | null;   // 혜택 합 > 패스값일 때만 채워짐(예: '이 혜택만 22,900P 상당 — 패스는 9,900P')
  }>;
  mine: PassMine | null;
};

/** B-6 공유 카드 */
export type ShareCard = {
  token: string;
  url: string;
  download_url: string;
  filename: string;
  meta?: { iljin: string; ten_god: string; animal: string; date: string };
};

/** B-5 신뢰 지표(실측) */
export type TrustStats = {
  consultations: number;
  feedback_votes: number;
  satisfaction_pct: number | null;
  reviews: number;
};

/** B-4 부적 발행 */
export type AmuletPurpose = "wealth" | "love" | "exam" | "health" | "protect" | "biz";
export type AmuletResult = {
  token: string;
  url: string;
  download_url: string;
  filename: string;
  credits_charged: number;
  tool_id?: string;   // 해설·추가질문(공용 tools 스트림)용 세션
  amulet: {
    purpose: AmuletPurpose;
    purpose_label: string;
    name: string;
    hanja: string;
    element: string;
    obang: string;
    color: string;
    year: string;
    samjae: string | null;
    reasons: string[];
    disclaimer: string;
  };
};

/** B-3 이용 후기 */
export type ReviewSource = "chat" | "compat" | "tarot" | "tool" | "sinnyeon" | "consultation";
export type Review = {
  id: number;
  source: ReviewSource;
  source_label: string;
  content: string;
  rating: number;
  display_name: string;
  status: "pending" | "approved" | "rejected";
  created_at: string | null;
};

/** B-11 무료 스낵 테스트 */
export type SnackTest = { test_id: string; title: string; emoji: string; badge: string; desc: string; icon?: string };
export type SnackResult = {
  test_id: string; title: string; emoji: string; result_key: string; label: string;
  icon?: string;          // 결과 타입별 FLUX 일러스트 경로(/snack/{test}_{key}.webp). 없으면 emoji 폴백.
  color: string; headline: string; body: string;
  meter?: { value: number; max: number; label: string };
  reasons: string[]; disclaimer: string;
  card?: { token: string; url: string; download_url: string; filename: string } | null;
};

/** 상담사 입점 신청(2026-07-11) */
export type PartnerTerms = {
  version: string; effective_date: string; text: string; sha256: string; key_points: string[];
};
export type PartnerApplication = {
  id: number; email: string; specialty: "saju" | "tarot" | "both";
  business_name: string; contact?: string | null; intro?: string | null;
  terms_version: string; agreed_at: string;
  status: "pending" | "approved" | "rejected";
  reviewed_at?: string | null; reject_reason?: string | null; consultant_id?: number | null;
  docs?: { id: string; kind: "biz_license" | "bank_book" | "evidence"; name: string; size: number }[];
  created_at: string;
};
/** 입점 문의(신청 전 게이트) — 관리자 [신청 허용] 후 신청서 작성 가능 */
export type PartnerInquiry = {
  id: number; email: string; note?: string | null;
  status: "pending" | "allowed" | "dismissed";
  decide_note?: string | null; decided_at?: string | null; created_at: string;
};

/** B-10 궁합 초대 */
export type CompatTeaser = {
  grade: string; total: number; line: string;
  axes?: { key: string; label: string; score: number }[];   // 티저 그래프(페이드 가림)용 — 구초대엔 없음
};
export type CompatInviteInfo = {
  status: "pending" | "accepted" | "expired";
  inviter_name: string;
  expires_at: string;
  teaser?: CompatTeaser;
};

/** B-8 운세 캘린더 */
export type CalendarDay = {
  date: string;
  day: number;
  weekday: number;
  ganzhi: string;
  grade: "대길" | "길" | "평" | "흉";
  score: number;
  sonless: boolean;
  warnings: string[];
  jieqi: string | null;
};
export type FortuneCalendar = {
  year: number;
  month: number;
  today: string;
  user_day_branch: string;
  days: CalendarDay[];
  note: string;
  tool_id?: string;     // 해설·추가질문(공용 tools 스트림)용 세션
  is_preview?: boolean; // 비로그인 = 해설 미리보기 컷
};

/** B-2 오늘의 운세 응답 */
export type TodayFortune = {
  date: string;
  iljin: { stem: string; branch: string; label: string };
  day_master: { stem: string; ko: string };
  ten_god: { hanja: string; ko: string; line: string };
  relation: { kind: "chung" | "hap"; note: string } | null;
  lucky: { element: string; color?: string; direction?: string };
  year: { domains: { label: string; value: number }[]; seun: { stem: string; branch: string; stem_ko: string; branch_ko: string; year: number } };
  tool_id?: string;     // 해설·추가질문(공용 tools 스트림)용 세션
  is_preview?: boolean; // 비로그인 = 해설 미리보기 컷
};

export type ToolResponse = {
  tool_id: string;
  tool: "naming" | "taekil" | "sinnyeon";
  kind: string;
  result: any;
  is_preview: boolean;
  billing_mode: string;
  credits_charged: number;
  balance_after: number | null;
  explain?: string;   // 저장된 해설(재열람 get_tool) — 복원 시 즉시 표시용
  reused?: boolean;   // 24시간 내 동일 입력 재조회 → 기존 세션 반환(무과금) 안내용
};

// 택일 용도 표시 라벨 — key는 서버 전송 enum(불변), 라벨은 기존 taekil.purpose_* 카탈로그 재사용.
// getter로 두어 언어 전환 시점의 로케일 문자열을 항상 반환한다(Object.keys 등 기존 사용처 불변).
export const PURPOSE_LABELS: Record<TaekilPurpose, string> = {
  get wedding() { return i18n.t("taekil.purpose_wedding"); },
  get birth() { return i18n.t("taekil.purpose_birth"); },
  get moving() { return i18n.t("taekil.purpose_moving"); },
  get opening() { return i18n.t("taekil.purpose_opening"); },
  get contract() { return i18n.t("taekil.purpose_contract"); },
  get ceremony() { return i18n.t("taekil.purpose_ceremony"); },
  get surgery() { return i18n.t("taekil.purpose_surgery"); },
  get travel() { return i18n.t("taekil.purpose_travel"); },
  get general() { return i18n.t("taekil.purpose_general"); },
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

/** 타로 덱 재학습 상태 — 최종 학습일시·버전·패리티(학습 후 편집 발생 여부) */
export type TarotLearnStatus = {
  version: number;
  learned_at: string | null;
  changed: boolean;
  manual_done_today: boolean;
  snapshot?: string;
  mode?: string;
  skipped?: boolean;  // auto 모드에서 변경분 없음 → 학습 생략(중복 방지)
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
  // 다운로드는 인증 헤더 필요(소유 검증) → fetch+blob(직링크 401 회피).
  // ⚠️ '받기(fetch)'와 '저장(a.click)'을 분리한다(운영자 보고 버그): 클릭 핸들러 안에서
  //   await fetch(14MB, 수 초) 후 a.click() 하면 모바일의 사용자 제스처(user activation)
  //   유효시간이 지나 브라우저가 저장을 '조용히' 무시 → 성공으로 오표시됐다.
  //   완료 시점에 blob 을 미리 준비해 두고, 클릭 핸들러는 동기 saveBlobUrl 만 호출할 것.
  // onProgress: 수신 진척률(0~100) 콜백(진행바용).
  prepareVideoBlob: async (
    token: string,
    onProgress?: (pct: number) => void,
  ): Promise<string> => {
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
          onProgress(Math.min(99, Math.round((received / total) * 100)));
        }
      }
      blob = new Blob(chunks as BlobPart[], { type: r.headers.get("Content-Type") || "video/mp4" });
    } else {
      blob = await r.blob();
    }
    onProgress?.(100);
    return URL.createObjectURL(blob);   // 호출부가 saveBlobUrl 로 저장·revoke 관리
  },
  // 준비된 blob URL 을 사용자 제스처 '동기' 흐름에서 저장 — await 없음(활성화 창 안 보장).
  // revoke 는 하지 않는다(재클릭 재저장 허용). 카드 닫힘/페이지 이탈 시 브라우저가 회수.
  saveBlobUrl: (url: string, filename: string) => {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
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

  // ---- B-11 무료 스낵 테스트 ----
  snackTests: () => jfetch<{ tests: SnackTest[] }>("/snack"),
  runSnack: (testId: string, birth: Birth, makeCard = false) =>
    jfetch<SnackResult>(`/snack/${testId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...birth, make_card: makeCard }),
    }),

  // ---- B-10 궁합 초대 ----
  partnerTerms: () => jfetch<PartnerTerms>("/partner/terms"),
  // 서류 첨부 필수(사업자등록증) → multipart. FormData 라 jfetch(인증헤더·Content-Type 자동) 사용.
  partnerApply: (body: { specialty: string; business_name: string; contact?: string; intro?: string; terms_version: string; agree_key_points: boolean; biz_license: File; bank_book: File; extra_docs?: File[] }) => {
    const fd = new FormData();
    fd.set("specialty", body.specialty);
    fd.set("business_name", body.business_name);
    if (body.contact) fd.set("contact", body.contact);
    if (body.intro) fd.set("intro", body.intro);
    fd.set("terms_version", body.terms_version);
    fd.set("agree_key_points", String(body.agree_key_points));
    fd.set("biz_license", body.biz_license);
    fd.set("bank_book", body.bank_book);
    for (const f of body.extra_docs || []) fd.append("extra_docs", f);
    return jfetch<PartnerApplication>("/partner/apply", { method: "POST", body: fd });
  },
  partnerApplyMine: () =>
    jfetch<{ application: PartnerApplication | null; inquiry: PartnerInquiry | null; can_apply: boolean }>("/partner/apply/mine"),
  partnerInquiry: (note: string) =>
    jfetch<PartnerInquiry>("/partner/inquiry", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note }),
    }),
  adminPartnerInquiries: (status?: string) =>
    jfetch<{ items: PartnerInquiry[] }>(`/admin/consultants/inquiries${status ? `?status=${status}` : ""}`),
  adminPartnerInquiryAllow: (id: number) =>
    jfetch<PartnerInquiry>(`/admin/consultants/inquiries/${id}/allow`, { method: "POST" }),
  adminPartnerInquiryDismiss: (id: number, reason: string) =>
    jfetch<PartnerInquiry>(`/admin/consultants/inquiries/${id}/dismiss`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason }),
    }),
  adminPartnerApplications: (status?: string) =>
    jfetch<{ items: PartnerApplication[] }>(`/admin/consultants/applications${status ? `?status=${status}` : ""}`),
  adminPartnerApprove: (id: number) =>
    jfetch<PartnerApplication>(`/admin/consultants/applications/${id}/approve`, { method: "POST" }),
  adminPartnerReject: (id: number, reason: string) =>
    jfetch<PartnerApplication>(`/admin/consultants/applications/${id}/reject`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason }),
    }),
  // 신청 서류 열람 — 인증 헤더 필요(직링크 401) → blob 새 탭. PDF/이미지 모두 브라우저 표시.
  adminPartnerDocOpen: async (appId: number, docId: string) => {
    const r = await fetch(BASE + `/admin/consultants/applications/${appId}/docs/${docId}`, { headers: authHeaders() });
    if (!r.ok) {
      const { message, code } = await parseError(r);
      throw new ApiError(message, r.status, code);
    }
    const url = URL.createObjectURL(await r.blob());
    window.open(url, "_blank", "noopener");
    setTimeout(() => URL.revokeObjectURL(url), 60_000);   // 탭이 로드할 시간 확보 후 회수
  },
  compatInviteCreate: (body: Birth & { label?: string }) =>
    jfetch<{ token: string; url: string; expires_at: string }>("/compatibility/invites", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  compatInviteInfo: (token: string) => jfetch<CompatInviteInfo>(`/compatibility/invites/${token}`),
  compatInvitePrefill: (token: string) =>
    jfetch<{ a: Birth; b: Birth }>(`/compatibility/invites/${token}/prefill`),
  compatInviteAccept: (token: string, birth: Birth) =>
    jfetch<{ status: string; teaser: CompatTeaser }>(`/compatibility/invites/${token}/accept`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(birth),
    }),

  // ---- B-8 운세 캘린더 ----
  fortuneCalendar: (birth: Birth, year: number, month: number) =>
    jfetch<FortuneCalendar>("/saju/calendar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...birth, year, month }),
    }),

  // ---- B-7 월 패스 ----
  passInfo: () => jfetch<PassInfo>("/pass"),
  passSubscribe: (tier: "lite" | "plus") =>
    jfetch<{ mine: PassMine }>("/pass/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tier }),
    }),
  passCancel: () => jfetch<{ mine: PassMine }>("/pass/cancel", { method: "POST" }),

  // ---- B-6 공유 카드 ----
  createShareCard: (body: Birth & { kind?: "today" }) =>
    jfetch<ShareCard>("/share-card", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "today", ...body }),
    }),

  // ---- B-5 신뢰 지표 ----
  trustStats: () => jfetch<TrustStats>("/trust-stats"),

  // ---- B-4 부적 발행 ----
  issueAmulet: (body: Birth & { purpose: AmuletPurpose }) =>
    jfetch<AmuletResult>("/amulet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  // ---- B-3 이용 후기 ----
  publicReviews: (source?: ReviewSource, limit = 20) =>
    jfetch<{ items: Review[] }>(`/reviews?limit=${limit}${source ? `&source=${source}` : ""}`),
  submitReview: (body: { source: ReviewSource; content: string; rating?: number }) =>
    jfetch<Review>("/reviews", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  adminReviews: (status?: string, limit = 100, offset = 0) =>
    jfetch<{ items: Review[]; total: number }>(
      `/admin/reviews?limit=${limit}&offset=${offset}${status ? `&status=${status}` : ""}`,
    ),
  adminUpdateReview: (id: number, status: "pending" | "approved" | "rejected") =>
    jfetch<Review>(`/admin/reviews/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }),

  // ---- admin: 과금/한도 설정 + 답변양식 ----
  adminGetSettings: () => jfetch<{ settings: AppSettings }>("/admin/settings"),
  adminPatchSettings: (body: Partial<AppSettings>) =>
    jfetch<{ settings: AppSettings }>("/admin/settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  // ---- 마케팅 가격 에이전트(2026-07-13): 조사→권장→관리자 승인 클릭으로만 가격변경 ----
  adminPricingOverview: () => jfetch<PricingOverview>("/admin/pricing/overview"),
  adminPricingSurvey: () => jfetch<{ batch_id: string; pending: number; skipped: number }>("/admin/pricing/survey", { method: "POST" }),
  adminPricingUpsertCompetitor: (body: { id?: number; competitor_name: string; menu_key: string; price_krw: number; note?: string }) =>
    jfetch<CompetitorPrice>("/admin/pricing/competitors", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  adminPricingDeleteCompetitor: (id: number) =>
    jfetch<void>(`/admin/pricing/competitors/${id}`, { method: "DELETE" }),
  adminPricingUpdateGuardrail: (body: Partial<PricingGuardrail> & { menu_key: string }) =>
    jfetch<PricingGuardrail>("/admin/pricing/guardrails", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  adminPricingApply: (id: number) =>
    jfetch<PricingRecommendation>(`/admin/pricing/recommendations/${id}/apply`, { method: "POST" }),
  adminPricingDismiss: (id: number) =>
    jfetch<PricingRecommendation>(`/admin/pricing/recommendations/${id}/dismiss`, { method: "POST" }),
  adminPricingRollback: (id: number) =>
    jfetch<PricingRecommendation>(`/admin/pricing/recommendations/${id}/rollback`, { method: "POST" }),
  // 운영/법무 설정(사업자 정보·약관 버전/본문·SMTP)
  adminGetSiteSettings: () => jfetch<{ settings: SiteSettings }>("/admin/site-settings"),
  adminPatchSiteSettings: (body: Record<string, string | number | boolean>) =>
    jfetch<{ settings: SiteSettings }>("/admin/site-settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  // 저장된 SMTP로 테스트 메일 발송(설정 검증). to 없으면 관리자 본인 메일.
  adminTestEmail: (to?: string) =>
    jfetch<{ ok: boolean; detail: string; to: string }>("/admin/settings/test-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ to: to || undefined }),
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
  adminUsageSummary: () => jfetch<AdminUsageSummary>("/admin/usage-summary"),
  adminAllPayments: (limit = 20, offset = 0) =>
    jfetch<{ items: AdminPaymentRow[]; total: number; limit: number; offset: number }>(
      `/admin/payments?limit=${limit}&offset=${offset}`
    ),
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
  // 타로 덱 재학습(확정 스냅샷 버전화) — 상태 조회 + 수동 실행(1일 1회, 초과 409)
  adminTarotLearnStatus: () =>
    jfetch<TarotLearnStatus>("/admin/tarot/learn-status"),
  adminTarotRelearn: () =>
    jfetch<TarotLearnStatus>("/admin/tarot/relearn", { method: "POST" }),

  // ---- 1:1 인적 상담(입점업체) ----
  consultants: (specialty?: "saju" | "tarot") =>
    jfetch<{ items: ConsultantPublic[] }>(
      `/consultation/consultants${specialty ? `?specialty=${specialty}` : ""}`
    ),
  consultationConfig: () => jfetch<ConsultationConfig>("/consultation/config"),
  myConsultantProfile: () =>
    jfetch<{ consultant: ConsultantSelf | null }>("/consultation/consultant/me"),
  // 상담사 본인 프로필(소개·#키워드·요금·상태) 셀프 수정
  updateMyConsultant: (body: ConsultantSelfBody) =>
    jfetch<{ consultant: ConsultantSelf }>("/consultation/consultant/me", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  // 상담사 본인 간판/사진 업로드 — FormData
  uploadMyConsultantSignboard: (form: FormData) =>
    jfetch<{ consultant: ConsultantSelf }>("/consultation/consultant/me/signboard", { method: "POST", body: form }),
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
  /* ── A-2 예약 상담 ── */
  consultantSlots: () => jfetch<{ items: ConsultationSlot[] }>("/consultation/consultant/slots"),
  addConsultantSlot: (start_at: string) =>
    jfetch<ConsultationSlot>("/consultation/consultant/slots", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start_at }),
    }),
  removeConsultantSlot: (slot_id: string) =>
    jfetch<ConsultationSlot>(`/consultation/consultant/slots/${slot_id}`, { method: "DELETE" }),
  consultantOpenSlots: (consultant_id: number) =>
    jfetch<{ items: ConsultationSlot[] }>(`/consultation/consultants/${consultant_id}/slots`),
  reserveSlot: (slot_id: string, consent: boolean) =>
    jfetch<ConsultationSlot>("/consultation/reservations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot_id, consent }),
    }),
  myReservations: () => jfetch<{ items: ConsultationSlot[] }>("/consultation/reservations/mine"),
  cancelReservation: (slot_id: string) =>
    jfetch<ConsultationSlot & { refund_p: number }>(`/consultation/reservations/${slot_id}`, { method: "DELETE" }),

  requestConsultation: (consultant_id: number, consent: boolean, source?: ConsultSource | null) =>
    jfetch<ConsultationSession>("/consultation/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        consultant_id,
        consent,
        source_kind: source?.kind ?? null,
        source_ref_id: source?.refId ?? null,
      }),
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
  consultantEarnings: () =>
    jfetch<ConsultantEarnings>("/consultation/consultant/earnings"),
  setConsultantAvailability: (online: boolean) =>
    jfetch<ConsultantSelf>("/consultation/consultant/availability", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ online }),
    }),
  // 관리자 정산 실지급 뷰
  adminSettlements: (consultantId?: number, status?: string, cycle?: string) => {
    const q = [
      consultantId ? `consultant_id=${consultantId}` : "",
      status ? `status=${status}` : "",
      cycle ? `cycle=${cycle}` : "",
    ].filter(Boolean).join("&");
    return jfetch<{ items: ConsultationSettlementRow[]; totals: SettlementTotals; current_cycle: string; cycle?: string; payout_date?: string }>(
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
  /** 포인트 원장(충전·차감·환불·리워드 전부, 최신순) — '잔액은 줄었는데 쓴 기록이 없다' 오해 차단. */
  creditHistory: (limit = 100) =>
    jfetch<{ items: CreditTxn[]; summary: CreditSummary }>(`/payments/transactions?limit=${limit}`),
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
  // period_* 는 공유 주기(사용자별 30일 롤링) — '다음 초기화 날짜' 표시에 쓴다.
  // period_start 는 서버 naive UTC 이므로 파싱 시 'Z' 를 붙일 것(ShareQuotaNote 참고).
  shareQuota: () =>
    jfetch<{
      used: number; limit: number; remaining: number; unlimited: boolean;
      period_days?: number; period_start?: string | null;
    }>("/share/quota"),
  submitShare: (body: {
    channel: "kakao" | "zalo" | "email" | "link";
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

  // ---- 상담서 PDF를 서버가 메일로 첨부 발송(로그인+공유한도). SMTP 미설정 시 503 → 프론트가 mailto 폴백 ----
  emailPdf: (body: { token: string; to: string; doc_title?: string; message?: string }) =>
    jfetch<{ ok: boolean }>("/pdf/email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

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
    compat_id?: string;    // 궁합 세션 — 있으면 2인 명식 + 5요소 펜타곤 포함
    // 타로 — 뽑은 카드(이미지 그리드로 PDF에 포함, 역방향 180° 회전)
    tarot_cards?: { position_name: string; name_kr: string; name_en: string; orientation: string; image_url: string }[];
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
  // '지난 결과' 목록(로그인 필수, 무차감 재열람용)
  listCompat: () => jfetch<CompatSessionList>("/compatibility"),

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
  bulkDeleteTarot: (ids: string[]) =>
    jfetch<{ deleted: number }>(`/tarot/bulk-delete`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids }),
    }),

  // ---- 명리 도구 ----
  createNaming: (body: {
    kind: NamingKind; birth: Birth; surname?: string; current_name?: string; reading?: string;
    name_len?: 1 | 2; dollimja?: string; dollimja_pos?: "front" | "back";  // 작명: 외자/두자·돌림자 고정
  }) =>
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
  /** B-2 오늘의 운세 — 무과금·무저장 */
  todayFortune: (birth: Birth) =>
    jfetch<TodayFortune>("/saju/today", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(birth),
    }),
  createSinnyeon: (body: { birth: Birth; year?: number | null }) =>
    jfetch<ToolResponse>("/tools/sinnyeon", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  getTool: (id: string) => jfetch<ToolResponse>(`/tools/${id}`),
  // '지난 결과' 목록(로그인 필수, 무차감 재열람용). tools 로 종류 필터(sinnyeon|naming|taekil|amulet).
  listTools: (tools?: string[]) =>
    jfetch<ToolSessionList>(`/tools${tools && tools.length ? `?tools=${encodeURIComponent(tools.join(","))}` : ""}`),
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
  bulkDeleteChatSessions: (ids: string[]) =>
    jfetch<{ deleted: number }>(`/chat/sessions/bulk-delete`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids }),
    }).then((r) => { invalidateGetCache("sessions"); return r; }),
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

/** 포인트 차감/충전/환불 직후 — 서버 진실 잔액을 즉시 캐시에 반영(사이드바·충전 FAB 갱신).
 *  차감 후 화면 잔액이 안 줄어 '안 빠졌나/재차감?' 오해가 나던 문제(패턴 B) 공통 해결.
 *  실제 차감 로직은 서버가 이미 커밋했으므로 여기선 '표시'만 진실값으로 맞춘다. 실패는 무시(다음 갱신에 교정). */
export function refreshMe(): Promise<void> {
  return api.me().then((m) => { setCachedMe(m); }).catch(() => { /* 다음 갱신에 교정 */ });
}
