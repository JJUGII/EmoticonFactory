"use client";

import { motion } from "framer-motion";

const RANDOM_POOL = [
  "심쿵", "뿌잉", "대박", "헉", "쿨쿨", "냥냥", "멍멍", "짜증",
  "눈물", "윙크", "화이팅", "놀람", "배고파", "졸려", "사랑해", "고마워",
];

type Props = {
  emotions: string[];
  onChange: (next: string[]) => void;
  phone: string;
  onPhoneChange: (v: string) => void;
};

export function StepEmotions({ emotions, onChange, phone, onPhoneChange }: Props) {
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

      {/* SMS 알림 (선택) */}
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="rounded-2xl bg-white/80 p-4 shadow-card"
      >
        <label className="block">
          <span className="flex items-center gap-1.5 text-sm font-medium text-kakao-brown">
            📱 완료 SMS 알림 <span className="text-xs font-normal text-kakao-brown/50">(선택)</span>
          </span>
          <input
            type="tel"
            inputMode="numeric"
            placeholder="010-0000-0000"
            value={phone}
            onChange={(e) => onPhoneChange(e.target.value)}
            className="mt-2 w-full rounded-xl border border-kakao-brown/10 bg-kakao-cream/50 px-3 py-2.5 text-sm outline-none focus:border-kakao-yellow"
          />
          <p className="mt-1.5 text-xs text-kakao-brown/40">
            생성이 완료되면 문자로 알려드려요
          </p>
        </label>
      </motion.div>

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
