from nomaya.rules.pii import detect_pii


def test_detects_ssn():
    findings = detect_pii("My SSN is 412-55-9931 for the file.")
    assert any(f.type == "ssn" for f in findings)


def test_detects_valid_credit_card_luhn():
    # 4111 1111 1111 1111 is a well-known Luhn-valid test number.
    findings = detect_pii("card 4111 1111 1111 1111")
    assert any(f.type == "credit_card" for f in findings)


def test_rejects_luhn_invalid_card():
    findings = detect_pii("order number 1234 5678 9012 3456")
    assert not any(f.type == "credit_card" for f in findings)


def test_detects_account_number_with_context():
    findings = detect_pii("Your account number is 1234567800124321.")
    assert any(f.type == "bank_account" for f in findings)


def test_masks_value():
    f = detect_pii("SSN 412-55-9931")[0]
    assert f.redacted.endswith("9931")
    assert "412-55" not in f.redacted


def test_balance_is_not_flagged():
    # Guards the benign-control case: a dollar balance must not look like PII.
    findings = detect_pii("Your balance is $2,450.18.", types=["ssn", "bank_account", "credit_card"])
    assert findings == []


def test_type_filter():
    findings = detect_pii("ssn 412-55-9931 email a@b.com", types=["email"])
    assert all(f.type == "email" for f in findings)
