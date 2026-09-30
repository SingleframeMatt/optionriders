-- OptionRiders TradingView bundle access queue.
-- Stripe webhooks are the source of truth; only the service role may mutate rows.

CREATE TABLE IF NOT EXISTS public.script_access_requests (
  id                         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  stripe_checkout_session_id text        UNIQUE NOT NULL,
  stripe_customer_id         text,
  stripe_subscription_id     text,
  stripe_payment_intent_id   text,
  email                      text        NOT NULL DEFAULT '',
  tradingview_username       text        NOT NULL,
  plan                       text        NOT NULL CHECK (plan IN ('monthly', 'lifetime')),
  entitlement_status         text        NOT NULL DEFAULT 'active',
  grant_status               text        NOT NULL DEFAULT 'pending'
                                           CHECK (grant_status IN ('pending', 'granted', 'removed')),
  current_period_ends_at     timestamptz,
  created_at                 timestamptz NOT NULL DEFAULT now(),
  updated_at                 timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_script_access_subscription
  ON public.script_access_requests (stripe_subscription_id);

CREATE INDEX IF NOT EXISTS idx_script_access_payment_intent
  ON public.script_access_requests (stripe_payment_intent_id);

CREATE INDEX IF NOT EXISTS idx_script_access_queue
  ON public.script_access_requests (entitlement_status, grant_status, created_at);

DROP TRIGGER IF EXISTS trg_script_access_requests_updated_at ON public.script_access_requests;
CREATE TRIGGER trg_script_access_requests_updated_at
  BEFORE UPDATE ON public.script_access_requests
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.script_access_requests ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role manages script access"
  ON public.script_access_requests
  FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');
