import streamlit as st
import pandas as pd
import numpy as np
import requests
import altair as alt
from io import BytesIO
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
NE_ASIA_REPORT={
"日本":{"顯示":"日經225指數","ticker":"^N225"},
"韓國":{"顯示":"韓國指數","ticker":"^KS11"},
"香港恆生":{"顯示":"香港恆生指數","ticker":"^HSI"},
"上證A股":{"顯示":"中國上證A股指數","ticker":"000001.SS"},
"香港國企":{"顯示":"香港國企指數","ticker":"^HSCE"},
"台灣":{"顯示":"台灣加權指數","ticker":"^TWII"},
}
DEFAULT_REPORT_ORDER=list(NE_ASIA_REPORT)

@st.cache_data(ttl=900)
def yahoo(ticker,range_="3mo"):
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    r=requests.get(url,params={"range":range_,"interval":"1d"},headers=HEADERS,timeout=15); r.raise_for_status()
    x=r.json()["chart"]["result"][0]; q=x["indicators"]["quote"][0]
    d=pd.DataFrame({"日期":pd.to_datetime(x["timestamp"],unit="s"),"最高":q.get("high"),"最低":q.get("low"),"收盤":q["close"],"成交量":q.get("volume")}).dropna(subset=["收盤"])
    return d

@st.cache_data(ttl=21600)
def imf_macro_table():
    """Load IMF WEO data through the DBnomics public mirror."""
    countries={"🇹🇼 台灣":"TWN","🇯🇵 日本":"JPN","🇰🇷 韓國":"KOR","🇨🇳 中國":"CHN"}
    indicators={"GDP成長率":"NGDP_RPCH","CPI年增率":"PCPIPCH","出口量成長率":"TX_RPCH","進口量成長率":"TM_RPCH"}
    collected={name:{"國家／市場":name} for name in countries}
    for label,indicator in indicators.items():
        for name,code in countries.items():
            url=f"https://api.db.nomics.world/v22/series/IMF/WEO:2025-04/{code}.{indicator}"
            r=requests.get(url,params={"observations":1},headers=HEADERS,timeout=20); r.raise_for_status()
            docs=r.json().get("series",{}).get("docs",[])
            series=docs[0] if docs else {}
            valid=[]
            for period,value in zip(series.get("period",[]),series.get("value",[])):
                try:
                    year=int(period)
                    if year<=datetime.now().year: valid.append((year,float(value)))
                except (TypeError,ValueError): continue
            if valid:
                year,value=max(valid,key=lambda item:item[0])
                collected[name][label]=value
                collected[name][f"{label}資料期"]=str(year)
            else:
                collected[name][label]=np.nan
                collected[name][f"{label}資料期"]="待更新"
    rows=[]
    for name in countries:
        item=collected[name]
        periods=[item.get(f"{label}資料期","待更新") for label in indicators]
        item["資料期／公布季"]="／".join(dict.fromkeys(periods))+"（年度）"
        rows.append(item)
    return pd.DataFrame(rows)

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

def extract_uploaded_text(uploaded):
    if uploaded is None:return ""
    suffix=uploaded.name.lower().rsplit(".",1)[-1]
    data=uploaded.getvalue()
    if suffix in ("txt","md","csv"):
        for encoding in ("utf-8-sig","utf-8","big5"):
            try:return data.decode(encoding)
            except UnicodeDecodeError:continue
        raise ValueError("文字檔編碼無法辨識")
    if suffix=="docx":
        from docx import Document
        doc=Document(BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if suffix=="pdf":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(BytesIO(data)).pages)
    raise ValueError("僅支援 TXT、MD、CSV、DOCX、PDF")

