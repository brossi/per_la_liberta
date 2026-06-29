# S2.0 — bbox + text↔box-alignment probe (GATE)

**Task** `S2.0` · **Issue** #18 · **Milestone** S2 · **Scope** `GATE` · **Branch** `spike/document-structure`
· **Spec** ENGINE_STRUCTURE_PLAN §3.0, D30, §1 portability note
· **Probe** `books/per_la_liberta/probes/s2_0_geometry_probe.py` (reproducible; numbers below are its output)

## Verdict

Geometry is **viable** as the primary re-bind / reading-order anchor for PLL — **conditional on a
column-aware matcher**. This is *not* a negative outcome: **S2.1-alt is not triggered.**

- **(a) S2.1 path → NORMAL (build S2.1).** Build the `GeometrySource` seam + PyMuPDF/Tesseract(ita)
  backend. The probe adds two hard requirements to the matcher spec (below). Both source PDFs are
  image scans, so the box layer is *generated* by a fresh OCR pass — `geometry_engine` is therefore
  a different engine from **every** witness; each box is a cross-engine match, exactly as §3.0 and
  S1.1's `Geom` match-provenance already require.
- **(b) S5 geometry mode → PRIMARY, per-atom confidence-gated (NOT demoted).** Measured ordered
  anchorability on body pages clears the pre-registered primary threshold once reading order is
  recovered from the box coordinates. Geometry stays the primary signal where the matcher is
  confident; where it is not (near-blank pages, index/back matter, column-detection failure),
  `geom.present=false` and re-bind falls back to the content + structural-path floor §3.0 defines.
  Absence is first-class; coordinates are never invented.

## Method

- **Box layer:** fresh OCR via PyMuPDF `get_textpage_ocr(language="ita", dpi=300, full=True)` on the
  LOC scan (`public-gdcmassbookdig-perlalibertdal00cres…pdf`, 278 pages). Native `get_text` is empty
  on both PDFs (see Finding 1), so this fresh pass *is* the only available box source.
- **Alignment target:** `copy3_raw.txt` (Gemini-vision OCR of the same LOC scan) — the **only**
  witness with a per-page char map (`copy3_pro_page_map.json`, keyed by scan page). It is also the
  *hardest* cross-engine target (a different OCR architecture from the Tesseract box pass), so it is
  a conservative measurement.
- **Three coverage metrics per page** (token = whitespace split, lowercased, edge-punctuation
  stripped):
  - **BoW** — multiset token overlap, order-independent → token-anchorability **ceiling**.
  - **naive ordered** — LCS coverage in raw OCR (full-width) reading order.
  - **col-aware ordered** — LCS coverage after recovering column reading order **from the box
    coordinates alone** (a crude central-gutter split; *not* the production matcher).
- **Sample:** 16 pages stratified across front matter / chapter starts / dense prose / footnotes /
  page furniture / embedded-letter / bad-OCR-index (footnote, letter, and dense pages located by
  pattern over the witness text + page map), plus a book-wide systematic sweep (every 7th page,
  ≥20 witness tokens, n=37). The ≥10-page floor is met by both.
- **Thresholds, set a priori (before the matching run):** ordered coverage median **≥0.85 →
  geometry usable as S5 primary**; 0.50–0.85 → tie-break only; <0.50 → no-geometry (S2.1-alt).

## Findings

