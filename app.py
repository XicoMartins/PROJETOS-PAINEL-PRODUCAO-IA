from __future__ import annotations

import streamlit as st

from branding import apply_branding
from data_loader import load_data
from filters import apply_filters
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


def _render_dashboard_header(selected_source_label: str, latest, quality: dict) -> None:
    st.markdown(
        f"""
        <div class="dashboard-heading">
            <h1>Dashboard Konica Minolta</h1>
            <div class="dashboard-version">Versão {APP_VERSION}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
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


def _render_placeholder(title: str, description: str) -> None:
    st.info(f"{title}: {description}")


def main() -> None:
    st.set_page_config(
        "Dashboard Konica Minolta",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_branding(show_header=False, use_background=False)

    data_sources = {
        "FORMS-MTECH (PostgreSQL)": "forms_postgres",
        "BASE DE DADOS FORMS (CSV legado)": "forms",
        "BASE ATUAL (registros.csv legado)": "base_atual",
        "BASE SQLITE legado (db.sqlite3)": "sqlite",
    }
    nav_tabs = [
        "Geral",
        "Saídas",
        "Estoque",
        "Pendências",
        "Follow-Up",
        "Análise Crítica",
        "Forecast",
        "MIF Analytics",
        "Metodologia",
    ]
    with st.sidebar:
        st.markdown('<div class="sidebar-nav-spacer"></div>', unsafe_allow_html=True)
        selected_tab = st.radio(
            "Navegação",
            nav_tabs,
            index=0,
            key="dashboard_sidebar_tab",
            label_visibility="collapsed",
        )
        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
        st.caption("Fonte dos dados")
        selected_label = st.selectbox(
            "Base de dados",
            list(data_sources.keys()),
            label_visibility="collapsed",
        )
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
    with st.sidebar:
        st.caption(f"Fonte em uso: {latest.name}")

    filtered, filter_context = apply_filters(df)

    _render_dashboard_header(selected_label, latest, quality)

    if selected_tab == "Geral":
        _render_section_title("Visão Geral de Negócios")
        render_kpis(filtered, filter_context)
        render_display_panel(filtered, filter_context)
    elif selected_tab == "Saídas":
        _render_section_title("Saídas")
        render_production_dashboard(filtered)
    elif selected_tab == "Estoque":
        _render_section_title("Estoque")
        render_filtered_table(filtered, filter_context)
    elif selected_tab == "Pendências":
        _render_section_title("Pendências")
        render_data_quality(df, quality)
    elif selected_tab == "Follow-Up":
        _render_section_title("Follow-Up")
        render_tv_panel(filtered, filter_context)
    elif selected_tab == "Análise Crítica":
        _render_section_title("Análise Crítica")
        render_charts(filtered, filter_context)
    elif selected_tab == "Forecast":
        _render_section_title("Forecast")
        render_charts(filtered, filter_context)
    elif selected_tab == "MIF Analytics":
        _render_section_title("MIF Analytics")
        render_production_dashboard(filtered)
    else:
        _render_section_title("Metodologia")
        _render_placeholder(
            "Metodologia",
            "documente aqui os critérios de cálculo, atualização e governança do painel.",
        )


if __name__ == "__main__":
    main()