def build_technical_report(name,d,news_text=""):
    sections=[]; signals=[]
    frames=[("日線",d),("週線",resample_ohlcv(d,"週線")),("月線",resample_ohlcv(d,"月線"))]
    for label,frame in frames:
        if len(frame)<12:continue
        z,t=technical(frame)
        last=float(z["收盤"].iloc[-1]); ma5=float(z["收盤"].tail(5).mean())
        ma20=float(z["收盤"].tail(20).mean()) if len(z)>=20 else float(z["收盤"].mean())
        structure="偏強" if last>ma5 and last>ma20 else ("偏弱" if last<ma5 and last<ma20 else "震盪")
        signals.append(structure)
        sections.append(
            f"【{label}】\n"
            f"價格結構：最新收盤 {last:,.2f}，位於短中期均線相對位置呈現{structure}。\n"
            f"KD：K值 {t['K']:.1f}、D值 {t['D']:.1f}，{t['KD解讀']}。\n"
            f"MACD：DIF {t['DIF']:.2f}、訊號線 {t['MACD']:.2f}、OSC {t['OSC']:.2f}；{t['MACD解讀']}。\n"
            f"量能：{t['量能']}。\n"
            f"KD背離：{t['KD背離']}。"
        )
    strong=signals.count("偏強"); weak=signals.count("偏弱")
    if strong>=2:overall="多數週期的價格結構偏強，但仍要確認量能能否延續，並留意高檔背離。"
    elif weak>=2:overall="多數週期的價格結構偏弱，反彈是否站回均線與動能翻正，是後續觀察重點。"
    else:overall="日、週、月訊號不同步，短線與中長線應分開判讀，避免只依單一週期操作。"
    report=f"{name} 技術線報告\n資料日期：{pd.to_datetime(d['日期'].iloc[-1]).strftime('%Y-%m-%d')}\n\n"+"\n\n".join(sections)
    report+=f"\n\n【多週期結論】\n{overall}"
    clean_news=news_text.strip()
    if clean_news:
        report+=f"\n\n【新聞與事件補充】\n{clean_news}\n\n【講稿銜接】\n以上新聞作為事件背景，需再對照價格、量能及事件發生時間；目前技術訊號不直接等同於新聞造成的因果關係。"
    report+="\n\n本報告僅供市場研究，不構成投資建議。"
    return report

def gemini_polish_report(report,api_key):
    prompt=(
        "你是繁體中文市場研究講稿編輯。請把以下技術線報告整理成自然、可直接口述的報告。"
        "必須維持日線、週線、月線的順序，且每個週期依序涵蓋價格結構、KD、MACD、量能、KD背離。"
        "新聞只能作為背景，不能虛構因果、數字、來源或未提供的事件；所有原始數值必須保留。"
        "最後加入多週期結論、觀察重點及『僅供市場研究，不構成投資建議』。\n\n原始報告：\n"+report
    )
    r=requests.post(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        headers={"x-goog-api-key":api_key,"Content-Type":"application/json"},
        json={"model":"gemini-3.8-flash","input":prompt,"store":False},timeout=90
    )
    r.raise_for_status(); payload=r.json(); output=[]
    for step in payload.get("steps",[]):
        if step.get("type")=="model_output":
            output.extend(x.get("text","") for x in step.get("content",[]) if x.get("type")=="text")
    text="".join(output).strip()
    if not text:raise ValueError("Gemini 沒有回傳可用文字")
    return text

def pptx_market_order(uploaded):
    if uploaded is None:return DEFAULT_REPORT_ORDER
    from pptx import Presentation
    prs=Presentation(BytesIO(uploaded.getvalue())); found=[]
    aliases={"日經":"日本","韓股":"韓國","韓國":"韓國","香港恆生":"香港恆生","上證":"上證A股","上証":"上證A股","香港國企":"香港國企","台灣加權":"台灣"}
    for slide in prs.slides:
        text="\n".join(sh.text for sh in slide.shapes if hasattr(sh,"text"))
        for alias,name in aliases.items():
            if alias in text and name not in found:found.append(name)
    return found+[x for x in DEFAULT_REPORT_ORDER if x not in found]

def timeframe_snapshot(d,label):
    frame=d if label=="日線" else resample_ohlcv(d,label)
    z,t=technical(frame); window=20 if label!="月線" else 12; recent=z.tail(window)
    last=float(z["收盤"].iloc[-1]); support=float(recent["最低"].min()); resistance=float(recent["最高"].max())
    ma5=float(z["收盤"].tail(5).mean()); ma20=float(z["收盤"].tail(20).mean()) if len(z)>=20 else float(z["收盤"].mean())
    structure="偏強" if last>ma5 and last>ma20 else ("偏弱" if last<ma5 and last<ma20 else "震盪")
    return {"label":label,"last":last,"support":support,"resistance":resistance,"structure":structure,**t}

