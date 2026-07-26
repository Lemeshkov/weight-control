# backend/python
"""
Тест преобразования HEX в INT
"""
def hex_to_signed_int(hex_str):
    try:
        val = int(hex_str, 16)
        if val > 0x7FFFFFFF:
            val = val - 0x100000000
        return val
    except ValueError:
        return 0

# Тестируем
test_values = [
    ("FFFFFC18", -1000),
    ("3E8", 1000),
    ("1388", 5000),
    ("FFFF3CB0", -50000),
]

for hex_val, expected in test_values:
    result = hex_to_signed_int(hex_val)
    print(f"{hex_val} -> {result} (ожидалось {expected}) {'✅' if result == expected else '❌'}")