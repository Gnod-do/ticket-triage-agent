from fbagent.pii import mask_pii


def test_masks_phone_email_inn_card():
    t = "Звоните +7 (912) 345-67-89, почта a.ivanov@mail.ru, ИНН 7701234567, карта 4276 1234 5678 9012"
    m = mask_pii(t)
    assert "[PHONE]" in m and "[EMAIL]" in m and "[INN]" in m and "[CARD]" in m
    assert "912" not in m and "ivanov" not in m and "7701234567" not in m


def test_masks_phone_variants():
    for p in ["89123456789", "8 912 345 67 89", "+79123456789", "+7-912-345-67-89"]:
        assert mask_pii(f"тел {p}") == "тел [PHONE]", p


def test_keeps_dates_and_error_codes():
    assert mask_pii("Отгрузка 11.07.2026, ошибка 404") == "Отгрузка 11.07.2026, ошибка 404"


def test_idempotent():
    m = mask_pii("ИНН 770123456789, тел +79123456789")
    assert mask_pii(m) == m
