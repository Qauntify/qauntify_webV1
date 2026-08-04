//+------------------------------------------------------------------+
//| QauntifyTickPush.mq5                                              |
//| Pushes ticks for the chart symbol (attach to XAUUSD) to the       |
//| production API (web/src/app/api/mt5/tick/route.ts) -- the VPS     |
//| this EA runs on does NOT need to run any other process for this.  |
//|                                                                    |
//| One-time manual step (cannot be done from this file): in MT5,     |
//| Tools -> Options -> Expert Advisors -> "Allow WebRequest for      |
//| listed URL" -> add the ApiUrl's origin below                      |
//| (https://web-seven-pi-76.vercel.app)                              |
//+------------------------------------------------------------------+
#property strict

input string AppSymbol     = "XAUUSD";       // symbol as stored in Supabase --
                                              // NOT _Symbol, brokers rename gold
                                              // (XAUUSD.a, XAUUSDm, GOLD, ...)
input string ApiUrl        = "https://web-seven-pi-76.vercel.app/api/mt5/tick";
input string WebhookSecret = "906f61d7dbd1aa2c72cc19a7a0382ce61434f8bd5d6d6c65466912d9808097e4"; // must match MT5_WEBHOOK_SECRET in Vercel's env vars
input int    MinIntervalMs = 200;            // floor between sends regardless
                                              // of price movement
input double MinPriceMove  = 0.0;            // 0 = disabled, extra filter on
                                              // top of MinIntervalMs

double lastSentPrice = 0.0;
uint   lastSentTick  = 0;
long   ticksSeen     = 0;   // every OnTick() call, whether sent or throttled
long   sendsOk       = 0;   // successful (HTTP 200) sends
long   sendsFailed   = 0;   // attempted but rejected/failed sends
int    lastStatus    = 0;   // last WebRequest() return value

void UpdateStatusComment()
  {
   Comment(StringFormat(
      "QauntifyTickPush | ticks seen: %d | sent OK: %d | failed: %d | last HTTP: %d",
      ticksSeen, sendsOk, sendsFailed, lastStatus));
  }

int OnInit()
  {
   if(WebhookSecret == "")
     {
      Print("QauntifyTickPush: WebhookSecret is empty -- set it before running live.");
     }
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
   double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(price <= 0.0)
     {
      UpdateStatusComment();
      return;
     }
   if(GetTickCount() - lastSentTick < (uint)MinIntervalMs)
     {
      UpdateStatusComment();
      return;
     }
   if(MinPriceMove > 0.0 && MathAbs(price - lastSentPrice) < MinPriceMove)
     {
      UpdateStatusComment();
      return;
     }

   string body = StringFormat(
      "{\"symbol\":\"%s\",\"price\":%.5f,\"time\":%d}",
      AppSymbol, price, (int)TimeCurrent());

   string headers = "Content-Type: application/json\r\n"
                    "Authorization: Bearer " + WebhookSecret + "\r\n";
   char   post[];
   char   result[];
   string resultHeaders;
   StringToCharArray(body, post, 0, StringLen(body));

   // 5s, not 1s: this is now a real internet round-trip (Vercel serverless
   // cold starts can take a second-plus occasionally), not localhost.
   int status = WebRequest("POST", ApiUrl, headers, 5000, post, result, resultHeaders);
   lastStatus = status;

   if(status == -1)
     {
      // 4014 = URL not in the allowlist -- see the header comment above.
      sendsFailed++;
      Print("QauntifyTickPush: WebRequest failed, error ", GetLastError(),
            ". Is ", ApiUrl, " allowed under Tools > Options > Expert Advisors?");
      UpdateStatusComment();
      return;
     }
   if(status != 200)
     {
      // Request reached the API but it rejected it -- 401 = wrong
      // WebhookSecret, 400 = malformed body. Not a connectivity problem.
      sendsFailed++;
      Print("QauntifyTickPush: API returned HTTP ", status,
            " -- check WebhookSecret matches MT5_WEBHOOK_SECRET in Vercel's env vars.");
      UpdateStatusComment();
      return;
     }
   sendsOk++;
   lastSentPrice = price;
   lastSentTick  = GetTickCount();
   UpdateStatusComment();
  }
//+------------------------------------------------------------------+
