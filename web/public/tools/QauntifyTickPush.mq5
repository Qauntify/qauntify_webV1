//+------------------------------------------------------------------+
//| QauntifyTickPush.mq5                                              |
//| 1) Pushes bid/ask ticks → /api/mt5/tick (SL/TP + live mid snap)   |
//| 2) Pushes closed M1 OHLC → /api/mt5/candles (pattern detection)   |
//| 3) Polls pending gold setup charts → ChartScreenShot upload      |
//|    (Scalp 5m/15m, Swing 1h, War Room floor)                       |
//|                                                                    |
//| VPS: attach this EA on an XAUUSD chart. On each 5m/15m/1h close  |
//| the candles API dispatches the GitHub signals engine.              |
//|                                                                    |
//| Allow WebRequest for ApiUrl / CandleApiUrl / Chart* origin:        |
//| Tools → Options → Expert Advisors                                  |
//+------------------------------------------------------------------+
#property strict
#property version   "1.10"

input string AppSymbol         = "XAUUSD";
input string ApiUrl            = "https://web-seven-pi-76.vercel.app/api/mt5/tick";
input string CandleApiUrl      = "https://web-seven-pi-76.vercel.app/api/mt5/candles";
input string ChartPendingUrl   = "https://web-seven-pi-76.vercel.app/api/mt5/charts/pending";
input string ChartUploadUrl    = "https://web-seven-pi-76.vercel.app/api/mt5/chart";
input string WebhookSecret     = "906f61d7dbd1aa2c72cc19a7a0382ce61434f8bd5d6d6c65466912d9808097e4";
input int    MinIntervalMs     = 150;
input double MinPriceMove      = 0.0;
input int    BackfillBars      = 2000;  // closed M1 bars sent on init (chunked)
input bool   UploadPendingCharts = true;
input int    ChartPollSec      = 20;    // how often to ask for pending setups
input int    ChartWidth        = 1280;
input int    ChartHeight       = 720;

double   lastSentMid    = 0.0;
uint     lastSentTick   = 0;
datetime lastClosedBar  = 0;
datetime lastChartPoll  = 0;
long     ticksSeen      = 0;
long     sendsOk        = 0;
long     sendsFailed    = 0;
long     candleSendsOk  = 0;
long     candleFails    = 0;
long     chartUploadsOk = 0;
long     chartFails     = 0;
int      lastStatus     = 0;
int      lastCandleHttp = 0;
int      lastChartHttp  = 0;
string   lastChartStatus = "idle";

string AuthHeaders()
  {
   return "Content-Type: application/json\r\n"
          "Authorization: Bearer " + WebhookSecret + "\r\n";
  }

string AuthHeadersGet()
  {
   return "Authorization: Bearer " + WebhookSecret + "\r\n";
  }

int HttpPost(const string url, const string body, string &responseBody)
  {
   char post[];
   char result[];
   string resultHeaders;
   StringToCharArray(body, post, 0, StringLen(body));
   int status = WebRequest("POST", url, AuthHeaders(), 30000, post, result, resultHeaders);
   responseBody = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
   return status;
  }

int HttpGet(const string url, string &responseBody)
  {
   char post[];
   char result[];
   string resultHeaders;
   ArrayResize(post, 0);
   int status = WebRequest("GET", url, AuthHeadersGet(), 15000, post, result, resultHeaders);
   responseBody = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
   return status;
  }

void UpdateStatusComment()
  {
   Comment(StringFormat(
      "QauntifyTickPush | ticks OK:%d fail:%d | candles OK:%d fail:%d | charts OK:%d fail:%d | mid:%.2f | lastBar:%s | %s",
      sendsOk, sendsFailed, candleSendsOk, candleFails, chartUploadsOk, chartFails,
      lastSentMid, TimeToString(lastClosedBar, TIME_DATE|TIME_MINUTES), lastChartStatus));
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
   string resp = "";
   lastCandleHttp = HttpPost(CandleApiUrl, body, resp);
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
   const int chunk = 400;
   int total = Bars(_Symbol, PERIOD_M1);
   int n = BackfillBars;
   if(n < 60) n = 60;
   if(total <= 1) return;
   if(n > total - 1) n = total - 1;

   int sent = 0;
   for(int endShift = n; endShift >= 1; endShift -= chunk)
     {
      int startShift = endShift - chunk + 1;
      if(startShift < 1) startShift = 1;
      string arr = "[";
      for(int shift = endShift; shift >= startShift; shift--)
        {
         if(shift < endShift) arr += ",";
         arr += CandleJson(shift);
        }
      arr += "]";
      if(!PushCandlesJson(arr))
        {
         Print("QauntifyTickPush: backfill stopped early after ", sent, " bars");
         return;
        }
      sent += (endShift - startShift + 1);
     }
   lastClosedBar = iTime(_Symbol, PERIOD_M1, 1);
   Print("QauntifyTickPush: backfilled ", sent, " closed M1 bars");
  }

