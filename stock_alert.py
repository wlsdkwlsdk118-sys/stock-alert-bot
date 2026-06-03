import requests
from datetime import datetime
import os

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

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

def find_hot_stock():
    candidates = [
        {"code": "005930", "name": "삼성전자"},
        {"code": "035420", "name": "NAVER"},
        {"code": "051910", "name": "LG화학"},
        {"code": "006400", "name": "삼성SDI"},
        {"code": "035720", "name": "카카오"},
        {"code": "207940", "name": "삼성바이오로직스"},
        {"code": "005380", "name": "현대차"},
        {"code": "000270", "name": "기아"},
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
            if rsi < 70: score += 1
            if score > best_score:
                best_score = score
                best = {
                    "name": c["name"],
                    "current": prices[-1],
                    "vol_ratio": round(vol_ratio, 1),
                    "rsi": rsi,
                    "target_10": round(prices[-1] * 1.10 / 100) * 100,
                    "stop_loss": round(prices[-1] * 0.97 / 100) * 100,
                    "shares": int(1000000 / prices[-1]),
                }
        except:
            continue
    return best

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    res = requests.post(url, json=payload, timeout=10)
    return res.status_code == 200

def main():
    now = datetime.now().strftime("%Y.%m.%d (%a)")
    prices, volumes = get_stock_price(MAIN_STOCK["code"])

    if not prices or len(prices) < 20:
        send_telegram("⚠️ 데이터 로딩 실패")
        return

    current = prices[-1]
    ma5 = sum(prices[-5:]) / 5
    ma20 = sum(prices[-20:]) / 20
    rsi = calc_rsi(prices)
    golden_cross = ma5 > ma20
    pnl = round(((current - MAIN_STOCK["avg_price"]) / MAIN_STOCK["avg_price"]) * 100, 1)

    target_3 = round(current * 1.03 / 100) * 100
    target_5 = round(current * 1.05 / 100) * 100
    stop_loss = round(current * 0.98 / 100) * 100

    # 보유 추천
    if pnl < 0:
        hold_msg = "📌 조금만 더 보유하세요 — 평단가 회복 구간"
    elif pnl < 5:
        hold_msg = "📌 3~5일 더 보유 추천"
    else:
        hold_msg = f"📌 {pnl:+.1f}% 수익 중 — 목표가까지 보유 추천"

    # 급등주
    hot = find_hot_stock()

    msg = f"""🔔 오전 매매 신호
━━━━━━━━━━━━━━━
📅 {now} 07:50

1️⃣ SK하이닉스 (000660)
• RSI {rsi} / {"골든크로스 ✅" if golden_cross else "데드크로스 ❌"}
• 현재가: {int(current):,}원
• 📈 매수가: {int(current):,}원
• 🎯 목표가(3%): {int(target_3):,}원
• 🎯 목표가(5%): {int(target_5):,}원
• 🛑 손절가: {int(stop_loss):,}원
• 평단 대비: {pnl:+.1f}%
{hold_msg}
━━━━━━━━━━━━━━━"""

    if hot:
        shares = hot['shares']
        profit = int((hot['target_10'] - hot['current']) * shares)
        msg += f"""

2️⃣ 오전 급등 후보: {hot['name']}
• 거래량: 평소 대비 {hot['vol_ratio']}배 ⚡
• 현재가: {int(hot['current']):,}원
• 📈 매수가: {int(hot['current']):,}원
• 🎯 목표가(10%): {int(hot['target_10']):,}원
• 🛑 손절가: {int(hot['stop_loss']):,}원
• 100만원 → {shares}주 매수 시
• 목표 수익: +{profit:,}원

✅ 08:00~09:20 단타 구간
━━━━━━━━━━━━━━━"""
    else:
        msg += "\n\n2️⃣ 오늘 급등 후보 없음 💤\n━━━━━━━━━━━━━━━"

    send_telegram(msg)
    print("전송 완료!")

if __name__ == "__main__":
    main()
