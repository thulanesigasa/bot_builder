// XAUUSD Hybrid Research EA — paper simulation only.
// Copyright (c) 2026. Original educational research implementation.
// NO order submission, no OrderSend, no CTrade, no demo or live positions.
#property strict
#property version "1.00"
#property description "XAUUSD hybrid H1/M15/M5 research; virtual baseline vs capped recovery; NO ORDERS"

input double InpHypotheticalUSD=50.0;
input double InpRiskFraction=0.0025;     // 0.25% initial risk per virtual trade
input double InpDailyLossFraction=0.02;  // 2% of initial hypothetical balance
input double InpMaximumDrawdown=0.10;    // 10% of initial hypothetical balance
input double InpRecoveryMultiplier=1.5; // bounded paper lot multiplier
input int InpMaxRecoveryIncreases=3;
input double InpATRStopMultiplier=1.5;
input double InpRewardToRisk=1.5;
input int InpMaxSpreadPoints=150;        // must be calibrated for broker symbol
input int InpMinimumATRPts=20;
input bool InpJournalToCommonFiles=false;

int hFast=INVALID_HANDLE,hSlow=INVALID_HANDLE,hRsi=INVALID_HANDLE,hAtr=INVALID_HANDLE,hPullback=INVALID_HANDLE;
datetime lastM5Bar=0;
struct VirtualBook {
  double balance;
  double peak;
  double dayOpening;
  int dayKey;
  int position;             // 0 flat, +1 buy, -1 sell
  double entry,sl,tp,volume;
  int recoveryLosses;
  int wins,losses,skipped;
  bool disabled;
};
VirtualBook baseline,recovery;
int journal=INVALID_HANDLE;

