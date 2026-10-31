"""
JARVIS Instant Math & Calculation Engine
Evaluates mathematical expressions, percentages, and conversational arithmetic in <1ms
without requiring internet search or LLM tokens.
"""

import ast
import operator
import re
import math
from typing import Optional, Dict, Any

SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

HINDI_NUMBERS = {
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5,
    "chhah": 6, "che": 6, "saat": 7, "aath": 8, "ath": 8, "nau": 9, "no": 9, "das": 10,
    "gyarah": 11, "barah": 12, "terah": 13, "chaudah": 14, "pandrah": 15, "solah": 16,
    "satrah": 17, "atharah": 18, "unnees": 19, "bees": 20, "pachees": 25, "tees": 30,
    "paintees": 35, "chalis": 40, "pachas": 50, "saath": 60, "sattar": 70, "assi": 80,
    "nabbe": 90, "sau": 100, "hazar": 1000, "lakh": 100000,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "छह": 6, "सात": 7,
    "आठ": 8, "नौ": 9, "दस": 10, "ग्यारह": 11, "बारह": 12, "तेरह": 13, "चौदह": 14,
    "पंद्रह": 15, "सोलह": 16, "सत्रह": 17, "अठारह": 18, "उन्नीस": 19, "बीस": 20,
    "पच्चीस": 25, "तीस": 30, "चालीस": 40, "पचास": 50, "साठ": 60, "सत्तर": 70,
    "अस्सी": 80, "नब्बे": 90, "सौ": 100, "हज़ार": 1000, "हजार": 1000, "लाख": 100000
}

def _safe_eval_node(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Non-numeric literal")
    elif isinstance(node, ast.BinOp):
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type}")
        op_func = SAFE_OPERATORS[op_type]
        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Division by zero")
        return op_func(left, right)
    elif isinstance(node, ast.UnaryOp):
        operand = _safe_eval_node(node.operand)
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type}")
        return SAFE_OPERATORS[op_type](operand)
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            func_name = node.func.id.lower()
            args = [_safe_eval_node(arg) for arg in node.args]
            if func_name == "sqrt" and len(args) == 1:
                if args[0] < 0:
                    raise ValueError("Square root of negative number")
                return math.sqrt(args[0])
            elif func_name == "abs" and len(args) == 1:
                return abs(args[0])
            elif func_name == "round" and len(args) in (1, 2):
                return round(*args)
        raise ValueError("Unsupported function call")
    raise ValueError("Invalid syntax for safe math evaluation")

def safe_math_eval(expr: str) -> Optional[float]:
    """Evaluates a clean mathematical string safely via AST."""
    clean_expr = expr.replace("^", "**").replace("x", "*").replace("×", "*").replace("÷", "/")
    # Remove any unwanted characters (allow only digits, operators, parens, decimal, sqrt, abs, round)
    if not re.match(r'^[0-9\.\+\-\*\/\%\(\)\s\*,sqrt,abs,round]+$', clean_expr):
        return None
    try:
        tree = ast.parse(clean_expr, mode='eval')
        res = _safe_eval_node(tree.body)
        if isinstance(res, (int, float)) and not math.isnan(res) and not math.isinf(res):
            return res
        return None
    except Exception:
        return None

def format_number(n: float) -> str:
    """Formats float/int nicely without trailing zeroes."""
    if abs(n - round(n)) < 1e-9:
        return f"{int(round(n)):,}"
    rounded = round(n, 4)
    s = f"{rounded:,.4f}".rstrip("0").rstrip(".")
    return s

