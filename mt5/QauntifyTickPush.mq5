//+------------------------------------------------------------------+
//| QauntifyTickPush.mq5                                              |
//| 1) Pushes bid/ask ticks → /api/mt5/tick (SL/TP + live mid snap)   |
//| 2) Pushes closed M1 OHLC → /api/mt5/candles (pattern detection)   |
//|                                                                    |
//| Allow WebRequest for the ApiUrl / CandleApiUrl origin:            |
//| Tools → Options → Expert Advisors                                 |
//+------------------------------------------------------------------+
#property strict

input string AppSymbol      = "XAUUSD";
input string ApiUrl         = "https://web-seven-pi-76.vercel.app/api/mt5/tick";
input string CandleApiUrl   = "https://web-seven-pi-76.vercel.app/api/mt5/candles";
input string WebhookSecret  = "906f61d7dbd1aa2c72cc19a7a0382ce61434f8bd5d6d6c65466912d9808097e4";
input int    MinIntervalMs  = 150;
input double MinPriceMove   = 0.0;
input int    BackfillBars   = 300;   // closed M1 bars sent on init

double   lastSentMid    = 0.0;
uint     lastSentTick   = 0;
datetime lastClosedBar  = 0;
long     ticksSeen      = 0;
long     sendsOk        = 0;
long     sendsFailed    = 0;
long     candleSendsOk  = 0;
long     candleFails    = 0;
int      lastStatus     = 0;
int      lastCandleHttp = 0;

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

void UpdateStatusComment()
  {
   Comment(StringFormat(
      "QauntifyTickPush | ticks OK:%d fail:%d | candles OK:%d fail:%d | mid:%.2f | lastBar:%s",
      sendsOk, sendsFailed, candleSendsOk, candleFails, lastSentMid,
      TimeToString(lastClosedBar, TIME_DATE|TIME_MINUTES)));
  }

string CandleJson(const int shift)
  {
   datetime t = iTime(_Symbol, PERIOD_M1, shift);
   double o = iOpen(_Symbol, PERIOD_M1, shift);
   double h = iHigh(_Symbol, PERIOD_M1, shift);
   double l = iLow(_Symbol, PERIOD_M1, shift);
   double c = iClose(_Symbol, PERIOD_M1, shift);
   long vol = iTickVolume(_Symbol, PERIOD_M1, shift);
   return StringFormat(
      "{\"open_time\":%d,\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%d}",
      (int)t, o, h, l, c, (int)vol);
  }

bool PushCandlesJson(const string candlesArrayJson)
  {
   string body = StringFormat(
      "{\"symbol\":\"%s\",\"timeframe\":\"1m\",\"candles\":%s}",
      AppSymbol, candlesArrayJson);
   lastCandleHttp = HttpPost(CandleApiUrl, body);
   if(lastCandleHttp == 200)
     {
      candleSendsOk++;
      return true;
     }
   candleFails++;
   if(lastCandleHttp == -1)
      Print("QauntifyTickPush: candle WebRequest failed, error ", GetLastError());
   else
      Print("QauntifyTickPush: candle API HTTP ", lastCandleHttp);
   return false;
  }

void BackfillClosedM1()
  {
   int total = Bars(_Symbol, PERIOD_M1);
   int n = BackfillBars;
   if(n < 60) n = 60;
   if(total <= 1) return;
   if(n > total - 1) n = total - 1;

   string arr = "[";
   // Oldest → newest among closed bars (shift n … 1).
   for(int shift = n; shift >= 1; shift--)
     {
      if(shift < n) arr += ",";
      arr += CandleJson(shift);
     }
   arr += "]";
   if(PushCandlesJson(arr))
     {
      lastClosedBar = iTime(_Symbol, PERIOD_M1, 1);
      Print("QauntifyTickPush: backfilled ", n, " closed M1 bars");
     }
  }

void MaybePushClosedM1()
  {
   datetime closed = iTime(_Symbol, PERIOD_M1, 1);
   if(closed <= 0 || closed == lastClosedBar) return;
   string arr = "[" + CandleJson(1) + "]";
   if(PushCandlesJson(arr))
      lastClosedBar = closed;
  }

int OnInit()
  {
   if(WebhookSecret == "")
      Print("QauntifyTickPush: WebhookSecret is empty.");
   BackfillClosedM1();
   UpdateStatusComment();
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   Comment("");
  }

void OnTick()
  {
   ticksSeen++;
   MaybePushClosedM1();

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(bid <= 0.0 || ask <= 0.0 || ask < bid)
      return;
   double mid = (bid + ask) * 0.5;
   bool dueToSend = GetTickCount() - lastSentTick >= (uint)MinIntervalMs
                    && (MinPriceMove <= 0.0 || MathAbs(mid - lastSentMid) >= MinPriceMove);

   if(dueToSend)
     {
      string body = StringFormat(
         "{\"symbol\":\"%s\",\"bid\":%.5f,\"ask\":%.5f,\"mid\":%.5f,\"price\":%.5f,\"time\":%d}",
         AppSymbol, bid, ask, mid, mid, (int)TimeCurrent());

      lastStatus = HttpPost(ApiUrl, body);

      if(lastStatus == -1)
        {
         sendsFailed++;
         Print("QauntifyTickPush: tick WebRequest failed, error ", GetLastError());
        }
      else if(lastStatus != 200)
        {
         sendsFailed++;
         Print("QauntifyTickPush: tick API HTTP ", lastStatus);
        }
      else
        {
         sendsOk++;
         lastSentMid  = mid;
         lastSentTick = GetTickCount();
        }
     }
   UpdateStatusComment();
  }
//+------------------------------------------------------------------+
