//+------------------------------------------------------------------+
//| QauntifyBBMA.mq5                                                  |
//| Taught BBMA (Oma Ally) on XAUUSD — live publish, no AI gate.     |
//|                                                                    |
//| Doctrine:                                                          |
//|   H4 bias = close vs Mid BB AND EMA50 (both must agree)           |
//|   Primary: H1 re-entry after CSAK/CSM into MA5/10 + Mid BB        |
//|   Secondary: Extreme (MA5 outside BB) → MHV → confirm candle      |
//|                                                                    |
//| Keep QauntifyTickPush.mq5 attached for ticks/candles + outcomes.  |
//| Allow WebRequest for SignalApiUrl origin:                          |
//| Tools → Options → Expert Advisors                                  |
//+------------------------------------------------------------------+
#property strict
#property copyright "Qauntify"
#property version   "1.01"

input string AppSymbol       = "XAUUSD";
input string SignalApiUrl    = "https://web-seven-pi-76.vercel.app/api/mt5/signal";
input string WebhookSecret   = "906f61d7dbd1aa2c72cc19a7a0382ce61434f8bd5d6d6c65466912d9808097e4";
input bool   ShowBbmaStack   = true;  // draw BB + MA5/10 H/L + EMA50 on chart
input int    Confidence      = 75;
input int    MinBars         = 60;
input double StopAtrBuffer   = 0.5;
input double MaxStopAtr      = 2.5;
input int    SignalLookback  = 10;
input int    ExtremeLookback = 6;
input int    MhvLookback     = 8;

datetime lastEvaluatedBar = 0;
long     signalsOk = 0;
long     signalsFail = 0;
long     signalsSkip = 0;
int      lastHttp = 0;
string   lastStatus = "idle";
string   plottedNames[];   // short names we added (removed on deinit)

//--- indicator handles (H1) -----------------------------------------------
int hBb1 = INVALID_HANDLE;
int hMa5h1 = INVALID_HANDLE;
int hMa5l1 = INVALID_HANDLE;
int hMa10h1 = INVALID_HANDLE;
int hMa10l1 = INVALID_HANDLE;
int hEma501 = INVALID_HANDLE;
int hAtr1 = INVALID_HANDLE;
//--- H4 bias --------------------------------------------------------------
int hBb4 = INVALID_HANDLE;
int hEma504 = INVALID_HANDLE;

void PlotAdd(const int handle)
  {
   if(!ShowBbmaStack || handle == INVALID_HANDLE) return;
   if(!ChartIndicatorAdd(0, 0, handle))
     {
      Print("QauntifyBBMA: ChartIndicatorAdd failed ", GetLastError());
      return;
     }
   int n = ChartIndicatorsTotal(0, 0);
   if(n <= 0) return;
   int sz = ArraySize(plottedNames);
   ArrayResize(plottedNames, sz + 1);
   plottedNames[sz] = ChartIndicatorName(0, 0, n - 1);
  }

void PlotClear()
  {
   for(int i = 0; i < ArraySize(plottedNames); i++)
     {
      if(StringLen(plottedNames[i]) > 0)
         ChartIndicatorDelete(0, 0, plottedNames[i]);
     }
   ArrayResize(plottedNames, 0);
  }

string AuthHeaders()
  {
   return "Content-Type: application/json\r\n"
          "Authorization: Bearer " + WebhookSecret + "\r\n";
  }

int HttpPost(const string url, const string body)
  {
   char post[];
   char result[];
   string resultHeaders;
   StringToCharArray(body, post, 0, StringLen(body));
   return WebRequest("POST", url, AuthHeaders(), 15000, post, result, resultHeaders);
  }

bool Copy1(const int handle, const int buffer, const int shift, double &out)
  {
   double buf[];
   if(CopyBuffer(handle, buffer, shift, 1, buf) != 1) return false;
   out = buf[0];
   return true;
  }

bool RiskOk(const double entry, const double stop, const double atr)
  {
   if(atr <= 0.0) return false;
   return MathAbs(entry - stop) / atr <= MaxStopAtr;
  }

