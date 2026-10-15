"""
Suggestion templates for the active semantic model.

The /suggestions endpoint renders a random subset of the model's templates
(`SUGGESTION_TEMPLATES` in the model package) with placeholders resolved from
a lightweight DAX context query (`build_context_dax`). Templates are
intentionally fixed (no LLM call) for predictable latency and cost.
"""
from __future__ import annotations

import random
import string
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from api.semantic_models import get_active_model

_MODEL = get_active_model()

TEMPLATES: List[str] = list(_MODEL.SUGGESTION_TEMPLATES)


_MONTH_NAMES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def now_in_model_timezone() -> datetime:
    """Current time in the active model's timezone."""
    return datetime.now(ZoneInfo(_MODEL.TIMEZONE))


def get_current_month_pt(now: Optional[datetime] = None) -> str:
    """
    Return current month + year in Portuguese, e.g. "Maio de 2026".
    Uses the active model's timezone.
    """
    if now is None:
        now = now_in_model_timezone()
    month_name = _MONTH_NAMES_PT[now.month - 1]
    return f"{month_name} de {now.year}"


def build_context_dax(now: Optional[datetime] = None) -> str:
    """DAX query that resolves the dynamic placeholders of the templates."""
    return _MODEL.build_context_dax(now or now_in_model_timezone())


def build_context(
    rows: Optional[List[Dict[str, Any]]],
    now: Optional[datetime] = None,
) -> Dict[str, str]:
    """
    Placeholder values for the templates. Always includes current_month_pt;
    the model adds its own keys from the context query rows (rows may be None
    when the query failed).
    """
    now = now or now_in_model_timezone()
    context = {"current_month_pt": get_current_month_pt(now)}
    context.update(_MODEL.build_context(now, rows))
    return context


def _placeholders(template: str) -> List[str]:
    return [name for _, name, _, _ in string.Formatter().parse(template) if name]


def render_templates(context: Dict[str, str], count: int = 6) -> List[str]:
    """
    Render a random subset of templates with the provided context.

    Args:
        context: placeholder values (see build_context)
        count: number of suggestions to return (default 6)

    Returns:
        List of rendered suggestion strings, chosen randomly among the
        templates whose placeholders are all present in the context — a
        template is never returned with a raw placeholder. Never raises.
    """
    usable = [
        template for template in TEMPLATES
        if all(name in context for name in _placeholders(template))
    ]
    selected = random.sample(usable, min(count, len(usable)))
    return [template.format(**context) for template in selected]
