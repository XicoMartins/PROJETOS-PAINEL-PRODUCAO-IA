from __future__ import annotations

import math
import unicodedata
from dataclasses import replace
from decimal import Decimal, InvalidOperation

import psycopg
import streamlit as st

from data_loader import get_database_url
from weekly_report import ALL_PROJECTS, select_projects
from weekly_report_data import emit_report
from weekly_control import (
    ComponentRequirement, build_weekly_control,
    component_key as weekly_component_key,
    project_key, validate_target_submission, weekly_periods,
)
from weekly_control_data import (
    ProjectIdentityConflictError, WeeklySourceData, list_painting_projects,
    load_weekly_source, save_component_requirements, save_weekly_target,
)
from weekly_control_view import render_weekly_control_html, render_weekly_empty_html


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    return "".join(char for char in text if unicodedata.category(char) != "Mn").strip().upper()


def database_url() -> str:
    return get_database_url() or ""
@st.cache_data(ttl=55, show_spinner=False)
def load_weekly_projects_cached(db_url: str):
    return list_painting_projects(db_url)


@st.cache_data(ttl=55, show_spinner=False)
def load_weekly_source_cached(db_url, identity, previous_period, current_period):
    return load_weekly_source(db_url, identity, previous_period, current_period)


def weekly_control_panel() -> None:
    try:
        db_url = database_url()
        projects = load_weekly_projects_cached(db_url)
        if not projects:
            st.markdown(
                render_weekly_empty_html(
                    "Nenhum projeto de pintura encontrado",
                    "A conexão funcionou, mas painting_entries não possui identidades completas.",
                ),
                unsafe_allow_html=True,
            )
            return

        by_key = {project.key: project for project in projects}
        selected_keys = st.multiselect(
            "Projetos analisados",
            options=(ALL_PROJECTS, *by_key),
            default=[projects[0].key],
            format_func=lambda key: "Todos os projetos" if key == ALL_PROJECTS else by_key[key].label,
            key="weekly_control_projects",
            placeholder="Pesquise cliente, display, número ou código",
        )
        selected_projects = select_projects(projects, selected_keys)
        current_period, following_period = weekly_periods()
        if not selected_projects:
            st.info("Selecione um projeto ou Todos os projetos. Pesquise pelo cliente, display, número ou código.")
            return
        render_weekly_report_controls(db_url, selected_projects, current_period, following_period)
        for selected in selected_projects:
            source = load_weekly_source_cached(
                db_url,
                selected.identity,
                current_period,
                following_period,
            )
            requirements = _complete_detected_requirements(source)
            control = build_weekly_control(
                source.previous_target,
                source.current_target,
                requirements,
                source.entries,
            )
            warnings = list(source.warnings)
            if not source.entries:
                warnings.append("Nenhum movimento reconhecido para o projeto selecionado.")
            if source.previous_target is None:
                warnings.append("Meta acumulada da semana atual não cadastrada.")
            if source.current_target is None:
                warnings.append("Meta acumulada da próxima semana não cadastrada.")
            warnings.extend(
                f"Quantidade por conjunto ausente: {requirement.display_name}."
                for requirement in requirements
                if requirement.active and requirement.quantity_per_set is None
            )
            control = replace(control, warnings=tuple(dict.fromkeys(warnings)))
            st.markdown(
                render_weekly_control_html(
                    selected.identity,
                    current_period,
                    following_period,
                    control,
                    source.updated_at,
                ),
                unsafe_allow_html=True,
            )
            render_target_editor(db_url, selected.identity, following_period, source)
            render_requirement_editor(db_url, selected.identity, requirements)
    except ProjectIdentityConflictError:
        st.markdown(
            render_weekly_empty_html(
                "Identidades de projeto conflitantes",
                "Padronize cliente, display, número e código de pintura na painting_entries.",
            ),
            unsafe_allow_html=True,
        )
    except psycopg.errors.UndefinedTable:
        st.markdown(
            render_weekly_empty_html(
                "Estrutura semanal ainda não configurada",
                "A migration das metas e requisitos precisa ser aplicada no Supabase.",
            ),
            unsafe_allow_html=True,
        )
    except Exception:
        st.markdown(
            render_weekly_empty_html(
                "Não foi possível carregar o controle semanal",
                "Tente novamente em alguns instantes.",
            ),
            unsafe_allow_html=True,
        )


