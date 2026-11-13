"""Распределение долей трафика между офферами потока.

Правила (как в редакторе из видео ТЗ):
- снятый оффер (removed) получает 0% и остаётся в списке, чтобы его можно было вернуть;
- закреплённый оффер (pinned) сохраняет свою долю;
- остаток 100% − сумма закреплённых делится поровну между незакреплёнными,
  лишние проценты от деления достаются первым по списку: 3 оффера → 34/33/33,
  остаток 75 на двоих → 38/37.
"""
from dataclasses import dataclass


class ShareError(ValueError):
    pass


@dataclass
class Item:
    offer_id: int
    share: int = 0
    pinned: bool = False
    removed: bool = False


def rebalance(items: list[Item]) -> list[Item]:
    """Пересчитывает доли на месте и возвращает тот же список."""
    for item in items:
        if item.removed:
            item.share = 0
            item.pinned = False
        elif not 0 <= item.share <= 100:
            raise ShareError(f"Доля оффера {item.offer_id} должна быть от 0 до 100")

    active = [i for i in items if not i.removed]
    pinned_sum = sum(i.share for i in active if i.pinned)
    if pinned_sum > 100:
        raise ShareError(f"Закреплённые доли дают {pinned_sum}% — больше 100%")

    free = [i for i in active if not i.pinned]
    if free:
        base, extra = divmod(100 - pinned_sum, len(free))
        for index, item in enumerate(free):
            item.share = base + (1 if index < extra else 0)
    return items


def validate(items: list[Item]) -> None:
    """Проверка перед отправкой в Keitaro: Keitaro сам сумму долей не проверяет."""
    ids = [i.offer_id for i in items]
    if len(ids) != len(set(ids)):
        raise ShareError("Оффер добавлен в поток дважды")
    active = [i for i in items if not i.removed]
    if not active:
        raise ShareError("В потоке должен остаться хотя бы один оффер")
    total = sum(i.share for i in active)
    if total != 100:
        raise ShareError(f"Сумма долей {total}%, нужно ровно 100%")
