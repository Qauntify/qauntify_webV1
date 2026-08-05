export function MethodologyNote() {
  return (
    <div className="mt-4 space-y-2 text-[11px] leading-relaxed text-slate/60">
      <p>
        <strong className="text-slate/80">How R is counted.</strong> R = reward ÷ risk, where risk is the
        distance from entry to stop. Every trade is scored as a scale-out, matching the three targets on
        the signal: one third of the position is booked at each of TP1, TP2 and TP3. Once TP1 is banked,
        the remainder is treated as trailed to breakeven, so banking TP1 locks a win even if price later
        tags the original stop. A trade that runs to the final target is therefore <strong>+2R</strong>,
        not +3R. A trade that banks TP1 and then reverses into the stop keeps about <strong>+0.33R</strong>.
        A stop hit before any target is a full −1R.
      </p>
      <p>
        <strong className="text-slate/80">Costs are deducted.</strong> Every trade is charged an estimated
        round-trip cost — spread plus commission — before it counts: 20&nbsp;bps on crypto, 2&nbsp;bps on
        gold, 1.5&nbsp;bps on GBPUSD. Cost is a share of price while R is a share of the stop distance, so
        tighter stops carry proportionally more of it. Gross is shown next to net so the gap is visible.
      </p>
      <p>
        <strong className="text-slate/80">Gold prices track your broker.</strong> XAUUSD
        1m structure requires closed MT5 candles from your EA (no PAXG mix);
        entry snaps to a fresh MT5 mid. Gold signals are refused if candles or
        ticks are stale. 1m scalps only fire in London/New York sessions.
      </p>
      <p>
        Every closed signal is included — nothing is cherry-picked or removed after the fact. Outcomes are
        read from candle data, so a bar touching both the stop and a target is scored as the stop. Past
        performance is not financial advice.
      </p>
    </div>
  );
}
