"use client";

import { motion } from "framer-motion";
import { downloadZipUrl } from "@/lib/api";

type Cut = { id: string; text: string; url?: string | null };

type Props = {
  jobId: string;
  cuts: Cut[];
  onRestart: () => void;
  onReselect: () => void;
};

export function StepResult({ jobId, cuts, onRestart, onReselect }: Props) {
  const saveAll = () => {
    window.open(downloadZipUrl(jobId), "_blank");
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6 pb-8">
      <h2 className="text-center text-xl font-bold">완성!</h2>
      <p className="text-center text-sm text-kakao-brown/70">
        16개의 이모티콘이 준비되었어요
      </p>

      <motion.div
        className="grid grid-cols-2 gap-3 sm:grid-cols-4"
        initial="hidden"
        animate="visible"
        variants={{ visible: { transition: { staggerChildren: 0.05 } } }}
      >
        {cuts.map((c) => (
          <motion.div
            key={c.id}
            variants={{ hidden: { opacity: 0, scale: 0.9 }, visible: { opacity: 1, scale: 1 } }}
            whileHover={{ scale: 1.05 }}
            className="overflow-hidden rounded-2xl bg-white shadow-card"
          >
            {c.url ? (
              <img src={c.url} alt={c.text} className="aspect-square w-full object-cover" />
            ) : (
              <motion.div className="aspect-square shimmer" />
            )}
            <p className="truncate px-2 py-2 text-center text-xs font-medium">{c.text}</p>
          </motion.div>
        ))}
      </motion.div>

      <div className="space-y-3 rounded-2xl bg-white/80 p-4 shadow-card">
        <button
          type="button"
          onClick={saveAll}
          className="w-full rounded-xl bg-kakao-yellow py-3 font-bold text-kakao-brown"
        >
          모두 저장 (ZIP)
        </button>
        <button
          type="button"
          onClick={onReselect}
          className="w-full rounded-xl border border-kakao-brown/15 bg-white py-3 text-sm font-medium"
        >
          후보 다시 선택
        </button>
        <button
          type="button"
          onClick={onRestart}
          className="w-full rounded-xl border border-kakao-brown/15 bg-white py-3 text-sm font-medium"
        >
          다른 스타일로 다시 만들기
        </button>
      </div>
    </motion.div>
  );
}
