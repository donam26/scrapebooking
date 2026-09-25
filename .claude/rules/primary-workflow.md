# Primary Workflow

## Before Coding
- Read existing code in the area you're modifying to understand patterns
- Check `CLAUDE.md` and `docs/` for project conventions
- For large features: outline your approach before implementing

## During Implementation
- Follow existing code patterns in the codebase
- After creating/modifying a PHP file, run `php -l <file>` to check syntax
- Keep controllers thin — put business logic in Services
- Use Form Requests for validation
- Use Enums for fixed value sets

## After Implementation
- Run `php -l` on all changed files
- Run `./vendor/bin/pint` for formatting
- Run `php artisan test` if tests exist for the modified area
- Review your changes for consistency with existing code

## Debugging
- Use `php artisan tinker` to test queries and logic interactively
- Check Laravel logs in `storage/logs/laravel.log`
- Use `php artisan route:list --path=<path>` to verify routes
