/** 사업자(통신판매업자) 신원정보 — 전자상거래법 제13조 의무표시.
 *
 *  이 시스템은 이관(판매) 대비 ENV 오버라이딩 방식이므로, 운영자는 빌드 전
 *  프론트엔드 .env 에 VITE_BIZ_* 값을 채워 배포한다. 미입력 항목은 화면에
 *  "(운영자 설정 전)" 으로 표기되어, 상용 오픈 전 반드시 채워야 함을 드러낸다.
 *
 *  예) .env
 *    VITE_SERVICE_NAME="인생상담 친구"
 *    VITE_BIZ_NAME="○○○ 사주연구소"
 *    VITE_BIZ_CEO="홍길동"
 *    VITE_BIZ_REG_NO="123-45-67890"
 *    VITE_BIZ_MAILORDER_NO="2026-서울강남-01234"
 *    VITE_BIZ_ADDRESS="서울특별시 …"
 *    VITE_BIZ_TEL="02-000-0000"
 *    VITE_BIZ_EMAIL="help@example.com"
 *    VITE_BIZ_PRIVACY_OFFICER="홍길동"
 *    VITE_BIZ_HOSTING="○○클라우드(주)"
 */
import i18n from "../i18n";

const _env = import.meta.env as Record<string, string | undefined>;
const _v = (key: string, fallback = ""): string => (_env[key]?.trim() || fallback);

export const COMPANY = {
  serviceName: _v("VITE_SERVICE_NAME", "Xem Bói"),
  bizName: _v("VITE_BIZ_NAME"),                       // 상호
  ceo: _v("VITE_BIZ_CEO"),                            // 대표자 성명
  regNo: _v("VITE_BIZ_REG_NO"),                       // 사업자등록번호
  mailOrderNo: _v("VITE_BIZ_MAILORDER_NO"),           // 통신판매업 신고번호
  address: _v("VITE_BIZ_ADDRESS"),                    // 사업장 소재지
  tel: _v("VITE_BIZ_TEL"),                            // 고객센터 전화
  email: _v("VITE_BIZ_EMAIL", "orion0321@gmail.com"), // 고객문의·개인정보 이메일
  privacyOfficer: _v("VITE_BIZ_PRIVACY_OFFICER"),     // 개인정보 보호책임자
  hosting: _v("VITE_BIZ_HOSTING"),                    // 호스팅 제공자
};

export const PLACEHOLDER = "(운영자 설정 전)";

/** 값이 있으면 그대로, 없으면 로케일 미설정 표기. 운영자가 채우면 자동 반영된다. */
export function show(val: string): string {
  return val && val.length > 0 ? val : i18n.t("misc.biz_unset");
}
