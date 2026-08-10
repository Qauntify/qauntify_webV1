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
#property version   "1.24"

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
input int    ChartWidth        = 560;   // embed width — keep modest so scale-0 candles stay fat
input int    ChartHeight       = 720;
input int    ChartBarsVisible  = 48;    // target visible bars in the shot
input int    ChartScale        = 0;     // 0=widest candles (terminal zoom-in)

int g_shotW = 0;
int g_shotH = 0;

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

int SplitCsv(const string csv, string &parts[])
  {
   ArrayResize(parts, 0);
   if(StringLen(csv) < 1) return 0;
   string work = csv;
   StringReplace(work, " ", "");
   string tmp[];
   int count = StringSplit(work, ',', tmp);
   if(count <= 0) return 0;
   ArrayResize(parts, count);
   for(int i = 0; i < count; i++)
      parts[i] = tmp[i];
   return count;
  }

// Moving cloud = stepped rectangles between consecutive (t, lo, hi) points.
// Flat cloud_high/cloud_low is only a fallback when series is missing.
int DrawCloudBand(const long chartId, const string tCsv, const string loCsv,
                  const string hiCsv, const color border, const color fill)
  {
   string ts[], los[], his[];
   int nt = SplitCsv(tCsv, ts);
   int nlo = SplitCsv(loCsv, los);
   int nhi = SplitCsv(hiCsv, his);
   int n = nt;
   if(nlo < n) n = nlo;
   if(nhi < n) n = nhi;
   if(n < 2) return 0;

   int drawn = 0;
   for(int i = 0; i < n - 1; i++)
     {
      datetime t0 = (datetime)StringToInteger(ts[i]);
      datetime t1 = (datetime)StringToInteger(ts[i + 1]);
      double lo = StringToDouble(los[i]);
      double hi = StringToDouble(his[i]);
      if(t1 <= t0 || hi <= lo) continue;
      string tag = "cloud_" + IntegerToString(i);
      string name = "QTP_" + tag;
      ObjectDelete(chartId, name);
      if(!ObjectCreate(chartId, name, OBJ_RECTANGLE, 0, t0, hi, t1, lo))
         continue;
      ObjectSetInteger(chartId, name, OBJPROP_COLOR, border);
      ObjectSetInteger(chartId, name, OBJPROP_STYLE, STYLE_SOLID);
      ObjectSetInteger(chartId, name, OBJPROP_WIDTH, 1);
      ObjectSetInteger(chartId, name, OBJPROP_FILL, true);
      ObjectSetInteger(chartId, name, OBJPROP_BACK, true);
      ObjectSetInteger(chartId, name, OBJPROP_BGCOLOR, fill);
      ObjectSetInteger(chartId, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(chartId, name, OBJPROP_HIDDEN, true);
      drawn++;
     }
   if(drawn > 0)
     {
      datetime tLabel = (datetime)StringToInteger(ts[0]);
      double hi0 = StringToDouble(his[0]);
      DrawLabel(chartId, "QTP_cloud_lbl", tLabel, hi0, "Cloud", border,
                ANCHOR_LEFT_LOWER);
     }
   return drawn;
  }

void CollectCsvPrices(const string loCsv, const string hiCsv,
                      double &prices[], int &n)
  {
   string los[], his[];
   int nlo = SplitCsv(loCsv, los);
   int nhi = SplitCsv(hiCsv, his);
   for(int i = 0; i < nlo; i++)
     {
      double v = StringToDouble(los[i]);
      if(v > 0.0)
        {
         ArrayResize(prices, n + 1);
         prices[n++] = v;
        }
     }
   for(int i = 0; i < nhi; i++)
     {
      double v = StringToDouble(his[i]);
      if(v > 0.0)
        {
         ArrayResize(prices, n + 1);
         prices[n++] = v;
        }
     }
  }

datetime CloudSeriesLeft(const string tCsv)
  {
   string ts[];
   if(SplitCsv(tCsv, ts) < 1) return 0;
   return (datetime)StringToInteger(ts[0]);
  }

void StripForeignIndicators(const long chartId)
  {
   int windows = (int)ChartGetInteger(chartId, CHART_WINDOWS_TOTAL);
   if(windows < 1) windows = 1;
   for(int w = windows - 1; w >= 0; w--)
     {
      int total = ChartIndicatorsTotal(chartId, w);
      for(int i = total - 1; i >= 0; i--)
        {
         string name = ChartIndicatorName(chartId, w, i);
         if(StringLen(name) > 0)
            ChartIndicatorDelete(chartId, w, name);
        }
     }
  }

void ChartClearAllObjects(const long chartId)
  {
   int total = ObjectsTotal(chartId, -1, -1);
   for(int i = total - 1; i >= 0; i--)
     {
      string name = ObjectName(chartId, i, -1, -1);
      if(StringLen(name) > 0)
         ObjectDelete(chartId, name);
     }
  }

void ApplyTerminalLook(const long chartId)
  {
   // Same vibe as the live XAUUSD window: black, white bodies, lime wicks/volume.
   ChartSetInteger(chartId, CHART_AUTOSCROLL, true);
   ChartSetInteger(chartId, CHART_SHIFT, true);
   ChartSetDouble(chartId, CHART_SHIFT_SIZE, 10.0);
   ChartSetInteger(chartId, CHART_SHOW_GRID, false);
   ChartSetInteger(chartId, CHART_SHOW_VOLUMES, (long)CHART_VOLUME_TICK);
   ChartSetInteger(chartId, CHART_MODE, (long)CHART_CANDLES);
   ChartSetInteger(chartId, CHART_FOREGROUND, false);
   ChartSetInteger(chartId, CHART_SHOW_PERIOD_SEP, false);
   ChartSetInteger(chartId, CHART_SHOW_TRADE_LEVELS, true);
   ChartSetInteger(chartId, CHART_COLOR_BACKGROUND, clrBlack);
   ChartSetInteger(chartId, CHART_COLOR_FOREGROUND, clrWhite);
   ChartSetInteger(chartId, CHART_COLOR_GRID, C'40,40,40');
   ChartSetInteger(chartId, CHART_COLOR_CANDLE_BULL, clrWhite);
   ChartSetInteger(chartId, CHART_COLOR_CANDLE_BEAR, clrBlack);
   ChartSetInteger(chartId, CHART_COLOR_CHART_UP, clrLime);
   ChartSetInteger(chartId, CHART_COLOR_CHART_DOWN, clrLime);
   ChartSetInteger(chartId, CHART_COLOR_VOLUME, clrLime);
   ChartSetInteger(chartId, CHART_SCALE, ChartScale);
  }

void ZoomToSetup(const long chartId, const ENUM_TIMEFRAMES tf,
                 const double &prices[], const int priceCount)
  {
   ApplyTerminalLook(chartId);
   ChartNavigate(chartId, CHART_END, 0);
   ChartRedraw(chartId);
   Sleep(150);

   long visible = ChartGetInteger(chartId, CHART_WIDTH_IN_BARS);
   Print("QauntifyTickPush: zoom visible_bars=", visible,
         " win_px=", ChartGetInteger(chartId, CHART_WIDTH_IN_PIXELS),
         " scale=", ChartGetInteger(chartId, CHART_SCALE));

   // Mild Y-frame around the setup so TP/SL stay in view — still looks like MT5.
   if(priceCount > 0)
     {
      double lo = 0.0;
      double hi = 0.0;
      bool any = false;
      for(int i = 0; i < priceCount; i++)
        {
         if(prices[i] <= 0.0) continue;
         if(!any) { lo = hi = prices[i]; any = true; continue; }
         if(prices[i] < lo) lo = prices[i];
         if(prices[i] > hi) hi = prices[i];
        }
      if(any)
        {
         double span = hi - lo;
         if(span <= 0.0) span = MathMax(hi * 0.0005, _Point * 50);
         double pad = MathMax(span * 0.35, _Point * 80);
         ChartSetInteger(chartId, CHART_SCALEFIX, true);
         ChartSetInteger(chartId, CHART_SCALEFIX_11, false);
         ChartSetDouble(chartId, CHART_FIXED_MIN, lo - pad);
         ChartSetDouble(chartId, CHART_FIXED_MAX, hi + pad);
        }
     }

   ChartSetInteger(chartId, CHART_SCALE, ChartScale);
   ChartRedraw(chartId);
   Sleep(400);
   ChartRedraw(chartId);
  }

string OpenShotChart(const ENUM_TIMEFRAMES tf, long &chartId)
  {
   // Fixed-pixel OBJ_CHART. Width controls bar count at scale 0 — a 1280px
   // embed still packed ~400 M1 hairlines on the VPS.
   string name = "QTP_SHOT_CHART";
   ObjectDelete(0, name);
   if(!ObjectCreate(0, name, OBJ_CHART, 0, 0, 0))
     {
      Print("QauntifyTickPush: OBJ_CHART create failed ", GetLastError());
      chartId = -1;
      return "";
     }
   int ox = ChartWidth;
   if(ox < 360) ox = 360;
   if(ox > 720) ox = 560;
   int oy = ChartHeight;
   if(oy < 560) oy = 720;
   if(oy > 900) oy = 720;
   g_shotW = ox;
   g_shotH = oy;
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 8);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 8);
   ObjectSetInteger(0, name, OBJPROP_XSIZE, ox);
   ObjectSetInteger(0, name, OBJPROP_YSIZE, oy);
   ObjectSetInteger(0, name, OBJPROP_BACK, false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   ObjectSetString(0, name, OBJPROP_SYMBOL, _Symbol);
   ObjectSetInteger(0, name, OBJPROP_PERIOD, tf);
   ObjectSetInteger(0, name, OBJPROP_DATE_SCALE, true);
   ObjectSetInteger(0, name, OBJPROP_PRICE_SCALE, true);
   ObjectSetInteger(0, name, OBJPROP_CHART_SCALE, 0);
   ChartRedraw(0);
   Sleep(900);
   chartId = ObjectGetInteger(0, name, OBJPROP_CHART_ID);
   if(chartId <= 0)
     {
      Print("QauntifyTickPush: OBJPROP_CHART_ID missing");
      ObjectDelete(0, name);
      return "";
     }
   StripForeignIndicators(chartId);
   ChartClearAllObjects(chartId);
   ApplyTerminalLook(chartId);
   ObjectSetInteger(0, name, OBJPROP_CHART_SCALE, 0);
   ChartSetInteger(chartId, CHART_SCALE, 0);
   ChartNavigate(chartId, CHART_END, 0);
   ChartRedraw(chartId);
   Sleep(500);
   return name;
  }

