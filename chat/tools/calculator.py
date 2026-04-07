"""Calculator tool — evaluates math expressions safely using sympy."""

import sympy
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor,
)


class CalculatorTool:
    @property
    def definition(self) -> dict:
        return {
            "name": "calculator",
            "description": "Evaluate mathematical expressions. Supports arithmetic, algebra, calculus, and unit conversions. Examples: '2+3*4', 'sqrt(144)', 'integrate(x**2, x)', 'solve(x**2 - 4, x)'",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The math expression to evaluate",
                    }
                },
                "required": ["expression"],
            },
        }

    async def execute(self, params: dict) -> dict:
        expr_str = params.get("expression", "")
        if not expr_str.strip():
            return {"error": "Empty expression"}

        blocked = ["import", "exec", "eval", "open", "__", "os.", "sys.", "subprocess"]
        if any(b in expr_str.lower() for b in blocked):
            return {"error": "Expression contains blocked keywords"}

        try:
            transformations = standard_transformations + (
                implicit_multiplication_application,
                convert_xor,
            )
            parsed = parse_expr(expr_str, transformations=transformations)
            simplified = sympy.simplify(parsed)

            # If the simplified result is a number, format it nicely
            if simplified.is_number:
                if simplified.is_Integer or (simplified.is_Float and int(simplified) == simplified):
                    return {"result": str(int(simplified))}
                result = simplified.evalf()
                # Check if evalf produced an integer value
                if abs(result - round(result)) < 1e-10:
                    return {"result": str(int(round(result)))}
                return {"result": str(result)}

            return {"result": str(simplified)}
        except Exception as e:
            return {"error": f"Could not evaluate: {e}"}
