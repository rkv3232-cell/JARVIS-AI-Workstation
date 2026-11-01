"""
Execution script for coding_specialist skill.
Reads JSON payload from stdin and writes JSON response to stdout.
"""

import sys
import json
import ast
from pathlib import Path

def analyze_python_code(code_str: str, check_security: bool = True):
    lines = code_str.splitlines()
    loc = len([l for l in lines if l.strip() and not l.strip().startswith("#")])
    
    try:
        tree = ast.parse(code_str)
    except SyntaxError as e:
        return {
            "status": "ERROR",
            "valid_syntax": False,
            "lines_of_code": loc,
            "error": f"SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}",
            "issues": [f"Line {e.lineno}: {e.msg}"]
        }
        
    functions = []
    classes = []
    issues = []
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif check_security and isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
                issues.append(f"Security Alert: Usage of dynamic code evaluation '{node.func.id}()' at line {node.lineno}.")

    return {
        "status": "SUCCESS",
        "valid_syntax": True,
        "lines_of_code": loc,
        "functions_count": len(functions),
        "functions": functions,
        "classes_count": len(classes),
        "classes": classes,
        "issues": issues,
        "summary": f"Clean code structure with {len(functions)} functions and {len(classes)} classes across {loc} SLOC."
    }

def main():
    try:
        raw_input = sys.stdin.read()
        params = json.loads(raw_input) if raw_input.strip() else {}
    except Exception:
        params = {}

    code_to_test = params.get("code")
    file_path = params.get("file_path")
    check_sec = params.get("check_security", True)

    if not code_to_test and file_path:
        p = Path(file_path)
        if p.exists() and p.is_file():
            try:
                code_to_test = p.read_text(encoding="utf-8")
            except Exception as e:
                print(json.dumps({"status": "ERROR", "error": f"Failed to read file: {e}"}))
                sys.exit(1)
        else:
            print(json.dumps({"status": "ERROR", "error": f"File not found: {file_path}"}))
            sys.exit(1)

    if not code_to_test:
        code_to_test = "# Sample Python code\ndef hello():\n    return 'Hello J.A.R.V.I.S.'"

    result = analyze_python_code(code_to_test, check_security=check_sec)
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()

