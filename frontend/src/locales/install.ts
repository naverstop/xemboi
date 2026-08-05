/** InstallPrompt(PWA 설치가이드) 문자열 카탈로그 — common.install 로 병합(ns "install").
 * ko 값은 기존 하드코딩 문구 그대로(한국 서비스 불변), vi 는 베트남어(브랜드=Xem Bói·인앱 예시=Zalo).
 * 자동 팝업(제목·나중에·설치·확인·본문)은 misc.pwa_* 기존 키 재사용(여기 미포함).
 * {{name}}=인앱 브라우저 표시명(lib/inapp), {{browser}}=Chrome/Safari(기기별 — 값 자체는 로케일 중립).
 */
export const installKo = {
  // ── 인앱 브라우저 자동 경고(경고→동의→외부 브라우저 탈출) ──
  warn_title: "📲 앱 설치 안내",
  warn_body: "<b>⚠️ 지금은 {{name}} 안의 브라우저예요.</b><br/>여기서는 <b>앱 설치(홈 화면 추가)가 안 돼요.</b> {{browser}}에서 열면 바로 설치할 수 있어요.",
  warn_open: "🧭 {{browser}}에서 열기 (동의)",
  warn_note: "버튼을 누르면 {{browser}}(기기 기본 브라우저)로 이 페이지가 열리고, 설치 안내가 이어집니다.",
  copied_strong: "주소가 복사됐어요!",
  copied_plain: "주소를 복사했어요.",
  copy_guide: "{{name}}에서는 자동 이동이 막혀 있어요 — 화면 <b>우측 상단/하단 메뉴(⋯)</b>에서 <b>\"{{browser}}로 열기\"</b>를 누르거나, {{browser}}를 직접 열어 <b>주소창에 붙여넣기</b> 해주세요.",
  copy_again_done: "✅ 복사됨",
  copy_again: "🔗 주소 다시 복사",
  just_browse: "그냥 둘러보기",

  // ── 설치 완료(standalone) 안내 ──
  already_installed: "✅ 이미 앱으로 실행 중이에요! 홈 화면 아이콘으로 언제든 바로 열 수 있어요.",

  // ── 단계별 가이드 공통 ──
  guide_inapp: "<b>⚠️ 지금은 {{name}} 안의 브라우저예요.</b> 여기서는 홈 화면에 추가할 수 없어요.",
  open_default: "🧭 {{browser}}(기본 브라우저)로 열기",
  copy_safari_done: "✅ 복사됨 — Safari에 붙여넣어 여세요",
  copy_safari: "🔗 주소 복사 (Safari에 붙여넣기)",
  oneclick_btn: "📲 한 번에 설치하기",
  oneclick_note: "이 버튼 한 번이면 홈 화면에 <b>상담친구</b> 앱이 설치돼요.",

  // ── Android 탭 ──
  aos_hint_ok: "✅ 위 <b>“한 번에 설치하기”</b> 버튼을 누르면 끝이에요. 버튼이 안 보이면 아래 방법으로도 돼요.",
  aos_hint: "Chrome에서 잠깐 둘러보시면 <b>“한 번에 설치하기” 버튼이 자동으로 나타나요.</b> 안 나오면 아래 방법으로 하세요.",
  aos_step1: "<b>Chrome</b>으로 이 사이트를 여세요.",
  aos_step2: "우측 상단 <b>메뉴(⋮)</b> → <b>“앱 설치”</b> 또는 <b>“홈 화면에 추가”</b>를 누르세요.",
  aos_step3: "<b>“설치”</b>를 누르면 홈 화면과 앱 서랍에 <b>상담친구</b> 앱이 생겨요.",

  // ── iPhone 탭 ──
  ios_only_safari: "<b>⚠️ 아이폰은 <u>Safari</u>에서만 앱으로 설치돼요.</b>",
  ios_safari_body: "지금 브라우저(크롬 등)에서는 홈 화면에 추가해도 진짜 앱이 안 돼요. 아래 버튼으로 주소를 복사해 <b>Safari</b> 주소창에 붙여넣어 여세요.",
  ios_copy_done: "✅ 주소 복사됨 — Safari에 붙여넣기",
  ios_copy: "🔗 주소 복사 → Safari로 열기",
  sheet_copy: "복사",
  sheet_add_home: "홈 화면에 추가",
  sheet_bookmark: "책갈피 추가",
  sheet_tap_here: "여기를 누르세요",
  sheet_share_title: "공유",
  sheet_bar_hint: "① 화면 <b>아래 가운데</b> 공유 버튼",
  ios_step1: "Safari 화면 <b>아래 가운데 공유 버튼(⬆︎)</b>을 누르세요.",
  ios_step2: "목록을 아래로 내려 <b>“홈 화면에 추가”</b>를 누르세요.",
  ios_step3: "오른쪽 위 <b>“추가”</b> → 홈 화면의 <b>상담친구</b> 아이콘으로 실행!",
  help_close: "▲ 닫기",
  help_open: "❓ ‘홈 화면에 추가’가 안 보이나요?",
  help1: "• 공유 목록을 <b>아래로 더 스크롤</b>해 보세요. 아래쪽에 있어요.",
  help2: "• 주소창의 <b>브라우저가 Safari인지</b> 확인하세요. 크롬·카카오·인스타에서는 안 보여요.",
  help3: "• 그래도 없으면 위 <b>주소 복사</b> 후 Safari를 직접 열어 붙여넣어 주세요.",
  ios_note: "설치하면 전체 화면 앱으로 열리고, iOS 16.4 이상에서는 <b>아침 운세 알림</b>도 받을 수 있어요.",
};