// Shrink the embed until WIDTH_IN_BARS is near the target (fat native candles).
void FitShotZoom(const string objName, const long chartId)
  {
   int target = ChartBarsVisible;
   if(target < 30) target = 30;
   if(target > 70) target = 70;
   int w = (int)ObjectGetInteger(0, objName, OBJPROP_XSIZE);
   for(int attempt = 0; attempt < 8; attempt++)
     {
      ObjectSetInteger(0, objName, OBJPROP_CHART_SCALE, 0);
      ChartSetInteger(chartId, CHART_SCALE, 0);
      ChartNavigate(chartId, CHART_END, 0);
      ChartRedraw(chartId);
      Sleep(280);
      long vis = ChartGetInteger(chartId, CHART_WIDTH_IN_BARS);
      long px = ChartGetInteger(chartId, CHART_WIDTH_IN_PIXELS);
      Print("QauntifyTickPush: fit vis=", vis, " px=", px, " objW=", w,
            " target<=", target);
      if(vis > 0 && vis <= target)
        {
         g_shotW = w;
         g_shotH = (int)ObjectGetInteger(0, objName, OBJPROP_YSIZE);
         return;
        }
      w = (int)MathMax(320, w * 0.72);
      ObjectSetInteger(0, objName, OBJPROP_XSIZE, w);
      ChartRedraw(0);
      Sleep(350);
     }
   g_shotW = (int)ObjectGetInteger(0, objName, OBJPROP_XSIZE);
   g_shotH = (int)ObjectGetInteger(0, objName, OBJPROP_YSIZE);
  }

