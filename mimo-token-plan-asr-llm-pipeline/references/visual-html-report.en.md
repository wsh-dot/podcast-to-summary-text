# Offline HTML Visual Brief Contract

## Contents

1. Fact and artifact order
2. Three structured routes
3. Manifest and evidence rules
4. Representative video frames
5. Reader and offline contract
6. Failure matrix
7. Manual file layout
8. Visual and accessibility QA

## 1. Fact and artifact order

Markdown is authoritative. Start the visual stage only after the calibrated transcript and timeline report pass window validation and the Markdown file is published.

```text
calibrated transcript + validated Markdown
  -> bounded VisualBatch JSON
  -> validated batch records
  -> VisualBriefManifest JSON
  -> manifest/evidence/full-coverage validation
  -> optional real frames
  -> fixed offline renderer
  -> atomic HTML + sibling assets publication
```

A visual failure must never roll back or overwrite the transcript or Markdown.

## 2. Three structured routes

- **api-llm**: call the selected provider in `timeline-batch-size` groups. Repair only an invalid batch, once. Global synthesis must read the complete calibrated transcript in order; validated records and the Markdown overview constrain evidence but never replace full-transcript reading.
- **ide-agent**: after manual sections publish validated Markdown, the CLI automatically exports visual prompts. The Agent follows them, saves the same JSON batch and manifest files with no explanatory prose, then continues through prepare/render.
- **manual**: the user places external model JSON in the workflow directory. The script validates and renders without an LLM call.

All routes share `visual_brief.py` and `visual_reader.py`. Never create route-specific schemas or HTML templates.

## 3. Manifest and evidence rules

Required document fields are `version`, `overview`, `core_insights`, and `chapters`. `overview`, each core insight, chapter `title`/`summary`, visual `title`, and process/concept item use a strict `SourcedText` object with exactly non-empty `text` and non-empty `source_windows`. Every chapter requires `id`, `title`, `summary`, `source_windows`, `evidence`, and `visuals`; video chapters may add integer `frame_priority` from 0 to 100. Each comparison/relationship item also requires `source_windows`; metrics and quotes keep their exact `source_window`.

- Flattened chapter windows must exactly equal transcript windows: no missing, duplicate, overlapping, or reordered windows.
- A chapter may group only adjacent transcript windows.
- Evidence windows must belong to the chapter.
- Quotes must be exact substrings of their declared window.
- Metric `source_sentence` values must be exact substrings of their declared window.
- Allowed visuals are `process`, `comparison`, `relationship`, `metrics`, `concept`, and `quote`.
- Use `visuals: []` when evidence supports no visual. The fixed renderer provides an editorial insight presentation.
- Every visible claim, diagram item, edge, and label must reference real windows inside its chapter; overview/core insights may reference real windows across the transcript.
- Short content is bounded to 6 core insights and 5 visuals; long content to 10 insights and 8 visuals. These are ceilings, not quotas.
- For sources over 60 minutes whose calibrated transcript has at least as many CJK characters as ASCII Latin letters, use the compact editorial profile: exactly 4 insights, 5 adjacent-window chapters, 1,800–2,500 visible CJK characters, at most 2 visuals per chapter, and at most 8 overall. Deterministically map `process` to flow/timeline, `comparison` to split comparison, cyclic `relationship` to flywheel, other relationships to network, `metrics` to metric strips, and `concept` to layered diagrams.

The schema is a strict allowlist. Reject model HTML, JavaScript, CSS, SVG, absolute paths, and traversal before publication.

## 4. Representative video frames

The compact editorial profile never calls the frame provider, rejects `frame_priority` and non-empty `frame_assets`, and creates no sibling assets directory. Publishing the new single-file HTML atomically removes old frame assets and restores both HTML and assets on failure.

- Up to one hour: at most about 8 high-value chapter frames.
- Over one hour: about 8–12, not a mandatory quota.
- Rank by `frame_priority`; at most one frame per chapter.
- Try the midpoint of a real chapter window, then bounded 35%, 65%, and 20% fallbacks in the same window.
- Encode WebP capped at 1280 display pixels with stable names such as `001_00-18_00-27.webp`.
- Validate decoding and dimensions with ffprobe; reject empty, black, or excessively dark grayscale samples.
- Any subset of frame failures degrades to infographic/text without cancelling HTML.

Bilibili visual media must use pinned BBDown 1.6.3 with `--video-only --video-ascending`, never yt-dlp fallback. Other URLs may use a temporary yt-dlp source capped at 720p.

