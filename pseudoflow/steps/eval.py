import json
import logging
from typing import Any

from pseudoflow.engine.context import FlowContext

logger = logging.getLogger("pseudoflow.steps.eval")


def _safe_eval(expression: str, vars_map: dict) -> Any:
    # Ограниченный контекст для eval
    safe_locals = {
        "json": json.loads,
        "str": str,
        "int": int,
        "bool": bool,
        "list": list,
        "dict": dict,
    }
    # Добавляем переменные потока в контекст (опционально, или использовать подстановку ${})
    # В текущей реализации переменные уже подставлены через ${...} до вызова этого шага,
    # поэтому expression уже содержит значения.

    try:
        return eval(expression, {"__builtins__": {}}, safe_locals)
    except Exception as e:
        raise ValueError(f"Failed to evaluate expression '{expression}': {e}")


async def handle(step: dict, ctx: FlowContext) -> None:
    expression = step.get("expression")
    target_var = step.get("var")

    if not expression:
        raise ValueError("eval.expression is required")
    if not target_var:
        raise ValueError("eval.var is required")

    result = _safe_eval(expression, ctx.vars)

    # Сохраняем результат. Если это объект/dict, превращаем в строку или сохраняем как есть?
    # ТЗ подразумевает строковые переменные, но для json-маппинга может потребоваться
    # сохранение структуры, если шаблонизатор умеет с ней работать.
    # Для совместимости приводим к строке, если это не примитив.
    if isinstance(result, (dict, list)):
        ctx.vars[target_var] = json.dumps(result)
    else:
        ctx.vars[target_var] = str(result)

    logger.info(f"Evaluated '{expression}' -> var '{target_var}'")