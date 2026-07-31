/** 법적 고지 문서 4종 — 이용약관 / 개인정보처리방침 / 환불정책 / 면책고지.
 *
 *  - 전자상거래 등에서의 소비자보호에 관한 법률(전자상거래법), 개인정보 보호법,
 *    정보통신망법(광고성 정보)을 기준으로 본 서비스(유료 AI 사주 상담)의 실제
 *    과금·데이터·외부전송 구조를 반영해 구체화했다.
 *  - 사업자(통신판매업자) 신원정보는 ENV(VITE_BIZ_*) 로 주입한다([[company]]).
 *  - 버전 문자열·최소가입연령은 백엔드 설정(/api/auth/legal)에서 가져온다.
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type LegalInfo } from "../api";
import { COMPANY, show } from "../lib/company";
import { renderRich } from "../lib/format";

type LegalKind = "terms" | "privacy" | "refund" | "disclaimer";

// 표시에 쓰는 사업자 정보 — 관리자 입력값(API) 우선, 없으면 ENV(company.ts), 그래도 없으면 빈값.
type Co = typeof COMPANY;
function buildCompany(info: LegalInfo | null): Co {
  const b = info?.business;
  const pick = (apiVal: string | undefined, envVal: string) => ((apiVal || "").trim() || envVal);
  return {
    serviceName: (info?.service_name || "").trim() || COMPANY.serviceName,
    bizName: pick(b?.name, COMPANY.bizName),
    ceo: pick(b?.ceo, COMPANY.ceo),
    regNo: pick(b?.reg_no, COMPANY.regNo),
    mailOrderNo: pick(b?.mailorder_no, COMPANY.mailOrderNo),
    address: pick(b?.address, COMPANY.address),
    tel: pick(b?.tel, COMPANY.tel),
    email: pick(b?.email, COMPANY.email),
    privacyOfficer: pick(b?.privacy_officer, COMPANY.privacyOfficer),
    hosting: pick(b?.hosting, COMPANY.hosting),
  };
}

const TITLE: Record<LegalKind, string> = {
  terms: "이용약관",
  privacy: "개인정보처리방침",
  refund: "환불·청약철회 정책",
  disclaimer: "면책고지",
};

const OTHER: { kind: LegalKind; to: string }[] = [
  { kind: "terms", to: "/legal/terms" },
  { kind: "privacy", to: "/legal/privacy" },
  { kind: "refund", to: "/legal/refund" },
  { kind: "disclaimer", to: "/legal/disclaimer" },
];

type Versions = { terms: string; privacy: string; refund: string; min_age: number };

// ───────────────────────── 사업자 정보 표 (전자상거래법 §13) ─────────────────────────
function BizTable({ co }: { co: Co }) {
  const rows: [string, string][] = [
    ["상호(서비스명)", `${show(co.bizName)} (${co.serviceName})`],
    ["대표자", show(co.ceo)],
    ["사업자등록번호", show(co.regNo)],
    ["통신판매업 신고번호", show(co.mailOrderNo)],
    ["사업장 소재지", show(co.address)],
    ["고객센터", show(co.tel)],
    ["전자우편", co.email],
    ["호스팅 제공자", show(co.hosting)],
  ];
  return (
    <table className="legal-biz">
      <tbody>
        {rows.map(([k, v]) => (
          <tr key={k}>
            <th>{k}</th>
            <td>{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ───────────────────────── 이용약관 ─────────────────────────
function Terms({ v, co }: { v: Versions; co: Co }) {
  return (
    <>
      <p className="legal-lead">
        본 약관은 {co.serviceName}(이하 “서비스”)의 이용 조건과 절차, 운영자(이하 “회사”)와
        회원의 권리·의무 및 책임 사항을 규정합니다.
      </p>

      <h2>제1조 (사업자 정보)</h2>
      <BizTable co={co} />
      <p className="legal-note">
        ※ 위 정보는 전자상거래 등에서의 소비자보호에 관한 법률 제13조에 따른 표시 사항입니다.
        상용 서비스 개시 전 사업자등록 및 통신판매업 신고를 완료하고 위 항목을 채워야 합니다.
      </p>

      <h2>제2조 (서비스의 성격)</h2>
      <ol>
        <li>본 서비스는 중국·일본·한국의 명리학(사주팔자) 고전 자료를 검색·정리한 AI가 사주 명식을
          계산하고 풀이를 제공하는 <b>정보 제공 및 오락 목적</b>의 상담 도구입니다.</li>
        <li>본 서비스의 응답은 <b>참고용</b>이며, 의료·법률·세무·투자·심리치료 등 전문 자문이 아닙니다.
          (자세한 내용은 <Link to="/legal/disclaimer">면책고지</Link>)</li>
        <li>회사는 특정 종교·신앙을 강제하지 않습니다.</li>
      </ol>

      <h2>제3조 (회원 가입 및 이용 자격)</h2>
      <ol>
        <li>만 {v.min_age}세 이상인 사람만 회원으로 가입할 수 있으며, 가입 시 본 약관·개인정보처리방침·
          환불정책에 동의해야 합니다.</li>
        <li>타인의 명의·정보를 도용하거나 허위 정보를 기재한 경우 이용이 제한될 수 있습니다.</li>
        <li>이메일 가입 외에 카카오·구글 소셜 로그인으로 가입·이용할 수 있습니다.</li>
      </ol>

      <h2>제4조 (포인트·요금 및 결제)</h2>
      <ol>
        <li><b>1포인트(P) = 1원</b> 기준이며, 포인트는 토스페이먼츠를 통해 충전합니다.
          충전 패키지는 1만·3만·5만·10만 원 및 연간회원권(12만 원)으로 구성됩니다.</li>
        <li>회원 가입 시 <b>가입 보너스 1,000P</b>를 1회 지급합니다. 보너스·무료 제공 포인트는
          환불 대상이 아닙니다.</li>
        <li>질문(상담) 1건의 기본 단가, 미리보기 전체보기(약 500P), 프리미엄 메뉴(궁합·택일·작명·개명·아호)
          입장료는 운영 정책에 따라 달라질 수 있으며, <b>결제·차감 전 화면에 실제 금액을 표시</b>합니다.</li>
        <li>비로그인 이용자에게는 답변의 약 50%만 미리보기로 제공되며, 전체 보기는 로그인 후
          무료 질문 또는 포인트 차감으로 이용합니다.</li>
        <li><b>연간회원</b>은 결제일로부터 약 1년(보너스 1개월 포함) 동안 정해진 한도(연 1,000회) 내에서
          무과금으로 이용하며, 한도 소진 또는 기간 만료 시 일반 과금으로 전환됩니다.</li>
        <li>결제·환불의 세부 사항은 <Link to="/legal/refund">환불·청약철회 정책</Link>에 따릅니다.</li>
      </ol>

      <h2>제5조 (회원의 의무)</h2>
      <ol>
        <li>회원은 계정 정보를 안전하게 관리할 책임이 있으며, 계정 공유·양도·매매를 할 수 없습니다.</li>
        <li>서비스의 정상 운영을 방해하는 행위(자동화 수집, 비정상 대량 요청, 역공학 등)를 해서는 안 됩니다.</li>
        <li>생성된 답변을 타인에게 단정적 예언·전문 자문인 것처럼 오인하게 사용해서는 안 됩니다.</li>
      </ol>

      <h2>제6조 (서비스의 변경·중단)</h2>
      <p>회사는 운영·기술상의 필요에 따라 서비스의 전부 또는 일부를 변경·중단할 수 있으며,
        중대한 변경은 사전에 공지합니다. 무료로 제공되던 기능은 사전 공지 후 유료로 전환되거나
        종료될 수 있습니다.</p>

      <h2>제7조 (지식재산권)</h2>
      <p>서비스 및 그 구성요소(소프트웨어·디자인·DB)에 대한 권리는 회사에 있습니다. 회원이 입력한
        내용에 대한 권리는 회원에게 있으며, 회사는 서비스 제공·품질 개선 범위에서 이를 이용합니다.</p>

      <h2>제8조 (책임의 한계)</h2>
      <ol>
        <li>본 서비스의 응답은 학습 자료에 근거한 참고 정보로, 사실과 다를 수 있습니다. 회사는 응답에
          기반한 회원의 의사결정 결과에 대해 책임지지 않습니다.</li>
        <li>천재지변, 외부 AI·결제·통신 사업자의 장애 등 회사의 합리적 통제를 벗어난 사유로 인한
          손해에 대해 회사는 책임을 지지 않습니다.</li>
      </ol>

      <h2>제9조 (분쟁 해결 및 준거법)</h2>
      <p>본 약관은 대한민국 법령에 따르며, 분쟁은 회사와 회원의 협의로 해결하되 합의가 어려운 경우
        전자상거래법 등 관련 법령 및 관할 법원에 따릅니다. 소비자분쟁은 한국소비자원·전자거래분쟁조정위원회
        등의 조정을 신청할 수 있습니다.</p>

      <p className="legal-eff">시행일: {v.terms} · 본 약관 변경 시 시행 7일 전(회원에게 불리한 변경은 30일 전) 공지합니다.</p>
    </>
  );
}

// ───────────────────────── 개인정보처리방침 ─────────────────────────
function Privacy({ v, co }: { v: Versions; co: Co }) {
  return (
    <>
      <p className="legal-lead">
        회사는 개인정보 보호법 등 관련 법령을 준수하며, 다음과 같이 개인정보를 처리합니다.
        (본 방침은 회원가입·로그인 화면 및 본 페이지에서 상시 확인할 수 있습니다.)
      </p>

      <h2>1. 수집하는 개인정보 항목</h2>
      <table className="legal-grid">
        <thead><tr><th>구분</th><th>항목</th></tr></thead>
        <tbody>
          <tr><td>회원가입(필수)</td><td>이메일, 비밀번호(암호화 저장), 생년월일(만 {v.min_age}세 확인·암호화 저장)</td></tr>
          <tr><td>회원가입(선택)</td><td>닉네임, 마케팅 수신 동의 여부, 답변 말투(사투리) 설정</td></tr>
          <tr><td>소셜 로그인</td><td>카카오·구글이 제공하는 회원식별자 및 이메일(이용자가 선택한 경우)</td></tr>
          <tr><td>서비스 이용 중 생성</td><td>사주 입력값(생년월일시·성별·양/음력·출생지 경도 등), 상담(대화) 내용, 사주 프로필, 포인트·결제 내역</td></tr>
          <tr><td>결제</td><td>결제수단·승인 정보(토스페이먼츠가 처리, 회사는 카드번호 등 원문을 보관하지 않음)</td></tr>
          <tr><td>자동 수집</td><td>접속 IP, 기기·브라우저 정보, 쿠키, 서비스 이용·접속 기록</td></tr>
        </tbody>
      </table>

      <h2>2. 수집·이용 목적</h2>
      <ul>
        <li>회원 식별·인증, 만 {v.min_age}세 이상 가입 자격 확인</li>
        <li>사주 명식 계산 및 상담 답변 제공(생년월일시 등)</li>
        <li>포인트 충전·차감, 결제·환불 처리 및 부정거래 방지</li>
        <li>고객 문의 대응, 서비스 품질·정확도 개선</li>
        <li>법령상 의무 이행 및 분쟁 대응</li>
        <li>(선택 동의 시) 이벤트·혜택 등 광고성 정보 발송</li>
      </ul>

      <h2>3. 보유 및 이용 기간</h2>
      <table className="legal-grid">
        <thead><tr><th>대상</th><th>기간</th></tr></thead>
        <tbody>
          <tr><td>회원 정보·상담 내용·사주 프로필</td><td>회원 탈퇴 시 지체 없이 파기(아래 법정 보존 항목 제외)</td></tr>
          <tr><td>계약·청약철회·대금결제·재화공급 기록</td><td>5년 (전자상거래법)</td></tr>
          <tr><td>소비자 불만·분쟁처리 기록</td><td>3년 (전자상거래법)</td></tr>
          <tr><td>표시·광고 기록</td><td>6개월 (전자상거래법)</td></tr>
          <tr><td>로그인 등 접속 기록</td><td>3개월 (통신비밀보호법)</td></tr>
        </tbody>
      </table>

      <h2>4. 처리위탁 및 제3자 제공</h2>
      <ul>
        <li><b>결제 처리</b> — 토스페이먼츠(주): 결제·환불 승인·정산</li>
        <li><b>소셜 로그인</b> — 카카오·구글: 이용자가 선택한 경우 인증</li>
        <li><b>인프라/호스팅</b> — {show(co.hosting)}: 서비스 서버 운영</li>
        <li>그 밖에 법령에 근거하거나 이용자가 동의한 경우에 한해 제공하며, 위탁 사항이 변경되면
          본 방침을 통해 공지합니다.</li>
      </ul>

      <h2>5. 개인정보의 국외 처리(외부 AI)</h2>
      <p>‘심화’ 풀이 등 일부 기능에서는 답변 품질 향상을 위해 사주 <b>명식 계산값과 질문 텍스트</b>가
        외부 AI 서비스(예: Anthropic, 미국)로 전송·처리될 수 있습니다. 이때 이름·연락처 등 직접
        식별정보는 전송하지 않습니다. 민감정보(건강·정치·종교 등)나 타인의 식별정보는 대화에 입력하지
        않도록 권고하며, 외부 전송을 원치 않으면 ‘기본’ 모드로 이용할 수 있습니다.</p>

      <h2>6. 만 14세 미만 아동</h2>
      <p>본 서비스는 만 {v.min_age}세 이상만 가입할 수 있어 만 14세 미만 아동의 개인정보를 수집하지
        않습니다. 아동 명의로 가입이 확인되면 해당 계정과 정보를 지체 없이 파기합니다.</p>

      <h2>7. 정보주체의 권리</h2>
      <p>이용자는 언제든지 개인정보 열람·정정·삭제·처리정지 및 동의 철회를 요청할 수 있습니다. 설정
        화면에서 정보를 수정하거나 회원 탈퇴할 수 있으며, 탈퇴 시 법정 보존 항목을 제외한 모든
        개인정보가 지체 없이 삭제됩니다.</p>

      <h2>8. 안전성 확보 조치</h2>
      <ul>
        <li>비밀번호 단방향 해시(bcrypt) 저장 — 평문 미보관</li>
        <li>생년월일 등 민감 식별정보 AES-256-GCM 암호화 저장</li>
        <li>전 구간 HTTPS 전송, DB 접근권한 분리·최소화, 접속기록 보관</li>
      </ul>

      <h2>9. 개인정보 보호책임자</h2>
      <table className="legal-biz">
        <tbody>
          <tr><th>보호책임자</th><td>{show(co.privacyOfficer)}</td></tr>
          <tr><th>문의</th><td>{co.email}</td></tr>
        </tbody>
      </table>
      <p className="legal-note">권익 침해 상담: 개인정보분쟁조정위원회(1833-6972), 개인정보침해신고센터(118),
        대검찰청 사이버수사과(1301), 경찰청 사이버수사국(182)</p>

      <p className="legal-eff">시행일: {v.privacy} · 내용 변경 시 시행 7일 전 공지합니다.</p>
    </>
  );
}

// ───────────────────────── 환불·청약철회 정책 ─────────────────────────
function Refund({ v, co }: { v: Versions; co: Co }) {
  return (
    <>
      <p className="legal-lead">
        본 정책은 전자상거래 등에서의 소비자보호에 관한 법률에 따른 청약철회 및 환불 기준을 정합니다.
        충전 포인트는 가분적(나누어 사용 가능한) 디지털콘텐츠에 해당합니다.
      </p>

      <h2>1. 청약철회(환불) 기준</h2>
      <ul>
        <li><b>미사용 포인트</b>: 충전(결제)일로부터 <b>7일 이내</b>이고 한 번도 사용하지 않았다면
          <b> 전액 환불</b>됩니다.</li>
        <li><b>일부 사용한 경우</b>: 이미 사용(질문·풀이 제공 완료)한 포인트는 콘텐츠 제공이 개시된
          부분으로 보아 청약철회가 제한되며, <b>남은 미사용 포인트</b>는 환불 가능합니다.</li>
        <li><b>가입 보너스·무료 제공·이벤트 적립 포인트</b>는 환불 대상이 아닙니다.</li>
        <li>표시·광고 내용과 다르거나 계약과 다르게 이행된 경우에는 사용 여부와 무관하게 환불 또는
          정상 이행을 요청할 수 있습니다.</li>
      </ul>

      <h2>2. 연간회원권 환불</h2>
      <ul>
        <li>이용 개시 전 또는 결제 후 7일 이내 미이용 시 전액 환불됩니다.</li>
        <li>이용을 개시한 경우, 결제금액에서 이미 이용한 분(이용 횟수·경과 기간 등 합리적 기준으로
          산정)과 환불 수수료를 공제한 잔액을 환불합니다.</li>
      </ul>

      <h2>3. 환불 신청·처리</h2>
      <ul>
        <li>신청: 충전/결제 내역 화면 또는 고객센터({co.email})로 요청해 주세요.</li>
        <li>처리: 청약철회를 접수한 날부터 <b>영업일 기준 3일 이내</b> 동일 결제수단으로 환급합니다.
          (결제수단 사정상 즉시 취소가 어려우면 별도 절차로 환급)</li>
      </ul>

      <h2>4. 환불 제한</h2>
      <ul>
        <li>이미 사용(제공 완료)된 포인트·질문</li>
        <li>충전일로부터 7일이 지난 미사용 포인트의 단순 변심(단, 회사 정책상 유효기간 내 사용은 가능)</li>
        <li>약관·법령 위반으로 이용이 제한된 경우(다만 결제 직후 미사용분은 환불)</li>
      </ul>

      <h2>5. 분쟁 해결</h2>
      <p>환불 분쟁은 한국소비자원·전자거래분쟁조정위원회의 분쟁조정 절차를 이용할 수 있습니다.</p>

      <p className="legal-eff">시행일: {v.refund}</p>
    </>
  );
}

// ───────────────────────── 면책고지 ─────────────────────────
function Disclaimer({ co }: { co: Co }) {
  return (
    <>
      <p className="legal-lead">
        {co.serviceName}은 명리학(사주팔자) 고전 자료를 검색·정리하여 정보 제공과 대화를
        보조하는 AI 도구입니다. 이용 전 아래 내용을 확인해 주세요.
      </p>
      <ul className="legal-disc">
        <li>본 서비스의 응답은 학습 자료에 근거한 <b>참고용 정보</b>일 뿐, 미래에 대한 단정적 예측이나
          운명의 확정이 아닙니다.</li>
        <li>본 서비스는 <b>의료·법률·세무·투자·심리치료 등 전문 자문을 대체하지 않습니다.</b> 건강·재산·
          법률 등 중요한 결정에는 반드시 해당 분야 전문가의 의견을 구하시기 바랍니다.</li>
        <li>AI 답변은 학습 데이터의 한계로 <b>사실과 다르거나 부정확할 수 있습니다.</b></li>
        <li>본 서비스를 신앙으로 강제하거나 타인에게 강요하는 용도로 사용하지 마세요.</li>
        <li>본 서비스의 답변에 의존하여 행한 의사결정의 결과에 대해 회사는 책임을 지지 않습니다.</li>
      </ul>
      <p className="legal-note">본 서비스 응답은 학습 자료 기반 참고용입니다. 의료·법률·투자 자문이 아닙니다.</p>
    </>
  );
}

export default function LegalPage({ kind }: { kind: LegalKind }) {
  const [info, setInfo] = useState<LegalInfo | null>(null);
  useEffect(() => {
    api.legalVersions().then(setInfo).catch(() => setInfo(null));
  }, []);

  const co = useMemo(() => buildCompany(info), [info]);
  const v: Versions = {
    terms: info?.terms || "-",
    privacy: info?.privacy || "-",
    refund: info?.refund || "-",
    min_age: info?.min_age_years ?? 19,
  };
  // 관리자가 입력한 본문 덮어쓰기(Markdown). 비어 있으면 기본 구조화 문안 사용.
  const override = (info?.bodies?.[kind] || "").trim();

  return (
    <div className="legal-doc">
      <header className="legal-head">
        <h1>{TITLE[kind]}</h1>
        <div className="legal-meta">{co.serviceName}</div>
      </header>

      <article className="legal-body">
        {override ? (
          <div style={{ whiteSpace: "pre-wrap" }}>{renderRich(override)}</div>
        ) : (
          <>
            {kind === "terms" && <Terms v={v} co={co} />}
            {kind === "privacy" && <Privacy v={v} co={co} />}
            {kind === "refund" && <Refund v={v} co={co} />}
            {kind === "disclaimer" && <Disclaimer co={co} />}
          </>
        )}
      </article>

      <nav className="legal-nav">
        <span>관련 문서</span>
        {OTHER.filter((o) => o.kind !== kind).map((o) => (
          <Link key={o.kind} to={o.to}>{TITLE[o.kind]}</Link>
        ))}
      </nav>
    </div>
  );
}
