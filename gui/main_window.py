"""Main Qt window for the emoticon generator GUI (v0.1)."""

from __future__ import annotations

import webbrowser
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QDialog,
    QCheckBox,
    QDoubleSpinBox,
)

from config import PROJECT_ROOT
from gui.candidate_dialog import CandidateDialog
from gui.styles import APP_STYLESHEET
from gui.widgets import ImageCard, ResultGridWidget
from gui.worker import (
    CandidateGenerationWorker,
    CharacterSheetWorker,
    EmoticonPipelineWorker,
)
from services.base_character_prompt import CANONICAL_BASE_POLICY_KO
from services.canonical_character_manager import (
    CanonicalCharacterManager,
    SELECTED_BASE_CANDIDATE_TYPE,
)
from services.identity_lock import clamp_strength
from services.identity_profile_analyzer import IdentityProfileAnalyzer
from services.candidate_feedback import write_candidate_feedback
from services.package_builder import PackageBuilder
from services.pipeline_runner import PipelineOptions, PipelineRunner
from services.reference_classifier import ReferenceClassifier


def _safe_folder_name(series_name: str) -> str:
    s = series_name.strip().replace(" ", "_")
    for ch in '<>:"/\\|?*':
        s = s.replace(ch, "_")
    s = s.strip("._") or "package"
    return s[:200]


