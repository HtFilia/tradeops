-- Demo schema v1. Run from the existing hourly retention job only after upgrade.
-- Ordinary/shared accounts are excluded even if an orphan guest row exists.
SET lock_timeout = '2s';
SET statement_timeout = '30s';
BEGIN;
WITH expired AS (
  SELECT u.id FROM public.users u
  JOIN public.demo_guests g ON g.user_id = u.id
  JOIN public.demo_cases c ON c.user_id = u.id
  WHERE u.principal_kind = 'guest'
    AND g.expires_at < CURRENT_TIMESTAMP - INTERVAL '24 hours'
  ORDER BY g.expires_at, u.id
  LIMIT 1000
  FOR UPDATE OF u, g, c SKIP LOCKED
)
DELETE FROM public.users u USING expired e
WHERE u.id = e.id AND u.principal_kind = 'guest';
COMMIT;
