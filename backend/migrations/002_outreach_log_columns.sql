create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;

create table if not exists public.outreach_log (
  id uuid primary key default gen_random_uuid(),
  agent_id text not null check (agent_id in ('mateo', 'valeria')),
  category text not null check (category in ('job_application', 'client_lead')),
  title text not null,
  recipient text not null default 'No figura en la fuente',
  source_platform text not null default 'No figura en la fuente',
  source_url text,
  source_url_of_application text,
  company_or_client_name text not null default 'No figura en la fuente',
  contact_channel text not null default 'No figura en la fuente',
  contact_ref text not null default 'No figura en la fuente',
  contact_ref_pending boolean not null default true,
  full_text text not null default '',
  summary text not null default '',
  cv_reference text,
  attachment_reference text,
  hourly_rate_usd integer,
  rate_model text,
  status text not null default 'pending_approval' check (status in ('enviado', 'espera_respuesta', 'respondido', 'cerrado', 'pending_approval', 'approved', 'rejected')),
  gmail_message_id text,
  gmail_thread_id text,
  gmail_label text check (gmail_label in ('Postulaciones', 'Clientes')),
  last_response_at timestamptz,
  notes text,
  operator text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.outreach_log add column if not exists id uuid default gen_random_uuid();
alter table public.outreach_log add column if not exists agent_id text not null default 'mateo';
alter table public.outreach_log add column if not exists category text not null default 'client_lead';
alter table public.outreach_log add column if not exists title text not null default 'Registro de seguimiento';
alter table public.outreach_log add column if not exists recipient text not null default 'No figura en la fuente';
alter table public.outreach_log add column if not exists source_platform text not null default 'No figura en la fuente';
alter table public.outreach_log add column if not exists source_url text;
alter table public.outreach_log add column if not exists source_url_of_application text;
alter table public.outreach_log add column if not exists company_or_client_name text not null default 'No figura en la fuente';
alter table public.outreach_log add column if not exists contact_channel text not null default 'No figura en la fuente';
alter table public.outreach_log add column if not exists contact_ref text not null default 'No figura en la fuente';
alter table public.outreach_log add column if not exists contact_ref_pending boolean not null default true;
alter table public.outreach_log add column if not exists full_text text not null default '';
alter table public.outreach_log add column if not exists summary text not null default '';
alter table public.outreach_log add column if not exists cv_reference text;
alter table public.outreach_log add column if not exists attachment_reference text;
alter table public.outreach_log add column if not exists hourly_rate_usd integer;
alter table public.outreach_log add column if not exists rate_model text;
alter table public.outreach_log add column if not exists status text not null default 'pending_approval';
alter table public.outreach_log add column if not exists gmail_message_id text;
alter table public.outreach_log add column if not exists gmail_thread_id text;
alter table public.outreach_log add column if not exists gmail_label text;
alter table public.outreach_log add column if not exists last_response_at timestamptz;
alter table public.outreach_log add column if not exists notes text;
alter table public.outreach_log add column if not exists operator text;
alter table public.outreach_log add column if not exists created_at timestamptz not null default now();
alter table public.outreach_log add column if not exists updated_at timestamptz not null default now();

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.outreach_log'::regclass and contype = 'p'
  ) then
    alter table public.outreach_log add constraint outreach_log_pkey primary key (id);
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.outreach_log'::regclass and conname = 'outreach_log_agent_id_check'
  ) then
    alter table public.outreach_log add constraint outreach_log_agent_id_check
      check (agent_id in ('mateo', 'valeria'));
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.outreach_log'::regclass and conname = 'outreach_log_category_check'
  ) then
    alter table public.outreach_log add constraint outreach_log_category_check
      check (category in ('job_application', 'client_lead'));
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.outreach_log'::regclass and conname = 'outreach_log_status_check'
  ) then
    alter table public.outreach_log add constraint outreach_log_status_check
      check (status in ('enviado', 'espera_respuesta', 'respondido', 'cerrado', 'pending_approval', 'approved', 'rejected'));
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.outreach_log'::regclass and conname = 'outreach_log_gmail_label_check'
  ) then
    alter table public.outreach_log add constraint outreach_log_gmail_label_check
      check (gmail_label in ('Postulaciones', 'Clientes'));
  end if;
end $$;

create index if not exists outreach_log_agent_status_idx
  on public.outreach_log (agent_id, status, created_at desc);
create index if not exists outreach_log_thread_idx
  on public.outreach_log (gmail_thread_id) where gmail_thread_id is not null;

alter table public.outreach_log enable row level security;