bool StructuralTps(const double entry, const double stop, const bool isLong,
                   const double target,
                   double &tp1, double &tp2, double &tp3)
  {
   double risk = MathAbs(entry - stop);
   if(risk <= 0.0) return false;
   double reach = isLong ? (target - entry) : (entry - target);
   double r1 = reach / risk;
   if(r1 <= 0.0) return false;
   if(isLong)
     {
      tp1 = entry + r1 * risk;
      tp2 = entry + (r1 + 1.0) * risk;
      tp3 = entry + (r1 + 2.0) * risk;
     }
   else
     {
      tp1 = entry - r1 * risk;
      tp2 = entry - (r1 + 1.0) * risk;
      tp3 = entry - (r1 + 2.0) * risk;
     }
   return true;
  }

// Returns 1=up, -1=down, 0=neutral
int HtfBias()
  {
   // iBands buffers: 0=BASE(mid), 1=UPPER, 2=LOWER — last closed H4 = shift 1
   double mid, ema50, close;
   if(!Copy1(hBb4, 0, 1, mid)) return 0;
   if(!Copy1(hEma504, 0, 1, ema50)) return 0;
   close = iClose(_Symbol, PERIOD_H4, 1);
   if(close > mid && close > ema50) return 1;
   if(close < mid && close < ema50) return -1;
   return 0;
  }

string ArmingSignal(const bool up)
  {
   // Arming must precede the pullback (shift 2). Confirm is shift 1.
   string found = "";
   for(int shift = 3; shift <= 2 + SignalLookback; shift++)
     {
      double upper, lower, mid, ma5, ma10, close;
      if(!Copy1(hBb1, 1, shift, upper)) continue;
      if(!Copy1(hBb1, 2, shift, lower)) continue;
      if(!Copy1(hBb1, 0, shift, mid)) continue;
      if(up)
        {
         if(!Copy1(hMa5h1, 0, shift, ma5)) continue;
         if(!Copy1(hMa10h1, 0, shift, ma10)) continue;
        }
      else
        {
         if(!Copy1(hMa5l1, 0, shift, ma5)) continue;
         if(!Copy1(hMa10l1, 0, shift, ma10)) continue;
        }
      close = iClose(_Symbol, PERIOD_H1, shift);
      double band = up ? upper : lower;
      if((up && close > band) || (!up && close < band))
         found = "csm";
      else if((up && close > ma5 && close > ma10 && close > mid) ||
              (!up && close < ma5 && close < ma10 && close < mid))
        {
         if(found == "") found = "csak";
        }
     }
   return found;
  }

bool Escaped(const bool above)
  {
   for(int shift = 1; shift <= ExtremeLookback; shift++)
     {
      double ma, band;
      if(above)
        {
         if(!Copy1(hMa5h1, 0, shift, ma)) continue;
         if(!Copy1(hBb1, 1, shift, band)) continue;
         if(ma > band) return true;
        }
      else
        {
         if(!Copy1(hMa5l1, 0, shift, ma)) continue;
         if(!Copy1(hBb1, 2, shift, band)) continue;
         if(ma < band) return true;
        }
     }
   return false;
  }

// Newest MHV bar shift in [2 .. 1+MhvLookback]; 0 if none
int MhvShift(const bool sell)
  {
   int best = 0;
   for(int shift = 2; shift <= 1 + MhvLookback; shift++)
     {
      double upper, lower;
      if(!Copy1(hBb1, 1, shift, upper)) continue;
      if(!Copy1(hBb1, 2, shift, lower)) continue;
      double high = iHigh(_Symbol, PERIOD_H1, shift);
      double low = iLow(_Symbol, PERIOD_H1, shift);
      double close = iClose(_Symbol, PERIOD_H1, shift);
      if(sell)
        {
         if(high >= upper && close < upper) { best = shift; break; }
        }
      else
        {
         if(low <= lower && close > lower) { best = shift; break; }
        }
     }
   // Prefer newest: loop from shift=2 upward already finds newest first
   return best;
  }

