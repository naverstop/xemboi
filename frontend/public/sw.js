/* Xem Bói Service Worker
 * - 정적 셸 프리캐시 + 런타임 캐시(정적 자원만).
 * - API(/api/*)·SSE 스트림은 캐시 제외(실시간성/인증 보호).
 * - Web Push 수신/클릭 핸들러(계획 2.7.6).
 */
const CACHE = "xemboi-shell-v69";
const SHELL = ["/", "/manifest.webmanifest"];  // 오프라인 폴백용

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    // 옛 캐시 전부 삭제
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)));
    await self.clients.claim();
    // 새로고침은 페이지 측 controllerchange 핸들러(main.tsx, reloaded 가드로 1회)가 담당한다.
    // 여기서 clients.navigate 로 또 새로고침하면 같은 사건에 리로드가 이중으로 걸려
    // '로그아웃→재로그인 시 화면이 한 번 더 로딩'되는 문제가 있어 제거함.
  })());
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // API / SSE / 외부 도메인은 캐시하지 않음(네트워크 직통)
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;
  if (req.headers.get("accept") === "text/event-stream") return;

  // HTML/내비게이션: 네트워크 우선(항상 최신 index.html → 최신 번들). 오프라인이면 캐시 폴백.
  const isNav = req.mode === "navigate" || (req.headers.get("accept") || "").includes("text/html");
  if (isNav) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put("/", copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match(req).then((c) => c || caches.match("/")))
    );
    return;
  }

  // 정적 해시 자원: stale-while-revalidate
  event.respondWith(
    caches.match(req).then((cached) => {
      const network = fetch(req)
        .then((res) => {
          if (res && res.status === 200 && res.type === "basic") {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});

// ---- Web Push ----
self.addEventListener("push", (event) => {
  let data = { title: "Xem Bói", body: "Bạn có thông báo mới.", url: "/chat" };
  try {
    if (event.data) data = { ...data, ...event.data.json() };
  } catch (_) {
    if (event.data) data.body = event.data.text();
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      data: { url: data.url || "/chat" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || "/chat";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if (client.url.includes(target) && "focus" in client) return client.focus();
      }
      return self.clients.openWindow(target);
    })
  );
});
