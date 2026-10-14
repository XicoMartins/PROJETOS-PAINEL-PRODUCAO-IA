import unittest
from unittest.mock import MagicMock, patch
from contextlib import ExitStack
import pandas as pd
import app

class StopAuthentication(Exception):
    pass

class WeeklyMainIntegrationTest(unittest.TestCase):
    def setup_main(self, stack, selected):
        ui = stack.enter_context(patch.object(app, 'st'))
        ui.session_state = {}
        ui.radio.return_value = selected
        stack.enter_context(patch.object(app, 'apply_branding'))
        stack.enter_context(patch.object(app, '_render_dashboard_title'))
        stack.enter_context(patch.object(app, 'is_admin_user', return_value=False))
        return ui

    def test_weekly_navigation_available_to_normal_and_admin(self):
        for admin in (False, True):
            tabs = app.build_navigation_tabs(is_admin=admin)
            self.assertEqual(tabs[tabs.index('Remessas pintura') + 1], 'Controle semanal pintura')

    def test_weekly_returns_before_production_and_painting_loaders(self):
        with ExitStack() as stack:
            self.setup_main(stack, 'Controle semanal pintura')
            stack.enter_context(patch.object(app, 'require_authentication'))
            weekly = stack.enter_context(patch.object(app, 'render_weekly_control', create=True))
            production = stack.enter_context(patch.object(app, 'load_data', return_value=(pd.DataFrame(), MagicMock(), {})))
            painting = stack.enter_context(patch.object(app, 'load_painting_data'))
            filters = stack.enter_context(patch.object(app, 'apply_filters'))
            app.main()
            weekly.assert_called_once_with()
            production.assert_not_called()
            painting.assert_not_called()
            filters.assert_not_called()

    def test_authentication_precedes_weekly_access(self):
        with ExitStack() as stack:
            ui = self.setup_main(stack, 'Controle semanal pintura')
            stack.enter_context(patch.object(app, 'require_authentication', side_effect=StopAuthentication))
            weekly = stack.enter_context(patch.object(app, 'render_weekly_control', create=True))
            with self.assertRaises(StopAuthentication):
                app.main()
            weekly.assert_not_called()
            ui.radio.assert_not_called()

    def test_default_general_view_keeps_production_loader(self):
        with ExitStack() as stack:
            self.setup_main(stack, 'Geral')
            stack.enter_context(patch.object(app, 'require_authentication'))
            stack.enter_context(patch.object(app, '_render_data_source_picker', return_value='FORMS-MTECH (PostgreSQL)'))
            production = stack.enter_context(patch.object(app, 'load_data', return_value=(pd.DataFrame(), MagicMock(), {})))
            weekly = stack.enter_context(patch.object(app, 'render_weekly_control', create=True))
            for name in ('_render_section_title', '_render_data_status', 'render_kpis'):
                stack.enter_context(patch.object(app, name))
            app.main()
            production.assert_called_once_with('forms_postgres')
            weekly.assert_not_called()



class WeeklyModuleIsolationTest(unittest.TestCase):
    def test_import_does_not_configure_page_or_inject_styles(self):
        import importlib
        import weekly_control_ui
        with patch.object(weekly_control_ui.st, 'set_page_config') as config, patch.object(weekly_control_ui.st, 'markdown') as markdown:
            importlib.reload(weekly_control_ui)
        config.assert_not_called()
        markdown.assert_not_called()

    def test_database_configuration_uses_existing_loader(self):
        import weekly_control_ui
        with patch.object(weekly_control_ui, 'get_database_url', return_value='postgresql://configured'):
            self.assertEqual(weekly_control_ui.database_url(), 'postgresql://configured')
        with patch.object(weekly_control_ui, 'get_database_url', return_value=None):
            self.assertEqual(weekly_control_ui.database_url(), '')

    def test_styles_are_injected_only_when_weekly_view_renders(self):
        import weekly_control_ui
        with patch.object(weekly_control_ui.st, 'container') as container, patch.object(weekly_control_ui.st, 'markdown') as markdown, patch.object(weekly_control_ui, 'weekly_control_panel') as panel:
            weekly_control_ui.render_weekly_control()
        container.assert_called_once_with(key='weekly_control_host')
        markdown.assert_called_once_with(weekly_control_ui.WEEKLY_HOST_CSS, unsafe_allow_html=True)
        panel.assert_called_once_with()
