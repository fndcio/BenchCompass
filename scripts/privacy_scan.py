#!/usr/bin/env python3
"""Public ağaç gizlilik taraması (hard gate).

Bulgu varsa exit 1. Donanım tier örnekleri (OMEN, RTX 5070, Ryzen)
hard-fail DEĞİLDİR — kullanılıcı onayıyla örnek tier olarak korunur.
Yanlış pozitifler için kök `.privacy-allowlist` (bir satır = gerekçeli
`substring | gerekçe`) kullanılır.
"""

import re
import sys
from pathlib import Path

TEXT_EXTS = {
    ".py",
    ".js",
    ".html",
    ".css",
    ".json",
    ".md",
    ".txt",
    ".ps1",
    ".cmd",
    ".bat",
    ".sh",
    ".toml",
    ".yaml",
    ".yml",
    ".env",
}
HARD_PATTERNS = [
    (re.compile(r"[A-Za-z]:\\Users\\developer"), "özel kullanıcı yolu"),
    (re.compile(r"[A-Za-z]:\\Users\\"), "mutlak kullanıcı yolu"),
    (re.compile(r"/home/(?!developer/)[A-Za-z0-9._-]+/"), "özel unix yolu"),
    (
        re.compile(
            r"[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
        ),
        "e-posta",
    ),
    (re.compile(r"gho_[A-Za-z0-9]{20,}"), "GitHub token"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "API anahtarı benzeri"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS anahtarı benzeri"),
]
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
BAD_JSON_KEYS = ('"user"', '"promptSample"', '"outputSample"')
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest-basetemp"}


def _is_private_ip(ip: str) -> bool:
    return (
        ip.startswith("127.")
        or ip.startswith("10.")
        or ip.startswith("192.168.")
        or ip.startswith("0.")
        or ip.startswith("172.16.")
        or ip.startswith("172.17.")
        or ip.startswith("172.18.")
        or ip.startswith("172.19.")
        or ip.startswith("172.20.")
        or ip.startswith("172.21.")
        or ip.startswith("172.22.")
        or ip.startswith("172.23.")
        or ip.startswith("172.24.")
        or ip.startswith("172.25.")
        or ip.startswith("172.26.")
        or ip.startswith("172.27.")
        or ip.startswith("172.28.")
        or ip.startswith("172.29.")
        or ip.startswith("172.30.")
        or ip.startswith("172.31.")
        or ip.startswith("100.64.")
        or ip.startswith("100.65.")
        or ip.startswith("100.66.")
        or ip.startswith("100.67.")
        or ip.startswith("100.68.")
        or ip.startswith("100.69.")
        or ip.startswith("100.70.")
        or ip.startswith("100.71.")
        or ip.startswith("100.72.")
        or ip.startswith("100.73.")
        or ip.startswith("100.74.")
        or ip.startswith("100.75.")
        or ip.startswith("100.76.")
        or ip.startswith("100.77.")
        or ip.startswith("100.78.")
        or ip.startswith("100.79.")
        or ip.startswith("100.80.")
        or ip.startswith("100.81.")
        or ip.startswith("100.82.")
        or ip.startswith("100.83.")
        or ip.startswith("100.84.")
        or ip.startswith("100.85.")
        or ip.startswith("100.86.")
        or ip.startswith("100.87.")
        or ip.startswith("100.88.")
        or ip.startswith("100.89.")
        or ip.startswith("100.90.")
        or ip.startswith("100.91.")
        or ip.startswith("100.92.")
        or ip.startswith("100.93.")
        or ip.startswith("100.94.")
        or ip.startswith("100.95.")
        or ip.startswith("100.96.")
        or ip.startswith("100.97.")
        or ip.startswith("100.98.")
        or ip.startswith("100.99.")
        or ip.startswith("100.100.")
        or ip.startswith("100.101.")
        or ip.startswith("100.102.")
        or ip.startswith("100.103.")
        or ip.startswith("100.104.")
        or ip.startswith("100.105.")
        or ip.startswith("100.106.")
        or ip.startswith("100.107.")
        or ip.startswith("100.108.")
        or ip.startswith("100.109.")
        or ip.startswith("100.110.")
        or ip.startswith("100.111.")
        or ip.startswith("100.112.")
        or ip.startswith("100.113.")
        or ip.startswith("100.114.")
        or ip.startswith("100.115.")
        or ip.startswith("100.116.")
        or ip.startswith("100.117.")
        or ip.startswith("100.118.")
        or ip.startswith("100.119.")
        or ip.startswith("100.120.")
        or ip.startswith("100.121.")
        or ip.startswith("100.122.")
        or ip.startswith("100.123.")
        or ip.startswith("100.124.")
        or ip.startswith("100.125.")
        or ip.startswith("100.126.")
        or ip.startswith("100.127.")
    )


def load_allowlist(root: Path) -> list[str]:
    p = root / ".privacy-allowlist"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line.split("|")[0].strip())
    return out


def scan_file(path: Path, allow: list[str]) -> list[str]:
    try:
        if path.suffix.lower() not in TEXT_EXTS:
            return []
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    findings: list[str] = []
    for rx, label in HARD_PATTERNS:
        for m in rx.finditer(text):
            snippet = m.group(0)[:80]
            if any(a in snippet for a in allow):
                continue
            findings.append(f"{label}: {snippet!r} -> {path}")
    for m in IP_RE.finditer(text):
        ip = m.group(0)
        # Sürüm sayıları (örn. 7.898.369.152) IP değil — geçersiz octet >255
        parts = ip.split(".")
        try:
            nums = [int(x) for x in parts]
        except ValueError:
            continue
        if any(n > 255 for n in nums):
            continue
        if _is_private_ip(ip):
            continue
        if any(a == ip for a in allow):
            continue
        findings.append(f"public IP: {ip!r} -> {path}")
    if path.suffix.lower() == ".json":
        for key in BAD_JSON_KEYS:
            if key in text and not any(a in key for a in allow):
                findings.append(f"kişisel veri alanı {key} -> {path}")
    return findings


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    allow = load_allowlist(root)
    all_findings: list[str] = []
    for base, dirs, files in __import__("os").walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            all_findings.extend(scan_file(Path(base) / fn, allow))
    if all_findings:
        print("PRIVACY SCAN FAIL", file=sys.stderr)
        for f in all_findings:
            print(f" - {f}", file=sys.stderr)
        return 1
    print("PRIVACY SCAN OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