def render_weekly_report_controls(db_url, projects, previous_period, current_period):
    selection=tuple(sorted(project.key for project in projects))
    st.caption("A emissão é registrada ao gerar o PDF. A primeira emissão é geral; as próximas incluem os itens alterados com seus totais acumulados. Baixar novamente reutiliza o arquivo gerado.")
    if projects and st.button("Gerar relatório PDF", key="weekly_report_generate"):
        try:
            pdf=emit_report(db_url,tuple(project.identity for project in projects),previous_period,current_period)
            if pdf is None:
                st.info("Sem alterações desde o último relatório")
            else:
                st.session_state["weekly_report_artifact"]={"selection":selection,"data":pdf}
        except psycopg.errors.UndefinedTable:
            st.error("Estrutura de relatórios ainda não configurada. Aplique a migração de relatórios.")
        except Exception:
            st.error("Não foi possível gerar o relatório. Tente novamente; a referência anterior foi preservada.")
    artifact=st.session_state.get("weekly_report_artifact")
    if artifact and artifact["selection"] == selection:
        st.download_button("Baixar PDF",data=artifact["data"],file_name="relatorio_semanal_pintura.pdf",mime="application/pdf",key="weekly_report_download")


def _complete_detected_requirements(
    source: WeeklySourceData,
) -> tuple[ComponentRequirement, ...]:
    requirements = list(source.requirements)
    known = {normalize(item.source_component_key) for item in requirements}
    used_orders = {item.display_order for item in requirements}
    next_order = 0
    for detected_key in source.detected_component_keys:
        if normalize(detected_key) in known:
            continue
        while next_order in used_orders:
            next_order += 1
        requirements.append(
            ComponentRequirement(
                source_component_key=detected_key,
                display_name=detected_key,
                quantity_per_set=None,
                display_order=next_order,
                active=True,
            )
        )
        used_orders.add(next_order)
        next_order += 1
    return tuple(sorted(requirements, key=lambda item: item.display_order))


def render_target_editor(db_url, identity, current_period, source) -> None:
    with st.expander("Editar meta acumulada da semana", expanded=False):
        st.caption(
            "Informe o total acumulado previsto até a sexta-feira da semana escolhida. "
            "Exemplo: 167 por semana resulta em 334 na segunda semana e 501 na terceira."
        )
        with st.form(f"weekly_target_form_{project_key(identity)}"):
            selected_day = st.date_input(
                "Semana da meta",
                value=current_period.end,
                format="DD/MM/YYYY",
                key=f"weekly_target_day_{project_key(identity)}",
            )
            target_sets = st.number_input(
                "Meta acumulada em conjuntos",
                min_value=0,
                step=1,
                value=int(source.current_target or 0),
                key=f"weekly_target_value_{project_key(identity)}",
            )
            confirmed = st.checkbox(
                "Confirmo a gravação desta meta acumulada",
                key=f"weekly_target_confirm_{project_key(identity)}",
            )
            submitted = st.form_submit_button("Salvar meta acumulada")
        if not submitted:
            return
        try:
            period, validated_target = validate_target_submission(
                selected_day,
                int(target_sets),
                confirmed,
            )
            save_weekly_target(db_url, identity, period, validated_target)
        except ValueError as exc:
            st.warning(str(exc))
            return
        except Exception:
            st.error("Não foi possível salvar a meta. Tente novamente.")
            return
        load_weekly_source_cached.clear()
        st.success(
            f"Meta acumulada de {validated_target} conjuntos salva para "
            f"{period.start.strftime('%d/%m')} a {period.end.strftime('%d/%m/%Y')}."
        )
        st.rerun()