void MaybePushClosedM1()
  {
   datetime closed = iTime(_Symbol, PERIOD_M1, 1);
   if(closed <= 0 || closed == lastClosedBar) return;
   string arr = "[" + CandleJson(1) + "]";
   if(PushCandlesJson(arr))
      lastClosedBar = closed;
  }

ENUM_TIMEFRAMES PeriodFromMinutes(const int minutes)
  {
   if(minutes == 5) return PERIOD_M5;
   if(minutes == 15) return PERIOD_M15;
   if(minutes == 60) return PERIOD_H1;
   return PERIOD_CURRENT;
  }

string ExtractJsonString(const string json, const string key, const int fromPos = 0)
  {
   string needle = "\"" + key + "\":\"";
   int p = StringFind(json, needle, fromPos);
   if(p < 0) return "";
   p += StringLen(needle);
   int end = StringFind(json, "\"", p);
   if(end < 0) return "";
   return StringSubstr(json, p, end - p);
  }

double ExtractJsonNumber(const string json, const string key, const int fromPos = 0)
  {
   string needle = "\"" + key + "\":";
   int p = StringFind(json, needle, fromPos);
   if(p < 0) return 0;
   p += StringLen(needle);
   while(p < StringLen(json) && (StringGetCharacter(json, p) == ' ' || StringGetCharacter(json, p) == '\t'))
      p++;
   int end = p;
   while(end < StringLen(json))
     {
      ushort ch = StringGetCharacter(json, end);
      if((ch >= '0' && ch <= '9') || ch == '.' || ch == '-' || ch == '+')
         end++;
      else
         break;
     }
   return StringToDouble(StringSubstr(json, p, end - p));
  }

void ChartPinsClear()
  {
   int total = ObjectsTotal(0, 0, -1);
   for(int i = total - 1; i >= 0; i--)
     {
      string name = ObjectName(0, i, 0, -1);
      if(StringFind(name, "QTP_") == 0)
         ObjectDelete(0, name);
     }
  }

void ChartPinLevels(const double entry, const double stop, const double tp)
  {
   ChartPinsClear();
   datetime t0 = iTime(_Symbol, PERIOD_CURRENT, 30);
   datetime t1 = iTime(_Symbol, PERIOD_CURRENT, 0) + PeriodSeconds() * 8;
   if(t0 == 0) t0 = TimeCurrent() - PeriodSeconds() * 30;
   if(t1 == 0) t1 = TimeCurrent() + PeriodSeconds() * 8;

   string en = "QTP_en";
   if(ObjectCreate(0, en, OBJ_TREND, 0, t0, entry, t1, entry))
     {
      ObjectSetInteger(0, en, OBJPROP_COLOR, clrDodgerBlue);
      ObjectSetInteger(0, en, OBJPROP_WIDTH, 2);
      ObjectSetInteger(0, en, OBJPROP_RAY_RIGHT, false);
      ObjectSetInteger(0, en, OBJPROP_SELECTABLE, false);
     }
   string sl = "QTP_sl";
   if(ObjectCreate(0, sl, OBJ_TREND, 0, t0, stop, t1, stop))
     {
      ObjectSetInteger(0, sl, OBJPROP_COLOR, clrOrangeRed);
      ObjectSetInteger(0, sl, OBJPROP_STYLE, STYLE_DASH);
      ObjectSetInteger(0, sl, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, sl, OBJPROP_RAY_RIGHT, false);
      ObjectSetInteger(0, sl, OBJPROP_SELECTABLE, false);
     }
   string tpName = "QTP_tp";
   if(ObjectCreate(0, tpName, OBJ_TREND, 0, t0, tp, t1, tp))
     {
      ObjectSetInteger(0, tpName, OBJPROP_COLOR, clrMediumSeaGreen);
      ObjectSetInteger(0, tpName, OBJPROP_STYLE, STYLE_DASH);
      ObjectSetInteger(0, tpName, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, tpName, OBJPROP_RAY_RIGHT, false);
      ObjectSetInteger(0, tpName, OBJPROP_SELECTABLE, false);
     }
   ChartRedraw(0);
  }

