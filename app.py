from __future__ import annotations

import streamlit as st

from branding import apply_branding
from data_loader import load_data
from filters import FilterContext, apply_filters
from panel_views import (
    render_charts,
    render_data_quality,
    render_display_panel,
    render_filtered_table,
    render_kpis,
    render_production_dashboard,
    render_tv_panel,
)

APP_VERSION = "13.1.0"


def _render_dashboard_title() -> None:
    st.markdown(
        f"""
        <div class="dashboard-heading">
            <h1>Dashboard MTECH Displays</h1>
            <div class="dashboard-version">Versão {APP_VERSION}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_data_source_picker(data_sources: dict[str, str]) -> str:
    options = list(data_sources.keys())
    selected_label = st.session_state.get("data_source_label", options[0])
    if selected_label not in data_sources:
        selected_label = options[0]
    return st.selectbox(
        "Fonte dos dados",
        options,
        index=options.index(selected_label),
        key="data_source_label",
        disabled=len(options) == 1,
    )


def _render_data_status(selected_source_label: str, latest, quality: dict) -> None:
    with st.expander("Status das Bases de Dados (Verificar Atualizações)"):
        st.write(f"Fonte selecionada: {selected_source_label}")
        if latest is not None:
            st.write(f"Arquivo/base em uso: {latest.name}")
        warnings = quality.get("warnings", []) if quality else []
        if warnings:
            for warning in warnings:
                st.warning(warning)
        else:
            st.success("Bases carregadas sem avisos críticos.")


def _render_section_title(title: str) -> None:
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown(f"## {title}")


def _build_unfiltered_context(df) -> FilterContext:
    return FilterContext(filtered_no_operator=df.copy())


def main() -> None:
    st.set_page_config(
        "Dashboard MTECH Displays",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_branding(show_header=False, use_background=False)

    data_sources = {
        "FORMS-MTECH (PostgreSQL)": "forms_postgres",
    }
    nav_tabs = [
        "Geral",
        "Painel Display",
        "Gráficos",
        "Registros",
        "Integridade",
        "Painel TV",
        "Painel de Produção",
    ]
    if st.session_state.get("dashboard_sidebar_tab") not in [None, *nav_tabs]:
        st.session_state["dashboard_sidebar_tab"] = "Geral"

    with st.sidebar:
        st.markdown('<div class="sidebar-nav-spacer"></div>', unsafe_allow_html=True)
        selected_tab = st.radio(
            "Navegação",
            nav_tabs,
            index=0,
            key="dashboard_sidebar_tab",
            label_visibility="collapsed",
        )

    _render_dashboard_title()

    if selected_tab == "Geral":
        selected_label = _render_data_source_picker(data_sources)
    else:
        selected_label = st.session_state.get(
            "data_source_label",
            list(data_sources.keys())[0],
        )
        if selected_label not in data_sources:
            selected_label = list(data_sources.keys())[0]
    selected_source = data_sources[selected_label]

    df, latest, quality = load_data(selected_source)
    if latest is None:
        source_warning = quality.get("warnings", [])
        if source_warning:
            st.error(source_warning[0])
        elif selected_source == "forms":
            st.error("Nenhum arquivo CSV encontrado na pasta 'BASE DE DADOS FORMS'.")
        elif selected_source == "forms_postgres":
            st.error("Banco PostgreSQL nao configurado ou indisponivel.")
        elif selected_source == "sqlite":
            st.error("Banco SQLite nao encontrado ou sem acesso na pasta do backend.")
        else:
            st.error("Nenhum arquivo CSV encontrado na pasta de saida.")
        st.stop()

    tabs_with_filters = {
        "Painel Display",
        "Gráficos",
        "Registros",
        "Painel TV",
        "Painel de Produção",
    }
    if selected_tab in tabs_with_filters:
        with st.sidebar:
            st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
            st.caption(f"Fonte em uso: {latest.name}")
        filtered, filter_context = apply_filters(df)
    else:
        filtered = df
        filter_context = _build_unfiltered_context(df)

    if selected_tab == "Geral":
        _render_section_title("Visão Geral de Negócios")
        _render_data_status(selected_label, latest, quality)
        render_kpis(filtered, filter_context)
    elif selected_tab == "Painel Display":
        _render_section_title("Painel Display")
        render_display_panel(filtered, filter_context)
    elif selected_tab == "Gráficos":
        _render_section_title("Gráficos")
        render_charts(filtered, filter_context)
    elif selected_tab == "Registros":
        _render_section_title("Registros")
        render_filtered_table(filtered, filter_context)
    elif selected_tab == "Integridade":
        _render_section_title("Integridade dos Dados")
        render_data_quality(df, quality)
    elif selected_tab == "Painel TV":
        _render_section_title("Painel TV")
        render_tv_panel(filtered, filter_context)
    elif selected_tab == "Painel de Produção":
        _render_section_title("Painel de Produção")
        render_production_dashboard(filtered)


if __name__ == "__main__":
    main()
