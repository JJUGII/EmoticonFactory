/* Emoticon Factory — Service Worker (Web Push) */

self.addEventListener("push", (event) => {
  if (!event.data) return;

  let payload;
  try {
    payload = event.data.json();
  } catch {
    payload = { title: "이모티콘 스튜디오", body: event.data.text(), url: "/" };
  }

  const title = payload.title || "이모티콘 스튜디오";
  const options = {
    body: payload.body || "",
    icon: "/icon-192.png",
    badge: "/icon-72.png",
    data: { url: payload.url || "/" },
    requireInteraction: false,
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = event.notification.data?.url || "/";

  event.waitUntil(
    clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((windowClients) => {
        // 이미 열린 탭이 있으면 포커스
        for (const client of windowClients) {
          const clientUrl = new URL(client.url);
          const targetUrlObj = new URL(targetUrl, self.location.origin);
          if (
            clientUrl.origin === targetUrlObj.origin &&
            clientUrl.pathname === targetUrlObj.pathname
          ) {
            client.focus();
            return;
          }
        }
        // 없으면 새 탭 오픈
        return clients.openWindow(targetUrl);
      })
  );
});
