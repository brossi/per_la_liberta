# Archive

This directory keeps historical project artifacts out of the active pipeline
surface without deleting provenance. Files here are not live entrypoints unless
a future change explicitly promotes them back into the documented workflow.

## Contents

- `doc_audits/2026-06/` — documentation audit artifacts from the June 2026
  documentation review pass.
- `one_off_scripts/` — retired repair, synthesis, and extraction scripts that
  are not imported by live code and are not part of any documented review track.
- `one_off_data/` — outputs produced by retired one-off scripts, kept with the
  related provenance.
- `design/` — historical typography/style specimens and design references.

Active build and review scripts intentionally remain at the repository root.
Large source PDFs also remain at the root because current OCR/review code
expects those local, gitignored filenames there.
