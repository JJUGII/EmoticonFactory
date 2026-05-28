/** Mobile-safe image pick / blob preview helpers (Safari HEIC 포함). */

/** StepUpload input accept (iOS 기본 메뉴: 보관함·촬영·파일) */
export const IMAGE_ACCEPT = "image/*";

const ALLOWED_EXT = new Set([
  ".jpg",
  ".jpeg",
  ".png",
  ".webp",
  ".heic",
  ".heif",
]);

const ALLOWED_MIME = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/heic",
  "image/heif",
  "image/heic-sequence",
]);

export function fileExtension(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
}

export function isAllowedImageFile(file: File): boolean {
  const ext = fileExtension(file.name);
  if (ext && ALLOWED_EXT.has(ext)) return true;
  const type = (file.type || "").toLowerCase();
  if (!type) {
    return ext ? ALLOWED_EXT.has(ext) : file.size > 0;
  }
  if (type.startsWith("image/")) {
    if (ALLOWED_MIME.has(type)) return true;
    // image/* 일반 허용 (일부 iOS 빌드)
    return type === "image/*" || type.includes("heic") || type.includes("heif");
  }
  return false;
}

export function logFileMeta(file: File, tag = "[UPLOAD_FILE]"): void {
  console.info(tag, {
    name: file.name,
    type: file.type || "(empty)",
    size: file.size,
    ext: fileExtension(file.name),
  });
}

export function createPreviewObjectUrl(file: File): string {
  return URL.createObjectURL(file);
}

export function revokePreviewObjectUrl(url: string | null | undefined): void {
  if (url && url.startsWith("blob:")) {
    URL.revokeObjectURL(url);
  }
}
