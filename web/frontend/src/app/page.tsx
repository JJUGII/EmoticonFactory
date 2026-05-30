"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BottomBar } from "@/components/BottomBar";
import { StepCandidates } from "@/components/StepCandidates";
import { StepEmotions } from "@/components/StepEmotions";
import { StepGenerate } from "@/components/StepGenerate";
import { StepResult } from "@/components/StepResult";
import { StepUpload } from "@/components/StepUpload";
import {
  fetchCandidates,
  fetchDefaultEmotions,
  fetchJob,
  fetchResult,
  generateCandidates,
  generateEmoticons,
  pollJob,
  selectCandidate,
  uploadPhoto,
  type CandidateItem,
  type JobStatus,
} from "@/lib/api";
import {
  createPreviewObjectUrl,
  logFileMeta,
  revokePreviewObjectUrl,
} from "@/lib/imageFile";

type Step = 1 | 2 | 3 | 4 | 5;

export default function HomePage() {
  const [step, setStep] = useState<Step>(1);
  const [jobId, setJobId] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [generator] = useState("openai");
  const [speciesHint, setSpeciesHint] = useState("");
  const [loading, setLoading] = useState(false);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [candidates, setCandidates] = useState<CandidateItem[]>([]);
  const [selectedCandidate, setSelectedCandidate] = useState<number | null>(null);
  const [emotions, setEmotions] = useState<string[]>([]);
  const [resultCuts, setResultCuts] = useState<
    { id: string; text: string; url?: string | null }[]
  >([]);
  const stopPollRef = useRef<(() => void) | null>(null);
  const previewBlobRef = useRef<string | null>(null);

  const clearPreviewBlob = useCallback(() => {
    revokePreviewObjectUrl(previewBlobRef.current);
    previewBlobRef.current = null;
  }, []);

  // ── URL 세션 복원 ─────────────────────────────────────────────────────
  const restoreSession = useCallback(async (id: string) => {
    try {
      const s = await fetchJob(id);
      setJobId(id);
      setJobStatus(s);
      if (s.phase === "completed") {
        const result = await fetchResult(id);
        setResultCuts(result.cuts);
        setStep(5);
      } else if (s.phase === "emoticons_running") {
        setStep(4);
        setLoading(true);
        stopPollRef.current?.();
        stopPollRef.current = pollJob(id, async (st) => {
          setJobStatus(st);
          if (st.phase === "completed") {
            const result = await fetchResult(id);
            setResultCuts(result.cuts);
            setStep(5);
            setLoading(false);
          }
          if (st.phase === "failed") setLoading(false);
        }, 2000, ["completed", "failed"]);
      } else if (s.phase === "canonical_selected") {
        setStep(3);
      } else if (s.phase === "candidates_ready") {
        const list = await fetchCandidates(id);
        setCandidates(list);
        setStep(2);
      } else if (s.phase === "candidates_running") {
        setStep(2);
        setLoading(true);
        stopPollRef.current?.();
        stopPollRef.current = pollJob(id, async (st) => {
          setJobStatus(st);
          if (st.phase === "candidates_ready") {
            const list = await fetchCandidates(id);
            setCandidates(list);
            setLoading(false);
          }
          if (st.phase === "failed") setLoading(false);
        }, 2000, ["candidates_ready", "failed"]);
      }
    } catch {
      // 복원 실패 시 그냥 step 1 유지
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // URL에서 job ID 복원
    const params = new URLSearchParams(window.location.search);
    const savedJobId = params.get("job");
    if (savedJobId) {
      restoreSession(savedJobId);
    }
    fetchDefaultEmotions().then(setEmotions);
    return () => {
      stopPollRef.current?.();
      clearPreviewBlob();
    };
  }, [clearPreviewBlob, restoreSession]);

  // jobId 변경 시 URL 업데이트
  useEffect(() => {
    if (jobId) {
      const url = new URL(window.location.href);
      url.searchParams.set("job", jobId);
      window.history.replaceState({}, "", url.toString());
    }
  }, [jobId]);

  const resetAll = useCallback(() => {
    setStep(1);
    setJobId(null);
    clearPreviewBlob();
    setPreviewUrl(null);
    setUploadError(null);
    setCandidates([]);
    setSelectedCandidate(null);
    setJobStatus(null);
    setResultCuts([]);
    fetchDefaultEmotions().then(setEmotions);
    // URL에서 job 파라미터 제거
    const url = new URL(window.location.href);
    url.searchParams.delete("job");
    window.history.replaceState({}, "", url.toString());
  }, [clearPreviewBlob]);

  const onUpload = async (file: File) => {
    logFileMeta(file);
    setUploadError(null);
    clearPreviewBlob();
    const blobUrl = createPreviewObjectUrl(file);
    previewBlobRef.current = blobUrl;
    setPreviewUrl(blobUrl);

    setLoading(true);
    try {
      const res = await uploadPhoto(file, { generator: "openai" });
      setJobId(res.job_id);
    } catch (e) {
      console.error("[UPLOAD_ERROR]", e);
      setUploadError(
        e instanceof Error ? e.message : "업로드에 실패했습니다. 잠시 후 다시 시도해 주세요."
      );
    } finally {
      setLoading(false);
    }
  };

  const onGenerateCandidates = async () => {
    if (!jobId) return;
    setStep(2);
    setLoading(true);
    setCandidates([]);
    try {
      // artStyle은 후보 선택 후 결정되므로 candidates 요청 시엔 무관 (백엔드가 양쪽 다 생성)
      await generateCandidates(jobId, generator, speciesHint, "illustration");
      stopPollRef.current?.();
      stopPollRef.current = pollJob(
        jobId,
        async (s) => {
          setJobStatus(s);
          if (s.phase === "candidates_ready") {
            const list = await fetchCandidates(jobId);
            setCandidates(list);
            setLoading(false);
          }
          if (s.phase === "failed") {
            setLoading(false);
            alert(s.error || "후보 생성 실패");
          }
        },
        2000,
        ["candidates_ready", "failed"]
      );
    } catch (e) {
      setLoading(false);
      alert(e instanceof Error ? e.message : "요청 실패");
    }
  };

  const onConfirmCandidate = async () => {
    if (!jobId || selectedCandidate == null) return;
    setLoading(true);
    try {
      await selectCandidate(jobId, selectedCandidate);
      setStep(3);
    } catch (e) {
      alert(e instanceof Error ? e.message : "선택 실패");
    } finally {
      setLoading(false);
    }
  };

  const onGenerateEmoticons = async () => {
    if (!jobId) return;
    setStep(4);
    setLoading(true);
    try {
      // 선택한 후보 번호로 스타일 자동 결정: 1,2=일러스트 / 3,4=실사풍 (파이프라인 1-based)
      const inferredStyle = (selectedCandidate ?? 0) >= 3 ? "realistic" : "illustration";
      const initial = await generateEmoticons(jobId, emotions, generator, true, inferredStyle);
      setJobStatus(initial);
      stopPollRef.current?.();
      stopPollRef.current = pollJob(
        jobId,
        async (s) => {
          setJobStatus(s);
          if (s.phase === "completed") {
            const result = await fetchResult(jobId);
            setResultCuts(result.cuts);
            setStep(5);
            setLoading(false);
          }
          if (s.phase === "failed") {
            setLoading(false);
            alert(s.error || "생성 실패");
          }
        },
        2000,
        ["completed", "failed"]
      );
    } catch (e) {
      setLoading(false);
      alert(e instanceof Error ? e.message : "요청 실패");
    }
  };

  let bottomLabel = "다음";
  let bottomAction = () => {};
  let bottomDisabled = true;

  if (step === 1) {
    bottomLabel = "다음";
    bottomDisabled = !previewUrl || !jobId;
    bottomAction = () => setStep(2);
  } else if (step === 2) {
    if (candidates.length === 0) {
      bottomLabel = "캐릭터 후보 생성하기";
      bottomDisabled = loading;
      bottomAction = onGenerateCandidates;
    } else {
      bottomLabel = "이 캐릭터로 진행하기";
      bottomDisabled = selectedCandidate == null || loading;
      bottomAction = onConfirmCandidate;
    }
  } else if (step === 3) {
    bottomLabel = "이모티콘 생성하기";
    bottomDisabled = emotions.some((t) => !t.trim()) || loading;
    bottomAction = onGenerateEmoticons;
  } else if (step === 5) {
    bottomLabel = "";
  }

  return (
    <main className="relative isolate mx-auto min-h-screen max-w-lg px-4 pb-32 pt-8">
      <header className="relative z-10 mb-6 text-center">
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="inline-block rounded-full bg-kakao-yellow/80 px-3 py-1 text-xs font-bold"
        >
          v0.8 Web
        </motion.p>
        <h1 className="mt-2 text-lg font-bold text-kakao-brown">이모티콘 스튜디오</h1>
      </header>

      <div className="relative z-10">
      <AnimatePresence mode="wait">
        {step === 1 && (
          <motion.div key="s1" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="relative z-10">
            <StepUpload
              previewUrl={previewUrl}
              uploadError={uploadError}
              uploading={loading}
              onFile={onUpload}
              onFileError={setUploadError}
              speciesHint={speciesHint}
              onSpeciesHintChange={setSpeciesHint}
            />
          </motion.div>
        )}
        {step === 2 && (
          <motion.div key="s2" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} className="relative z-10">
            <StepCandidates
              loading={loading && candidates.length === 0}
              message={jobStatus?.message || ""}
              candidates={candidates}
              selected={selectedCandidate}
              onSelect={setSelectedCandidate}
            />
          </motion.div>
        )}
        {step === 3 && (
          <motion.div key="s3" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
            <StepEmotions emotions={emotions} onChange={setEmotions} />
          </motion.div>
        )}
        {step === 4 && (
          <motion.div key="s4" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
            <StepGenerate
              message={jobStatus?.message ?? "이모티콘 생성 준비 중..."}
              progress={jobStatus?.progress ?? 0}
              cuts={jobStatus?.cuts ?? emotions.map((t, i) => ({
                id: String(i + 1).padStart(2, "0"),
                text: t,
                status: "pending" as const,
              }))}
              currentCut={jobStatus?.current_cut}
            />
          </motion.div>
        )}
        {step === 5 && jobId && (
          <motion.div key="s5" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
            <StepResult
              jobId={jobId}
              cuts={resultCuts}
              onRestart={resetAll}
              onReselect={() => {
                setStep(2);
                setSelectedCandidate(null);
              }}
            />
          </motion.div>
        )}
      </AnimatePresence>
      </div>

      {step !== 5 && bottomLabel && (
        <BottomBar
          label={bottomLabel}
          onClick={bottomAction}
          disabled={bottomDisabled}
          loading={loading}
        />
      )}
    </main>
  );
}
