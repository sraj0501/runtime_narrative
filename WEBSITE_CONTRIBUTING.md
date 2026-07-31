# Site authoring guide (internal — not deployed content)

This file is for whoever writes the remaining `website/docs/*.html` pages. It is not part of the
published site. Read `website/docs/installation.html` first — it is the canonical, fully-worked
example. Every rule below is demonstrated there.

## File shell — copy verbatim

Every doc page is a full HTML document with this exact structure. Copy `website/docs/installation.html`
as your starting point for each new page, then:

1. Change `<title>` to `"<Page Title> — runtime-narrative"` and `<meta name="description">` to a
   one-sentence summary.
2. Change `<body data-page="...">` to the page's `id` from `website/assets/nav-data.js` (e.g.
   `data-page="story"` for `docs/story.html`). This drives sidebar highlighting and prev/next — it
   must match exactly or those features silently break for that page.
3. Replace the `<article class="prose">...</article>` content. **Do not touch anything else** —
   header, sidebar shell, footer, and the two `<script>` tags at the bottom must be byte-identical
   across every page (the header's `Docs` link `active` class is the only per-page tweak, and even
   that's optional — leave it as-is, it's cosmetic).
4. Do not hand-write the sidebar nav links, the "On this page" TOC, or the prev/next footer —
   `assets/app.js` builds all three automatically from `assets/nav-data.js` and the headings inside
   `.prose`. Leave `#sidebar-nav`, `#toc`, and `#page-nav` exactly as they appear in the template
   (empty containers).

All asset/internal links are root-relative (`/assets/...`, `/docs/...`) — never relative (`../assets`)
and never bare filenames. This matches the Netlify publish root (`website/`) and works identically
with a local static server run from inside `website/`.

## Content rules

- Wrap the whole page body in one `<article class="prose">`. Start with a single `<h1>` (the page
  title) and a `<p class="lede">` one-liner right under it — see installation.html.
- Use `<h2>` for top-level sections and `<h3>` for subsections. Headings get IDs and anchor links
  automatically — write plain heading text, no manual `id=` or `#` needed.
- Every code example needs a language on the `<code>` element: `class="language-python"` or
  `class="language-bash"` (or `language-text` for plain output/terminal transcripts with no
  highlighting). Wrap it in `<div class="code-block has-head"><div class="code-block-head"><span>python</span></div><pre><code class="language-python">...</code></pre></div>` —
  see installation.html for the exact nesting. The copy button and syntax coloring are added by
  `app.js` at runtime; you only write the semantic markup.
- HTML-escape code content (`&lt;`, `&gt;`, `&amp;`) since it's inside `<code>`, not raw text.
- Use `<table><thead><tr><th>...</tr></thead><tbody>...</tbody></table>` for parameter/field
  references — same shape as installation.html's extras table. `app.js` wraps tables for
  horizontal scroll automatically; don't add your own wrapper div.
- Use callouts for anything a reader must not miss — production safety notes, gotchas, "this
  defaults to X and should stay that way" warnings, cross-references. Four variants, pick by
  meaning (not decoration):
  - `callout-note` — supplementary info, "see also"
  - `callout-tip` — a recommended pattern or shortcut
  - `callout-warning` — something that will bite you if ignored (e.g. sync/async gotchas)
  - `callout-danger` — safety-critical: production behavior, silently-swallowed exceptions, security

  ```html
  <div class="callout callout-warning">
    <svg class="callout-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>
    <div>
      <p class="callout-title">Short, specific title</p>
      <p>One or two sentences. Can include <code>inline code</code> and a link.</p>
    </div>
  </div>
  ```
- Inline `<code>` for identifiers, params, filenames, env vars, values. Don't bold identifiers
  instead of coding them.
- End every page with a "Next step" `callout-note` pointing at the logical next page (mirror the
  one at the bottom of installation.html), unless the page is a natural leaf (e.g. Event Reference).
