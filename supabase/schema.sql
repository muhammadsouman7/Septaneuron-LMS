-- Septaneuron intern LMS — run once in Supabase: SQL Editor > New query > paste > Run.
-- The Flask backend talks to these tables with the *secret* key (server-side only).
-- Row Level Security is switched ON with no policies, so the public/anon key can read nothing.

create table if not exists public.domains (
    id          uuid primary key default gen_random_uuid(),
    slug        text not null unique,
    name        text not null unique,
    created_at  timestamptz not null default now()
);

create table if not exists public.users (
    id                    uuid primary key default gen_random_uuid(),
    email                 text not null unique check (email = lower(email)),
    full_name             text not null,
    password_hash         text not null,
    role                  text not null check (role in ('super_admin', 'admin', 'intern')),
    domain_id             uuid references public.domains(id) on delete restrict,
    is_active             boolean not null default true,
    must_change_password  boolean not null default true,
    failed_attempts       int not null default 0,
    locked_until          timestamptz,
    last_login_at         timestamptz,
    created_at            timestamptz not null default now(),
    constraint users_domain_required check (role = 'super_admin' or domain_id is not null)
);
create index if not exists users_domain_role_idx on public.users (domain_id, role);

create table if not exists public.tasks (
    id               uuid primary key default gen_random_uuid(),
    domain_id        uuid not null references public.domains(id) on delete cascade,
    title            text not null,
    description      text not null default '',
    due_at           timestamptz,
    max_points       int not null default 100 check (max_points between 1 and 1000),
    attachment_path  text,
    attachment_name  text,
    created_by       uuid references public.users(id) on delete set null,
    emailed_count    int not null default 0,
    emailed_at       timestamptz,
    email_error      text,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);
create index if not exists tasks_domain_due_idx on public.tasks (domain_id, due_at);

create table if not exists public.submissions (
    id            uuid primary key default gen_random_uuid(),
    task_id       uuid not null references public.tasks(id) on delete cascade,
    intern_id     uuid not null references public.users(id) on delete cascade,
    domain_id     uuid not null references public.domains(id) on delete cascade,
    note          text,
    link_url      text,
    file_path     text,
    file_name     text,
    status        text not null default 'submitted' check (status in ('submitted', 'needs_revision', 'approved')),
    is_late       boolean not null default false,
    score         int check (score >= 0),
    feedback      text,
    reviewed_by   uuid references public.users(id) on delete set null,
    reviewed_at   timestamptz,
    submitted_at  timestamptz not null default now(),
    unique (task_id, intern_id)
);
create index if not exists submissions_domain_status_idx on public.submissions (domain_id, status);
create index if not exists submissions_intern_idx on public.submissions (intern_id);

-- Lock the tables down: RLS on, no policies => only the secret/service_role key can access them.
alter table public.domains     enable row level security;
alter table public.users       enable row level security;
alter table public.tasks       enable row level security;
alter table public.submissions enable row level security;

-- Private storage bucket for task attachments and intern submissions (4 MB per file).
insert into storage.buckets (id, name, public, file_size_limit)
values ('lms-files', 'lms-files', false, 4194304)
on conflict (id) do nothing;

-- Starter domains (add or rename more later from the portal's Team page).
insert into public.domains (slug, name) values
    ('web-development',     'Web Development'),
    ('python-programming',  'Python Programming'),
    ('ai-machine-learning', 'AI & Machine Learning'),
    ('ai-automation',       'AI Automation')
on conflict (slug) do nothing;
