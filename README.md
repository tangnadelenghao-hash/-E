# TI_cup_E_25

Private team repository for the TI Cup E problem project.

## Project Layout

- `car/` - car-side embedded code and board projects.
- `vision/` - vision and camera code.
- `tools/` - local build, flash, and environment helper scripts.
- `docs/` - notes, plans, and project documentation.
- `resources_local/` - large vendor/reference packages kept only on local machines.

## Module Rules

Put new code in the matching area:

- Car firmware, drivers, and MCU experiments go under `car/<module_name>/`.
- Vision scripts, camera tests, and image-processing modules go under `vision/<module_name>/`.
- Shared helper scripts go under `tools/`.
- Team notes and usage docs go under `docs/`.

Use short English folder names that describe the module, for example `motor_control`,
`oled_display`, `camera_stream`, or `rectangle_detector`.

## Git Workflow

This is a private team project. After every important change:

1. Keep generated files and large local packages out of Git.
2. Commit only the files related to the change.
3. Push the commit to GitHub so the team has the latest code.

The large competition/reference package is intentionally ignored in
`resources_local/` and should not be uploaded to GitHub.
