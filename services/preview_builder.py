"""Build a static HTML preview report for a generated emoticon package."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def _esc(s: Any) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _is_cut16(cid: str) -> bool:
    return len(cid) == 2 and cid.isdigit() and 1 <= int(cid) <= 16


def _failed_cut_ids(
    *,
    consistency_report: dict[str, Any] | None,
    qc_report: dict[str, Any],
    generation_log: dict[str, Any] | None,
) -> set[str]:
    ids: set[str] = set()
    if consistency_report:
        for row in consistency_report.get("failed") or []:
            if isinstance(row, dict) and row.get("id") is not None:
                sid = str(row["id"])
                if _is_cut16(sid):
                    ids.add(sid)
        for row in consistency_report.get("items") or []:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("id", ""))
            if _is_cut16(sid) and str(row.get("status", "")).lower() == "fail":
                ids.add(sid)
    for k in (qc_report.get("per_cut_png_errors") or {}):
        ids.add(str(k))
    for k in (qc_report.get("per_cut_icon_errors") or {}):
        ids.add(str(k))
    if generation_log:
        for cut in generation_log.get("cuts") or []:
            if isinstance(cut, dict) and not cut.get("success") and cut.get("id") is not None:
                ids.add(str(cut["id"]))
    return ids


def _consistency_by_id(report: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not report:
        return out
    for row in report.get("items") or []:
        if isinstance(row, dict) and row.get("id") is not None:
            out[str(row["id"])] = row
    return out


def _webp_by_cut(webp_report: dict[str, Any] | None) -> dict[str, str]:
    m: dict[str, str] = {}
    if not webp_report:
        return m
    for it in webp_report.get("items") or []:
        if not isinstance(it, dict):
            continue
        cid = str(it.get("id", ""))
        rel = it.get("relative_path")
        if cid and isinstance(rel, str) and rel.strip():
            m[cid] = rel.replace("\\", "/")
    return m


def _drift_heatmap_html(cut_ids: list[str], cons_map: dict[str, dict[str, Any]]) -> str:
    cells: list[str] = []
    for cid in cut_ids:
        row = cons_map.get(cid, {})
        ds = row.get("canonical_identity_score", row.get("drift_similarity", ""))
        title = (
            f"{cid}: canonical_identity={row.get('canonical_identity_score', '—')} "
            f"drift_similarity={row.get('drift_similarity', '—')}"
        )
        bg = "#e0e0e0"
        try:
            v = float(ds)
            v = max(0.0, min(1.0, v))
            r = int(40 + 215 * (1.0 - v))
            g = int(80 + 160 * v)
            b = int(70 + 120 * (1.0 - abs(v - 0.65)))
            bg = f"rgb({r},{g},{b})"
        except (TypeError, ValueError):
            pass
        cells.append(
            f'<div class="dcell" style="background:{bg}" title="{_esc(title)}">'
            f'<span class="dlabel">{_esc(cid)}</span></div>'
        )
    inner = "".join(cells) or "<p class='muted'>일관성 리포트 없음</p>"
    return (
        '<div class="card"><h2>Identity drift heatmap (canonical_identity / drift)</h2>'
        "<p class='muted'>색이 붉을수록 canonical_identity·drift 유사도가 낮음. "
        "초록에 가까울수록 동일 존재로 유지됨. 회색=데이터 없음.</p>"
        f'<div class="drift-grid">{inner}</div></div>'
    )


def _rejected_cuts_html(
    package_dir: Path,
    emoticon_subdir: str,
    failed_ids: set[str],
    cons_map: dict[str, dict[str, Any]],
    qc_report: dict[str, Any],
) -> str:
    if not failed_ids:
        return ""
    rows: list[str] = []
    for cid in sorted(failed_ids, key=lambda x: int(x) if str(x).isdigit() else 0):
        png_rel = f"./{emoticon_subdir}/{cid}.png"
        pth = package_dir / emoticon_subdir / f"{cid}.png"
        img = (
            f'<img class="rej-thumb" src="{_esc(png_rel)}" alt="cut {cid}" loading="lazy" />'
            if pth.is_file()
            else "<div class='rej-miss'>PNG 없음</div>"
        )
        issues: list[str] = []
        crow = cons_map.get(cid, {})
        if isinstance(crow.get("issues"), list):
            issues.extend(str(x) for x in crow["issues"][:8])
        qe_png = (qc_report.get("per_cut_png_errors") or {}).get(cid)
        qe_ic = (qc_report.get("per_cut_icon_errors") or {}).get(cid)
        if qe_png:
            issues.append(f"QC PNG: {qe_png!s}")
        if qe_ic:
            issues.append(f"QC icon: {qe_ic!s}")
        li = "".join(f"<li>{_esc(x)}</li>" for x in issues[:10]) or "<li>—</li>"
        rows.append(
            f'<div class="rej-row"><div>{img}</div><div class="rej-meta">'
            f"<strong>{_esc(cid)}</strong><ul class='mini'>{li}</ul></div></div>"
        )
    body = "".join(rows)
    return (
        '<div class="card"><h2>Rejected / 문제 컷</h2>'
        "<p class='muted'>일관성 실패·QC 오류·생성 실패로 표시된 컷 요약입니다.</p>"
        f'<div class="rej-wrap">{body}</div></div>'
    )


def _stylizer_status_ko(backend: str) -> str:
    b = str(backend or "").strip().lower()
    if b == "none":
        return "원본 사진 기반 직접 생성"
    if b == "openai":
        return "AI 표준 캐릭터 기반 생성 — 캐릭터 드리프트 가능"
    if b == "mock":
        return "개발용 목업 — 품질 판단 금지"
    return "—"


def _pet_profile_summary_html(pet: dict[str, Any]) -> str:
    if not pet:
        return "<p class='muted'>PetProfile 메타가 없습니다.</p>"
    colors = ", ".join(str(x) for x in (pet.get("main_colors") or [])[:8])
    pers = ", ".join(str(x) for x in (pet.get("personality_keywords") or [])[:4])
    return (
        "<ul class='mini'>"
        f"<li><b>species</b>: {_esc(pet.get('species', ''))}</li>"
        f"<li><b>breed_style</b>: {_esc(pet.get('breed_style', ''))}</li>"
        f"<li><b>main_colors</b>: {_esc(colors or '—')}</li>"
        f"<li><b>expression_baseline</b>: {_esc(pet.get('expression_baseline', ''))}</li>"
        f"<li><b>personality_keywords</b>: {_esc(pers or '—')}</li>"
        "</ul>"
    )


def _reference_classification_card_html(pkg: dict[str, Any]) -> str:
    rtype = pkg.get("reference_type")
    if rtype is None and pkg.get("reference_classifier_metrics") is None:
        return "<p class='muted'>reference 타입 메타 없음(이전 패키지).</p>"
    rtype_s = _esc(str(rtype or "—"))
    conf = pkg.get("reference_type_confidence")
    conf_s = _esc(f"{float(conf):.3f}" if isinstance(conf, (int, float)) else "—")
    reasons = pkg.get("reference_type_reasons") or []
    if not isinstance(reasons, list):
        reasons = []
    reasons_li = "".join(f"<li>{_esc(x)}</li>" for x in reasons[:12])
    sty = str(pkg.get("stylizer_backend") or "").strip().lower()
    rec = _reference_recommended_mode_ko(str(rtype or ""), sty, conf)
    metrics = pkg.get("reference_classifier_metrics")
    metrics_block = ""
    if isinstance(metrics, dict) and metrics:
        # keep preview small
        keys = sorted(metrics.keys())[:24]
        lines = [f"{k}: {_esc(metrics.get(k))}" for k in keys]
        inner = "<br/>".join(lines)
        metrics_block = (
            f"<details style='margin-top:8px;'><summary class='muted'>metrics (일부)</summary>"
            f"<p class='tiny' style='margin:6px 0 0;font-family:ui-monospace,monospace;'>{inner}</p>"
            "</details>"
        )
    warn = ""
    if str(rtype) == "unknown" or (
        isinstance(conf, (int, float)) and float(conf) < 0.42 and str(rtype) != "photo" and str(rtype) != "character_art"
    ):
        warn = "<p class='warn'>입력 타입 자동 판별 신뢰도가 낮습니다. <code>--reference-type</code> 로 수동 지정을 권장합니다.</p>"
    photo_note = ""
    if str(rtype) == "photo":
        photo_note = (
            "<p class='muted'>실사 입력: 캐릭터화 품질은 <b>generator</b>·<b>stylizer</b>(API) 성능에 의존합니다.</p>"
        )
    exp = ""
    if str(rtype) == "photo" and sty == "openai":
        exp = "<p class='warn'>실사 입력 + <b>stylizer=openai</b>: 실사→캐릭터 원본 생성 <b>실험 모드</b>입니다.</p>"
    return (
        "<h2>Reference 입력 타입 판별</h2>"
        f"<ul class='mini'><li><b>reference_type</b>: {rtype_s}</li>"
        f"<li><b>confidence</b>: {conf_s}</li></ul>"
        f"<p><b>추천 사용 모드</b>: {_esc(rec)}</p>"
        f"{photo_note}{exp}{warn}"
        "<p class='muted'>판별 근거(reasons)</p><ul class='mini'>"
        f"{reasons_li or '<li>—</li>'}"
        "</ul>"
        f"{metrics_block}"
    )


def _reference_recommended_mode_ko(rtype: str, stylizer: str, conf: Any) -> str:
    sty = str(stylizer or "").strip().lower()
    t = str(rtype or "").strip().lower()
    if t == "character_art" and sty == "none":
        return "캐릭터 아트 입력 — stylizer none + 원본(reference) 기준(권장 흐름과 일치)"
    if t == "character_art" and sty in ("openai", "mock"):
        return f"캐릭터 아트 입력 — stylizer={sty}: 표준 시트가 원본 스타일을 바꿀 수 있음(의도적 실험/개발)"
    if t == "photo" and sty == "none":
        return "실사 입력 — stylizer none + 원본 실사 기준; OpenAI 생성 시 품질을 컷 01에서 먼저 확인"
    if t == "photo" and sty == "openai":
        return "실사 입력 + stylizer openai — 실사→캐릭터 원본 생성 실험 모드"
    if t == "unknown":
        return "unknown — auto 판별 불확실; --reference-type 로 photo/character_art/unknown 지정 권장"
    if isinstance(conf, (int, float)) and float(conf) < 0.42:
        return "confidence 낮음 — 수동 --reference-type 지정 권장"
    return "일반 파이프라인(auto 판별 또는 명시 타입)"


def _pipeline_flow_banner_html(
    package_dir: Path,
    *,
    cand_fb: dict[str, Any] | None,
    canonical_used: bool,
    has_sticker_outputs: bool,
) -> str:
    sel = ""
    if isinstance(cand_fb, dict) and cand_fb.get("selected_candidate") is not None:
        sel = f" → 선택 후보 #{_esc(cand_fb.get('selected_candidate'))}"
    steps = [
        ("1. Input", ref_char_path := package_dir / "character" / "reference.png"),
        ("2. Base candidates", package_dir / "character_candidates"),
        ("3. Selected canonical", package_dir / "character" / "canonical_character.png"),
        ("4. Emoticon outputs", package_dir / "png"),
    ]
    cells: list[str] = []
    for label, p in steps:
        ok = p.is_dir() and any(p.glob("*.png")) if p.name != "reference.png" else p.is_file()
        if label.startswith("3"):
            ok = canonical_used and (package_dir / "character" / "canonical_character.png").is_file()
        if label.startswith("4"):
            ok = has_sticker_outputs
        mark = "✓" if ok else "·"
        cells.append(
            f'<span class="flow-step" title="{_esc(str(p.relative_to(package_dir)))}">'
            f"{mark} {_esc(label)}{sel if 'Selected' in label else ''}</span>"
        )
    arrow = ' <span class="flow-arrow">→</span> '
    flow_line = arrow.join(cells)
    sheet_note = ""
    sp = package_dir / "character" / "canonical_sheet.png"
    if sp.is_file():
        sheet_note = (
            "<p class='muted' style='margin-top:8px;'><strong>고급</strong>: "
            "canonical_sheet.png 가 있습니다 (기본 흐름에서는 사용하지 않음).</p>"
        )
    return (
        "<div class='card' style='background:#f8f9fa;border:1px solid #dee2e6;'>"
        "<h2 style='margin-top:0;font-size:1.05rem;'>파이프라인</h2>"
        f"<p class='flow-pipeline'>{flow_line}</p>"
        f"{sheet_note}"
        "</div>"
    )


def write_preview_html(
    package_dir: Path,
    *,
    emoticon_subdir: str,
    qc_report: dict[str, Any],
    consistency_report: dict[str, Any] | None,
    generation_log: dict[str, Any] | None,
) -> Path:
    """Write ``preview.html`` at package root. Paths in HTML are relative to that file."""
    package_dir = Path(package_dir).resolve()
    meta_dir = package_dir / "meta"
    pkg = _load_json(meta_dir / "package_info.json") or {}
    webp_rep = _load_json(meta_dir / "webp_report.json")

    series = str(pkg.get("series_name", ""))
    theme = str(pkg.get("theme", ""))
    rep_id = str(pkg.get("representative_item_id") or "01").zfill(2)
    items_list: list[dict[str, Any]] = [
        x for x in (pkg.get("items") or []) if isinstance(x, dict)
    ]
    items_by_id: dict[str, dict[str, Any]] = {}
    for x in items_list:
        rid = str(x.get("id", "")).strip().zfill(2)
        if rid:
            items_by_id[rid] = x

    test_mode = bool(pkg.get("test_mode"))
    gen_count = pkg.get("generated_count")
    sel_cut = pkg.get("selected_cut_ids")
    if test_mode:
        cut_ids = sorted(
            items_by_id.keys(),
            key=lambda x: int(x) if str(x).isdigit() else 0,
        )
    else:
        cut_ids = [f"{i:02d}" for i in range(1, 17)]

    grid_extra_class = " grid-test" if test_mode else ""

    failed_ids = _failed_cut_ids(
        consistency_report=consistency_report,
        qc_report=qc_report,
        generation_log=generation_log,
    )
    if test_mode and items_by_id:
        allowed = set(items_by_id.keys())
        failed_ids = {x for x in failed_ids if x in allowed}

    cons_map = _consistency_by_id(consistency_report)
    webp_map_full = _webp_by_cut(webp_rep)
    if test_mode and items_by_id:
        webp_map = {k: v for k, v in webp_map_full.items() if k in items_by_id}
    else:
        webp_map = webp_map_full

    share_rel = "./share/share.png"
    rep_png_rel = f"./{emoticon_subdir}/{rep_id}.png"
    std_rel = pkg.get("standardized_character")
    std_img = ""
    if isinstance(std_rel, str) and std_rel.strip():
        std_img = f"./{std_rel.replace(chr(92), '/')}"

    no_ai_t = pkg.get("no_ai_text")
    text_ov = pkg.get("text_overlay_applied")
    sty_b = str(pkg.get("stylizer_backend") or "")
    gen_b = str(pkg.get("generator_backend") or pkg.get("generator") or "")
    cr_used = str(pkg.get("canonical_reference_used") or "")
    cr_pol = str(pkg.get("canonical_reference_policy") or "")
    cc_used = bool(pkg.get("canonical_character_used"))
    cc_path = str(pkg.get("canonical_character_path") or "").strip()
    cc_pol = str(pkg.get("canonical_character_policy") or "")
    cs_used = bool(pkg.get("canonical_sheet_used"))
    cs_path = str(pkg.get("canonical_sheet_path") or "").strip()
    cs_pol = str(pkg.get("canonical_sheet_policy") or "")
    pet_src = str(pkg.get("pet_profile_source") or "")
    pet_prof = pkg.get("pet_profile") if isinstance(pkg.get("pet_profile"), dict) else {}
    sheet_log = _load_json(package_dir / "character" / "canonical_sheet_log.json") or {}

    csgm = str(
        pkg.get("character_sheet_generation_mode")
        or sheet_log.get("character_sheet_generation_mode")
        or sheet_log.get("sheet_generation_mode")
        or ""
    ).strip()
    csmod = str(
        pkg.get("character_sheet_model")
        or sheet_log.get("character_sheet_model")
        or sheet_log.get("model")
        or ""
    ).strip()
    csapi = str(sheet_log.get("api_phase") or "")
    sheet_gen_policy_html = ""
    if pkg.get("sheet_mock") or sheet_log.get("sheet_mock") or sheet_log.get("backend") == "mock":
        sheet_gen_policy_html = (
            "<p class='warn'><strong>MOCK character sheet</strong> — not a production turnaround sheet.</p>"
        )
    elif sheet_log.get("backend") == "openai" and csapi == "images.generate":
        mlab = _esc(csmod or "gpt-image-1")
        sheet_gen_policy_html = (
            f"<p class='muted'><strong>Character sheet:</strong> "
            f"Sheet generated via {mlab} generate mode.</p>"
        )
    elif csgm == "edit":
        sheet_gen_policy_html = (
            "<p class='muted'><strong>Character sheet:</strong> Sheet generated via edit mode.</p>"
        )
    if sheet_log.get("text_only_fallback"):
        sheet_gen_policy_html += (
            "<p class='warn'>Image reference was not available to the API. Character drift may occur.</p>"
        )
    if pkg.get("forced_character_sheet_on_character_art") or sheet_log.get(
        "forced_character_sheet_on_character_art"
    ):
        sheet_gen_policy_html += (
            "<p class='warn'><strong>경고</strong> "
            "character_art 입력에서 sheet 재생성은 캐릭터 드리프트 가능성이 큼.</p>"
        )

    mock_warn = ""
    if sty_b == "mock" and std_img:
        mock_warn = (
            "<p class='warn'><strong>MOCK 기준 캐릭터</strong> — 실제 반려동물 원본과 다를 수 있습니다. "
            "품질·납품 판단에 사용하지 마세요.</p>"
        )

    gen_ref_kind = ""
    if generation_log and isinstance(generation_log.get("generation_reference_kind"), str):
        gen_ref_kind = str(generation_log["generation_reference_kind"])

    cand_fb = _load_json(package_dir / "character_candidates" / "candidate_feedback.json")
    fb_line = ""
    if isinstance(cand_fb, dict) and cand_fb.get("selected_candidate") is not None:
        fb_line = (
            "<p class='muted'><strong>후보 피드백</strong>: "
            f"selected_candidate={_esc(cand_fb.get('selected_candidate'))} · "
            f"canonical_sheet_used={_esc(cand_fb.get('canonical_sheet_used'))}</p>"
        )

    cad_pkg = bool(pkg.get("character_art_direct_canonical"))
    direct_mode_html = ""
    if cad_pkg or (
        sheet_log.get("skipped_sheet_generation") and sheet_log.get("character_art_direct_canonical")
    ):
        direct_mode_html = (
            "<div style='margin:12px 0;padding:10px 12px;border-radius:8px;"
            "background:#e8f5e9;border:1px solid #81c784;'>"
            "<p style='margin:0 0 6px;font-weight:600;'>완성 캐릭터 원본 직접 사용 모드</p>"
            "<p style='margin:0;font-size:0.9rem;'>새 시트 생성 생략</p>"
            "</div>"
        )

    v05_card = ""
    if (cs_used or gen_ref_kind == "canonical_sheet") and (
        package_dir / "character" / "canonical_sheet.png"
    ).is_file():
        v05_card = (
            "<div style='margin:12px 0;padding:10px 12px;border-radius:8px;"
            "background:#eef2f7;border:1px solid #b0bec5;'>"
            "<p style='margin:0 0 6px;font-weight:600;'>고급: character sheet</p>"
            "<p style='margin:0;font-size:0.9rem;'>canonical_sheet.png (기본 흐름 아님)</p>"
            "</div>"
        )

    policy_html = (
        "<p class='muted'>"
        f"AI 텍스트 사용 여부: {_esc('true' if no_ai_t is False else 'false')} · "
        f"Python 텍스트 오버레이: {_esc('true' if text_ov is True else 'false')} · "
        f"stylizer: {_esc(sty_b or '—')} · generator: {_esc(gen_b or '—')}"
        "</p>"
        "<p class='muted'>"
        f"기준 이미지(패키지 상대 경로): {_esc(cr_used or '—')}"
        "</p>"
        f"<p class='muted'>기준 이미지 정책: {_esc(cr_pol or '—')}</p>"
        f"{direct_mode_html}"
        f"{v05_card}"
        f"{fb_line}"
        f"{sheet_gen_policy_html}"
        "<p class='muted'>"
        f"<strong>stylizer 상태</strong> ({_esc(sty_b or '—')}): {_esc(_stylizer_status_ko(sty_b))}"
        "</p>"
    )
    if pet_src:
        policy_html += f"<p class='muted'>pet_profile_source: {_esc(pet_src)}</p>"
    if cc_used:
        policy_html += (
            "<p class='warn'><strong>캐릭터 원본 고정 모드</strong> — "
            f"canonical: {_esc(cc_path or 'character/canonical_character.png')}"
            "</p>"
        )
        if cc_pol:
            policy_html += f"<p class='muted'>{_esc(cc_pol)}</p>"
    if cs_used or cs_path:
        policy_html += (
            "<p class='warn'><strong>캐논 시트 모드</strong> — "
            f"{_esc(cs_path or 'character/canonical_sheet.png')}"
            "</p>"
        )
        if cs_pol:
            policy_html += f"<p class='muted'>{_esc(cs_pol)}</p>"
    if gen_ref_kind:
        policy_html += f"<p class='muted'>generation_reference_kind: {_esc(gen_ref_kind)}</p>"

    pet_block = (
        "<h2>PetProfile 요약</h2>"
        f"{_pet_profile_summary_html(pet_prof)}"
    )
    ref_card = _reference_classification_card_html(pkg)

    canon_src_json = package_dir / "character" / "canonical_character_source.json"
    canon_json_html = ""
    if canon_src_json.is_file():
        try:
            cdoc = json.loads(canon_src_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cdoc = {}
        if isinstance(cdoc, dict) and cdoc:
            bits = [
                f"source_type={_esc(str(cdoc.get('source_type', '')))}",
                f"candidate_index={_esc(str(cdoc.get('candidate_index', '')))}",
                f"created_at={_esc(str(cdoc.get('created_at', '')))}",
            ]
            canon_json_html = (
                "<p class='muted'><strong>canonical_character_source.json</strong>: "
                f"{_esc(' · '.join(x for x in bits if x))}</p>"
            )

    hero_extra_parts: list[str] = []
    canon_png = package_dir / "character" / "canonical_character.png"
    if canon_png.is_file():
        hero_extra_parts.append(
            '<div class="rep"><p class="muted"><strong>캐릭터 원본 고정</strong> (canonical_character.png)</p>'
            '<img class="canonical-hero" src="./character/canonical_character.png" '
            'alt="canonical identity" loading="lazy" /></div>'
        )
        if canon_json_html:
            hero_extra_parts.append(f'<div class="rep">{canon_json_html}</div>')
    ref_char_path = package_dir / "character" / "reference.png"
    ref_meta_path = package_dir / "meta" / "reference.png"
    if ref_char_path.is_file():
        hero_extra_parts.append(
            '<div class="rep"><p class="muted">입력 원본 (character/reference.png)</p>'
            '<img src="./character/reference.png" alt="reference" loading="lazy" /></div>'
        )
    elif ref_meta_path.is_file():
        hero_extra_parts.append(
            '<div class="rep"><p class="muted">입력 원본 (meta/reference.png)</p>'
            '<img src="./meta/reference.png" alt="reference" loading="lazy" /></div>'
        )
    sheet_png = package_dir / "character" / "canonical_sheet.png"
    if sheet_png.is_file():
        hero_extra_parts.append(
            '<div class="rep"><p class="muted">캐릭터 시트 (character/canonical_sheet.png)</p>'
            '<img class="sheet" src="./character/canonical_sheet.png" alt="sheet" loading="lazy" /></div>'
        )
    if std_img:
        std_label = "표준 캐릭터"
        if sty_b == "openai":
            std_label = "표준 캐릭터 (experimental · stylizer=openai)"
        elif sty_b == "mock":
            std_label = "MOCK 표준 캐릭터 (개발 전용)"
        hero_extra_parts.append(
            f'<div class="rep"><p class="muted">{_esc(std_label)}</p>'
            f'<img src="{_esc(std_img)}" alt="standardized" loading="lazy" /></div>'
        )
    gr_path = package_dir / "generated_raw" / f"{rep_id}.png"
    if gr_path.is_file():
        hero_extra_parts.append(
            f'<div class="rep"><p class="muted">AI 원본 (generated_raw/{_esc(rep_id)})</p>'
            f'<img src="./generated_raw/{_esc(rep_id)}.png" alt="raw" loading="lazy" /></div>'
        )
    nt_path = package_dir / "png_no_text" / f"{rep_id}.png"
    if nt_path.is_file():
        hero_extra_parts.append(
            f'<div class="rep"><p class="muted">정규화·텍스트 없음 (png_no_text)</p>'
            f'<img src="./png_no_text/{_esc(rep_id)}.png" alt="no text" loading="lazy" /></div>'
        )
    sheet_log_html = ""
    if sheet_log:
        panels = sheet_log.get("panels")
        pan_s = ", ".join(str(x) for x in panels) if isinstance(panels, list) else ""
        sheet_log_html = (
            '<div class="card">'
            "<h2>캐릭터 시트 로그</h2>"
            f"<p class='muted'>backend={_esc(sheet_log.get('backend'))} · "
            f"created_at={_esc(sheet_log.get('created_at_utc', ''))}</p>"
            f"<p class='muted'>panels: {_esc(pan_s or '—')}</p>"
            '<p><a href="./character/canonical_sheet_log.json">canonical_sheet_log.json</a></p>'
            "</div>"
        )

    hero_extra = "".join(hero_extra_parts)
    qc_ok = bool(qc_report.get("ok"))
    qc_errors = qc_report.get("errors") or []
    qc_warnings = qc_report.get("warnings") or []
    cons_ok = None if consistency_report is None else bool(consistency_report.get("ok"))
    cons_thr = consistency_report.get("threshold") if consistency_report else None

    qc_block = (
        f'<p class="status {"ok" if qc_ok else "fail"}">'
        f'QualityChecker: {"통과" if qc_ok else "실패"}'
        f"</p>"
        f"<ul class='mini'>{''.join(f'<li>{_esc(e)}</li>' for e in qc_errors[:12])}</ul>"
    )
    if qc_warnings:
        qc_block += "<p class='warn'>경고</p><ul class='mini'>" + "".join(
            f"<li>{_esc(w)}</li>" for w in qc_warnings[:8]
        ) + "</ul>"

    if consistency_report is None:
        cons_block = "<p class='muted'>일관성 검사 없음(생략 또는 미실행).</p>"
    else:
        drift_thr = consistency_report.get("drift_threshold")
        strict_d = consistency_report.get("strict_drift")
        drift_note = ""
        if drift_thr is not None:
            drift_note = (
                f"<p class='muted'>drift_similarity 기준: ≥{_esc(drift_thr)} "
                f"(strict_drift={_esc(strict_d)})</p>"
            )
        cons_block = (
            f'<p class="status {"ok" if cons_ok else "fail"}">'
            f'CharacterConsistency: {"통과" if cons_ok else "실패"}'
            f"{f' (consistency threshold {cons_thr})' if cons_thr is not None else ''}"
            f"</p>"
            f"{drift_note}"
        )

    gen_rows = ""
    if generation_log:
        cuts_raw = generation_log.get("cuts") or []
        if test_mode and items_by_id:
            allow_ids = set(items_by_id.keys())
            cuts_iter = [
                c
                for c in cuts_raw
                if isinstance(c, dict)
                and str(c.get("id", "")).strip().zfill(2) in allow_ids
            ]
        else:
            cuts_iter = cuts_raw
        for cut in cuts_iter:
            if not isinstance(cut, dict):
                continue
            cid = _esc(cut.get("id", ""))
            ok = cut.get("success")
            ws = cut.get("wall_seconds", "")
            err = cut.get("error")
            phases = ""
            for al in cut.get("attempt_logs") or []:
                if isinstance(al, dict):
                    wsa = al.get("wall_seconds", "")
                    phases += (
                        f"{al.get('phase','?')}#{al.get('attempt','?')} "
                        f"({_esc(wsa)}s):{'OK' if al.get('success') else 'FAIL'}; "
                    )
            cls = "ok" if ok else "fail"
            gen_rows += (
                f"<tr><td>{cid}</td><td class='{cls}'>{'성공' if ok else '실패'}</td>"
                f"<td>{_esc(ws)}</td><td class='tiny'>{_esc(phases[:200])}</td>"
                f"<td class='tiny'>{_esc((err or '')[:180])}</td></tr>"
            )

    grid_cells = ""
    for cid in cut_ids:
        item = items_by_id.get(cid, {})
        text = str(item.get("text", "—"))
        emotion = str(item.get("emotion", "—"))
        action = str(item.get("action", "—"))
        png_rel = f"./{emoticon_subdir}/{cid}.png"
        png_path_fs = package_dir / emoticon_subdir / f"{cid}.png"
        exists = png_path_fs.is_file()
        is_fail = cid in failed_ids
        cons_row = cons_map.get(cid, {})
        score = cons_row.get("score", "")
        id_sim = cons_row.get("identity_similarity", score)
        canon_id = cons_row.get("canonical_identity_score", "")
        tex_sim = cons_row.get("texture_similarity", "")
        sty_sim = cons_row.get("style_similarity", "")
        drift_reason = cons_row.get("drift_reason", "")
        status = str(cons_row.get("status", ""))
        drift_sim = cons_row.get("drift_similarity", "")
        drift_score = cons_row.get("drift_score", "")
        drift_st = str(cons_row.get("drift_status", "") or "")
        if is_fail:
            border_cls = "cell fail"
        elif consistency_report and status == "pass":
            border_cls = "cell pass"
        else:
            border_cls = "cell neutral"
        status_badge = (
            '<span class="badge fail">FAIL</span>'
            if is_fail
            else ('<span class="badge ok">PASS</span>' if status == "pass" else "")
        )

        img_tag = (
            f'<img class="thumb" src="{_esc(png_rel)}" alt="cut {cid}" loading="lazy" />'
            if exists
            else '<div class="placeholder">PNG 없음</div>'
        )

        wrel = webp_map.get(cid)
        webp_block = ""
        if wrel:
            wpath = (package_dir / wrel.replace("\\", "/")).resolve()
            if wpath.is_file():
                webp_src = "./" + wrel.lstrip("/").replace("\\", "/")
                webp_block = (
                    f'<p class="webp-label">WebP</p>'
                    f'<img class="thumb webp" src="{_esc(webp_src)}" '
                    f'alt="webp {cid}" loading="lazy" />'
                )

        rel_fs = f"{emoticon_subdir}/{cid}.png"
        grid_cells += f"""
        <div class="{border_cls}">
          <div class="cell-head">{_esc(cid)} {status_badge}</div>
          {img_tag}
          {webp_block}
          <div class="meta">
            <div><b>문구</b> {_esc(text)}</div>
            <div><b>emotion</b> {_esc(emotion)}</div>
            <div><b>action</b> {_esc(action)}</div>
            <div class="path">{_esc(rel_fs)}</div>
            <div class="score">consistency: {_esc(score)} ({_esc(status)})</div>
            <div class="score">identity: {_esc(id_sim)} · canonical_id: {_esc(canon_id)} · texture: {_esc(tex_sim)} · style: {_esc(sty_sim)}</div>
            <div class="score">drift_similarity: {_esc(drift_sim)} drift_score: {_esc(drift_score)} ({_esc(drift_st)})</div>
            <div class="score drift-reason">{_esc(drift_reason) if drift_reason else ""}</div>
          </div>
        </div>
        """

    drift_hm = _drift_heatmap_html(cut_ids, cons_map)
    rej_html = _rejected_cuts_html(package_dir, emoticon_subdir, failed_ids, cons_map, qc_report)

    pkg_summary = (
        f"<ul class='summary'>"
        f"<li>시리즈: {_esc(series)}</li>"
        f"<li>테마: {_esc(theme)}</li>"
        f"<li>스티커 서브디렉터리: {_esc(emoticon_subdir)}</li>"
        f"<li>컷 수 (package_info): {len(items_list)}</li>"
    )
    si_pkg = pkg.get("style_intensity")
    si_log = generation_log.get("style_intensity") if generation_log else None
    si_val = si_pkg if si_pkg is not None else si_log
    if si_val is not None:
        pkg_summary += f"<li><strong>style_intensity</strong>: {_esc(si_val)} (0=벡터, 1=수채/동화책)</li>"
    id_prof = _load_json(package_dir / "meta" / "identity_profile.json")
    if isinstance(id_prof, dict) and id_prof.get("entity_type"):
        pkg_summary += (
            f"<li><strong>entity_type</strong>: {_esc(id_prof.get('entity_type'))} "
            f"(confidence={_esc(id_prof.get('entity_type_confidence', ''))})</li>"
        )
    pkg_summary += (
        f"</ul>"
        f'<p><a href="./meta/package_info.json">package_info.json</a> · '
        f'<a href="./meta/generation_log.json">generation_log.json</a> · '
        f'<a href="./meta/consistency_report.json">consistency_report.json</a>'
    )
    if (package_dir / "meta" / "identity_profile.json").is_file():
        pkg_summary += ' · <a href="./meta/identity_profile.json">identity_profile.json</a>'
    if (package_dir / "character" / "canonical_sheet_log.json").is_file():
        pkg_summary += ' · <a href="./character/canonical_sheet_log.json">canonical_sheet_log.json</a>'
    if (package_dir / "character_candidates" / "candidate_feedback.json").is_file():
        pkg_summary += ' · <a href="./character_candidates/candidate_feedback.json">candidate_feedback.json</a>'
    if webp_rep:
        pkg_summary += ' · <a href="./meta/webp_report.json">webp_report.json</a>'
    pkg_summary += "</p>"
    if test_mode:
        sid_txt = ""
        if isinstance(sel_cut, list) and sel_cut:
            sid_txt = f" · <strong>selected_cut_ids</strong>: {_esc(', '.join(str(x) for x in sel_cut))}"
        pkg_summary += (
            f"<p class='warn'><strong>test_mode</strong> · "
            f"<strong>generated_count</strong>: {_esc(gen_count if gen_count is not None else len(items_list))}"
            f"{sid_txt}</p>"
        )

    grid_title = "테스트 모드: 생성된 컷" if test_mode else "16컷 그리드"

    spec = pkg.get("spec") or {}
    if isinstance(spec, dict) and spec:
        pkg_summary += (
            f"<p class='muted'>규격 요약: 스티커 {_esc(spec.get('emoticon_size'))} · "
            f"아이콘 {_esc(spec.get('icon_size'))} · 공유 {_esc(spec.get('share_size'))} · "
            f"용량 상한 emoticon={_esc(spec.get('max_emoticon_bytes'))} bytes</p>"
        )

    cc_used_flow = bool(pkg.get("canonical_character_used")) or (
        package_dir / "character" / "canonical_character.png"
    ).is_file()
    flow_banner = _pipeline_flow_banner_html(
        package_dir,
        cand_fb=cand_fb if isinstance(cand_fb, dict) else None,
        canonical_used=cc_used_flow,
        has_sticker_outputs=bool(items_list),
    )

    html_doc = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(series)} — 이모티콘 미리보기</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans KR", sans-serif;
      margin: 0; padding: 24px; background: #f4f5f7; color: #222;
    }}
    h1 {{ font-size: 1.35rem; margin: 0 0 8px; }}
    h2 {{ font-size: 1.05rem; margin: 24px 0 12px; border-bottom: 1px solid #ddd; padding-bottom: 6px; }}
    .card {{
      background: #fff; border-radius: 12px; padding: 20px 22px;
      box-shadow: 0 1px 3px rgba(0,0,0,.08); margin-bottom: 20px;
    }}
    .muted {{ color: #666; font-size: 0.9rem; }}
    .hero {{ display: flex; flex-wrap: wrap; gap: 20px; align-items: flex-start; }}
    .hero img.banner {{ max-width: 100%; height: auto; border-radius: 8px; border: 1px solid #e5e5e5; }}
    .hero .rep {{ text-align: center; }}
    .hero .rep img {{ width: 180px; height: 180px; object-fit: contain; border-radius: 8px;
      border: 1px solid #e5e5e5; background: #fafafa; }}
    .hero .rep img.sheet {{ width: min(100%, 420px); max-width: 420px; height: auto; min-height: 120px;
      object-fit: contain; }}
    .hero .rep img.canonical-hero {{
      width: min(96vw, 320px); height: min(96vw, 320px); max-width: 320px; max-height: 320px;
      object-fit: contain; border-radius: 10px; border: 2px solid #81c784; background: #f1f8e9;
    }}
    .drift-grid {{
      display: grid; grid-template-columns: repeat(8, minmax(0, 1fr)); gap: 6px; max-width: 720px;
    }}
    @media (max-width: 720px) {{
      .drift-grid {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
    }}
    .dcell {{
      border-radius: 6px; min-height: 44px; display: flex; align-items: center; justify-content: center;
      border: 1px solid rgba(0,0,0,.08); color: #fff; font-weight: 700; font-size: 0.82rem;
      text-shadow: 0 0 4px rgba(0,0,0,.45);
    }}
    .rej-wrap {{ display: flex; flex-direction: column; gap: 12px; }}
    .rej-row {{
      display: flex; gap: 14px; align-items: flex-start; border-bottom: 1px solid #eee; padding-bottom: 12px;
    }}
    .rej-thumb {{
      width: 120px; height: 120px; object-fit: contain; border-radius: 8px; border: 1px solid #e0e0e0;
      background: #fafafa;
    }}
    .rej-miss {{
      width: 120px; height: 120px; border-radius: 8px; background: #f5f5f5; display: flex;
      align-items: center; justify-content: center; font-size: 0.78rem; color: #888;
    }}
    .grid {{
      display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px;
    }}
    .grid.grid-test {{
      max-width: 420px;
      grid-template-columns: 1fr;
    }}
    @media (max-width: 1100px) {{
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 600px) {{
      .grid {{ grid-template-columns: 1fr; }}
    }}
    .cell {{
      background: #fff; border-radius: 10px; padding: 12px;
      box-shadow: 0 1px 2px rgba(0,0,0,.06);
      border: 2px solid transparent;
    }}
    .cell.pass {{ border-color: #2e7d32; }}
    .cell.fail {{ border-color: #c62828; box-shadow: 0 0 0 1px #ffcdd2; }}
    .cell.neutral {{ border-color: #e0e0e0; }}
    .cell-head {{ font-weight: 700; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }}
    .thumb {{ width: 180px; height: 180px; object-fit: contain; display: block; margin: 0 auto 8px;
      background: #fafafa; border-radius: 6px; }}
    .thumb.webp {{ margin-top: 4px; }}
    .webp-label {{ font-size: 0.75rem; color: #555; margin: 4px 0 0; text-align: center; }}
    .placeholder {{
      width: 180px; height: 180px; margin: 0 auto 8px; display: flex; align-items: center; justify-content: center;
      background: #f0f0f0; color: #888; border-radius: 6px; font-size: 0.85rem;
    }}
    .meta {{ font-size: 0.8rem; line-height: 1.45; }}
    .meta .path {{ font-family: ui-monospace, monospace; font-size: 0.72rem; color: #555; word-break: break-all; }}
    .meta .score {{ color: #444; margin-top: 4px; }}
    .badge {{ font-size: 0.65rem; padding: 2px 6px; border-radius: 4px; font-weight: 600; }}
    .badge.ok {{ background: #e8f5e9; color: #2e7d32; }}
    .badge.fail {{ background: #ffebee; color: #c62828; }}
    .status.ok {{ color: #2e7d32; font-weight: 600; }}
    .status.fail {{ color: #c62828; font-weight: 600; }}
    .warn {{ color: #e65100; }}
    ul.mini {{ margin: 6px 0 0 16px; padding: 0; font-size: 0.85rem; }}
    ul.summary {{ margin: 8px 0; padding-left: 20px; }}
    table.gen {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
    table.gen th, table.gen td {{ border: 1px solid #e0e0e0; padding: 6px 8px; text-align: left; vertical-align: top; }}
    table.gen th {{ background: #f5f5f5; }}
    td.tiny {{ font-size: 0.75rem; max-width: 240px; word-break: break-word; }}
    p.tiny {{ font-size: 0.76rem; line-height: 1.35; color: #444; }}
    a {{ color: #1565c0; }}
    .flow-pipeline {{ font-size: 0.88rem; line-height: 1.8; margin: 8px 0; }}
    .flow-step {{ display: inline-block; padding: 2px 6px; background: #fff; border-radius: 4px; border: 1px solid #ddd; }}
    .flow-arrow {{ color: #888; }}
  </style>
</head>
<body>
  {flow_banner}
  <div class="card">
    <h1>{_esc(series)}</h1>
    <p class="muted">테마: {_esc(theme)} · 로컬 패키지 미리보기 (프로토타입)</p>
    {pkg_summary}
    {pet_block}
    {ref_card}
    {sheet_log_html}
    {policy_html}
    {mock_warn}
  </div>

  <div class="card">
    <h2>대표 이미지</h2>
    <div class="hero">
      <div>
        <p class="muted">공유 배너 (share/share.png)</p>
        <img class="banner" src="{_esc(share_rel)}" alt="share" loading="lazy" />
      </div>
      {hero_extra}
      <div class="rep">
        <p class="muted">최종 대표 컷 {_esc(rep_id)} ({_esc(emoticon_subdir)})</p>
        <img src="{_esc(rep_png_rel)}" alt="representative" loading="lazy" />
      </div>
    </div>
  </div>

  <div class="card">
    <h2>품질 검사 (QualityChecker)</h2>
    {qc_block}
  </div>

  <div class="card">
    <h2>캐릭터 일관성</h2>
    {cons_block}
  </div>

  {drift_hm}

  {rej_html}

  <div class="card">
    <h2>{_esc(grid_title)} (180px)</h2>
    <p class="muted">빨간 테두리: 실패 컷. 초록 테두리: 일관성 pass. 회색: 미검사 또는 기타. identity/texture/style은 canonical 대비 휴리스틱 유사도(0–1).</p>
    <div class="grid{grid_extra_class}">
      {grid_cells}
    </div>
  </div>

  <div class="card">
    <h2>generation_log 요약</h2>
    <table class="gen">
      <tr><th>컷</th><th>결과</th><th>wall_s</th><th>시도 phase</th><th>오류</th></tr>
      {gen_rows or "<tr><td colspan='5'>기록 없음</td></tr>"}
    </table>
  </div>
</body>
</html>
"""

    out_path = package_dir / "preview.html"
    out_path.write_text(html_doc, encoding="utf-8")
    return out_path
