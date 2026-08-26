import unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import psycopg
import streamlit_app
from weekly_control import (
    ComponentRequirement,
    MovementEntry,
    ProjectIdentity,
    WeekPeriod,
    project_key,
)
from weekly_control_data import ProjectIdentityConflictError, ProjectOption, WeeklySourceData


class WeeklyNavigationTest(unittest.TestCase):
    def test_main_renders_managerial_and_weekly_tabs(self):
        managerial_tab = MagicMock()
        weekly_tab = MagicMock()
        with (
            patch.object(
                streamlit_app.st,
                "tabs",
                return_value=(managerial_tab, weekly_tab),
            ) as tabs,
            patch.object(streamlit_app, "dashboard_fragment") as dashboard,
            patch.object(
                streamlit_app,
                "weekly_control_panel",
                create=True,
            ) as weekly,
            patch.object(streamlit_app.st, "markdown"),
        ):
            streamlit_app.main()

        tabs.assert_called_once_with(["Visão gerencial", "Controle semanal"])
        dashboard.assert_called_once_with()
        weekly.assert_called_once_with()

    def test_main_injects_readable_active_and_inactive_tab_styles(self):
        managerial_tab = MagicMock()
        weekly_tab = MagicMock()
        with (
            patch.object(
                streamlit_app.st,
                "tabs",
                return_value=(managerial_tab, weekly_tab),
            ),
            patch.object(streamlit_app, "dashboard_fragment"),
            patch.object(streamlit_app, "weekly_control_panel"),
            patch.object(streamlit_app.st, "markdown") as markdown,
        ):
            streamlit_app.main()

        rendered_css = markdown.call_args_list[0].args[0]
        self.assertIn(
            '[data-testid="stTab"] { color: var(--ink) !important;',
            rendered_css,
        )
        self.assertIn(
            '[data-testid="stTab"][aria-selected="true"] { color: var(--red) !important;',
            rendered_css,
        )


