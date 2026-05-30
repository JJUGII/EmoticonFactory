/**
 * Web Push 구독 헬퍼
 *
 * 사용법:
 *   const ok = await requestPushForJob(jobId);
 */

import { getApiBase } from "./apiBase";

function apiUrl(path: string): string {
  const base = getApiBase();
  const p = path.startsWith("/") ? path : `/${path}`;
  return base ? `${base}${p}` : p;
}

// Base64URL → Uint8Array (VAPID public key 변환용)
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

async function getVapidPublicKey(): Promise<string> {
  const res = await fetch(apiUrl("/api/push/vapid-public-key"));
  if (!res.ok) throw new Error("VAPID key 요청 실패");
  const data = await res.json();
  return data.public_key as string;
}

async function registerServiceWorker(): Promise<ServiceWorkerRegistration> {
  if (!("serviceWorker" in navigator)) throw new Error("ServiceWorker 미지원");
  return navigator.serviceWorker.register("/sw.js");
}

async function subscribePush(
  reg: ServiceWorkerRegistration,
  vapidKey: string
): Promise<PushSubscription> {
  const existing = await reg.pushManager.getSubscription();
  if (existing) return existing;
  return reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(vapidKey),
  });
}

async function sendSubscriptionToServer(
  jobId: string,
  subscription: PushSubscription
): Promise<void> {
  const res = await fetch(apiUrl(`/api/push/subscribe/${jobId}`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(subscription.toJSON()),
  });
  if (!res.ok) throw new Error("구독 정보 전송 실패");
}

/**
 * 알림 권한을 요청하고, 성공 시 job에 push 구독을 등록합니다.
 * @returns true if 구독 성공, false if 실패/거부
 */
export async function requestPushForJob(jobId: string): Promise<boolean> {
  try {
    if (!("Notification" in window) || !("PushManager" in window)) return false;

    // 이미 거부됐으면 포기
    if (Notification.permission === "denied") return false;

    // 아직 결정 안 됐으면 요청
    if (Notification.permission !== "granted") {
      const result = await Notification.requestPermission();
      if (result !== "granted") return false;
    }

    const [vapidKey, reg] = await Promise.all([
      getVapidPublicKey(),
      registerServiceWorker(),
    ]);

    const sub = await subscribePush(reg, vapidKey);
    await sendSubscriptionToServer(jobId, sub);
    return true;
  } catch (e) {
    console.warn("[push] 구독 실패:", e);
    return false;
  }
}

/** 현재 알림 권한 상태 반환 */
export function notificationPermission(): NotificationPermission | "unsupported" {
  if (!("Notification" in window)) return "unsupported";
  return Notification.permission;
}
