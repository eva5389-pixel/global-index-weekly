import streamlit as st
import pandas as pd
import numpy as np
import requests
import altair as alt
from datetime import datetime

st.set_page_config(page_title="全球指數週動態",page_icon="🌏",layout="wide")
st.title("🌏 全球指數一週動態・市場解說")
st.caption("自動整理全球主要指數本週表現、近一月趨勢與跨資產背景。資料為市場研究用途，不構成投資建議。")

HEADERS={"User-Agent":"Mozilla/5.0"}
MARKETS={
"🇹🇼 台灣":{"台灣加權":"^TWII","櫃買":"^TWOII"},
"🇯🇵 日本":{"日經225":"^N225","TOPIX":"^TOPX"},
"🇰🇷 韓國":{"KOSPI":"^KS11"},
"🇨🇳 中國／香港":{"上證":"000001.SS","滬深300":"000300.SS","恆生":"^HSI","恆生科技":"^HSTECH"},
"🇺🇸 美國":{"S&P 500":"^GSPC","Nasdaq":"^IXIC","費城半導體":"^SOX","Russell 2000":"^RUT"},
"🇪🇺 歐洲":{"STOXX Europe 600":"^STOXX","DAX":"^GDAXI","CAC 40":"^FCHI","FTSE 100":"^FTSE"}}
CROSS={"美元指數":"DX-Y.NYB","美債10Y殖利率":"^TNX","VIX":"^VIX","黃金":"GC=F","原油WTI":"CL=F","Bitcoin":"BTC-USD"}

@st.cache_data(ttl=900)
def yahoo(ticker,range_="3mo"):
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    r=requests.get(url,params={"range":range_,"interval":"1d"},headers=HEADERS,timeout=15); r.raise_for_status()
    x=r.json()["chart"]["result"][0]; q=x["indicators"]["quote"][0]
    d=pd.DataFrame({"日期":pd.to_datetime(x["timestamp"],unit="s"),"最高":q.get("high"),"最低":q.get("low"),"收盤":q["close"],"成交量":q.get("volume")}).dropna(subset=["收盤"])
    return d

def technical(d):
    z=d.copy()
    low9=z["最低"].rolling(9).min(); high9=z["最高"].rolling(9).max()
    rsv=((z["收盤"]-low9)/(high9-low9).replace(0,np.nan)*100).fillna(50)
    z["K"]=rsv.ewm(alpha=1/3,adjust=False).mean()
    z["D"]=z["K"].ewm(alpha=1/3,adjust=False).mean()
    ema12=z["收盤"].ewm(span=12,adjust=False).mean(); ema26=z["收盤"].ewm(span=26,adjust=False).mean()
    z["DIF"]=ema12-ema26; z["MACD"]=z["DIF"].ewm(span=9,adjust=False).mean(); z["OSC"]=z["DIF"]-z["MACD"]
    z["VMA5"]=z["成交量"].rolling(5).mean(); z["VMA20"]=z["成交量"].rolling(20).mean()
    k=float(z["K"].iloc[-1]); dd=float(z["D"].iloc[-1]); dif=float(z["DIF"].iloc[-1]); macd=float(z["MACD"].iloc[-1]); osc=float(z["OSC"].iloc[-1])
    kd=("高檔" if k>=80 else "低檔" if k<=20 else "中性區")+"；"+("K>D 偏強" if k>dd else "K<D 偏弱")
    macd_txt=("DIF在訊號線上方" if dif>macd else "DIF在訊號線下方")+"；柱狀體"+("為正" if osc>0 else "為負")
    v=z["成交量"].iloc[-1]; v20=z["VMA20"].iloc[-1]
    vol="成交量資料不足" if pd.isna(v) or pd.isna(v20) or v20==0 else f"量能為20日均量的 {v/v20:.2f} 倍，"+("放量" if v/v20>=1.2 else "量縮" if v/v20<=0.8 else "量能一般")
    # 以最近約60個交易日的局部高/低點，比較價格與K值，判斷規則式KD背離
    t=z.tail(60).reset_index(drop=True)
    highs=[]; lows=[]
    for i in range(2,len(t)-2):
        if t.loc[i,"收盤"]>=t.loc[i-2:i+2,"收盤"].max(): highs.append(i)
        if t.loc[i,"收盤"]<=t.loc[i-2:i+2,"收盤"].min(): lows.append(i)
    div="未偵測到明顯KD背離"
    if len(highs)>=2:
        a,b=highs[-2],highs[-1]
        if t.loc[b,"收盤"]>t.loc[a,"收盤"] and t.loc[b,"K"]<t.loc[a,"K"]: div="⚠️ 偵測到KD頂背離：價格創較高高點，但K值未同步創高"
    if div.startswith("未") and len(lows)>=2:
        a,b=lows[-2],lows[-1]
        if t.loc[b,"收盤"]<t.loc[a,"收盤"] and t.loc[b,"K"]>t.loc[a,"K"]: div="🟢 偵測到KD底背離：價格創較低低點，但K值未同步破低"
    return z,{"K":k,"D":dd,"KD解讀":kd,"DIF":dif,"MACD":macd,"OSC":osc,"MACD解讀":macd_txt,"量能":vol,"KD背離":div}

