#!/bin/bash
# ──────────────────────────────────────────────────────────────
# git_push.sh — exFAT 소스 → APFS 클론 동기화 후 GitHub push
#
# 사용법:
#   bash git_push.sh "커밋 메시지"
#   bash git_push.sh          (메시지 없으면 자동 생성)
# ──────────────────────────────────────────────────────────────

SOURCE="/Volumes/JJU/#Project/Mac/emoticon/KakaoEmoticonFactory"
REPO="/Users/jjugii/EmoticonFactory_repo"
MSG="${1:-auto: $(date '+%Y-%m-%d %H:%M') 변경사항 반영}"

echo "📂 exFAT → APFS 동기화 중..."
rsync -a \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='.venv_windows_backup/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='outputs/' \
  --exclude='inputs/' \
  --exclude='logs/' \
  --exclude='web/jobs/*' \
  --exclude='web/frontend/.next/' \
  --exclude='web/frontend/node_modules/' \
  --exclude='node_modules/' \
  --exclude='AI_CONTEXT/' \
  --exclude='._*' \
  --exclude='.DS_Store' \
  --exclude='reference.jpg' \
  --exclude='reference_.png' \
  --exclude='reference*.jpg' \
  --exclude='reference*.png' \
  --exclude='config.yml' \
  --exclude='cloudflare/config.yml' \
  --exclude='cloudflare/tunnel.env' \
  --exclude='ngrok/ngrok.env' \
  --exclude='.env' \
  "$SOURCE/" "$REPO/"

echo "📝 변경된 파일:"
cd "$REPO" && git status --short | head -20

echo ""
echo "🚀 커밋 & push: $MSG"
git add -A
git commit -m "$MSG

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>" 2>/dev/null || echo "변경사항 없음 (nothing to commit)"
git push origin main

echo "✅ 완료! https://github.com/JJUGII/EmoticonFactory"