export const installVi: typeof installKo = {
  warn_title: "📲 Hướng dẫn cài đặt ứng dụng",
  warn_body: "<b>⚠️ Bạn đang ở trong trình duyệt của {{name}}.</b><br/>Tại đây <b>không thể cài đặt ứng dụng (thêm vào màn hình chính)</b>. Mở bằng {{browser}} là cài được ngay.",
  warn_open: "🧭 Mở bằng {{browser}} (đồng ý)",
  warn_note: "Bấm nút, trang này sẽ mở bằng {{browser}} (trình duyệt mặc định của máy) và hướng dẫn cài đặt sẽ tiếp tục.",
  copied_strong: "Đã sao chép địa chỉ!",
  copied_plain: "Đã sao chép địa chỉ.",
  copy_guide: "Trong {{name}}, tự động chuyển trang bị chặn — hãy bấm <b>\"Mở bằng {{browser}}\"</b> trong <b>menu góc trên/dưới bên phải (⋯)</b>, hoặc tự mở {{browser}} rồi <b>dán vào thanh địa chỉ</b> nhé.",
  copy_again_done: "✅ Đã sao chép",
  copy_again: "🔗 Sao chép lại địa chỉ",
  just_browse: "Cứ xem tiếp",

  already_installed: "✅ Bạn đang chạy dưới dạng ứng dụng rồi! Có thể mở ngay bất cứ lúc nào bằng biểu tượng trên màn hình chính.",

  guide_inapp: "<b>⚠️ Bạn đang ở trong trình duyệt của {{name}}.</b> Tại đây không thể thêm vào màn hình chính.",
  open_default: "🧭 Mở bằng {{browser}} (trình duyệt mặc định)",
  copy_safari_done: "✅ Đã sao chép — dán vào Safari để mở",
  copy_safari: "🔗 Sao chép địa chỉ (dán vào Safari)",
  oneclick_btn: "📲 Cài đặt một chạm",
  oneclick_note: "Chỉ một lần bấm nút này, ứng dụng <b>Xem Bói</b> sẽ được cài lên màn hình chính.",

  aos_hint_ok: "✅ Bấm nút <b>“Cài đặt một chạm”</b> ở trên là xong. Nếu không thấy nút, làm theo cách bên dưới cũng được.",
  aos_hint: "Duyệt trong Chrome một lát, <b>nút “Cài đặt một chạm” sẽ tự xuất hiện.</b> Nếu không hiện, hãy làm theo cách bên dưới.",
  aos_step1: "Mở trang này bằng <b>Chrome</b>.",
  aos_step2: "Bấm <b>menu (⋮)</b> góc trên bên phải → <b>“Cài đặt ứng dụng”</b> hoặc <b>“Thêm vào màn hình chính”</b>.",
  aos_step3: "Bấm <b>“Cài đặt”</b>, ứng dụng <b>Xem Bói</b> sẽ xuất hiện trên màn hình chính và khay ứng dụng.",

  ios_only_safari: "<b>⚠️ iPhone chỉ cài được ứng dụng bằng <u>Safari</u>.</b>",
  ios_safari_body: "Với trình duyệt hiện tại (Chrome v.v.), dù thêm vào màn hình chính cũng không thành ứng dụng thật. Hãy bấm nút bên dưới để sao chép địa chỉ, rồi dán vào thanh địa chỉ <b>Safari</b> để mở.",
  ios_copy_done: "✅ Đã sao chép địa chỉ — dán vào Safari",
  ios_copy: "🔗 Sao chép địa chỉ → mở bằng Safari",
  sheet_copy: "Sao chép",
  sheet_add_home: "Thêm vào màn hình chính",
  sheet_bookmark: "Thêm dấu trang",
  sheet_tap_here: "Bấm vào đây",
  sheet_share_title: "Chia sẻ",
  sheet_bar_hint: "① Nút chia sẻ ở <b>giữa cạnh dưới</b> màn hình",
  ios_step1: "Bấm <b>nút chia sẻ (⬆︎) ở giữa cạnh dưới</b> màn hình Safari.",
  ios_step2: "Kéo danh sách xuống rồi bấm <b>“Thêm vào màn hình chính”</b>.",
  ios_step3: "Bấm <b>“Thêm”</b> ở góc trên bên phải → mở bằng biểu tượng <b>Xem Bói</b> trên màn hình chính!",
  help_close: "▲ Đóng",
  help_open: "❓ Không thấy ‘Thêm vào màn hình chính’?",
  help1: "• Hãy <b>cuộn danh sách chia sẻ xuống thêm</b>. Mục này nằm phía dưới.",
  help2: "• Kiểm tra <b>trình duyệt trên thanh địa chỉ có phải Safari không</b>. Trong Chrome·Zalo·Instagram sẽ không thấy.",
  help3: "• Nếu vẫn không có, hãy bấm <b>Sao chép địa chỉ</b> ở trên rồi tự mở Safari và dán vào.",
  ios_note: "Sau khi cài, trang sẽ mở như ứng dụng toàn màn hình; từ iOS 16.4 trở lên còn nhận được <b>thông báo vận trình buổi sáng</b>.",
};
