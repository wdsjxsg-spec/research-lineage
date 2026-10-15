#!/usr/bin/env bash
# 安装或更新 research-lineage skill,并下载期刊/会议等级表。
#
#   一键安装(装到 ~/.claude/skills,对所有项目可用):
#     curl -fsSL https://raw.githubusercontent.com/wdsjxsg-spec/research-lineage/main/install.sh | bash
#   只装到某个项目(装到 <项目>/.claude/skills):
#     curl -fsSL .../install.sh | bash -s -- --project /path/to/project
#   在已克隆的仓库里:
#     ./install.sh [--project DIR] [--no-data]
#
# 环境变量:REPO_URL 覆盖仓库地址;REF 指定分支或 tag(默认 main)。
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/wdsjxsg-spec/research-lineage.git}"
REF="${REF:-main}"
SKILLS_DIR="$HOME/.claude/skills"
FETCH_DATA=1

while [ $# -gt 0 ]; do
  case "$1" in
    --project) mkdir -p "$2"; SKILLS_DIR="$(cd "$2" && pwd)/.claude/skills"; shift 2 ;;
    --no-data) FETCH_DATA=0; shift ;;
    -h|--help) echo "用法: install.sh [--project DIR] [--no-data]   (环境变量 REPO_URL、REF 可选)"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done
DEST="$SKILLS_DIR/research-lineage"

need() { command -v "$1" >/dev/null 2>&1 || { echo "缺少 $1,请先安装" >&2; exit 1; }; }
need git
need python3
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
  || { echo "需要 Python 3.9 或更高版本(当前 $(python3 -V 2>&1))" >&2; exit 1; }

# 从已克隆的仓库运行、且它就是目标目录:只补数据
HERE=""  # 通过 curl | bash 运行时为空
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [ -n "$HERE" ] && [ -f "$HERE/SKILL.md" ] && [ "$HERE" = "$DEST" ]; then
  echo "skill 已在 $DEST"
elif [ -d "$DEST/.git" ]; then
  echo "更新 $DEST"
  git -C "$DEST" pull --ff-only
elif [ -e "$DEST" ]; then
  echo "$DEST 已存在但不是 git 仓库。请先移走它(其中 data/ 下的 CSV 可以保留后放回)再重试。" >&2
  exit 1
else
  mkdir -p "$SKILLS_DIR"
  if [ -n "$HERE" ] && [ -f "$HERE/SKILL.md" ] && [ -d "$HERE/.git" ]; then
    echo "从本地仓库 $HERE 克隆到 $DEST"
    git clone "$HERE" "$DEST"
  else
    echo "从 $REPO_URL ($REF) 克隆到 $DEST"
    git clone --depth 1 --branch "$REF" "$REPO_URL" "$DEST"
  fi
fi

if [ "$FETCH_DATA" = 1 ]; then
  # 仓库自带等级表;这里只补下缺失的文件(例如数据被移除后)
  python3 -I "$DEST/scripts/fetch_data.py" || echo "等级表补下载失败：其余功能可用，稍后运行 python3 -I $DEST/scripts/fetch_data.py 重试" >&2
fi

cat <<EOF

安装完成:$DEST
在 Claude Code 中打开存放论文的项目，说"分析这批论文的研究脉络"即可使用。
可选：设置 S2_API_KEY(Semantic Scholar,免费申请)可减少限流;
      设置 OPENALEX_MAILTO=<你的邮箱> 可进入 OpenAlex 的礼貌队列。
更新:再次运行本脚本，或 git -C $DEST pull
EOF
