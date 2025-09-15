1. 功能范围（Scope）
输入：用户上传的 .pptx
处理：
1.	解析 PPT → 结构化 JSON
2.	按规则切块（快速/仔细两种模式），以页为最小颗粒并支持跨块 1 页重叠
3.	以预置 Prompt拼接每块文本 → 并发调用 LLM
4.	归并所有块的返回表格，按页面顺序输出
5.	显示进度（解析 → 发送 Prompt → AI 思考中 → 整理结果）
6.	稳健性：默认不自动重试；允许用户对失败块单独重跑并刷新结果输出：每页一行的三列表格（拼写/语法-表述/逻辑），支持导出 CSV/Excel
不做：修正文案本身；对非文本对象（图片/图表数据）做 OCR 或数值校验（后续可扩展）。
________________________________________
2. 端到端流程（E2E）
1.	上传：前端接收 .pptx → 后端存储临时对象（加密，时效 24h）。
2.	解析：见第三节
3.	切块（见第 4 节）：按模式将多页聚合为若干块，不拆页，并在块间重叠 1 页。
4.	Prompt 拼装：对每块构造固定前言 + slides JSON，并追加输出格式约束（只允许强化“返回结构”，不改任务语义）。
5.	并发执行：按块并发调用 LLM（限流可配），收集每块的标准化表格结果。
6.	归并排序：以 page_number 为主键合并多块结果（处理重叠页去重/合并），生成最终全册表。
7.	展示与导出：前端展示可筛选表格（支持按问题类型/是否为空筛选），并提供 CSV/XLSX 导出。
8.	失败重跑：标记失败块，允许单块重提并增量刷新汇总。
________________________________________
3. 数据模型（关键 Schema）
3.1 解析后每页 JSON
{
  "slide_number": 1,
  "elements": "Market growth slows in FY25",
  "notes": "- US +2% YoY\\\\n- EU -1% YoY\\\\nNote: excludes divested unit"
}
 
3.2 切块结果
{
  "chunk_id": "ck_0001",
  "mode": "fast|precise",
  "page_start": 1,
  "page_end": 8,
  "page_numbers": [1,2,3,4,5,6,7,8],
  "word_count": 5600
}
 
3.3 LLM 请求载荷（每块）
{
  "system": "<固定前言：ZD 任务说明>",
  "user": {
    "slides": [
      {
        "page_number": 1,
        "tagline": "...",
        "body_other": "...",
        "speaker_notes": "Do not review"
      }
      // ...
    ],
    "format": "请按下述表格返回（见第 5 节格式约束）"
  }
}
 
3.4 LLM 标准化返回（解析后内部结构）
虽然模型产出为 Markdown 表格，服务端需将其规范化为 JSON便于合并/导出。
[
  {
    "page_number": 1,
    "spelling": ["recieve", "adress"],
    "grammar": ["Missing article before 'EU'", "Inconsistent tense"],
    "logic": ["↔ p 5: tagline contradicts EU decline"]
  }
]
 
3.5 运行状态（Progress）
{
  "job_id": "job_123",
  "status": "parsing|chunking|prompting|thinking|merging|done|error",
  "counts": {
    "chunks_total": 7,
    "chunks_sent": 7,
    "chunks_completed": 3,
    "chunks_failed": 1
  },
  "percent": 43
}
 
________________________________________
4. 文本切块规则（实现要点）
两种模式均以页为单位，不拆页，跨块重叠 1 页。词数仅统计 tagline + body_other（英文场景）。
•	方案 A｜快速 
o	目标词数/批：4,000–6,500
o	每批最大页数：10 页
o	重叠页数：1 页
•	方案 B｜仔细 
o	目标词数/批：2,500–4,000
o	每批最大页数：5 页
o	重叠页数：1 页
实现建议：
•	逐页累加词数（split(/\\\\s+/) 近似），达到目标上限或页数上限即切块；若下页加入后超上限且当前块为空，则允许单页超限一次以避免死锁。
•	生成块序列后，插入重叠：块 i 的最后 1 页 = 块 i+1 的第一页。
•	为跨页逻辑校验保留重叠，去重策略见第 6 节。
________________________________________
5. Prompt
固定部分（已提供；保持原文，不改任务语义）：
You are a McKinsey-style consultant performing a Zero-Defect (ZD) and logic review of an English-language PowerPoint deck that has been exported for you as easy-to-read JSON.
For every slide you will receive:
• page_number
• tagline – headline text (highest priority)
• body_other – body copy, bullets, call-outs, charts (second priority; ignore purely alphanumeric labels such as “A.” “I-1” that serve only as markers)
• speaker_notes – presenter notes (do not review)
 