def solve_math_query(query_text: str) -> Optional[Dict[str, Any]]:
    """
    Detects and solves math queries, arithmetic, and percentages.
    Returns None if the query is not a calculation.
    """
    raw = query_text.strip()
    low = raw.lower().replace("?", "").replace("!", "").strip()

    # 1. Percentage Calculations
    # Pattern A: 18% of 50000 or 18 % of 50000
    m_pct_a = re.search(r'(\d+(?:\.\d+)?)\s*%\s*(?:of|ka|ki|ke|me|mein|का|की|के)?\s*(\d+(?:\.\d+)?)', low)
    # Pattern B: 50000 ka 18% or 50000 का 18 प्रतिशत
    m_pct_b = re.search(r'(\d+(?:\.\d+)?)\s*(?:ka|ki|ke|me|mein|का|की|के)\s*(\d+(?:\.\d+)?)\s*(?:%|pratishat|प्रतिशत|percent)', low)

    if m_pct_a:
        pct = float(m_pct_a.group(1))
        base = float(m_pct_a.group(2))
        res = (pct / 100.0) * base
        expr_str = f"{format_number(base)} का {format_number(pct)}%"
        res_str = format_number(res)
        return {
            "text": f"जी सर, {expr_str} = {res_str} होता है।",
            "expression": f"{base} * {pct}%",
            "result": res,
            "formatted_result": res_str,
            "intent": "calculation"
        }
    elif m_pct_b:
        base = float(m_pct_b.group(1))
        pct = float(m_pct_b.group(2))
        res = (pct / 100.0) * base
        expr_str = f"{format_number(base)} का {format_number(pct)}%"
        res_str = format_number(res)
        return {
            "text": f"जी सर, {expr_str} = {res_str} होता है।",
            "expression": f"{base} * {pct}%",
            "result": res,
            "formatted_result": res_str,
            "intent": "calculation"
        }

    # 2. Square Root Calculations
    # e.g. "square root of 144", "144 ka square root", "144 ka vargmool", "sqrt(144)"
    m_sqrt = re.search(r'(?:square\s*root\s*(?:of)?|sqrt|वर्गमूल)\s*(?:of)?\s*(\d+(?:\.\d+)?)', low) or \
             re.search(r'(\d+(?:\.\d+)?)\s*(?:ka|ki|ke|का|की|के)?\s*(?:square\s*root|sqrt|vargmool|वर्गमूल)', low)
    if m_sqrt:
        val = float(m_sqrt.group(1))
        if val >= 0:
            res = math.sqrt(val)
            res_str = format_number(res)
            return {
                "text": f"जी सर, √{format_number(val)} = {res_str} होता है।",
                "expression": f"sqrt({val})",
                "result": res,
                "formatted_result": res_str,
                "intent": "calculation"
            }

    # 3. Direct Mathematical Expression Check (e.g. "2+2", "2 + 2", "5 * 12", "100 / 4", "500 - 120", "2^8")
    # Clean filler prefixes like "calculate", "solve", "kitna hota hai", "kitna hoga", "kya hoga"
    expr_clean = low
    for prefix in ["calculate", "solve", "math", "hisab karo", "बताओ", "गणना करो", "जोड़ो", "कितना होता है", "कितना होगा", "क्या होगा"]:
        expr_clean = expr_clean.replace(prefix, "")
    expr_clean = expr_clean.replace("=", "").strip()

    # Replace conversational operators
    conv_replacements = [
        ("plus", "+"), ("प्लस", "+"), ("aur", "+"), ("और", "+"), ("and", "+"),
        ("minus", "-"), ("माइनस", "-"), ("ghatao", "-"), ("घटाओ", "-"), ("kam", "-"),
        ("multiply by", "*"), ("multiplied by", "*"), ("times", "*"), ("guna", "*"), ("गुणा", "*"),
        ("divided by", "/"), ("divide by", "/"), ("divide", "/"), ("bhag", "/"), ("भाग", "/"),
        ("power", "**"), ("ki power", "**"), ("घात", "**")
    ]
    for w_from, w_to in conv_replacements:
        expr_clean = re.sub(rf'\b{re.escape(w_from)}\b', f' {w_to} ', expr_clean)

    # Replace word numbers (e.g. "do aur do" -> "2 + 2")
    tokens = expr_clean.split()
    converted_tokens = []
    has_converted_word_num = False
    for t in tokens:
        if t in HINDI_NUMBERS:
            converted_tokens.append(str(HINDI_NUMBERS[t]))
            has_converted_word_num = True
        else:
            converted_tokens.append(t)
    expr_clean = " ".join(converted_tokens)

    # Check if this looks like a valid math expression with at least one operator
    # Examples: "2+2", "2 + 2", "100 - 30", "5 * 25", "10 / 2", "2**8"
    is_math_syntax = bool(re.search(r'[-+]?\d+(?:\.\d+)?\s*[\+\-\*\/\%\^]\s*[-+]?\d+(?:\.\d+)?', expr_clean))
    
    if is_math_syntax:
        # Strip all letters except allowed functions
        clean_for_eval = re.sub(r'[^0-9\.\+\-\*\/\%\(\)\s\^]', '', expr_clean).strip()
        val = safe_math_eval(clean_for_eval)
        if val is not None:
            # Format clean expression string
            display_expr = clean_for_eval.replace("**", "^").replace("*", "×").replace("/", "÷")
            res_str = format_number(val)
            return {
                "text": f"जी सर, {display_expr} = {res_str} होता है।",
                "expression": clean_for_eval,
                "result": val,
                "formatted_result": res_str,
                "intent": "calculation"
            }

    return None