bool ReadClosed(const int handle,double &out) {
  double data[1];
  if(handle==INVALID_HANDLE || CopyBuffer(handle,0,1,1,data)!=1) return false;
  out=data[0];
  return MathIsValidNumber(out);
}
bool IsGoldSymbol() {
  string s=_Symbol;
  StringToUpper(s);
  return StringFind(s,"XAUUSD")>=0 || StringFind(s,"GOLD")>=0;
}
void ResetBook(VirtualBook &b) {
  b.balance=InpHypotheticalUSD;b.peak=InpHypotheticalUSD;b.dayOpening=InpHypotheticalUSD;
  b.dayKey=-1;b.position=0;b.entry=0;b.sl=0;b.tp=0;b.volume=0;
  b.recoveryLosses=0;b.wins=0;b.losses=0;b.skipped=0;b.disabled=false;
}
int DateKey(datetime t) {
  MqlDateTime d;TimeToStruct(t,d);
  return d.year*10000+d.mon*100+d.day;
}
void Audit(const string variant,const string event,const double bal,const double vol,const string reason) {
  string msg=StringFormat("XAU_RESEARCH|%s|%s|balance=%.5f|volume=%.5f|%s",variant,event,bal,vol,reason);
  Print(msg);
  if(journal!=INVALID_HANDLE) FileWrite(journal,TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),variant,event,DoubleToString(bal,5),DoubleToString(vol,5),reason);
}
bool UpdateLimits(VirtualBook &b,const string label) {
  int today=DateKey(TimeCurrent());
  if(today!=b.dayKey) {b.dayKey=today;b.dayOpening=b.balance;}
  if(b.balance>b.peak) b.peak=b.balance;
  if(b.balance<=InpHypotheticalUSD*(1.0-InpMaximumDrawdown) ||
     b.balance<=b.dayOpening-InpHypotheticalUSD*InpDailyLossFraction) {
    if(!b.disabled) Audit(label,"RISK_LOCK",b.balance,b.volume,"virtual loss threshold");
    b.disabled=true;
  }
  return !b.disabled;
}
double Pnl(const VirtualBook &b,double exitPrice) {
  double tickSize=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
  double tickValue=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE);
  if(tickSize<=0 || tickValue<=0) return 0;
  return b.position*(exitPrice-b.entry)/tickSize*tickValue*b.volume;
}
void CloseVirtual(VirtualBook &b,const string label,const double price,const string reason) {
  double change=Pnl(b,price);
  b.balance+=change;
  if(change>0) {b.wins++;b.recoveryLosses=0;}
  else {b.losses++;b.recoveryLosses++;}
  // Recovery is capped: after the 4th loss reset to initial risk.
  if(b.recoveryLosses>InpMaxRecoveryIncreases) b.recoveryLosses=0;
  Audit(label,"CLOSE",b.balance,b.volume,StringFormat("pnl=%.5f; %s",change,reason));
  b.position=0;b.volume=0;
  UpdateLimits(b,label);
}
void MarkToMarket(VirtualBook &b,const string label,const MqlTick &tick) {
  if(b.position==0) return;
  // Use executable side of spread. Stop takes precedence for ambiguous quotes.
  double price=b.position>0?tick.bid:tick.ask;
  if((b.position>0 && price<=b.sl)||(b.position<0 && price>=b.sl)) {
    CloseVirtual(b,label,price,"STOP (slippage included)");return;
  }
  if((b.position>0 && price>=b.tp)||(b.position<0 && price<=b.tp))
    CloseVirtual(b,label,price,"TARGET");
}
void OpenVirtual(VirtualBook &b,const string label,const int side,const double atr,const MqlTick &tick,const bool bounded) {
  if(b.position!=0 || !UpdateLimits(b,label)) return;
  double tickSize=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
  double tickValue=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE);
  double minLot=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
  double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
  double maxLot=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
  double pt=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
  if(tickSize<=0||tickValue<=0||minLot<=0||step<=0||pt<=0||maxLot<minLot) {
    b.skipped++;Audit(label,"SKIP",b.balance,0,"INVALID_BROKER_SYMBOL_SPEC");return;
  }
  double distance=MathMax(atr*InpATRStopMultiplier,2.0*tickSize);
  double stops=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*pt;
  distance=MathMax(distance,stops+2*pt);
  double factor=bounded?MathPow(InpRecoveryMultiplier,b.recoveryLosses):1.0;
  double budget=b.balance*InpRiskFraction*factor;
  double perLotLoss=distance/tickSize*tickValue;
  if(perLotLoss<=0) return;
  // Round down. Never silently force minimum lot beyond allowed risk.
  double candidate=budget/perLotLoss;
  double lots=MathFloor((candidate+1e-12)/step)*step;
  lots=NormalizeDouble(MathMin(lots,maxLot),8);
  if(lots<minLot || perLotLoss*lots>budget+1e-8) {
    b.skipped++;Audit(label,"SKIP",b.balance,0,
       StringFormat("LOT_INFEASIBLE risk_budget=%.4f min_lot_loss=%.4f",budget,minLot*perLotLoss));return;
  }
  double entry=side>0?tick.ask:tick.bid;
  b.position=side;b.entry=entry;b.volume=lots;
  b.sl=NormalizeDouble(entry-side*distance,_Digits);
  b.tp=NormalizeDouble(entry+side*distance*InpRewardToRisk,_Digits);
  Audit(label,"OPEN_VIRTUAL",b.balance,lots,
     StringFormat("side=%d;entry=%.5f;sl=%.5f;tp=%.5f;recovery_level=%d",
       side,entry,b.sl,b.tp,b.recoveryLosses));
}
int Signal(double &atr) {
  double fast,slow,rsi,pullback;
  if(!ReadClosed(hFast,fast)||!ReadClosed(hSlow,slow)||
     !ReadClosed(hRsi,rsi)||!ReadClosed(hAtr,atr)||!ReadClosed(hPullback,pullback)) return 0;
  MqlRates m15[2],m5[2];
  // CopyRates into fixed arrays is chronological: [0] older, [1] newer.
  if(CopyRates(_Symbol,PERIOD_M15,1,2,m15)!=2||
     CopyRates(_Symbol,PERIOD_M5,1,2,m5)!=2) return 0;
  if(atr < InpMinimumATRPts*_Point) return 0;
  bool bullish=(m5[1].close>m5[1].open && m5[1].close>m5[0].close);
  bool bearish=(m5[1].close<m5[1].open && m5[1].close<m5[0].close);
  bool pull=(MathAbs(m15[1].close-pullback)<=atr*0.65);
  if(fast>slow && m15[1].close>pullback && rsi>50 && rsi<70 && bullish && pull) return 1;
  if(fast<slow && m15[1].close<pullback && rsi<50 && rsi>30 && bearish && pull) return -1;
  return 0;
}
int OnInit() {
  if(!IsGoldSymbol()) {Print("XAU research requires XAUUSD/gold chart");return INIT_FAILED;}
  if(InpHypotheticalUSD!=50.0 || InpRiskFraction<=0||InpRiskFraction>0.005||
     InpDailyLossFraction<=0||InpDailyLossFraction>0.02||
     InpMaximumDrawdown<=0||InpMaximumDrawdown>0.10||
     InpRecoveryMultiplier<1.0||InpRecoveryMultiplier>1.5||
     InpMaxRecoveryIncreases<0||InpMaxRecoveryIncreases>3||
     InpATRStopMultiplier<=0||InpRewardToRisk<=0||InpMaxSpreadPoints<=0) return INIT_PARAMETERS_INCORRECT;
  hFast=iMA(_Symbol,PERIOD_H1,50,0,MODE_EMA,PRICE_CLOSE);
  hSlow=iMA(_Symbol,PERIOD_H1,200,0,MODE_EMA,PRICE_CLOSE);
  hRsi=iRSI(_Symbol,PERIOD_M15,14,PRICE_CLOSE);
  hAtr=iATR(_Symbol,PERIOD_M15,14);
  hPullback=iMA(_Symbol,PERIOD_M15,20,0,MODE_EMA,PRICE_CLOSE);
  if(hFast==INVALID_HANDLE||hSlow==INVALID_HANDLE||hRsi==INVALID_HANDLE||
     hAtr==INVALID_HANDLE||hPullback==INVALID_HANDLE) return INIT_FAILED;
  ResetBook(baseline);ResetBook(recovery);
  if(InpJournalToCommonFiles) {
    journal=FileOpen("XAUUSD_Research_NoTrades.csv",FILE_WRITE|FILE_CSV|FILE_COMMON|FILE_ANSI,',');
    if(journal!=INVALID_HANDLE) FileWrite(journal,"server_time","variant","event","balance","lots","details");
  }
  Print("XAUUSD RESEARCH MODE: NO OrderSend / CTrade / purchases; virtual USD50 baseline and capped recovery.");
  return INIT_SUCCEEDED;
}
void OnTick() {
  MqlTick t;if(!SymbolInfoTick(_Symbol,t)) return;
  MarkToMarket(baseline,"BASELINE",t);
  MarkToMarket(recovery,"RECOVERY_1_5",t);
  datetime current=iTime(_Symbol,PERIOD_M5,0);
  if(current<=0||current==lastM5Bar) return;
  lastM5Bar=current;
  double pt=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
  if(pt<=0 || (t.ask-t.bid)/pt>InpMaxSpreadPoints) return;
  double atr=0;int direction=Signal(atr);
  if(direction==0)return;
  OpenVirtual(baseline,"BASELINE",direction,atr,t,false);
  OpenVirtual(recovery,"RECOVERY_1_5",direction,atr,t,true);
}
void OnDeinit(const int reason) {
  Print(StringFormat("XAU_FINAL BASELINE balance=%.5f wins=%d losses=%d skipped=%d; RECOVERY balance=%.5f wins=%d losses=%d skipped=%d",
      baseline.balance,baseline.wins,baseline.losses,baseline.skipped,
      recovery.balance,recovery.wins,recovery.losses,recovery.skipped));
  if(journal!=INVALID_HANDLE) FileClose(journal);
  if(hFast!=INVALID_HANDLE) IndicatorRelease(hFast);
  if(hSlow!=INVALID_HANDLE) IndicatorRelease(hSlow);
  if(hRsi!=INVALID_HANDLE) IndicatorRelease(hRsi);
  if(hAtr!=INVALID_HANDLE) IndicatorRelease(hAtr);
  if(hPullback!=INVALID_HANDLE) IndicatorRelease(hPullback);
}
