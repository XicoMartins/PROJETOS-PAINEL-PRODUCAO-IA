# Painel de Producao IA

Painel Streamlit para analise dos lancamentos do FORMS-MTECH.

## Fonte principal

Em producao, o painel le a tabela `production_entries` usando a mesma `DATABASE_URL`
configurada no app de lancamentos.

Configure nos Secrets do Streamlit Cloud:

```toml
DATABASE_URL = "postgresql://usuario:senha@host:5432/banco?sslmode=require"
```

## Deploy no Streamlit Cloud

1. Suba esta pasta em um repositorio GitHub.
2. No Streamlit Cloud, selecione o repositorio.
3. Main file: `streamlit_app.py`.
4. Configure o mesmo `DATABASE_URL` do FORMS-MTECH nos Secrets.

## Execucao local

```powershell
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Migrar SQLite legado para PostgreSQL

A base antiga fica em `PROJETOS -BACKEND/db.sqlite3`, tabela `core_productionentry`.
Para validar a leitura sem gravar:

```powershell
python scripts/migrate_sqlite_to_postgres.py --dry-run
```

Para migrar para o PostgreSQL:

```powershell
$env:DATABASE_URL="postgresql://usuario:senha@host:5432/banco?sslmode=require"
python scripts/migrate_sqlite_to_postgres.py
```

O script usa `ON CONFLICT DO NOTHING`, entao pode ser reexecutado sem duplicar
registros que ja existam por `source_hash` ou `import_key`.
