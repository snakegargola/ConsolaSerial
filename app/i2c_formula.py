"""Safe formulas and bit-field helpers for datasheet-driven sensor decoding."""

import ast
import math


_FUNCTIONS = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "sqrt": math.sqrt,
    "pow": pow,
}
_BINARY = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.BitAnd: lambda a, b: int(a) & int(b),
    ast.BitOr: lambda a, b: int(a) | int(b),
    ast.BitXor: lambda a, b: int(a) ^ int(b),
}
_UNARY = {
    ast.UAdd: lambda value: value,
    ast.USub: lambda value: -value,
    ast.Invert: lambda value: ~int(value),
}


def evaluate_formula(expression, **variables):
    """Evaluate a small arithmetic expression without ``eval`` or attributes."""
    expression = str(expression).strip()
    if not expression:
        return variables.get("x")
    if len(expression) > 256:
        raise ValueError("Formula is too long.")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Formula syntax is invalid.") from exc
    if sum(1 for _node in ast.walk(tree)) > 64:
        raise ValueError("Formula is too complex.")

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if abs(float(node.value)) > 1e15:
                raise ValueError("Formula constant is too large.")
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise ValueError(f"Unknown formula variable: {node.id}")
            return variables[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            return _BINARY[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            base, exponent = visit(node.left), visit(node.right)
            if abs(float(exponent)) > 16:
                raise ValueError("Formula exponent must be between -16 and 16.")
            return base ** exponent
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.LShift, ast.RShift)
        ):
            value, shift = int(visit(node.left)), int(visit(node.right))
            if not 0 <= shift <= 63:
                raise ValueError("Formula shift must be from 0 to 63 bits.")
            return value << shift if isinstance(node.op, ast.LShift) else value >> shift
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](visit(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            function = _FUNCTIONS.get(node.func.id)
            if function is None or node.keywords:
                raise ValueError("Formula function is not allowed.")
            arguments = [visit(argument) for argument in node.args]
            if node.func.id == "pow" and len(arguments) >= 2:
                if abs(float(arguments[1])) > 16:
                    raise ValueError("Formula exponent must be between -16 and 16.")
            return function(*arguments)
        raise ValueError("Formula contains an unsupported operation.")

    try:
        result = visit(tree)
    except (ArithmeticError, OverflowError, TypeError) as exc:
        raise ValueError(f"Formula failed: {exc}") from exc
    if not isinstance(result, (int, float)) or not math.isfinite(float(result)):
        raise ValueError("Formula result must be a finite number.")
    return result


def extract_bit_field(value, specification):
    """Extract ``bit`` or inclusive ``msb:lsb`` from an integer."""
    text = str(specification).strip()
    if not text:
        return int(value)
    try:
        if ":" in text:
            msb_text, lsb_text = text.split(":", 1)
            msb, lsb = int(msb_text, 0), int(lsb_text, 0)
        else:
            msb = lsb = int(text, 0)
    except ValueError as exc:
        raise ValueError("Bit field must be BIT or MSB:LSB, for example 7:5.") from exc
    if not 0 <= lsb <= msb <= 63:
        raise ValueError("Bit field must satisfy 0 <= LSB <= MSB <= 63.")
    return (int(value) >> lsb) & ((1 << (msb - lsb + 1)) - 1)


def parse_enum_map(text):
    """Parse ``0=Sleep, 1=Active`` into an integer-to-label mapping."""
    result = {}
    if not str(text).strip():
        return result
    for entry in str(text).split(","):
        if "=" not in entry:
            raise ValueError("Enum entries must use VALUE=Label.")
        raw_value, label = entry.split("=", 1)
        try:
            value = int(raw_value.strip(), 0)
        except ValueError as exc:
            raise ValueError(f"Invalid enum value: {raw_value.strip()}") from exc
        label = label.strip()
        if not label:
            raise ValueError(f"Enum 0x{value:X} has an empty label.")
        result[value] = label
    return result
