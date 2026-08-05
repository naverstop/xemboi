/** B-2 오늘의 운세 — 무료·무저장. 오늘 일진 × 내 일간의 십성/충합(결정적) + 올해 배경.
 * 데일리 푸시(08:00) 클릭 랜딩. 저장된 본인 사주가 있으면 자동 조회. */
import { useEffect, useRef, useState } from "react";
import { api, useMe, type Birth, type TodayFortune, type ShareCard } from "../api";
import PrivacyNotice from "../components/PrivacyNotice";
import { resolveBirthTime } from "../lib/birthTime";
import BirthFields, { type BirthValue } from "../components/BirthFields";
import RememberBirthToggle, { useBirthMemory } from "../components/RememberBirth";
import AnswerActions from "../components/AnswerActions";
import ExplainChat from "../components/ExplainChat";
import { displayName } from "../lib/displayName";
import { kakaoAvailable, shareKakaoLink } from "../lib/kakaoShare";
import { canNativeFileShare } from "../lib/webShare";
import DownloadGuard from "../components/DownloadGuard";
import ShareQuotaNote from "../components/ShareQuotaNote";
import { Link } from "react-router-dom";
import { useTranslation, Trans } from "react-i18next";
import i18n from "../i18n";

function fmtToday(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return i18n.t("today.date_fmt", { m: d.getMonth() + 1, d: d.getDate(), w: i18n.t("today.weekdays").split(",")[d.getDay()] });
}

// 결과를 복사/공유/PDF용 plain text로 직렬화(공용 액션바 규약)
function todayText(res: TodayFortune): string {
  const lines = [
    i18n.t("today.txt_title", { date: fmtToday(res.date), iljin: res.iljin.label }),
    i18n.t("today.txt_energy", { tg: res.ten_god.ko, hanja: res.ten_god.hanja, dm: res.day_master.ko, stem: res.day_master.stem }),
    res.ten_god.line,
  ];
  if (res.relation) lines.push(`${res.relation.kind === "chung" ? "⚠️" : "🤝"} ${res.relation.note}`);
  lines.push(i18n.t("today.txt_lucky", { color: res.lucky.color, dir: res.lucky.direction, elem: res.lucky.element }));
  if (res.year?.domains?.length) {
    lines.push("\n" + i18n.t("today.txt_year_head", { year: res.year.seun.year, gz: `${res.year.seun.stem_ko}${res.year.seun.branch_ko}` }));
    res.year.domains.forEach((d) => lines.push(`- ${d.label} ${d.value}`));
  }
  return lines.join("\n");
}

