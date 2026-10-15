import unittest
from unittest.mock import patch
import weekly_control_ui as streamlit_app
from test_weekly_report import ID,NOW,source
from weekly_control_data import ProjectOption
from weekly_control import project_key
from weekly_report import ALL_PROJECTS, select_projects
class FilterDownloadTest(unittest.TestCase):
    def test_selection_all_empty_and_specific(self):
        option=ProjectOption(project_key(ID),ID,'FEMSA DISPLAY 1 VM',NOW)
        self.assertEqual(select_projects((option,),[]),())
        self.assertEqual(select_projects((option,),[ALL_PROJECTS]),(option,))
        self.assertEqual(select_projects((option,),[option.key]),(option,))
    def test_generate_download_exact_bytes_and_selection_failure_retains_artifact(self):
        option=ProjectOption(project_key(ID),ID,'FEMSA DISPLAY 1 VM',NOW); state={}
        with patch.object(streamlit_app.st,'session_state',state),patch.object(streamlit_app.st,'caption'),patch.object(streamlit_app.st,'selectbox',return_value='Última atualização'),patch.object(streamlit_app.st,'info'),patch.object(streamlit_app.st,'error'),patch.object(streamlit_app.st,'button',return_value=True) as button,patch.object(streamlit_app.st,'download_button') as download,patch.object(streamlit_app,'emit_report',return_value=b'%PDF-exact') as emit:
            streamlit_app.render_weekly_report_controls('db',(option,),*streamlit_app.weekly_periods())
            self.assertEqual(download.call_args.kwargs['data'],b'%PDF-exact'); self.assertEqual(emit.call_count,1)
            self.assertEqual(emit.call_args.kwargs['order_by'],'latest_update')
            button.return_value=False
            streamlit_app.render_weekly_report_controls('db',(option,),*streamlit_app.weekly_periods())
            self.assertEqual(emit.call_count,1)
            button.return_value=True
            emit.side_effect=RuntimeError('secret')
            streamlit_app.render_weekly_report_controls('db',(option,),*streamlit_app.weekly_periods())
            self.assertEqual(state['weekly_report_artifact']['data'],b'%PDF-exact')
            download.reset_mock()
            streamlit_app.render_weekly_report_controls('db',(),*streamlit_app.weekly_periods())
            download.assert_not_called()

    def test_order_and_selection_changes_hide_previous_download(self):
        first=ProjectOption(project_key(ID),ID,'First',NOW)
        second=ProjectOption('second',ID,'Second',NOW)
        state={}
        with patch.object(streamlit_app.st,'session_state',state),patch.object(streamlit_app.st,'caption'),patch.object(streamlit_app.st,'selectbox',return_value='Ordem de seleção') as order,patch.object(streamlit_app.st,'button',return_value=True) as button,patch.object(streamlit_app.st,'download_button') as download,patch.object(streamlit_app,'emit_report',return_value=b'%PDF-selection') as emit:
            periods=streamlit_app.weekly_periods()
            streamlit_app.render_weekly_report_controls('db',(second,first),*periods)
            self.assertEqual(emit.call_args.args[1],(second.identity,first.identity))
            self.assertEqual(emit.call_args.kwargs['order_by'],'selection')
            self.assertEqual(state['weekly_report_artifact']['key'],(('second',first.key),'selection'))
            button.return_value=False
            download.reset_mock()
            streamlit_app.render_weekly_report_controls('db',(first,second),*periods)
            download.assert_not_called()
            order.return_value='Última atualização'
            streamlit_app.render_weekly_report_controls('db',(second,first),*periods)
            download.assert_not_called()
