-- Apply before enabling JOURNAL_SECURITY_STORAGE=1 in Vercel.
begin;
create table if not exists public.journal_connections (
 user_id uuid primary key references auth.users(id) on delete cascade,
 encrypted_credentials text not null check (length(encrypted_credentials) < 4096)
);
alter table public.journal_connections enable row level security;
revoke all on public.journal_connections from anon, authenticated;
grant all on public.journal_connections to service_role;
-- Deliberately no user policy: browsers cannot retrieve even encrypted tokens.

create table if not exists public.journal_preferences (
 user_id uuid not null references auth.users(id) on delete cascade,
 currency text not null check (currency in ('USD','GBP','EUR')),
 monthly_target numeric(11,2) not null check (monthly_target between 0.01 and 999999999.99),
 trading_days integer not null check (trading_days between 1 and 31),
 primary key (user_id,currency)
);
create table if not exists public.journal_discipline (
 user_id uuid not null references auth.users(id) on delete cascade,
 day date not null,
 followed_rules boolean not null default false,
 primary key (user_id,day)
);
alter table public.journal_preferences enable row level security;
alter table public.journal_discipline enable row level security;
revoke all on public.journal_preferences, public.journal_discipline from anon;
grant select, insert, update, delete on public.journal_preferences, public.journal_discipline to authenticated;
grant all on public.journal_preferences, public.journal_discipline to service_role;
drop policy if exists journal_preferences_own on public.journal_preferences;
create policy journal_preferences_own on public.journal_preferences to authenticated
 using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists journal_discipline_own on public.journal_discipline;
create policy journal_discipline_own on public.journal_discipline to authenticated
 using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create table if not exists public.journal_request_budgets (
 user_id uuid not null references auth.users(id) on delete cascade,
 bucket text not null,
 window_start timestamptz not null,
 count integer not null,
 primary key(user_id,bucket)
);
alter table public.journal_request_budgets enable row level security;
revoke all on public.journal_request_budgets from anon, authenticated;
create or replace function public.journal_consume_budget(bucket_name text)
returns boolean language plpgsql security definer set search_path = '' as $$
declare
 caller uuid := auth.uid();
 max_count integer;
 new_count integer;
 budget_start timestamptz := pg_catalog.date_trunc('minute', pg_catalog.clock_timestamp());
begin
 if caller is null then return false; end if;
 max_count := case bucket_name when 'sync' then 2 when 'read' then 120 when 'write' then 30 else 0 end;
 if max_count = 0 then return false; end if;
 insert into public.journal_request_budgets as b(user_id,bucket,window_start,count)
 values(caller,bucket_name,budget_start,1)
 on conflict(user_id,bucket) do update set window_start=excluded.window_start,
 count=case when b.window_start=excluded.window_start then least(b.count+1,max_count+1) else 1 end
 returning count into new_count;
 return new_count <= max_count;
end;
$$;
revoke all on function public.journal_consume_budget(text) from public, anon;
grant execute on function public.journal_consume_budget(text) to authenticated;
-- Copy valid legacy preferences. Ignore malformed user-editable metadata;
-- never replace a newer row on a repeated migration. Retain legacy metadata
-- until rollout verification so rollback does not destroy the old history.
do $$
declare u record; entry record; v jsonb; d date; target numeric; days integer;
begin
 for u in select id, raw_user_meta_data from auth.users loop
  for entry in select key,value from jsonb_each(coalesce(u.raw_user_meta_data,'{}'::jsonb)) loop
   begin
    if entry.key ~ '^journal_goal_(USD|GBP|EUR)$' then
     v := entry.value;
     if jsonb_typeof(v->'monthlyTarget') <> 'number' or jsonb_typeof(v->'tradingDays') <> 'number' then continue; end if;
     target := (v->>'monthlyTarget')::numeric;
     if (v->>'tradingDays')::numeric <> trunc((v->>'tradingDays')::numeric) then continue; end if;
     days := (v->>'tradingDays')::integer;
     if target between 0.01 and 999999999.99 and days between 1 and 31 then
      insert into public.journal_preferences values(u.id,right(entry.key,3),target,days) on conflict do nothing;
     end if;
    elsif entry.key ~ '^journal_rules_[0-9]{4}-[0-9]{2}-[0-9]{2}$' and jsonb_typeof(entry.value) = 'boolean' then
     d := substring(entry.key from 15)::date;
     if d <= current_date + 1 then
      insert into public.journal_discipline values(u.id,d,entry.value::text::boolean) on conflict do nothing;
     end if;
    end if;
   exception when invalid_text_representation or numeric_value_out_of_range or datetime_field_overflow or invalid_datetime_format then
    continue;
   end;
  end loop;
 end loop;
end;
$$;
commit;
