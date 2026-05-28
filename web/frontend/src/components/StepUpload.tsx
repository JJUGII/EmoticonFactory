"use client";

import { useCallback, useRef, useState } from "react";
import { isAllowedImageFile, logFileMeta } from "@/lib/imageFile";

const FILE_ACCEPT = "image/*";

const SPECIES_OPTIONS = [
  { value: "",        label: "자동감지", emoji: "🔍" },
  { value: "human",   label: "사람",    emoji: "👤" },
  { value: "cat",     label: "고양이",  emoji: "🐱" },
  { value: "dog",     label: "강아지",  emoji: "🐶" },
  { value: "rabbit",  label: "토끼",    emoji: "🐰" },
  { value: "hamster", label: "햄스터",  emoji: "🐹" },
  { value: "bird",    label: "새",      emoji: "🐦" },
];

type ArtStyle = "illustration" | "realistic";

type Props = {
  previewUrl: string | null;
  uploadError: string | null;
  uploading?: boolean;
  onFile: (file: File) => void;
  onFileError: (message: string) => void;
  artStyle?: ArtStyle;
  onArtStyleChange?: (v: ArtStyle) => void;
  gridMode?: boolean;
  onGridModeChange?: (v: boolean) => void;
  speciesHint?: string;
  onSpeciesHintChange?: (v: string) => void;
};

export function StepUpload({
  previewUrl,
  uploadError,
  uploading = false,
  onFile,
  onFileError,
  artStyle = "illustration",
  onArtStyleChange,
  gridMode = false,
  onGridModeChange,
  speciesHint = "",
  onSpeciesHintChange,
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

      <div className="rounded-2xl bg-white/70 p-4 shadow-card space-y-4">

        {/* 대상 종류 선택 */}
        <div>
          <label className="text-sm font-medium text-kakao-brown">대상 종류</label>
          <p className="mb-2 text-xs text-kakao-brown/60">
            사진 속 대상을 선택하면 더 정확한 캐릭터가 만들어져요
          </p>
          <div className="grid grid-cols-4 gap-2">
            {SPECIES_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => onSpeciesHintChange?.(opt.value)}
                className={`flex flex-col items-center rounded-xl border py-2 text-xs transition ${
                  speciesHint === opt.value
                    ? "border-kakao-yellow bg-kakao-yellow/30 font-bold text-kakao-brown"
                    : "border-kakao-brown/10 bg-white text-kakao-brown/70 hover:bg-kakao-yellow/10"
                }`}
              >
                <span className="text-lg">{opt.emoji}</span>
                <span className="mt-0.5">{opt.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* 스타일 선택 */}
        <div>
          <label className="text-sm font-medium text-kakao-brown">이모티콘 스타일</label>
          <p className="mb-2 text-xs text-kakao-brown/60">
            생성할 이모티콘의 그림 스타일을 선택해요
          </p>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => onArtStyleChange?.("illustration")}
              className={`flex flex-col items-center rounded-xl border py-3 text-xs transition ${
                artStyle === "illustration"
                  ? "border-kakao-yellow bg-kakao-yellow/30 font-bold text-kakao-brown"
                  : "border-kakao-brown/10 bg-white text-kakao-brown/70 hover:bg-kakao-yellow/10"
              }`}
            >
              <span className="text-2xl mb-1">🎨</span>
              <span className="font-medium">일러스트</span>
              <span className="mt-0.5 text-kakao-brown/50">치비·수채화·카툰</span>
            </button>
            <button
              type="button"
              onClick={() => onArtStyleChange?.("realistic")}
              className={`flex flex-col items-center rounded-xl border py-3 text-xs transition ${
                artStyle === "realistic"
                  ? "border-kakao-yellow bg-kakao-yellow/30 font-bold text-kakao-brown"
                  : "border-kakao-brown/10 bg-white text-kakao-brown/70 hover:bg-kakao-yellow/10"
              }`}
            >
              <span className="text-2xl mb-1">📸</span>
              <span className="font-medium">실사(웹툰)</span>
              <span className="mt-0.5 text-kakao-brown/50">세미리얼·웹툰</span>
            </button>
          </div>
        </div>

        {/* 그리드 모드 */}
        <label className="flex cursor-pointer items-center justify-between rounded-xl border border-kakao-brown/10 bg-kakao-cream/60 px-3 py-2">
          <div>
            <p className="text-sm font-medium text-kakao-brown">그리드 모드</p>
            <p className="text-xs text-kakao-brown/60">
              16컷을 4×4 이미지 1장으로 생성 → API 1회 호출 (비용 절감)
            </p>
          </div>
          <div
            role="switch"
            aria-checked={gridMode}
            onClick={() => onGridModeChange?.(!gridMode)}
            className={`relative ml-3 h-6 w-11 shrink-0 rounded-full transition-colors ${
              gridMode ? "bg-kakao-yellow" : "bg-kakao-brown/20"
            }`}
          >
            <span
              className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
                gridMode ? "translate-x-5" : "translate-x-0.5"
              }`}
            />
          </div>
        </label>

      </div>
    </div>
  );
}
