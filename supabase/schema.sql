-- Horizons: Supabase schema (decisions, trades, trade_closes, notes) with row-level security.
--
-- Paste this whole file into Supabase > SQL Editor > New query and press Run. It is safe to run
-- again: tables and functions are created only if missing, and policies are replaced.
--
-- Who can read and write: only the signed-in user listed in public.app_owner, and only their own
-- rows. Nobody else (including other signed-up users and the public key on its own) can read or
-- write anything. The GitHub workflows use the secret key, which bypasses row-level security, to
-- fill trades at the close, mark them to market and score decisions.
--
-- After your first magic-link login, add yourself as the owner (once), replacing the email:
--   insert into public.app_owner (user_id)
--   select id from auth.users where email = 'you@example.com'
--   on conflict do nothing;

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- owner
create table if not exists public.app_owner (
  user_id uuid primary key references auth.users (id) on delete cascade,
  added_at timestamptz not null default now()
);
alter table public.app_owner enable row level security;
-- no policies on app_owner: the app cannot read or change it, only the SQL editor and the secret key

create or replace function public.is_owner()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (select 1 from public.app_owner o where o.user_id = (select auth.uid()));
$$;
revoke all on function public.is_owner() from public;
grant execute on function public.is_owner() to authenticated;

-- ---------------------------------------------------------------- decisions
create table if not exists public.decisions (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null default auth.uid() references auth.users (id) on delete cascade,
  created_at     timestamptz not null default now(),
  decision_date  date not null,
  country        text not null check (country in ('BR', 'MX', 'FR', 'GOLD')),
  instrument     text not null,                     -- book code, e.g. USDBRL, OATBUND, XAUUSD
  instrument_label text,                            -- as written in the record, e.g. "USD/BRL"
  action         text not null check (action in ('Buy', 'Sell', 'Hold', 'Close', 'No trade')),
  risk_pct       numeric not null default 0 check (risk_pct >= 0 and risk_pct <= 2),
  probability    numeric check (probability > 0 and probability < 1),
  horizon        date,
  entry_trigger  text,
  stop_text      text,
  stop_level     numeric,
  thesis         text,
  key_factors    text,
  change_mind    text,
  vs_consensus   text,
  raw            text not null,                     -- the pasted block, unchanged
  trade_id       uuid,
  -- written by the scoring workflow
  outcome        smallint check (outcome in (0, 1)),
  brier          numeric,
  scored_at      timestamptz,
  score_note     text,
  constraint buy_sell_needs_size check (action not in ('Buy', 'Sell') or (risk_pct > 0 and stop_level is not null))
);
create index if not exists decisions_user_country on public.decisions (user_id, country, decision_date desc);

-- ---------------------------------------------------------------- trades
create table if not exists public.trades (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null default auth.uid() references auth.users (id) on delete cascade,
  created_at     timestamptz not null default now(),
  decision_id    uuid references public.decisions (id) on delete set null,
  source         text not null default 'decision' check (source in ('decision', 'algorithm', 'manual')),
  instrument     text not null,
  direction      text not null check (direction in ('long', 'short')),
  risk_pct       numeric not null check (risk_pct > 0 and risk_pct <= 2),
  stop_level     numeric not null,
  target_level   numeric,
  horizon        date,
  requested_at   timestamptz not null default now(),
  status         text not null default 'pending' check (status in ('pending', 'open', 'closed', 'rejected')),
  note           text,
  -- written by the daily workflow (fill at the next end-of-day close, marks, exit)
  entry_date     date,
  entry_value    numeric,
  notional_usd   numeric,
  risk_usd       numeric,
  duration       numeric,
  series_used    text,                               -- the price series the fill used; marks keep using it
  last_date      date,
  last_value     numeric,
  pnl_price      numeric,
  pnl_carry      numeric,
  pnl_cost       numeric,
  pnl_total      numeric,
  marks          jsonb not null default '[]'::jsonb,   -- [[date, value, price, carry, cost, total], ...]
  exit_date      date,
  exit_value     numeric,
  exit_reason    text,                               -- stop, target, closed, rejected
  reject_reason  text,
  updated_at     timestamptz
);
create index if not exists trades_user_status on public.trades (user_id, status);
alter table public.trades add column if not exists series_used text;   -- for projects created before this column existed