class MainWindow(QWidget):
    """Pet emoticon generator — thin shell over ``app.py`` + workers."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(APP_STYLESHEET)

        self._photo_path: str | None = None
        self._selected_candidate: int | None = None
        self._thread: QThread | None = None
        self._worker: QObject | None = None

        self._runner = PipelineRunner(project_root=PROJECT_ROOT)

        root = QVBoxLayout(self)

        top = QGroupBox("입력")
        tg = QGridLayout(top)
        self._btn_photo = QPushButton("1) 사진 선택")
        self._btn_photo.clicked.connect(self._pick_photo)
        self._preview = QLabel("미리보기 없음")
        self._preview.setMinimumSize(180, 180)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._series = QLineEdit("우리집 귀찮냥")
        self._theme = QLineEdit("사랑")
        self._species = QComboBox()
        for s in (
            "auto",
            "human",
            "baby",
            "cat",
            "dog",
            "rabbit",
            "hamster",
            "bird",
            "couple",
            "family",
            "unknown",
        ):
            self._species.addItem(s)
        self._entity_label = QLabel("입력 타입: (미분석)")
        self._entity_label.setWordWrap(True)
        self._personality = QLineEdit()
        self._generator = QComboBox()
        self._generator.addItems(["mock", "openai"])
        self._ref_type = QComboBox()
        self._ref_type.addItems(["auto", "photo", "character_art"])
        tg.addWidget(self._btn_photo, 0, 0)
        tg.addWidget(self._preview, 0, 1, 3, 1)
        tg.addWidget(QLabel("시리즈명"), 1, 0)
        tg.addWidget(self._series, 1, 1)
        tg.addWidget(QLabel("테마"), 2, 0)
        tg.addWidget(self._theme, 2, 1)
        tg.addWidget(QLabel("종 힌트"), 3, 0)
        tg.addWidget(self._species, 3, 1)
        tg.addWidget(QLabel("성격 힌트"), 4, 0)
        tg.addWidget(self._personality, 4, 1)
        tg.addWidget(QLabel("generator"), 5, 0)
        tg.addWidget(self._generator, 5, 1)
        tg.addWidget(QLabel("reference_type"), 6, 0)
        tg.addWidget(self._ref_type, 6, 1)
        self._style_intensity = QDoubleSpinBox()
        self._style_intensity.setRange(0.0, 1.0)
        self._style_intensity.setSingleStep(0.1)
        self._style_intensity.setDecimals(2)
        self._style_intensity.setValue(0.5)
        tg.addWidget(QLabel("style_intensity"), 7, 0)
        tg.addWidget(self._style_intensity, 7, 1)
        self._pose_strength = QDoubleSpinBox()
        self._pose_strength.setRange(0.0, 1.0)
        self._pose_strength.setSingleStep(0.1)
        self._pose_strength.setValue(1.0)
        self._expr_strength = QDoubleSpinBox()
        self._expr_strength.setRange(0.0, 1.0)
        self._expr_strength.setSingleStep(0.1)
        self._expr_strength.setValue(1.0)
        tg.addWidget(QLabel("pose_variation"), 8, 0)
        tg.addWidget(self._pose_strength, 8, 1)
        tg.addWidget(QLabel("expression"), 9, 0)
        tg.addWidget(self._expr_strength, 9, 1)
        tg.addWidget(self._entity_label, 10, 0, 1, 2)
        root.addWidget(top)

        advanced = QGroupBox("고급 옵션 (character sheet)")
        ag = QGridLayout(advanced)
        self._chk_use_sheet = QCheckBox("캐릭터 시트 기준 (--use-character-sheet)")
        self._chk_use_sheet.setChecked(False)
        self._sheet_gen = QComboBox()
        self._sheet_gen.addItems(["mock", "openai"])
        self._btn_sheet = QPushButton("캐릭터 시트 생성 (고급)")
        self._btn_sheet.clicked.connect(self._run_character_sheet)
        self._btn_canonical = QPushButton("입력 이미지를 canonical으로 직접 고정 (고급)")
        self._btn_canonical.clicked.connect(self._fix_canonical_from_photo)
        ag.addWidget(self._chk_use_sheet, 0, 0, 1, 2)
        ag.addWidget(QLabel("sheet_generator"), 1, 0)
        ag.addWidget(self._sheet_gen, 1, 1)
        ag.addWidget(self._btn_sheet, 2, 0, 1, 2)
        ag.addWidget(self._btn_canonical, 3, 0, 1, 2)
        root.addWidget(advanced)

        mid = QHBoxLayout()
        canon_col = QVBoxLayout()
        canon_col.addWidget(QLabel("Canonical reference (고정)"))
        self._canon_preview = QLabel("canonical_character: (없음)")
        self._canon_preview.setMinimumSize(200, 220)
        self._canon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canon_col.addWidget(self._canon_preview)
        self._canonical_label = QLabel("canonical: (미설정)")
        canon_col.addWidget(self._canonical_label)
        canon_col.addStretch(1)
        mid.addLayout(canon_col, stretch=0)

        left = QVBoxLayout()
        self._btn_candidates = QPushButton("2) 베이스 캐릭터 후보 3장 생성")
        self._btn_candidates.clicked.connect(self._run_candidates)
        self._btn_test = QPushButton("3) 선택 캐릭터로 3컷 테스트")
        self._btn_test.clicked.connect(self._run_test_cuts)
        self._btn_full = QPushButton("4) 선택 캐릭터로 16컷 생성")
        self._btn_full.clicked.connect(self._run_full_cuts)
        self._btn_preview = QPushButton("5) preview.html 열기")
        self._btn_preview.clicked.connect(self._open_preview)
        self._btn_folder = QPushButton("6) 출력 폴더 열기")
        self._btn_folder.clicked.connect(self._open_folder)
        self._btn_full_reset = QPushButton("전체 초기화 (--full-reset)")
        self._btn_full_reset.setToolTip(
            "outputs/<series> 폴더 전체 삭제. 일반 생성은 후보·캐논을 유지합니다(--overwrite)."
        )
        self._btn_full_reset.clicked.connect(self._run_full_reset)
        for b in (
            self._btn_candidates,
            self._btn_test,
            self._btn_full,
            self._btn_preview,
            self._btn_folder,
            self._btn_full_reset,
        ):
            left.addWidget(b)
        left.addStretch(1)

        center = QVBoxLayout()
        self._cand_row = QHBoxLayout()
        self._cand_cards: list[ImageCard] = []
        for i in range(3):
            card = ImageCard(f"후보 {i + 1}", None)
            idx = i + 1

            def _mk_click(j: int):
                return lambda: self._select_candidate_card(j)

            card.clicked.connect(_mk_click(idx))
            self._cand_cards.append(card)
            self._cand_row.addWidget(card)
        center.addLayout(self._cand_row)
        self._sheet_preview = QLabel("canonical_sheet (고급): (없음)")
        self._sheet_preview.setMinimumHeight(80)
        self._sheet_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sheet_preview.setVisible(False)
        center.addWidget(self._sheet_preview)
        self._result_grid = ResultGridWidget()
        self._result_grid.regenerate_requested.connect(self._regenerate_cut)
        center.addWidget(self._result_grid, stretch=1)

        mid.addLayout(left, stretch=0)
        mid.addLayout(center, stretch=1)
        root.addLayout(mid, stretch=1)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(140)
        self._progress = QProgressBar()
        self._status = QLabel("준비")
        root.addWidget(self._progress)
        root.addWidget(self._status)
        root.addWidget(self._log)

    def _package_dir(self) -> Path:
        out = PROJECT_ROOT / "outputs" / _safe_folder_name(self._series.text())
        return out

    def _species_hint(self) -> str:
        s = self._species.currentText().strip().lower()
        return "" if s == "auto" else s

    def _pick_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "반려동물 사진 선택",
            str(PROJECT_ROOT),
            "Images (*.png *.jpg *.jpeg *.webp)",
        )
        if not path:
            return
        self._photo_path = path
        pix = QPixmap(path)
        if not pix.isNull():
            self._preview.setPixmap(
                pix.scaled(
                    200,
                    200,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self._log.append(f"[사진] {path}")
        self._status.setText("사진 선택됨")
        self._analyze_entity_type(Path(path))

    def _ensure_dirs(self) -> Path:
        pkg = self._package_dir()
        PackageBuilder(PROJECT_ROOT / "outputs").ensure_package_dirs(pkg)
        return pkg

    def _fix_canonical_from_photo(self) -> None:
        if not self._photo_path:
            QMessageBox.warning(self, "canonical", "먼저 사진을 선택하세요.")
            return
        try:
            pkg = self._ensure_dirs()
            CanonicalCharacterManager().set_from_existing_image(
                Path(self._photo_path),
                pkg,
                "gui_user_selected_photo_as_canonical",
                {"original_reference": self._photo_path},
            )
        except OSError as exc:
            QMessageBox.critical(self, "canonical", str(exc))
            return
        self._ref_type.setCurrentText("character_art")
        self._canonical_label.setText("canonical: character/canonical_character.png (사진 복사)")
        self._refresh_canon_thumbnail()
        self._log.append("[canonical] 현재 사진을 고정했습니다.")
        QMessageBox.information(self, "canonical", "character/canonical_character.png 로 저장했습니다.")

    def _select_candidate_card(self, one_based: int) -> None:
        self._selected_candidate = one_based
        for i, c in enumerate(self._cand_cards):
            c.set_selected(i + 1 == one_based)
        self._canonical_label.setText(f"선택된 후보: candidate_{one_based:02d}.png (미고정 — 다이얼로그에서 확정 필요)")

    def _commit_selected_candidate(self, one_based: int) -> bool:
        pkg = self._package_dir()
        cand_path = pkg / "character_candidates" / f"candidate_{one_based:02d}.png"
        if not cand_path.is_file():
            QMessageBox.warning(self, "선택", f"후보 파일이 없습니다: {cand_path}")
            return False
        try:
            CanonicalCharacterManager().set_from_existing_image(
                cand_path,
                pkg,
                SELECTED_BASE_CANDIDATE_TYPE,
                {
                    "original_reference": str(cand_path.resolve()),
                    "candidate_index": one_based,
                    "policy": CANONICAL_BASE_POLICY_KO,
                },
            )
        except OSError as exc:
            QMessageBox.critical(self, "canonical", str(exc))
            return False
        self._selected_candidate = one_based
        self._canonical_label.setText("canonical_character.png 고정 완료")
        write_candidate_feedback(
            pkg,
            selected_candidate=one_based,
            candidate_count=3,
            source_reference=str(cand_path.resolve()),
            canonical_sheet_used=False,
        )
        self._refresh_canon_thumbnail()
        return True

    def _options_base(self) -> PipelineOptions:
        if not self._photo_path:
            raise ValueError("사진을 선택하세요.")
        sp = self._species_hint()
        return PipelineOptions(
            character_path=self._photo_path,
            series_name=self._series.text().strip(),
            theme=self._theme.text().strip(),
            species_hint=sp if sp else "unknown",
            personality_hint=self._personality.text(),
            reference_type=self._ref_type.currentText(),
            stylizer="none",
            generator=self._generator.currentText(),
            overwrite=True,
            make_preview=True,
            output_root=str(PROJECT_ROOT / "outputs"),
            use_character_sheet=False,
            sheet_generator=self._sheet_gen.currentText().strip().lower() or "mock",
            style_intensity=float(self._style_intensity.value()),
            pose_variation_strength=clamp_strength(float(self._pose_strength.value())),
            expression_strength=clamp_strength(float(self._expr_strength.value())),
        )

    def _cleanup_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(8000)
        self._thread = None
        self._worker = None

    def _run_candidates(self) -> None:
        if not self._photo_path:
            QMessageBox.warning(self, "후보", "사진을 선택하세요.")
            return
        self._cleanup_thread()
        try:
            opts = self._options_base()
        except ValueError as exc:
            QMessageBox.warning(self, "입력", str(exc))
            return
        opts = PipelineOptions(**{**opts.__dict__, "make_candidates": True, "candidate_count": 3})
        self._btn_candidates.setEnabled(False)
        self._progress.setValue(0)
        self._log.append("[후보] subprocess 실행…")

        th = QThread()
        worker = CandidateGenerationWorker(self._runner, opts)
        worker.moveToThread(th)
        th.started.connect(worker.run)
        worker.log.connect(self._append_log)
        worker.progress.connect(self._progress.setValue)
        worker.finished.connect(self._on_candidates_done)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(th.quit)
        worker.failed.connect(th.quit)
        th.finished.connect(lambda: self._btn_candidates.setEnabled(True))
        self._thread = th
        self._worker = worker
        th.start()

    @Slot(object)
    def _on_candidates_done(self, result: object) -> None:
        self._log.append(f"[후보] 완료 returncode={getattr(result, 'returncode', '?')}")
        pkg = self._package_dir()
        cand_dir = pkg / "character_candidates"
        paths = sorted(cand_dir.glob("candidate_*.png"))
        for i, card in enumerate(self._cand_cards):
            p = paths[i] if i < len(paths) else None
            card.set_image_path(p)
        dlg = CandidateDialog(paths[:3], self, candidates_dir=cand_dir)
        code = dlg.exec()
        if code == CandidateDialog.REGENERATE_CODE:
            self._run_candidates()
            return
        if code == QDialog.Accepted:
            sel = dlg.selected_index_1based()
            if sel:
                self._select_candidate_card(sel)
                self._commit_selected_candidate(sel)
        self._reload_result_grid()
        self._refresh_sheet_thumbnail()

    def _run_character_sheet(self) -> None:
        if not self._photo_path:
            QMessageBox.warning(self, "시트", "사진을 선택하세요.")
            return
        self._cleanup_thread()
        try:
            opts = self._options_base()
        except ValueError as exc:
            QMessageBox.warning(self, "입력", str(exc))
            return
        opts = PipelineOptions(
            **{
                **opts.__dict__,
                "make_character_sheet": True,
                "sheet_generator": self._sheet_gen.currentText().strip().lower() or "mock",
            }
        )
        self._btn_sheet.setEnabled(False)
        self._progress.setValue(0)
        self._log.append("[시트] subprocess 실행…")
        th = QThread()
        worker = CharacterSheetWorker(self._runner, opts)
        worker.moveToThread(th)
        th.started.connect(worker.run)
        worker.log.connect(self._append_log)
        worker.progress.connect(self._progress.setValue)
        worker.finished.connect(self._on_sheet_done)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(th.quit)
        worker.failed.connect(th.quit)
        th.finished.connect(lambda: self._btn_sheet.setEnabled(True))
        self._thread = th
        self._worker = worker
        th.start()

    @Slot(object)
    def _on_sheet_done(self, result: object) -> None:
        self._log.append(f"[시트] 완료 returncode={getattr(result, 'returncode', '?')}")
        self._refresh_sheet_thumbnail()

    def _refresh_sheet_thumbnail(self) -> None:
        pkg = self._package_dir()
        sp = pkg / "character" / "canonical_sheet.png"
        if sp.is_file():
            pix = QPixmap(str(sp))
            if not pix.isNull():
                self._sheet_preview.setPixmap(
                    pix.scaled(
                        320,
                        200,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self._sheet_preview.setToolTip(str(sp))
                self._refresh_canon_thumbnail()
                return
        self._sheet_preview.clear()
        self._sheet_preview.setText("canonical_sheet: (없음)")
        self._refresh_canon_thumbnail()

    def _refresh_canon_thumbnail(self) -> None:
        pkg = self._package_dir()
        cp = CanonicalCharacterManager.get_canonical_path(pkg)
        if cp is not None and cp.is_file():
            pix = QPixmap(str(cp))
            if not pix.isNull():
                self._canon_preview.setPixmap(
                    pix.scaled(
                        300,
                        300,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self._canon_preview.setToolTip(str(cp))
                return
        self._canon_preview.clear()
        self._canon_preview.setText("canonical_character: (없음)")

    @Slot(str)
    def _on_worker_failed(self, msg: str) -> None:
        self._log.append(f"[오류] {msg}")
        QMessageBox.critical(self, "오류", msg)

    def _append_log(self, line: str) -> None:
        self._log.append(line)
        self._status.setText(line[:120])

    def _run_test_cuts(self) -> None:
        if not self._photo_path:
            QMessageBox.warning(self, "실행", "사진을 선택하세요.")
            return
        pkg = self._package_dir()
        has_canon = CanonicalCharacterManager.get_canonical_path(pkg) is not None
        if not has_canon:
            QMessageBox.warning(
                self,
                "실행",
                "먼저 「베이스 캐릭터 후보 3장 생성」 후 1장을 선택해 canonical_character.png 를 고정하세요.",
            )
            return
        self._run_pipeline(test_ids="01,02,03", select_candidate=self._selected_candidate)

    def _run_full_reset(self) -> None:
        if not self._series.text().strip():
            QMessageBox.warning(self, "전체 초기화", "시리즈 이름을 입력하세요.")
            return
        pkg = self._package_dir()
        if not pkg.is_dir():
            QMessageBox.information(self, "전체 초기화", "삭제할 출력 폴더가 없습니다.")
            return
        ok = QMessageBox.question(
            self,
            "전체 초기화",
            f"다음 폴더를 전부 삭제합니다:\n{pkg}\n\n"
            "후보·캐논·생성 결과가 모두 제거됩니다. 계속할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ok != QMessageBox.StandardButton.Yes:
            return
        self._cleanup_thread()
        try:
            opts = self._options_base()
        except ValueError as exc:
            QMessageBox.warning(self, "입력", str(exc))
            return
        opts = PipelineOptions(
            **{
                **opts.__dict__,
                "full_reset": True,
                "reset_only": True,
                "overwrite": False,
                "make_candidates": False,
                "test_ids": "",
                "select_candidate": None,
            }
        )
        self._btn_full_reset.setEnabled(False)
        self._progress.setValue(0)
        self._log.append("[전체 초기화] subprocess --full-reset …")

        th = QThread()
        worker = EmoticonPipelineWorker(self._runner, opts)
        worker.moveToThread(th)
        th.started.connect(worker.run)
        worker.log.connect(self._append_log)
        worker.progress.connect(self._progress.setValue)
        worker.finished.connect(self._on_full_reset_done)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(th.quit)
        worker.failed.connect(th.quit)
        th.finished.connect(lambda: self._btn_full_reset.setEnabled(True))
        self._thread = th
        self._worker = worker
        th.start()

    @Slot(object)
    def _on_full_reset_done(self, result: object) -> None:
        rc = getattr(result, "returncode", 1)
        self._log.append(f"[전체 초기화] 종료 code={rc}")
        self._selected_candidate = None
        self._canonical_label.setText("canonical: (미설정)")
        self._canon_preview.setText("canonical_character: (없음)")
        self._reload_result_grid()
        if rc == 0:
            QMessageBox.information(
                self,
                "전체 초기화",
                "시리즈 출력 폴더가 삭제되었습니다. 처음부터 후보 생성을 진행하세요.",
            )

    def _run_full_cuts(self) -> None:
        if not self._photo_path:
            QMessageBox.warning(self, "실행", "사진을 선택하세요.")
            return
        pkg = self._package_dir()
        has_canon = CanonicalCharacterManager.get_canonical_path(pkg) is not None
        if not has_canon:
            QMessageBox.warning(
                self,
                "실행",
                "먼저 「베이스 캐릭터 후보 3장 생성」 후 1장을 선택해 canonical_character.png 를 고정하세요.",
            )
            return
        self._run_pipeline(test_ids="", select_candidate=self._selected_candidate)

    def _run_pipeline(
        self,
        *,
        test_ids: str,
        select_candidate: int | None,
        auto_regenerate: bool = False,
    ) -> None:
        self._cleanup_thread()
        try:
            opts = self._options_base()
        except ValueError as exc:
            QMessageBox.warning(self, "입력", str(exc))
            return
        opts = PipelineOptions(
            **{
                **opts.__dict__,
                "test_ids": test_ids,
                "test_one": False,
                "select_candidate": select_candidate,
                "auto_regenerate": auto_regenerate,
            }
        )
        self._btn_test.setEnabled(False)
        self._btn_full.setEnabled(False)
        self._progress.setValue(0)
        self._log.append("[파이프라인] subprocess 실행…")

        th = QThread()
        worker = EmoticonPipelineWorker(self._runner, opts)
        worker.moveToThread(th)
        th.started.connect(worker.run)
        worker.log.connect(self._append_log)
        worker.progress.connect(self._progress.setValue)
        worker.finished.connect(self._on_pipeline_done)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(th.quit)
        worker.failed.connect(th.quit)
        th.finished.connect(lambda: self._btn_test.setEnabled(True))
        th.finished.connect(lambda: self._btn_full.setEnabled(True))
        self._thread = th
        self._worker = worker
        th.start()

    @Slot(object)
    def _on_pipeline_done(self, result: object) -> None:
        rc = getattr(result, "returncode", 1)
        self._log.append(f"[파이프라인] 종료 code={rc}")
        self._reload_result_grid()
        if rc == 0:
            self._open_preview()

    def _analyze_entity_type(self, path: Path) -> None:
        try:
            rc = ReferenceClassifier().analyze(path)
            ident = IdentityProfileAnalyzer().analyze(
                path,
                species_hint=self._species_hint() or None,
                reference_type=rc.reference_type,
            )
            self._entity_label.setText(
                f"입력 타입: {ident.entity_type} "
                f"(confidence={ident.entity_type_confidence:.2f}) · "
                f"{', '.join(ident.entity_type_reasons[:2])}"
            )
            if ident.entity_type in ("human", "baby", "couple", "family"):
                self._species.setCurrentText(ident.entity_type)
        except OSError:
            self._entity_label.setText("입력 타입: 분석 실패")

    def _regenerate_cut(self, cut_id: str) -> None:
        if not self._photo_path:
            QMessageBox.warning(self, "재생성", "사진을 선택하세요.")
            return
        cid = str(cut_id).zfill(2)
        self._log.append(f"[재생성] 컷 {cid} — subprocess")
        self._run_pipeline(
            test_ids=cid,
            select_candidate=self._selected_candidate,
            auto_regenerate=True,
        )

    def _reload_result_grid(self) -> None:
        pkg = self._package_dir()
        if pkg.is_dir():
            self._result_grid.load_from_package_dir(pkg)
        self._refresh_sheet_thumbnail()
        self._refresh_canon_thumbnail()

    def _open_preview(self) -> None:
        prev = self._package_dir() / "preview.html"
        if prev.is_file():
            webbrowser.open(prev.as_uri())
        else:
            QMessageBox.information(self, "미리보기", "preview.html 이 없습니다. 파이프라인을 먼저 실행하세요.")

    def _open_folder(self) -> None:
        pkg = self._package_dir()
        pkg.mkdir(parents=True, exist_ok=True)
        webbrowser.open(pkg.as_uri())
