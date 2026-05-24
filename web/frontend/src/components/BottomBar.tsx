"use client";

import { motion } from "framer-motion";

type Props = {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  loading?: boolean;
};

export function BottomBar({ label, onClick, disabled, loading }: Props) {
  return (
    <motion.div
      initial={{ y: 80 }}
      animate={{ y: 0 }}
      className="fixed bottom-0 left-0 right-0 z-40 border-t border-kakao-brown/10 bg-white/95 px-4 py-3 shadow-[0_-4px_24px_rgba(60,30,30,0.08)] safe-area-pb"
    >
      <div className="mx-auto max-w-lg">
        <button
          type="button"
          disabled={disabled || loading}
          onClick={onClick}
          className="w-full rounded-2xl bg-kakao-yellow py-4 text-base font-bold text-kakao-brown shadow-card transition enabled:hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading ? "잠시만요..." : label}
        </button>
      </div>
    </motion.div>
  );
}
