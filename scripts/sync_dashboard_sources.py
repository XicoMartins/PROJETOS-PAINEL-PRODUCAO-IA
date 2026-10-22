"""Atualiza as copias de consulta que acompanham o deploy online."""
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from constants import BUNDLED_DATA_DIR, DATA_DIR, FORMS_DIR, SQLITE_DB_PATH
from data_loader import _read_sqlite_source


def main():
    # Leia tudo antes de substituir as copias; nunca exporte tabelas de autenticacao.
    production = _read_sqlite_source(SQLITE_DB_PATH)
    forms = list(FORMS_DIR.glob('*.csv'))
    if not forms:
        raise RuntimeError('Nenhum CSV historico encontrado.')
    BUNDLED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (BUNDLED_DATA_DIR / 'forms').mkdir(exist_ok=True)
    shutil.copy2(DATA_DIR / 'registros.csv', BUNDLED_DATA_DIR / 'registros.csv')
    for source in forms:
        shutil.copy2(source, BUNDLED_DATA_DIR / 'forms' / source.name)
    with closing(sqlite3.connect(BUNDLED_DATA_DIR / 'db.sqlite3')) as conn:
        production.to_sql('core_productionentry', conn, if_exists='replace', index=False)
    print(f'Copias atualizadas: CSV atual, {len(forms)} CSV historico(s), SQLite com {len(production)} registros.')


if __name__ == '__main__':
    main()