def fmt_level(value):return f"{value:,.0f}"

def meeting_sentence(s):
    return (f"{s['label']}：最新 {fmt_level(s['last'])} 點，價格結構{s['structure']}。"
            f"KD為K {s['K']:.1f}、D {s['D']:.1f}，{s['KD解讀']}；MACD為DIF {s['DIF']:.2f}、OSC {s['OSC']:.2f}，{s['MACD解讀']}；"
            f"{s['量能']}；{s['KD背離']}。支撐 {fmt_level(s['support'])} 點、壓力 {fmt_level(s['resistance'])} 點。")

def collect_ne_asia_report(order):
    output=[]
    for name in order:
        info=NE_ASIA_REPORT[name]; d=yahoo(info["ticker"],"2y")
        output.append({"name":name,"display":info["顯示"],"date":pd.to_datetime(d["日期"].iloc[-1]).date(),"frames":[timeframe_snapshot(d,x) for x in ("日線","週線","月線")]})
    return output

def style_report_doc(doc):
    from docx.shared import Pt
    style=doc.styles["Normal"]; style.font.name="Microsoft JhengHei"; style.font.size=Pt(10.5)
    for section in doc.sections:
        section.top_margin=section.bottom_margin=Pt(42); section.left_margin=section.right_margin=Pt(42)

def build_meeting_doc(data):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt
    doc=Document(); style_report_doc(doc); now=datetime.now(); roc=now.year-1911
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; r=p.add_run(f"{roc}/{now.month}/{now.day} 東北亞市場會議記錄"); r.bold=True; r.font.size=Pt(16)
    doc.add_paragraph("亞洲地區：")
    table=doc.add_table(rows=1,cols=2); table.style="Table Grid"; table.rows[0].cells[0].text="國別"; table.rows[0].cells[1].text="最新點位與技術線型分析"
    for item in data:
        cells=table.add_row().cells; cells[0].text=item["name"]; cells[1].text="\n".join(meeting_sentence(x) for x in item["frames"])
    out=BytesIO(); doc.save(out); return out.getvalue()

def build_barometer_doc(data):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt
    doc=Document(); style_report_doc(doc); p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run("本週重點市場指數預測"); r.bold=True; r.font.size=Pt(16); doc.add_paragraph("評等：部分加碼／持有／部分減碼")
    table=doc.add_table(rows=1,cols=5); table.style="Table Grid"
    for cell,text in zip(table.rows[0].cells,["市場（指數）","最新點位","本週走勢預測","建議","短線壓力／支撐"]):cell.text=text
    for item in data:
        daily,weekly,_=item["frames"]
        if daily["structure"]==weekly["structure"]=="偏強":forecast,action="整理偏強","部分加碼"
        elif daily["structure"]==weekly["structure"]=="偏弱":forecast,action="整理偏弱","部分減碼"
        else:forecast,action="區間整理","持有"
        cells=table.add_row().cells
        values=[item["display"],fmt_level(daily["last"]),forecast,action,f"支撐 {fmt_level(daily['support'])}、壓力 {fmt_level(daily['resistance'])}"]
        for cell,value in zip(cells,values):cell.text=value
    doc.add_paragraph("資料日期："+"；".join(f"{x['name']} {x['date']}" for x in data))
    out=BytesIO(); doc.save(out); return out.getvalue()

