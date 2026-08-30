#!/usr/bin/env python3
"""Static checks for the PowerShell operator scripts (Stage 4, N2).

WHY THIS EXISTS
---------------
`scripts/run_local_demo.ps1` is handed to a non-technical operator on Windows,
and this repository's CI has no Windows runner and no PowerShell interpreter —
the agent sandbox cannot install one either (packages.microsoft.com, the
GitHub release CDN and nuget are all unreachable). So the script cannot be
*executed* before it reaches the person who is blocked by it.

That makes the failure modes we CAN check statically worth checking, because
each of them makes the script unusable for its entire audience:

1. **UTF-8 BOM.** Windows PowerShell 5.1 — still the default `powershell.exe`
   on Windows 10/11 — decodes a `.ps1` as ANSI unless it starts with a UTF-8
   BOM. Without one, every Persian message renders as mojibake. This is not
   theoretical: it is the single most common way a non-ASCII PowerShell script
   arrives broken.
2. **Console output encoding.** Even with a BOM, the console codepage mangles
   non-ASCII on the way out unless `[Console]::OutputEncoding` is set.
3. **Balanced quotes/braces** and **CRLF-safe** content.
4. **Every `param()` switch is actually handled** in the body — a documented
   flag that silently does nothing is worse than no flag.
5. **No `curl`/`wget`/`sudo`** — Unix-isms that fail or alias badly on Windows
   (`curl` is an alias for `Invoke-WebRequest` in PS 5.1, with different args).

Run: `python3 scripts/check_ps1.py` — exit 0 = pass.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGETS = sorted(REPO.glob("scripts/*.ps1"))

GREEN, RED, YELLOW, RESET = "\033[0;32m", "\033[0;31m", "\033[0;33m", "\033[0m"


class Checker:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, ok: bool, name: str, detail: str) -> None:
        tag = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"  {tag}  {name}: {detail}")
        if not ok:
            self.failures.append(f"{name}: {detail}")

    def warn(self, name: str, detail: str) -> None:
        print(f"  {YELLOW}NOTE{RESET}  {name}: {detail}")


def check_file(path: Path, c: Checker) -> None:
    rel = path.relative_to(REPO)
    print(f"\n{rel}\n" + "-" * 62)

    raw = path.read_bytes()

    # 1. UTF-8 BOM ------------------------------------------------------------
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    body = raw[3:] if has_bom else raw
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        c.check(False, "utf-8 decode", str(exc))
        return

    non_ascii = any(ord(ch) > 127 for ch in text)
    if non_ascii:
        c.check(has_bom, "UTF-8 BOM",
                "present — Windows PowerShell 5.1 will render the Persian text"
                if has_bom
                else "MISSING and the file contains non-ASCII text: PS 5.1 reads "
                     "it as ANSI and every Persian message becomes mojibake")
    else:
        c.warn("UTF-8 BOM", "file is pure ASCII; BOM not required")

    # 2. console output encoding ---------------------------------------------
    if non_ascii:
        c.check("[Console]::OutputEncoding" in text, "console encoding",
                "set explicitly"
                if "[Console]::OutputEncoding" in text
                else "not set — the console codepage will mangle non-ASCII output")

    # 3a. CRLF / stray CR -----------------------------------------------------
    c.check(b"\r" not in body or b"\r\n" in body, "line endings",
            "consistent" if b"\r" not in body or b"\r\n" in body
            else "stray CR without LF")

    # 3b. balanced braces and parentheses ------------------------------------
    #     (string literals and comments removed first, so braces inside text
    #     like "{Engine running}" cannot cause a false alarm)
    stripped = re.sub(r"<#.*?#>", "", text, flags=re.S)          # block comments
    stripped = re.sub(r"(?m)#.*$", "", stripped)                 # line comments
    stripped = re.sub(r"'[^'\n]*'", "''", stripped)              # single-quoted
    stripped = re.sub(r'"[^"\n]*"', '""', stripped)              # double-quoted
    for open_ch, close_ch, label in (("{", "}", "braces"), ("(", ")", "parens")):
        n_open, n_close = stripped.count(open_ch), stripped.count(close_ch)
        c.check(n_open == n_close, f"balanced {label}",
                f"{n_open} open / {n_close} close"
                + ("" if n_open == n_close else "  <-- MISMATCH"))

    # 3c. balanced quotes -----------------------------------------------------
    no_comments = re.sub(r"<#.*?#>", "", text, flags=re.S)
    no_comments = re.sub(r"(?m)#.*$", "", no_comments)
    for quote, label in (("'", "single quotes"), ('"', "double quotes")):
        count = no_comments.count(quote)
        c.check(count % 2 == 0, f"balanced {label}",
                f"{count} occurrences"
                + ("" if count % 2 == 0 else "  <-- ODD, likely unterminated string"))

    # 4. every declared switch is handled ------------------------------------
    param_block = re.search(r"param\s*\((.*?)\)", text, flags=re.S)
    if param_block:
        switches = re.findall(r"\[switch\]\s*\$(\w+)", param_block.group(1))
        body_after = text[param_block.end():]
        for sw in switches:
            used = re.search(rf"\$\b{sw}\b", body_after) is not None
            c.check(used, f"switch -{sw}",
                    "handled in the body" if used
                    else "declared but NEVER used — a documented flag that does nothing")
        if switches:
            c.warn("switches", f"declared: {', '.join('-' + s for s in switches)}")

    # 5. no Unix-isms ---------------------------------------------------------
    for bad, why in (
        (r"(?m)^\s*sudo\b", "sudo does not exist on Windows"),
        (r"(?m)^\s*wget\b", "wget is an alias with different arguments in PS 5.1"),
        (r"(?m)^\s*curl\s+-", "curl is an alias for Invoke-WebRequest in PS 5.1; "
                              "Unix-style flags fail"),
    ):
        hits = re.findall(bad, text)
        c.check(not hits, f"no unix-ism ({bad.split(chr(92))[-1][:12]})",
                "none found" if not hits else f"{len(hits)} occurrence(s): {why}")

    # 6. shebang-style safety: script must not silently continue on error -----
    c.check("$ErrorActionPreference" in text, "error preference",
            "set" if "$ErrorActionPreference" in text
            else "not set — failures would be silently ignored")


def main() -> int:
    if not TARGETS:
        print("no .ps1 files found under scripts/")
        return 0

    print("PowerShell static checks (no interpreter available in CI/sandbox)")
    c = Checker()
    for path in TARGETS:
        check_file(path, c)

    print("\n" + "=" * 62)
    if c.failures:
        print(f"{RED}RESULT: FAIL{RESET} — {len(c.failures)} problem(s):")
        for f in c.failures:
            print(f"  - {f}")
        return 1
    print(f"{GREEN}RESULT: PASS{RESET}")
    print("\nNOTE: these are STATIC checks. They cannot prove the script runs.")
    print("First execution on a real Windows machine is the acceptance test;")
    print("relay the console output as evidence (Stage 4, N2 DoD).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
