"""
Orquestador del agente NL2SQL -> POST /api/query.

Responsable: Rol A.

Pipeline (docs/01-arquitectura.md §2):
    1. fallback.match_rule(question)      -> si coincide (o no hay LLM), usar SQL fijo
    2. si no: llm genera SQL con schema_prompt.build_system_prompt()
    3. sql_guard.validate_sql(sql)         -> solo SELECT, LIMIT, sin PII
    4. db.run_query(sql)                   -> si falla, UN reintento enviando el error al LLM
    5. sql_guard.check_result_columns()
    6. redactar `answer` (LLM o plantilla de la regla)
    7. alerts.recommendations_for(...)
"""


def answer_question(question: str) -> dict:
    """Responde una pregunta en lenguaje natural.

    Devuelve exactamente:
        {"answer": str, "sql": str, "source": "rules" | "llm",
         "columns": list[str], "rows": list[list],
         "chart": {"type": "bar|line|pie|none", "x": str, "y": str},
         "recommendations": list[str]}
    """
    raise NotImplementedError


def choose_chart(columns: list[str], rows: list[list]) -> dict:
    """Elige el gráfico con reglas simples: fecha/mes en x -> line; <= 8 categorías -> bar/pie; si no -> none."""
    raise NotImplementedError
