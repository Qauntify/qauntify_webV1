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
#property version   "1.12"

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
input int    ChartBarsVisible  = 48;   // target bars in view (hint for scale)
input int    ChartScale        = 0;    // 0=most zoomed-in (widest candles) … 5=zoomed-out

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
   if(minutes == 1) return PERIOD_M1;
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

void ChartPinsClearId(const long chartId)
  {
   int total = ObjectsTotal(chartId, 0, -1);
   for(int i = total - 1; i >= 0; i--)
     {
      string name = ObjectName(chartId, i, 0, -1);
      if(StringFind(name, "QTP_") == 0)
         ObjectDelete(chartId, name);
     }
  }

datetime SnapBarTime(const ENUM_TIMEFRAMES tf, const datetime t)
  {
   if(t <= 0) return 0;
   int sh = iBarShift(_Symbol, tf, t, false);
   if(sh < 0) return t;
   datetime bt = iTime(_Symbol, tf, sh);
   return bt > 0 ? bt : t;
  }

void DrawHLine(const long chartId, const string name, const datetime t0,
               const datetime t1, const double price, const color clr,
               const int style, const int width)
  {
   ObjectDelete(chartId, name);
   if(price <= 0.0 || t1 <= t0) return;
   if(!ObjectCreate(chartId, name, OBJ_TREND, 0, t0, price, t1, price)) return;
   ObjectSetInteger(chartId, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(chartId, name, OBJPROP_STYLE, style);
   ObjectSetInteger(chartId, name, OBJPROP_WIDTH, width);
   ObjectSetInteger(chartId, name, OBJPROP_RAY_RIGHT, false);
   ObjectSetInteger(chartId, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(chartId, name, OBJPROP_BACK, false);
   ObjectSetInteger(chartId, name, OBJPROP_HIDDEN, true);
  }

void DrawLabel(const long chartId, const string name, const datetime t,
               const double price, const string text, const color clr,
               const ENUM_ANCHOR_POINT anchor = ANCHOR_LEFT_LOWER)
  {
   ObjectDelete(chartId, name);
   if(price <= 0.0 || t <= 0) return;
   if(!ObjectCreate(chartId, name, OBJ_TEXT, 0, t, price)) return;
   ObjectSetString(chartId, name, OBJPROP_TEXT, " " + text + " ");
   ObjectSetInteger(chartId, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(chartId, name, OBJPROP_FONTSIZE, 10);
   ObjectSetString(chartId, name, OBJPROP_FONT, "Arial Bold");
   ObjectSetInteger(chartId, name, OBJPROP_ANCHOR, anchor);
   ObjectSetInteger(chartId, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(chartId, name, OBJPROP_HIDDEN, true);
   ObjectSetInteger(chartId, name, OBJPROP_BACK, false);
  }

void DrawZone(const long chartId, const string tag, const datetime t0,
              const datetime t1, const double high, const double low,
              const color border, const color fill, const string label)
  {
   string name = "QTP_" + tag;
   ObjectDelete(chartId, name);
   if(high <= low || t1 <= t0) return;
   if(!ObjectCreate(chartId, name, OBJ_RECTANGLE, 0, t0, high, t1, low)) return;
   ObjectSetInteger(chartId, name, OBJPROP_COLOR, border);
   ObjectSetInteger(chartId, name, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(chartId, name, OBJPROP_WIDTH, 2);
   ObjectSetInteger(chartId, name, OBJPROP_FILL, true);
   ObjectSetInteger(chartId, name, OBJPROP_BACK, true);
   ObjectSetInteger(chartId, name, OBJPROP_BGCOLOR, fill);
   ObjectSetInteger(chartId, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(chartId, name, OBJPROP_HIDDEN, true);
   DrawLabel(chartId, name + "_lbl", t0, high, label, border, ANCHOR_LEFT_LOWER);
  }

void DrawArrow(const long chartId, const string name, const datetime t,
               const double price, const bool up, const color clr)
  {
   ObjectDelete(chartId, name);
   if(price <= 0.0 || t <= 0) return;
   ENUM_OBJECT kind = up ? OBJ_ARROW_UP : OBJ_ARROW_DOWN;
   if(!ObjectCreate(chartId, name, kind, 0, t, price)) return;
   ObjectSetInteger(chartId, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(chartId, name, OBJPROP_WIDTH, 3);
   ObjectSetInteger(chartId, name, OBJPROP_ANCHOR,
                    up ? ANCHOR_TOP : ANCHOR_BOTTOM);
   ObjectSetInteger(chartId, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(chartId, name, OBJPROP_HIDDEN, true);
  }

void ZoomToSetup(const long chartId, const ENUM_TIMEFRAMES tf,
                 const double &prices[], const int priceCount)
  {
   int wantBars = ChartBarsVisible;
   if(wantBars < 30) wantBars = 30;
   if(wantBars > 120) wantBars = 120;
   int scale = ChartScale;
   if(scale < 0) scale = 0;
   if(scale > 5) scale = 5;

   ChartSetInteger(chartId, CHART_AUTOSCROLL, false);
   ChartSetInteger(chartId, CHART_SHIFT, true);
   ChartSetInteger(chartId, CHART_SHOW_GRID, true);
   ChartSetInteger(chartId, CHART_SHOW_VOLUMES, CHART_VOLUME_HIDE);
   ChartSetInteger(chartId, CHART_MODE, CHART_CANDLES);
   ChartSetInteger(chartId, CHART_SCALE, scale);
   ChartNavigate(chartId, CHART_END, 0);

   // Lock price axis tightly around setup levels so Entry/SL/TP dominate.
   if(priceCount > 0)
     {
      double lo = prices[0];
      double hi = prices[0];
      for(int i = 1; i < priceCount; i++)
        {
         if(prices[i] <= 0.0) continue;
         if(prices[i] < lo) lo = prices[i];
         if(prices[i] > hi) hi = prices[i];
        }
      double span = hi - lo;
      if(span <= 0.0) span = MathMax(hi * 0.001, _Point * 50);
      double pad = span * 0.22;
      ChartSetInteger(chartId, CHART_SCALEFIX, true);
      ChartSetDouble(chartId, CHART_FIXED_MIN, lo - pad);
      ChartSetDouble(chartId, CHART_FIXED_MAX, hi + pad);
     }

   // Nudge so ~ChartBarsVisible candles fit (scale already set).
   int total = Bars(_Symbol, tf);
   if(total > wantBars)
      ChartNavigate(chartId, CHART_END, 0);

   ChartRedraw(chartId);
  }

bool ProcessOnePending(const string block)
  {
   string id = ExtractJsonString(block, "id");
   if(StringLen(id) < 8) return false;
   int periodMin = (int)ExtractJsonNumber(block, "period_minutes");
   double entry = ExtractJsonNumber(block, "entry");
   double stop = ExtractJsonNumber(block, "stop_loss");
   double tp1 = ExtractJsonNumber(block, "take_profit");
   double tp2 = ExtractJsonNumber(block, "take_profit_2");
   double tp3 = ExtractJsonNumber(block, "take_profit_3");
   string direction = ExtractJsonString(block, "direction");
   bool isBuy = (direction != "short");

   double fvgTop = ExtractJsonNumber(block, "fvg_top");
   double fvgBot = ExtractJsonNumber(block, "fvg_bottom");
   datetime fvgStart = (datetime)ExtractJsonNumber(block, "fvg_start");
   double sweepLevel = ExtractJsonNumber(block, "sweep_level");
   double sweepLow = ExtractJsonNumber(block, "sweep_low");
   double sweepHigh = ExtractJsonNumber(block, "sweep_high");
   datetime sweepTime = (datetime)ExtractJsonNumber(block, "sweep_time");
   double chochLevel = ExtractJsonNumber(block, "choch_level");
   datetime chochTime = (datetime)ExtractJsonNumber(block, "choch_time");
   double cloudHigh = ExtractJsonNumber(block, "cloud_high");
   double cloudLow = ExtractJsonNumber(block, "cloud_low");
   double zoneHigh = ExtractJsonNumber(block, "zone_high");
   double zoneLow = ExtractJsonNumber(block, "zone_low");
   double ceTrail = ExtractJsonNumber(block, "ce_trail");
   datetime retestTime = (datetime)ExtractJsonNumber(block, "retest_time");

   ENUM_TIMEFRAMES want = PeriodFromMinutes(periodMin);
   if(want == PERIOD_CURRENT)
     {
      Print("QauntifyTickPush: unknown period_minutes for ", id);
      return false;
     }

   long chartId = ChartOpen(_Symbol, want);
   if(chartId <= 0)
     {
      Print("QauntifyTickPush: ChartOpen failed ", GetLastError());
      return false;
     }
   Sleep(1500);
   ChartPinsClearId(chartId);

   // Snap event times onto real bars (broker time), else markers float wrongly.
   fvgStart = SnapBarTime(want, fvgStart);
   sweepTime = SnapBarTime(want, sweepTime);
   chochTime = SnapBarTime(want, chochTime);
   retestTime = SnapBarTime(want, retestTime);

   datetime tNow = iTime(_Symbol, want, 0);
   if(tNow == 0) tNow = TimeCurrent();
   datetime tRight = tNow + PeriodSeconds(want) * 6;

   // Left edge of drawings: earliest structure event, else ~45 bars back.
   datetime tLeft = iTime(_Symbol, want, 45);
   if(tLeft == 0) tLeft = tNow - PeriodSeconds(want) * 45;
   if(sweepTime > 0 && sweepTime < tLeft) tLeft = sweepTime - PeriodSeconds(want) * 2;
   if(chochTime > 0 && chochTime < tLeft) tLeft = chochTime - PeriodSeconds(want) * 2;
   if(fvgStart > 0 && fvgStart < tLeft) tLeft = fvgStart - PeriodSeconds(want);
   if(retestTime > 0 && retestTime < tLeft) tLeft = retestTime - PeriodSeconds(want);

   // Bright fills (dark olive was invisible on black charts).
   color colFvgBorder = C'20,184,166';      // teal
   color colFvgFill   = C'13,148,136';
   color colCloudBorder = C'45,212,191';   // bright aqua
   color colCloudFill   = C'15,118,110';
   color colSrBorder = C'56,189,248';
   color colSrFill   = C'3,105,161';
   color colLiq = C'245,158,11';           // amber
   color colChoch = C'167,139,250';        // violet
   color colEntry = C'226,232,240';
   color colSl = C'251,113,133';
   color colTp = C'52,211,153';
   color colRetest = C'163,230,53';

   if(cloudHigh > 0.0 && cloudLow > 0.0 && cloudHigh > cloudLow)
      DrawZone(chartId, "cloud", tLeft, tRight, cloudHigh, cloudLow,
               colCloudBorder, colCloudFill, "Cloud");
   if(zoneHigh > 0.0 && zoneLow > 0.0 && zoneHigh > zoneLow)
      DrawZone(chartId, "sr", tLeft, tRight, zoneHigh, zoneLow,
               colSrBorder, colSrFill, "S/R");
   if(fvgTop > 0.0 && fvgBot > 0.0 && fvgTop > fvgBot)
     {
      datetime fs = fvgStart > 0 ? fvgStart : tLeft;
      DrawZone(chartId, "fvg", fs, tRight, fvgTop, fvgBot,
               colFvgBorder, colFvgFill, "FVG");
     }

   datetime sweepFrom = sweepTime > 0 ? sweepTime : tLeft;
   if(sweepLevel > 0.0)
     {
      DrawHLine(chartId, "QTP_sweep", sweepFrom, tRight, sweepLevel, colLiq, STYLE_DOT, 2);
      DrawLabel(chartId, "QTP_sweep_lbl", sweepFrom, sweepLevel, "Liquidity", colLiq);
     }
   datetime chochFrom = chochTime > 0 ? chochTime : tLeft;
   if(chochLevel > 0.0)
     {
      DrawHLine(chartId, "QTP_choch", chochFrom, tRight, chochLevel, colChoch, STYLE_DASH, 2);
      DrawLabel(chartId, "QTP_choch_lbl", chochFrom, chochLevel, "CHoCH", colChoch);
     }
   if(ceTrail > 0.0)
     {
      DrawHLine(chartId, "QTP_ce", tLeft, tRight, ceTrail, clrSilver, STYLE_DASHDOT, 1);
      DrawLabel(chartId, "QTP_ce_lbl", tLeft, ceTrail, "CE", clrSilver);
     }

   if(sweepTime > 0)
     {
      double sweepPx = isBuy
                       ? (sweepLow > 0.0 ? sweepLow : sweepLevel)
                       : (sweepHigh > 0.0 ? sweepHigh : sweepLevel);
      if(sweepPx > 0.0)
        {
         DrawArrow(chartId, "QTP_sweep_arr", sweepTime, sweepPx, !isBuy, colLiq);
         DrawLabel(chartId, "QTP_sweep_mk", sweepTime, sweepPx, "Sweep", colLiq,
                   isBuy ? ANCHOR_LEFT_UPPER : ANCHOR_LEFT_LOWER);
        }
     }
   if(chochTime > 0 && chochLevel > 0.0)
     {
      DrawArrow(chartId, "QTP_choch_arr", chochTime, chochLevel, isBuy, colChoch);
      DrawLabel(chartId, "QTP_choch_mk", chochTime, chochLevel, "CHoCH", colChoch,
                isBuy ? ANCHOR_LEFT_LOWER : ANCHOR_LEFT_UPPER);
     }
   if(retestTime > 0 && entry > 0.0)
     {
      DrawArrow(chartId, "QTP_retest", retestTime, entry, isBuy, colRetest);
      DrawLabel(chartId, "QTP_retest_lbl", retestTime, entry, "Entry", colRetest,
                isBuy ? ANCHOR_LEFT_LOWER : ANCHOR_LEFT_UPPER);
     }

   DrawHLine(chartId, "QTP_en", tLeft, tRight, entry, colEntry, STYLE_SOLID, 3);
   DrawLabel(chartId, "QTP_en_lbl", tRight, entry, "Entry", colEntry, ANCHOR_LEFT);
   DrawHLine(chartId, "QTP_sl", tLeft, tRight, stop, colSl, STYLE_DASH, 2);
   DrawLabel(chartId, "QTP_sl_lbl", tRight, stop, "SL", colSl, ANCHOR_LEFT);
   DrawHLine(chartId, "QTP_tp1", tLeft, tRight, tp1, colTp, STYLE_DASH, 2);
   DrawLabel(chartId, "QTP_tp1_lbl", tRight, tp1, "TP1", colTp, ANCHOR_LEFT);
   if(tp2 > 0.0)
     {
      DrawHLine(chartId, "QTP_tp2", tLeft, tRight, tp2, colTp, STYLE_DOT, 2);
      DrawLabel(chartId, "QTP_tp2_lbl", tRight, tp2, "TP2", colTp, ANCHOR_LEFT);
     }
   if(tp3 > 0.0)
     {
      DrawHLine(chartId, "QTP_tp3", tLeft, tRight, tp3, colTp, STYLE_DOT, 2);
      DrawLabel(chartId, "QTP_tp3_lbl", tRight, tp3, "TP3", colTp, ANCHOR_LEFT);
     }

   double prices[];
   ArrayResize(prices, 0);
   double cand[];
   ArrayResize(cand, 16);
   int n = 0;
   cand[n++] = entry; cand[n++] = stop; cand[n++] = tp1;
   if(tp2 > 0.0) cand[n++] = tp2;
   if(tp3 > 0.0) cand[n++] = tp3;
   if(fvgTop > 0.0) cand[n++] = fvgTop;
   if(fvgBot > 0.0) cand[n++] = fvgBot;
   if(cloudHigh > 0.0) cand[n++] = cloudHigh;
   if(cloudLow > 0.0) cand[n++] = cloudLow;
   if(zoneHigh > 0.0) cand[n++] = zoneHigh;
   if(zoneLow > 0.0) cand[n++] = zoneLow;
   if(sweepLevel > 0.0) cand[n++] = sweepLevel;
   if(chochLevel > 0.0) cand[n++] = chochLevel;
   if(ceTrail > 0.0) cand[n++] = ceTrail;
   ArrayResize(prices, n);
   for(int i = 0; i < n; i++) prices[i] = cand[i];

   ZoomToSetup(chartId, want, prices, n);
   Sleep(600);

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
