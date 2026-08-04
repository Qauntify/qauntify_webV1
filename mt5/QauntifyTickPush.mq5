//+------------------------------------------------------------------+
//| QauntifyTickPush.mq5                                              |
//| Pushes ticks for the chart symbol (attach to XAUUSD) to the       |
//| realtime watcher (signals/realtime_watcher.py) running on the     |
//| SAME machine, over localhost HTTP only -- never internet-facing.  |
//|                                                                    |
//| One-time manual step (cannot be done from this file): in MT5,     |
//| Tools -> Options -> Expert Advisors -> "Allow WebRequest for      |
//| listed URL" -> add http://127.0.0.1:<TickPort>                    |
//+------------------------------------------------------------------+
#property strict

input string AppSymbol     = "XAUUSD";       // symbol as stored in Supabase --
                                              // NOT _Symbol, brokers rename gold
                                              // (XAUUSD.a, XAUUSDm, GOLD, ...)
input int    TickPort      = 8787;           // must match MT5_TICK_PORT
input string WebhookSecret = "";             // must match MT5_WEBHOOK_SECRET
input int    MinIntervalMs = 200;            // floor between sends regardless
                                              // of price movement
input double MinPriceMove  = 0.0;            // 0 = disabled, extra filter on
                                              // top of MinIntervalMs

double lastSentPrice = 0.0;
uint   lastSentTick  = 0;

int OnInit()
  {
   if(WebhookSecret == "")
     {
      Print("QauntifyTickPush: WebhookSecret is empty -- set it before running live.");
     }
   return(INIT_SUCCEEDED);
  }

void OnTick()
  {
   double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(price <= 0.0)
      return;
   if(GetTickCount() - lastSentTick < (uint)MinIntervalMs)
      return;
   if(MinPriceMove > 0.0 && MathAbs(price - lastSentPrice) < MinPriceMove)
      return;

   string body = StringFormat(
      "{\"symbol\":\"%s\",\"price\":%.5f,\"time\":%d}",
      AppSymbol, price, (int)TimeCurrent());

   string headers = "Content-Type: application/json\r\n"
                    "Authorization: Bearer " + WebhookSecret + "\r\n";
   char   post[];
   char   result[];
   string resultHeaders;
   StringToCharArray(body, post, 0, StringLen(body));

   string url = StringFormat("http://127.0.0.1:%d/tick", TickPort);
   int status = WebRequest("POST", url, headers, 1000, post, result, resultHeaders);

   if(status == -1)
     {
      // 4014 = URL not in the allowlist -- see the header comment above.
      Print("QauntifyTickPush: WebRequest failed, error ", GetLastError(),
            ". Is ", url, " allowed under Tools > Options > Expert Advisors?");
      return;
     }
   if(status != 200)
     {
      // Request reached the receiver but it rejected it -- 401 = wrong
      // WebhookSecret, 400 = malformed body. Not a connectivity problem.
      Print("QauntifyTickPush: receiver returned HTTP ", status,
            " -- check WebhookSecret matches MT5_WEBHOOK_SECRET on the VPS.");
      return;
     }
   lastSentPrice = price;
   lastSentTick  = GetTickCount();
  }
//+------------------------------------------------------------------+
