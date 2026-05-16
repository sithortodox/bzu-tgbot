def calculate_xe(carbs: float | None) -> float | None:
    if carbs is None:
        return None
    return round(carbs / 12.0, 1)


def calculate_bje(proteins: float | None, fats: float | None) -> float | None:
    if proteins is None or fats is None:
        return None
    return round(proteins / 2.0 + fats / 2.0, 1)


def get_bje_warning(bje: float | None) -> str | None:
    if bje is None:
        return None
    if bje > 5:
        return "⚠️ Высокое содержание белково-жировых единиц. Это может замедлить всасывание углеводов. Проконсультируйтесь с врачом."
    if bje > 3:
        return "💡 Умеренное содержание БЖЕ. Углеводы могут всасываться медленнее."
    return None


def get_gi_category(gi: float | None) -> str | None:
    if gi is None:
        return None
    if gi <= 35:
        return "Низкий ГИ"
    if gi <= 55:
        return "Средний ГИ"
    return "Высокий ГИ ⚠️"
