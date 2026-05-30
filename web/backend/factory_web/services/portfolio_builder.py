"""이모티콘 포트폴리오 HTML 생성기.

ZIP 안에 portfolio.html 로 동봉되거나,
/api/jobs/{job_id}/portfolio 엔드포인트로 브라우저에 직접 렌더링됩니다.

이미지 경로 모드:
  - embed=True  : base64 data URI 인라인 (브라우저 미리보기, 이메일 공유용)
  - embed=False : 상대 경로 png/01.png (ZIP 내부 오프라인 열람용)
"""

from __future__ import annotations

import base64
import html
from datetime import datetime
from pathlib import Path
from typing import Any


# ── 카카오 팔레트 ──────────────────────────────────────────────────────────
_YELLOW  = "#FEE500"
_BROWN   = "#3C1E1E"
_CREAM   = "#FFF8F0"
_CARD_BG = "#FFFFFF"
_ACCENT  = "#F7C948"


def _b64_img(path: Path) -> str | None:
    """파일을 base64 data URI로 변환."""
    if not path.is_file():
        return None
    data = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/png;base64,{data}"


def _safe(text: str) -> str:
    return html.escape(str(text))


def build_portfolio_html(
    job: dict[str, Any],
    pkg: Path,
    *,
    embed: bool = True,
) -> str:
    """포트폴리오 HTML 문자열을 반환합니다.

    Args:
        job:   job.json 데이터 dict
        pkg:   패키지 디렉터리 (png/, character/ 등이 있는 곳)
        embed: True=이미지 base64 인라인, False=상대경로(ZIP용)
    """
    cuts: list[dict] = job.get("cuts") or []
    created_at: str = job.get("created_at", "")[:10] or datetime.now().strftime("%Y-%m-%d")
    art_style: str  = job.get("art_style", "")
    style_label = "일러스트 스타일" if "illus" in art_style.lower() else \
                  "실사 스타일"     if "real"  in art_style.lower() else "AI 생성"

    # ── 캐릭터 대표 이미지 ──────────────────────────────────────────────────
    canon_path = pkg / "character" / "canonical_character.png"
    if embed:
        canon_src = _b64_img(canon_path) or ""
    else:
        canon_src = "character/canonical_character.png"
    has_canon = canon_path.is_file()

    # ── 이모티콘 컷 이미지 목록 ─────────────────────────────────────────────
    png_dir = pkg / "png_no_text" if (pkg / "png_no_text").is_dir() else pkg / "png"

    cut_items: list[dict] = []
    for c in cuts:
        cid   = str(c.get("id", "")).zfill(2)
        text  = c.get("text", "")
        fpath = png_dir / f"{cid}.png"
        if embed:
            src = _b64_img(fpath) or ""
        else:
            subdir = "png_no_text" if (pkg / "png_no_text").is_dir() else "png"
            src = f"{subdir}/{cid}.png"
        cut_items.append({"id": cid, "text": text, "src": src, "ok": fpath.is_file()})

    # 빈 슬롯 채우기 (16개 맞춤)
    while len(cut_items) < 16:
        cut_items.append({"id": "", "text": "", "src": "", "ok": False})

    # ── 컷 그리드 HTML ──────────────────────────────────────────────────────
    grid_items = []
    for item in cut_items:
        if item["ok"]:
            grid_items.append(f"""
        <div class="cut-card">
          <div class="cut-img-wrap">
            <img src="{item['src']}" alt="{_safe(item['text'])}" loading="lazy" />
          </div>
          <p class="cut-label">{_safe(item['text'])}</p>
        </div>""")
        else:
            grid_items.append("""
        <div class="cut-card empty">
          <div class="cut-img-wrap placeholder"></div>
          <p class="cut-label">&nbsp;</p>
        </div>""")

    grid_html = "\n".join(grid_items)

    # ── 캐릭터 섹션 ─────────────────────────────────────────────────────────
    canon_section = ""
    if has_canon:
        canon_section = f"""
      <div class="canon-wrap">
        <img src="{canon_src}" alt="캐릭터" class="canon-img" />
      </div>"""

    # ── 전체 HTML ──────────────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>나만의 이모티콘 포트폴리오</title>
  <style>
    /* ── 기본 리셋 ── */
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo",
                   "Noto Sans KR", "Malgun Gothic", sans-serif;
      background: {_CREAM};
      color: {_BROWN};
      min-height: 100vh;
    }}

    /* ── 헤더 ── */
    .header {{
      background: {_YELLOW};
      text-align: center;
      padding: 2.5rem 1rem 2rem;
    }}
    .header-badge {{
      display: inline-block;
      background: {_BROWN};
      color: {_YELLOW};
      font-size: 0.7rem;
      font-weight: 700;
      letter-spacing: 0.1em;
      padding: 0.25rem 0.75rem;
      border-radius: 999px;
      margin-bottom: 0.75rem;
    }}
    .header h1 {{
      font-size: clamp(1.5rem, 5vw, 2.2rem);
      font-weight: 900;
      line-height: 1.2;
      color: {_BROWN};
    }}
    .header .sub {{
      margin-top: 0.5rem;
      font-size: 0.9rem;
      color: {_BROWN}bb;
    }}
    .header .date {{
      margin-top: 0.75rem;
      font-size: 0.8rem;
      color: {_BROWN}99;
    }}

    /* ── 본문 컨테이너 ── */
    .container {{
      max-width: 680px;
      margin: 0 auto;
      padding: 2rem 1rem 4rem;
    }}

    /* ── 캐릭터 소개 ── */
    .intro-section {{
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 1rem;
      background: {_CARD_BG};
      border-radius: 1.5rem;
      padding: 2rem 1.5rem;
      box-shadow: 0 4px 24px rgba(60,30,30,.07);
      margin-bottom: 2rem;
    }}
    .canon-wrap {{
      width: 140px;
      height: 140px;
      border-radius: 50%;
      overflow: hidden;
      border: 4px solid {_YELLOW};
      box-shadow: 0 0 0 6px {_ACCENT}44;
      flex-shrink: 0;
    }}
    .canon-img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
    }}
    .intro-text {{
      text-align: center;
    }}
    .intro-text .style-badge {{
      display: inline-block;
      background: {_YELLOW};
      font-size: 0.75rem;
      font-weight: 700;
      padding: 0.2rem 0.65rem;
      border-radius: 999px;
      margin-bottom: 0.5rem;
    }}
    .intro-text h2 {{
      font-size: 1.15rem;
      font-weight: 800;
    }}
    .intro-text p {{
      margin-top: 0.35rem;
      font-size: 0.85rem;
      color: {_BROWN}99;
      line-height: 1.6;
    }}

    /* ── 갤러리 ── */
    .gallery-section {{
      background: {_CARD_BG};
      border-radius: 1.5rem;
      padding: 1.75rem 1.25rem;
      box-shadow: 0 4px 24px rgba(60,30,30,.07);
      margin-bottom: 2rem;
    }}
    .section-title {{
      font-size: 0.95rem;
      font-weight: 800;
      letter-spacing: 0.03em;
      margin-bottom: 1.25rem;
      display: flex;
      align-items: center;
      gap: 0.4rem;
    }}
    .cut-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 0.75rem;
    }}
    .cut-card {{
      border-radius: 1rem;
      overflow: hidden;
      background: {_CREAM};
      box-shadow: 0 2px 8px rgba(60,30,30,.06);
      transition: transform .18s ease, box-shadow .18s ease;
    }}
    .cut-card:hover {{
      transform: translateY(-3px) scale(1.03);
      box-shadow: 0 8px 20px rgba(60,30,30,.12);
    }}
    .cut-card.empty {{
      opacity: 0.3;
    }}
    .cut-img-wrap {{
      aspect-ratio: 1;
      overflow: hidden;
    }}
    .cut-img-wrap img {{
      width: 100%; height: 100%;
      object-fit: cover;
      display: block;
    }}
    .cut-img-wrap.placeholder {{
      background: {_YELLOW}44;
    }}
    .cut-label {{
      font-size: 0.68rem;
      font-weight: 600;
      text-align: center;
      padding: 0.35rem 0.2rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      color: {_BROWN}cc;
    }}

    /* ── 액션 버튼 ── */
    .actions {{
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
      justify-content: center;
      margin-bottom: 2rem;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.7rem 1.4rem;
      border-radius: 999px;
      font-size: 0.9rem;
      font-weight: 700;
      cursor: pointer;
      border: none;
      transition: opacity .15s;
      text-decoration: none;
    }}
    .btn:active {{ opacity: 0.75; }}
    .btn-primary {{ background: {_YELLOW}; color: {_BROWN}; }}
    .btn-outline {{ background: transparent; border: 2px solid {_BROWN}22; color: {_BROWN}; }}

    /* ── 푸터 ── */
    .footer {{
      text-align: center;
      font-size: 0.78rem;
      color: {_BROWN}66;
      line-height: 1.8;
    }}
    .footer strong {{
      color: {_BROWN}99;
    }}

    /* ── 인쇄 ── */
    @media print {{
      body {{ background: white; }}
      .actions {{ display: none; }}
      .cut-card {{ box-shadow: none; break-inside: avoid; }}
      .cut-card:hover {{ transform: none; }}
      .header {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
      .header-badge {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
      .style-badge {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    }}

    /* ── 모바일 ── */
    @media (max-width: 480px) {{
      .cut-grid {{ grid-template-columns: repeat(4, 1fr); gap: 0.5rem; }}
      .canon-wrap {{ width: 110px; height: 110px; }}
    }}
  </style>
</head>
<body>

  <!-- 헤더 -->
  <div class="header">
    <div class="header-badge">✨ EMOTICON STUDIO</div>
    <h1>나만의 이모티콘<br>완성됐어요!</h1>
    <p class="sub">AI로 직접 만든 나만의 캐릭터 이모티콘</p>
    <p class="date">제작일 {_safe(created_at)}</p>
  </div>

  <div class="container">

    <!-- 캐릭터 소개 -->
    <div class="intro-section">
      {canon_section}
      <div class="intro-text">
        <span class="style-badge">{_safe(style_label)}</span>
        <h2>나의 이모티콘 캐릭터</h2>
        <p>사진 한 장으로 탄생한 나만의 캐릭터<br>
           총 {len([c for c in cut_items if c['ok']])}가지 감정을 표현해요</p>
      </div>
    </div>

    <!-- 갤러리 -->
    <div class="gallery-section">
      <p class="section-title">🎨 감정 이모티콘 갤러리</p>
      <div class="cut-grid">
{grid_html}
      </div>
    </div>

    <!-- 버튼 -->
    <div class="actions">
      <button class="btn btn-primary" onclick="window.print()">
        🖨 인쇄 / PDF 저장
      </button>
      <button class="btn btn-outline" onclick="copyLink()">
        🔗 링크 복사
      </button>
    </div>

    <!-- 푸터 -->
    <div class="footer">
      <p>이 이모티콘은 <strong>이모티콘 스튜디오</strong>에서<br>
         AI로 직접 제작한 <strong>나만의 작품</strong>입니다 ❤️</p>
      <p style="margin-top:.5rem">{_safe(created_at)} · {_safe(style_label)}</p>
    </div>

  </div>

  <script>
    function copyLink() {{
      var url = window.location.href;
      if (navigator.clipboard) {{
        navigator.clipboard.writeText(url).then(function() {{
          alert('링크가 복사됐어요!');
        }});
      }} else {{
        prompt('아래 링크를 복사하세요:', url);
      }}
    }}
  </script>
</body>
</html>"""
