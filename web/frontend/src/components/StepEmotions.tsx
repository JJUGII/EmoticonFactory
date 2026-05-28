"use client";

import { motion } from "framer-motion";

const RANDOM_POOL = [
  "심쿵", "뿌잉", "대박", "헉", "쿨쿨", "냥냥", "멍멍", "짜증",
  "눈물", "윙크", "화이팅", "놀람", "배고파", "졸려", "사랑해", "고마워",
];

type Props = {
  emotions: string[];
  onChange: (next: string[]) => void;
};

export function StepEmotions({ emotions, onChange }: Props) {
  const setAt = (i: number, v: string) => {
    const next = [...emotions];
    next[i] = v;
    onChange(next);
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center"
      >
        <h2 className="text-xl font-bold">이 캐릭터로 생성할까요?</h2>
        <p className="mt-2 text-sm text-kakao-brown/70">
          원하는 감정이나 문구를 자유롭게 수정할 수 있어요
        </p>
      </motion.div>

      <div className="flex flex-wrap justify-center gap-2">
        <button
          type="button"
          className="rounded-full bg-white px-4 py-2 text-sm shadow-card"
          onClick={() => {
            const shuffled = [...RANDOM_POOL].sort(() => Math.random() - 0.5);
            onChange(shuffled.slice(0, 16));
          }}
        >
          랜덤 추천
        </button>
        <button
          type="button"
          className="rounded-full bg-white px-4 py-2 text-sm shadow-card"
          onClick={() =>
            onChange([
              "사랑해", "좋아", "고마워", "미안해", "배고파", "졸려", "행복해", "화났어",
              "놀랐어", "응원해", "가지마", "안아줘", "심심해", "축하해", "잘자", "보고싶어",
            ])
          }
        >
          초기화
        </button>
      </div>

      <motion.div
        className="grid grid-cols-2 gap-3 sm:grid-cols-4"
        initial="hidden"
        animate="visible"
        variants={{ visible: { transition: { staggerChildren: 0.03 } } }}
      >
        {emotions.map((text, i) => (
          <motion.label
            key={i}
            variants={{ hidden: { opacity: 0 }, visible: { opacity: 1 } }}
            className="flex flex-col rounded-2xl bg-white/90 p-2 shadow-card"
          >
            <span className="mb-1 text-xs text-kakao-brown/50">{String(i + 1).padStart(2, "0")}</span>
            <input
              value={text}
              onChange={(e) => setAt(i, e.target.value)}
              className="w-full rounded-lg border border-kakao-brown/10 bg-kakao-cream/50 px-2 py-2 text-center text-sm font-medium outline-none focus:border-kakao-yellow"
            />
          </motion.label>
        ))}
      </motion.div>
    </motion.div>
  );
}
