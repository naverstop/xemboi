/** 생성 중 3점 바운스 인디케이터 — '멈춘 게 아니라 생성 중'임을 확실히 인지시키는 UI(운영자 지시 2026-07-21).
 *  메신저 표준 타이핑 애니메이션(3점 순차 바운스). 순수 표시용(로직 없음). */
export default function TypingDots() {
  return (
    <span className="typing3" aria-hidden="true">
      <i /><i /><i />
    </span>
  );
}
