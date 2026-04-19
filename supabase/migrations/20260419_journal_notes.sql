-- =============================================================
-- Option Riders — Trade Journal Notes
-- =============================================================
-- One row per trade the user has notes on. Trade identity =
-- (user_id, symbol, close_datetime) — stable across IBKR re-syncs
-- because close_datetime is the timestamp of the round-trip's
-- closing fill and doesn't change once the trade is flat.
-- =============================================================

CREATE TABLE IF NOT EXISTS public.journal_notes (
  id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  symbol          text        NOT NULL,
  close_datetime  text        NOT NULL,
  trade_date      text,
  body            text        NOT NULL DEFAULT '',
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),

  UNIQUE (user_id, symbol, close_datetime)
);

CREATE INDEX IF NOT EXISTS idx_journal_notes_user_date
  ON public.journal_notes (user_id, trade_date);

-- Auto-bump updated_at on every write (reuses set_updated_at() if present)
DROP TRIGGER IF EXISTS trg_journal_notes_updated_at ON public.journal_notes;
CREATE TRIGGER trg_journal_notes_updated_at
  BEFORE UPDATE ON public.journal_notes
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------
-- Row-Level Security: users can CRUD their own notes only.
-- ---------------------------------------------------------------
ALTER TABLE public.journal_notes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users read own notes"
  ON public.journal_notes
  FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users insert own notes"
  ON public.journal_notes
  FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users update own notes"
  ON public.journal_notes
  FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users delete own notes"
  ON public.journal_notes
  FOR DELETE
  USING (auth.uid() = user_id);
