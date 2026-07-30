import html
import json
import os
import re
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


def _split_summary_units(text, punctuation):
    units = [
        part
        for part in re.findall(rf"[^{re.escape(punctuation)}]+[{re.escape(punctuation)}]*", text)
        if part
    ]
    return units if "".join(units) == text else [text]


def _summary_card_groups(summary, minimum=3, maximum=5):
    text = summary
    units = _split_summary_units(text, "。！？!?")
    if len(units) < minimum:
        units = _split_summary_units(text, "。！？!?；;：:")
    if len(units) < minimum:
        units = _split_summary_units(text, "。！？!?；;：:，,")
    if len(units) < minimum and len(text) >= minimum:
        cut_points = [round(len(text) * index / minimum) for index in range(minimum + 1)]
        units = [text[cut_points[index]:cut_points[index + 1]] for index in range(minimum)]

    target = min(maximum, len(units))
    if len(units) <= target:
        groups = units
    else:
        groups = []
        start = 0
        for slot in range(target):
            remaining_units = len(units) - start
            remaining_slots = target - slot
            take = (remaining_units + remaining_slots - 1) // remaining_slots
            groups.append("".join(units[start:start + take]))
            start += take
    if "".join(groups) != text:
        raise VisualStageError("summary card split must preserve the complete chapter summary")
    return groups


