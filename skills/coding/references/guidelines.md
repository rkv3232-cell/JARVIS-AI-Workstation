# Python Coding Standards & Clean Architecture Guidelines

1. **Explicit Typing**: Use Python 3.10+ type hints everywhere.
2. **Pathlib Usage**: Prefer `pathlib.Path` over raw `os.path` strings.
3. **AST Safety**: Prohibit dynamic `eval()` or unvalidated `exec()`.
4. **Error Handling**: Catch specific exceptions and log with context.