void CloseShotChart(const string objName, const long chartId)
  {
   if(StringLen(objName) > 0)
      ObjectDelete(0, objName);
   ChartRedraw(0);
  }

// Brace-matched object extract so long CSV string fields stay intact.
string ExtractJsonObjectFromId(const string json, const int idPos)
  {
   int objStart = idPos;
   for(int back = idPos; back >= 0 && back > idPos - 120; back--)
     {
      if(StringGetCharacter(json, back) == '{')
        {
         objStart = back;
         break;
        }
     }
   int depth = 0;
   bool inStr = false;
   for(int i = objStart; i < StringLen(json); i++)
     {
      ushort ch = StringGetCharacter(json, i);
      if(ch == '"' && (i == 0 || StringGetCharacter(json, i - 1) != '\\'))
         inStr = !inStr;
      if(inStr) continue;
      if(ch == '{') depth++;
      else if(ch == '}')
        {
         depth--;
         if(depth == 0)
            return StringSubstr(json, objStart, i - objStart + 1);
        }
     }
   return "";
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
   datetime fvgEnd = (datetime)ExtractJsonNumber(block, "fvg_end");
   double sweepLevel = ExtractJsonNumber(block, "sweep_level");
   double sweepLow = ExtractJsonNumber(block, "sweep_low");
   double sweepHigh = ExtractJsonNumber(block, "sweep_high");
   datetime sweepTime = (datetime)ExtractJsonNumber(block, "sweep_time");
   double chochLevel = ExtractJsonNumber(block, "choch_level");
   datetime chochTime = (datetime)ExtractJsonNumber(block, "choch_time");
   double cloudHigh = ExtractJsonNumber(block, "cloud_high");
   double cloudLow = ExtractJsonNumber(block, "cloud_low");
   string cloudT = ExtractJsonString(block, "cloud_t");
   string cloudLo = ExtractJsonString(block, "cloud_lo");
   string cloudHi = ExtractJsonString(block, "cloud_hi");
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

   long chartId = -1;
   string shotObj = OpenShotChart(want, chartId);
   if(chartId <= 0 || StringLen(shotObj) < 1)
     {
      Print("QauntifyTickPush: shot chart open failed");
      return false;
     }
   ChartPinsClearId(chartId);

   fvgStart = SnapBarTime(want, fvgStart);
   fvgEnd = SnapBarTime(want, fvgEnd);
   sweepTime = SnapBarTime(want, sweepTime);
   chochTime = SnapBarTime(want, chochTime);
   retestTime = SnapBarTime(want, retestTime);

   datetime tNow = iTime(_Symbol, want, 0);
   if(tNow == 0) tNow = TimeCurrent();
   datetime tRight = tNow + PeriodSeconds(want) * 4;

   int barsBack = ChartBarsVisible;
   if(barsBack < 40) barsBack = 40;
   if(barsBack > 120) barsBack = 120;
   // Pad a little left of the visible window for early sweep labels.
   barsBack += 8;
   datetime tLeft = iTime(_Symbol, want, barsBack);
   if(tLeft == 0) tLeft = tNow - PeriodSeconds(want) * barsBack;

   datetime cloudLeft = CloudSeriesLeft(cloudT);
   if(cloudLeft > 0 && cloudLeft < tLeft)
      tLeft = cloudLeft - PeriodSeconds(want);
   if(sweepTime > 0 && sweepTime < tLeft) tLeft = sweepTime - PeriodSeconds(want) * 2;
   if(chochTime > 0 && chochTime < tLeft) tLeft = chochTime - PeriodSeconds(want) * 2;
   if(fvgStart > 0 && fvgStart < tLeft) tLeft = fvgStart - PeriodSeconds(want);
   if(retestTime > 0 && retestTime < tLeft) tLeft = retestTime - PeriodSeconds(want);

   color colFvgBorder = C'20,184,166';
   color colFvgFill   = C'13,148,136';
   color colCloudBorder = C'45,212,191';
   color colCloudFill   = C'15,118,110';
   color colSrBorder = C'56,189,248';
   color colSrFill   = C'3,105,161';
   color colLiq = C'245,158,11';
   color colChoch = C'167,139,250';
   color colEntry = C'226,232,240';
   color colSl = C'251,113,133';
   color colTp = C'52,211,153';
   color colRetest = C'163,230,53';

   int cloudSegs = 0;
   if(StringLen(cloudT) > 0 && StringLen(cloudLo) > 0 && StringLen(cloudHi) > 0)
      cloudSegs = DrawCloudBand(chartId, cloudT, cloudLo, cloudHi,
                                colCloudBorder, colCloudFill);
   else if(cloudHigh > 0.0 && cloudLow > 0.0 && cloudHigh > cloudLow)
      DrawZone(chartId, "cloud", tLeft, tRight, cloudHigh, cloudLow,
               colCloudBorder, colCloudFill, "Cloud (flat)");

   if(zoneHigh > 0.0 && zoneLow > 0.0 && zoneHigh > zoneLow)
      DrawZone(chartId, "sr", tLeft, tRight, zoneHigh, zoneLow,
               colSrBorder, colSrFill, "S/R");

   // FVG = 3-candle imbalance box (start → end), not full chart width.
   if(fvgTop > 0.0 && fvgBot > 0.0 && fvgTop > fvgBot)
     {
      datetime fs = fvgStart > 0 ? fvgStart : tLeft;
      datetime fe = fvgEnd;
      if(fe <= fs)
         fe = fs + PeriodSeconds(want) * 3;
      // Light forward extension past the gap (still active zone feel).
      datetime fvgRight = fe + PeriodSeconds(want) * 2;
      if(fvgRight > tRight) fvgRight = tRight;
      DrawZone(chartId, "fvg", fs, fvgRight, fvgTop, fvgBot,
               colFvgBorder, colFvgFill, "FVG");
      // 50% CE midline of the gap.
      double ce = (fvgTop + fvgBot) * 0.5;
      DrawHLine(chartId, "QTP_fvg_ce", fs, fvgRight, ce, colFvgBorder,
                STYLE_DOT, 1);
     }

   datetime sweepFrom = sweepTime > 0 ? sweepTime : tLeft;
   if(sweepLevel > 0.0)
     {
      DrawHLine(chartId, "QTP_sweep", sweepFrom, tRight, sweepLevel, colLiq,
                STYLE_DOT, 2);
      DrawLabel(chartId, "QTP_sweep_lbl", sweepFrom, sweepLevel, "Liquidity",
                colLiq);
     }
   datetime chochFrom = chochTime > 0 ? chochTime : tLeft;
   if(chochLevel > 0.0)
     {
      DrawHLine(chartId, "QTP_choch", chochFrom, tRight, chochLevel, colChoch,
                STYLE_DASH, 2);
      DrawLabel(chartId, "QTP_choch_lbl", chochFrom, chochLevel, "CHoCH",
                colChoch);
     }
   if(ceTrail > 0.0)
     {
      DrawHLine(chartId, "QTP_ce", tLeft, tRight, ceTrail, clrSilver,
                STYLE_DASHDOT, 1);
      DrawLabel(chartId, "QTP_ce_lbl", tLeft, ceTrail, "CE", clrSilver);
     }

   // Sweep marker sits on the wick extreme that grabbed liquidity.
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

   // Y-zoom only on the core setup — TP2/TP3/cloud extremes stretch the frame.
   double prices[];
   ArrayResize(prices, 0);
   int n = 0;
   double seed[];
   ArrayResize(seed, 16);
   int sn = 0;
   seed[sn++] = entry;
   seed[sn++] = stop;
   seed[sn++] = tp1;
   if(fvgTop > 0.0) seed[sn++] = fvgTop;
   if(fvgBot > 0.0) seed[sn++] = fvgBot;
   if(sweepLevel > 0.0) seed[sn++] = sweepLevel;
   if(sweepLow > 0.0) seed[sn++] = sweepLow;
   if(sweepHigh > 0.0) seed[sn++] = sweepHigh;
   if(chochLevel > 0.0) seed[sn++] = chochLevel;
   if(zoneHigh > 0.0) seed[sn++] = zoneHigh;
   if(zoneLow > 0.0) seed[sn++] = zoneLow;
   if(ceTrail > 0.0) seed[sn++] = ceTrail;
   // Flat cloud snapshot only (not the full series range).
   if(cloudSegs <= 0)
     {
      if(cloudHigh > 0.0) seed[sn++] = cloudHigh;
      if(cloudLow > 0.0) seed[sn++] = cloudLow;
     }
   ArrayResize(prices, sn);
   for(int i = 0; i < sn; i++) prices[i] = seed[i];
   n = sn;

   ZoomToSetup(chartId, want, prices, n);
   FitShotZoom(shotObj, chartId);
   ObjectSetInteger(0, shotObj, OBJPROP_CHART_SCALE, 0);
   ChartSetInteger(chartId, CHART_SCALE, 0);
   ChartNavigate(chartId, CHART_END, 0);
   ChartRedraw(chartId);
   Sleep(500);

   string fileName = "qtp_chart_" + id + ".png";
   // Screenshot at the fitted embed size (fat native candles), server soft-upscales.
   int w = g_shotW;
   if(w < 320) w = 560;
   int h = g_shotH;
   if(h < 480) h = 720;
   bool shot = ChartScreenShot(chartId, fileName, w, h, ALIGN_RIGHT);
   CloseShotChart(shotObj, chartId);
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
   // tight_frame=true → soft lanczos upscale only (no crop/dilate).
   string body = "{\"signal_id\":\"" + id +
                 "\",\"kind\":\"setup\",\"tight_frame\":true,\"image_base64\":\"" + b64 + "\"}";
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

   int pos = 0;
   int processed = 0;
   while(processed < 3)
     {
      int idPos = StringFind(resp, "\"id\":\"", pos);
      if(idPos < 0) break;
      string block = ExtractJsonObjectFromId(resp, idPos);
      if(StringLen(block) < 8) break;
      ProcessOnePending(block);
      processed++;
      pos = idPos + StringLen(block);
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
