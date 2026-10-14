import unittest
from unittest.mock import patch
from dataclasses import replace
from streamlit.testing.v1 import AppTest
import streamlit_app
from test_weekly_report import ID,NOW,source
from weekly_control import project_key
from weekly_control_data import ProjectOption

class LiveWeeklyWidgetTest(unittest.TestCase):
    def test_two_projects_render_editors_without_duplicate_widget_ids(self):
        other=replace(ID,numero_display='2')
        projects=tuple(ProjectOption(project_key(identity),identity,f'FEMSA DISPLAY {identity.numero_display} VM',NOW) for identity in (ID,other))
        app=AppTest.from_string('import streamlit_app\nstreamlit_app.weekly_control_panel()')
        with patch.object(streamlit_app,'database_url',return_value='db'),patch.object(streamlit_app,'load_weekly_projects_cached',return_value=projects),patch.object(streamlit_app,'load_weekly_source_cached',return_value=source()):
            app.run()
            self.assertEqual(len(app.exception),0)
            app.multiselect[0].set_value([project.key for project in projects]).run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(len(app.date_input),2)
            self.assertEqual(len(app.number_input),2)
            self.assertEqual(len(app.checkbox),4)
