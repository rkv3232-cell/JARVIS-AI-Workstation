# Python & Systems Coding Specialist Skill

## Overview
The **Python & Systems Coding Specialist** provides automated static source code analysis, AST inspection, syntax validation, and code safety scanning for the J.A.R.V.I.S. ecosystem.

## Capabilities
1. **Syntax & AST Validation**: Validates syntax correctness and parses AST tree structure.
2. **Structural Metrics**: Extracts total lines of code, function definitions, and class declarations.
3. **Safety Scanning**: Inspects for potentially unsafe patterns, unhandled exceptions, and dead code.
4. **Actionable Suggestions**: Provides precise diagnostic feedback for code quality improvements.

## Input Parameters
- `code` *(string, optional)*: Raw Python source code string.
- `file_path` *(string, optional)*: Relative or absolute path to a Python script file to inspect.
- `check_security` *(boolean, default true)*: Whether to scan for security-sensitive builtins.

## Output Schema
```json
{
  "status": "SUCCESS",
  "valid_syntax": true,
  "lines_of_code": 45,
  "functions_count": 3,
  "classes_count": 1,
  "issues": [],
  "summary": "Code syntax valid with 3 functions and 1 class."
}
```
