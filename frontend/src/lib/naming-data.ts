// 작명 친화 데이터: 한글 성씨→대표 한자, 영문 뜻→한글 키워드.

// 한국 주요 성씨 (한글 → 대표 한자). "기타"는 직접 한자 입력.
export const SURNAMES: { ko: string; han: string }[] = [
  { ko: "김", han: "金" }, { ko: "이", han: "李" }, { ko: "박", han: "朴" },
  { ko: "최", han: "崔" }, { ko: "정", han: "鄭" }, { ko: "강", han: "姜" },
  { ko: "조", han: "趙" }, { ko: "윤", han: "尹" }, { ko: "장", han: "張" },
  { ko: "임", han: "林" }, { ko: "오", han: "吳" }, { ko: "한", han: "韓" },
  { ko: "신", han: "申" }, { ko: "서", han: "徐" }, { ko: "권", han: "權" },
  { ko: "황", han: "黃" }, { ko: "안", han: "安" }, { ko: "송", han: "宋" },
  { ko: "전", han: "全" }, { ko: "홍", han: "洪" }, { ko: "유", han: "柳" },
  { ko: "고", han: "高" }, { ko: "문", han: "文" }, { ko: "양", han: "梁" },
  { ko: "손", han: "孫" }, { ko: "배", han: "裵" }, { ko: "백", han: "白" },
  { ko: "허", han: "許" }, { ko: "남", han: "南" }, { ko: "심", han: "沈" },
  { ko: "하", han: "河" }, { ko: "곽", han: "郭" }, { ko: "성", han: "成" },
  { ko: "차", han: "車" }, { ko: "주", han: "朱" }, { ko: "우", han: "禹" },
  { ko: "구", han: "具" }, { ko: "나", han: "羅" }, { ko: "민", han: "閔" },
  { ko: "진", han: "陳" }, { ko: "지", han: "池" }, { ko: "엄", han: "嚴" },
  { ko: "채", han: "蔡" }, { ko: "원", han: "元" }, { ko: "천", han: "千" },
  { ko: "방", han: "方" }, { ko: "공", han: "孔" }, { ko: "현", han: "玄" },
  { ko: "함", han: "咸" }, { ko: "변", han: "卞" }, { ko: "노", han: "盧" },
  { ko: "여", han: "呂" }, { ko: "추", han: "秋" }, { ko: "도", han: "都" },
  { ko: "석", han: "石" }, { ko: "설", han: "薛" }, { ko: "선", han: "宣" },
  { ko: "마", han: "馬" }, { ko: "길", han: "吉" }, { ko: "위", han: "魏" },
  { ko: "표", han: "表" }, { ko: "명", han: "明" }, { ko: "기", han: "奇" },
  { ko: "왕", han: "王" }, { ko: "반", han: "潘" }, { ko: "옥", han: "玉" },
  { ko: "육", han: "陸" }, { ko: "인", han: "印" }, { ko: "맹", han: "孟" },
];

// 영문 뜻 키워드 → 한글. Unihan kDefinition 한글화(표시용 근사).
const EN_KO: [string, string][] = [
  ["bright", "밝음"], ["clear", "맑음"], ["beautiful", "아름다움"], ["beauty", "아름다움"],
  ["wise", "지혜"], ["wisdom", "지혜"], ["virtue", "덕"], ["virtuous", "덕"],
  ["noble", "고귀함"], ["talent", "재능"], ["elegant", "우아함"], ["graceful", "우아함"],
  ["grace", "우아함"], ["auspicious", "길함"], ["lucky", "행운"], ["prosper", "번영"],
  ["abundant", "풍요"], ["gem", "보배"], ["jade", "옥"], ["pure", "순수함"],
  ["gentle", "온화함"], ["brave", "용감함"], ["strong", "강건함"], ["great", "위대함"],
  ["flourish", "번성"], ["luxuriant", "무성함"], ["shine", "빛남"], ["shining", "빛남"],
  ["light", "빛"], ["good", "선함"], ["joy", "기쁨"], ["happy", "행복"],
  ["peace", "평화"], ["peaceful", "평화"], ["grow", "성장"], ["rise", "상승"],
  ["rising", "상승"], ["honor", "명예"], ["refined", "세련됨"], ["excellent", "탁월함"],
  ["harmony", "조화"], ["harmonious", "조화"], ["fragrant", "향기"], ["hero", "영웅"],
  ["flower", "꽃"], ["spring", "봄"], ["river", "강"], ["mountain", "산"],
  ["sun", "해"], ["moon", "달"], ["star", "별"], ["gold", "금"],
  ["autumn", "가을"], ["morning", "아침"], ["cloud", "구름"], ["sea", "바다"],
  ["ocean", "바다"], ["forest", "숲"], ["tree", "나무"], ["grain", "곡식"],
  ["scholar", "학자"], ["learn", "배움"], ["write", "글"], ["literature", "문학"],
  ["benevolent", "어짊"], ["kind", "어짊"], ["faith", "신의"], ["sincere", "성실"],
  ["eternal", "영원"], ["long", "장구함"], ["high", "높음"], ["deep", "깊음"],
  ["wide", "넓음"], ["heaven", "하늘"], ["sky", "하늘"], ["dragon", "용"],
  ["phoenix", "봉황"], ["spirit", "정신"], ["heart", "마음"], ["mind", "마음"],
  ["dream", "꿈"], ["hope", "희망"], ["bloom", "피어남"], ["fruit", "결실"],
  ["jewel", "보석"], ["pearl", "진주"], ["snow", "눈"], ["rain", "비"],
  ["wind", "바람"], ["water", "물"], ["fire", "불"], ["earth", "땅"],
  ["bird", "새"], ["crane", "학"], ["pine", "소나무"], ["bamboo", "대나무"],
  ["orchid", "난초"], ["plum", "매화"], ["fragrance", "향기"], ["warm", "따뜻함"],
  ["calm", "고요함"], ["quiet", "고요함"], ["truth", "진실"], ["jade-like", "옥같음"],
];

/** 영문 뜻 → 한글 키워드 요약(최대 3개). 매칭 없으면 빈 문자열. */
export function glossKo(meaning: string): string {
  if (!meaning) return "";
  const low = meaning.toLowerCase();
  const found: string[] = [];
  for (const [en, ko] of EN_KO) {
    if (low.includes(en) && !found.includes(ko)) found.push(ko);
    if (found.length >= 3) break;
  }
  return found.join("·");
}
