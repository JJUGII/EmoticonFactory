"use client";

import { motion } from "framer-motion";
import type { CutStatus } from "@/lib/api";

type Props = {
  message: string;
  progress: number;
  cuts: { id: string; text: string; status: CutStatus }[];
  currentCut?: string | null;
};

const statusLabel: Record<CutStatus, string> = {
  pending: "대기중",
  running: "생성중",
  done: "완료",
  failed: "실패",
};

export function StepGenerate({ message, progress, cuts, currentCut }: Props) {
  return (
    <motion.div initial={ { opacity: 0 } } animate={ { opacity: 1 } } className="space-y-6">
      <div className="text-center">
        <h2 className="text-xl font-bold">이모티콘 생성 중</h2>
        <p className="mt-2 text-sm text-kakao-brown/70">{message}</p>
        {currentCut && (
          <p className="mt-1 text-sm font-medium text-kakao-brown">
            [{currentCut} 생성중...]
          </p>
        )}
      </div>

      <motion.div
        className="h-3 overflow-hidden rounded-full bg-white shadow-inner"
        initial={ { width: "100%" } }
      >
        <motion.div
          className="h-full rounded-full bg-kakao-yellow"
          animate={ { width: `${progress}%` } }
          transition={ { ease: "easeOut" } }
        />
      </motion.div>
      <p className="text-center text-xs text-kakao-brown/60">{progress}%</p>

      <div className="grid grid-cols-4 gap-2 sm:gap-3">
        {cuts.map((c) => (
          <motion.div
            key={c.id}
            layout
            className={`flex aspect-square flex-col items-center justify-center rounded-2xl p-1 text-center text-xs shadow-card ${
              c.status === "running"
                ? "bg-kakao-yellow/40 ring-2 ring-kakao-yellow"
                : c.status === "done"
                  ? "bg-kakao-mint"
                  : "bg-white/80 shimmer"
            }`}
          >
            <span className="font-bold">{c.id}</span>
            <span className="mt-1 line-clamp-2 text-[10px]">{c.text || "—"}</span>
            <span className="mt-1 text-[10px] opacity-70">{statusLabel[c.status]}</span>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}
