/**
 * 업로드 전 이미지 자동 압축.
 *
 * Vercel 프록시 제한(~4MB)을 피하기 위해
 * 3MB 초과 파일을 canvas로 리사이즈·JPEG 압축해 반환합니다.
 * 3MB 이하면 원본 그대로 반환합니다.
 */

const MAX_BYTES   = 3 * 1024 * 1024;   // 3 MB — Vercel 4MB 한도보다 여유 있게
const MAX_DIM     = 2048;               // 최대 가로·세로 픽셀
const QUALITIES   = [0.88, 0.78, 0.68, 0.55, 0.45];

async function blobFromCanvas(canvas: HTMLCanvasElement, quality: number): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error("canvas.toBlob 실패"))),
      "image/jpeg",
      quality
    );
  });
}

/**
 * 필요하면 압축 후 File 반환. 이미 작으면 원본 반환.
 *
 * @param file     원본 파일
 * @param maxBytes 이 크기를 넘으면 압축 (기본 3MB)
 */
export async function compressIfNeeded(
  file: File,
  maxBytes: number = MAX_BYTES
): Promise<File> {
  // 작으면 즉시 반환
  if (file.size <= maxBytes) return file;

  // 이미지 → Bitmap
  const bitmap = await createImageBitmap(file);

  // 축소 비율 계산
  let { width, height } = bitmap;
  if (width > MAX_DIM || height > MAX_DIM) {
    const ratio = Math.min(MAX_DIM / width, MAX_DIM / height);
    width  = Math.round(width  * ratio);
    height = Math.round(height * ratio);
  }

  // Canvas에 그리기
  const canvas = document.createElement("canvas");
  canvas.width  = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas 2D context 없음");
  ctx.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();

  // 품질을 낮춰가며 목표 크기 이하로
  for (const q of QUALITIES) {
    const blob = await blobFromCanvas(canvas, q);
    if (blob.size <= maxBytes) {
      const name = file.name.replace(/\.[^.]+$/, "") + ".jpg";
      console.log(
        `[compress] ${(file.size / 1024 / 1024).toFixed(1)}MB → ` +
        `${(blob.size / 1024 / 1024).toFixed(1)}MB (quality=${q})`
      );
      return new File([blob], name, { type: "image/jpeg" });
    }
  }

  // 최후 수단: 가장 낮은 품질
  const blob = await blobFromCanvas(canvas, QUALITIES[QUALITIES.length - 1]);
  const name = file.name.replace(/\.[^.]+$/, "") + ".jpg";
  return new File([blob], name, { type: "image/jpeg" });
}