def resample_ohlcv(d,period):
    z=d.copy().set_index("日期")
    rule="W-FRI" if period=="週線" else "ME"
    return z.resample(rule).agg({"最高":"max","最低":"min","收盤":"last","成交量":"sum"}).dropna(subset=["收盤"]).reset_index()

def tech_summary(label,d):
    z,t=technical(d)
    last=float(z["收盤"].iloc[-1]); ma5=float(z["收盤"].tail(5).mean())
    ma20=float(z["收盤"].tail(20).mean()) if len(z)>=20 else float(z["收盤"].mean())
    structure="偏強" if last>ma5 and last>ma20 else ("偏弱" if last<ma5 and last<ma20 else "震盪")
    momentum="動能偏強" if t["K"]>t["D"] and t["DIF"]>t["MACD"] else ("動能偏弱" if t["K"]<t["D"] and t["DIF"]<t["MACD"] else "動能分歧")
    return t,f"{label}：價格結構{structure}，{momentum}；{t['KD背離']}。"

def tech_panel(name,d):
    z,t=technical(d)
    st.subheader(f"📈 {name} 技術線")
    c1,c2,c3,c4=st.columns(4)
    c1.metric("KD",f"K {t['K']:.1f} / D {t['D']:.1f}"); c2.metric("MACD",f"DIF {t['DIF']:.2f}",f"OSC {t['OSC']:.2f}")
    c3.metric("量能",t["量能"].split("，")[0]); c4.metric("KD背離","有" if "偵測到" in t["KD背離"] else "無")
    st.write(f"**KD：** {t['KD解讀']}　｜　**MACD：** {t['MACD解讀']}　｜　**量：** {t['量能']}")
    st.write(f"**背離判讀：** {t['KD背離']}")
    st.markdown("#### 🧭 日／週／月多週期判讀")
    frames=[("日線",d),("週線",resample_ohlcv(d,"週線")),("月線",resample_ohlcv(d,"月線"))]
    multi=[]
    for label,frame in frames:
        if len(frame)>=12:
            tt,summary=tech_summary(label,frame)
            multi.append({"週期":label,"K":tt["K"],"D":tt["D"],"OSC":tt["OSC"],"KD背離":tt["KD背離"],"解讀":summary})
    if multi:
        md=pd.DataFrame(multi)
        st.dataframe(md,use_container_width=True,hide_index=True,column_config={"K":st.column_config.NumberColumn(format="%.1f"),"D":st.column_config.NumberColumn(format="%.1f"),"OSC":st.column_config.NumberColumn(format="%.2f")})
        strong=sum(("偏強" in x["解讀"]) for x in multi); weak=sum(("偏弱" in x["解讀"]) for x in multi)
        if strong>=2: overall="日、週、月多週期目前以偏強訊號較多，但仍需觀察量能與背離是否惡化。"
        elif weak>=2: overall="日、週、月多週期目前以偏弱訊號較多，需留意短線反彈是否能扭轉中期動能。"
        else: overall="日、週、月訊號目前分歧，屬多週期不同步，較適合分開看短線與中長線。"
        st.info("**多週期結論：** "+overall)
    price=z.tail(90)[["日期","收盤"]]
    st.altair_chart(alt.Chart(price).mark_line().encode(x="日期:T",y=alt.Y("收盤:Q",scale=alt.Scale(zero=False))).properties(height=180),use_container_width=True)
    with st.expander("查看 KD / MACD / 成交量圖"):
        kd=z.tail(90).melt("日期",value_vars=["K","D"],var_name="線",value_name="值")
        st.altair_chart(alt.Chart(kd).mark_line().encode(x="日期:T",y=alt.Y("值:Q",scale=alt.Scale(domain=[0,100])),color="線:N").properties(height=160),use_container_width=True)
        mm=z.tail(90).melt("日期",value_vars=["DIF","MACD"],var_name="線",value_name="值")
        st.altair_chart(alt.Chart(mm).mark_line().encode(x="日期:T",y="值:Q",color="線:N").properties(height=160),use_container_width=True)
        st.bar_chart(z.tail(90).set_index("日期")["成交量"],height=160)

def stats(ticker):
    d=yahoo(ticker)
    if d.empty:return None,d
    last=float(d["收盤"].iloc[-1])
    w=d.tail(6); m=d.tail(22)
    wp=(last/float(w["收盤"].iloc[0])-1)*100 if len(w)>1 else np.nan
    mp=(last/float(m["收盤"].iloc[0])-1)*100 if len(m)>1 else np.nan
    ma20=float(d["收盤"].tail(20).mean())
    trend="轉強" if last>ma20 and wp>0 else ("轉弱" if last<ma20 and wp<0 else "震盪")
    return {"最新":last,"本週%":wp,"近1月%":mp,"MA20":ma20,"趨勢":trend,"日期":d["日期"].iloc[-1].date()},d

