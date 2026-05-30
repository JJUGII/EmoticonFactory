"use client";

import { motion } from "framer-motion";
import type { CandidateItem } from "@/lib/api";

type Props = {
  loading: boolean;
  message: string;
  candidates: CandidateItem[];
  selected: number | null;
  onSelect: (index: number) => void;
};

const gridVariants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.08 },
  },
};

const cardVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0 },
};

export function StepCandidates({
  loading,
  message,
  candidates,
  selected,
  onSelect,
}: Props) {
  if (loading && candidates.length === 0) {
    return (
      <div className="relative z-10 space-y-4">
        <h2 className="text-center text-xl font-bold">귀여운 캐릭터 만드는 중...</h2>
        <p className="text-center text-sm text-kakao-brown/70">{message}</p>
        <motion.div
          className="grid grid-cols-2 gap-4"
          initial="hidden"
          animate="visible"
          variants={gridVariants}
        >
          {[0, 1].map((i) => (
            <motion.div
              key={i}
              variants={cardVariants}
              className="aspect-square rounded-3xl shimmer"
            />
          ))}
        </motion.div>
      </div>
    );
  }

  if (candidates.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="relative z-10 space-y-4 text-center"
      >
        <h2 className="text-xl font-bold">캐릭터 후보를 만들어 볼까요?</h2>
        <p className="text-sm text-kakao-brown/70">
          아래 버튼을 눌러 일러스트·실사 후보 2장을 생성해 주세요.
        </p>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="relative z-10 space-y-6"
    >
      <h2 className="text-center text-xl font-bold">무엇으로 생성할까요?</h2>
      <p className="text-center text-sm text-kakao-brown/70">
        마음에 드는 캐릭터를 골라주세요
      </p>
      <motion.div
        className="relative z-10 grid grid-cols-2 gap-4"
        initial="visible"
        animate="visible"
        variants={gridVariants}
      >
        {candidates.map((c) => {
          const active = selected === c.index;
          const styleLabel = c.index === 0
            ? { emoji: "🎨", name: "일러스트", sub: "치비·수채화" }
            : { emoji: "📸", name: "실사풍", sub: "CG·디지털 아트" };
          return (
            <motion.button
              key={c.index}
              type="button"
              variants={cardVariants}
              initial={{ opacity: 1, y: 0 }}
              whileTap={{ scale: 0.97 }}
              animate={{ scale: active ? 1.03 : 1 }}
              onClick={() => onSelect(c.index)}
              className={`relative z-10 overflow-hidden rounded-3xl bg-white shadow-card transition ring-4 ${
                active ? "ring-kakao-yellow" : "ring-transparent"
              }`}
            >
              <img
                src={c.url}
                alt={styleLabel.name}
                className="relative z-10 aspect-square w-full bg-white object-cover"
                loading="lazy"
                onError={(e) => {
                  const el = e.currentTarget;
                  el.style.opacity = "1";
                  el.alt = "이미지를 불러올 수 없습니다";
                }}
              />
              {active && (
                <span className="absolute right-3 top-3 z-20 flex h-8 w-8 items-center justify-center rounded-full bg-kakao-yellow text-kakao-brown shadow-md">
                  ✓
                </span>
              )}
              <div className="relative z-10 bg-white py-2 text-center">
                <span className="text-sm font-bold">
                  {styleLabel.emoji} {styleLabel.name}
                </span>
                <span className="block text-xs text-kakao-brown/50">{styleLabel.sub}</span>
              </div>
            </motion.button>
          );
        })}
      </motion.div>
    </motion.div>
  );
}
