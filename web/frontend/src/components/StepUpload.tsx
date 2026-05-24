"use client";

import { useCallback, useRef, useState } from "react";
import { isAllowedImageFile, logFileMeta } from "@/lib/imageFile";

const FILE_ACCEPT = "image/*";

type Props = {
  previewUrl: string | null;
  uploadError: string | null;
  uploading?: boolean;
  onFile: (file: File) => void;
  onFileError: (message: string) => void;
  generator: string;
  onGeneratorChange: (g: string) => void;
};

export function StepUpload({
  previewUrl,
  uploadError,
  uploading = false,
  onFile,
  onFileError,
  generator,
  onGeneratorChange,
}: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  const pick = useCallback(
    (file: File | null) => {
      if (!file) return;
      logFileMeta(file);
      if (!isAllowedImageFile(file)) {
        onFileError("JPG, PNG, WEBP, HEIC 형식만 선택할 수 있어요.");
        return;
      }
      onFile(file);
    },
    [onFile, onFileError]
  );

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h1 className="text-2xl font-bold text-kakao-brown">사진을 선택해주세요</h1>
        <p className="mt-2 text-sm text-kakao-brown/70">
          반려동물·캐릭터 사진을 이모티콘 스타일로 바꿔드려요
        </p>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept={FILE_ACCEPT}
        className="hidden"
        onChange={(e) => {
          pick(e.target.files?.[0] ?? null);
          if (e.currentTarget) e.currentTarget.value = "";
        }}
      />

      {uploadError ? (
        <div
          role="alert"
          className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-relaxed text-red-800"
        >
          {uploadError}
        </div>
      ) : null}

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          pick(e.dataTransfer.files[0] ?? null);
        }}
        className={`rounded-3xl border-2 border-dashed p-6 text-center shadow-card transition sm:p-8 ${
          drag
            ? "border-kakao-yellow bg-kakao-yellow/20"
            : "border-kakao-brown/20 bg-white/80"
        }`}
      >
        {previewUrl ? (
          <img
            src={previewUrl}
            alt="미리보기"
            className="mx-auto max-h-64 w-auto rounded-2xl object-contain"
            onError={() => {
              console.error("[UPLOAD_ERROR] preview img onError", previewUrl);
              onFileError(
                "미리보기를 표시할 수 없습니다. 다른 사진으로 다시 시도해 주세요."
              );
            }}
          />
        ) : (
          <div>
            <p className="text-4xl">📷</p>
            <p className="mt-3 text-sm text-kakao-brown/60">
              PC에서는 여기로 드래그 앤 드롭할 수 있어요
            </p>
          </div>
        )}

        {uploading ? (
          <p className="mt-3 text-sm font-medium text-kakao-brown/70">서버에 업로드 중...</p>
        ) : null}
      </div>

      <button
        type="button"
        disabled={uploading}
        onClick={() => fileInputRef.current?.click()}
        className="w-full rounded-2xl bg-kakao-yellow px-6 py-4 text-base font-bold text-kakao-brown shadow-card transition enabled:hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
      >
        사진 선택
      </button>

      <div className="rounded-2xl bg-white/70 p-4 shadow-card">
        <label className="text-sm font-medium">생성 엔진</label>
        <select
          value={generator}
          onChange={(e) => onGeneratorChange(e.target.value)}
          className="mt-2 w-full rounded-xl border border-kakao-brown/15 bg-white px-3 py-2 text-sm"
        >
          <option value="mock">목업 (빠른 테스트)</option>
          <option value="openai">OpenAI (실제 생성)</option>
        </select>
      </div>
    </div>
  );
}
