"""privacy_scan: public ağaç hard gate (Y29)."""

from scripts.privacy_scan import scan_file


def test_clean_tier_example_passes(tmp_path):
    p = tmp_path / "a.py"
    p.write_text('GPU = "RTX 5070 Ti"\nPANEL = "BenchCompass OMEN"\n', encoding="utf-8")
    assert scan_file(p, []) == []


def test_absolute_path_fails(tmp_path):
    p = tmp_path / "a.py"
    p.write_text('x = r"C:\\Users\\developer\\secret"\n', encoding="utf-8")
    findings = scan_file(p, [])
    assert findings
    assert any("kullanıcı yolu" in f for f in findings)


def test_email_and_public_ip_fail(tmp_path):
    p = tmp_path / "a.txt"
    mail = "foo" + "@" + "bar.com"
    ip = "27.90." + "18.50"
    p.write_text(f"mail {mail} ip {ip} loop 127.0.0.1\n", encoding="utf-8")
    findings = scan_file(p, [])
    labels = " ".join(findings)
    assert "e-posta" in labels
    assert ip in labels
    assert "127.0.0.1" not in labels


def test_json_personal_keys_fail(tmp_path):
    p = tmp_path / "d.json"
    p.write_text('{"user": {"username": "x"}}', encoding="utf-8")
    assert any("kişisel veri alanı" in f for f in scan_file(p, []))


def test_seed_without_keys_passes(tmp_path):
    p = tmp_path / "d.json"
    p.write_text('{"model": "m", "tokSOut": 1.2}', encoding="utf-8")
    assert scan_file(p, []) == []


def test_allowlist_suppresses(tmp_path):
    p = tmp_path / "a.txt"
    mail = "foo" + "@" + "bar.com"
    p.write_text(f"mail {mail}\n", encoding="utf-8")
    assert scan_file(p, [mail]) == []