bool TryReentry(const int bias, string &direction, double &entry, double &stop,
                double &tp1, double &tp2, double &tp3, string &strategy,
                string &trigger, string &side)
  {
   if(bias == 0) return false;
   double atr;
   if(!Copy1(hAtr1, 0, 1, atr) || atr <= 0.0) return false;

   double ma5l_p, ma10l_p, mid_p, ma5h_p, ma10h_p;
   double ma10l, ma10h, mid, ma5h, ma5l;
   if(!Copy1(hMa5l1, 0, 2, ma5l_p)) return false;
   if(!Copy1(hMa10l1, 0, 2, ma10l_p)) return false;
   if(!Copy1(hBb1, 0, 2, mid_p)) return false;
   if(!Copy1(hMa5h1, 0, 2, ma5h_p)) return false;
   if(!Copy1(hMa10h1, 0, 2, ma10h_p)) return false;
   if(!Copy1(hMa10l1, 0, 1, ma10l)) return false;
   if(!Copy1(hMa10h1, 0, 1, ma10h)) return false;
   if(!Copy1(hBb1, 0, 1, mid)) return false;
   if(!Copy1(hMa5h1, 0, 1, ma5h)) return false;
   if(!Copy1(hMa5l1, 0, 1, ma5l)) return false;

   double pullLow = iLow(_Symbol, PERIOD_H1, 2);
   double pullHigh = iHigh(_Symbol, PERIOD_H1, 2);
   double pullClose = iClose(_Symbol, PERIOD_H1, 2);
   double barLow = iLow(_Symbol, PERIOD_H1, 1);
   double barHigh = iHigh(_Symbol, PERIOD_H1, 1);
   double barClose = iClose(_Symbol, PERIOD_H1, 1);

   if(bias > 0)
     {
      trigger = ArmingSignal(true);
      if(trigger == "") return false;
      if(!(pullLow <= ma5l_p && pullClose > ma10l_p && pullClose > mid_p &&
           barClose > pullClose && barClose > ma10l && barClose > mid))
         return false;
      entry = barClose;
      stop = MathMin(pullLow, MathMin(barLow, ma10l)) - StopAtrBuffer * atr;
      if(!(stop < entry && RiskOk(entry, stop, atr))) return false;
      double target = MathMax(ma5h, ma10h);
      if(!StructuralTps(entry, stop, true, target, tp1, tp2, tp3)) return false;
      direction = "long";
      strategy = "bbma_reentry";
      side = "support";
      return true;
     }

   trigger = ArmingSignal(false);
   if(trigger == "") return false;
   if(!(pullHigh >= ma5h_p && pullClose < ma10h_p && pullClose < mid_p &&
        barClose < pullClose && barClose < ma10h && barClose < mid))
      return false;
   entry = barClose;
   stop = MathMax(pullHigh, MathMax(barHigh, ma10h)) + StopAtrBuffer * atr;
   if(!(stop > entry && RiskOk(entry, stop, atr))) return false;
   double target = MathMin(ma5l, ma10l);
   if(!StructuralTps(entry, stop, false, target, tp1, tp2, tp3)) return false;
   direction = "short";
   strategy = "bbma_reentry";
   side = "resistance";
   return true;
  }

