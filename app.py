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
    d=pd.DataFrame({"日期":pd.to_datetime(x["timestamp"],unit="s"),"收盤":q["close"],"成交量":q.get("volume")}).dropna(subset=["收盤"])
    return d

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

def explain(name,x):
    if not x:return "資料暫缺。"
    direction="上漲" if x["本週%"]>0 else "下跌"
    return f"{name}本週{direction} {abs(x['本週%']):.2f}%，近一月 {x['近1月%']:+.2f}%。目前收盤相對20日均線呈{x['趨勢']}型態。這是價格與均線的技術描述，不代表未來方向。"

tab1,tab2,tab3=st.tabs(["🗺️ 一週市場地圖","🌐 各國解說","🧭 跨資產"])
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
            st.markdown("**30秒解說稿**")
            st.write(explain(name,x))
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
