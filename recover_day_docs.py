#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Recover one day's Daily Paper README and sidebar from existing docs/*.md files.

Usage:
  python recover_day_docs.py --date 20260507

It will scan:
  docs/202605/07/*.md

and regenerate:
  docs/202605/07/README.md
  docs/_sidebar.md

No LLM call. No JINA call. No token cost.
"""

import argparse
import json
import os
import re
from datetime import datetime
from typing import Dict, List, Tuple, Any


ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
DOCS_DIR = os.path.join(ROOT_DIR, "docs")


def format_date_str(date_str: str) -> str:
    s = str(date_str or "").strip()
    m = re.fullmatch(r"(\d{8})-(\d{8})", s)
    if m:
        a, b = m.group(1), m.group(2)
        return f"{a[:4]}-{a[4:6]}-{a[6:]} ~ {b[:4]}-{b[4:6]}-{b[6:]}"
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s


def build_docsify_id_href(path_no_ext: str) -> str:
    p = str(path_no_ext or "").strip().replace("\\", "/")
    p = re.sub(r"\.md$", "", p, flags=re.IGNORECASE)
    return "/" + p.lstrip("/")


def get_day_dir(date_str: str) -> str:
    s = str(date_str or "").strip()
    if re.fullmatch(r"\d{8}-\d{8}", s):
        return os.path.join(DOCS_DIR, s)
    return os.path.join(DOCS_DIR, s[:6], s[6:])


def paper_id_from_md_path(md_path: str) -> str:
    rel = os.path.relpath(md_path, DOCS_DIR).replace("\\", "/")
    if rel.lower().endswith(".md"):
        rel = rel[:-3]
    return rel.strip("/")


def parse_simple_front_matter(md_text: str) -> Dict[str, Any]:
    text = (md_text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text.startswith("---\n"):
        return {}

    end = text.find("\n---", 3)
    if end == -1:
        return {}

    block = text[4:end].strip()
    meta: Dict[str, Any] = {}

    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        raw = raw.strip()
        if not key:
            continue

        # Very lightweight parser; enough for title/score/tags/tldr/evidence.
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            if inner:
                items = []
                cur = ""
                in_quote = False
                quote_char = ""
                escape = False
                for ch in inner:
                    if escape:
                        cur += ch
                        escape = False
                        continue
                    if ch == "\\":
                        cur += ch
                        escape = True
                        continue
                    if ch in ("'", '"') and not in_quote:
                        in_quote = True
                        quote_char = ch
                        cur += ch
                        continue
                    if in_quote and ch == quote_char:
                        in_quote = False
                        quote_char = ""
                        cur += ch
                        continue
                    if ch == "," and not in_quote:
                        val = cur.strip().strip('"').strip("'")
                        if val:
                            items.append(val)
                        cur = ""
                        continue
                    cur += ch
                val = cur.strip().strip('"').strip("'")
                if val:
                    items.append(val)
                meta[key] = items
            else:
                meta[key] = []
        else:
            val = raw.strip().strip('"').strip("'")
            val = val.replace("\\n", "\n").replace('\\"', '"')
            meta[key] = val

    return meta


def extract_h1_title(md_text: str) -> str:
    for line in (md_text or "").splitlines():
        m = re.match(r"^#\s+(.+)$", line.strip())
        if m:
            return m.group(1).strip()
    return ""


def title_from_filename(fn: str) -> str:
    base = fn[:-3] if fn.lower().endswith(".md") else fn
    # remove arxiv id prefix
    base = re.sub(r"^\d{4}\.\d{4,6}v\d+-", "", base)
    return base.replace("-", " ").strip() or fn


def parse_paper_md(md_path: str) -> Tuple[str, str, float, List[str], str, str]:
    """
    Returns:
      paper_id, title, score, tags, evidence, section
    """
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()

    meta = parse_simple_front_matter(text)
    paper_id = paper_id_from_md_path(md_path)

    title = str(meta.get("title") or "").strip()
    if not title:
        title = extract_h1_title(text)
    if not title:
        title = title_from_filename(os.path.basename(md_path))

    score_raw = str(meta.get("score") or "").strip()
    try:
        score = float(score_raw)
    except Exception:
        score = 0.0

    raw_tags = meta.get("tags") or []
    tags: List[str] = []
    if isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    elif isinstance(raw_tags, str):
        tags = [t.strip() for t in re.split(r",|，", raw_tags) if t.strip()]

    evidence = str(meta.get("evidence") or "").strip()

    # If detailed summary exists, classify as deep; otherwise quick.
    section = "deep" if "## 论文详细总结（自动生成）" in text else "quick"

    return paper_id, title, score, tags, evidence, section


def score_suffix(score: float) -> str:
    return f"（{score:.1f}/10）" if score > 0 else ""


def build_day_readme(date_str: str, deep: List[dict], quick: List[dict]) -> str:
    label = format_date_str(date_str)
    lines: List[str] = []
    lines.append(f"# 日报 · {label}")
    lines.append("")
    lines.append(f"- 恢复时间：{datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"- 当天论文总数：{len(deep) + len(quick)}")
    lines.append(f"- 精读区：{len(deep)}")
    lines.append(f"- 速读区：{len(quick)}")
    lines.append("")
    lines.append("> 该日报由本地恢复脚本根据当天已存在的论文 Markdown 文件重建，未重新调用 LLM。")
    lines.append("")

    lines.append("## 精读区")
    if deep:
        for i, item in enumerate(deep, start=1):
            href = build_docsify_id_href(item["paper_id"])
            lines.append(f"{i}. [{item['title']}]({href}) {score_suffix(item['score'])}")
    else:
        lines.append("- 本次无精读推荐。")
    lines.append("")

    lines.append("## 速读区")
    if quick:
        for i, item in enumerate(quick, start=1):
            href = build_docsify_id_href(item["paper_id"])
            lines.append(f"{i}. [{item['title']}]({href}) {score_suffix(item['score'])}")
    else:
        lines.append("- 本次无速读推荐。")
    lines.append("")

    lines.append("---")
    lines.append("使用键盘方向键可在日报/论文之间快速切换。")
    lines.append("")
    return "\n".join(lines)


def build_sidebar_block(date_str: str, deep: List[dict], quick: List[dict]) -> List[str]:
    label = format_date_str(date_str)
    marker = f"<!--dpr-date:{date_str}-->"
    block: List[str] = [f"  * {label} {marker}\n"]

    if deep:
        block.append("    * 精读区\n")
        for item in deep:
            title = item["title"].replace('"', "&quot;")
            href = f"#/{item['paper_id']}"
            payload = {
                "title": item["title"],
                "link": href,
                "score": f"{item['score']:.1f}" if item["score"] > 0 else "-",
                "tags": [{"kind": "query", "label": t.split(":", 1)[-1]} for t in item["tags"]],
            }
            if item.get("evidence"):
                payload["evidence"] = item["evidence"]
            payload_json = json.dumps(payload, ensure_ascii=False).replace('"', "&quot;")
            block.append(
                f'      * <a class="dpr-sidebar-item-link dpr-sidebar-item-structured" '
                f'href="{href}" data-sidebar-item="{payload_json}">{title}</a>\n'
            )

    if quick:
        block.append("    * 速读区\n")
        for item in quick:
            title = item["title"].replace('"', "&quot;")
            href = f"#/{item['paper_id']}"
            payload = {
                "title": item["title"],
                "link": href,
                "score": f"{item['score']:.1f}" if item["score"] > 0 else "-",
                "tags": [{"kind": "query", "label": t.split(":", 1)[-1]} for t in item["tags"]],
            }
            if item.get("evidence"):
                payload["evidence"] = item["evidence"]
            payload_json = json.dumps(payload, ensure_ascii=False).replace('"', "&quot;")
            block.append(
                f'      * <a class="dpr-sidebar-item-link dpr-sidebar-item-structured" '
                f'href="{href}" data-sidebar-item="{payload_json}">{title}</a>\n'
            )

    return block


def update_sidebar(date_str: str, deep: List[dict], quick: List[dict]) -> None:
    sidebar_path = os.path.join(DOCS_DIR, "_sidebar.md")
    marker = f"<!--dpr-date:{date_str}-->"
    block = build_sidebar_block(date_str, deep, quick)

    lines: List[str] = []
    if os.path.exists(sidebar_path):
        with open(sidebar_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    daily_idx = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("* Daily Papers"):
            daily_idx = i
            break

    if daily_idx == -1:
        if not any("[首页]" in line for line in lines):
            lines.append("* [首页](/)\n")
        lines.append("* Daily Papers\n")
        daily_idx = len(lines) - 1

    # Remove existing block for same date if present.
    day_idx = -1
    for i in range(daily_idx + 1, len(lines)):
        if lines[i].startswith("* "):
            break
        if marker in lines[i]:
            day_idx = i
            break

    if day_idx != -1:
        end = day_idx + 1
        while end < len(lines):
            if lines[end].startswith("  * ") and not lines[end].startswith("    * "):
                break
            if lines[end].startswith("* "):
                break
            end += 1
        del lines[day_idx:end]

    insert_idx = daily_idx + 1
    lines[insert_idx:insert_idx] = block

    os.makedirs(os.path.dirname(sidebar_path), exist_ok=True)
    with open(sidebar_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def sync_home_readme(date_str: str, deep: List[dict], quick: List[dict]) -> None:
    home_path = os.path.join(DOCS_DIR, "README.md")
    label = format_date_str(date_str)
    if re.fullmatch(r"\d{8}-\d{8}", date_str):
      day_href = build_docsify_id_href(f"{date_str}/README")
    else:
      day_href = build_docsify_id_href(f"{date_str[:6]}/{date_str[6:]}/README")

    lines: List[str] = []
    lines.append("────────────────────────────────────────")
    lines.append("（公告占位）欢迎使用 Daily Paper Reader。")
    lines.append("────────────────────────────────────────")
    lines.append("")
    lines.append("## 每次日报")
    lines.append(f"- 最新运行日期：{label}")
    lines.append(f"- 恢复时间：{datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"- 本次总论文数：{len(deep) + len(quick)}")
    lines.append(f"- 精读区：{len(deep)}")
    lines.append(f"- 速读区：{len(quick)}")
    lines.append(f"- 详情：[{day_href}]({day_href})")
    lines.append("")
    lines.append("### 精读区")
    if deep:
        for i, item in enumerate(deep, start=1):
            lines.append(f"{i}. [{item['title']}]({build_docsify_id_href(item['paper_id'])}) {score_suffix(item['score'])}")
    else:
        lines.append("- 本次无精读推荐。")
    lines.append("")
    lines.append("### 速读区")
    if quick:
        for i, item in enumerate(quick, start=1):
            lines.append(f"{i}. [{item['title']}]({build_docsify_id_href(item['paper_id'])}) {score_suffix(item['score'])}")
    else:
        lines.append("- 本次无速读推荐。")
    lines.append("")
    lines.append("════════════════════════════════════════")
    lines.append("（宣传占位）欢迎 Star / Fork 本项目。")
    lines.append("════════════════════════════════════════")
    lines.append("")

    with open(home_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYYMMDD, e.g. 20260507")
    args = parser.parse_args()

    date_str = args.date.strip()
    day_dir = get_day_dir(date_str)

    if not os.path.isdir(day_dir):
        raise SystemExit(f"[ERROR] day dir not found: {day_dir}")

    papers: List[dict] = []
    for fn in sorted(os.listdir(day_dir)):
        if not fn.lower().endswith(".md"):
            continue
        if fn.upper() == "README.MD" or fn.startswith("_"):
            continue

        md_path = os.path.join(day_dir, fn)
        try:
            paper_id, title, score, tags, evidence, section = parse_paper_md(md_path)
        except Exception as e:
            print(f"[WARN] skip {fn}: {e}")
            continue

        papers.append(
            {
                "paper_id": paper_id,
                "title": title,
                "score": score,
                "tags": tags,
                "evidence": evidence,
                "section": section,
            }
        )

    papers.sort(key=lambda x: (-float(x.get("score") or 0), x["paper_id"]))
    deep = [p for p in papers if p["section"] == "deep"]
    quick = [p for p in papers if p["section"] != "deep"]

    day_readme = os.path.join(day_dir, "README.md")
    with open(day_readme, "w", encoding="utf-8") as f:
        f.write(build_day_readme(date_str, deep, quick))

    update_sidebar(date_str, deep, quick)
    sync_home_readme(date_str, deep, quick)

    print(f"[OK] recovered papers: total={len(papers)}, deep={len(deep)}, quick={len(quick)}")
    print(f"[OK] updated: {day_readme}")
    print(f"[OK] updated: {os.path.join(DOCS_DIR, '_sidebar.md')}")
    print(f"[OK] updated: {os.path.join(DOCS_DIR, 'README.md')}")


if __name__ == "__main__":
    main()
