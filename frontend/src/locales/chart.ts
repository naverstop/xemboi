/** 명식표(SajuChart) + 명리 도감(MyeongriWheel) 문자열·독음 카탈로그 — common.chart 로 병합.
 *
 * 도메인 독음은 vi=한월음(Hán-Việt). 백엔드 saju/constants.py(STEM_VI/BRANCH_VI/WUXING_VI/
 * TEN_GODS_VI)의 정본 라틴 독음을 프론트 매핑으로 옮긴 것.
 *  - stem/branch/wuxing/tengod/zodiac: 한자(漢字) 키 → 로케일 독음. ko=한글, vi=Hán-Việt.
 *  - life/sinsal/napeum: 백엔드가 내려주는 한국어 값(십이운성·십이신살·납음 60갑자명) → 로케일 표시.
 *    (ko 는 원값 그대로, vi 는 한월음. 미매핑 값은 컴포넌트에서 원값으로 폴백.)
 *  - strength: 백엔드 enum(strong/weak/neutral). ko 는 현행 그대로(원값 노출), vi 만 한월음.
 * MyeongriWheel(mw_*)은 랜딩 히어로 도감 — 12지 아바타 이미지 파일명은 로케일 무관(한국어 파일명).
 */
export const chartKo = {
  // ── 기둥 라벨(표시용) — 백엔드 데이터 키(시/일/월/년, 시지…)는 컴포넌트에서 그대로 사용 ──
  pillar_hour: "시",
  pillar_day: "일",
  pillar_month: "월",
  pillar_year: "년",
  day_master_god: "일원",       // 일주 천간 위 표기(일간=주체)
  hour_unknown: "시 미상",

  // ── 천간·지지·오행·십성 독음 (한자 키) ──
  stem: {
    甲: "갑", 乙: "을", 丙: "병", 丁: "정", 戊: "무",
    己: "기", 庚: "경", 辛: "신", 壬: "임", 癸: "계",
  },
  branch: {
    子: "자", 丑: "축", 寅: "인", 卯: "묘", 辰: "진", 巳: "사",
    午: "오", 未: "미", 申: "신", 酉: "유", 戌: "술", 亥: "해",
  },
  wuxing: { 木: "목", 火: "화", 土: "토", 金: "금", 水: "수" },
  tengod: {
    比肩: "비견", 劫財: "겁재", 食神: "식신", 傷官: "상관", 偏財: "편재",
    正財: "정재", 偏官: "편관", 正官: "정관", 偏印: "편인", 正印: "정인",
  },
  zodiac: {
    子: "쥐", 丑: "소", 寅: "호랑이", 卯: "토끼", 辰: "용", 巳: "뱀",
    午: "말", 未: "양", 申: "원숭이", 酉: "닭", 戌: "개", 亥: "돼지",
  },

  // ── 백엔드 한국어 값 → 표시(ko 는 원값 그대로) ──
  life: {
    장생: "장생", 목욕: "목욕", 관대: "관대", 건록: "건록", 제왕: "제왕", 쇠: "쇠",
    병: "병", 사: "사", 묘: "묘", 절: "절", 태: "태", 양: "양",
  },
  sinsal: {
    겁살: "겁살", 재살: "재살", 천살: "천살", 지살: "지살", 년살: "년살", 월살: "월살",
    망신: "망신", 장성: "장성", 반안: "반안", 역마: "역마", 육해: "육해", 화개: "화개",
  },
  napeum: {
    해중금: "해중금", 노중화: "노중화", 대림목: "대림목", 노방토: "노방토", 검봉금: "검봉금",
    산두화: "산두화", 간하수: "간하수", 성두토: "성두토", 백랍금: "백랍금", 양류목: "양류목",
    천중수: "천중수", 옥상토: "옥상토", 벽력화: "벽력화", 송백목: "송백목", 장류수: "장류수",
    사중금: "사중금", 산하화: "산하화", 평지목: "평지목", 벽상토: "벽상토", 금박금: "금박금",
    복등화: "복등화", 천하수: "천하수", 대역토: "대역토", 채천금: "채천금", 상자목: "상자목",
    대계수: "대계수", 사중토: "사중토", 천상화: "천상화", 석류목: "석류목", 대해수: "대해수",
  },

  // ── 툴팁·섹션 라벨 ──
  life_tip: "십이운성",
  sinsal_tip: "십이신살",
  napeum_label: "납음(納音)",
  saryeong_label: "사령(司令)",
  gongmang_label: "공망(空亡)",

  // ── 일간 정보 줄 ──
  day_master_label: "일간",
  wuxing_label: "오행",
  strength_label: "강약",
  strength: { strong: "strong", weak: "weak", neutral: "neutral" },

  // ── 조후용신 ──
  yongsin_label: "조후용신(調候)",
  yongsin_support: "보조",
  yongsin_climate: "조후 우선",

  // ── 대운 ──
  daewoon_forward: "순행",
  daewoon_backward: "역행",
  daewoon_title: "대운 ({{dir}}, 대운수 {{age}}세)",
  dw_now: "지금",

  // ── 기질 6축·영역별 운세(SajuChart 하단 지표) ──
  trait_aria: "기질 레이더",
  metrics_traits_title: "기질 6축",
  metrics_traits_sub: "십성 분포",
  metrics_domains_title: "영역별 운세 비중",
  metrics_domains_sub: "올해 세운 반영",
  seun_label: " ({{year}} 세운 {{ganji}})",
  trust_badge: "🔒 결정적 계산",
  trust_tx: "명식·대운·조후용신을 <b>규칙으로 산출</b> — 지어내지 않아요",
  // lib/sajuMetrics.ts traits()의 key(drive…) → 표시 라벨 (trait_{key})
  trait_drive: "자기주도",
  trait_express: "표현력",
  trait_money: "재물감각",
  trait_duty: "책임감",
  trait_learn: "배움",
  trait_social: "관계유연",
  // 영역별 운세 — 백엔드 domain_scores·프론트 폴백(sajuMetrics.domains)의 한국어 라벨 키 → 표시
  domain: { 직업운: "직업운", 재물운: "재물운", 대인운: "대인운", 연애운: "연애운", 건강운: "건강운" },

  // ── 오행 균형 오각(OhaengRadar — 작명·개명) ──
  or_aria: "오행 균형 오각 차트",
  or_cur: "현재 사주",
  or_comp_default: "이름 보완 후",

  // ── 명리 도감(MyeongriWheel) ──
  mw_aria: "명리 기초 도감 — 천간과 지지",
  mw_tab_gan: "천간",
  mw_tab_ji: "지지",
  mw_yy: { yang: "양", yin: "음" },
  mw_stem_desc: {
    甲: "큰나무 · 시작",
    乙: "덩굴나무 · 유연함",
    丙: "태양 · 밝음",
    丁: "촛불 · 빛 · 정성",
    戊: "큰산 · 중심",
    己: "밭 · 토양 · 양육",
    庚: "쇠 · 강함 · 결단",
    辛: "보석 · 정밀함",
    壬: "바다 · 큰물 · 지혜",
    癸: "비 · 작은물 · 스며듦",
  },
  mw_season: {
    子: "겨울", 丑: "겨울", 寅: "봄", 卯: "봄", 辰: "봄", 巳: "여름",
    午: "여름", 未: "여름", 申: "가을", 酉: "가을", 戌: "가을", 亥: "겨울",
  },
  mw_dir: {
    子: "북", 丑: "북북동", 寅: "동북동", 卯: "동", 辰: "동남동", 巳: "남남동",
    午: "남", 未: "남남서", 申: "서남서", 酉: "서", 戌: "서북서", 亥: "북북서",
  },
  mw_time: {
    子: "23~01시", 丑: "01~03시", 寅: "03~05시", 卯: "05~07시", 辰: "07~09시", 巳: "09~11시",
    午: "11~13시", 未: "13~15시", 申: "15~17시", 酉: "17~19시", 戌: "19~21시", 亥: "21~23시",
  },
  // 12지 아바타 이미지 src(한국어 파일명) — 로케일 무관, ko/vi 동일.
  mw_img: {
    子: "/zodiac/쥐_청년.jpg", 丑: "/zodiac/소_청년.jpg", 寅: "/zodiac/호랑이_청년.jpg",
    卯: "/zodiac/토끼_청년.jpg", 辰: "/zodiac/용_청년.jpg", 巳: "/zodiac/뱀_청년.jpg",
    午: "/zodiac/말_청년.jpg", 未: "/zodiac/양_청년.jpg", 申: "/zodiac/원숭이_청년.jpg",
    酉: "/zodiac/닭_청년.jpg", 戌: "/zodiac/개_청년.jpg", 亥: "/zodiac/돼지_청년.jpg",
  },
  mw_hub_stem_name: "{{yy}}의 {{el}}",   // 예: 양의 목
  mw_hub_zodiac: "{{animal}}띠",          // 예: 쥐띠
  mw_legend_gan: "상생 <b>목→화→토→금→수→목</b> · 상극 <b>목↘토↘수↘화↘금↘목</b>",
  mw_legend_ji: "지지는 시간·방향·계절·띠 동물로 이어져요 — 눌러서 살펴보세요",
};

