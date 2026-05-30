"use client";

import { motion } from "framer-motion";
import { assetUrl } from "@/lib/api";
import type { CutStatus } from "@/lib/api";

type Cut = { id: string; text: string; status: CutStatus; url?: string | null };

type Props = {
  message: string;
  progress: number;
  cuts: Cut[];
  currentCut?: string | null;
};

export function StepGenerate({ message, progress, cuts, currentCut }: Props) {
  const doneCount = cuts.filter((c) => c.status === "done").length;
  const total = cuts.length || 16;

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
      <div className="text-center">
        <h2 className="text-xl font-bold">이모티콘 생성 중</h2>
        <p className="mt-2 text-sm text-kakao-brown/70">
          {doneCount > 0 ? `${doneCount} / ${total}장 완성` : message}
        </p>
        {currentCut && doneCount < total && (
          <p className="mt-1 text-xs text-kakao-brown/50">
            컷 {currentCut} 생성중…
          </p>
        )}
      </div>

      {/* 진행 바 */}
      <div>
        <div className="h-3 overflow-hidden rounded-full bg-white shadow-inner">
          <motion.div
            className="h-full rounded-full bg-kakao-yellow"
            animate={{ width: `${progress}%` }}
            transition={{ ease: "easeOut" }}
          />
        </div>
        <p className="mt-1 text-center text-xs text-kakao-brown/60">{progress}%</p>
      </div>

      {/* 컷 그리드 — 완성되면 즉시 이미지 표시 */}
      <div className="grid grid-cols-4 gap-2 sm:gap-3">
        {cuts.map((c) => (
          <motion.div
            key={c.id}
            layout
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className={`relative overflow-hidden rounded-2xl shadow-card ${
              c.status === "running"
                ? "ring-2 ring-kakao-yellow"
                : ""
            }`}
          >
            {c.status === "done" && c.url ? (
              /* 완성된 컷 — 실제 이미지 */
              <div className="aspect-square w-full">
                <img
                  src={assetUrl(c.url)}
                  alt={c.text}
                  className="h-full w-full object-cover"
                />
                <p className="truncate bg-white px-1 py-1 text-center text-[10px] font-medium">
                  {c.text}
                </p>
              </div>
            ) : c.status === "running" ? (
              /* 현재 생성 중 */
              <div className="aspect-square shimmer flex flex-col items-center justify-center bg-kakao-yellow/20">
                <span className="text-lg animate-bounce">✏️</span>
                <p className="mt-1 text-[10px] text-kakao-brown/60 truncate px-1">{c.text}</p>
              </div>
            ) : (
              /* 대기 중 */
              <div className="aspect-square shimmer flex flex-col items-center justify-center bg-white/80">
                <p className="text-[10px] text-kakao-brown/40 truncate px-1">{c.text}</p>
              </div>
            )}
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}
