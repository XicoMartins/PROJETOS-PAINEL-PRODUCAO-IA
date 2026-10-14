import unittest
from unittest.mock import patch
from contextlib import contextmanager
from io import BytesIO
from pypdf import PdfReader
from test_weekly_report import ID, NOW, source
from weekly_control import weekly_periods
from weekly_report import snapshot, changes

class Cursor:
    def __init__(self, baselines=None, fail_save=False): self.calls=[]; self.baselines=baselines or {}; self.fail_save=fail_save; self.last=None
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def execute(self,sql,args=()):
        self.calls.append((sql,args)); self.last=args
        if self.fail_save and 'INSERT INTO' in sql: raise RuntimeError('save failed')
    def fetchone(self): return self.baselines.get(self.last[0])
class Connection:
    def __init__(self,cursor): self.cur=cursor; self.rollback=False; self.commit=False
    def __enter__(self): return self
    def __exit__(self,t,*args): self.rollback=t is not None; self.commit=t is None
    def cursor(self,**kwargs): return self.cur
class EmissionTest(unittest.TestCase):
    def api(self):
        try: from weekly_report_data import emit_report
        except ImportError: self.fail('Durable atomic emission missing')
        return emit_report
    def test_no_changes_does_not_generate_or_save(self):
        emit=self.api(); snap=snapshot(ID,source()); cur=Cursor({snap['project_key']:{'snapshot':snap,'generated_at':NOW}}); connection=Connection(cur)
        with patch('weekly_report_data.psycopg.connect',return_value=connection),patch('weekly_report_data.load_weekly_source',return_value=source()),patch('weekly_report_data.build_pdf') as pdf:
            self.assertIsNone(emit('db',(ID,),*weekly_periods(NOW))); pdf.assert_not_called()
        self.assertFalse(any('INSERT INTO' in sql for sql,_ in cur.calls))
    def test_generation_and_save_failure_rollback(self):
        emit=self.api()
        for fail_save in (False,True):
            connection=Connection(Cursor(fail_save=fail_save))
            with patch('weekly_report_data.psycopg.connect',return_value=connection),patch('weekly_report_data.load_weekly_source',return_value=source()),patch('weekly_report_data.build_pdf',side_effect=None if fail_save else RuntimeError('pdf failed'),return_value=b'%PDF-test'):
                with self.assertRaises(RuntimeError): emit('db',(ID,),*weekly_periods(NOW))
            self.assertTrue(connection.rollback)
    def test_sorted_locks_before_fresh_source_and_exact_pdf(self):
        from dataclasses import replace
        emit=self.api(); other=replace(ID,numero_display='2'); cur=Cursor(); connection=Connection(cur)
        def load(*args, **kwargs):
            self.assertEqual(sum('pg_advisory' in sql for sql,_ in cur.calls),2)
            return source()
        with patch('weekly_report_data.psycopg.connect',return_value=connection),patch('weekly_report_data.load_weekly_source',side_effect=load) as fresh,patch('weekly_report_data.build_pdf',return_value=b'%PDF-exact'):
            result=emit('db',(other,ID),*weekly_periods(NOW))
        self.assertEqual(result,b'%PDF-exact'); self.assertTrue(connection.commit)
        locks=[args[0] for sql,args in cur.calls if 'pg_advisory' in sql]; self.assertEqual(locks,sorted(locks)); self.assertEqual(len(locks),2)
        self.assertIs(fresh.call_args.kwargs['connection'],connection)
    def test_mixed_general_unchanged_project_only_saves_changed_scope(self):
        from dataclasses import replace
        from weekly_control import project_key
        emit=self.api(); other=replace(ID,numero_display='2'); snap=snapshot(ID,source()); cur=Cursor({snap['project_key']:{'snapshot':snap,'generated_at':NOW}})
        with patch('weekly_report_data.psycopg.connect',return_value=Connection(cur)),patch('weekly_report_data.load_weekly_source',return_value=source()),patch('weekly_report_data.build_pdf',return_value=b'%PDF-exact') as pdf:
            emit('db',(ID,other),*weekly_periods(NOW))
        self.assertEqual(len(pdf.call_args.args[0]),1)
        saved=[args[0] for sql,args in cur.calls if 'INSERT INTO' in sql]
        self.assertEqual(saved,[project_key(other)])
class PDFTest(unittest.TestCase):
    def test_binary_pdf_paginated_and_reconciliation_extractable(self):
        try: from weekly_report_pdf import build_pdf
        except ImportError: self.fail('PDF generator missing')
        before=snapshot(ID,source()); now=snapshot(ID,source('162'))
        rows=changes(now,before)
        report={'snapshot':now,'previous_at':NOW,'rows':rows}
        data=build_pdf([report],NOW); self.assertTrue(data.startswith(b'%PDF-'))
        text=''.join(page.extract_text() for page in PdfReader(BytesIO(data)).pages)
        for value in ('152 + 10 = 162','124 + 0 = 124','28 + 10 = 38','RETORNO','REMESSA','14/10/2026','12/10 - 16/10/2026','19/10 - 23/10/2026'): self.assertIn(value,text)
        report['rows']=rows*90
        reader=PdfReader(BytesIO(build_pdf([report],NOW))); self.assertGreater(len(reader.pages),1)
        self.assertTrue(all('Página' in page.extract_text() for page in reader.pages))