**1. No native word-box layer exists — both PDFs are image scans.**
`get_text("words")` returns 0 boxes / 0 text chars on every book-content page of both the LOC scan
and the Harvard/Google scan; each page is a single image. (The Harvard PDF carries a text layer on
*one* page — Google's "This is a digital copy…" boilerplate cover — never on content.) A usable box
layer can only be **generated** by a fresh OCR pass, which is necessarily a different engine from the
witness producers (copy1/2 = IA-Tesseract, copy3 = Gemini). Tesseract 5.5.2 with `ita` traineddata
is present and produces boxes at ~2 s/page.

**2. The generated box layer is geometrically valid.** Mean box in-bounds = **0.999**; vertical
monotonicity (reading-order sanity of the box stream) ≈ 0.99 on text pages.

**3. Cross-engine token anchorability is high and uniform.** Book-wide sweep (n=37): BoW coverage
**median 0.939, mean 0.925, min 0.788, p10 0.865**; 34/37 pages ≥0.85. The fresh-OCR boxes carry
~93 % of the witness tokens — i.e. the boxes *can* be trusted as anchors at the token level.

**4. The body is uniformly two-column — this is the dominant layout fact.** 37/37 swept body pages
show a near-empty central gutter (two columns); the page image of scan 21 confirms it directly.
Consequence: **naive full-width OCR interleaves the two columns line-by-line** (`colA-line | colB-line
| colA-line …`) while the witness reads each column top-to-bottom, so naive ordered coverage
collapses to a median of **0.498** even though BoW is 0.94. Recovering column reading order **from the
box coordinates alone** lifts ordered coverage back to a median of **0.928** (per body page: dense
prose 0.82–0.95, footnotes 0.93–0.95, letters 0.90–0.95, two-column chapter bodies 0.90–0.94). The
reading-order signal is present in the geometry; the gap between naive (0.50) and col-aware (0.93) is
the entire value proposition.

> The pre-registered 0.85 bar is applied to the **correct** (column-aware) reading order, not the
> naive one. Naive ordering scores 0.498 only because full-width concatenation is the *wrong* order
> for a two-column book — a probe artifact, not a property of the geometry. The order-independent BoW
> (0.94) independently confirms the tokens/boxes are right and only order was at issue. The threshold
> was not moved; the measurement was corrected.

**5. Failure modes the S2.1 matcher must handle (each observed):**
- **Near-blank pages hallucinate boxes.** Scan 6 (a 7-token verso) yields 658 noise boxes from scan
  speckle / show-through. The matcher must gate on box confidence/density and emit `geom.present=false`
  on such pages — never anchor to noise.
- **Single-column pages must not be force-split.** The crude probe heuristic over-splits the
  single-column cover (scan 5: 0.85→0.68), prefazione opening (scan 7: 0.97→0.52), and index
  (scan 269: 0.41→0.25). A production matcher needs real single-vs-N-column detection (take the
  correct ordering per page), not a blanket midline split.
- **Index / dense small type degrades.** Scan 269 BoW 0.46 — genuine OCR degradation; low confidence
  → fall back, do not force a box anchor.

## Reproduce

```bash
cd engine
TESSDATA_PREFIX=/opt/homebrew/share/tessdata \
  uv run python books/per_la_liberta/probes/s2_0_geometry_probe.py out.json
# env overrides: PLL_LOC_PDF (default repo-root LOC scan), PLL_OCR_DPI (default 300)
```

## Implications for downstream

- **S2.1 (`GeometrySource` + backend) — proceed**, with two probe-mandated additions to the
  witness-text↔geometry matcher: (i) **column-aware reading-order recovery** (detect single vs
  N columns from the box x-distribution; order each column top→bottom) — without it geometry is worth
  ~0.50 and useless; (ii) **box-confidence/density gating** so near-blank pages and degraded regions
  yield `geom.present=false` rather than anchoring to hallucinated boxes. `match_confidence` should
  encode per-page column-detection success and token-match rate; unmatched boxes remain unusable for
  primary re-bind (already in the S2.1 row).
- **S2.1-alt — not triggered.** Keep it specified as the conditional fallback, but the evidence does
  not invoke it.
- **S2.2 (geometry property tests)** — the four assertions hold in principle here (boxes in bounds
  0.999; source-order↔geometric-order coherent after column recovery; absent/unmatched geom
  representable). They become binding tests against the S2.1 backend.
- **S5 (re-bind)** — geometry is the **primary** anchor on the two-column body (the bulk of the
  book), gated per-atom by `match_confidence`; content + structural-path remain the fallback where
  geometry is absent or low-confidence.

## Caveats / follow-ups

- The column-aware reorder in the probe is a **crude central-gutter heuristic**, deliberately not the
  production matcher; its over-splitting of single-column pages (Finding 5) is the concrete S2.1
  requirement, not a measurement defect.
- The structural witnesses appear to read the columns **correctly** (copy2/IA-Tesseract on Harvard
  and copy3/Gemini both show column-ordered text on scan 21: `mille barricate → Radetzky → Monte
  Tabor` monotonic, ~2.2 k-char A→B gap). **copy1 column ordering is «unverified»** here — copy1 has
  no page map, so it was not isolated per page; confirm during S2.1 when the matcher aligns boxes to
  copy1. If any structural witness *were* column-scrambled, geometry would be the signal that repairs
  its reading order — a point in geometry's favour, but to be checked, not assumed.
- Numbers are at dpi=300, default Tesseract (no Bodoni training). A higher dpi or a Didone-tuned model
  would only raise anchorability; the gate clears the threshold already.

## S2.1 design inputs (from review, 2026-06-29)

Design notes for the S2.1 matcher's segmentation front-end, captured here so they are not lost. These
are **inputs to S2.1, not built** (S2.1 is not greenlit). They make the gate's "conditional" concrete:
geometry is primary *where the front-end is confident*, human-adjudicated where it is not, and
`geom.present=false` only after **both** automatic detection and human review decline. The three stages
compose as: **density pre-check → column / reading-order detection → box↔witness match**, each emitting a
per-page confidence; any stage below threshold routes the page to a human-review worklist (below).

**1. Density pre-check (blank / content + don't-trust-boxes).** Standard blank-page detection:
binarize, count the foreground (ink) pixel ratio, threshold (the established technique behind scanner
blank-page skip). Validated on PLL — with one implementation trap:

- **Do not use per-page adaptive Otsu.** On a near-blank page there is no real ink/paper bimodal
  split, so Otsu maximizes between-class variance at a spurious *high* threshold and **inflates** the
  ink count: scan 6 (the 658-hallucinated-box verso) read 0.24 ink under per-page Otsu — *higher* than
  the densest text page. (The search's own caveat: Otsu "degrades when background intensity varies.")
- **Use a fixed, book-calibrated ink threshold** (here T≈130, drawn from the text-page Otsu cluster of
  120–135), or gate on histogram bimodality first. At fixed T=130 the separation is clean (~10×):
  near-blank/furniture scan 6 / 125 / 126 = 0.0009 / 0.0039 / 0.0000; content pages 0.038–0.104.
- A raw *average* pixel value (the first instinct) works but is the weakest form — the aged cream
  paper (~200 gray) drifts the mean; binarize-then-count is more stable. The fixed threshold is a
  per-book constant (portability-profile style), not universal.
- Payoff: a page measuring ~0 ink → `geom.present=false` + flag, never anchor to its hallucinated
  boxes. This directly retires Finding 5's near-blank hazard.

**2. Column / reading-order detection.** The canonical method is the **vertical projection profile /
Recursive X-Y Cut** (Nagy): sum ink (or box density) per x-column → two columns show a deep zero-valley
at the gutter; cut at the deepest valley; the recursive cut-tree yields **reading order for free** (what
the probe reconstructed by hand). Refinements from review:

- **The gutter valley is the discriminator, symmetry is a corroborator.** A single full-width column is
  *also* mirror-symmetric about the page centerline (a left-edge box mirrors onto the same line's right
  edge), so left↔right symmetry cannot by itself separate single-column from two-column — the empty
  central band can. Symmetry adds robustness by *rejecting* false positives (an offset single column, or
  column-plus-marginalia, is not mirror-balanced). Measure symmetry at the **column-block / projection
  level**, not per-word-box (words do not mirror word-to-word).
- **Cross-page prior.** Layout is locally constant, so a simple sequential model — "inherit the previous
  page's column class unless the projection profile strongly disagrees" (a 2-state prior) — is cheap and
  robust. The single-column exceptions the prior must allow are front/back matter and chapter-opening
  pages (the probe's scan 5 / 7 / 269 over-splits).

**3. Human-in-the-loop confidence gate (the keystone).** Pages the front-end cannot score confidently —
low density-class confidence, ambiguous column profile, or low box↔witness match — route to a
**human-review worklist** (the page image with the algorithm's tentative column split + boxes overlaid)
for refinement **before** the page passes the gate. Nothing silently guesses or auto-falls-back. This is
the per-page instance of S5.2's monotone-strictness ("more human review, not a lower bar") and the
project's *build-the-artifact-and-hand-it-over* pattern; it relaxes stages 1–2, which then only need to
be **calibrated to abstain**, not perfect. See the project memory `project-ingestion-human-in-loop`.
