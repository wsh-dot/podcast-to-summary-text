import html
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from visual_brief import ManifestValidationError, validate_visual_brief
from visual_remote import source_time_url


@dataclass(frozen=True)
class VisualBriefResult:
    html_path: Path
    assets_dir: Optional[Path]


class VisualStageError(RuntimeError):
    pass


class _OfflineHTMLValidator(HTMLParser):
    def __init__(self, assets_name):
        super().__init__()
        self.assets_name = assets_name
        self.has_details = False
        self.has_viewport = False
        self.has_main = False
        self.has_compact_editorial = False
        self.errors = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = attributes.get("class", "").split()
        if "compact-editorial" in classes:
            self.has_compact_editorial = True
        if tag == "details":
            self.has_details = True
        elif tag == "main":
            self.has_main = True
        elif tag == "meta" and attributes.get("name") == "viewport":
            self.has_viewport = True
        elif tag == "link":
            self.errors.append("external link resources are forbidden")
        elif tag == "script" and attributes.get("src"):
            self.errors.append("external scripts are forbidden")
        elif tag == "img":
            source = attributes.get("src", "")
            path = Path(source)
            if not self.assets_name:
                self.errors.append("images are forbidden in compact editorial output")
            elif path.is_absolute() or ".." in path.parts or not source.startswith(f"{self.assets_name}/"):
                self.errors.append("image paths must be confined to the sibling asset directory")


def _text(value):
    return html.escape(str(value), quote=True)


def _claim_text(value):
    return _text(value["text"])


def _source_attrs(value):
    windows = value.get("source_windows", [])
    joined = " ".join(windows)
    readable = ", ".join(windows)
    return f' data-source-windows="{_text(joined)}" title="Sources: {_text(readable)}"'


def _single_source_attrs(window):
    return _source_attrs({"source_windows": [window]})


def _window_start_seconds(window):
    start = window.split("-", 1)[0]
    minute, second = map(int, start.split(":"))
    return minute * 60 + second


def _render_visual(visual):
    visual_type = visual["type"]
    title_value = visual["title"]
    title = _claim_text(title_value)
    if visual_type == "quote":
        body = (
            f'<blockquote{_single_source_attrs(visual["source_window"])}>'
            f'{_text(visual["quote"])}</blockquote>'
        )
    elif visual_type == "comparison":
        body = "".join(
            f'<div{_source_attrs(item)}><strong>{_text(item["label"])}</strong>'
            f'<span>{_text(item["value"])}</span></div>'
            for item in visual.get("items", [])
        )
    elif visual_type == "relationship":
        body = "".join(
            f'<div{_source_attrs(item)}><strong>{_text(item["from"])}</strong>'
            f'<span>{_text(item["label"])}</span><strong>{_text(item["to"])}</strong></div>'
            for item in visual.get("items", [])
        )
    elif visual_type == "metrics":
        body = "".join(
            f'<div{_single_source_attrs(item["source_window"])}>'
            f'<strong>{_text(item["value"])}</strong><span>{_text(item["label"])}</span></div>'
            for item in visual.get("items", [])
        )
    else:
        body = "".join(
            f'<li{_source_attrs(item)}>{_claim_text(item)}</li>'
            for item in visual.get("items", [])
        )
        body = f"<ol>{body}</ol>"
    return (
        f'<figure class="visual {visual_type}-visual">'
        f'<figcaption{_source_attrs(title_value)}>{title}</figcaption>{body}</figure>'
    )


def _is_compact_profile(blocks, metadata):
    text = "".join(
        block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
        for block in blocks
    )
    cjk_count = sum("\u4e00" <= char <= "\u9fff" for char in text)
    latin_count = sum(char.isascii() and char.isalpha() for char in text)
    duration = metadata.get("duration_seconds")
    long_form = isinstance(duration, (int, float)) and duration > 3600
    if not long_form:
        long_form = len(blocks) > 20
    return long_form and cjk_count > 0 and cjk_count >= latin_count


def _relationship_is_cycle(items):
    if len(items) < 3:
        return False
    outgoing = {item.get("from"): item.get("to") for item in items}
    start = items[0].get("from")
    current = start
    visited = set()
    for _ in range(len(items)):
        if current in visited or current not in outgoing:
            return False
        visited.add(current)
        current = outgoing[current]
    return current == start and len(visited) == len(items)


