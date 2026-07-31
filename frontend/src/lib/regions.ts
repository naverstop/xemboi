/** 출생지(시·도 → 시·군·구) 경도 데이터 — 진태양시 보정용.
 *
 * 경도(°E)는 각 시·군·구 중심 근사값. 진태양시 보정은 (135 − 경도)×4분으로 시각을 당기므로
 * 0.1° 차이는 약 0.4분 → '시(時)' 경계에서만 의미. 시·군·구 단위면 충분히 정밀하다.
 * 한 곳(AdvancedBirthSettings)에서만 쓰여 전 메뉴 입력화면에 공통 반영된다.
 */
export type Gun = { name: string; lon: number };
export type Sido = { name: string; short: string; guns: Gun[] };

export const DEFAULT_LON = 126.98; // 서울 종로 기준(미선택 시)

export const KR_REGIONS: Sido[] = [
  { name: "서울특별시", short: "서울", guns: [
    { name: "종로구", lon: 126.98 }, { name: "중구", lon: 127.0 }, { name: "용산구", lon: 126.99 },
    { name: "성동구", lon: 127.04 }, { name: "광진구", lon: 127.08 }, { name: "동대문구", lon: 127.04 },
    { name: "중랑구", lon: 127.09 }, { name: "성북구", lon: 127.02 }, { name: "강북구", lon: 127.03 },
    { name: "도봉구", lon: 127.05 }, { name: "노원구", lon: 127.08 }, { name: "은평구", lon: 126.93 },
    { name: "서대문구", lon: 126.94 }, { name: "마포구", lon: 126.91 }, { name: "양천구", lon: 126.87 },
    { name: "강서구", lon: 126.82 }, { name: "구로구", lon: 126.89 }, { name: "금천구", lon: 126.9 },
    { name: "영등포구", lon: 126.9 }, { name: "동작구", lon: 126.94 }, { name: "관악구", lon: 126.95 },
    { name: "서초구", lon: 127.03 }, { name: "강남구", lon: 127.05 }, { name: "송파구", lon: 127.11 },
    { name: "강동구", lon: 127.12 },
  ] },
  { name: "부산광역시", short: "부산", guns: [
    { name: "중구", lon: 129.03 }, { name: "서구", lon: 129.02 }, { name: "동구", lon: 129.05 },
    { name: "영도구", lon: 129.07 }, { name: "부산진구", lon: 129.05 }, { name: "동래구", lon: 129.08 },
    { name: "남구", lon: 129.08 }, { name: "북구", lon: 128.99 }, { name: "해운대구", lon: 129.16 },
    { name: "사하구", lon: 128.97 }, { name: "금정구", lon: 129.09 }, { name: "강서구", lon: 128.83 },
    { name: "연제구", lon: 129.08 }, { name: "수영구", lon: 129.11 }, { name: "사상구", lon: 128.99 },
    { name: "기장군", lon: 129.22 },
  ] },
  { name: "대구광역시", short: "대구", guns: [
    { name: "중구", lon: 128.59 }, { name: "동구", lon: 128.63 }, { name: "서구", lon: 128.55 },
    { name: "남구", lon: 128.59 }, { name: "북구", lon: 128.58 }, { name: "수성구", lon: 128.63 },
    { name: "달서구", lon: 128.53 }, { name: "달성군", lon: 128.43 }, { name: "군위군", lon: 128.57 },
  ] },
  { name: "인천광역시", short: "인천", guns: [
    { name: "중구", lon: 126.62 }, { name: "동구", lon: 126.64 }, { name: "미추홀구", lon: 126.65 },
    { name: "연수구", lon: 126.68 }, { name: "남동구", lon: 126.74 }, { name: "부평구", lon: 126.72 },
    { name: "계양구", lon: 126.73 }, { name: "서구", lon: 126.68 }, { name: "강화군", lon: 126.49 },
    { name: "옹진군", lon: 126.64 },
  ] },
  { name: "광주광역시", short: "광주", guns: [
    { name: "동구", lon: 126.92 }, { name: "서구", lon: 126.89 }, { name: "남구", lon: 126.9 },
    { name: "북구", lon: 126.91 }, { name: "광산구", lon: 126.79 },
  ] },
  { name: "대전광역시", short: "대전", guns: [
    { name: "동구", lon: 127.45 }, { name: "중구", lon: 127.42 }, { name: "서구", lon: 127.38 },
    { name: "유성구", lon: 127.34 }, { name: "대덕구", lon: 127.42 },
  ] },
  { name: "울산광역시", short: "울산", guns: [
    { name: "중구", lon: 129.33 }, { name: "남구", lon: 129.33 }, { name: "동구", lon: 129.42 },
    { name: "북구", lon: 129.36 }, { name: "울주군", lon: 129.16 },
  ] },
  { name: "세종특별자치시", short: "세종", guns: [{ name: "세종시", lon: 127.29 }] },
  { name: "경기도", short: "경기", guns: [
    { name: "수원시", lon: 127.03 }, { name: "성남시", lon: 127.14 }, { name: "고양시", lon: 126.83 },
    { name: "용인시", lon: 127.18 }, { name: "부천시", lon: 126.78 }, { name: "안산시", lon: 126.83 },
    { name: "안양시", lon: 126.95 }, { name: "남양주시", lon: 127.22 }, { name: "화성시", lon: 126.83 },
    { name: "평택시", lon: 127.11 }, { name: "의정부시", lon: 127.05 }, { name: "시흥시", lon: 126.8 },
    { name: "파주시", lon: 126.78 }, { name: "김포시", lon: 126.72 }, { name: "광명시", lon: 126.86 },
    { name: "광주시", lon: 127.26 }, { name: "군포시", lon: 126.94 }, { name: "하남시", lon: 127.21 },
    { name: "오산시", lon: 127.08 }, { name: "이천시", lon: 127.44 }, { name: "양주시", lon: 127.05 },
    { name: "구리시", lon: 127.13 }, { name: "안성시", lon: 127.28 }, { name: "포천시", lon: 127.2 },
    { name: "의왕시", lon: 126.97 }, { name: "여주시", lon: 127.64 }, { name: "양평군", lon: 127.49 },
    { name: "동두천시", lon: 127.06 }, { name: "과천시", lon: 126.99 }, { name: "가평군", lon: 127.51 },
    { name: "연천군", lon: 127.07 },
  ] },
  { name: "강원특별자치도", short: "강원", guns: [
    { name: "춘천시", lon: 127.73 }, { name: "원주시", lon: 127.92 }, { name: "강릉시", lon: 128.9 },
    { name: "동해시", lon: 129.11 }, { name: "태백시", lon: 128.99 }, { name: "속초시", lon: 128.59 },
    { name: "삼척시", lon: 129.17 }, { name: "홍천군", lon: 127.89 }, { name: "횡성군", lon: 127.99 },
    { name: "영월군", lon: 128.46 }, { name: "평창군", lon: 128.39 }, { name: "정선군", lon: 128.66 },
    { name: "철원군", lon: 127.31 }, { name: "화천군", lon: 127.71 }, { name: "양구군", lon: 127.99 },
    { name: "인제군", lon: 128.17 }, { name: "고성군", lon: 128.47 }, { name: "양양군", lon: 128.62 },
  ] },
  { name: "충청북도", short: "충북", guns: [
    { name: "청주시", lon: 127.49 }, { name: "충주시", lon: 127.93 }, { name: "제천시", lon: 128.19 },
    { name: "보은군", lon: 127.73 }, { name: "옥천군", lon: 127.57 }, { name: "영동군", lon: 127.78 },
    { name: "증평군", lon: 127.58 }, { name: "진천군", lon: 127.44 }, { name: "괴산군", lon: 127.79 },
    { name: "음성군", lon: 127.69 }, { name: "단양군", lon: 128.37 },
  ] },
  { name: "충청남도", short: "충남", guns: [
    { name: "천안시", lon: 127.11 }, { name: "공주시", lon: 127.12 }, { name: "보령시", lon: 126.61 },
    { name: "아산시", lon: 127.0 }, { name: "서산시", lon: 126.45 }, { name: "논산시", lon: 127.1 },
    { name: "계룡시", lon: 127.25 }, { name: "당진시", lon: 126.65 }, { name: "금산군", lon: 127.49 },
    { name: "부여군", lon: 126.91 }, { name: "서천군", lon: 126.69 }, { name: "청양군", lon: 126.8 },
    { name: "홍성군", lon: 126.66 }, { name: "예산군", lon: 126.84 }, { name: "태안군", lon: 126.3 },
  ] },
  { name: "전북특별자치도", short: "전북", guns: [
    { name: "전주시", lon: 127.15 }, { name: "군산시", lon: 126.74 }, { name: "익산시", lon: 126.96 },
    { name: "정읍시", lon: 126.86 }, { name: "남원시", lon: 127.39 }, { name: "김제시", lon: 126.88 },
    { name: "완주군", lon: 127.16 }, { name: "진안군", lon: 127.42 }, { name: "무주군", lon: 127.66 },
    { name: "장수군", lon: 127.52 }, { name: "임실군", lon: 127.29 }, { name: "순창군", lon: 127.14 },
    { name: "고창군", lon: 126.7 }, { name: "부안군", lon: 126.73 },
  ] },
  { name: "전라남도", short: "전남", guns: [
    { name: "목포시", lon: 126.39 }, { name: "여수시", lon: 127.66 }, { name: "순천시", lon: 127.49 },
    { name: "나주시", lon: 126.71 }, { name: "광양시", lon: 127.7 }, { name: "담양군", lon: 126.99 },
    { name: "곡성군", lon: 127.29 }, { name: "구례군", lon: 127.46 }, { name: "고흥군", lon: 127.28 },
    { name: "보성군", lon: 127.08 }, { name: "화순군", lon: 126.99 }, { name: "장흥군", lon: 126.91 },
    { name: "강진군", lon: 126.77 }, { name: "해남군", lon: 126.6 }, { name: "영암군", lon: 126.7 },
    { name: "무안군", lon: 126.48 }, { name: "함평군", lon: 126.52 }, { name: "영광군", lon: 126.51 },
    { name: "장성군", lon: 126.78 }, { name: "완도군", lon: 126.75 }, { name: "진도군", lon: 126.26 },
    { name: "신안군", lon: 126.1 },
  ] },
  { name: "경상북도", short: "경북", guns: [
    { name: "포항시", lon: 129.36 }, { name: "경주시", lon: 129.22 }, { name: "김천시", lon: 128.11 },
    { name: "안동시", lon: 128.73 }, { name: "구미시", lon: 128.34 }, { name: "영주시", lon: 128.62 },
    { name: "영천시", lon: 128.94 }, { name: "상주시", lon: 128.16 }, { name: "문경시", lon: 128.19 },
    { name: "경산시", lon: 128.74 }, { name: "의성군", lon: 128.7 }, { name: "청송군", lon: 129.06 },
    { name: "영양군", lon: 129.11 }, { name: "영덕군", lon: 129.37 }, { name: "청도군", lon: 128.73 },
    { name: "고령군", lon: 128.26 }, { name: "성주군", lon: 128.28 }, { name: "칠곡군", lon: 128.4 },
    { name: "예천군", lon: 128.45 }, { name: "봉화군", lon: 128.73 }, { name: "울진군", lon: 129.4 },
    { name: "울릉군", lon: 130.91 },
  ] },
  { name: "경상남도", short: "경남", guns: [
    { name: "창원시", lon: 128.68 }, { name: "진주시", lon: 128.11 }, { name: "통영시", lon: 128.43 },
    { name: "사천시", lon: 128.06 }, { name: "김해시", lon: 128.89 }, { name: "밀양시", lon: 128.75 },
    { name: "거제시", lon: 128.62 }, { name: "양산시", lon: 129.04 }, { name: "의령군", lon: 128.26 },
    { name: "함안군", lon: 128.41 }, { name: "창녕군", lon: 128.49 }, { name: "고성군", lon: 128.32 },
    { name: "남해군", lon: 127.89 }, { name: "하동군", lon: 127.75 }, { name: "산청군", lon: 127.87 },
    { name: "함양군", lon: 127.73 }, { name: "거창군", lon: 127.91 }, { name: "합천군", lon: 128.17 },
  ] },
  { name: "제주특별자치도", short: "제주", guns: [
    { name: "제주시", lon: 126.53 }, { name: "서귀포시", lon: 126.56 },
  ] },
];

/** 시·도 이름 → Sido */
export function sidoByName(name: string): Sido | undefined {
  return KR_REGIONS.find((s) => s.name === name);
}

/** 경도로 가장 가까운 (시·도, 시·군·구) 역추적 — 저장된 birth_longitude로 드롭다운 복원용 */
export function nearestRegion(lon: number | null | undefined): { sido: string; gun: string } {
  const target = lon ?? DEFAULT_LON;
  let best = { sido: "서울특별시", gun: "종로구" };
  let bestD = Infinity;
  for (const s of KR_REGIONS) {
    for (const g of s.guns) {
      const d = Math.abs(g.lon - target);
      if (d < bestD) { bestD = d; best = { sido: s.name, gun: g.name }; }
    }
  }
  return best;
}