Tasks for each slide
Spelling mistakes – typos, repeated letters, wrong homophones, etc.
Grammar / phrasing issues – subject–verb agreement, tense, articles, punctuation, awkward wording, etc.
Logic inconsistencies
Within the slide: contradictions between the tagline and the body_other content, or internal logical gaps.
Across slides: contradictions or mis-alignments between this slide’s tagline and earlier/later taglines. (Reference both page numbers when you spot one.)
Output format
Produce a three-column table where each row corresponds to one slide.
 
Slide Spelling mistakes Grammar / wording issues Logic inconsistencies
• Column 1 – Comma-separated list of spelling mistakes for that slide, or “—” if none.
• Column 2 – Comma-separated list of grammar / wording issues, or “—”.
• Column 3 –
“—” if the slide is logically sound.
Otherwise, a short description of the inconsistency.
For cross-slide issues, prefix with “↔ p X” where X is the other slide’s page_number (e.g., “↔ p 5: tagline contradicts revenue trend”).
• Do NOT correct or rewrite the original content; only list the issues.
 
**Return a GitHub-Flavored Markdown table with columns: page_number | Spelling mistakes | Grammar / wording issues | Logic inconsistencies.
No explanations, no code fences.**
 
________________________________________
6. 结果归并与去重
•	主键：page_number
•	重叠页合并：若同一页在相邻块均出现，进行项级去重（字符串去重/合并）。
•	顺序：按 page_number 升序。
•	空值标准：三列均无问题时使用 —。
•	导出：CSV/XLSX，编码 UTF-8，字段包含：page_number, spelling[], grammar[], logic[] 与 Markdown 展示版各一份。
________________________________________
7. 并发与稳健性（Robustness）
•	并发度：可配（默认 max_concurrency = 5）；遇到 429/限流采用指数退避 + 单块重试 0 次（默认）。
•	失败策略：记录失败 chunk_id 与错误原因；前端提供“仅重跑该块”按钮。重跑成功后触发一次局部归并与 UI 刷新。
•	幂等：同一 job_id + chunk_id + slides hash 的重跑可覆盖旧结果；保留审计日志。
•	参数：temperature=0，top_p=1，seed 可配；超时（如 60s）可配。
________________________________________
8. 进度显示（前端）
状态流：
•	解析 PPT → 发出 Prompt → AI 思考中 → 整理结果
数值逻辑：
•	发出 Prompt进度 = chunks_sent / chunks_total
•	AI 思考中进度 = chunks_completed / chunks_sent
•	整理结果为最后固定 10% 至 100% 的过渡（可按项计时平滑）。
UI 元素：
•	总体进度条 + 分段状态标签
•	块级列表（chunk_id、页范围、状态、重跑按钮、错误信息）
•	结果表格：可筛选（仅显示有问题的页/仅逻辑问题等）
________________________________________
9. 接口设计（示例）
9.1 后端 REST
•	POST /zd/jobs（上传）→ { job_id }
•	GET /zd/jobs/{job_id}（查询进度）→ 见 3.5
•	POST /zd/jobs/{job_id}/run（开始解析+执行，含模式参数 mode=fast|precise）
•	POST /zd/jobs/{job_id}/chunks/{chunk_id}/retry
•	GET /zd/jobs/{job_id}/result?format=markdown|json|csv|xlsx
9.2 错误码（示例）
•	400 PPT_UNSUPPORTED（空文件/格式错误）
•	413 FILE_TOO_LARGE
•	429 RATE_LIMITED
•	500 LLM_ERROR
•	504 LLM_TIMEOUT
________________________________________
10. 关键实现细节与伪代码
10.1 解析PPT
#!/usr/bin/env python3
"""
PowerPoint Text Extractor (CLI Edition)
---------------------------------------
 
• Prompts for:
    1) PowerPoint (.pptx) file path
    2) Desired output format (json / txt)
    3) Output file path
 
• Extracts slide-number-labeled text (titles, body text, tables, chart titles,
  speaker notes, etc.) using python-pptx.
 
• Saves either:
    • Structured JSON  – best for downstream processing
    • Nicely formatted TXT – easy for manual scanning or lightweight AI tools
"""
 