def _compact_visual_body(visual):
    visual_type = visual["type"]
    items = visual.get("items", [])
    accent = (
        '<svg class="diagram-accent" viewBox="0 0 120 12" aria-hidden="true">'
        '<path d="M2 6H112"/><path d="m106 2 6 4-6 4"/></svg>'
    )
    if visual_type == "process":
        diagram_class = "flow-diagram" if len(items) <= 4 else "timeline-diagram"
        nodes = "".join(
            f'<div class="diagram-node"{_source_attrs(item)}><span>{index:02d}</span>'
            f'<strong>{_claim_text(item)}</strong></div>'
            for index, item in enumerate(items, start=1)
        )
        return f'{accent}<div class="{diagram_class}">{nodes}</div>'
    if visual_type == "comparison":
        nodes = "".join(
            f'<div{_source_attrs(item)}><span>{_text(item["label"])}</span>'
            f'<strong>{_text(item["value"])}</strong></div>'
            for item in items
        )
        return f'{accent}<div class="comparison-diagram">{nodes}</div>'
    if visual_type == "relationship":
        diagram_class = "flywheel-diagram" if _relationship_is_cycle(items) else "network-diagram"
        nodes = "".join(
            f'<div{_source_attrs(item)}><strong>{_text(item["from"])}</strong>'
            f'<span>{_text(item["label"])}</span><strong>{_text(item["to"])}</strong></div>'
            for item in items
        )
        return f'{accent}<div class="{diagram_class}">{nodes}</div>'
    if visual_type == "metrics":
        nodes = "".join(
            f'<div{_single_source_attrs(item["source_window"])}><strong>{_text(item["value"])}</strong>'
            f'<span>{_text(item["label"])}</span></div>'
            for item in items
        )
        return f'{accent}<div class="metrics-diagram">{nodes}</div>'
    nodes = "".join(
        f'<div{_source_attrs(item)}><span>{index:02d}</span><strong>{_claim_text(item)}</strong></div>'
        for index, item in enumerate(items, start=1)
    )
    return f'{accent}<div class="layered-diagram">{nodes}</div>'


def _render_compact_visual(visual):
    title = visual["title"]
    return (
        f'<figure class="editorial-visual {_text(visual["type"])}-visual">'
        f'<figcaption{_source_attrs(title)}>{_claim_text(title)}</figcaption>'
        f'{_compact_visual_body(visual)}</figure>'
    )


