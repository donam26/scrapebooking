# Documentation Management

## Directory Structure
- `./docs/` — Project documentation (architecture, standards, roadmap)
- `./plans/` — Implementation plans and reports

## When to Update Docs
- After implementing a major feature: update changelog and roadmap
- After architectural changes: update system architecture doc
- After adding new patterns/conventions: update code standards

## Plan Format
When creating implementation plans, save in `./plans/` with structure:
```
plans/{description}/
  plan.md              # Overview with phases and status
  phase-01-*.md        # Detailed phase files
  reports/             # Research and review reports
```
