/**
 * SMS 알림 전화번호 등록 헬퍼
 */

import { getApiBase } from "./apiBase";

function apiUrl(path: string): string {
  const base = getApiBase();
  const p = path.startsWith("/") ? path : `/${path}`;
  return base ? `${base}${p}` : p;
}

/**
 * 전화번호를 job에 등록합니다. 생성 완료 시 백엔드에서 SMS를 발송합니다.
 * @returns true if 등록 성공
 */
export async function registerSmsPhone(jobId: string, phone: string): Promise<boolean> {
  try {
    const res = await fetch(apiUrl(`/api/sms/register/${jobId}`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone }),
    });
    return res.ok;
  } catch (e) {
    console.warn("[sms] 전화번호 등록 실패:", e);
    return false;
  }
}
