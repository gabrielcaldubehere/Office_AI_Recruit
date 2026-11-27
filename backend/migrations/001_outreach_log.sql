-- AI Office · Oficina 1
-- Registro histórico y trazable de postulaciones (Mateo) y contactos (Valeria).
-- Ejecutar una vez en el SQL Editor de Supabase. Idempotente.

create table if not exists public.outreach_log (
  id uuid primary key default gen_random_uuid(),
  agent_id text not null check (agent_id in ('mateo', 'valeria')),
  category text not null check (category in ('job_application', 'client_lead')),

  -- Trazabilidad de origen (anti-alucinación)
  source_platform text not null default 'No figura en la fuente',
  source_url text,
  company_or_client_name text not null default 'No figura en la fuente',
  contact_channel text not null default 'No figura en la fuente',
  contact_ref text not null default 'No figura en la fuente',
  contact_ref_pending boolean not null default true,

  -- Contenido real preparado / enviado
  title text not null,
  recipient text not null default 'No figura en la fuente',
  full_text text not null default '',
  summary text not null default '',
  source_url_of_application text,
  cv_reference text,
  attachment_reference text,
  hourly_rate_usd integer,
  rate_model text,
  deliverable_id uuid references public.deliverables(id) on delete set null,

  -- Seguimiento
  status text not null default 'pending_approval'
    check (status in ('enviado', 'espera_respuesta', 'respondido', 'cerrado',
                      'pending_approval', 'approved', 'rejected')),
  gmail_message_id text,
  gmail_thread_id text,
  gmail_label text check (gmail_label in ('Postulaciones', 'Clientes')),
  last_response_at timestamptz,
  operator text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists outreach_log_agent_status_idx
  on public.outreach_log (agent_id, status, created_at desc);
create index if not exists outreach_log_thread_idx
  on public.outreach_log (gmail_thread_id) where gmail_thread_id is not null;

alter table public.outreach_log enable row level security;
-- Solo el backend (service_role) accede; no hay policies anon/authenticated.
