-- ONE-TIME DATA REPAIR. Already applied to the live database.
--
-- This is why schema.sql was split into migrations: it lived in a file whose
-- documented usage was "re-run it in the SQL editor", so every re-run replayed
-- data mutations like these against production rows.
--
-- Both statements are written to be safe if replayed, but they should not be
-- replayed. Do not add new repairs to this file — write a new migration.

-- Only copy legacy take_profit into TP1. Never clone the same price into
-- TP2/TP3 — that made one candle hit mark all three levels at once.
update public.signals
set take_profit_1 = coalesce(take_profit_1, take_profit)
where take_profit_1 is null;

-- Repair rows previously backfilled with TP2=TP3=TP1.
update public.signals
set take_profit_2 = null, take_profit_3 = null
where take_profit_1 is not null
  and take_profit_2 is not distinct from take_profit_1
  and take_profit_3 is not distinct from take_profit_1;
