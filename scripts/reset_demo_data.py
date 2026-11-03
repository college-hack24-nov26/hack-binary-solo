"""Clear the demo patients' records and their audit entries so the demo can be rerun.
Removes only the synthetic demo tokens (fixtures/demo/*.json and the kiosk demo patient). Records of other patients are untouched.
The audit log is one hash chain: if entries of other patients remain, the log is left alone unless --rechain-others is given
(that re-computes the hashes of the remaining entries, which changes their hashes).
Run: .venv/bin/python scripts/reset_demo_data.py [--rechain-others]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dosing import audit, demo  # noqa: E402
from intake.demo import DEMO_TOKEN  # noqa: E402
from records import store  # noqa: E402


def demo_tokens() -> set:
    return set(demo.DEMO_TOKENS) | {DEMO_TOKEN}


def reset(rechain_others: bool = False) -> dict:
    tokens = demo_tokens()
    removed = [t for t in sorted(tokens) if store.load(t) is not None]
    for t in removed:
        store.delete(t)
    entries = audit.read()
    keep = [e for e in entries if e.get("token") not in tokens]
    dropped = len(entries) - len(keep)
    audit_note = "no demo audit entries"
    if dropped and not keep:
        audit.log_path().unlink()
        audit_note = f"removed {dropped} demo audit entries (log is now empty)"
    elif dropped and rechain_others:
        audit.rewrite(keep)
        audit_note = f"removed {dropped} demo audit entries and re-chained {len(keep)} others"
    elif dropped:
        audit_note = (f"{dropped} demo audit entries kept: {len(keep)} entries of other patients share the chain. "
                      "Re-run with --rechain-others to remove them")
        dropped = 0
    return {"records_removed": removed, "audit_removed": dropped, "audit_note": audit_note, "chain_valid": audit.verify()}


def main(argv=None) -> int:
    r = reset("--rechain-others" in (argv if argv is not None else sys.argv[1:]))
    print(f"Records removed: {', '.join(r['records_removed']) or 'none'}")
    print(f"Audit: {r['audit_note']} (chain valid: {r['chain_valid']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