-- ---------------------------------------------------------------- close requests
create table if not exists public.trade_closes (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null default auth.uid() references auth.users (id) on delete cascade,
  trade_id       uuid not null references public.trades (id) on delete cascade,
  requested_at   timestamptz not null default now(),
  note           text,
  processed_at   timestamptz                          -- set by the workflow when the exit fills
);
create index if not exists trade_closes_trade on public.trade_closes (trade_id);

-- ---------------------------------------------------------------- notes
create table if not exists public.notes (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null default auth.uid() references auth.users (id) on delete cascade,
  created_at     timestamptz not null default now(),
  trade_id       uuid references public.trades (id) on delete cascade,
  decision_id    uuid references public.decisions (id) on delete cascade,
  country        text check (country in ('BR', 'MX', 'FR', 'GOLD')),
  body           text not null check (length(body) between 1 and 5000)
);

-- ---------------------------------------------------------------- row-level security
alter table public.decisions    enable row level security;
alter table public.trades       enable row level security;
alter table public.trade_closes enable row level security;
alter table public.notes        enable row level security;

-- read: own rows, owner only
drop policy if exists "owner reads decisions" on public.decisions;
create policy "owner reads decisions" on public.decisions for select to authenticated
  using (user_id = (select auth.uid()) and (select public.is_owner()));
drop policy if exists "owner reads trades" on public.trades;
create policy "owner reads trades" on public.trades for select to authenticated
  using (user_id = (select auth.uid()) and (select public.is_owner()));
drop policy if exists "owner reads closes" on public.trade_closes;
create policy "owner reads closes" on public.trade_closes for select to authenticated
  using (user_id = (select auth.uid()) and (select public.is_owner()));
drop policy if exists "owner reads notes" on public.notes;
create policy "owner reads notes" on public.notes for select to authenticated
  using (user_id = (select auth.uid()) and (select public.is_owner()));

-- write: the app adds decisions, trade requests (unfilled), close requests and notes
drop policy if exists "owner adds decisions" on public.decisions;
create policy "owner adds decisions" on public.decisions for insert to authenticated
  with check (user_id = (select auth.uid()) and (select public.is_owner()) and outcome is null and brier is null);
drop policy if exists "owner links decision to trade" on public.decisions;
create policy "owner links decision to trade" on public.decisions for update to authenticated
  using (user_id = (select auth.uid()) and (select public.is_owner()))
  with check (user_id = (select auth.uid()) and (select public.is_owner()));
drop policy if exists "owner requests trades" on public.trades;
create policy "owner requests trades" on public.trades for insert to authenticated
  with check (user_id = (select auth.uid()) and (select public.is_owner()) and status = 'pending' and entry_value is null and pnl_total is null);
drop policy if exists "owner cancels pending trades" on public.trades;
create policy "owner cancels pending trades" on public.trades for delete to authenticated
  using (user_id = (select auth.uid()) and (select public.is_owner()) and status = 'pending');
drop policy if exists "owner requests closes" on public.trade_closes;
create policy "owner requests closes" on public.trade_closes for insert to authenticated
  with check (user_id = (select auth.uid()) and (select public.is_owner()) and processed_at is null);
drop policy if exists "owner adds notes" on public.notes;
create policy "owner adds notes" on public.notes for insert to authenticated
  with check (user_id = (select auth.uid()) and (select public.is_owner()));
drop policy if exists "owner deletes notes" on public.notes;
create policy "owner deletes notes" on public.notes for delete to authenticated
  using (user_id = (select auth.uid()) and (select public.is_owner()));

-- only the trade link may change on a decision from the app; scores come from the workflow
create or replace function public.decisions_guard()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if (select auth.role()) = 'authenticated' then
    if (to_jsonb(new) - 'trade_id') is distinct from (to_jsonb(old) - 'trade_id') then
      raise exception 'Only the trade link of a decision can be changed from the app';
    end if;
  end if;
  return new;
end;
$$;
drop trigger if exists decisions_guard on public.decisions;
create trigger decisions_guard before update on public.decisions for each row execute function public.decisions_guard();

-- the public (anon) role gets nothing
revoke all on public.decisions, public.trades, public.trade_closes, public.notes, public.app_owner from anon;
grant select, insert, update on public.decisions to authenticated;
grant select, insert, delete on public.trades to authenticated;
grant select, insert on public.trade_closes to authenticated;
grant select, insert, delete on public.notes to authenticated;