class WeeklyPanelStateTest(unittest.TestCase):
    def test_empty_project_catalog_has_an_explicit_state(self):
        with (
            patch.object(streamlit_app, "database_url", return_value="postgresql://database"),
            patch.object(
                streamlit_app,
                "load_weekly_projects_cached",
                return_value=(),
                create=True,
            ),
            patch.object(streamlit_app.st, "markdown") as markdown,
        ):
            streamlit_app.weekly_control_panel()

        rendered = markdown.call_args.args[0]
        self.assertIn("Nenhum projeto de pintura encontrado", rendered)

    def test_selected_project_builds_the_weekly_view_from_real_source_data(self):
        instant = datetime(2026, 8, 25, 12, tzinfo=ZoneInfo("America/Sao_Paulo"))
        identity = ProjectIdentity(
            "FEMSA",
            "PG + ECONOMIA HIBRIDO",
            "26081000",
            "VM - 1000",
        )
        option = ProjectOption(
            project_key(identity),
            identity,
            "FEMSA · PG + ECONOMIA HIBRIDO · Nº 26081000 · VM - 1000",
            instant,
        )
        source = WeeklySourceData(
            previous_target=334,
            current_target=501,
            requirements=(
                ComponentRequirement("CORPO", "CORPO", Decimal("1"), 1, True),
            ),
            entries=(
                MovementEntry("CORPO", "remessa", Decimal("463"), instant),
                MovementEntry("CORPO", "retorno", Decimal("317"), instant),
            ),
            detected_component_keys=("CORPO",),
            updated_at=instant,
            warnings=(),
        )

        with (
            patch.object(streamlit_app, "database_url", return_value="postgresql://database"),
            patch.object(streamlit_app, "load_weekly_projects_cached", return_value=(option,)),
            patch.object(
                streamlit_app,
                "load_weekly_source_cached",
                return_value=source,
                create=True,
            ),
            patch.object(streamlit_app.st, "selectbox", return_value=option.key),
            patch.object(streamlit_app, "render_target_editor", create=True),
            patch.object(streamlit_app, "render_requirement_editor", create=True),
            patch.object(streamlit_app.st, "markdown") as markdown,
        ):
            streamlit_app.weekly_control_panel()

        rendered_blocks = [call.args[0] for call in markdown.call_args_list]
        self.assertTrue(
            any("Controle semanal de remessas e retornos" in block for block in rendered_blocks)
        )
        self.assertTrue(any("PG + ECONOMIA HIBRIDO" in block for block in rendered_blocks))

    def test_project_without_recognized_movements_has_an_explicit_warning(self):
        instant = datetime(2026, 8, 25, 12, tzinfo=ZoneInfo("America/Sao_Paulo"))
        identity = ProjectIdentity("FEMSA", "DISPLAY", "1", "VM - 1000")
        option = ProjectOption(project_key(identity), identity, "FEMSA · DISPLAY", instant)
        source = WeeklySourceData(
            previous_target=0,
            current_target=0,
            requirements=(),
            entries=(),
            detected_component_keys=(),
            updated_at=None,
            warnings=(),
        )
        with (
            patch.object(streamlit_app, "database_url", return_value="postgresql://database"),
            patch.object(streamlit_app, "load_weekly_projects_cached", return_value=(option,)),
            patch.object(streamlit_app, "load_weekly_source_cached", return_value=source),
            patch.object(streamlit_app.st, "selectbox", return_value=option.key),
            patch.object(streamlit_app, "render_target_editor"),
            patch.object(streamlit_app, "render_requirement_editor"),
            patch.object(streamlit_app.st, "markdown") as markdown,
        ):
            streamlit_app.weekly_control_panel()

        rendered = markdown.call_args.args[0]
        self.assertIn("Nenhum movimento reconhecido para o projeto selecionado", rendered)

    def test_missing_weekly_tables_has_a_specific_migration_state(self):
        instant = datetime(2026, 8, 25, 12, tzinfo=ZoneInfo("America/Sao_Paulo"))
        identity = ProjectIdentity("FEMSA", "DISPLAY", "1", "VM - 1000")
        option = ProjectOption(
            project_key(identity),
            identity,
            "FEMSA · DISPLAY · Nº 1 · VM - 1000",
            instant,
        )
        with (
            patch.object(streamlit_app, "database_url", return_value="postgresql://database"),
            patch.object(streamlit_app, "load_weekly_projects_cached", return_value=(option,)),
            patch.object(streamlit_app.st, "selectbox", return_value=option.key),
            patch.object(
                streamlit_app,
                "load_weekly_source_cached",
                side_effect=psycopg.errors.UndefinedTable("relation does not exist"),
            ),
            patch.object(streamlit_app.st, "markdown") as markdown,
        ):
            streamlit_app.weekly_control_panel()

        rendered = markdown.call_args.args[0]
        self.assertIn("Estrutura semanal ainda não configurada", rendered)

    def test_database_failure_does_not_expose_connection_details(self):
        with (
            patch.object(streamlit_app, "database_url", return_value="postgresql://database"),
            patch.object(
                streamlit_app,
                "load_weekly_projects_cached",
                side_effect=RuntimeError("password=segredo host=interno"),
            ),
            patch.object(streamlit_app.st, "markdown") as markdown,
        ):
            streamlit_app.weekly_control_panel()

        rendered = markdown.call_args.args[0]
        self.assertIn("Tente novamente em alguns instantes", rendered)
        self.assertNotIn("segredo", rendered)

    def test_conflicting_project_identity_has_a_specific_state(self):
        with (
            patch.object(streamlit_app, "database_url", return_value="postgresql://database"),
            patch.object(
                streamlit_app,
                "load_weekly_projects_cached",
                side_effect=ProjectIdentityConflictError("conflito interno"),
            ),
            patch.object(streamlit_app.st, "markdown") as markdown,
        ):
            streamlit_app.weekly_control_panel()

        rendered = markdown.call_args.args[0]
        self.assertIn("Identidades de projeto conflitantes", rendered)
        self.assertIn("Padronize", rendered)

    def test_detected_components_fill_free_orders_before_manual_chave_and_suporte(self):
        source = WeeklySourceData(
            previous_target=None,
            current_target=None,
            requirements=(
                ComponentRequirement("CHAVE", "CHAVE", Decimal("1"), 8, True),
                ComponentRequirement("SUPORTE", "SUPORTE", Decimal("2"), 9, True),
            ),
            entries=(),
            detected_component_keys=("CORPO", "TOLDO"),
            updated_at=None,
            warnings=(),
        )

        completed = streamlit_app._complete_detected_requirements(source)

        self.assertEqual(
            [(item.source_component_key, item.display_order) for item in completed],
            [("CORPO", 0), ("TOLDO", 1), ("CHAVE", 8), ("SUPORTE", 9)],
        )