def _render_compact_page(blocks, metadata, media_source, manifest):
    title = _text(metadata.get("title", "图文解读"))
    language = _text(metadata.get("language", "zh-CN"))
    insights = "".join(
        f'<li{_source_attrs(item)}><span>{index:02d}</span><p>{_claim_text(item)}</p></li>'
        for index, item in enumerate(manifest["core_insights"], start=1)
    )
    chapter_html = []
    for index, chapter in enumerate(manifest["chapters"], start=1):
        evidence = "".join(
            f'<li><span>{_text(item["window"])}</span>{_text(item["label"])}</li>'
            for item in chapter.get("evidence", [])
        )
        visuals = "".join(_render_compact_visual(item) for item in chapter.get("visuals", []))
        if not visuals:
            visuals = '<div class="editorial-text-treatment">本节以文字解读呈现</div>'
        chapter_html.append(
            f'<section id="{_text(chapter["id"])}" class="chapter-band">'
            f'<div class="chapter-copy"><p class="chapter-index">SECTION {index:02d}</p>'
            f'<h2{_source_attrs(chapter["title"])}>{_claim_text(chapter["title"])}</h2>'
            f'<p class="chapter-summary"{_source_attrs(chapter["summary"])}>'
            f'{_claim_text(chapter["summary"])}</p><ul class="source-tags">{evidence}</ul></div>'
            f'<div class="chapter-graphics">{visuals}</div></section>'
        )
    source_link = ""
    if media_source.get("url"):
        source_link = f'<a class="source-link" href="{_text(media_source["url"])}">查看原始来源</a>'
    return f'''<!doctype html>
<html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>
:root{{--ink:#172026;--paper:#f7f4ee;--white:#fff;--red:#dc563f;--teal:#397b80;--line:#cfc9bd;--soft:#e8e3d9}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--paper);color:var(--ink);font:17px/1.75 system-ui,"Microsoft YaHei",sans-serif;letter-spacing:0}}
a{{color:var(--teal);text-underline-offset:3px}}a:focus-visible{{outline:3px solid var(--red);outline-offset:4px}}.skip{{position:absolute;left:-9999px}}.skip:focus{{left:1rem;top:1rem;background:white;padding:.6rem;z-index:2}}
.compact-editorial{{max-width:1080px;margin:auto;padding:0 32px}}.page-header{{padding:64px 0 46px;border-bottom:3px solid var(--ink)}}.kicker,.chapter-index{{font-size:.78rem;font-weight:800;color:var(--red);letter-spacing:0;text-transform:uppercase}}
h1{{font:800 4rem/1.08 Georgia,"Microsoft YaHei",serif;margin:10px 0 24px}}.overview{{max-width:48rem;font-size:1.12rem;margin:0 0 18px}}
.insights{{padding:42px 0 52px}}.section-label{{font-size:.85rem;font-weight:800;border-bottom:1px solid var(--line);padding-bottom:9px}}.insight-grid{{list-style:none;padding:0;margin:22px 0 0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}
.insight-grid li{{background:var(--white);padding:20px;display:grid;grid-template-columns:34px 1fr;gap:10px;border-top:4px solid var(--teal)}}.insight-grid span{{color:var(--red);font-weight:800}}.insight-grid p{{margin:0}}
.chapter-band{{display:grid;grid-template-columns:minmax(260px,.78fr) minmax(0,1.22fr);gap:44px;padding:58px 0;border-top:1px solid var(--line)}}.chapter-copy h2{{font:800 2rem/1.2 Georgia,"Microsoft YaHei",serif;margin:8px 0 18px}}.chapter-summary{{margin:0}}
.source-tags{{list-style:none;padding:0;margin:22px 0 0;display:flex;flex-wrap:wrap;gap:8px}}.source-tags li{{font-size:.76rem;background:var(--soft);padding:5px 8px}}.source-tags span{{color:var(--red);font-weight:800;margin-right:6px}}
.chapter-graphics{{display:grid;gap:18px}}.editorial-visual{{margin:0;background:var(--white);padding:22px;border:1px solid var(--line)}}figcaption{{font-size:1.05rem;font-weight:800;margin-bottom:16px}}.diagram-accent{{display:block;width:120px;height:12px;margin-bottom:18px;fill:none;stroke:var(--red);stroke-width:2}}
.flow-diagram{{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px}}.diagram-node{{padding:14px;background:var(--soft);min-height:92px;display:grid;align-content:space-between}}.diagram-node span,.layered-diagram span{{font-size:.72rem;color:var(--red);font-weight:800}}.diagram-node strong{{font-size:.95rem}}
.timeline-diagram{{display:grid;gap:0;border-left:3px solid var(--teal);margin-left:12px}}.timeline-diagram .diagram-node{{position:relative;background:transparent;min-height:0;padding:10px 14px 10px 22px}}.timeline-diagram .diagram-node:before{{content:"";position:absolute;width:11px;height:11px;border-radius:50%;background:var(--red);left:-7px;top:18px}}
.comparison-diagram{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}.comparison-diagram>div{{padding:18px;background:var(--soft);display:grid;gap:8px}}.comparison-diagram span{{font-size:.78rem;color:var(--teal);font-weight:800}}
.flywheel-diagram,.network-diagram{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}.flywheel-diagram>div,.network-diagram>div{{padding:14px;border:2px solid var(--teal);display:grid;gap:5px;text-align:center}}.flywheel-diagram span,.network-diagram span{{color:var(--red);font-size:.8rem}}
.metrics-diagram{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}}.metrics-diagram>div{{background:var(--ink);color:white;padding:18px;display:grid}}.metrics-diagram strong{{font-size:2rem;color:#79c6bf}}.metrics-diagram span{{font-size:.8rem}}
.layered-diagram{{display:flex;flex-direction:column-reverse;gap:6px}}.layered-diagram>div{{padding:13px 16px;background:var(--soft);display:flex;gap:12px;justify-content:center}}.layered-diagram>div:nth-child(2){{margin-inline:7%}}.layered-diagram>div:nth-child(3){{margin-inline:14%}}
.editorial-text-treatment{{padding:22px;border-left:5px solid var(--red);background:var(--white)}}footer{{padding:34px 0 60px;border-top:3px solid var(--ink);font-size:.82rem;color:var(--teal)}}
@media(max-width:760px){{body{{font-size:16px}}.compact-editorial{{padding:0 18px}}.page-header{{padding:42px 0 34px}}h1{{font-size:2.35rem;overflow-wrap:anywhere}}.insight-grid,.chapter-band{{grid-template-columns:1fr}}.chapter-band{{gap:24px;padding:42px 0}}.comparison-diagram{{grid-template-columns:1fr}}}}
@media(prefers-reduced-motion:reduce){{html{{scroll-behavior:auto}}}}@media print{{body{{background:white}}.compact-editorial{{max-width:none}}}}
</style></head><body><a class="skip" href="#content">跳至正文</a><main id="content" class="compact-editorial">
<header class="page-header"><p class="kicker">TRANSCRIPT INTERPRETATION</p><h1>{title}</h1><p class="overview"{_source_attrs(manifest["overview"])}>{_claim_text(manifest["overview"])}</p>{source_link}</header>
<section class="insights"><p class="section-label">核心结论</p><ol class="insight-grid">{insights}</ol></section>{''.join(chapter_html)}
<footer>基于完整校对转写稿整理 · {len(blocks)} 个来源窗口</footer></main></body></html>'''


