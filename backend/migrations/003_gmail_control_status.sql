do $$
begin
  alter table public.outreach_log drop constraint if exists outreach_log_status_check;
  alter table public.outreach_log add constraint outreach_log_status_check
    check (status in ('enviado', 'espera_respuesta', 'respondido', 'novedad_detectada',
                      'cerrado', 'pending_approval', 'approved', 'rejected'));
end $$;

create index if not exists outreach_log_novedad_idx
  on public.outreach_log (status, created_at desc)
  where status = 'novedad_detectada';