export default function TodayPage() {
  const { t: tr } = useTranslation();
  const [b, setB] = useState<BirthValue>({ birth_date: "", birth_time: "", unknown_time: false, gender: "male", calendar: "solar", is_leap_month: false, apply_true_solar_time: true, birth_longitude: 126.98 });
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<TodayFortune | null>(null);

  const me = useMe();
  const autoRan = useRef(false);

  // B-6 공유 카드
  const [card, setCard] = useState<ShareCard | null>(null);
  const [cardBusy, setCardBusy] = useState(false);
  const shareLock = useRef(false);   // 공유 버튼 동기 연타 잠금(state 로는 같은 틱 연타를 못 막음)
  const [cardHint, setCardHint] = useState("");   // 공유 결과 토스트(.share-hint) — alert 대체
  const who = displayName(me);   // ⚠️ 호칭=이메일 아이디 고정(운영자 결정) — lib/displayName.ts

  async function makeCard() {
    if (cardBusy || !b.birth_date) return;
    setCardBusy(true);
    try {
      const birth: Birth = {
        birth_date: b.birth_date, birth_time: resolveBirthTime(b.birth_time, b.unknown_time),
        calendar: b.calendar, gender: b.gender, is_leap_month: b.calendar === "lunar" ? b.is_leap_month : false,
        apply_true_solar_time: !!b.apply_true_solar_time, night_zi_mode: b.night_zi_mode ?? "yaja",
        birth_longitude: b.birth_longitude ?? null, apply_equation_of_time: !!b.apply_equation_of_time,
      };
      setCard(await api.createShareCard(birth));
    } catch (e: any) {
      setErr(e?.message || tr("today.card_fail"));
    } finally {
      setCardBusy(false);
    }
  }

  // [운영자 지적 #21] 오늘의 운세 결과가 나오면 공유카드를 자동 생성해 바로 노출(버튼 클릭 불필요).
  //   서버 이미지 렌더(LLM 아님)라 부하 낮고, 공유 한도는 실제 '공유(submitShare)' 시에만 차감돼
  //   자동 생성엔 과금 영향 없음. res 객체 1회당 1번만(재생성 폭주 방지) — 재실행(새 운세)이면 재생성.
  const cardAutoFor = useRef<TodayFortune | null>(null);
  useEffect(() => {
    if (!res || cardAutoFor.current === res) return;
    cardAutoFor.current = res;
    setCard(null);              // 새 운세면 이전 카드 치우고 로더 노출
    if (b.birth_date) makeCard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [res]);

  // 공용 공유 규약(AnswerActions 와 동일, 2026-07-23 재설계):
  //   **사전 확인 → 공유 → 성공 시에만 집계**. 예전엔 모바일이 '공유 후 집계'라 한도를 못 막았고,
  //   데스크톱은 '집계 후 공유'라 복사 실패 시 횟수만 날아갔다.
  //   판정은 ApiError.code 기준 — 한국어 문구 부분일치는 카피 수정 한 번에 무증상 fail-open 됐다.
  function gateOf(e: any): "quota" | "login" | "other" {
    const code = String(e?.code || "");
    if (code === "share_quota_exceeded") return "quota";
    if (code === "login required to share" || e?.status === 401) return "login";
    return "other";
  }

  async function canShareNow(): Promise<boolean> {
    try {
      const q = await api.shareQuota();
      if (!q.unlimited && q.remaining <= 0) {
        alert(tr("today.share_quota_alert"));
        return false;
      }
      return true;
    } catch (e: any) {
      if (gateOf(e) === "login") { alert(tr("today.share_login_alert")); return false; }
      return true;   // 그 외 장애는 공유를 막지 않는다(가용성 우선)
    }
  }

  async function countShare(channel: "kakao" | "link"): Promise<void> {
    try {
      await api.submitShare({ channel });
      window.dispatchEvent(new Event("saju:share-counted"));   // 잔여 배지 즉시 갱신
    } catch { /* 이미 나간 공유는 되돌릴 수 없다 */ }
  }

  function toast(msg: string) {
    setCardHint(msg);
    window.setTimeout(() => setCardHint(""), 4000);
  }

  // 카드 공유 — ①(모바일 Android/iOS 한정) 파일 첨부 → ②(데스크톱) 카카오 링크카드 → ③링크 복사.
  //  집계·토스트는 공용 규약. ⚠️ canShare 기능감지만으로 분기 금지(Windows 공유창 멈춤 — lib/webShare.ts).
  async function shareCard() {
    if (!card) return;
    if (shareLock.current) return;      // 동기 연타 잠금 — 없을 땐 더블클릭 1번에 2회 차감됐다
    shareLock.current = true;
    try {
      if (!(await canShareNow())) return;   // ⚠️ 반드시 공유 '앞'에서 — 뒤면 이미 나간 뒤라 못 막는다
      const absUrl = window.location.origin + card.url;
      try {
        const blob = await fetch(card.url).then((r) => r.blob());
        const file = new File([blob], card.filename || tr("today.card_filename"), { type: "image/png" });
        const nav: any = navigator;
        if (canNativeFileShare([file])) {
          try {
            await nav.share({ files: [file], title: tr("today.share_title") });
            await countShare("link");   // 성공 확정 후 1회 집계(취소 시 미집계)
          } catch (e: any) {
            if (e?.name !== "AbortError") toast(tr("today.share_fail_toast"));
          }
          return;
        }
      } catch { /* 폴백 진행 */ }
      if (kakaoAvailable()) {
        const sent = await shareKakaoLink({
          title: tr("today.share_title"), description: tr("today.share_desc"),
          url: absUrl, imageUrl: absUrl,
        });
        if (sent) { await countShare("kakao"); return; }
        /* 카카오 실패 → 링크 복사 폴백 */
      }
      try {
        await navigator.clipboard.writeText(absUrl);
        await countShare("link");       // 복사 성공이 확인된 뒤에만 집계
        toast(tr("today.link_copied"));
      } catch {
        // 복사 실패 — 아무것도 나가지 않았으므로 차감하지 않는다(예전엔 차감만 되고 안내도 없었다).
        toast(tr("today.longpress_save"));
      }
    } finally {
      shareLock.current = false;
    }
  }

  // scroll=false: '기억하기' 자동조회(진입 즉시) — 결과로 스크롤하면 화면이 중간부터 보인다(운영자 지적).
  //               사용자가 직접 누른 조회만 결과로 스크롤(캘린더와 동일 규약).
  async function run(bv: BirthValue, scroll = true) {
    setErr(null); setLoading(true);
    const birth: Birth = {
      birth_date: bv.birth_date, birth_time: resolveBirthTime(bv.birth_time, bv.unknown_time),
      calendar: bv.calendar, gender: bv.gender, is_leap_month: bv.calendar === "lunar" ? bv.is_leap_month : false,
      apply_true_solar_time: !!bv.apply_true_solar_time, night_zi_mode: bv.night_zi_mode ?? "yaja",
      birth_longitude: bv.birth_longitude ?? null, apply_equation_of_time: !!bv.apply_equation_of_time,
    };
    try {
      setRes(await api.todayFortune(birth));
      if (scroll) setTimeout(() => document.getElementById("tool-result")?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
    } catch (e: any) {
      setErr(e?.message || tr("today.load_fail"));
    } finally { setLoading(false); }
  }

  // 공통 '기억하기' — 저장본(회원 프로필/비회원 LS) 자동 채움 + 최초 1회 자동 조회(푸시 랜딩 UX)
  const { remember, toggleRemember } = useBirthMemory(
    b, (patch) => setB((prev) => ({ ...prev, ...patch })),
    { onPrefill: (patch) => { if (!autoRan.current) { autoRan.current = true; run({ ...b, ...patch }, false); } } },
  );

  return (
    <div className="compat-page">
      <PrivacyNotice variant="tool" />
      <header className="compat-hero">
        <div className="compat-hero-badge">{tr("today.hero_badge")}</div>
        <h1>{tr("today.hero_title")}</h1>
        <p><Trans i18nKey="today.hero_desc" components={{ b: <b /> }} /></p>
      </header>

      <div className="tool-form">
        <RememberBirthToggle remember={remember} onToggle={toggleRemember} />
        <BirthFields value={b} onChange={(patch) => setB((prev) => ({ ...prev, ...patch }))} remembered={remember} />
      </div>

      <div className="compat-actions">
        <button className="compat-cta" disabled={!b.birth_date || loading} onClick={() => run(b)}>
          {loading ? tr("today.loading") : tr("today.cta")}
        </button>
        {!b.birth_date && <div className="cta-hint">{tr("today.cta_hint")}</div>}
      </div>
      {err && <div className="compat-err">{err}</div>}

      {res && (
        <div id="tool-result" className="compat-result">
          <div className="cr-headline">
            <span className="cr-names">{fmtToday(res.date)}</span>
            <span className="cr-grade" style={{ background: "var(--brand-grad)" }}>{tr("today.iljin_badge", { label: res.iljin.label })}</span>
          </div>

          {/* 오늘의 핵심 — 십성 기운 */}
          <div className="td-main">
            <div className="td-tengod">
              <span className="big">{res.ten_god.ko}</span>
              <span className="hj">({res.ten_god.hanja})</span>
              <span className="sub">{tr("today.tengod_sub", { dm: res.day_master.ko, stem: res.day_master.stem })}</span>
            </div>
            <p className="td-line">{res.ten_god.line}</p>
            {res.relation && (
              <p className={`td-rel ${res.relation.kind}`}>{res.relation.kind === "chung" ? "⚠️" : "🤝"} {res.relation.note}</p>
            )}
          </div>

          {/* 행운 요소 */}
          <div className="td-lucky">
            <span className="td-chip">{tr("today.lucky_color")} <b>{res.lucky.color}</b></span>
            <span className="td-chip">{tr("today.lucky_dir")} <b>{res.lucky.direction}</b></span>
            <span className="td-chip">{tr("today.lucky_elem")} <b>{res.lucky.element}</b></span>
          </div>

          {/* 올해 배경(연 단위) */}
          {res.year?.domains?.length > 0 && (
            <>
              <div className="cr-sub">{tr("today.year_head", { year: res.year.seun.year })} <span>{tr("today.year_head_sub", { gz: `${res.year.seun.stem_ko}${res.year.seun.branch_ko}` })}</span></div>
              <div className="sy-domains">
                {res.year.domains.map((d) => (
                  <div key={d.label} className="sy-domain">
                    <span className="lb">{d.label}</span>
                    <span className="bar"><span className="fill" style={{ width: `${Math.max(4, Math.min(100, d.value))}%` }} /></span>
                    <span className="val">{d.value}</span>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* 공용 액션바 — 텍스트복사·공유(카카오/메일/링크/PDF)·PDF (6메뉴 표준. 무저장이라 피드백은 자동 미노출) */}
          <AnswerActions
            text={todayText(res)}
            source="tool"
            pdf={{
              docTitle: tr("today.pdf_doc", { who }),
              personLine: tr("today.pdf_person", { who }),
              item: tr("today.pdf_item", { date: fmtToday(res.date) }),
            }}
          />

          {/* B-6 공유 카드(V5) — 날짜 박힌 스토리 규격 이미지. 운세 결과와 함께 자동 생성·노출(#21).
              생성 중=로더 / 완료=카드+공유·저장 / (자동 생성 실패 시에만) 만들기 버튼 폴백. */}
          <div className="td-share">
            {card ? (
              <div className="td-card-box">
                <img src={card.url} alt={tr("today.card_alt")} />
                <div className="td-card-actions">
                  <span className="share-wrap">
                    <button onClick={shareCard}>{tr("today.share_btn")}</button>
                    {cardHint && <span className="share-hint" role="status">{cardHint}</span>}
                  </span>
                  <DownloadGuard href={card.download_url} doneLabel={tr("today.save_done")}>{tr("today.save_btn")}</DownloadGuard>
                </div>
                <ShareQuotaNote className="share-quota-note inline" />
              </div>
            ) : cardBusy ? (
              <div className="td-share-loading" role="status">{tr("today.card_making")}</div>
            ) : (
              <button className="td-share-btn" onClick={makeCard}>{tr("today.card_make_btn")}</button>
            )}
          </div>

          {/* 해설(무과금)·추가질문(기존 정책: 기본 1,000P/심화 3,000P, 부족 시 충전유도) — 공용 tools 스트림 */}
          {res.tool_id && (
            <ExplainChat
              streamPath={`/api/tools/${res.tool_id}/messages/stream`}
              isPreview={!!res.is_preview}
              autoStart={false}
              pdf={{
                docTitle: tr("today.pdf_doc", { who }),
                personLine: tr("today.pdf_person", { who }),
                item: tr("today.pdf_item", { date: fmtToday(res.date) }),
              }}
              pdfHeader={todayText(res)}
              feedbackSource="tool"
              feedbackSessionId={res.tool_id}
              suggestFetch={() => api.getToolSuggestions(res.tool_id!).then((r) => r.suggestions || [])}
            />
          )}

          <p className="td-note"><Trans i18nKey="today.note" components={{ chat: <Link to="/chat" /> }} /></p>
        </div>
      )}
    </div>
  );
}
