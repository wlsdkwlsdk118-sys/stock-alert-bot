import requests
import json
from datetime import datetime
import os

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 설정값
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
MODE = os.environ.get("MODE", "morning")  # morning / afternoon

# 관심 종목
MAIN_STOCK = {"code": "000660", "name": "SK하이닉스", "avg_price": 2370000}

def get_stock_price(code):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{code}.KS?interval=1d&range=60d"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        volumes = data["chart"]["result"][0]["indicators"]["quote"][0]["volume"]
        closes = [c for c in closes if c is not None]
        volumes = [v for v in volumes if v is not None]
        return closes, volumes
    except:
        return None, None

def calc_rsi(prices, period=14):
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

def analyze(prices, volumes, avg_price):
    if not prices or len(prices) < 20:
        return None
    current = prices[-1]
    ma5 = sum(prices[-5:]) / 5
    ma20 = sum(prices[-20:]) / 20
    rsi = calc_rsi(prices)
    golden_cross = ma5 > ma20

    # 거래량 급증 체크
    avg_vol = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 0
    vol_surge = volumes[-1] > avg_vol * 1.5 if avg_vol > 0 else False

    buy_signals = 0
    if golden_cross: buy_signals += 1
    if rsi < 65: buy_signals += 1
    if vol_surge: buy_signals += 1

    signal = "매수" if buy_signals >= 2 else "관망"

    # 보유 추천 기간
    hold_days = "3~5일" if rsi < 60 and golden_cross else "내일 재확인"

    return {
        "current": current,
        "ma5": round(ma5),
        "ma20": round(ma20),
        "rsi": rsi,
        "golden_cross": golden_cross,
        "vol_surge": vol_surge,
        "signal": signal,
        "buy_signals": buy_signals,
        "target_3": round(current * 1.03 / 100) * 100,
        "target_5": round(current * 1.05 / 100) * 100,
        "target_10": round(current * 1.10 / 100) * 100,
        "stop_loss": round(current * 0.98 / 100) * 100,
        "pnl": round(((current - avg_price) / avg_price) * 100, 1) if avg_price else 0,
        "hold_days": hold_days,
    }

def find_hot_stock():
    """거래량 급등 후보 종목 스캔 (주요 종목 중)"""
    candidates = [
        {"code": "005930", "name": "삼성전자"},
        {"code": "035420", "name": "NAVER"},
        {"code": "051910", "name": "LG화학"},
        {"code": "006400", "name": "삼성SDI"},
        {"code": "035720", "name": "카카오"},
        {"code": "028260", "name": "삼성물산"},
        {"code": "207940", "name": "삼성바이오로직스"},
    ]
    best = None
    best_score = 0
    for c in candidates:
        try:
            prices, volumes = get_stock_price(c["code"])
            if not prices or len(prices) < 20:
                continue
            avg_vol = sum(volumes[-20:]) / 20
            vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1
            rsi = calc_rsi(prices)
            ma5 = sum(prices[-5:]) / 5
            ma20 = sum(prices[-20:]) / 20
            score = vol_ratio
            if ma5 > ma20: score += 1
            if 30 < rsi < 65: score += 1
            if score > best_score:
                best_score = score
                best = {
                    "name": c["name"],
                    "code": c["code"],
                    "current": prices[-1],
                    "vol_ratio": round(vol_ratio, 1),
                    "rsi": rsi,
                    "target_10": round(prices[-1] * 1.10 / 100) * 100,
                    "stop_loss": round(prices[-1] * 0.97 / 100) * 100,
                    "shares": int(1000000 / prices[-1]),  # 100만원 기준 주수
                }
        except:
            continue
    return best

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    res = requests.post(url, json=payload, timeout=10)
    return res.status_code == 200

