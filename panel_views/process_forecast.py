from __future__ import annotations

import math
from datetime import date, datetime, time

import pandas as pd
import plotly.express as px
import streamlit as st

from services.metrics import format_datetime, format_duration, format_float, format_int, format_percent
from services.process_forecast import (
    WorkCalendar,
    generate_forecast,
    parse_holidays,
    prepare_lot_history,
    require_admin_access,
)
from services.process_forecast_repository import (
    list_forecasts,
    save_forecast,
    save_routing_forecast,
)
from services.process_routing import RoutingTask, schedule_all_scenarios
from services.planilha_service import (
    find_planilha_for_display,
    load_planilha_processes,
    normalize_process_name,
)


@st.cache_data(show_spinner=False, ttl=30)
def _load_saved_history_cached() -> list[dict]:
    return list_forecasts(is_admin=True, limit=50)


def _clean_dimension(frame: pd.DataFrame, source: str, target: str, *, lower: bool = False) -> pd.DataFrame:
    if target in frame.columns:
        return frame
    result = frame.copy()
    values = result[source].astype("string").str.strip()
    if source == "display":
        values = values.str.replace(r"(?i)\s*-\s*lote.*", "", regex=True)
    if lower:
        values = values.str.lower()
    result[target] = values.mask(values.str.lower().isin(["", "none", "nan", "<na>"]))
    return result


