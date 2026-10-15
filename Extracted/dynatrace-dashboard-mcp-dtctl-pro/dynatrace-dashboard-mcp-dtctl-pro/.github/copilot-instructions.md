# Dynatrace dashboard editing via dtctl MCP

- Use the existing Dynatrace MCP for discovery and read-only Grail queries.
- Use `dynatrace-dashboard-editor-dtctl` for editing **Latest Dynatrace** dashboards only.
- Use exact dashboard IDs, not ambiguous names. Read with `get_dashboard` and `list_dashboard_tiles` first.
- To edit one visualization, prefer `plan_update_tile_visualization` (mode=merge); for a chart-type change use mode=replace with settings appropriate to the target chart. Reference settings from an existing compatible tile, not guessed keys.
- Use `plan_edit_tile_dql` for query changes, `plan_update_tile_layout` for x/y/w/h, and `plan_patch_dashboard_field` for individual deeply nested properties (pointer relative to `content`).
- All tools starting `plan_` create previews, not writes. Show user the `diff` and `dtctl_dry_run` from plan or `review_change`.
- **Never invoke `publish_change` unless the user has explicitly approved the exact change shown in the current chat.** Even when DTCTL_ALLOW_WRITE=1, obtain that approval and then use confirm=true.
- Validate DQL and visualization field mapping when relevant. Avoid running high-cost queries unless asked.
- Keep all unrelated fields unchanged. Do not change dashboard IDs or overwrite whole documents unless expressly asked.
- Dry-run/backup/re-reading mitigate risk, but dtctl's apply is not an atomic compare-and-swap; warn on concurrent editing.
