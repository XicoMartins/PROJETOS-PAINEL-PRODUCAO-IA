from __future__ import annotations

import hashlib
import hmac
import os
import secrets as secrets_lib

import streamlit as st

from branding import apply_branding
from data_loader import load_data, load_painting_data
from filters import FilterContext, apply_filters
from painting_filters import apply_painting_filters
from panel_views import (
    render_charts,
    render_data_quality,
    render_display_panel,
    render_filtered_table,
    render_kpis,
    render_painting_shipments,
    render_production_dashboard,
    render_tv_panel,
)

APP_VERSION = "13.2.0"
AUTH_SESSION_KEY = "auth_authenticated"
AUTH_USER_KEY = "auth_user"


def build_password_hash(password: str, salt: str | None = None, iterations: int = 260000) -> str:
    salt = salt or secrets_lib.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password: str, stored_password: str) -> bool:
    stored_password = str(stored_password or "")
    if stored_password.startswith("pbkdf2_sha256$"):
        try:
            _algorithm, iterations, salt, expected = stored_password.split("$", 3)
            candidate = build_password_hash(password, salt=salt, iterations=int(iterations))
            candidate_hash = candidate.rsplit("$", 1)[-1]
        except (TypeError, ValueError):
            return False
        return hmac.compare_digest(candidate_hash, expected)
    return hmac.compare_digest(password, stored_password)


def _get_auth_secret(key: str):
    try:
        auth_config = st.secrets.get("auth", {})
        if key in auth_config:
            return auth_config.get(key)
    except Exception:
        pass
    return os.getenv(f"AUTH_{key.upper()}")


def get_auth_users() -> dict[str, str]:
    users = {}
    try:
        auth_config = st.secrets.get("auth", {})
        configured_users = auth_config.get("users", {})
        if hasattr(configured_users, "items"):
            users.update({str(user): str(password) for user, password in configured_users.items()})
    except Exception:
        pass

    username = _get_auth_secret("username")
    password_hash = _get_auth_secret("password_hash")
    password = _get_auth_secret("password")
    if username and (password_hash or password):
        users[str(username)] = str(password_hash or password)

    return users


def render_login_screen(users: dict[str, str]) -> None:
    st.markdown('<div class="panel-card">', unsafe_allow_html=True)
    st.markdown("### Acesso restrito")

    if not users:
        st.error("Login nao configurado. Configure usuario e senha nos Secrets do Streamlit Cloud.")
        st.code(
            '[auth.users]\n'
            'admin = "pbkdf2_sha256$260000$..."',
            language="toml",
        )
        st.markdown("</div>", unsafe_allow_html=True)
        return

    with st.form("login_form"):
        username = st.text_input("Usuario")
        password = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar")

    if entrar:
        stored_password = users.get(username)
        if stored_password and verify_password(password, stored_password):
            st.session_state[AUTH_SESSION_KEY] = True
            st.session_state[AUTH_USER_KEY] = username
            st.rerun()
        else:
            st.error("Usuario ou senha invalidos.")

    st.markdown("</div>", unsafe_allow_html=True)


def require_authentication() -> None:
    if st.session_state.get(AUTH_SESSION_KEY):
        return
    render_login_screen(get_auth_users())
    st.stop()


def render_logout_control() -> None:
    user = st.session_state.get(AUTH_USER_KEY, "")
    if user:
        st.caption(f"Usuario: {user}")
    if st.button("Sair"):
        st.session_state.pop(AUTH_SESSION_KEY, None)
        st.session_state.pop(AUTH_USER_KEY, None)
        st.rerun()


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
    require_authentication()

    data_sources = {
        "FORMS-MTECH (PostgreSQL)": "forms_postgres",
    }
    nav_tabs = [
        "Geral",
        "Painel Display",
        "Registros",
        "Integridade",
        "Painel TV",
        "Remessas pintura",
        "Painel de Produção",
    ]
    if st.session_state.get("dashboard_sidebar_tab") == "Gráficos":
        st.session_state["dashboard_sidebar_tab"] = "Painel Display"
        st.session_state["display_panel_subtab"] = "Gráficos"
    if st.session_state.get("dashboard_sidebar_tab") not in [None, *nav_tabs]:
        st.session_state["dashboard_sidebar_tab"] = "Geral"

    with st.sidebar:
        render_logout_control()
        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
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

    if selected_tab == "Remessas pintura":
        df, latest, quality = load_painting_data()
    else:
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
        "Registros",
        "Remessas pintura",
        "Painel TV",
        "Painel de Produção",
    }
    if selected_tab in tabs_with_filters:
        with st.sidebar:
            st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
            st.caption(f"Fonte em uso: {latest.name}")
        period_mode = "month" if selected_tab == "Painel de Produção" else "date"
        if selected_tab == "Remessas pintura":
            filtered = apply_painting_filters(df)
            filter_context = _build_unfiltered_context(filtered)
        else:
            filtered, filter_context = apply_filters(df, period_mode=period_mode)
    else:
        filtered = df
        filter_context = _build_unfiltered_context(df)

    if selected_tab == "Geral":
        _render_section_title("Visão Geral de Negócios")
        _render_data_status(selected_label, latest, quality)
        render_kpis(filtered, filter_context)
    elif selected_tab == "Painel Display":
        _render_section_title("Painel Display")
        selected_display_subtab = st.radio(
            "Subtópicos do Painel Display",
            ["Painel", "Gráficos"],
            horizontal=True,
            key="display_panel_subtab",
        )
        if selected_display_subtab == "Painel":
            render_display_panel(filtered, filter_context)
        else:
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
        render_production_dashboard(filtered, reference_df=df)
    elif selected_tab == "Remessas pintura":
        render_painting_shipments(filtered)


if __name__ == "__main__":
    main()