def _scope_options(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    frame = df.copy()
    for source, target, lower in (
        ("display", "display_clean", False),
        ("processo", "processo_clean", False),
        ("maquinario", "maquinario_clean", True),
    ):
        if source not in frame.columns:
            frame[source] = pd.NA
        frame = _clean_dimension(frame, source, target, lower=lower)
    valid = (
        pd.to_numeric(frame.get("quantidade_produzida"), errors="coerce").fillna(0) > 0
    ) & (
        pd.to_numeric(frame.get("duracao_horas"), errors="coerce").fillna(0) > 0
    )
    displays = sorted(frame.loc[valid, "display_clean"].dropna().astype(str).unique())
    frame["forecast_process_key"] = frame["processo"].apply(normalize_process_name)
    frame["forecast_machine_key"] = frame["maquinario"].apply(normalize_process_name)
    return frame, displays


def _routing_catalog(display: str, display_scope: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    path, plan_name = find_planilha_for_display([display])
    if path is not None:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = None
        plan = load_planilha_processes(str(path), mtime)
        if not plan.empty:
            return plan.copy(), f"Roteiro sugerido pela ordem de {plan_name}; revise as dependências."
    fallback = (
        display_scope[["forecast_machine_key", "forecast_process_key", "maquinario", "processo"]]
        .dropna()
        .drop_duplicates(["forecast_machine_key", "forecast_process_key"])
        .reset_index(drop=True)
    )
    fallback = fallback.rename(
        columns={
            "forecast_machine_key": "maquinario_key",
            "forecast_process_key": "processo_key",
            "maquinario": "maquinario_nome",
            "processo": "processo_nome",
        }
    )
    fallback["qnt_por_produto"] = 1.0
    fallback["ordem_planilha"] = range(1, len(fallback) + 1)
    return fallback, "Sem planilha de roteiro: quantidade por produto assumida como 1."


def _parse_codes(value: object) -> tuple[str, ...]:
    return tuple(
        code.strip().upper()
        for code in str(value or "").replace(",", ";").split(";")
        if code.strip()
    )


def _resolve_dependencies(config: pd.DataFrame) -> dict[str, tuple[str, ...]]:
    rows = {str(row["Código"]): row for _, row in config.iterrows()}
    resolved: dict[str, tuple[str, ...]] = {}
    resolving: set[str] = set()

    def resolve(code: str) -> tuple[str, ...]:
        if code in resolved:
            return resolved[code]
        if code in resolving:
            raise ValueError(f"Referência paralela cíclica envolvendo {code}.")
        if code not in rows:
            raise ValueError(f"Código de processo inexistente: {code}.")
        resolving.add(code)
        row = rows[code]
        execution = str(row.get("Execução", "Dependente"))
        if execution == "Inicial":
            dependencies: tuple[str, ...] = ()
        elif execution == "Paralelo":
            reference = str(row.get("Paralelo a", "")).strip().upper()
            if not reference:
                raise ValueError(f"{code}: informe o processo de referência paralela.")
            dependencies = resolve(reference)
        else:
            dependencies = _parse_codes(row.get("Predecessores", ""))
            if not dependencies:
                raise ValueError(f"{code}: informe ao menos um predecessor.")
        resolving.remove(code)
        resolved[code] = dependencies
        return dependencies

    for process_code in rows:
        resolve(process_code)
    return resolved


def _format_lot_label(row: pd.Series) -> str:
    start = row.get("data_inicio")
    date_label = start.strftime("%d/%m/%Y") if pd.notna(start) else "data N/A"
    return (
        f"{row['lote']} · {format_int(row['quantidade_produzida'])} peças · "
        f"{format_float(row['produtividade'], 1)} peças/h · {date_label}"
    )


def _render_scenarios(result) -> None:
    if not result.scenarios:
        st.warning("Sem histórico suficiente para gerar previsão automática.")
        return
    rows = []
    for name in ("Otimista", "Provável", "Conservador"):
        scenario = result.scenarios[name]
        rows.append(
            {
                "Cenário": name,
                "Produtividade estimada": f"{format_float(scenario.productivity)} peças/h",
                "Horas necessárias": format_duration(scenario.required_hours),
                "Data prevista de término": format_datetime(scenario.finish_at),
                "Confiança": result.confidence,
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    probable = result.scenarios["Provável"]
    optimistic = result.scenarios["Otimista"]
    conservative = result.scenarios["Conservador"]
    cols = st.columns(4)
    cols[0].metric("Referência PCP", format_datetime(probable.finish_at))
    cols[1].metric("Lotes analisados", result.valid_lot_count)
    cols[2].metric("Coeficiente de variação", format_percent(result.coefficient_variation, 1))
    spread = conservative.required_hours / optimistic.required_hours - 1
    cols[3].metric("Variação entre extremos", format_percent(spread, 1))


def _render_base_comparison(comparison: dict[str, object] | None) -> None:
    if not comparison:
        return
    st.markdown("### Comparação com o lote-base")
    columns = st.columns(4)
    columns[0].metric("Produtividade do lote", f"{format_float(comparison['productivity_per_operator'])} peças/h/op")
    columns[1].metric("Posição", str(comparison["position"]))
    columns[2].metric("Diferença da média", format_percent(comparison["difference_percent"], 1))
    columns[3].metric("Operadores registrados", int(comparison["operators"]))
    st.caption(
        f"Produzido: {format_int(comparison['quantity'])} · "
        f"Duração: {format_duration(comparison['hours'])} · "
        f"Peças mortas: {format_int(comparison['scrap'])}. "
        "Eficiência do lote não é exibida porque a fonte atual não armazena esse indicador por lote."
    )


def _render_saved_history() -> None:
    with st.expander("Histórico de previsões salvas"):
        try:
            rows = _load_saved_history_cached()
        except Exception as exc:
            st.info(f"Histórico indisponível: {exc}")
            return
        if not rows:
            st.caption("Nenhuma previsão foi salva.")
            return
        display_rows = []
        for row in rows:
            scenarios = (row.get("resultado") or {}).get("scenarios", {})
            display_rows.append(
                {
                    "Data": format_datetime(row.get("created_at")),
                    "Usuário": row.get("created_by"),
                    "Display": row.get("display"),
                    "Processo": row.get("processo"),
                    "Máquina": row.get("maquinario"),
                    "Lote-base": row.get("lote_base") or "—",
                    "Quantidade": row.get("quantidade_planejada"),
                    "Término provável": format_datetime(
                        scenarios.get("Provável", {}).get("finish_at")
                    ),
                }
            )
        st.dataframe(pd.DataFrame(display_rows), hide_index=True, use_container_width=True)


def _render_routing_forecast(frame: pd.DataFrame, displays: list[str], *, username: str) -> None:
    st.info(
        "Configure o roteiro completo. Processos com os mesmos predecessores podem iniciar "
        "em paralelo, desde que exista capacidade de maquinário disponível."
    )
    display = st.selectbox("Display do roteiro", displays, key="routing_display")
    display_scope = frame[frame["display_clean"] == display].copy()
    catalog, source_note = _routing_catalog(display, display_scope)
    st.caption(source_note)
    if catalog.empty:
        st.warning("Nenhum processo foi encontrado para montar o roteiro.")
        return

    catalog = catalog.sort_values("ordem_planilha").reset_index(drop=True)
    machine_rows = (
        catalog[["maquinario_key", "maquinario_nome"]]
        .drop_duplicates("maquinario_key")
        .rename(columns={"maquinario_key": "Chave", "maquinario_nome": "Maquinário"})
    )
    machine_rows["Máquinas disponíveis"] = 1

    st.markdown("### Capacidade por maquinário")
    capacity_editor = st.data_editor(
        machine_rows,
        hide_index=True,
        use_container_width=True,
        disabled=["Chave", "Maquinário"],
        column_config={
            "Máquinas disponíveis": st.column_config.NumberColumn(min_value=1, step=1, required=True)
        },
        key=f"routing_capacity_{normalize_process_name(display)}",
    )
    capacities = {
        str(row["Chave"]): int(row["Máquinas disponíveis"])
        for _, row in capacity_editor.iterrows()
    }

    route_rows = []
    previous_code = ""
    for index, row in catalog.iterrows():
        code = f"P{index + 1:02d}"
        route_rows.append(
            {
                "Código": code,
                "Processo": row["processo_nome"],
                "Maquinário": row["maquinario_nome"],
                "Chave máquina": row["maquinario_key"],
                "Qtd./produto": float(row["qnt_por_produto"]),
                "Execução": "Inicial" if index == 0 else "Dependente",
                "Predecessores": "" if index == 0 else previous_code,
                "Paralelo a": "",
                "Máquinas alocadas": 1,
            }
        )
        previous_code = code
    route_frame = pd.DataFrame(route_rows)
    codes = route_frame["Código"].tolist()

    st.markdown("### Processos dependentes e paralelos")
    st.caption(
        "Dependente: informe um ou mais códigos separados por ponto e vírgula. "
        "Paralelo: escolha um processo de referência; ambos herdarão os mesmos predecessores."
    )
    route_editor = st.data_editor(
        route_frame,
        hide_index=True,
        use_container_width=True,
        disabled=["Código", "Processo", "Maquinário", "Chave máquina", "Qtd./produto"],
        column_config={
            "Execução": st.column_config.SelectboxColumn(
                options=["Inicial", "Dependente", "Paralelo"], required=True
            ),
            "Paralelo a": st.column_config.SelectboxColumn(options=["", *codes]),
            "Máquinas alocadas": st.column_config.NumberColumn(min_value=1, step=1, required=True),
            "Chave máquina": None,
        },
        key=f"routing_dependencies_{normalize_process_name(display)}",
    )

    input_cols = st.columns(4)
    planned_products = input_cols[0].number_input(
        "Quantidade de displays", min_value=1, step=1, value=100, key="routing_quantity"
    )
    operators_per_machine = input_cols[1].number_input(
        "Operadores por máquina", min_value=1, step=1, value=1, key="routing_operators"
    )
    start_date = input_cols[2].date_input(
        "Data de início do roteiro", value=date.today(), key="routing_start_date"
    )
    start_time = input_cols[3].time_input(
        "Horário de início", value=time(7, 0), key="routing_start_time"
    )

    with st.expander("Calendário produtivo do roteiro"):
        calendar_cols = st.columns(3)
        daily_hours = calendar_cols[0].number_input(
            "Horas produtivas/dia", min_value=0.5, max_value=24.0,
            value=9.0, step=0.5, key="routing_daily_hours",
        )
        shift_start = calendar_cols[1].time_input(
            "Início do turno", value=time(7, 0), key="routing_shift_start"
        )
        day_labels = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        selected_days = calendar_cols[2].multiselect(
            "Dias produtivos", day_labels, default=day_labels[:5], key="routing_days"
        )
        holiday_text = st.text_input(
            "Feriados/dias não produtivos (DD/MM/AAAA, separados por vírgula)",
            key="routing_holidays",
        )
    if not selected_days:
        st.error("Selecione ao menos um dia produtivo.")
        return
    calendar = WorkCalendar(
        daily_hours=float(daily_hours), shift_start=shift_start,
        productive_weekdays=frozenset(day_labels.index(day) for day in selected_days),
        holidays=parse_holidays(part.strip() for part in holiday_text.split(",") if part.strip()),
    )

    try:
        dependencies = _resolve_dependencies(route_editor)
    except ValueError as exc:
        st.error(str(exc))
        return

    tasks: list[RoutingTask] = []
    process_quality = []
    for _, row in route_editor.iterrows():
        code = str(row["Código"])
        machine_key = str(row["Chave máquina"])
        allocated = int(row["Máquinas alocadas"])
        capacity = capacities.get(machine_key, 0)
        if allocated > capacity:
            st.error(
                f"{code}: {allocated} máquina(s) alocada(s), mas apenas {capacity} disponível(is)."
            )
            return
        process_key = normalize_process_name(row["Processo"])
        history_scope = display_scope[
            (display_scope["forecast_process_key"] == process_key)
            & (display_scope["forecast_machine_key"] == machine_key)
        ].copy()
        required_quantity = max(1, int(math.ceil(float(planned_products) * float(row["Qtd./produto"]))))
        forecast = generate_forecast(
            history_scope,
            planned_quantity=required_quantity,
            start_at=datetime.combine(start_date, start_time),
            planned_operators=int(operators_per_machine),
            planned_machines=allocated,
            calendar=calendar,
        )
        process_quality.append(
            {
                "Código": code, "Processo": row["Processo"],
                "Lotes válidos": forecast.valid_lot_count, "Confiança": forecast.confidence,
            }
        )
        if not forecast.scenarios:
            continue
        tasks.append(
            RoutingTask(
                code=code, process=str(row["Processo"]), machine=machine_key,
                predecessors=dependencies[code], machine_units=allocated,
                required_quantity=required_quantity,
                scenario_hours={
                    name: scenario.required_hours for name, scenario in forecast.scenarios.items()
                },
            )
        )

    quality_frame = pd.DataFrame(process_quality)
    insufficient = quality_frame[quality_frame["Confiança"] == "Sem histórico suficiente"]
    if not insufficient.empty:
        st.warning(
            "Não foi possível calcular o roteiro completo: processos sem ao menos dois lotes válidos."
        )
        st.dataframe(quality_frame, hide_index=True, use_container_width=True)
        return

    try:
        routing = schedule_all_scenarios(
            tasks,
            start_at=datetime.combine(start_date, start_time),
            calendar=calendar,
            machine_capacities=capacities,
        )
    except ValueError as exc:
        st.error(str(exc))
        return

    result_rows = []
    for name in ("Otimista", "Provável", "Conservador"):
        scenario = routing[name]
        result_rows.append(
            {
                "Cenário": name,
                "Término do roteiro": format_datetime(scenario.finish_at),
                "Processos": len(scenario.schedule),
            }
        )
    st.markdown("### Previsão do roteiro completo")
    st.dataframe(pd.DataFrame(result_rows), hide_index=True, use_container_width=True)

    probable = routing["Provável"].schedule.copy()
    probable["Atividade"] = probable["code"] + " · " + probable["process"]
    probable["Início"] = probable["start"]
    probable["Término"] = probable["finish"]
    probable["Maquinário"] = probable["machine"]
    fig = px.timeline(
        probable, x_start="Início", x_end="Término", y="Atividade",
        color="Maquinário", hover_data=["predecessors", "machine_units", "required_quantity", "hours"],
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(height=max(420, 36 * len(probable)), margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "O gráfico usa datas corridas no eixo horizontal; fins de semana e feriados podem aparecer "
        "dentro das barras, mas não são contabilizados nas horas produtivas."
    )

    schedule_table = probable.rename(
        columns={
            "code": "Código", "process": "Processo", "machine": "Maquinário",
            "predecessors": "Predecessores", "machine_units": "Máquinas",
            "required_quantity": "Quantidade", "hours": "Horas",
            "start": "Início", "finish": "Término",
        }
    )
    st.dataframe(
        schedule_table[[
            "Código", "Processo", "Maquinário", "Predecessores", "Máquinas",
            "Quantidade", "Horas", "Início", "Término",
        ]],
        hide_index=True, use_container_width=True,
    )

    if st.button("Salvar previsão do roteiro", type="primary"):
        routing_payload = {
            "confidence": "Por processo",
            "valid_lots": {
                str(row["Código"]): int(row["Lotes válidos"])
                for _, row in quality_frame.iterrows()
            },
            "scenarios": {
                name: {
                    "finish_at": scenario.finish_at.isoformat(),
                    "processes": len(scenario.schedule),
                    "schedule": [
                        {
                            "code": str(item["code"]),
                            "process": str(item["process"]),
                            "machine": str(item["machine"]),
                            "predecessors": str(item["predecessors"]),
                            "machine_units": int(item["machine_units"]),
                            "required_quantity": int(item["required_quantity"]),
                            "hours": float(item["hours"]),
                            "start": item["start"].isoformat(),
                            "finish": item["finish"].isoformat(),
                        }
                        for _, item in scenario.schedule.iterrows()
                    ],
                }
                for name, scenario in routing.items()
            },
        }
        parameters = {
            "machine_capacities": capacities,
            "operators_per_machine": int(operators_per_machine),
            "daily_hours": float(daily_hours),
            "shift_start": shift_start.isoformat(),
            "productive_weekdays": sorted(calendar.productive_weekdays),
            "holidays": sorted(value.isoformat() for value in calendar.holidays),
            "route": [
                {
                    "code": str(row["Código"]),
                    "process": str(row["Processo"]),
                    "machine": str(row["Chave máquina"]),
                    "quantity_per_product": float(row["Qtd./produto"]),
                    "execution": str(row["Execução"]),
                    "predecessors": list(dependencies[str(row["Código"])]),
                    "machine_units": int(row["Máquinas alocadas"]),
                }
                for _, row in route_editor.iterrows()
            ],
        }
        try:
            forecast_id = save_routing_forecast(
                is_admin=True, username=username, display=display,
                planned_quantity=int(planned_products),
                start_at=datetime.combine(start_date, start_time),
                operators_per_machine=int(operators_per_machine),
                parameters=parameters, routing_result=routing_payload,
            )
        except Exception as exc:
            st.error(f"Não foi possível salvar o roteiro: {exc}")
        else:
            _load_saved_history_cached.clear()
            st.success(f"Previsão de roteiro #{forecast_id} salva com sucesso.")


def render_process_forecast(df: pd.DataFrame, *, username: str, is_admin: bool) -> None:
    require_admin_access(is_admin)
    st.caption(
        "Simulação baseada em lotes concluídos comparáveis, produtividade por hora produtiva "
        "e calendário configurado abaixo. Alterações recalculam automaticamente."
    )
    frame, displays = _scope_options(df)
    if not displays:
        st.warning("Nenhum display possui apontamentos com quantidade e duração válidas.")
        return

    forecast_mode = st.radio(
        "Modo de previsão",
        ["Processo individual", "Roteiro: paralelos e dependentes"],
        horizontal=True,
        key="forecast_mode",
    )
    if forecast_mode == "Roteiro: paralelos e dependentes":
        _render_routing_forecast(frame, displays, username=username)
        return

    selector_cols = st.columns(3)
    display = selector_cols[0].selectbox("Display", displays, key="forecast_display")
    display_scope = frame[frame["display_clean"] == display]
    processes = sorted(display_scope["processo_clean"].dropna().astype(str).unique())
    if not processes:
        st.warning("O display selecionado não possui processo válido.")
        return
    processo = selector_cols[1].selectbox("Processo comparável", processes, key="forecast_process")
    process_scope = display_scope[display_scope["processo_clean"] == processo]
    machines = sorted(process_scope["maquinario_clean"].dropna().astype(str).unique())
    if not machines:
        st.warning("O processo selecionado não possui maquinário identificado.")
        return
    maquinario = selector_cols[2].selectbox("Maquinário comparável", machines, key="forecast_machine")
    scope = process_scope[process_scope["maquinario_clean"] == maquinario].copy()

    lots, preliminary_exclusions = prepare_lot_history(scope)
    lot_options = [str(value) for value in lots.get("lote", pd.Series(dtype=str)).tolist()]
    lot_rows = {str(row["lote"]): row for _, row in lots.iterrows()}
    base_lot = st.selectbox(
        "Lote-base de referência",
        [None, *lot_options],
        format_func=lambda value: "Sem lote-base" if value is None else _format_lot_label(lot_rows[str(value)]),
        key="forecast_base_lot",
    )

    input_cols = st.columns(5)
    planned_quantity = input_cols[0].number_input(
        "Quantidade a produzir", min_value=1, step=1, value=100, key="forecast_quantity"
    )
    start_date = input_cols[1].date_input("Data estimada de início", value=date.today(), key="forecast_start_date")
    start_time = input_cols[2].time_input("Horário de início", value=time(7, 0), key="forecast_start_time")
    planned_operators = input_cols[3].number_input(
        "Operadores por máquina", min_value=1, step=1, value=1, key="forecast_operators"
    )
    planned_machines = input_cols[4].number_input(
        "Máquinas disponíveis", min_value=1, step=1, value=1, key="forecast_machines"
    )

    with st.expander("Calendário produtivo e premissas", expanded=False):
        calendar_cols = st.columns(3)
        daily_hours = calendar_cols[0].number_input(
            "Horas produtivas por dia", min_value=0.5, max_value=24.0,
            value=9.0, step=0.5, key="forecast_daily_hours",
        )
        shift_start = calendar_cols[1].time_input(
            "Início do turno", value=time(7, 0), key="forecast_shift_start"
        )
        day_labels = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        selected_days = calendar_cols[2].multiselect(
            "Dias produtivos", day_labels, default=day_labels[:5], key="forecast_days"
        )
        holiday_text = st.text_input(
            "Feriados/dias não produtivos (DD/MM/AAAA, separados por vírgula)",
            key="forecast_holidays",
        )

    if not selected_days:
        st.error("Selecione ao menos um dia produtivo.")
        return
    holidays = parse_holidays(part.strip() for part in holiday_text.split(",") if part.strip())
    calendar = WorkCalendar(
        daily_hours=float(daily_hours), shift_start=shift_start,
        productive_weekdays=frozenset(day_labels.index(day) for day in selected_days),
        holidays=holidays,
    )
    result = generate_forecast(
        scope, planned_quantity=int(planned_quantity),
        start_at=datetime.combine(start_date, start_time),
        planned_operators=int(planned_operators), planned_machines=int(planned_machines),
        calendar=calendar, base_lot=base_lot,
    )

    for warning in result.warnings:
        st.warning(warning)
    _render_scenarios(result)
    _render_base_comparison(result.base_comparison)

    with st.expander("Critérios, amostra e exclusões"):
        st.write(
            "Provável: soma produzida ÷ soma de horas-operador. Otimista e conservador: "
            "mediana, respectivamente, dos 20% superiores e inferiores (mínimo de dois lotes). "
            "A taxa por operador é multiplicada pelos operadores previstos. Outliers: limites de "
            "Tukey (1,5 IQR), aplicados com quatro ou mais lotes."
        )
        exclusions = result.exclusions or preliminary_exclusions
        st.json(exclusions)
        if not result.lots.empty:
            sample = result.lots.rename(
                columns={
                    "lote": "Lote", "quantidade_produzida": "Quantidade",
                    "duracao_horas": "Horas", "operadores": "Operadores",
                    "pecas_mortas": "Peças mortas", "produtividade": "Peças/h",
                    "produtividade_por_operador": "Peças/h/operador",
                    "data_inicio": "Início", "data_termino": "Término",
                }
            )
            visible = [
                "Lote", "Quantidade", "Horas", "Operadores", "Peças mortas",
                "Peças/h", "Peças/h/operador", "Início", "Término",
            ]
            st.dataframe(sample[visible], hide_index=True, use_container_width=True)

    if result.scenarios and st.button("Salvar previsão", type="primary"):
        parameters = {
            "daily_hours": float(daily_hours), "shift_start": shift_start.isoformat(),
            "productive_weekdays": sorted(calendar.productive_weekdays),
            "holidays": sorted(value.isoformat() for value in holidays),
            "planned_machines": int(planned_machines),
        }
        try:
            forecast_id = save_forecast(
                is_admin=True, username=username, display=display, processo=processo,
                maquinario=maquinario, base_lot=base_lot,
                planned_quantity=int(planned_quantity),
                start_at=datetime.combine(start_date, start_time),
                planned_operators=int(planned_operators), parameters=parameters, result=result,
            )
        except Exception as exc:
            st.error(f"Não foi possível salvar a previsão: {exc}")
        else:
            _load_saved_history_cached.clear()
            st.success(f"Previsão #{forecast_id} salva com sucesso.")

    _render_saved_history()
