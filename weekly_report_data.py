"""Serialize emissions per project; source read, PDF and checkpoint share a transaction."""
from datetime import datetime
import psycopg
import psycopg.rows
from psycopg.types.json import Jsonb
from weekly_control import SAO_PAULO, project_key
from weekly_control_data import load_weekly_source
from weekly_report import snapshot, changes
from weekly_report_pdf import build_pdf

def emit_report(db_url, identities, previous_period, current_period, order_by='latest_update'):
    if order_by not in ('latest_update','selection'):
        raise ValueError('Ordenação inválida')
    identities={project_key(identity):identity for identity in identities}
    if not identities: return None
    with psycopg.connect(db_url,connect_timeout=12) as connection:
        with connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            # Sorted text keys also sort the lock acquisition, independent of UI selection.
            for key in sorted(identities):
                cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))',(key,))
            reports=[]
            for key in identities:
                cursor.execute('SELECT snapshot, generated_at FROM public.painting_report_checkpoints WHERE project_key = %s',(key,))
                previous=cursor.fetchone()
                source=load_weekly_source(db_url,identities[key],previous_period,current_period,connection=connection)
                current=snapshot(identities[key],source)
                rows=changes(current,previous['snapshot'] if previous else None)
                unchanged=bool(previous and not rows)
                # Show current accumulated values without treating them as changes.
                display_rows=changes(current,None) if unchanged else rows
                reports.append({'snapshot':current,'previous_at':previous['generated_at'] if previous else None,'rows':display_rows,'periods':(previous_period,current_period),'status':'unchanged' if unchanged else 'changed','source_updated_at':source.updated_at})
            if order_by == 'latest_update':
                # Stable order for equal or missing dates, with missing dates last.
                reports.sort(key=lambda report: (report['source_updated_at'] is None, -(report['source_updated_at'].timestamp()) if report['source_updated_at'] else 0))
            generated_at=datetime.now(SAO_PAULO)
            pdf=build_pdf(reports,generated_at)
            if not isinstance(pdf,bytes) or not pdf.startswith(b'%PDF-'): raise ValueError('PDF inválido')
            for report in reports:
                if report['status'] == 'unchanged': continue
                current=report['snapshot']
                cursor.execute('''INSERT INTO public.painting_report_checkpoints(project_key,snapshot,generated_at)
                    VALUES (%s,%s,%s) ON CONFLICT (project_key) DO UPDATE
                    SET snapshot=EXCLUDED.snapshot,generated_at=EXCLUDED.generated_at''',
                    (current['project_key'],Jsonb(current),generated_at))
        # Connection context commits only after every checkpoint succeeds.
    return pdf