## 5. Reader and offline contract

The regular reader contains overview, core insights, chapter navigation, evidence, six infographic types, and optional representative frames. The compact editorial reader uses an approximately 1080px single-column layout, renderer-owned CSS/SVG graphics, and source-window labels; it contains no search, sticky sidebar, video frames, serialized manifest, or full transcript.

- The visual intent is a warm, confident, modern editorial poster. Use semantic tokens: amber `--color-primary: #CC8800`, burnt orange `--color-secondary: #C55221`, surface `#FFFFFF`, and text `#111827`; body copy must not depend on ad hoc raw colors.
- The compact profile uses a cream canvas and distinct SECTION groups. Each chapter keeps its title and source tags above a deterministic 3–5 card split of the complete summary, using semantic sentence boundaries and a two-column white-card grid. Concatenating card bodies in order must reproduce the original summary exactly. Infographics span the full width below the cards; below 680px the content cards become one column. The regular reader uses a burnt-orange hero, cream grid canvas, and white navigation/chapter cards. Both profiles share one typography, color, spacing, and focus language.
- Display typography prefers Chakra Petch and mono typography prefers JetBrains Mono. Never fetch fonts over the network; use the system fallbacks declared in the embedded CSS.
- Interactive links, search inputs, and disclosures have a minimum 44px touch target. Links provide default, hover, focus-visible, and active states where relevant; search provides default, hover, and focus-visible states.
- Escape every untrusted string.
- Generate image paths inside the sibling assets directory only.
- Images need width/height, stable aspect ratio, lazy loading, async decoding, alt text, and captions.
- Embed CSS, enhancement JavaScript, icons, and page data.
- No CDN, remote font, analytics, tracking, remote image, or runtime package.
- JavaScript may enhance local search, current chapter, mobile chapter navigation, and printing only.
- Without JavaScript, text, anchors, visuals, and images remain available.
- Use a single column with mobile chapter disclosure at 375/768 and the three-column reader at 1024/1440.
- Include skip navigation, visible focus, sequential headings, reduced motion, and print expansion.
- Prohibit low-contrast small amber text, missing focus outlines, decorative gradient overload, indiscriminate pill shapes, inconsistent card spacing, and hover-only information.

## 6. Failure matrix

| Failure | Required behavior |
|---|---|
| Invalid batch JSON/evidence | Repair only that batch once, then stop HTML if still invalid. |
| Invalid synthesis manifest | Repair once with the original synthesis input and validation error, then stop HTML if still invalid. |
| IDE prompt export | Warn once and retain the published Markdown. |
| Invalid synthesis manifest | Publish no HTML/assets; retain Markdown. |
| Bilibili visual download | Warn once, render without frames, never use yt-dlp. |
| Other visual download | Warn once and render without frames. |
| Empty/dark/corrupt frame | Use bounded same-window fallback, then skip it. |
| Render/static validation | Remove staging; retain the previous reader and core artifacts. |
| Partial publication | Remove new parts and restore the previous HTML/assets. |

Errors must not expose credentials, cookies, or transcript content.

## 7. Manual file layout

```text
<base>_visual_prompts/
  workflow.json
  batch_prompts/001.md
  batch_results/001.json
  synthesis_prompt.md
  manifest.json
```

The prepare stage requires the exact expected batch filename set. Missing, extra, duplicate, or malformed files never enter synthesis. The render stage reads only `manifest.json`, validates through the shared contract, and publishes the same reader as API mode.

## 8. Visual and accessibility QA

- [ ] No horizontal scrolling at 375, 390, 768, 1024, or 1440px; long titles wrap without colliding with decorative copy.
- [ ] Each compact chapter summary becomes 3–5 two-column content cards and collapses to one column below 680px; concatenating all card bodies exactly reproduces the original summary, and infographics span the width below.
- [ ] All six infographic types, text fallback, video frames, navigation, search, and source links use the same semantic tokens.
- [ ] Tab reaches the skip link, every link, search, and disclosure; focus outlines are at least 3px and never clipped.
- [ ] Touch targets are at least 44px; `prefers-reduced-motion` removes smooth scrolling and hover transitions.
- [ ] Print removes background texture, sticky navigation, and scripts while avoiding unnecessary chapter splits.
- [ ] The HTML preserves the single-file/sibling-assets contract and contains no remote fonts, CDN, remote images, or tracking.
