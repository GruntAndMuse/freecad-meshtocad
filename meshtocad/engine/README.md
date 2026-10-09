# engine/ — DO NOT HAND-EDIT

These files are copies of the mesh-to-cad pipeline scripts
(`mesh-to-cad/scripts/`). The pipeline repo is the single source of truth.

- To update: fix the pipeline, then run `../../sync_engine.sh`.
- CI runs `sync_engine.sh --check` and fails on drift.

If you're reading this because you want to change pipeline behavior: change
it in the mesh-to-cad repo, not here.
