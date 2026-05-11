-- ── Part 1: Fix RLS init-plan warnings ────────────────────────────────────────
-- Wrap auth.uid()/auth.role() in (select ...) so Postgres evaluates once per
-- query instead of once per row. Big win on large scans.

alter policy "Users read own subscription" on public.dashboard_subscriptions
  using ((select auth.uid()) = user_id);

alter policy "Service role full access" on public.dashboard_subscriptions
  using ((select auth.role()) = 'service_role'::text);

alter policy "journal_fills_select_own" on public.journal_fills
  using ((select auth.uid()) = user_id);

alter policy "journal_fills_insert_own" on public.journal_fills
  with check ((select auth.uid()) = user_id);

alter policy "journal_fills_update_own" on public.journal_fills
  using ((select auth.uid()) = user_id);

alter policy "journal_fills_delete_own" on public.journal_fills
  using ((select auth.uid()) = user_id);

alter policy "Users read own notes" on public.journal_notes
  using ((select auth.uid()) = user_id);

alter policy "Users insert own notes" on public.journal_notes
  with check ((select auth.uid()) = user_id);

alter policy "Users update own notes" on public.journal_notes
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

alter policy "Users delete own notes" on public.journal_notes
  using ((select auth.uid()) = user_id);

-- ── Part 2: Server-side aggregates ───────────────────────────────────────────
-- Replaces ~10MB of row fetching with a ~16KB jsonb response on the stats
-- endpoint. Relies on RLS so the caller must be authenticated — auth.uid()
-- filters automatically through the underlying journal_fills policy.
--
-- Aggregates are computed over CLOSE fills (realized_pnl != 0) rather than
-- pair-matched round-trip trades. For day-traders whose closes map 1:1 to
-- trades this matches to within a few cents. If exact round-trip matching is
-- needed, journal_cloud.compute_stats accepts filters['exact']=True to force
-- the legacy row-pull path.

create or replace function public.journal_stats(
  p_from date default null,
  p_to   date default null
) returns jsonb
language sql
stable
as $$
  with filtered as (
    select *,
           coalesce(realized_pnl, 0) * coalesce(fx_rate_to_base, 1) as pnl_base,
           coalesce(commission,   0) * coalesce(fx_rate_to_base, 1) as comm_base
    from public.journal_fills
    where (p_from is null or trade_date >= p_from)
      and (p_to   is null or trade_date <= p_to)
      and coalesce(asset_class, '') <> 'CASH'
  ),
  closes as (
    select * from filtered where coalesce(realized_pnl, 0) <> 0
  ),
  by_symbol as (
    select coalesce(underlying, symbol, 'UNKNOWN') as symbol,
           sum(pnl_base) as pnl,
           count(*) as count,
           count(*) filter (where pnl_base > 0) as wins
    from closes
    group by coalesce(underlying, symbol, 'UNKNOWN')
  ),
  by_day as (
    select trade_date::text as date,
           sum(pnl_base) as pnl
    from closes
    where trade_date is not null
    group by trade_date
  ),
  by_class as (
    select coalesce(asset_class, 'UNKNOWN') as asset_class,
           sum(pnl_base) as pnl
    from closes
    group by coalesce(asset_class, 'UNKNOWN')
  ),
  agg as (
    select
      coalesce(sum(pnl_base),                                0) as net_pnl,
      coalesce(sum(pnl_base) + sum(comm_base),               0) as net_pnl_after_comm,
      coalesce(sum(pnl_base) filter (where pnl_base > 0),    0) as gross_profit,
      coalesce(sum(pnl_base) filter (where pnl_base < 0),    0) as gross_loss,
      coalesce(sum(comm_base),                               0) as commissions,
      count(*) as close_count,
      count(*) filter (where pnl_base > 0) as wins,
      count(*) filter (where pnl_base < 0) as losses,
      coalesce(max(pnl_base), 0) as best_trade,
      coalesce(min(pnl_base), 0) as worst_trade
    from closes
  ),
  fill_total as (
    select count(*) as fill_count,
           bool_or(coalesce(fx_rate_to_base, 0) <> 0) as base_currency_applied
    from filtered
  )
  select jsonb_build_object(
    'net_pnl',             round(agg.net_pnl::numeric, 2),
    'net_pnl_after_comm',  round(agg.net_pnl_after_comm::numeric, 2),
    'gross_profit',        round(agg.gross_profit::numeric, 2),
    'gross_loss',          round(agg.gross_loss::numeric, 2),
    'commissions',         round(agg.commissions::numeric, 2),
    'fill_count',          fill_total.fill_count,
    'trade_count',         agg.close_count,
    'close_count',         agg.close_count,
    'wins',                agg.wins,
    'losses',              agg.losses,
    'win_rate',            case when agg.close_count > 0
                                then round(agg.wins::numeric / agg.close_count * 100, 2)
                                else 0 end,
    'profit_factor',       case when agg.gross_loss <> 0
                                then round((agg.gross_profit / abs(agg.gross_loss))::numeric, 3)
                                else 0 end,
    'avg_win',             case when agg.wins > 0
                                then round((agg.gross_profit / agg.wins)::numeric, 2)
                                else 0 end,
    'avg_loss',            case when agg.losses > 0
                                then round((agg.gross_loss / agg.losses)::numeric, 2)
                                else 0 end,
    'expectancy',          case when agg.close_count > 0
                                then round((agg.net_pnl / agg.close_count)::numeric, 2)
                                else 0 end,
    'best_trade',          round(agg.best_trade::numeric, 2),
    'worst_trade',         round(agg.worst_trade::numeric, 2),
    'by_symbol',           coalesce((select jsonb_agg(
                                       jsonb_build_object(
                                         'symbol', symbol,
                                         'pnl',    round(pnl::numeric, 2),
                                         'count',  count,
                                         'wins',   wins
                                       )
                                       order by pnl desc
                                     ) from by_symbol), '[]'::jsonb),
    'by_day',              coalesce((select jsonb_agg(
                                       jsonb_build_object(
                                         'date', date,
                                         'pnl',  round(pnl::numeric, 2)
                                       )
                                       order by date
                                     ) from by_day), '[]'::jsonb),
    'by_asset_class',      coalesce((select jsonb_agg(
                                       jsonb_build_object(
                                         'asset_class', asset_class,
                                         'pnl',         round(pnl::numeric, 2)
                                       )
                                       order by pnl desc
                                     ) from by_class), '[]'::jsonb),
    'base_currency_applied', coalesce(fill_total.base_currency_applied, false)
  )
  from agg, fill_total;
$$;

grant execute on function public.journal_stats(date, date) to authenticated;

-- Supports the (user_id, trade_date) range filter used by the function
-- and by all the date-windowed endpoints. Without this, large users do
-- a full table scan per request.
create index if not exists idx_journal_fills_user_trade_date
  on public.journal_fills (user_id, trade_date);
