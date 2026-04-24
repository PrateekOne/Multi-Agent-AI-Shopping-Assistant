def compare_prices(blinkit_cart, zepto_cart):
    result = []

    for b, z in zip(blinkit_cart, zepto_cart):
        result.append({
            "name": b["name"],
            "blinkit": b["price"],
            "zepto": z["price"]
        })

    blinkit_total = sum(i["blinkit"] for i in result)
    zepto_total = sum(i["zepto"] for i in result)

    savings = abs(blinkit_total - zepto_total)
    cheaper = "Blinkit" if blinkit_total < zepto_total else "Zepto"

    return {
        "items": result,
        "blinkit_total": blinkit_total,
        "zepto_total": zepto_total,
        "savings": savings,
        "cheaper": cheaper
    }