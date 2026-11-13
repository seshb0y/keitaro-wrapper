import pytest

from app.shares import Item, ShareError, rebalance, validate


def shares(items):
    return [i.share for i in items]


def test_even_split_remainder_goes_to_first():
    assert shares(rebalance([Item(1), Item(2), Item(3)])) == [34, 33, 33]
    assert shares(rebalance([Item(1), Item(2), Item(3), Item(4)])) == [25, 25, 25, 25]


def test_removed_gets_zero_and_rest_rebalanced():
    items = rebalance([Item(1, 25), Item(2, 25), Item(3, 25, removed=True), Item(4, 25)])
    assert shares(items) == [34, 33, 0, 33]


def test_pinned_share_is_kept_rest_split():
    # сценарий из видео ТЗ: закреплено 25%, оставшиеся 75% на двоих → 38/37
    items = rebalance([Item(1), Item(2), Item(3, 25, pinned=True), Item(4, removed=True)])
    assert shares(items) == [38, 37, 25, 0]


def test_removed_offer_loses_pin():
    items = rebalance([Item(1, 40, pinned=True, removed=True), Item(2)])
    assert items[0].pinned is False
    assert shares(items) == [0, 100]


def test_pinned_over_100_rejected():
    with pytest.raises(ShareError):
        rebalance([Item(1, 70, pinned=True), Item(2, 40, pinned=True)])


def test_validate_requires_exactly_100():
    validate([Item(1, 60), Item(2, 40)])
    with pytest.raises(ShareError, match="110"):
        validate([Item(1, 60), Item(2, 50)])
    with pytest.raises(ShareError, match="хотя бы один"):
        validate([Item(1, 0, removed=True)])
    with pytest.raises(ShareError, match="дважды"):
        validate([Item(1, 50), Item(1, 50)])


def test_all_pinned_not_100_fails_validation():
    items = rebalance([Item(1, 30, pinned=True), Item(2, 30, pinned=True)])
    with pytest.raises(ShareError, match="60"):
        validate(items)