bool TryExtremeMhv(const int bias, string &direction, double &entry, double &stop,
                   double &tp1, double &tp2, double &tp3, string &strategy,
                   string &side)
  {
   double atr;
   if(!Copy1(hAtr1, 0, 1, atr) || atr <= 0.0) return false;
   double barOpen = iOpen(_Symbol, PERIOD_H1, 1);
   double barHigh = iHigh(_Symbol, PERIOD_H1, 1);
   double barLow = iLow(_Symbol, PERIOD_H1, 1);
   double barClose = iClose(_Symbol, PERIOD_H1, 1);

   // short Extreme — don't fade strong H4 up
   if(bias != 1 && Escaped(true))
     {
      int mhv = MhvShift(true);
      double ma5h;
      if(mhv > 0 && Copy1(hMa5h1, 0, 1, ma5h))
        {
         if(barClose < barOpen && barHigh >= ma5h && barClose < ma5h)
           {
            entry = barClose;
            double spikeHigh = barHigh;
            for(int s = 1; s <= mhv; s++)
               spikeHigh = MathMax(spikeHigh, iHigh(_Symbol, PERIOD_H1, s));
            stop = spikeHigh + StopAtrBuffer * atr;
            if(stop > entry && RiskOk(entry, stop, atr))
              {
               double ma5l, ma10l;
               if(Copy1(hMa5l1, 0, 1, ma5l) && Copy1(hMa10l1, 0, 1, ma10l))
                 {
                  double target = MathMax(ma5l, ma10l);
                  if(StructuralTps(entry, stop, false, target, tp1, tp2, tp3))
                    {
                     direction = "short";
                     strategy = "bbma_extreme";
                     side = "resistance";
                     return true;
                    }
                 }
              }
           }
        }
     }

   // long Extreme — don't fade strong H4 down
   if(bias != -1 && Escaped(false))
     {
      int mhv = MhvShift(false);
      double ma5l;
      if(mhv > 0 && Copy1(hMa5l1, 0, 1, ma5l))
        {
         if(barClose > barOpen && barLow <= ma5l && barClose > ma5l)
           {
            entry = barClose;
            double spikeLow = barLow;
            for(int s = 1; s <= mhv; s++)
               spikeLow = MathMin(spikeLow, iLow(_Symbol, PERIOD_H1, s));
            stop = spikeLow - StopAtrBuffer * atr;
            if(stop < entry && RiskOk(entry, stop, atr))
              {
               double ma5h, ma10h;
               if(Copy1(hMa5h1, 0, 1, ma5h) && Copy1(hMa10h1, 0, 1, ma10h))
                 {
                  double target = MathMin(ma5h, ma10h);
                  if(StructuralTps(entry, stop, true, target, tp1, tp2, tp3))
                    {
                     direction = "long";
                     strategy = "bbma_extreme";
                     side = "support";
                     return true;
                    }
                 }
              }
           }
        }
     }
   return false;
  }

bool Publish(const string direction, const double entry, const double stop,
             const double tp1, const double tp2, const double tp3,
             const string strategy, const string trigger, const string side,
             const int bias)
  {
   if(StringLen(WebhookSecret) < 8)
     {
      lastStatus = "set WebhookSecret";
      return false;
     }
   datetime barTime = iTime(_Symbol, PERIOD_H1, 1);
   string biasStr = bias > 0 ? "up" : (bias < 0 ? "down" : "null");
   string trigJson = trigger == "" ? "null" : ("\"" + trigger + "\"");
   string body = StringFormat(
      "{\"symbol\":\"%s\",\"timeframe\":\"1h\",\"direction\":\"%s\","
      "\"entry\":%.5f,\"stop_loss\":%.5f,\"take_profit\":%.5f,"
      "\"take_profit_2\":%.5f,\"take_profit_3\":%.5f,\"confidence\":%d,"
      "\"rationale\":\"Taught BBMA %s (H4 bias %s, MT5 EA live)\","
      "\"bar_time\":%d,"
      "\"indicators\":{\"strategy\":\"%s\",\"side\":\"%s\",\"trigger\":%s,"
      "\"htf_bias\":\"%s\",\"source\":\"mt5_ea\",\"doctrine\":\"taught_mtf\"}}",
      AppSymbol, direction, entry, stop, tp1, tp2, tp3, Confidence,
      strategy, biasStr, (int)barTime, strategy, side, trigJson, biasStr);

   lastHttp = HttpPost(SignalApiUrl, body);
   if(lastHttp == 200)
     {
      signalsOk++;
      lastStatus = "published " + strategy + " " + direction;
      return true;
     }
   if(lastHttp == 409)
     {
      signalsSkip++;
      lastStatus = "skip: open signal exists";
      return false;
     }
   signalsFail++;
   if(lastHttp == -1)
      lastStatus = StringFormat("WebRequest err %d", GetLastError());
   else
      lastStatus = StringFormat("HTTP %d", lastHttp);
   Print("QauntifyBBMA: ", lastStatus);
   return false;
  }