def _summary_card_title(text):
    compact = re.sub(r"\s+", " ", text).strip(" “”—\"'")
    candidate = re.split(r"[，,。；;：:！？!?]", compact, maxsplit=1)[0].strip()
    if len(candidate) < 4:
        candidate = compact
    return candidate if len(candidate) <= 18 else f"{candidate[:18]}…"


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
        summary_cards = "".join(
            f'<article class="summary-card"{_source_attrs(chapter["summary"])}>'
            f'<p class="summary-card-index">{card_index:02d}</p>'
            f'<h3>{_text(_summary_card_title(card_text))}</h3>'
            f'<p>{_text(card_text)}</p></article>'
            for card_index, card_text in enumerate(
                _summary_card_groups(chapter["summary"]["text"]),
                start=1,
            )
        )
        chapter_html.append(
            f'<section id="{_text(chapter["id"])}" class="chapter-section">'
            f'<div class="chapter-copy"><p class="chapter-index">SECTION {index:02d}</p>'
            f'<h2{_source_attrs(chapter["title"])}>{_claim_text(chapter["title"])}</h2>'
            f'<ul class="source-tags">{evidence}</ul></div>'
            f'<div class="summary-card-grid">{summary_cards}</div>'
            f'<div class="chapter-graphics">{visuals}</div></section>'
        )
    source_link = ""
    if media_source.get("url"):
        source_link = f'<a class="source-link" href="{_text(media_source["url"])}">查看原始来源</a>'
    return f'''<!doctype html>
<html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>
:root{{--color-primary:#CC8800;--color-primary-ink:#7A5100;--color-secondary:#C55221;--color-secondary-strong:#963B18;--color-success:#16A34A;--color-warning:#D97706;--color-danger:#DC2626;--color-surface:#FFFFFF;--color-surface-cream:#FFF8E8;--color-surface-apricot:#FBE9D8;--color-surface-sand:#F2E6D2;--color-surface-rose:#F7E3DC;--color-canvas:#F4E8D3;--color-cream:#FFF8E8;--color-text:#111827;--color-muted:#594E43;--color-line:#D4C2A8;--color-focus:#1D4ED8;--shadow-card:0 14px 34px rgba(62,38,14,.10);--shadow-lift:0 18px 44px rgba(62,38,14,.16);--radius-card:2px;--font-display:"Chakra Petch","Microsoft YaHei",system-ui,sans-serif;--font-body:"Microsoft YaHei",system-ui,sans-serif;--font-mono:"JetBrains Mono",Consolas,monospace}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--color-canvas);color:var(--color-text);font:17px/1.72 var(--font-body);letter-spacing:.01em;background-image:radial-gradient(circle at 8% 8%,rgba(204,136,0,.13),transparent 24rem)}}
a{{color:var(--color-primary-ink);font-weight:700;text-underline-offset:4px;text-decoration-thickness:2px}}a:hover{{color:var(--color-secondary-strong)}}a:focus-visible{{outline:3px solid var(--color-focus);outline-offset:4px;border-radius:2px}}.skip{{position:absolute;left:-9999px}}.skip:focus{{left:16px;top:16px;background:var(--color-surface);padding:12px 16px;z-index:10;box-shadow:var(--shadow-card)}}
.compact-editorial{{max-width:1080px;margin:auto;padding:0 32px}}.page-header{{position:relative;padding:88px 0 56px;border-bottom:1px solid var(--color-line)}}.page-header:before{{content:"";position:absolute;inset:0 auto auto 0;width:96px;height:8px;background:var(--color-primary)}}.page-header:after{{content:"VISUAL / BRIEF";position:absolute;right:0;top:32px;color:var(--color-secondary);font:700 12px/1 var(--font-mono);letter-spacing:.14em}}.kicker,.chapter-index{{font:700 12px/1.3 var(--font-mono);color:var(--color-secondary-strong);letter-spacing:.12em;text-transform:uppercase}}
h1{{max-width:900px;font:800 clamp(3rem,8vw,5.8rem)/.94 var(--font-display);letter-spacing:-.055em;text-wrap:balance;margin:18px 0 28px}}.overview{{max-width:46rem;font-size:1.16rem;line-height:1.8;margin:0 0 24px;color:var(--color-muted)}}.source-link{{display:inline-flex;align-items:center;min-height:44px;padding:10px 16px;background:var(--color-secondary);color:#fff;text-decoration:none;box-shadow:5px 5px 0 var(--color-primary)}}.source-link:hover{{background:var(--color-secondary-strong);color:#fff;transform:translate(-1px,-1px);box-shadow:7px 7px 0 var(--color-primary)}}.source-link:active{{transform:translate(2px,2px);box-shadow:3px 3px 0 var(--color-primary)}}
.insights{{padding:48px 0 64px}}.section-label{{font:700 14px/1.3 var(--font-mono);letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid var(--color-line);padding-bottom:12px}}.insight-grid{{list-style:none;padding:0;margin:24px 0 0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}
.insight-grid li{{position:relative;background:var(--color-surface);padding:24px;display:grid;grid-template-columns:40px 1fr;gap:12px;border-top:6px solid var(--color-primary);box-shadow:var(--shadow-card);transition:transform .18s ease,box-shadow .18s ease}}.insight-grid li:hover{{transform:translateY(-3px);box-shadow:var(--shadow-lift)}}.insight-grid span{{color:var(--color-secondary-strong);font:700 13px/1.4 var(--font-mono)}}.insight-grid p{{margin:0;font-weight:600}}
.chapter-stack{{padding:0 0 72px}}.chapter-section{{min-width:0;padding:56px 0 64px;border-top:1px solid var(--color-line);break-inside:avoid}}.chapter-copy{{max-width:780px;margin-bottom:28px}}.chapter-copy h2{{font:800 clamp(2rem,4vw,3rem)/1.06 var(--font-display);letter-spacing:-.035em;text-wrap:balance;overflow-wrap:anywhere;margin:12px 0 20px}}
.source-tags{{list-style:none;padding:0;margin:24px 0 0;display:flex;flex-wrap:wrap;gap:8px}}.source-tags li{{font:600 12px/1.4 var(--font-mono);background:var(--color-cream);border:1px solid var(--color-line);padding:7px 10px}}.source-tags span{{color:var(--color-secondary-strong);font-weight:800;margin-right:7px}}
.summary-card-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:start;gap:16px}}.summary-card{{--card-surface:var(--color-surface);--card-accent:var(--color-primary);min-width:0;background:var(--card-surface);padding:24px;border-top:6px solid var(--card-accent);box-shadow:var(--shadow-card);break-inside:avoid}}.summary-card:nth-child(4n+1){{--card-surface:var(--color-surface);--card-accent:var(--color-primary)}}.summary-card:nth-child(4n+2){{--card-surface:var(--color-surface-apricot);--card-accent:var(--color-secondary)}}.summary-card:nth-child(4n+3){{--card-surface:var(--color-surface-cream);--card-accent:var(--color-primary)}}.summary-card:nth-child(4n){{--card-surface:var(--color-surface-rose);--card-accent:var(--color-secondary)}}.chapter-section:nth-child(even) .summary-card:nth-child(4n+1){{--card-surface:var(--color-surface-sand)}}.chapter-section:nth-child(even) .summary-card:nth-child(4n+3){{--card-surface:var(--color-surface)}}.summary-card-index{{margin:0 0 10px;color:var(--color-secondary-strong);font:700 12px/1.3 var(--font-mono);letter-spacing:.08em}}.summary-card h3{{margin:0 0 12px;font:800 1.2rem/1.25 var(--font-display);overflow-wrap:anywhere}}.summary-card>p:last-child{{margin:0;color:var(--color-muted)}}
.chapter-graphics{{display:grid;gap:16px;margin-top:20px}}.editorial-visual{{margin:0;background:var(--color-surface);color:var(--color-text);padding:24px;border:1px solid var(--color-line);border-top:6px solid var(--color-secondary);box-shadow:var(--shadow-card)}}figcaption{{font:700 1.08rem/1.4 var(--font-display);margin-bottom:18px}}.diagram-accent{{display:block;width:120px;height:12px;margin-bottom:20px;fill:none;stroke:var(--color-secondary);stroke-width:2}}
.flow-diagram{{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px}}.diagram-node{{padding:16px;background:var(--color-cream);min-height:96px;display:grid;align-content:space-between;border-bottom:3px solid var(--color-primary)}}.diagram-node span,.layered-diagram span{{font:700 12px/1.3 var(--font-mono);color:var(--color-secondary-strong)}}.diagram-node strong{{font-size:.95rem}}
.timeline-diagram{{display:grid;gap:0;border-left:4px solid var(--color-primary);margin-left:12px}}.timeline-diagram .diagram-node{{position:relative;background:transparent;min-height:0;padding:11px 14px 11px 24px;border:0}}.timeline-diagram .diagram-node:before{{content:"";position:absolute;width:13px;height:13px;border-radius:50%;background:var(--color-secondary);border:3px solid var(--color-surface);left:-9px;top:18px}}
.comparison-diagram{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}.comparison-diagram>div{{padding:20px;background:var(--color-cream);display:grid;gap:8px;border-bottom:4px solid var(--color-secondary)}}.comparison-diagram span{{font:700 12px/1.3 var(--font-mono);color:var(--color-primary-ink)}}
.flywheel-diagram,.network-diagram{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}.flywheel-diagram>div,.network-diagram>div{{padding:16px;border:2px solid var(--color-primary);background:var(--color-cream);display:grid;gap:6px;text-align:center}}.flywheel-diagram span,.network-diagram span{{color:var(--color-secondary-strong);font:700 12px/1.4 var(--font-mono)}}
.metrics-diagram{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}}.metrics-diagram>div{{background:var(--color-text);color:#fff;padding:20px;display:grid;border-bottom:6px solid var(--color-primary)}}.metrics-diagram strong{{font:800 2.2rem/1 var(--font-display);color:#FFD58A}}.metrics-diagram span{{font-size:.8rem;margin-top:8px}}
.layered-diagram{{display:flex;flex-direction:column-reverse;gap:7px}}.layered-diagram>div{{padding:14px 16px;background:var(--color-cream);border-bottom:3px solid var(--color-primary);display:flex;gap:12px;justify-content:center}}.layered-diagram>div:nth-child(2){{margin-inline:7%}}.layered-diagram>div:nth-child(3){{margin-inline:14%}}
.editorial-text-treatment{{padding:22px;border-left:6px solid var(--color-primary);background:var(--color-cream);color:var(--color-text)}}footer{{padding:40px 0 64px;border-top:1px solid var(--color-line);font:600 12px/1.5 var(--font-mono);color:var(--color-muted);letter-spacing:.04em}}
@media(max-width:680px){{body{{font-size:16px}}.compact-editorial{{padding:0 18px}}.page-header{{padding:64px 0 42px}}.page-header:after{{top:24px}}h1{{font-size:clamp(2.7rem,15vw,4.2rem);overflow-wrap:anywhere}}.insight-grid,.summary-card-grid{{grid-template-columns:1fr}}.chapter-section{{padding:44px 0 52px}}.summary-card{{padding:20px}}.comparison-diagram{{grid-template-columns:1fr}}.editorial-visual{{padding:18px}}}}
@media(hover:none){{.insight-grid li:hover{{transform:none;box-shadow:var(--shadow-card)}}}}@media(prefers-reduced-motion:reduce){{html{{scroll-behavior:auto}}*,*:before,*:after{{scroll-behavior:auto!important;transition:none!important}}}}@media print{{body{{background:#fff;background-image:none}}.compact-editorial{{max-width:none}}.summary-card-grid{{grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}.summary-card,.editorial-visual{{box-shadow:none}}}}
</style></head><body><a class="skip" href="#content">跳至正文</a><main id="content" class="compact-editorial">
<header class="page-header"><p class="kicker">TRANSCRIPT INTERPRETATION</p><h1>{title}</h1><p class="overview"{_source_attrs(manifest["overview"])}>{_claim_text(manifest["overview"])}</p>{source_link}</header>
<section class="insights"><p class="section-label">核心结论</p><ol class="insight-grid">{insights}</ol></section><div class="chapter-stack">{''.join(chapter_html)}</div>
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
:root{{--color-primary:#CC8800;--color-primary-ink:#7A5100;--color-secondary:#C55221;--color-secondary-strong:#963B18;--color-success:#16A34A;--color-warning:#D97706;--color-danger:#DC2626;--color-surface:#FFFFFF;--color-canvas:#F4E8D3;--color-cream:#FFF8E8;--color-text:#111827;--color-muted:#594E43;--color-line:#D4C2A8;--color-focus:#1D4ED8;--shadow-card:0 12px 30px rgba(62,38,14,.10);--font-display:"Chakra Petch",system-ui,sans-serif;--font-body:system-ui,sans-serif;--font-mono:"JetBrains Mono",Consolas,monospace}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;color:var(--color-text);background:var(--color-canvas);font:16px/1.68 var(--font-body);background-image:linear-gradient(90deg,rgba(204,136,0,.06) 1px,transparent 1px);background-size:32px 32px}}
a{{color:var(--color-primary-ink);font-weight:700;text-underline-offset:4px}}a:hover{{color:var(--color-secondary-strong)}}a:focus-visible,summary:focus-visible,button:focus-visible,input:focus-visible{{outline:3px solid var(--color-focus);outline-offset:3px}}
.skip{{position:absolute;left:-9999px}}.skip:focus{{left:16px;top:16px;background:var(--color-surface);padding:12px 16px;z-index:10;box-shadow:var(--shadow-card)}}
header{{position:relative;color:#fff;background:var(--color-secondary);padding:72px max(24px,calc((100% - 1240px)/2));border-bottom:10px solid var(--color-primary)}}header:after{{content:"OFFLINE / VISUAL BRIEF";position:absolute;right:max(24px,calc((100% - 1240px)/2));top:28px;font:700 12px/1 var(--font-mono);letter-spacing:.14em;color:#FFE1B0}}header>p:first-child{{font:700 12px/1.4 var(--font-mono);letter-spacing:.12em;text-transform:uppercase;color:#FFE1B0}}h1{{max-width:900px;font:800 clamp(2.8rem,7vw,5.4rem)/.96 var(--font-display);letter-spacing:-.05em;text-wrap:balance;margin:16px 0 24px}}.overview{{max-width:68ch;font-size:1.12rem;color:#FFF8EE}}header .source-link{{display:inline-flex;align-items:center;min-height:44px;padding:10px 16px;background:var(--color-cream);color:var(--color-secondary-strong);text-decoration:none;box-shadow:5px 5px 0 #733019}}header .source-link:hover{{background:#fff;color:var(--color-secondary-strong);transform:translate(-1px,-1px)}}
.layout{{display:grid;grid-template-columns:minmax(200px,240px) minmax(0,760px) minmax(190px,220px);gap:28px;max-width:1240px;margin:auto;padding:40px 24px}}
nav,aside{{position:sticky;top:20px;align-self:start;background:var(--color-surface);padding:20px;border-top:6px solid var(--color-primary);box-shadow:var(--shadow-card)}}nav h2,aside h2{{font:700 13px/1.3 var(--font-mono);letter-spacing:.06em;text-transform:uppercase;margin:0 0 16px}}nav ol{{padding-left:22px;margin-bottom:0}}nav li+li{{margin-top:10px}}main{{min-width:0}}main>section:first-child{{padding:24px 28px;margin-bottom:24px;background:var(--color-text);color:#fff;border-bottom:6px solid var(--color-primary);box-shadow:var(--shadow-card)}}main>section:first-child h2{{margin-top:0;font-family:var(--font-display)}}.chapter{{padding:32px;margin:0 0 24px;background:var(--color-surface);border-top:6px solid var(--color-primary);box-shadow:var(--shadow-card)}}.chapter:nth-of-type(2n+3){{border-top-color:var(--color-secondary)}}.chapter h2{{font:800 clamp(1.8rem,4vw,2.5rem)/1.05 var(--font-display);letter-spacing:-.03em;text-wrap:balance;margin:0 0 16px}}
.mobile-chapter-nav{{display:none}}
.evidence{{padding:16px 16px 16px 34px;background:var(--color-cream);border-left:4px solid var(--color-primary)}}.evidence-window{{color:var(--color-secondary-strong);font:700 13px/1.4 var(--font-mono)}}.visual{{margin:24px 0 0;padding:20px;background:var(--color-cream);border:1px solid var(--color-line);border-top:5px solid var(--color-primary)}}figcaption{{font:700 1.08rem/1.4 var(--font-display);margin-bottom:14px}}blockquote{{margin:0;padding:16px 20px;background:var(--color-surface);border-left:5px solid var(--color-secondary);font-size:1.1rem}}
.editorial-insight{{margin:24px 0;padding:20px;border-left:6px solid var(--color-secondary);background:var(--color-cream)}}
.source-frame{{margin:24px 0}}.source-frame img{{display:block;width:100%;height:auto;aspect-ratio:var(--frame-ratio,16/9);object-fit:contain;background:var(--color-text);border:6px solid var(--color-text)}}.source-frame figcaption{{padding:10px 0 0}}
.comparison-visual>div,.relationship-visual>div,.metrics-visual>div{{display:flex;gap:16px;justify-content:space-between;border-top:1px solid var(--color-line);padding:12px 0}}.metrics-visual>div strong{{font:800 1.8rem/1 var(--font-display);color:var(--color-secondary-strong)}}
details{{margin-top:20px;background:var(--color-surface);border-top:6px solid var(--color-primary);box-shadow:var(--shadow-card)}}summary{{cursor:pointer;font-weight:700;min-height:44px;padding:12px 16px}}details[open] summary{{border-bottom:1px solid var(--color-line)}}
.search{{display:grid;gap:8px;margin:16px 0}}.search span{{font:700 12px/1.4 var(--font-mono)}}input[type=search]{{width:100%;min-height:44px;padding:10px 12px;color:var(--color-text);background:var(--color-cream);border:2px solid var(--color-line);border-radius:2px}}input[type=search]:hover{{border-color:var(--color-primary)}}input[type=search]:focus{{background:#fff;border-color:var(--color-focus)}}svg.icon{{width:1em;height:1em;vertical-align:-.1em;margin-right:6px}}
@media(prefers-reduced-motion:reduce){{html{{scroll-behavior:auto}}*,*:before,*:after{{scroll-behavior:auto!important;transition:none!important}}}}@media(max-width:900px){{header{{padding-block:60px 48px}}.layout{{grid-template-columns:minmax(0,1fr);padding:24px 18px}}nav,aside{{position:static}}.desktop-navigation{{display:none}}.mobile-chapter-nav{{display:block;margin:0}}.chapter{{padding:24px}}}}@media(max-width:560px){{header:after{{display:none}}h1{{overflow-wrap:anywhere}}.chapter{{padding:20px}}.comparison-visual>div,.relationship-visual>div,.metrics-visual>div{{align-items:flex-start;flex-direction:column;gap:4px}}}}@media print{{body{{background:#fff;background-image:none}}header{{color:var(--color-text);background:#fff;border-bottom:4px solid var(--color-primary)}}header .overview{{color:var(--color-text)}}nav,aside,.mobile-chapter-nav,script{{display:none}}.layout{{display:block;max-width:none;padding:0}}main>section:first-child{{color:var(--color-text);background:#fff;box-shadow:none}}.chapter{{box-shadow:none;break-inside:avoid}}}}
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
