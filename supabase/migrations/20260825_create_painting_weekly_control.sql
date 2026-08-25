begin;

create table if not exists public.painting_weekly_targets (
    id bigint generated always as identity primary key,
    project_key text not null check (length(project_key) = 64),
    source_cliente text not null check (btrim(source_cliente) <> ''),
    source_display text not null check (btrim(source_display) <> ''),
    source_numero_display text not null check (btrim(source_numero_display) <> ''),
    source_codigo_pintura text not null check (btrim(source_codigo_pintura) <> ''),
    week_start date not null check (extract(isodow from week_start) = 1),
    week_end date not null,
    target_sets integer not null check (target_sets >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint painting_weekly_targets_week_range_check
        check (week_end = week_start + 4),
    constraint painting_weekly_targets_project_week_key
        unique (project_key, week_start)
);

create index if not exists painting_weekly_targets_project_period_idx
    on public.painting_weekly_targets (project_key, week_start desc);

create table if not exists public.painting_component_requirements (
    id bigint generated always as identity primary key,
    project_key text not null check (length(project_key) = 64),
    source_component_key text not null check (btrim(source_component_key) <> ''),
    display_name text not null check (btrim(display_name) <> ''),
    quantity_per_set numeric(12, 3) check (quantity_per_set > 0),
    display_order integer not null check (display_order >= 0),
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint painting_component_requirements_project_component_key
        unique (project_key, source_component_key),
    constraint painting_component_requirements_project_order_key
        unique (project_key, display_order)
);

create index if not exists painting_component_requirements_active_order_idx
    on public.painting_component_requirements (project_key, active, display_order);

alter table public.painting_weekly_targets enable row level security;
alter table public.painting_component_requirements enable row level security;

revoke all on table public.painting_weekly_targets from anon, authenticated;
revoke all on table public.painting_component_requirements from anon, authenticated;

commit;