import json
import os
import sys
from pathlib import Path
 
try:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    from pptx.enum.shapes import PP_PLACEHOLDER
except ImportError:
    sys.exit("❌  python-pptx is not installed.  Run:  pip install python-pptx")
 
# ──────────────────────────────────────────────────────────────────────────────
#  Extraction helpers
# ──────────────────────────────────────────────────────────────────────────────
def extract_text_recursive(shape):
    """Recursively pull out text from a shape (handling groups, tables, charts)."""
    chunks = []
    sid = f"Shape ID {shape.shape_id}"
 
    # 1) Plain text frames -----------------------------------------------------
    if shape.has_text_frame and shape.text_frame.text.strip():
        text = shape.text_frame.text.strip()
        type_hint = "Body"
        if shape.is_placeholder:
            ph = shape.placeholder_format
            if ph.type in {
                PP_PLACEHOLDER.TITLE,
                PP_PLACEHOLDER.CENTER_TITLE,
                PP_PLACEHOLDER.SUBTITLE,
                PP_PLACEHOLDER.VERTICAL_TITLE,
            }:
                type_hint = "Title/Subtitle"
            elif ph.type == PP_PLACEHOLDER.BODY:
                type_hint = "Body Placeholder"
            elif ph.type == PP_PLACEHOLDER.OBJECT and "Title" in shape.name:
                type_hint = "Object Title"
 
        chunks.append({"id": sid, "type": type_hint, "text": text})
 
    # 2) Table cells -----------------------------------------------------------
    elif shape.has_table:
        tbl_txt = []
        for r, row in enumerate(shape.table.rows):
            for c, cell in enumerate(row.cells):
                cell_txt = cell.text_frame.text.strip()
                if cell_txt:
                    tbl_txt.append(f"Row {r+1}, Col {c+1}: {cell_txt}")
        if tbl_txt:
            chunks.append({"id": sid, "type": "Table", "text": "\\n".join(tbl_txt)})
 
    # 3) Grouped shapes --------------------------------------------------------
    elif shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        for s in shape.shapes:
            chunks.extend(extract_text_recursive(s))
 
    # 4) Chart title (limited) -------------------------------------------------
    elif shape.has_chart:
        ch = shape.chart
        if ch.has_title and ch.chart_title.text_frame.text.strip():
            chunks.append(
                {
                    "id": sid,
                    "type": "Chart Info",
                    "text": f"Chart Title: {ch.chart_title.text_frame.text.strip()}",
                }
            )
 
    return chunks
 
def extract_powerpoint_text(pptx_path):
    """Return list[dict] – one entry per slide – or None on error."""
    if not Path(pptx_path).exists():
        print(f"❌  File not found: {pptx_path}")
        return None
 
    try:
        prs = Presentation(pptx_path)
    except Exception as exc:
        print(f"❌  Could not open presentation: {exc}")
        return None
 
    slides_data = []
    for idx, slide in enumerate(prs.slides, start=1):
        slide_info = {"slide_number": idx, "elements": [], "notes": None}
 
        for shp in slide.shapes:
            slide_info["elements"].extend(extract_text_recursive(shp))
 
        if slide.has_notes_slide:
            notes_tf = slide.notes_slide.notes_text_frame
            if notes_tf and notes_tf.text.strip():
                slide_info["notes"] = notes_tf.text.strip()
 
        if slide_info["elements"] or slide_info["notes"]:
            slides_data.append(slide_info)
 
    return slides_data
 
# ──────────────────────────────────────────────────────────────────────────────
#  Simple CLI prompts
# ──────────────────────────────────────────────────────────────────────────────
def prompt_path(prompt_msg, must_exist=False, default=None):
    while True:
        path_str = input(f"{prompt_msg}{' ['+default+']' if default else ''}: ").strip()
        if not path_str and default:
            path_str = default
        if not path_str:
            print("  ↳ Please enter a path.")
            continue
        p = Path(path_str).expanduser()
        if must_exist and not p.exists():
            print("  ↳ Path does not exist; try again.")
            continue
        return p
 