def render_requirement_editor(db_url, identity, requirements) -> None:
    records = [
        {
            "Ativo": requirement.active,
            "Componente na base": requirement.source_component_key,
            "Nome exibido": requirement.display_name,
            "Qtd. por conjunto": (
                float(requirement.quantity_per_set)
                if requirement.quantity_per_set is not None
                else None
            ),
            "Ordem": requirement.display_order,
        }
        for requirement in requirements
    ]
    with st.expander("Configurar componentes do projeto", expanded=False):
        st.caption(
            "Os componentes detectados em painting_entries aparecem automaticamente. "
            "Preencha a quantidade por conjunto, ajuste os nomes e adicione linhas quando necessário."
        )
        with st.form(f"weekly_requirements_form_{project_key(identity)}"):
            edited = st.data_editor(
                records,
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                key=f"weekly_requirements_editor_{project_key(identity)}",
                column_config={
                    "Ativo": st.column_config.CheckboxColumn("Ativo"),
                    "Componente na base": st.column_config.TextColumn(
                        "Componente na base",
                        help="Nome normalizado que será relacionado ao processo de pintura.",
                    ),
                    "Nome exibido": st.column_config.TextColumn("Nome exibido"),
                    "Qtd. por conjunto": st.column_config.NumberColumn(
                        "Qtd. por conjunto",
                        min_value=0.001,
                        step=1.0,
                    ),
                    "Ordem": st.column_config.NumberColumn(
                        "Ordem",
                        min_value=0,
                        step=1,
                    ),
                },
            )
            confirmed = st.checkbox(
                "Confirmo a gravação destes requisitos",
                key=f"weekly_requirements_confirm_{project_key(identity)}",
            )
            submitted = st.form_submit_button("Salvar componentes")
        if not submitted:
            return
        if not confirmed:
            st.warning("Confirme a gravação dos requisitos.")
            return
        try:
            rows = edited.to_dict("records") if hasattr(edited, "to_dict") else edited
            parsed: list[ComponentRequirement] = []
            for row in rows:
                raw_quantity = row.get("Qtd. por conjunto")
                quantity = None
                if raw_quantity not in (None, "") and not (
                    isinstance(raw_quantity, float) and math.isnan(raw_quantity)
                ):
                    quantity = Decimal(str(raw_quantity))
                raw_order = row.get("Ordem")
                if raw_order in (None, ""):
                    raise ValueError("Todas as linhas precisam de uma ordem de exibição.")
                parsed.append(
                    ComponentRequirement(
                        source_component_key=weekly_component_key(
                            row.get("Componente na base")
                        ),
                        display_name=str(row.get("Nome exibido") or "").strip(),
                        quantity_per_set=quantity,
                        display_order=int(raw_order),
                        active=bool(row.get("Ativo", True)),
                    )
                )
            save_component_requirements(db_url, identity, tuple(parsed))
        except (ValueError, InvalidOperation) as exc:
            st.warning(str(exc))
            return
        except Exception:
            st.error("Não foi possível salvar os componentes. Tente novamente.")
            return
        load_weekly_source_cached.clear()
        st.success("Componentes do projeto salvos.")
        st.rerun()


def render_weekly_control() -> None:
    """Render weekly controls only after the host application authenticates."""
    with st.container(key="weekly_control_host"):
        st.markdown(WEEKLY_HOST_CSS, unsafe_allow_html=True)
        weekly_control_panel()


WEEKLY_HOST_CSS = """
<style>
.st-key-weekly_control_host { color: #f4f4f4; }
.st-key-weekly_control_host [data-testid="stWidgetLabel"],
.st-key-weekly_control_host [data-testid="stCaptionContainer"],
.st-key-weekly_control_host [data-testid="stExpander"] summary { color: #f4f4f4 !important; }
.st-key-weekly_control_host .weekly-control p { color: inherit; }
.st-key-weekly_control_host .weekly-control .weekly-period { color: #51565a; }
</style>
"""
