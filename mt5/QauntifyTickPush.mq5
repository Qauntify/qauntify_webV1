//+------------------------------------------------------------------+
//| QauntifyTickPush.mq5                                              |
//| Pushes bid/ask ticks for the chart symbol (attach to XAUUSD) to   |
//| production API (web/src/app/api/mt5/tick/route.ts).               |
//|                                                                    |
//| One-time: Tools -> Options -> Expert Advisors ->                   |
//| "Allow WebRequest for listed URL" -> add ApiUrl origin            |
//| (https://web-seven-pi-76.vercel.app)                              |
//+------------------------------------------------------------------+
#property strict

input string AppSymbol     = "XAUUSD";       // symbol as stored in Supabase --
                                              // NOT _Symbol, brokers rename gold
input string ApiUrl        = "https://web-seven-pi-76.vercel.app/api/mt5/tick";
input string WebhookSecret = "906f61d7dbd1aa2c72cc19a7a0382ce61434f8bd5d6d6c65466912d9808097e4"; // must match MT5_WEBHOOK_SECRET
input int    MinIntervalMs = 150;            // floor between sends
input double MinPriceMove  = 0.0;            // 0 = disabled

double lastSentMid   = 0.0;
uint   lastSentTick  = 0;
long   ticksSeen     = 0;
long   sendsOk       = 0;
long   sendsFailed   = 0;
int    lastStatus    = 0;

void UpdateStatusComment()
  {
   Comment(StringFormat(
      "QauntifyTickPush | ticks: %d | OK: %d | fail: %d | HTTP: %d | mid: %.2f",
      ticksSeen, sendsOk, sendsFailed, lastStatus, lastSentMid));
  }

int OnInit()
  {
   if(WebhookSecret == "")
      Print("QauntifyTickPush: WebhookSecret is empty -- set it before running live.");
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
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(bid <= 0.0 || ask <= 0.0 || ask < bid)
      return;
   double mid = (bid + ask) * 0.5;
   bool dueToSend = GetTickCount() - lastSentTick >= (uint)MinIntervalMs
                    && (MinPriceMove <= 0.0 || MathAbs(mid - lastSentMid) >= MinPriceMove);

   if(dueToSend)
     {
      // price = mid for older readers; bid/ask drive spread-aware outcomes.
      string body = StringFormat(
         "{\"symbol\":\"%s\",\"bid\":%.5f,\"ask\":%.5f,\"mid\":%.5f,\"price\":%.5f,\"time\":%d}",
         AppSymbol, bid, ask, mid, mid, (int)TimeCurrent());

      string headers = "Content-Type: application/json\r\n"
                       "Authorization: Bearer " + WebhookSecret + "\r\n";
      char   post[];
      char   result[];
      string resultHeaders;
      StringToCharArray(body, post, 0, StringLen(body));

      lastStatus = WebRequest("POST", ApiUrl, headers, 5000, post, result, resultHeaders);

      if(lastStatus == -1)
        {
         sendsFailed++;
         Print("QauntifyTickPush: WebRequest failed, error ", GetLastError(),
               ". Is ", ApiUrl, " allowed under Tools > Options > Expert Advisors?");
        }
      else if(lastStatus != 200)
        {
         sendsFailed++;
         Print("QauntifyTickPush: API returned HTTP ", lastStatus,
               " -- check WebhookSecret matches MT5_WEBHOOK_SECRET.");
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
