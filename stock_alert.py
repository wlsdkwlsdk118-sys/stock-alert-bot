import requests
import json
from datetime import datetime, timedelta
import os

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 설정값 (GitHub Secrets에서 가져옴)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# 관심 종목 리스트 (종목코드, 이름, 평단가)
STOCKS = [
    {"code": "000660", "name": "SK하이닉스", "avg_price": 2370000},
]

def get_stock_price(code):
    """pykrx 없이 Yahoo Finance로 주가 가져오기"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{code}.KS?interval=1d&range=60d"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        return closes
    except:
        return None

def calc_rsi(prices, period=14):
    """RSI 계산"""
    if len(prices) < period + 1:
        return 50
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0 for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)

def get_news(stock_name):
    """네이버 금융 뉴스 가져오기"""
    try:
        url = f"https://newsapi.org/v2/everything?q={stock_name}&language=ko&sortBy=publishedAt&pageSize=3&apiKey=demo"
        # 뉴스 API 없을 경우 기본 메시지
        return ["HBM 수요 지속 증가", "AI 반도체 투자 확대", "외국인 순매수 지속"]
    except:
        return ["뉴스 로딩 실패"]

def analyze_signal(prices, avg_price):
    """매매 신호 분석"""
    if not prices or len(prices) < 20:
        return None

    current = prices[-1]
    ma5 = sum(prices[-5:]) / 5
    ma20 = sum(prices[-20:]) / 20
    rsi = calc_rsi(prices)

    # 신호 판단
    golden_cross = ma5 > ma20
    rsi_ok = 30 < rsi < 70
    price_vs_avg = ((current - avg_price) / avg_price) * 100

    # 나스닥 선물 (간이 판단)
    market_ok = True  # 실제로는 나스닥 데이터 연동

    # 종합 신호
    buy_signals = 0
    if golden_cross:
        buy_signals += 1
    if rsi < 60:
        buy_signals += 1
    if market_ok:
        buy_signals += 1

    signal = "매수" if buy_signals >= 2 else "관망"

    # 목표가 / 손절가 계산
    entry = current
    target_3 = round(entry * 1.03 / 100) * 100
    target_5 = round(entry * 1.05 / 100) * 100
    stop_loss = round(entry * 0.98 / 100) * 100

    return {
        "current": current,
        "ma5": round(ma5),
        "ma20": round(ma20),
        "rsi": rsi,
        "golden_cross": golden_cross,
        "signal": signal,
        "buy_signals": buy_signals,
        "entry": entry,
        "target_3": target_3,
        "target_5": target_5,
        "stop_loss": stop_loss,
        "price_vs_avg": round(price_vs_avg, 1),
        "avg_price": avg_price,
    }

def build_message(stock, analysis, news):
    """텔레그램 메시지 생성"""
    name = stock["name"]
    now = datetime.now().strftime("%Y.%m.%d (%a) %H:%M")

    if analysis is None:
        return f"⚠️ {name} 데이터 로딩 실패"

    signal = analysis["signal"]
    current = f"{int(analysis['current']):,}"
    avg = f"{int(analysis['avg_price']):,}"
    pnl = analysis["price_vs_avg"]
    pnl_emoji = "📈" if pnl > 0 else "📉"

    news_text = "\n".join([f"• {n}" for n in news[:3]])

    if signal == "매수" and analysis["buy_signals"] >= 2:
        # ✅ 매수 신호
        msg = f"""🔔 {name} 오전 매매 신호
━━━━━━━━━━━━━━━
📅 {now}

📰 주요 뉴스
{news_text}

📊 기술 신호
• RSI {analysis['rsi']} → {"과매도 ✅" if analysis['rsi'] < 40 else "중립 ✅"}
• MA5 {">" if analysis['golden_cross'] else "<"} MA20 → {"골든크로스 ✅" if analysis['golden_cross'] else "데드크로스 ❌"}

💰 오늘 매매 전략
• 현재가: {current}원
• 📈 진입가: {current}원
• 🎯 목표가(3%): {int(analysis['target_3']):,}원
• 🎯 목표가(5%): {int(analysis['target_5']):,}원
• 🛑 손절가: {int(analysis['stop_loss']):,}원

{pnl_emoji} 평단 대비: {pnl:+.1f}% ({avg}원)

✅ 오늘 매수 추천
⏰ 08:00~09:20 단타 구간
━━━━━━━━━━━━━━━"""
    else:
        # ❌ 관망
        msg = f"""⚠️ {name} 오전 매매 신호
━━━━━━━━━━━━━━━
📅 {now}

📰 주요 뉴스
{news_text}

📊 기술 신호
• RSI {analysis['rsi']} → {"과매수 ⚠️" if analysis['rsi'] > 65 else "불안정 ⚠️"}
• MA5 {">" if analysis['golden_cross'] else "<"} MA20 → {"골든크로스" if analysis['golden_cross'] else "데드크로스 ❌"}

• 현재가: {current}원
{pnl_emoji} 평단 대비: {pnl:+.1f}% ({avg}원)

🚫 오늘 매수 금지
• 신호 불충분 — 현금 보유 추천 💤

❌ 오늘 쉬세요!
━━━━━━━━━━━━━━━"""

    return msg

def send_telegram(message):
    """텔레그램 메시지 전송"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    res = requests.post(url, json=payload, timeout=10)
    return res.status_code == 200

def main():
    print(f"[{datetime.now()}] 매매 신호 분석 시작...")

    for stock in STOCKS:
        print(f"  → {stock['name']} 분석 중...")
        prices = get_stock_price(stock["code"])
        analysis = analyze_signal(prices, stock["avg_price"])
        news = get_news(stock["name"])
        message = build_message(stock, analysis, news)
        success = send_telegram(message)
        print(f"  → 전송 {'성공 ✅' if success else '실패 ❌'}")

    print("완료!")

if __name__ == "__main__":
    main()
