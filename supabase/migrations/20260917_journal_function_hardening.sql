-- Existing functions only use explicitly qualified tables and built-in functions.
-- Lock object lookup to the trusted PostgreSQL system schema.
begin;
alter function public.set_updated_at() set search_path = pg_catalog;
alter function public.journal_stats(date,date) set search_path = pg_catalog;
commit;
