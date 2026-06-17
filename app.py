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


def main() -> None:
    st.set_page_config("Painel de Producao IA", layout="wide")
    apply_branding()
    st.title("Painel de Producao IA")

    data_sources = {
        "FORMS-MTECH (PostgreSQL)": "forms_postgres",
        "BASE DE DADOS FORMS (CSV legado)": "forms",
        "BASE ATUAL (registros.csv legado)": "base_atual",
        "BASE SQLITE legado (db.sqlite3)": "sqlite",
    }
    with st.sidebar:
        st.header("Fonte dos dados")
        selected_label = st.selectbox("Base de dados", list(data_sources.keys()))
        st.header("Visualizacao")
        view_mode = st.radio(
            "Modo",
            ["Painel completo", "Painel TV", "Painel de producao"],
            index=0,
            key="view_mode",
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
    if view_mode == "Painel TV":
        render_tv_panel(filtered, filter_context)
    elif view_mode == "Painel de producao":
        render_production_dashboard(filtered)
    else:
        render_kpis(filtered, filter_context)
        render_display_panel(filtered, filter_context)
        render_charts(filtered, filter_context)
        render_filtered_table(filtered, filter_context)
        render_data_quality(df, quality)


if __name__ == "__main__":
    main()
