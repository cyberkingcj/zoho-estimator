from datetime import date

def calculate_amount(qty, price):
    try:
        return round(float(qty) * float(price), 2)
    except:
        return 0.0

def today_date():
    return date.today().isoformat()
