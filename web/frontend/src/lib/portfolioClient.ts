/**
 * 브라우저에서 직접 포트폴리오 HTML을 생성해 새 탭으로 엽니다.
 * 백엔드 요청이 전혀 없으므로 413 · 프록시 이슈 없음.
 */

type Cut = { id: string; text: string; url?: string | null };

interface PortfolioOptions {
  date?: string;
  styleLabel?: string;
  canonUrl?: string | null;
}

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** 상대 URL → 절대 URL 변환 */
function abs(url: string | null | undefined): string {
  if (!url) return "";
  if (url.startsWith("http") || url.startsWith("data:")) return url;
  return `${window.location.origin}${url}`;
}

function buildHTML(cuts: Cut[], opts: PortfolioOptions): string {
  const { date = new Date().toISOString().slice(0, 10), styleLabel = "AI 생성", canonUrl } = opts;

  const cutCards = cuts
    .map((c) => {
      const imgSrc = abs(c.url);
      return imgSrc
        ? `<div class="cut-card">
          <div class="cut-img-wrap"><img src="${esc(imgSrc)}" alt="${esc(c.text)}" loading="lazy" /></div>
          <p class="cut-label">${esc(c.text)}</p>
        </div>`
        : `<div class="cut-card empty">
          <div class="cut-img-wrap placeholder"></div>
          <p class="cut-label">&nbsp;</p>
        </div>`;
    })
    .join("\n");

  const canonSection = canonUrl
    ? `<div class="canon-wrap"><img src="${esc(abs(canonUrl))}" alt="캐릭터" class="canon-img" /></div>`
    : "";

  return `<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>나만의 이모티콘 포트폴리오</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic", sans-serif; background: #FFF8F0; color: #3C1E1E; }

    .header { background: #FEE500; text-align: center; padding: 2.5rem 1rem 2rem; }
    .header-badge { display: inline-block; background: #3C1E1E; color: #FEE500; font-size: .7rem; font-weight: 700; letter-spacing: .1em; padding: .25rem .75rem; border-radius: 999px; margin-bottom: .75rem; }
    .header h1 { font-size: clamp(1.5rem, 5vw, 2.2rem); font-weight: 900; color: #3C1E1E; }
    .header .sub { margin-top: .5rem; font-size: .9rem; color: #3C1E1E99; }
    .header .date { margin-top: .75rem; font-size: .8rem; color: #3C1E1E80; }

    .container { max-width: 680px; margin: 0 auto; padding: 2rem 1rem 4rem; }

    .intro-section { display: flex; flex-direction: column; align-items: center; gap: 1rem; background: #fff; border-radius: 1.5rem; padding: 2rem 1.5rem; box-shadow: 0 4px 24px rgba(60,30,30,.07); margin-bottom: 2rem; }
    .canon-wrap { width: 140px; height: 140px; border-radius: 50%; overflow: hidden; border: 4px solid #FEE500; box-shadow: 0 0 0 6px #F7C94844; flex-shrink: 0; }
    .canon-img { width: 100%; height: 100%; object-fit: cover; }
    .intro-text { text-align: center; }
    .style-badge { display: inline-block; background: #FEE500; font-size: .75rem; font-weight: 700; padding: .2rem .65rem; border-radius: 999px; margin-bottom: .5rem; }
    .intro-text h2 { font-size: 1.15rem; font-weight: 800; }
    .intro-text p { margin-top: .35rem; font-size: .85rem; color: #3C1E1E99; line-height: 1.6; }

    .gallery-section { background: #fff; border-radius: 1.5rem; padding: 1.75rem 1.25rem; box-shadow: 0 4px 24px rgba(60,30,30,.07); margin-bottom: 2rem; }
    .section-title { font-size: .95rem; font-weight: 800; margin-bottom: 1.25rem; }
    .cut-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: .75rem; }
    .cut-card { border-radius: 1rem; overflow: hidden; background: #FFF8F0; box-shadow: 0 2px 8px rgba(60,30,30,.06); transition: transform .18s ease, box-shadow .18s ease; }
    .cut-card:hover { transform: translateY(-3px) scale(1.03); box-shadow: 0 8px 20px rgba(60,30,30,.12); }
    .cut-card.empty { opacity: .3; }
    .cut-img-wrap { aspect-ratio: 1; overflow: hidden; }
    .cut-img-wrap img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .cut-img-wrap.placeholder { background: #FEE50044; }
    .cut-label { font-size: .68rem; font-weight: 600; text-align: center; padding: .35rem .2rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #3C1E1ECC; }

    .actions { display: flex; gap: .75rem; flex-wrap: wrap; justify-content: center; margin-bottom: 2rem; }
    .btn { display: inline-flex; align-items: center; gap: .4rem; padding: .7rem 1.4rem; border-radius: 999px; font-size: .9rem; font-weight: 700; cursor: pointer; border: none; transition: opacity .15s; }
    .btn:active { opacity: .75; }
    .btn-primary { background: #FEE500; color: #3C1E1E; }
    .btn-outline { background: transparent; border: 2px solid #3C1E1E22; color: #3C1E1E; }

    .footer { text-align: center; font-size: .78rem; color: #3C1E1E66; line-height: 1.8; }
    .footer strong { color: #3C1E1E99; }

    @media print {
      body { background: white; }
      .actions { display: none; }
      .cut-card { box-shadow: none; break-inside: avoid; }
      .cut-card:hover { transform: none; }
      .header { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .style-badge { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    }
    @media (max-width: 480px) {
      .cut-grid { gap: .5rem; }
      .canon-wrap { width: 110px; height: 110px; }
    }
  </style>
</head>
<body>
  <div class="header">
    <div class="header-badge">✨ EMOTICON STUDIO</div>
    <h1>나만의 이모티콘<br>완성됐어요!</h1>
    <p class="sub">AI로 직접 만든 나만의 캐릭터 이모티콘</p>
    <p class="date">제작일 ${esc(date)}</p>
  </div>

  <div class="container">
    <div class="intro-section">
      ${canonSection}
      <div class="intro-text">
        <span class="style-badge">${esc(styleLabel)}</span>
        <h2>나의 이모티콘 캐릭터</h2>
        <p>사진 한 장으로 탄생한 나만의 캐릭터<br>${cuts.filter((c) => c.url).length}가지 감정을 표현해요</p>
      </div>
    </div>

    <div class="gallery-section">
      <p class="section-title">🎨 감정 이모티콘 갤러리</p>
      <div class="cut-grid">${cutCards}</div>
    </div>

    <div class="actions">
      <button class="btn btn-primary" onclick="window.print()">🖨 인쇄 / PDF 저장</button>
      <button class="btn btn-outline" onclick="copyLink()">🔗 링크 복사</button>
    </div>

    <div class="footer">
      <p>이 이모티콘은 <strong>이모티콘 스튜디오</strong>에서<br>AI로 직접 제작한 <strong>나만의 작품</strong>입니다 ❤️</p>
      <p style="margin-top:.5rem">${esc(date)} · ${esc(styleLabel)}</p>
    </div>
  </div>

  <script>
    function copyLink() {
      var text = document.title + ' — ' + window.location.href;
      if (navigator.clipboard) {
        navigator.clipboard.writeText(window.location.href).then(function() { alert('링크가 복사됐어요!'); });
      } else {
        prompt('아래 링크를 복사하세요:', window.location.href);
      }
    }
  </script>
</body>
</html>`;
}

/**
 * 포트폴리오를 새 탭에서 엽니다 (Blob URL — 백엔드 요청 없음).
 */
export function openPortfolio(cuts: Cut[], opts: PortfolioOptions = {}): void {
  const html = buildHTML(cuts, opts);
  const blob = new Blob([html], { type: "text/html; charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const win = window.open(url, "_blank");
  // 새 탭이 열리면 Blob URL 정리
  if (win) {
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }
}
