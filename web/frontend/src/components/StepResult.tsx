"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { downloadZipUrl, downloadSlackZipUrl, exportToTelegram, getDiscordBotInviteUrl, uploadToDiscord } from "@/lib/api";
import { openPortfolio } from "@/lib/portfolioClient";

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
  const [dcStep, setDcStep]       = useState<"idle" | "invited" | "done">("idle");
  const [dcBotUrl, setDcBotUrl]   = useState("");
  const [guildId, setGuildId]     = useState("");
  const [dcResult, setDcResult]   = useState<{ uploaded_count: number } | null>(null);
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

  const handleDiscordInvite = async () => {
    setDcState("loading");
    setErrMsg("");
    try {
      const { bot_invite_url } = await getDiscordBotInviteUrl();
      window.open(bot_invite_url, "_blank", "width=520,height=700");
      setDcBotUrl(bot_invite_url);
      setDcStep("invited");
      setDcState("idle");
    } catch (e: unknown) {
      setErrMsg(e instanceof Error ? e.message : "오류 발생");
      setDcState("error");
    }
  };

  const handleDiscordUpload = async () => {
    if (!guildId.trim()) {
      setErrMsg("서버 ID를 입력해 주세요");
      return;
    }
    setDcState("loading");
    setErrMsg("");
    try {
      const result = await uploadToDiscord(jobId, guildId.trim());
      setDcResult(result);
      setDcStep("done");
      setDcState("done");
    } catch (e: unknown) {
      setErrMsg(e instanceof Error ? e.message : "업로드 실패");
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
          {dcStep !== "done" && (
            <div className="space-y-2">
              {/* 봇 초대 버튼 */}
              <button
                type="button"
                onClick={handleDiscordInvite}
                disabled={dcState === "loading"}
                className="flex w-full items-center justify-center gap-2 rounded-xl py-3 font-bold text-white transition-opacity disabled:opacity-60"
                style={{ backgroundColor: "#5865F2" }}
              >
                {dcState === "loading" && !guildId ? (
                  <span className="animate-pulse">연결 중…</span>
                ) : (
                  <>
                    <svg viewBox="0 0 24 24" className="h-5 w-5 fill-current">
                      <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057.1 18.084.117 18.11.143 18.126a19.919 19.919 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
                    </svg>
                    {dcStep === "invited" ? "봇 재초대" : "① 봇 서버에 초대"}
                  </>
                )}
              </button>

              {/* 서버 ID 입력 — 항상 표시 */}
              <div className="rounded-xl border border-[#5865F2]/25 bg-[#5865F2]/5 p-3 space-y-2">
                <p className="text-xs text-kakao-brown/60">
                  ② Discord 설정 → 고급 → <strong>개발자 모드 ON</strong> → 서버 꾹 누르기 → ID 복사
                </p>
                <input
                  type="text"
                  value={guildId}
                  onChange={(e) => setGuildId(e.target.value)}
                  placeholder="서버 ID 붙여넣기 (18자리 숫자)"
                  className="w-full rounded-lg border border-kakao-brown/20 bg-white px-3 py-2 text-sm outline-none focus:border-[#5865F2]"
                />
                <button
                  type="button"
                  onClick={handleDiscordUpload}
                  disabled={dcState === "loading" || !guildId.trim()}
                  className="w-full rounded-lg py-2 text-sm font-bold text-white disabled:opacity-50"
                  style={{ backgroundColor: "#5865F2" }}
                >
                  {dcState === "loading" ? "업로드 중…" : "③ 스티커 업로드"}
                </button>
              </div>
            </div>
          )}

          {dcStep === "done" && dcResult && (
            <div className="rounded-xl bg-[#5865F2]/10 px-3 py-2 text-center text-xs text-[#5865F2] font-medium">
              ✅ Discord 스티커 {dcResult.uploaded_count}개 업로드 완료!
            </div>
          )}
        </div>

        {/* Slack */}
        <div className="space-y-1">
          <button
            type="button"
            onClick={() => window.open(downloadSlackZipUrl(jobId), "_blank")}
            className="flex w-full items-center justify-center gap-2 rounded-xl py-3 font-bold text-white"
            style={{ backgroundColor: "#4A154B" }}
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5 fill-current">
              <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zM8.834 6.313a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zM18.956 8.834a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zM17.688 8.834a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312zM15.165 18.956a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.522h2.52zM15.165 17.688a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z"/>
            </svg>
            Slack 이모지 다운로드 (ZIP)
          </button>
          <p className="text-center text-xs text-kakao-brown/50">
            다운로드 후 → slack.com/customize/emoji 에서 업로드
          </p>
        </div>

        {/* 에러 메시지 */}
        {errMsg && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-center text-xs text-red-600">
            {errMsg}
          </p>
        )}

        {/* 포트폴리오 */}
        <div className="rounded-xl bg-kakao-yellow/20 p-4 space-y-2 border border-kakao-yellow/50">
          <p className="text-center text-xs font-bold text-kakao-brown/80">
            ✨ 자녀·지인에게 자랑하기
          </p>
          <button
            type="button"
            onClick={() => openPortfolio(cuts, { date: new Date().toISOString().slice(0, 10) })}
            className="w-full rounded-xl bg-kakao-yellow py-3 font-bold text-kakao-brown flex items-center justify-center gap-2"
          >
            📋 포트폴리오 보기
          </button>
          <p className="text-center text-[11px] text-kakao-brown/50">
            브라우저에서 열어 인쇄·PDF 저장·링크 공유
          </p>
        </div>

        <div className="pt-1 border-t border-kakao-brown/10 space-y-2">
          <button
            type="button"
            onClick={saveAll}
            className="w-full rounded-xl bg-white border border-kakao-brown/15 py-3 font-bold text-kakao-brown"
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
