// 공용 시각 포맷터 — 항상 한국시간(KST, Asia/Seoul)으로 표시.
//
// 백엔드는 시각을 UTC(datetime.utcnow)로 저장하고 tz 표기 없는 ISO 로 응답한다.
// 그대로 new Date()/문자열 slice 로 찍으면 (a)9시간 빠른 UTC 가 보이거나
// (b)보는 사람 브라우저 타임존에 따라 달라진다. 어느 지역에서 접속하든 한국시간으로
// 통일하기 위해 'UTC 로 명시 → Asia/Seoul 로 변환'한다.

const KST = "Asia/Seoul";

function toUtcDate(iso?: string | null): Date | null {
  if (!iso) return null;
  const hasTz = /[zZ]$|[+-]\d\d:?\d\d$/.test(iso);
  const d = new Date(hasTz ? iso : iso + "Z");
  return isNaN(d.getTime()) ? null : d;
}

/** "YYYY-MM-DD HH:mm:ss" (KST). 파싱 불가 시 원본 반환. */
export function fmtKSTDateTime(iso?: string | null): string {
  const d = toUtcDate(iso);
  if (!d) return iso ?? "";
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: KST, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(d).replace(",", "");
}

/** "YYYY-MM-DD" (KST). */
export function fmtKSTDate(iso?: string | null): string {
  const d = toUtcDate(iso);
  if (!d) return iso ?? "";
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: KST, year: "numeric", month: "2-digit", day: "2-digit",
  }).format(d);
}

/** "M/D HH:mm" (KST) — 좁은 영역용 짧은 표기. */
export function fmtKSTShort(iso?: string | null): string {
  const d = toUtcDate(iso);
  if (!d) return iso ?? "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: KST, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(d);
  const g = (t: string) => parts.find((x) => x.type === t)?.value ?? "";
  return `${Number(g("month"))}/${Number(g("day"))} ${g("hour")}:${g("minute")}`;
}
