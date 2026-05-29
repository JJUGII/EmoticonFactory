"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { downloadZipUrl, exportToTelegram, getDiscordInviteUrl } from "@/lib/api";

type Cut = { id: string; text: string; url?: string | null };

type Props = {
  jobId: string;
  cuts: Cut[];
  onRestart: () => void;
  onReselect: () => void;
};

type ExportState = "idle" | "loading" | "done" | "error";

export function StepResult({ jobId, cuts, onRestart, onReselect }: Props) {
  const [tgState, setTgState]     = useState<ExportState>("idle");
  const [tgLink, setTgLink]       = useState("");
  const [dcState, setDcState]     = useState<ExportState>("idle");
  const [errMsg, setErrMsg]       = useState("");

  const saveAll = () => window.open(downloadZipUrl(jobId), "_blank");

  const handleTelegram = async () => {
    setTgState("loading");
    setErrMsg("");
    try {
      const { link } = await exportToTelegram(jobId);
      setTgLink(link);
      setTgState("done");
    } catch (e: unknown) {
      setErrMsg(e instanceof Error ? e.message : "오류 발생");
      setTgState("error");
    }
  };

  const handleDiscord = async () => {
    setDcState("loading");
    setErrMsg("");
    try {
      const { oauth2_url } = await getDiscordInviteUrl(jobId);
      // 새 창으로 Discord 인증 페이지 열기
      window.open(oauth2_url, "_blank", "width=520,height=700");
      setDcState("done");
    } catch (e: unknown) {
      setErrMsg(e instanceof Error ? e.message : "오류 발생");
      setDcState("error");
    }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6 pb-8">
      <h2 className="text-center text-xl font-bold">완성!</h2>
      <p className="text-center text-sm text-kakao-brown/70">
        16개의 이모티콘이 준비되었어요
      </p>

      {/* 스티커 그리드 */}
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

      {/* 내보내기 버튼 */}
      <div className="space-y-3 rounded-2xl bg-white/80 p-4 shadow-card">
        <p className="text-center text-xs font-semibold text-kakao-brown/60 uppercase tracking-wide">
          메신저에 바로 추가
        </p>

        {/* Telegram */}
        <div className="space-y-2">
          <button
            type="button"
            onClick={handleTelegram}
            disabled={tgState === "loading"}
            className="flex w-full items-center justify-center gap-2 rounded-xl py-3 font-bold text-white transition-opacity disabled:opacity-60"
            style={{ backgroundColor: "#229ED9" }}
          >
            {tgState === "loading" ? (
              <span className="animate-pulse">스티커팩 생성 중…</span>
            ) : (
              <>
                <svg viewBox="0 0 24 24" className="h-5 w-5 fill-current">
                  <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.894 8.221-1.97 9.28c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12L7.17 13.35l-2.945-.924c-.64-.203-.653-.64.136-.953l11.498-4.43c.537-.194 1.006.131.835.953z" />
                </svg>
                Telegram에 추가
              </>
            )}
          </button>

          {tgState === "done" && tgLink && (
            <a
              href={tgLink}
              target="_blank"
              rel="noopener noreferrer"
              className="flex w-full items-center justify-center gap-1 rounded-xl border border-[#229ED9] py-2 text-sm font-medium text-[#229ED9]"
            >
              📦 설치 링크 열기 →
            </a>
          )}
        </div>

        {/* Discord */}
        <div className="space-y-2">
          <button
            type="button"
            onClick={handleDiscord}
            disabled={dcState === "loading"}
            className="flex w-full items-center justify-center gap-2 rounded-xl py-3 font-bold text-white transition-opacity disabled:opacity-60"
            style={{ backgroundColor: "#5865F2" }}
          >
            {dcState === "loading" ? (
              <span className="animate-pulse">연결 중…</span>
            ) : (
              <>
                <svg viewBox="0 0 24 24" className="h-5 w-5 fill-current">
                  <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057.1 18.084.117 18.11.143 18.126a19.919 19.919 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
                </svg>
                Discord 서버에 추가
              </>
            )}
          </button>

          {dcState === "done" && (
            <p className="text-center text-xs text-kakao-brown/60">
              Discord 창에서 서버 선택 후 허가하면 자동으로 업로드됩니다
            </p>
          )}
        </div>

        {/* 에러 메시지 */}
        {errMsg && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-center text-xs text-red-600">
            {errMsg}
          </p>
        )}

        <div className="pt-1 border-t border-kakao-brown/10 space-y-2">
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
      </div>
    </motion.div>
  );
}
