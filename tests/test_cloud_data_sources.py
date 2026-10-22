from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import sqlite3

import data_loader


class CloudDataSourcesTests(TestCase):
    def test_packaged_sources_load_when_network_drive_is_absent(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'forms').mkdir()
            csv = 'id,data_producao,quantidade,pecas_mortas\n1,15/07/26,12,0\n'
            (root / 'registros.csv').write_text(csv, encoding='utf-8')
            (root / 'forms' / 'historico.csv').write_text(csv, encoding='utf-8')
            columns = 'id,timestamp,cliente,display,numero_display,maquinario,processo,data_producao,operadores,hora_inicio,hora_fim,quantidade,pecas_mortas,quantidade_total'
            with closing(sqlite3.connect(root / 'db.sqlite3')) as conn:
                conn.execute('CREATE TABLE core_productionentry (' + columns + ')')
                conn.execute("INSERT INTO core_productionentry (id,data_producao,quantidade,pecas_mortas) VALUES (1,'15/07/26',12,0)")
                conn.commit()
            with patch.multiple(data_loader, DATA_DIR=root / 'missing', FORMS_DIR=root / 'missing_forms', SQLITE_DB_PATH=root / 'missing.sqlite3'), patch.object(data_loader, 'BUNDLED_DATA_DIR', root, create=True):
                data_loader._load_data_cached.clear()
                for source in ('base_atual', 'forms', 'sqlite'):
                    with self.subTest(source=source):
                        frame, latest, quality = data_loader.load_data(source)
                        self.assertIsNotNone(latest)
                        self.assertEqual(frame['quantidade_produzida'].tolist(), [12])