def morning_alert():
    """07:50 오전 알림"""
    now = datetime.now().strftime("%Y.%m.%d (%a)")
    prices, volumes = get_stock_price(MAIN_STOCK["code"])
    a = analyze(prices, volumes, MAIN_STOCK["avg_price"])
    hot = find_hot_stock()

    if not a:
        send_telegram("⚠️ 데이터 로딩 실패. 오늘 매매 보류하세요.")
        return

    # 장 안좋은지 판단
    market_bad = a["rsi"] > 72 or (not a["golden_cross"] and a["rsi"] > 65)

    if market_bad:
        msg = f"""⚠️ SK하이닉스 오전 매매 신호
━━━━━━━━━━━━━━━
📅 {now} 07:50

📊 기술 신호
• RSI {a['rsi']} → {"과매수 ⚠️" if a['rsi'] > 70 else "불안정"}
• {"골든크로스 ✅" if a['golden_cross'] else "데드크로스 ❌"}
• 현재가: {int(a['current']):,}원
• 평단 대비: {a['pnl']:+.1f}%

🚫 오늘 매수 금지!
장 상황이 좋지 않아요 💤
━━━━━━━━━━━━━━━"""
    else:
        hold_msg = f"📌 보유 추천: {a['hold_days']} 더 보유하세요" if a['pnl'] < 0 else f"📌 {a['pnl']:+.1f}% 수익 중 — {a['hold_days']} 보유 추천"

        msg = f"""🔔 오전 매매 신호
━━━━━━━━━━━━━━━
📅 {now} 07:50

1️⃣ SK하이닉스 (000660)
• 현재가: {int(a['current']):,}원
• 📈 매수가: {int(a['current']):,}원
• 🎯 목표가(3%): {int(a['target_3']):,}원
• 🎯 목표가(5%): {int(a['target_5']):,}원
• 🛑 손절가: {int(a['stop_loss']):,}원
• 평단 대비: {a['pnl']:+.1f}% (237만원)
{hold_msg}

━━━━━━━━━━━━━━━"""

        if hot:
            shares = hot['shares']
            invest = int(hot['current'] * shares)
            profit = int(hot['target_10'] * shares - invest)
            msg += f"""
2️⃣ 오전 급등 후보: {hot['name']}
• 거래량: 평소 대비 {hot['vol_ratio']}배 ⚡
• 현재가: {int(hot['current']):,}원
• 📈 매수가: {int(hot['current']):,}원
• 🎯 목표가(10%): {int(hot['target_10']):,}원
• 🛑 손절가: {int(hot['stop_loss']):,}원
• 100만원 투자 시 → {shares}주
• 목표 수익: +{profit:,}원

✅ 08:00~09:20 단타 구간
━━━━━━━━━━━━━━━"""
        else:
            msg += "\n2️⃣ 오늘 급등 후보 없음 💤\n━━━━━━━━━━━━━━━"

    send_telegram(msg)
    print("오전 알림 전송 완료!")

def afternoon_alert():
    """15:10 오후 알림"""
    now = datetime.now().strftime("%Y.%m.%d (%a)")
    prices, volumes = get_stock_price(MAIN_STOCK["code"])
    a = analyze(prices, volumes, MAIN_STOCK["avg_price"])

    if not a:
        send_telegram("⚠️ 오후 데이터 로딩 실패.")
        return

    # 종가 매수 추천 판단
    close_buy = a["golden_cross"] and a["rsi"] < 65 and a["buy_signals"] >= 2

    if close_buy:
        msg = f"""📊 SK하이닉스 오후 전략
━━━━━━━━━━━━━━━
📅 {now} 15:10

✅ 종가 매수 추천!

• 종가 예상가: {int(a['current']):,}원
• 🎯 내일 목표가(3%): {int(a['target_3']):,}원
• 🎯 내일 목표가(5%): {int(a['target_5']):,}원
• 🛑 손절가: {int(a['stop_loss']):,}원

📌 오늘 장 마감 직전
   종가 매수 주문 넣으세요!
━━━━━━━━━━━━━━━"""
    else:
        msg = f"""📊 SK하이닉스 오후 전략
━━━━━━━━━━━━━━━
📅 {now} 15:10

❌ 종가 매수 비추천

• RSI {a['rsi']} → {"과매수" if a['rsi'] > 65 else "신호 약함"}
• {"골든크로스 ✅" if a['golden_cross'] else "데드크로스 ❌"}
• 현재가: {int(a['current']):,}원

💤 오늘은 현금 보유 추천
━━━━━━━━━━━━━━━"""

    send_telegram(msg)
    print("오후 알림 전송 완료!")

def main():
    print(f"[{datetime.now()}] MODE: {MODE}")
    if MODE == "afternoon":
        afternoon_alert()
    else:
        morning_alert()

if __name__ == "__main__":
    main()