bool UploadChartPng(const string signalId)
  {
   ChartRedraw(0);
   Sleep(300);
   string fileName = "qtp_chart_" + signalId + ".png";
   int w = ChartWidth > 640 ? ChartWidth : 1280;
   int h = ChartHeight > 360 ? ChartHeight : 720;
   if(!ChartScreenShot(0, fileName, w, h, ALIGN_RIGHT))
     {
      Print("QauntifyTickPush: ChartScreenShot failed ", GetLastError());
      return false;
     }

   int handle = FileOpen(fileName, FILE_READ|FILE_BIN);
   if(handle == INVALID_HANDLE)
     {
      Print("QauntifyTickPush: open screenshot failed ", GetLastError());
      return false;
     }
   int size = (int)FileSize(handle);
   if(size <= 0)
     {
      FileClose(handle);
      FileDelete(fileName);
      return false;
     }
   uchar data[];
   ArrayResize(data, size);
   if(FileReadArray(handle, data, 0, size) != size)
     {
      FileClose(handle);
      FileDelete(fileName);
      return false;
     }
   FileClose(handle);
   FileDelete(fileName);

   uchar key[];
   uchar encoded[];
   if(!CryptEncode(CRYPT_BASE64, data, key, encoded))
     {
      Print("QauntifyTickPush: base64 encode failed ", GetLastError());
      return false;
     }
   string b64 = CharArrayToString(encoded, 0, WHOLE_ARRAY, CP_UTF8);
   string body = "{\"signal_id\":\"" + signalId +
                 "\",\"kind\":\"setup\",\"image_base64\":\"" + b64 + "\"}";
   string resp = "";
   lastChartHttp = HttpPost(ChartUploadUrl, body, resp);
   if(lastChartHttp == 200)
     {
      chartUploadsOk++;
      return true;
     }
   chartFails++;
   Print("QauntifyTickPush: chart upload HTTP ", lastChartHttp, " ", resp);
   return false;
  }

