/** 통화·숫자 표시 공용 포매터.
 * - VN 빌드(xemboi)=VND(đ) / 그 외(사주1 ko)=원(KRW).
 * - 포인트(P/điểm) 등 순수 숫자는 fmtNum, 결제 금액은 통화단위 포함 fmtMoney.
 * - 통화는 서비스 기준(VN=VND)이라 표시언어(ko/vi)와 무관하게 빌드로 고정한다.
 */
import { IS_VN_BUILD } from "../i18n";

const LOC = IS_VN_BUILD ? "vi-VN" : "ko-KR";

/** 천단위 구분 숫자(로케일). 포인트 수량 등에 사용. */
export function fmtNum(n: number): string {
  return n.toLocaleString(LOC);
}

/** 결제 금액 표시(통화단위 포함). VN=`50.000 đ` / ko=`50,000원`. */
export function fmtMoney(n: number): string {
  return IS_VN_BUILD ? `${n.toLocaleString(LOC)} đ` : `${n.toLocaleString(LOC)}원`;
}