def _render_page(blocks, timeline_report, metadata, media_source, manifest,
                 frames_by_chapter, assets_name):
    title = _text(metadata.get("title", "Visual brief"))
    language = _text(metadata.get("language", "zh-CN"))
    insights = "".join(
        f'<li{_source_attrs(item)}>{_claim_text(item)}</li>'
        for item in manifest.get("core_insights", [])
    )
    navigation = "".join(
        f'<li><a href="#{_text(chapter["id"])}"{_source_attrs(chapter["title"])}>'
        f'{_claim_text(chapter["title"])}</a></li>'
        for chapter in manifest["chapters"]
    )
    chapters = []
    for chapter in manifest["chapters"]:
        source_url = media_source.get("url")
        chapter_source_url = source_time_url(
            source_url,
            _window_start_seconds(chapter["source_windows"][0]),
        )
        source_time = chapter["source_windows"][0].split("-", 1)[0]
        chapter_source_link = ""
        if chapter_source_url:
            label = "Open original source"
            if chapter_source_url != source_url:
                label = f"Open source at {source_time}"
            chapter_source_link = (
                f'<p><a class="chapter-source-link" href="{_text(chapter_source_url)}">'
                f'{_text(label)}</a></p>'
            )
        evidence = "".join(
            f'<li><span class="evidence-window">{_text(item["window"])}</span> {_text(item["label"])}</li>'
            for item in chapter.get("evidence", [])
        )
        visuals = "".join(_render_visual(item) for item in chapter.get("visuals", []))
        frame = frames_by_chapter.get(chapter["id"])
        frame_html = ""
        if frame:
            frame_html = (
                '<figure class="source-frame">'
                f'<img src="{_text(assets_name)}/frames/{_text(frame["filename"])}" '
                f'width="{frame["width"]}" height="{frame["height"]}" '
                f'style="--frame-ratio:{frame["width"]}/{frame["height"]}" '
                f'alt="{_text(frame["alt"])}" loading="lazy" decoding="async">'
                f'<figcaption>{_text(frame["caption"])}</figcaption></figure>'
            )
        if visuals:
            summary = (
                f'<p{_source_attrs(chapter["summary"])}>'
                f'{_claim_text(chapter["summary"])}</p>'
            )
        else:
            summary = (
                '<div class="editorial-insight">'
                f'<p{_source_attrs(chapter["summary"])}>'
                f'{_claim_text(chapter["summary"])}</p></div>'
            )
        chapters.append(
            f'<section id="{_text(chapter["id"])}" class="chapter">'
            f'<h2{_source_attrs(chapter["title"])}>{_claim_text(chapter["title"])}</h2>'
            f'{chapter_source_link}{summary}'
            f'<ul class="evidence">{evidence}</ul>{frame_html}{visuals}'
            f'</section>'
        )
    page_data = json.dumps(manifest, ensure_ascii=True).replace("</", "<\\/")
    source_link = ""
    if media_source.get("url"):
        source_link = f'<a class="source-link" href="{_text(media_source["url"])}">Open original source</a>'
    return f'''<!doctype html>
<html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>
:root{{--ink:#202124;--muted:#5f6368;--paper:#fbfbfa;--line:#d9d9d6;--red:#a63d2f;--blue:#2366a8}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;color:var(--ink);background:var(--paper);font:16px/1.65 system-ui,sans-serif}}
a{{color:var(--blue)}}a:focus-visible,summary:focus-visible,button:focus-visible,input:focus-visible{{outline:3px solid var(--blue);outline-offset:3px}}
.skip{{position:absolute;left:-9999px}}.skip:focus{{left:1rem;top:1rem;background:white;padding:.5rem;z-index:3}}
header{{border-bottom:1px solid var(--line);padding:2rem max(1rem,calc((100% - 1180px)/2))}}h1{{font:700 2.4rem/1.15 Georgia,serif;margin:.2rem 0}}.overview{{max-width:72ch}}
.layout{{display:grid;grid-template-columns:minmax(180px,240px) minmax(0,720px) minmax(180px,240px);gap:2rem;max-width:1180px;margin:auto;padding:2rem 1rem}}
nav,aside{{position:sticky;top:1rem;align-self:start}}main{{min-width:0}}.chapter{{padding:0 0 3rem;border-bottom:1px solid var(--line);margin-bottom:3rem}}
.mobile-chapter-nav{{display:none}}
.evidence-window{{color:var(--red);font-weight:700}}.visual{{margin:1.5rem 0;padding:1rem;border-left:4px solid var(--blue);background:white}}figcaption{{font-weight:700;margin-bottom:.75rem}}
.editorial-insight{{margin:1.5rem 0;padding:1rem;border-left:4px solid var(--red);background:white}}
.source-frame{{margin:1.5rem 0}}.source-frame img{{display:block;width:100%;height:auto;aspect-ratio:var(--frame-ratio,16/9);object-fit:contain;background:#111}}
.comparison-visual>div,.relationship-visual>div,.metrics-visual>div{{display:flex;gap:1rem;justify-content:space-between;border-top:1px solid var(--line);padding:.6rem 0}}
details{{margin-top:1.5rem}}summary{{cursor:pointer;font-weight:700}}
.search{{display:grid;gap:.35rem;margin:1rem 0}}input[type=search]{{width:100%;min-height:2.5rem;padding:.5rem;border:1px solid var(--line);border-radius:4px}}svg.icon{{width:1em;height:1em;vertical-align:-.1em;margin-right:.35rem}}
@media(prefers-reduced-motion:reduce){{html{{scroll-behavior:auto}}}}@media(max-width:900px){{.layout{{grid-template-columns:minmax(0,1fr)}}nav,aside{{position:static}}.desktop-navigation{{display:none}}.mobile-chapter-nav{{display:block}}}}@media print{{nav,aside,.mobile-chapter-nav,script{{display:none}}.layout{{display:block}}}}
</style></head><body><svg width="0" height="0" aria-hidden="true" focusable="false"><symbol id="icon-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="m16 16 5 5" fill="none" stroke="currentColor" stroke-width="2"/></symbol></svg><a class="skip" href="#content">Skip to content</a>
<header><p>Offline visual brief</p><h1>{title}</h1><p class="overview"{_source_attrs(manifest["overview"])}>{_claim_text(manifest["overview"])}</p>{source_link}</header>
<div class="layout"><nav class="desktop-navigation" aria-label="Chapter navigation"><h2>Chapter navigation</h2><label class="search" for="chapter-search"><span><svg class="icon" aria-hidden="true"><use href="#icon-search"></use></svg>Search chapters</span><input id="chapter-search" data-chapter-search type="search" autocomplete="off"></label><ol>{navigation}</ol></nav>
<details class="mobile-chapter-nav"><summary>Chapter navigation</summary><label class="search" for="mobile-chapter-search"><span><svg class="icon" aria-hidden="true"><use href="#icon-search"></use></svg>Search chapters</span><input id="mobile-chapter-search" data-chapter-search type="search" autocomplete="off"></label><ol>{navigation}</ol></details>
<main id="content"><section><h2>Core insights</h2><ul>{insights}</ul></section>{''.join(chapters)}</main>
<aside><h2>Current chapter</h2><p id="current-chapter-title"{_source_attrs(manifest["chapters"][0]["title"])}>{_claim_text(manifest["chapters"][0]["title"])}</p><p>{len(blocks)} calibrated source windows</p><p>{_text(metadata.get("duration", ""))}</p></aside></div>
<script type="application/json" id="visual-brief-data">{page_data}</script><script>
document.documentElement.classList.add('js');
const searches = document.querySelectorAll('[data-chapter-search]');
searches.forEach((search) => search.addEventListener('input', () => {{
  const query = search.value.trim().toLocaleLowerCase();
  searches.forEach((other) => {{ if (other !== search) other.value = search.value; }});
  document.querySelectorAll('.chapter').forEach((chapter) => {{
    chapter.hidden = query !== '' && !chapter.textContent.toLocaleLowerCase().includes(query);
  }});
}}));
const currentTitle = document.querySelector('#current-chapter-title');
if ('IntersectionObserver' in window) {{
  const observer = new IntersectionObserver((entries) => {{
    entries.filter((entry) => entry.isIntersecting).forEach((entry) => {{
      currentTitle.textContent = entry.target.querySelector('h2').textContent;
      currentTitle.dataset.sourceWindows = entry.target.querySelector('h2').dataset.sourceWindows;
    }});
  }}, {{ rootMargin: '-20% 0px -60% 0px' }});
  document.querySelectorAll('.chapter').forEach((chapter) => observer.observe(chapter));
}}
</script></body></html>'''