export const chartVi: typeof chartKo = {
  pillar_hour: "Giờ",
  pillar_day: "Ngày",
  pillar_month: "Tháng",
  pillar_year: "Năm",
  day_master_god: "Nhật nguyên",
  hour_unknown: "Không rõ giờ",

  stem: {
    甲: "Giáp", 乙: "Ất", 丙: "Bính", 丁: "Đinh", 戊: "Mậu",
    己: "Kỷ", 庚: "Canh", 辛: "Tân", 壬: "Nhâm", 癸: "Quý",
  },
  branch: {
    子: "Tý", 丑: "Sửu", 寅: "Dần", 卯: "Mão", 辰: "Thìn", 巳: "Tỵ",
    午: "Ngọ", 未: "Mùi", 申: "Thân", 酉: "Dậu", 戌: "Tuất", 亥: "Hợi",
  },
  wuxing: { 木: "Mộc", 火: "Hỏa", 土: "Thổ", 金: "Kim", 水: "Thủy" },
  tengod: {
    比肩: "Tỷ kiên", 劫財: "Kiếp tài", 食神: "Thực thần", 傷官: "Thương quan", 偏財: "Thiên tài",
    正財: "Chính tài", 偏官: "Thiên quan", 正官: "Chính quan", 偏印: "Thiên ấn", 正印: "Chính ấn",
  },
  // 十二生肖(베트남): 丑=Trâu(물소)·卯=Mèo(고양이)·未=Dê(염소) — 한국과 갈림.
  zodiac: {
    子: "Chuột", 丑: "Trâu", 寅: "Hổ", 卯: "Mèo", 辰: "Rồng", 巳: "Rắn",
    午: "Ngựa", 未: "Dê", 申: "Khỉ", 酉: "Gà", 戌: "Chó", 亥: "Lợn",
  },

  life: {
    장생: "Trường sinh", 목욕: "Mộc dục", 관대: "Quan đới", 건록: "Kiến lộc", 제왕: "Đế vượng", 쇠: "Suy",
    병: "Bệnh", 사: "Tử", 묘: "Mộ", 절: "Tuyệt", 태: "Thai", 양: "Dưỡng",
  },
  sinsal: {
    겁살: "Kiếp sát", 재살: "Tai sát", 천살: "Thiên sát", 지살: "Địa sát", 년살: "Niên sát", 월살: "Nguyệt sát",
    망신: "Vong thần", 장성: "Tướng tinh", 반안: "Phàn yên", 역마: "Dịch mã", 육해: "Lục hại", 화개: "Hoa cái",
  },
  napeum: {
    해중금: "Hải trung kim", 노중화: "Lô trung hỏa", 대림목: "Đại lâm mộc", 노방토: "Lộ bàng thổ", 검봉금: "Kiếm phong kim",
    산두화: "Sơn đầu hỏa", 간하수: "Giản hạ thủy", 성두토: "Thành đầu thổ", 백랍금: "Bạch lạp kim", 양류목: "Dương liễu mộc",
    천중수: "Tuyền trung thủy", 옥상토: "Ốc thượng thổ", 벽력화: "Tích lịch hỏa", 송백목: "Tùng bách mộc", 장류수: "Trường lưu thủy",
    사중금: "Sa trung kim", 산하화: "Sơn hạ hỏa", 평지목: "Bình địa mộc", 벽상토: "Bích thượng thổ", 금박금: "Kim bạc kim",
    복등화: "Phú đăng hỏa", 천하수: "Thiên hà thủy", 대역토: "Đại dịch thổ", 채천금: "Thoa xuyến kim", 상자목: "Tang chá mộc",
    대계수: "Đại khê thủy", 사중토: "Sa trung thổ", 천상화: "Thiên thượng hỏa", 석류목: "Thạch lựu mộc", 대해수: "Đại hải thủy",
  },

  life_tip: "Thập nhị trường sinh",
  sinsal_tip: "Thập nhị thần sát",
  napeum_label: "Nạp âm",
  saryeong_label: "Tư lệnh",
  gongmang_label: "Không vong",

  day_master_label: "Nhật nguyên",
  wuxing_label: "Ngũ hành",
  strength_label: "Cường nhược",
  strength: { strong: "Thân vượng", weak: "Thân nhược", neutral: "Trung hòa" },

  yongsin_label: "Điều hậu dụng thần",
  yongsin_support: "Phụ trợ",
  yongsin_climate: "Ưu tiên điều hậu",

  daewoon_forward: "Thuận",
  daewoon_backward: "Nghịch",
  daewoon_title: "Đại vận ({{dir}}, khởi vận {{age}} tuổi)",
  dw_now: "Hiện tại",

  trait_aria: "Radar khí chất",
  metrics_traits_title: "6 trục khí chất",
  metrics_traits_sub: "Phân bố thập thần",
  metrics_domains_title: "Tỷ trọng vận trình theo lĩnh vực",
  metrics_domains_sub: "Đã tính Tuế vận năm nay",
  seun_label: " ({{year}} Tuế vận {{ganji}})",
  trust_badge: "🔒 Tính toán xác định",
  trust_tx: "Lá số·Đại vận·Điều hậu dụng thần <b>tính theo quy tắc</b> — không bịa ra",
  trait_drive: "Tự chủ",
  trait_express: "Biểu đạt",
  trait_money: "Nhạy tài lộc",
  trait_duty: "Trách nhiệm",
  trait_learn: "Học hỏi",
  trait_social: "Khéo quan hệ",
  domain: { 직업운: "Vận sự nghiệp", 재물운: "Vận tiền tài", 대인운: "Vận quan hệ", 연애운: "Vận tình duyên", 건강운: "Vận sức khỏe" },

  or_aria: "Biểu đồ ngũ giác cân bằng ngũ hành",
  or_cur: "Lá số hiện tại",
  or_comp_default: "Sau khi bổ khuyết bằng tên",

  mw_aria: "Cẩm nang mệnh lý cơ bản — Thiên can và Địa chi",
  mw_tab_gan: "Thiên can",
  mw_tab_ji: "Địa chi",
  mw_yy: { yang: "Dương", yin: "Âm" },
  mw_stem_desc: {
    甲: "Cây lớn · Khởi đầu",
    乙: "Cây dây leo · Mềm dẻo",
    丙: "Mặt trời · Rực rỡ",
    丁: "Ngọn nến · Ánh sáng · Tận tâm",
    戊: "Núi lớn · Trung tâm",
    己: "Ruộng đất · Nuôi dưỡng",
    庚: "Kim loại · Mạnh mẽ · Quyết đoán",
    辛: "Ngọc quý · Tinh xảo",
    壬: "Biển cả · Nước lớn · Trí tuệ",
    癸: "Mưa · Nước nhỏ · Thấm nhuần",
  },
  mw_season: {
    子: "Mùa đông", 丑: "Mùa đông", 寅: "Mùa xuân", 卯: "Mùa xuân", 辰: "Mùa xuân", 巳: "Mùa hè",
    午: "Mùa hè", 未: "Mùa hè", 申: "Mùa thu", 酉: "Mùa thu", 戌: "Mùa thu", 亥: "Mùa đông",
  },
  mw_dir: {
    子: "Bắc", 丑: "Bắc đông bắc", 寅: "Đông đông bắc", 卯: "Đông", 辰: "Đông đông nam", 巳: "Nam đông nam",
    午: "Nam", 未: "Nam tây nam", 申: "Tây tây nam", 酉: "Tây", 戌: "Tây tây bắc", 亥: "Bắc tây bắc",
  },
  mw_time: {
    子: "23–01h", 丑: "01–03h", 寅: "03–05h", 卯: "05–07h", 辰: "07–09h", 巳: "09–11h",
    午: "11–13h", 未: "13–15h", 申: "15–17h", 酉: "17–19h", 戌: "19–21h", 亥: "21–23h",
  },
  mw_img: {
    子: "/zodiac/쥐_청년.jpg", 丑: "/zodiac/물소_청년.jpg", 寅: "/zodiac/호랑이_청년.jpg",
    卯: "/zodiac/고양이_청년.jpg", 辰: "/zodiac/용_청년.jpg", 巳: "/zodiac/뱀_청년.jpg",
    午: "/zodiac/말_청년.jpg", 未: "/zodiac/양_청년.jpg", 申: "/zodiac/원숭이_청년.jpg",
    酉: "/zodiac/닭_청년.jpg", 戌: "/zodiac/개_청년.jpg", 亥: "/zodiac/돼지_청년.jpg",
  },
  mw_hub_stem_name: "{{el}} {{yy}}",     // 예: Mộc Dương
  mw_hub_zodiac: "tuổi {{animal}}",       // 예: tuổi Chuột
  mw_legend_gan: "Tương sinh <b>Mộc→Hỏa→Thổ→Kim→Thủy→Mộc</b> · Tương khắc <b>Mộc↘Thổ↘Thủy↘Hỏa↘Kim↘Mộc</b>",
  mw_legend_ji: "Địa chi nối theo giờ · phương hướng · mùa · con giáp — nhấn để xem",
};