void UpdateComment()
  {
   Comment(StringFormat(
      "QauntifyBBMA | ok:%d fail:%d skip:%d | %s | lastH1:%s",
      signalsOk, signalsFail, signalsSkip, lastStatus,
      TimeToString(lastEvaluatedBar, TIME_DATE|TIME_MINUTES)));
  }

int OnInit()
  {
   if(_Symbol != AppSymbol && StringFind(_Symbol, "XAU") < 0 && StringFind(_Symbol, "GOLD") < 0)
      Print("QauntifyBBMA: attach on XAU/GOLD chart (AppSymbol=", AppSymbol, ")");

   hBb1 = iBands(_Symbol, PERIOD_H1, 20, 0, 2.0, PRICE_CLOSE);
   hMa5h1 = iMA(_Symbol, PERIOD_H1, 5, 0, MODE_LWMA, PRICE_HIGH);
   hMa5l1 = iMA(_Symbol, PERIOD_H1, 5, 0, MODE_LWMA, PRICE_LOW);
   hMa10h1 = iMA(_Symbol, PERIOD_H1, 10, 0, MODE_LWMA, PRICE_HIGH);
   hMa10l1 = iMA(_Symbol, PERIOD_H1, 10, 0, MODE_LWMA, PRICE_LOW);
   hEma501 = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   hAtr1 = iATR(_Symbol, PERIOD_H1, 14);
   hBb4 = iBands(_Symbol, PERIOD_H4, 20, 0, 2.0, PRICE_CLOSE);
   hEma504 = iMA(_Symbol, PERIOD_H4, 50, 0, MODE_EMA, PRICE_CLOSE);

   if(hBb1 == INVALID_HANDLE || hMa5h1 == INVALID_HANDLE || hMa5l1 == INVALID_HANDLE ||
      hMa10h1 == INVALID_HANDLE || hMa10l1 == INVALID_HANDLE || hEma501 == INVALID_HANDLE ||
      hAtr1 == INVALID_HANDLE || hBb4 == INVALID_HANDLE || hEma504 == INVALID_HANDLE)
     {
      Print("QauntifyBBMA: indicator init failed");
      return INIT_FAILED;
     }

   // Visible BBMA stack (same handles used for signal math). Best on H1 chart.
   PlotAdd(hBb1);      // BB 20/2
   PlotAdd(hMa5h1);    // LWMA 5 High
   PlotAdd(hMa5l1);    // LWMA 5 Low
   PlotAdd(hMa10h1);   // LWMA 10 High
   PlotAdd(hMa10l1);   // LWMA 10 Low
   PlotAdd(hEma501);   // EMA 50

   UpdateComment();
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   PlotClear();
   IndicatorRelease(hBb1);
   IndicatorRelease(hMa5h1);
   IndicatorRelease(hMa5l1);
   IndicatorRelease(hMa10h1);
   IndicatorRelease(hMa10l1);
   IndicatorRelease(hEma501);
   IndicatorRelease(hAtr1);
   IndicatorRelease(hBb4);
   IndicatorRelease(hEma504);
   Comment("");
  }

void OnTick()
  {
   if(Bars(_Symbol, PERIOD_H1) < MinBars + 5) return;
   if(Bars(_Symbol, PERIOD_H4) < MinBars) return;

   datetime barTime = iTime(_Symbol, PERIOD_H1, 1); // last closed H1
   if(barTime == 0 || barTime == lastEvaluatedBar) return;
   lastEvaluatedBar = barTime;

   int bias = HtfBias();
   string direction = "", strategy = "", trigger = "", side = "";
   double entry = 0, stop = 0, tp1 = 0, tp2 = 0, tp3 = 0;

   bool found = TryReentry(bias, direction, entry, stop, tp1, tp2, tp3,
                           strategy, trigger, side);
   if(!found)
      found = TryExtremeMhv(bias, direction, entry, stop, tp1, tp2, tp3,
                            strategy, side);

   if(found)
      Publish(direction, entry, stop, tp1, tp2, tp3, strategy, trigger, side, bias);
   else
      lastStatus = StringFormat("no setup (H4 %s)",
         bias > 0 ? "up" : (bias < 0 ? "down" : "flat"));

   UpdateComment();
  }