def _validate_staged_html(path, assets_name=None):
    content = path.read_text(encoding="utf-8")
    validator = _OfflineHTMLValidator(assets_name)
    validator.feed(content)
    if not content.lower().startswith("<!doctype html>"):
        validator.errors.append("HTML doctype is missing")
    if '<meta charset="utf-8">' not in content.lower():
        validator.errors.append("UTF-8 charset is missing")
    if not validator.has_viewport:
        validator.errors.append("viewport metadata is missing")
    if not validator.has_main or (not validator.has_details and not validator.has_compact_editorial):
        validator.errors.append("core semantic reader content is missing")
    if validator.errors:
        raise VisualStageError(f"visual static validation failed: {'; '.join(validator.errors)}")


def _remove_path(path):
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _stage_frame_assets(frame_assets, blocks, manifest, staged_assets):
    if not frame_assets:
        return {}
    known_windows = {block.window for block in blocks}
    chapter_windows = {
        chapter["id"]: set(chapter["source_windows"])
        for chapter in manifest["chapters"]
    }
    frames_by_chapter = {}
    for index, record in enumerate(frame_assets, start=1):
        chapter_id = record.get("chapter_id")
        source_window = record.get("source_window")
        source = Path(record.get("path", ""))
        if chapter_id not in chapter_windows or source_window not in known_windows:
            raise VisualStageError("visual frame references an unknown chapter or source window")
        if source_window not in chapter_windows[chapter_id]:
            raise VisualStageError("visual frame source window does not belong to its chapter")
        if not source.is_file() or source.stat().st_size == 0 or source.suffix.lower() != ".webp":
            raise VisualStageError("visual frame must be a non-empty WebP file")
        width = record.get("width")
        height = record.get("height")
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            raise VisualStageError("visual frame dimensions must be positive integers")
        start_label, end_label = source_window.split("-", 1)
        filename = (
            f"{index:03d}_{start_label.replace(':', '-')}_"
            f"{end_label.replace(':', '-')}.webp"
        )
        shutil.copy2(source, staged_assets / "frames" / filename)
        frames_by_chapter[chapter_id] = {
            "filename": filename,
            "width": width,
            "height": height,
            "alt": record.get("alt", chapter_id),
            "caption": record.get("caption", chapter_id),
        }
    return frames_by_chapter


