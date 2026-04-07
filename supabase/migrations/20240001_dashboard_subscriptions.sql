-- =============================================================
-- Option Riders — Dashboard Subscription Schema
-- =============================================================
-- Run this in the Supabase SQL editor (or via supabase db push).
-- One row per active subscription. Webhook events upsert here.
-- =============================================================

CREATE TABLE IF NOT EXISTS public.dashboard_subscriptions (
  id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                 uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  email                   text        NOT NULL DEFAULT '',
  stripe_customer_id      text,
  stripe_subscription_id  text        UNIQUE,        -- upsert key for webhook events
  product_key             text        NOT NULL DEFAULT 'dashboard',
  -- Stripe lifecycle statuses: trialing | active | past_due | unpaid | canceled | incomplete | incomplete_expired
  status                  text        NOT NULL DEFAULT 'inactive',
  trial_ends_at           timestamptz,
  current_period_ends_at  timestamptz,
  created_at              timestamptz NOT NULL DEFAULT now(),
  updated_at              timestamptz NOT NULL DEFAULT now(),

  UNIQUE (user_id, product_key)   -- one dashboard row per user
);

-- Auto-bump updated_at on every write
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_dashboard_subscriptions_updated_at ON public.dashboard_subscriptions;
CREATE TRIGGER trg_dashboard_subscriptions_updated_at
  BEFORE UPDATE ON public.dashboard_subscriptions
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------
-- Row-Level Security
-- ---------------------------------------------------------------
ALTER TABLE public.dashboard_subscriptions ENABLE ROW LEVEL SECURITY;

-- Users can read their own row (used by the subscription-status endpoint
-- as a fallback; the endpoint itself uses service-role key, so this
-- policy mainly protects direct client-side Supabase queries).
CREATE POLICY "Users read own subscription"
  ON public.dashboard_subscriptions
  FOR SELECT
  USING (auth.uid() = user_id);

-- Only service-role (our backend) can insert / update / delete.
-- No user-facing client should mutate subscription status directly.
CREATE POLICY "Service role full access"
  ON public.dashboard_subscriptions
  FOR ALL
  USING (auth.role() = 'service_role');

-- ---------------------------------------------------------------
-- Optional helper: fast lookup by customer ID (webhook path)
-- ---------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_dashboard_subscriptions_customer
  ON public.dashboard_subscriptions (stripe_customer_id);

CREATE INDEX IF NOT EXISTS idx_dashboard_subscriptions_user
  ON public.dashboard_subscriptions (user_id);
