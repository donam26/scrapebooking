# Development Rules

Follow YAGNI, KISS, DRY principles.

## PHP & Laravel Conventions
- **PHP 8.2+**: Use typed properties, enums, match expressions, named arguments, constructor promotion
- **File naming**: PascalCase for all PHP files (Laravel standard): `ExamRoomController.php`, `ExamRoomService.php`
- **Namespaces**: Must match directory structure exactly
- **Models**: Place in `app/Models/`, use `HasUuids` trait for UUID primary keys, `SoftDeletes` where appropriate
- **Services**: Place in `app/Services/`, inject dependencies via constructor promotion (`protected Service $service`)
- **Controllers**: Place in `app/Http/Controllers/{Role}/`, inject services via constructor
- **Requests**: Place in `app/Http/Requests/{Domain}/`, separate Store/Update requests
- **Enums**: Place in `app/Enums/`, use backed enums with `label()` and `color()` methods
- **Traits**: Place in `app/Traits/{Domain}/`

## Code Structure
- Keep controllers thin: delegate business logic to Services
- Use Form Requests for validation, not inline validation in controllers
- Use Eloquent relationships and scopes instead of raw queries
- Use Enums instead of string/int constants
- Group related functionality into domain folders (e.g. `ExamRoom/`, `Auth/`)
- Wrap database operations in `DB::transaction()` when multiple writes are involved

## Code Quality
- Run `php -l <file>` after modifying PHP files to check syntax
- Run `./vendor/bin/pint` for code formatting before commit
- Use try-catch for external service calls and database transactions
- Return proper HTTP status codes in API responses
- Do NOT create new "enhanced" versions of files — update existing files directly

## Pre-commit Rules
- Run `php -l` syntax check on changed files
- Run `./vendor/bin/pint` for formatting
- Do NOT commit `.env`, API keys, or database credentials
- Use conventional commit format: `feat:`, `fix:`, `refactor:`, `chore:`