- Do **not** invent APIs, parameters, or defaults. Every claim must trace back to `README.md` or
  `WIKI.md` in the repo root (the assignment below tells you which section). If something is
  ambiguous, keep the wording close to the source rather than guessing.
- Voice: same as the existing docs — direct, technical, no marketing fluff, short sentences,
  concrete code over abstract description. Second person ("you") is fine for guidance; avoid "we"/"I".
- Do not reference internal AI-assistant tooling, CLAUDE.md, or this guide's own existence anywhere
  in page content.

## Components available (use only these classes)

- `.callout.callout-{note,tip,warning,danger}` — see above.
- `.badge` — small pill for things like `<span class="badge">requires otel extra</span>`.
- `.grid-cards.cols-2` / `.cols-3` with `.card` children — only if a page has a natural set of
  parallel sub-topics worth scanning (e.g. "four assertion methods", "three renderer categories").
  Don't force it onto every page; prose + tables are the default.
- `<hr>` between major unrelated subsections is fine but not required (h2 already gets a top rule).

## Page → source mapping

Write from the **actual current content** in these files (read them directly, don't rely on
anything pasted secondhand) — line numbers are approximate anchors, read the surrounding section:

| Page | Primary source |
|---|---|
| `quickstart.html` | `WIKI.md` §4 "Quick Start" + README "Quick start" |
| `concepts.html` | `WIKI.md` §3 "Core Concepts" |
| `story.html` | `WIKI.md` §5 "story()" |
| `stage.html` | `WIKI.md` §6 "stage()" |
| `decorators.html` | `WIKI.md` §7 "Decorators" |
| `auto-instrumentation.html` | `WIKI.md` §8 "Auto-Instrumentation" |
| `diagnostics.html` | `WIKI.md` §9 "Failure Diagnostics" (9.1–9.7) |
| `custom-analyzers.html` | `WIKI.md` §18 "Custom Failure Analyzers" |
| `background-analysis.html` | `WIKI.md` §16 "Background Analysis" |
| `renderers.html` | `WIKI.md` §10 "Renderers" (10.1–10.10) |
| `custom-renderers.html` | `WIKI.md` §17 "Custom Renderers" |
| `integrations.html` | `WIKI.md` §11 "Framework Integrations" (11.1–11.4) |
| `task-groups.html` | `WIKI.md` §12 "Async Task Groups" |
| `substories-logging.html` | `WIKI.md` §21 "Sub-stories and Log Capture" + README "Sub-stories" / "Capture existing logging calls" sections |
| `persistence-cli.html` | `WIKI.md` §13 "SQLite Persistence and CLI" |
| `testing.html` | `WIKI.md` §14 "Testing with StoryRecorder" |
| `dry-run.html` | `WIKI.md` §15 "dry_run Mode" |
| `env-vars.html` | `WIKI.md` §19 "Environment Variables" + README "Environment variables" table |
| `events.html` | `WIKI.md` §20 "Event Reference" |
| `examples.html` | README "Examples" section (the full table of `examples/*.py` scripts, grouped) |

## Sidebar order / prev-next

`assets/nav-data.js` already lists every page in the correct order (grouped: Getting Started, Core
API, Diagnostics & Analysis, Renderers, Integrations & Concurrency, Operations, Reference). Prev/next
footer links are derived from that flat order automatically — you don't configure anything per page.
If you're told to add a page not already listed there, add an entry to the appropriate group in
`nav-data.js` (and nowhere else).

## Checklist before considering a page done

- [ ] `<title>`, meta description, and `data-page` are correct and match `nav-data.js`
- [ ] Header/sidebar/footer/scripts are untouched copies from installation.html
- [ ] All internal links are root-relative (`/docs/...`, `/assets/...`)
- [ ] Every code block has a language class and is wrapped in `.code-block`
- [ ] Every table is inside `<table><thead>...<tbody>` (no manual `.table-wrap`)
- [ ] Content matches the current README.md/WIKI.md — no invented parameters or defaults
- [ ] At least one internal cross-link to a related page, styled as a normal prose link or a
      closing "Next step" callout