def weekly_commentary(name,x,d):
    if not x:return "資料暫缺。"
    z,t=technical(d)
    direction="上漲" if x["本週%"]>0 else "下跌"
    # 價格/技術面能直接由行情計算；不把未取得的新聞或總經事件硬寫成原因。
    tech=f"技術面方面，KD為 K {t['K']:.1f}、D {t['D']:.1f}（{t['KD解讀']}）；MACD {t['MACD解讀']}；{t['量能']}。{t['KD背離']}。"
    return f"{name}本週{direction} {abs(x['本週%']):.2f}%，近一月 {x['近1月%']:+.2f}%。{tech}目前這一版的漲跌原因只根據價格、動能與量能描述；新聞、經濟數據與資金面尚未接入時，不會自行臆測事件原因。"

def explain(name,x,d=None):
    if not x:return "資料暫缺。"
    if d is not None and not d.empty:return weekly_commentary(name,x,d)
    direction="上漲" if x["本週%"]>0 else "下跌"
    return f"{name}本週{direction} {abs(x['本週%']):.2f}%，近一月 {x['近1月%']:+.2f}%。目前收盤相對20日均線呈{x['趨勢']}型態。"

st.header("📊 技術線總覽")
tech_region=st.selectbox("技術線市場",list(MARKETS),key="tech_region")
tech_name=st.selectbox("技術線指數",list(MARKETS[tech_region]),key="tech_name")
try:
    tech_d=yahoo(MARKETS[tech_region][tech_name],"2y")
    tech_panel(tech_name,tech_d)
except Exception as e:
    st.warning("技術線資料目前無法取得："+str(e))
st.divider()

tab1,tab2,tab3,tab4=st.tabs(["🗺️ 一週市場地圖","🌐 各國解說","🧭 跨資產","📊 估值與企業獲利"])
rows=[]; cache={}
for region,items in MARKETS.items():
    for name,ticker in items.items():
        try:x,d=stats(ticker)
        except Exception:x,d=None,pd.DataFrame()
        cache[name]=(x,d,region)
        if x: rows.append({"市場":region,"指數":name,"最新":x["最新"],"本週漲跌%":x["本週%"],"近1月%":x["近1月%"],"趨勢":x["趨勢"],"資料日期":x["日期"]})
with tab1:
    if rows:
        z=pd.DataFrame(rows).sort_values("本週漲跌%",ascending=False)
        st.dataframe(z,use_container_width=True,hide_index=True,column_config={"本週漲跌%":st.column_config.NumberColumn(format="%.2f%%"),"近1月%":st.column_config.NumberColumn(format="%.2f%%")})
        st.bar_chart(z.set_index("指數")["本週漲跌%"],horizontal=True)
    else: st.warning("目前無法取得指數行情。")
with tab2:
    region=st.selectbox("選擇市場",list(MARKETS))
    for name in MARKETS[region]:
        x,d,_=cache[name]
        st.subheader(name)
        if x:
            c1,c2,c3,c4=st.columns(4)
            c1.metric("最新",f"{x['最新']:,.2f}"); c2.metric("本週",f"{x['本週%']:+.2f}%"); c3.metric("近1月",f"{x['近1月%']:+.2f}%"); c4.metric("趨勢",x["趨勢"])
            chart=d.tail(30).copy()
            st.altair_chart(alt.Chart(chart).mark_line().encode(x="日期:T",y=alt.Y("收盤:Q",scale=alt.Scale(zero=False))).properties(height=220),use_container_width=True)
            st.markdown("**本週動態拆解**")
            zt,tt=technical(d)
            e1,e2,e3=st.columns(3)
            e1.write("**價格／技術**")
            e1.write(f"本週 {x['本週%']:+.2f}%｜近1月 {x['近1月%']:+.2f}%｜{x['趨勢']}")
            e2.write("**經濟數據／事件**")
            e2.write("尚未接入即時事件資料源，不自行補寫原因。")
            e3.write("**資金／風險背景**")
            e3.write(f"{tt['量能']}；KD背離："+("有" if "偵測到" in tt["KD背離"] else "無"))
            st.markdown("**30秒解說稿**")
            st.write(explain(name,x,d))
        else: st.warning("行情暫時無法取得。")
        st.divider()
with tab3:
    cr=[]
    for name,ticker in CROSS.items():
        try:x,d=stats(ticker)
        except Exception:x=None
        if x: cr.append({"資產":name,"最新":x["最新"],"本週漲跌%":x["本週%"],"近1月%":x["近1月%"],"趨勢":x["趨勢"]})
    if cr:
        st.dataframe(pd.DataFrame(cr),use_container_width=True,hide_index=True)
        st.caption("跨資產用來協助理解股市背景；例如美元、殖利率、波動率與商品的同步或背離。")

st.caption("最後更新執行："+datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
