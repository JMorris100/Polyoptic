# data/

`bundle.json` is written here by `python ingest/ingest.py`.

It is committed to the repository on purpose. The site is static — Cloudflare
Pages serves this file directly; there is no server and no database at runtime.
The GitHub Action in `.github/workflows/refresh.yml` regenerates and commits it
weekly, which also gives a full revision history of every published series.

That history matters more than it sounds. ONS and DfE revise figures. When
someone says a number has changed, `git log data/bundle.json` tells you exactly
when and by how much.

Until the ingest has run, `explore.html` falls back to the placeholder data
embedded in the page and labels every chart accordingly.