def render_ne_asia_generator():
    st.header("📑 一鍵產生東北亞會議文件")
    st.caption("固定順序：日本 → 韓國 → 香港恆生 → 上證A股 → 香港國企 → 台灣；各市場依日線 → 週線 → 月線分析。")
    tech_file=st.file_uploader("上傳技術線簡報（PPTX，選填）",type=["pptx"],key="ne_asia_tech_pptx")
    if st.button("一鍵更新點位並產生會議記錄＋晴雨表",type="primary",key="make_ne_asia_docs"):
        try:
            with st.spinner("正在更新六個市場的最新點位與技術線……"):
                order=pptx_market_order(tech_file); data=collect_ne_asia_report(order)
                st.session_state["ne_meeting_doc"]=build_meeting_doc(data); st.session_state["ne_barometer_doc"]=build_barometer_doc(data)
                st.session_state["ne_preview"]=pd.DataFrame([{"順序":i+1,"市場":x["name"],"最新點位":x["frames"][0]["last"],"日線支撐":x["frames"][0]["support"],"日線壓力":x["frames"][0]["resistance"],"資料日期":x["date"]} for i,x in enumerate(data)])
        except Exception as e:st.error("文件產生失敗："+str(e))
    if "ne_preview" in st.session_state:
        st.dataframe(st.session_state["ne_preview"],use_container_width=True,hide_index=True,column_config={"最新點位":st.column_config.NumberColumn(format="%.0f"),"日線支撐":st.column_config.NumberColumn(format="%.0f"),"日線壓力":st.column_config.NumberColumn(format="%.0f")})
        c1,c2=st.columns(2); stamp=datetime.now().strftime("%Y%m%d")
        c1.download_button("下載更新後會議記錄 DOCX",st.session_state["ne_meeting_doc"],f"會議記錄_{stamp}_東北亞.docx","application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        c2.download_button("下載更新後晴雨表 DOCX",st.session_state["ne_barometer_doc"],f"晴雨表_{stamp}_東北亞.docx","application/vnd.openxmlformats-officedocument.wordprocessingml.document")

def tech_panel(name,d):
    z,t=technical(d)
    st.subheader(f"📈 {name} 技術線")
    c1,c2,c3,c4=st.columns(4)
    c1.metric("KD",f"K {t['K']:.1f} / D {t['D']:.1f}"); c2.metric("MACD",f"DIF {t['DIF']:.2f}",f"OSC {t['OSC']:.2f}")
    c3.metric("量能",t["量能"].split("，")[0]); c4.metric("KD背離","無" if t["KD背離"].startswith("未") else "有")
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
    st.markdown("#### 📝 技術線報告產生器")
    st.caption("講稿依日線 → 週線 → 月線排列，依序說明價格結構、KD、MACD、量能與KD背離。")
    pasted_news=st.text_area("貼上新聞或事件內容（選填）",height=140,placeholder="可貼入新聞、研究摘要或你想放進講稿的資料……",key=f"news_{name}")
    uploaded=st.file_uploader("上傳新聞／研究檔案（選填）",type=["txt","md","csv","docx","pdf"],key=f"file_{name}")
    if st.button("產生技術線報告",type="primary",key=f"report_btn_{name}"):
        try:
            file_text=extract_uploaded_text(uploaded)
            combined="\n\n".join(x for x in (pasted_news.strip(),file_text.strip()) if x)
            generated=build_technical_report(name,d,combined)
            st.session_state[f"report_{name}"]=generated
            st.session_state[f"report_edit_{name}"]=generated
        except Exception as e:
            st.error("檔案內容讀取失敗："+str(e))
    report=st.session_state.get(f"report_{name}")
    if report:
        if f"report_edit_{name}" not in st.session_state:st.session_state[f"report_edit_{name}"]=report
        edited=st.text_area("已產生講稿（可直接修改或複製）",height=520,key=f"report_edit_{name}")
        st.markdown("##### ✨ Gemini AI 潤稿")
        st.caption("Gemini 會整合技術數據與你提供的新聞，但不會把新聞直接假設成漲跌原因。API 金鑰不會寫入 GitHub。")
        try:saved_key=st.secrets.get("GEMINI_API_KEY","")
        except Exception:saved_key=""
        api_key=st.text_input("Gemini API Key",value=saved_key,type="password",placeholder="貼上 Google AI Studio API Key",key=f"gemini_key_{name}")
        st.link_button("前往 Google AI Studio 取得 API Key","https://aistudio.google.com/apikey")
        if st.button("使用 Gemini 產生完整講稿",key=f"gemini_btn_{name}"):
            if not api_key.strip():st.warning("請先輸入 Gemini API Key。")
            else:
                try:
                    with st.spinner("Gemini 正在整理講稿……"):
                        ai_report=gemini_polish_report(edited,api_key.strip())
                    st.session_state[f"report_{name}"]=ai_report
                    st.session_state[f"report_edit_{name}"]=ai_report
                    st.rerun()
                except Exception as e:
                    st.error("Gemini 產生失敗："+str(e))
        st.download_button("下載講稿 TXT",data=edited.encode("utf-8-sig"),file_name=f"{name}_技術線報告_{datetime.now().strftime('%Y%m%d')}.txt",mime="text/plain",key=f"report_download_{name}")

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

render_ne_asia_generator()
st.divider()

tab1,tab2,tab3,tab4,tab5=st.tabs(["🗺️ 一週市場地圖","🌐 各國解說","🧭 跨資產","📊 估值與企業獲利","🌏 經濟與進出口"])
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

with tab4:
    st.subheader("📊 各國估值與企業獲利")
    st.caption("先架展示版：欄位依 Siblis Research 的 P/E、Forward P/E 與 EPS Index 設計。EPS Index 是獲利指數，不是單一公司的每股盈餘。")
    valuation_demo=pd.DataFrame([
        {"市場":"🇹🇼 台灣 TWSE","P/E (TTM)":30.90,"Forward P/E":22.40,"EPS Index (TTM)":167.07,"資料期":"2026/06/30"},
        {"市場":"🇯🇵 日本 Nikkei 225","P/E (TTM)":22.09,"Forward P/E":17.82,"EPS Index (TTM)":155.43,"資料期":"2026/06/30"},
        {"市場":"🇰🇷 韓國 KOSPI","P/E (TTM)":22.95,"Forward P/E":7.82,"EPS Index (TTM)":252.73,"資料期":"2026/06/30"},
        {"市場":"🇨🇳 中國 A股／MSCI China","P/E (TTM)":"待來源更新","Forward P/E":"待來源更新","EPS Index (TTM)":"待來源更新","資料期":"待更新"},
    ])
    st.dataframe(valuation_demo,use_container_width=True,hide_index=True)
    st.markdown("#### 🔎 怎麼讀")
    v1,v2,v3=st.columns(3)
    v1.metric("P/E (TTM)","過去12個月","目前價格 ÷ 過去獲利")
    v2.metric("Forward P/E","未來預估","市場價格 ÷ 預估獲利")
    v3.metric("EPS Index","企業獲利趨勢","2024/01/01 = 100")
    st.info("下一步會把這裡改成自動更新資料，並加入「指數 vs EPS」、「P/E 歷史區間」及估值擴張／收縮判讀；目前展示值不會假裝成即時資料。")
    st.markdown("**資料來源：** Siblis Research — P/E Ratios by Country")
    st.link_button("開啟 Siblis Research 原始資料","https://siblisresearch.com/data/pe-ratios-by-country/")

with tab5:
    st.subheader("🌏 台日韓中經濟與進出口")
    st.caption("GDP、CPI、商品與服務進出口量成長率採 IMF WEO 最新可用年度資料（經 DBnomics 公開鏡像讀取）。")
    try:
        macro=imf_macro_table()
        display_cols=["國家／市場","GDP成長率","CPI年增率","出口量成長率","進口量成長率","資料期／公布季"]
        st.dataframe(macro[display_cols],use_container_width=True,hide_index=True,column_config={
            "GDP成長率":st.column_config.NumberColumn(format="%.2f%%"),
            "CPI年增率":st.column_config.NumberColumn(format="%.2f%%"),
            "出口量成長率":st.column_config.NumberColumn(format="%.2f%%"),
            "進口量成長率":st.column_config.NumberColumn(format="%.2f%%"),
        })
        st.markdown("**資料來源：** IMF World Economic Outlook（WEO），DBnomics 公開鏡像")
        st.link_button("開啟 IMF DataMapper","https://www.imf.org/external/datamapper/datasets/WEO")
    except Exception as e:
        st.warning("IMF 經濟與進出口資料目前無法取得："+str(e))

st.caption("最後更新執行："+datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