def _publish_staged(staged_html, staged_assets, destination, assets_dir, stage_root):
    backup_html = stage_root / "previous.html"
    backup_assets = stage_root / "previous_assets"
    had_html = destination.exists()
    had_assets = assets_dir.exists()
    published_html = False
    published_assets = False
    try:
        if had_html:
            os.replace(destination, backup_html)
        if had_assets:
            os.replace(assets_dir, backup_assets)
        os.replace(staged_assets, assets_dir)
        published_assets = True
        os.replace(staged_html, destination)
        published_html = True
    except OSError as exc:
        if published_html:
            _remove_path(destination)
        if published_assets:
            _remove_path(assets_dir)
        try:
            if had_assets and backup_assets.exists():
                os.replace(backup_assets, assets_dir)
            if had_html and backup_html.exists():
                os.replace(backup_html, destination)
        except OSError as rollback_exc:
            raise VisualStageError(
                f"visual publication failed and rollback failed: {rollback_exc}"
            ) from exc
        raise VisualStageError(f"visual publication failed: {exc}") from exc


def _publish_compact_html(staged_html, destination, assets_dir, stage_root):
    backup_html = stage_root / "previous.html"
    backup_assets = stage_root / "previous_assets"
    had_html = destination.exists()
    had_assets = assets_dir.exists()
    published_html = False
    try:
        if had_html:
            os.replace(destination, backup_html)
        if had_assets:
            os.replace(assets_dir, backup_assets)
        os.replace(staged_html, destination)
        published_html = True
    except OSError as exc:
        if published_html:
            _remove_path(destination)
        try:
            if had_assets and backup_assets.exists():
                os.replace(backup_assets, assets_dir)
            if had_html and backup_html.exists():
                os.replace(backup_html, destination)
        except OSError as rollback_exc:
            raise VisualStageError(
                f"visual publication failed and rollback failed: {rollback_exc}"
            ) from exc
        raise VisualStageError(f"visual publication failed: {exc}") from exc


