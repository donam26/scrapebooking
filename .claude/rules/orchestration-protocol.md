# Orchestration Protocol

## Task Approach
- For simple bugs/changes: fix directly, verify with syntax check
- For medium features: outline steps, implement sequentially, verify each step
- For large features: break into phases, implement one phase at a time

## File Organization
- Plans and implementation docs go in `./plans/` directory
- Project documentation goes in `./docs/` directory
- Do NOT create markdown files outside these directories unless requested

## Quality Checks
After any code change, always:
1. `php -l <file>` — syntax check
2. `./vendor/bin/pint <file>` — format
3. Verify the change works with existing code (no broken imports, no missing dependencies)
