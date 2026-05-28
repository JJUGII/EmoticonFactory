"""Background workers (QThread) for candidate generation and pipeline runs."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from services.pipeline_runner import PipelineOptions, PipelineRunner


@dataclass
class WorkerFailed:
    message: str


class CandidateGenerationWorker(QObject):
    log = Signal(str)
    progress = Signal(int)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, runner: PipelineRunner, options: PipelineOptions) -> None:
        super().__init__()
        self._runner = runner
        self._options = options

    @Slot()
    def run(self) -> None:
        try:
            self.progress.emit(10)
            self.log.emit("후보 생성 subprocess 시작…")

            def sink(msg: str) -> None:
                self.log.emit(msg)

            res = self._runner.generate_candidates(self._options, log=sink)
            self.progress.emit(100)
            self.finished.emit(res)
        except Exception as exc:
            self.failed.emit(str(exc))


class EmoticonPipelineWorker(QObject):
    log = Signal(str)
    progress = Signal(int)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, runner: PipelineRunner, options: PipelineOptions) -> None:
        super().__init__()
        self._runner = runner
        self._options = options

    @Slot()
    def run(self) -> None:
        try:
            self.progress.emit(10)
            self.log.emit("이모티콘 파이프라인 subprocess 시작…")

            def sink(msg: str) -> None:
                self.log.emit(msg)

            res = self._runner.run_emoticon_pipeline(self._options, log=sink)
            self.progress.emit(100)
            self.finished.emit(res)
        except Exception as exc:
            self.failed.emit(str(exc))


class CharacterSheetWorker(QObject):
    """Background job for ``--make-character-sheet``."""

    log = Signal(str)
    progress = Signal(int)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, runner: PipelineRunner, options: PipelineOptions) -> None:
        super().__init__()
        self._runner = runner
        self._options = options

    @Slot()
    def run(self) -> None:
        try:
            self.progress.emit(10)
            self.log.emit("캐릭터 시트 subprocess 시작…")

            def sink(msg: str) -> None:
                self.log.emit(msg)

            res = self._runner.generate_character_sheet(self._options, log=sink)
            self.progress.emit(100)
            self.finished.emit(res)
        except Exception as exc:
            self.failed.emit(str(exc))
