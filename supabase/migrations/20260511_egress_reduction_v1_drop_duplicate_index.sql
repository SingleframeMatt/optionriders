-- Duplicate index cleanup: idx_journal_fills_user_date (pre-existing) already
-- covers (user_id, trade_date), making the index added in the prior migration
-- redundant. Drop the new one.
drop index if exists public.idx_journal_fills_user_trade_date;