class WeeklyEditorTest(unittest.TestCase):
    def test_confirmed_target_form_persists_the_accumulated_value(self):
        identity = ProjectIdentity(
            "FEMSA",
            "PG + ECONOMIA HIBRIDO",
            "26081000",
            "VM - 1000",
        )
        period = WeekPeriod(
            datetime(2026, 8, 24).date(),
            datetime(2026, 8, 28).date(),
        )
        source = MagicMock(current_target=501)
        context = MagicMock()
        with (
            patch.object(streamlit_app.st, "expander", return_value=context),
            patch.object(streamlit_app.st, "form", return_value=context),
            patch.object(streamlit_app.st, "caption"),
            patch.object(streamlit_app.st, "date_input", return_value=period.end),
            patch.object(streamlit_app.st, "number_input", return_value=501),
            patch.object(streamlit_app.st, "checkbox", return_value=True),
            patch.object(streamlit_app.st, "form_submit_button", return_value=True),
            patch.object(
                streamlit_app,
                "save_weekly_target",
                create=True,
            ) as save,
            patch.object(streamlit_app.load_weekly_source_cached, "clear"),
            patch.object(streamlit_app.st, "success"),
            patch.object(streamlit_app.st, "rerun"),
        ):
            streamlit_app.render_target_editor(
                "postgresql://database",
                identity,
                period,
                source,
            )

        save.assert_called_once_with(
            "postgresql://database",
            identity,
            period,
            501,
        )

    def test_confirmed_component_editor_persists_manual_requirements(self):
        identity = ProjectIdentity(
            "FEMSA",
            "PG + ECONOMIA HIBRIDO",
            "26081000",
            "VM - 1000",
        )
        requirements = (
            ComponentRequirement("CHAVE", "CHAVE", Decimal("1"), 1, True),
        )
        edited_rows = [
            {
                "Ativo": True,
                "Componente na base": "CHAVE",
                "Nome exibido": "CHAVE",
                "Qtd. por conjunto": 1,
                "Ordem": 1,
            },
            {
                "Ativo": True,
                "Componente na base": "SUPORTE FIXAÇÃO DISPLAY",
                "Nome exibido": "SUPORTE FIXAÇÃO DISPLAY",
                "Qtd. por conjunto": 2,
                "Ordem": 2,
            },
        ]
        context = MagicMock()
        with (
            patch.object(streamlit_app.st, "expander", return_value=context),
            patch.object(streamlit_app.st, "form", return_value=context),
            patch.object(streamlit_app.st, "caption"),
            patch.object(streamlit_app.st, "data_editor", return_value=edited_rows),
            patch.object(streamlit_app.st, "checkbox", return_value=True),
            patch.object(streamlit_app.st, "form_submit_button", return_value=True),
            patch.object(
                streamlit_app,
                "save_component_requirements",
                create=True,
            ) as save,
            patch.object(streamlit_app.load_weekly_source_cached, "clear"),
            patch.object(streamlit_app.st, "success"),
            patch.object(streamlit_app.st, "rerun"),
        ):
            streamlit_app.render_requirement_editor(
                "postgresql://database",
                identity,
                requirements,
            )

        saved = save.call_args.args[2]
        self.assertEqual(
            [(item.source_component_key, item.quantity_per_set) for item in saved],
            [
                ("CHAVE", Decimal("1")),
                ("SUPORTE FIXACAO DISPLAY", Decimal("2")),
            ],
        )

    def test_component_editor_does_not_write_without_confirmation(self):
        identity = ProjectIdentity("FEMSA", "DISPLAY", "1", "VM - 1000")
        requirement = ComponentRequirement("CHAVE", "CHAVE", Decimal("1"), 1, True)
        context = MagicMock()
        with (
            patch.object(streamlit_app.st, "expander", return_value=context),
            patch.object(streamlit_app.st, "form", return_value=context),
            patch.object(streamlit_app.st, "caption"),
            patch.object(
                streamlit_app.st,
                "data_editor",
                return_value=[
                    {
                        "Ativo": True,
                        "Componente na base": "CHAVE",
                        "Nome exibido": "CHAVE",
                        "Qtd. por conjunto": 1,
                        "Ordem": 1,
                    }
                ],
            ),
            patch.object(streamlit_app.st, "checkbox", return_value=False),
            patch.object(streamlit_app.st, "form_submit_button", return_value=True),
            patch.object(streamlit_app, "save_component_requirements") as save,
            patch.object(streamlit_app.st, "warning") as warning,
        ):
            streamlit_app.render_requirement_editor(
                "postgresql://database",
                identity,
                (requirement,),
            )

        save.assert_not_called()
        warning.assert_called_once_with("Confirme a gravação dos requisitos.")

    def test_target_write_failure_does_not_expose_database_details(self):
        identity = ProjectIdentity("FEMSA", "DISPLAY", "1", "VM - 1000")
        period = WeekPeriod(
            datetime(2026, 8, 24).date(),
            datetime(2026, 8, 28).date(),
        )
        context = MagicMock()
        with (
            patch.object(streamlit_app.st, "expander", return_value=context),
            patch.object(streamlit_app.st, "form", return_value=context),
            patch.object(streamlit_app.st, "caption"),
            patch.object(streamlit_app.st, "date_input", return_value=period.end),
            patch.object(streamlit_app.st, "number_input", return_value=501),
            patch.object(streamlit_app.st, "checkbox", return_value=True),
            patch.object(streamlit_app.st, "form_submit_button", return_value=True),
            patch.object(
                streamlit_app,
                "save_weekly_target",
                side_effect=RuntimeError("password=segredo host=interno"),
            ),
            patch.object(streamlit_app.st, "error") as error,
        ):
            streamlit_app.render_target_editor(
                "postgresql://database",
                identity,
                period,
                MagicMock(current_target=501),
            )

        message = error.call_args.args[0]
        self.assertEqual("Não foi possível salvar a meta. Tente novamente.", message)
        self.assertNotIn("segredo", message)


if __name__ == "__main__":
    unittest.main()
