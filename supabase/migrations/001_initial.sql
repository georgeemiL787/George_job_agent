create table if not exists roles (
  slug text primary key,
  rank integer not null default 0,
  company text not null default '',
  title text not null default '',
  location text not null default '',
  source text not null default '',
  score integer not null default 0,
  tier text not null default '',
  role_family text not null default '',
  fit_summary text not null default '',
  apply_url text not null default '',
  cv_ready boolean not null default false,
  letter_ready boolean not null default false,
  status text not null default 'Not Applied',
  applied_date date,
  first_seen timestamptz,
  last_updated timestamptz
);

create index if not exists ix_roles_status on roles (status);
create index if not exists ix_roles_score on roles (score desc);
create index if not exists ix_roles_last_updated on roles (last_updated desc);

create table if not exists events (
  id bigserial primary key,
  timestamp timestamptz not null,
  event text not null,
  detail text not null,
  slug text references roles(slug) on delete set null
);

create table if not exists runs (
  id bigserial primary key,
  timestamp timestamptz not null,
  manual boolean not null,
  dry_run boolean not null,
  report_json jsonb not null
);
