from unittest import TestCase
from streamlit.testing.v1 import AppTest


class SourceNavigationTests(TestCase):
    def test_selected_source_survives_navigation_and_filter_reruns(self):
        script = '''
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import streamlit as st
import app
from filters import FilterContext

def load(source):
    return pd.DataFrame({'source': [source]}), Path(source), {}
def filters(frame, **kwargs):
    st.sidebar.text_input('Filtro de teste', key='navigation_test_filter')
    return frame, FilterContext(filtered_no_operator=frame)
with patch.object(app, 'require_authentication'), patch.object(app, 'apply_branding'), patch.object(app, 'render_logout_control'), patch.object(app, 'is_admin_user', return_value=False), patch.object(app, 'load_data', side_effect=load), patch.object(app, 'apply_filters', side_effect=filters), patch.object(app, 'render_kpis'), patch.object(app, 'render_filtered_table', side_effect=lambda frame, context: st.dataframe(frame)):
    app.main()
'''
        for label, source in [('Base atual (CSV) — março/2026', 'base_atual'), ('FORMS histórico (CSV) — janeiro/2026', 'forms'), ('Base legada (SQLite) — junho/2026', 'sqlite')]:
            with self.subTest(source=source):
                page = AppTest.from_string(script, default_timeout=15).run()
                picker = page.selectbox(key='data_source_label')
                self.assertEqual(picker.options, [
                    'FORMS histórico (CSV) — janeiro/2026',
                    'Base atual (CSV) — março/2026',
                    'Base legada (SQLite) — junho/2026',
                    'FORMS-MTECH (PostgreSQL)',
                ])
                self.assertEqual(picker.value, 'FORMS-MTECH (PostgreSQL)')
                picker.select(label).run()
                page.radio(key='dashboard_sidebar_tab').set_value('Registros').run()
                self.assertEqual(page.dataframe[0].value['source'].tolist(), [source])
                page.text_input(key='navigation_test_filter').input('anterior').run()
                self.assertEqual(page.dataframe[0].value['source'].tolist(), [source])
                page.radio(key='dashboard_sidebar_tab').set_value('Geral').run()
                self.assertEqual(page.selectbox(key='data_source_label').value, label)
                self.assertFalse(page.exception)
