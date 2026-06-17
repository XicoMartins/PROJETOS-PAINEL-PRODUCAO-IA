from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import streamlit as st

from filters import FilterContext
from panel_views.common import (
    build_display_image_map,
    build_panel_card_html,
    build_time_estimate_html,
    load_image_as_data_uri,
    render_panel_card,
    render_prod_hora_kpis,
)
from services.display_panel_service import compute_display_panel_summary
from services.metrics import format_duration, format_float, format_int, format_percent
from services.planilha_service import normalize_display_name


def render_display_panel(
    df: pd.DataFrame,
    filter_context: FilterContext,
    display_selected_override: list[str] | None = None,
    numero_selected_override: list[str] | None = None,
    layout: str = "default",
) -> None:
    if df.empty:
        return

    if layout != "tv":
        st.markdown(
            """
            <style>
            :root {
                --display-panel-shared-height: min(78vh, 980px);
            }
            .display-photo-shell {
                height: var(--display-panel-shared-height);
                width: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
            }
            .display-photo-shell img {
                width: 100%;
                height: 100%;
                object-fit: contain;
                object-position: center;
                display: block;
            }
            .display-panel-stack {
                height: var(--display-panel-shared-height);
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
            .display-panel-stack .panel-card {
                flex: 1 1 0;
                min-height: 84px;
                display: flex;
                flex-direction: column;
                justify-content: center;
                overflow: hidden;
                margin-bottom: 0 !important;
            }
            .display-panel-stack .panel-card-emphasis {
                flex: 1.7 1 0;
                justify-content: flex-start;
            }
            .display-panel-stack .panel-card-compact {
                flex: 0.78 1 0;
            }
            .display-panel-stack .panel-card-a-produzir {
                flex: 1.05 1 0;
            }
            .display-panel-stack .panel-title {
                font-size: clamp(0.72rem, 0.22vw + 0.66rem, 0.84rem);
                line-height: 1.2;
                margin-bottom: 0.35rem;
            }
            .display-panel-stack .panel-value {
                font-size: clamp(0.98rem, 0.6vw + 0.8rem, 1.55rem);
                line-height: 1.15;
            }
            .display-panel-stack .panel-sub {
                font-size: clamp(0.72rem, 0.2vw + 0.66rem, 0.84rem);
                line-height: 1.2;
                margin-top: 0.45rem;
            }
            .display-panel-stack .panel-time-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.7rem;
                width: 100%;
            }
            .display-panel-stack .panel-time-item {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 0.18rem;
                align-items: flex-start;
            }
            .display-panel-stack .panel-time-label {
                font-size: clamp(0.8rem, 0.24vw + 0.72rem, 0.92rem);
                font-weight: 700;
                line-height: 1.15;
            }
            .display-panel-stack .panel-time-duration {
                font-size: clamp(0.98rem, 0.56vw + 0.84rem, 1.45rem);
                font-weight: 700;
                line-height: 1.08;
                overflow-wrap: anywhere;
            }
            .display-panel-stack .panel-time-date {
                font-size: clamp(0.82rem, 0.22vw + 0.74rem, 0.96rem);
                font-weight: 600;
                line-height: 1.15;
                overflow-wrap: anywhere;
            }
            @media (max-width: 1450px) {
                :root {
                    --display-panel-shared-height: min(80vh, 1040px);
                }
                .display-panel-stack .panel-time-grid {
                    grid-template-columns: 1fr;
                    gap: 0.55rem;
                }
                .display-panel-stack .panel-card-emphasis {
                    flex: 2.2 1 0;
                }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    operator_count_key = "display_panel_operator_count"
    if layout != "tv":
        operator_count = int(
            st.number_input(
                "Numero de operadores no processo",
                min_value=1,
                max_value=20,
                value=int(st.session_state.get(operator_count_key, 1) or 1),
                step=1,
                key=operator_count_key,
            )
        )
    else:
        operator_count = int(st.session_state.get(operator_count_key, 1) or 1)

    summary = compute_display_panel_summary(
        df,
        filter_context,
        operator_count=operator_count,
        display_selected_override=display_selected_override,
        numero_selected_override=numero_selected_override,
    )
    display_selected = summary.display_selected

    if summary.planilha_warning:
        st.warning(summary.planilha_warning)

    total_lote_text = (
        format_int(summary.target_total)
        if summary.target_total is not None
        else "Sem meta"
    )

    remaining_text = "Sem meta"
    remaining_sub = None
    if summary.remaining is not None:
        remaining_text = (
            "Concluido"
            if summary.remaining <= 0
            else format_int(summary.remaining)
        )
    if summary.qnt_planilha is not None:
        remaining_sub = f"QNT planilha: {format_int(summary.qnt_planilha)}"

    tempo_value = "Sem meta"
    tempo_subtitle = None
    if summary.remaining is not None:
        if summary.remaining <= 0:
            tempo_value = "Concluido"
        elif summary.time_estimate is not None:
            tempo_subtitle = summary.time_estimate.subtitle
            tempo_value = build_time_estimate_html(
                summary.time_estimate.best_hours,
                summary.time_estimate.avg_hours,
                summary.time_estimate.worst_hours,
                summary.time_estimate.best_finish,
                summary.time_estimate.avg_finish,
                summary.time_estimate.worst_finish,
            )

    col_img, col_info = st.columns([3, 2])
    with col_img:
        images_dir = Path(__file__).resolve().parent.parent / "FOTOS DISPLAY"
        image_map = build_display_image_map(images_dir)
        if display_selected:
            key = normalize_display_name(display_selected[0])
            image_path = image_map.get(key)
            if image_path:
                if layout == "tv":
                    st.image(str(image_path), width="stretch")
                else:
                    image_uri = load_image_as_data_uri(image_path)
                    if image_uri:
                        st.markdown(
                            f"""
                            <div class="display-photo-shell">
                                <img src="{image_uri}" alt="Imagem do display">
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    else:
                        st.info("Imagem do display nao encontrada.")
            else:
                st.info("Imagem do display nao encontrada.")
        else:
            st.info("Selecione um display para ver a imagem.")

    with col_info:
        cards_html: list[str] = []
        if summary.planilha_name:
            st.caption(f"Planilha vinculada: {summary.planilha_name}")
        if layout == "tv":
            left_col, right_col = st.columns(2)
            with left_col:
                render_panel_card("DISPLAYS", summary.lote_text)
                render_panel_card("Total do lote", total_lote_text)
                render_panel_card("A produzir", remaining_text, remaining_sub)
            with right_col:
                render_panel_card("Total produzido", format_int(summary.total_produzido))
                render_panel_card("Tempo restante", tempo_value)
                render_panel_card("Registros", format_int(summary.registros))
        else:
            cards_html.extend(
                [
                    build_panel_card_html("DISPLAYS", summary.lote_text),
                    build_panel_card_html("Total do lote", total_lote_text),
                    build_panel_card_html(
                        "Total produzido",
                        format_int(summary.total_produzido),
                    ),
                    build_panel_card_html(
                        "A produzir",
                        remaining_text,
                        remaining_sub,
                        card_class="panel-card-a-produzir",
                    ),
                    build_panel_card_html(
                        "Tempo restante",
                        tempo_value,
                        tempo_subtitle,
                        card_class="panel-card-emphasis",
                        value_is_html=True,
                    ),
                    build_panel_card_html(
                        "Registros",
                        format_int(summary.registros),
                        card_class="panel-card-compact",
                    ),
                ]
            )

        if summary.operator_comparison is not None:
            comparison = summary.operator_comparison
            subtitle = (
                f"{format_percent(comparison.percent, 1)} do total"
                if comparison.percent is not None
                else None
            )
            if layout == "tv":
                render_panel_card(
                    f"Operador: {comparison.label}",
                    format_int(comparison.operator_total),
                    subtitle,
                )
            else:
                cards_html.append(
                    build_panel_card_html(
                        f"Operador: {comparison.label}",
                        format_int(comparison.operator_total),
                        subtitle,
                    )
                )

            ratio_text = (
                format_percent(comparison.ratio, 0)
                if comparison.ratio is not None
                else "N/A"
            )
            subtitle_rate = (
                "Operador: "
                f"{format_float(comparison.rate_operator)}"
                f" | Tempo: {format_duration(comparison.operator_hours)}"
                " | Processo: "
                f"{format_float(comparison.rate_process)}"
                f" | Tempo: {format_duration(comparison.process_hours)}"
                if comparison.rate_operator is not None
                or comparison.rate_process is not None
                or comparison.operator_hours
                or comparison.process_hours
                else None
            )
            if layout == "tv":
                render_panel_card("Media do operador vs processo", ratio_text, subtitle_rate)
            else:
                cards_html.append(
                    build_panel_card_html(
                        "Media do operador vs processo",
                        ratio_text,
                        subtitle_rate,
                    )
                )

        if layout != "tv":
            st.markdown(
                f'<div class="display-panel-stack">{"".join(cards_html)}</div>',
                unsafe_allow_html=True,
            )


def render_tv_panel(df: pd.DataFrame, filter_context: FilterContext) -> None:
    st.markdown(
        """
        <style>
        section.main > div:first-child {
            padding: 8px 10px;
        }
        .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
        }
        .stApp h1 {
            display: none;
        }
        .panel-card {
            padding: 10px 12px;
            margin-bottom: 8px !important;
        }
        .panel-title {
            font-size: 0.7rem;
        }
        .panel-value {
            font-size: 1.35rem;
            margin-top: 4px;
        }
        .panel-sub {
            font-size: 0.8rem;
        }
        .kpi-card {
            padding: 10px 12px;
        }
        .kpi-title {
            font-size: 0.75rem;
        }
        .kpi-value {
            font-size: 1.6rem;
        }
        .stImage img {
            max-height: 62vh;
            object-fit: contain;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    if df.empty:
        st.info("Nenhum dado apos os filtros.")
        return

    display_selected = filter_context.display_selected
    numero_selected = filter_context.numero_display_selected
    if not display_selected or not numero_selected:
        st.info("Selecione o Display/Peca e o Numero display no filtro lateral.")
        return

    combo_cols = [c for c in ["display", "numero_display", "maquinario", "processo"] if c in df.columns]
    combos_df = df[combo_cols].dropna().drop_duplicates()
    sort_cols = [c for c in ["display", "numero_display", "maquinario", "processo"] if c in combos_df.columns]
    if sort_cols:
        combos_df = combos_df.sort_values(sort_cols)
    combos = list(combos_df.itertuples(index=False, name=None))
    if not combos:
        st.info("Sem dados de maquinario/processo para exibir.")
        return

    with st.sidebar:
        st.header("Painel TV")
        auto_rotate = st.checkbox("Rotacao automatica", value=True, key="tv_auto")
        interval = st.number_input(
            "Intervalo (seg)",
            min_value=3,
            max_value=60,
            value=8,
            step=1,
            key="tv_interval",
        )
        labels = [" | ".join(str(val) for val in combo) for combo in combos]
        manual_label = None
        if not auto_rotate:
            manual_label = st.selectbox(
                "Maquinario / Processo",
                labels,
                index=0,
                key="tv_combo_manual",
            )

    index = st.session_state.get("tv_index", 0) % len(combos)
    if not auto_rotate and manual_label is not None:
        try:
            index = labels.index(manual_label)
        except ValueError:
            index = 0

    combo = combos[index]
    display_val = combo[combo_cols.index("display")] if "display" in combo_cols else None
    numero_val = combo[combo_cols.index("numero_display")] if "numero_display" in combo_cols else None
    maquinario = combo[combo_cols.index("maquinario")] if "maquinario" in combo_cols else None
    processo = combo[combo_cols.index("processo")] if "processo" in combo_cols else None

    heading_parts = []
    if display_val is not None:
        heading_parts.append(f"Display: {display_val}")
    if numero_val is not None:
        heading_parts.append(f"Numero: {numero_val}")
    if maquinario is not None:
        heading_parts.append(f"Maquinario: {maquinario}")
    if processo is not None:
        heading_parts.append(f"Processo: {processo}")
    if heading_parts:
        st.markdown("### " + " | ".join(heading_parts))

    df_cycle = df
    if display_val is not None and "display" in df_cycle:
        df_cycle = df_cycle[df_cycle["display"] == display_val]
    if numero_val is not None and "numero_display" in df_cycle:
        df_cycle = df_cycle[df_cycle["numero_display"] == numero_val]
    if maquinario is not None and "maquinario" in df_cycle:
        df_cycle = df_cycle[df_cycle["maquinario"] == maquinario]
    if processo is not None and "processo" in df_cycle:
        df_cycle = df_cycle[df_cycle["processo"] == processo]

    base_no_operator_cycle = filter_context.filtered_no_operator
    if not base_no_operator_cycle.empty:
        if display_val is not None and "display" in base_no_operator_cycle:
            base_no_operator_cycle = base_no_operator_cycle[
                base_no_operator_cycle["display"] == display_val
            ]
        if numero_val is not None and "numero_display" in base_no_operator_cycle:
            base_no_operator_cycle = base_no_operator_cycle[
                base_no_operator_cycle["numero_display"] == numero_val
            ]
        if maquinario is not None and "maquinario" in base_no_operator_cycle:
            base_no_operator_cycle = base_no_operator_cycle[
                base_no_operator_cycle["maquinario"] == maquinario
            ]
        if processo is not None and "processo" in base_no_operator_cycle:
            base_no_operator_cycle = base_no_operator_cycle[
                base_no_operator_cycle["processo"] == processo
            ]
    else:
        base_no_operator_cycle = df_cycle

    display_override = [str(display_val)] if display_val is not None else None
    numero_override = [str(numero_val)] if numero_val is not None else None
    cycle_context = filter_context.with_overrides(
        display_selected=display_override or [],
        numero_display_selected=numero_override or [],
        maquinario_selected=[str(maquinario)] if maquinario is not None else [],
        processo_selected=[str(processo)] if processo is not None else [],
        filtered_no_operator=base_no_operator_cycle,
    )
    render_display_panel(
        df_cycle,
        cycle_context,
        display_selected_override=display_override,
        numero_selected_override=numero_override,
        layout="tv",
    )
    render_prod_hora_kpis(df_cycle, show_info=False)

    if auto_rotate and len(combos) > 1:
        st.session_state["tv_index"] = (index + 1) % len(combos)
        time.sleep(int(interval))
        st.rerun()
