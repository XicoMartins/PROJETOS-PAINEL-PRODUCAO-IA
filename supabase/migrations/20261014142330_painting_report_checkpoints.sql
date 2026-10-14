begin;
create table public.painting_report_checkpoints (
    project_key text primary key check (length(project_key) = 64),
    snapshot jsonb not null check (jsonb_typeof(snapshot) = 'object'),
    generated_at timestamptz not null
);
alter table public.painting_report_checkpoints enable row level security;
revoke all on table public.painting_report_checkpoints from anon, authenticated;
commit;