bool ProcessOnePending(const string block)
  {
   string id = ExtractJsonString(block, "id");
   if(StringLen(id) < 8) return false;
   int periodMin = (int)ExtractJsonNumber(block, "period_minutes");
   double entry = ExtractJsonNumber(block, "entry");
   double stop = ExtractJsonNumber(block, "stop_loss");
   double tp = ExtractJsonNumber(block, "take_profit");
   ENUM_TIMEFRAMES want = PeriodFromMinutes(periodMin);
   if(want == PERIOD_CURRENT)
     {
      Print("QauntifyTickPush: unknown period_minutes for ", id);
      return false;
     }

   // Open a throwaway chart so we never ChartSetSymbolPeriod on the
   // live EA chart (that re-inits the expert and stops the tick loop).
   long chartId = ChartOpen(_Symbol, want);
   if(chartId <= 0)
     {
      Print("QauntifyTickPush: ChartOpen failed ", GetLastError());
      return false;
     }
   Sleep(1000);

   datetime t0 = iTime(_Symbol, want, 30);
   datetime t1 = iTime(_Symbol, want, 0) + PeriodSeconds(want) * 8;
   if(t0 == 0) t0 = TimeCurrent() - PeriodSeconds(want) * 30;
   if(t1 == 0) t1 = TimeCurrent() + PeriodSeconds(want) * 8;

   string en = "QTP_en";
   ObjectCreate(chartId, en, OBJ_TREND, 0, t0, entry, t1, entry);
   ObjectSetInteger(chartId, en, OBJPROP_COLOR, clrDodgerBlue);
   ObjectSetInteger(chartId, en, OBJPROP_WIDTH, 2);
   ObjectSetInteger(chartId, en, OBJPROP_RAY_RIGHT, false);

   string sl = "QTP_sl";
   ObjectCreate(chartId, sl, OBJ_TREND, 0, t0, stop, t1, stop);
   ObjectSetInteger(chartId, sl, OBJPROP_COLOR, clrOrangeRed);
   ObjectSetInteger(chartId, sl, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(chartId, sl, OBJPROP_WIDTH, 1);
   ObjectSetInteger(chartId, sl, OBJPROP_RAY_RIGHT, false);

   string tpName = "QTP_tp";
   ObjectCreate(chartId, tpName, OBJ_TREND, 0, t0, tp, t1, tp);
   ObjectSetInteger(chartId, tpName, OBJPROP_COLOR, clrMediumSeaGreen);
   ObjectSetInteger(chartId, tpName, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(chartId, tpName, OBJPROP_WIDTH, 1);
   ObjectSetInteger(chartId, tpName, OBJPROP_RAY_RIGHT, false);

   ChartRedraw(chartId);
   Sleep(400);

   string fileName = "qtp_chart_" + id + ".png";
   int w = ChartWidth > 640 ? ChartWidth : 1280;
   int h = ChartHeight > 360 ? ChartHeight : 720;
   bool shot = ChartScreenShot(chartId, fileName, w, h, ALIGN_RIGHT);
   ChartClose(chartId);
   if(!shot)
     {
      Print("QauntifyTickPush: ChartScreenShot failed ", GetLastError());
      chartFails++;
      return false;
     }

   int handle = FileOpen(fileName, FILE_READ|FILE_BIN);
   if(handle == INVALID_HANDLE)
     {
      chartFails++;
      return false;
     }
   int size = (int)FileSize(handle);
   if(size <= 0)
     {
      FileClose(handle);
      FileDelete(fileName);
      chartFails++;
      return false;
     }
   uchar data[];
   ArrayResize(data, size);
   if(FileReadArray(handle, data, 0, size) != size)
     {
      FileClose(handle);
      FileDelete(fileName);
      chartFails++;
      return false;
     }
   FileClose(handle);
   FileDelete(fileName);

   uchar key[];
   uchar encoded[];
   if(!CryptEncode(CRYPT_BASE64, data, key, encoded))
     {
      chartFails++;
      return false;
     }
   string b64 = CharArrayToString(encoded, 0, WHOLE_ARRAY, CP_UTF8);
   string body = "{\"signal_id\":\"" + id +
                 "\",\"kind\":\"setup\",\"image_base64\":\"" + b64 + "\"}";
   string resp = "";
   lastChartHttp = HttpPost(ChartUploadUrl, body, resp);
   if(lastChartHttp == 200)
     {
      chartUploadsOk++;
      lastChartStatus = "uploaded " + id;
      return true;
     }
   chartFails++;
   lastChartStatus = "fail " + id;
   Print("QauntifyTickPush: chart upload HTTP ", lastChartHttp, " ", resp);
   return false;
  }

void MaybeUploadPendingCharts()
  {
   if(!UploadPendingCharts) return;
   if(StringLen(ChartPendingUrl) < 8 || StringLen(ChartUploadUrl) < 8) return;
   datetime now = TimeCurrent();
   if(lastChartPoll > 0 && (now - lastChartPoll) < ChartPollSec) return;
   lastChartPoll = now;

   string url = ChartPendingUrl + "?symbol=" + AppSymbol + "&limit=3";
   string resp = "";
   int status = HttpGet(url, resp);
   if(status != 200)
     {
      lastChartStatus = StringFormat("poll HTTP %d", status);
      if(status == -1)
         Print("QauntifyTickPush: pending chart WebRequest err ", GetLastError());
      return;
     }

   // Walk each {"id":...} object in the pending array (simple scan).
   int pos = 0;
   int processed = 0;
   while(processed < 3)
     {
      int idPos = StringFind(resp, "\"id\":\"", pos);
      if(idPos < 0) break;
      int objStart = idPos;
      // Prefer the nearest '{' before id.
      for(int back = idPos; back >= 0 && back > idPos - 80; back--)
        {
         if(StringGetCharacter(resp, back) == '{')
           {
            objStart = back;
            break;
           }
        }
      int objEnd = StringFind(resp, "}", idPos);
      if(objEnd < 0) break;
      string block = StringSubstr(resp, objStart, objEnd - objStart + 1);
      ProcessOnePending(block);
      processed++;
      pos = objEnd + 1;
     }
   if(processed == 0)
      lastChartStatus = "no pending";
  }

int OnInit()
  {
   if(WebhookSecret == "")
      Print("QauntifyTickPush: WebhookSecret is empty.");
   originalPeriod = (ENUM_TIMEFRAMES)ChartPeriod(0);
   BackfillClosedM1();
   UpdateStatusComment();
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   ChartPinsClear();
   Comment("");
  }

void OnTick()
  {
   ticksSeen++;
   MaybePushClosedM1();
   MaybeUploadPendingCharts();

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

      string resp = "";
      lastStatus = HttpPost(ApiUrl, body, resp);

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