def prompt_format():
    while True:
        fmt = input("Choose output format (json/txt): ").strip().lower()
        if fmt in {"json", "txt"}:
            return fmt
        print("  ↳ Enter 'json' or 'txt'.")
 
def main():
    print("\\n📝  PowerPoint Text Extractor (CLI)\\n" + "─" * 40)
 
    pptx_path = prompt_path("Enter .pptx file path", must_exist=True)
 
    out_format = prompt_format()
 
    default_out = (
        pptx_path.with_suffix(".json")
        if out_format == "json"
        else pptx_path.with_suffix(".txt")
    )
    out_path = prompt_output_path(default_out)
 
    # -------------------------------------------------------------------------
    print("\\n🔍  Extracting text …")
    data = extract_powerpoint_text(pptx_path)
    if not data:
        sys.exit("❌  No extractable text found or an error occurred.")
 
    # -------------------------------------------------------------------------
    try:
        if out_format == "json":
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        else:  # txt
            with open(out_path, "w", encoding="utf-8") as f:
                for slide in data:
                    f.write(f"--- Slide {slide['slide_number']} ---\\n\\n")
 
                    titles = [
                        e["text"]
                        for e in slide["elements"]
                        if e["type"] == "Title/Subtitle"
                    ]
                    if titles:
                        f.write("Tagline/Title(s):\\n")
                        for t in titles:
                            f.write(f"- {t}\\n")
                        f.write("\\n")
 
                    f.write("Body/Other Elements:\\n")
                    body_found = False
                    for e in slide["elements"]:
                        if e["type"] != "Title/Subtitle":
                            body_found = True
                            lines = e["text"].splitlines()
                            first = lines[0]
                            rest = "\\n  ".join(lines[1:]) if len(lines) > 1 else ""
                            f.write(f"- [{e['type']} / {e['id']}] {first}")
                            if rest:
                                f.write(f"\\n  {rest}")
                            f.write("\\n")
                    if not body_found:
                        f.write("(No other text elements found on this slide)\\n")
 
                    if slide["notes"]:
                        f.write("\\nSpeaker Notes:\\n")
                        f.write(slide["notes"] + "\\n")
                    else:
                        f.write("\\nSpeaker Notes: (None)\\n")
 
                    f.write("\\n" + "=" * 20 + "\\n\\n")
 
        print(f"✅  Saved output to: {out_path.resolve()}")
    except Exception as exc:
        sys.exit(f"❌  Failed to write output: {exc}")
 
def prompt_output_path(default_path):
    """
    Ask for an output path. If the user types a directory, append the default
    file name. Also auto create the directory tree if it doesn’t exist.
    """
    while True:
        raw = input(f"Enter output file path [{default_path}]: ").strip()
        raw = raw or str(default_path)
        p = Path(raw).expanduser()
 
        # If they gave a directory, append the default file name
        if p.is_dir() or (not p.suffix and p.exists()):
            p = p / default_path.name
 
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
        except Exception as e:
            print(f"  ↳ Can’t use that location: {e}")
 
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\\n⏹️  Aborted by user.")
________________________________________
________________________________________
11. 性能与质量指标（建议）
•	解析耗时：< 5s/100 页（纯文本）
•	LLM 成功率：> 98%（以块为单位）
•	整体 TTR（100 页，快速模式，5 并发）：可作为基准测量并优化
•	正确性抽检：抽样页人工比对（拼写、语法、逻辑三类各取样）。
________________________________________
12. 前端交互要点
•	上传后立即显示页面统计（总页数/词数估计/建议模式）。
•	模式切换提示： 
o	快速：吞吐优先、成本更低
o	仔细：查错更敏感、跨页逻辑更稳
•	结果页： 
o	表格行 = 页；三列问题；空用 —；可展开查看原始 tagline/body_other 预览
o	失败块醒目标识 + “重跑”
13. LLM 设置
•	使用chatgpt作为LLM模型， 允许用户选择模型，包括gpt-5，gpt-5-thinking，gpt-4.5，gpt-5-pro
•	模型设置参考environment中的base url和api key
 