def render_visual_brief(*, calibrated_transcript_blocks, validated_timeline_report,
                        trusted_metadata, media_source, manifest, output_destination,
                        frame_assets=None):
    destination = Path(output_destination)
    assets_dir = destination.with_name(f"{destination.stem}_assets")
    try:
        stage_root = Path(tempfile.mkdtemp(prefix=f".{destination.stem}-", dir=destination.parent))
    except OSError as exc:
        raise VisualStageError(f"visual staging failed: {exc}") from exc
    try:
        blocks = validate_visual_brief(calibrated_transcript_blocks, manifest, media_source)
        staged_html = stage_root / destination.name
        compact = _is_compact_profile(blocks, trusted_metadata)
        if compact:
            if frame_assets:
                raise VisualStageError("compact editorial output rejects frame assets")
            if any(
                visual.get("type") == "quote"
                for chapter in manifest["chapters"]
                for visual in chapter.get("visuals", [])
            ):
                raise VisualStageError("compact editorial output rejects quote visuals")
            if any("frame_priority" in chapter for chapter in manifest["chapters"]):
                raise VisualStageError("compact editorial output rejects frame_priority")
            staged_html.write_text(
                _render_compact_page(blocks, trusted_metadata, media_source, manifest),
                encoding="utf-8",
            )
            _validate_staged_html(staged_html)
            _publish_compact_html(staged_html, destination, assets_dir, stage_root)
            return VisualBriefResult(destination, None)
        staged_assets = stage_root / assets_dir.name
        (staged_assets / "frames").mkdir(parents=True)
        frames_by_chapter = _stage_frame_assets(frame_assets, blocks, manifest, staged_assets)
        staged_html.write_text(
            _render_page(
                blocks,
                validated_timeline_report,
                trusted_metadata,
                media_source,
                manifest,
                frames_by_chapter,
                assets_dir.name,
            ),
            encoding="utf-8",
        )
        _validate_staged_html(staged_html, assets_dir.name)
        _publish_staged(staged_html, staged_assets, destination, assets_dir, stage_root)
        return VisualBriefResult(destination, assets_dir)
    except (ManifestValidationError, KeyError, TypeError, ValueError) as exc:
        raise VisualStageError(f"visual validation failed: {exc}") from exc
    except OSError as exc:
        raise VisualStageError(f"visual rendering failed: {exc}") from exc
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)
