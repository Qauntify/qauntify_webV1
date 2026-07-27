export function MethodologyNote() {
  return (
    <div className="mt-4 space-y-2 text-[11px] leading-relaxed text-slate/60">
      <p>
        <strong className="text-slate/80">How R is counted.</strong> R = reward ÷ risk, where risk is the
        distance from entry to stop. Every trade is scored as a scale-out, matching the three targets on
        the signal: one third of the position is booked at each of TP1, TP2 and TP3, and the stop moves to
        breakeven once TP1 is banked. A trade that runs to the final target is therefore{" "}
        <strong>+2R</strong>, not +3R. A trade that banks TP1 and then reverses is <strong>+0.33R</strong>,
        not −1R. Only a stop hit before any target is a full −1R.
      </p>
      <p>
        <strong className="text-slate/80">Costs are deducted.</strong> Every trade is charged an estimated
        round-trip cost — spread plus commission — before it counts: 20&nbsp;bps on crypto, 2&nbsp;bps on
        gold, 1.5&nbsp;bps on GBPUSD. Cost is a share of price while R is a share of the stop distance, so
        tighter stops carry proportionally more of it. Gross is shown next to net so the gap is visible.
      </p>
      <p>
        <strong className="text-slate/80">Gold prices are futures.</strong> XAUUSD levels are derived from
        the front-month COMEX gold future (GC=F), not spot gold. The two differ by a small basis that also
        steps at contract roll, so prices will not match a spot gold feed exactly.
      </p>
      <p>
        Every closed signal is included — nothing is cherry-picked or removed after the fact. Outcomes are
        read from candle data, so a bar touching both the stop and a target is scored as the stop. Past
        performance is not financial advice.
      </p>
    </div>
  );
}
