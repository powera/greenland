#!/usr/bin/env python3
"""Pre-commit helper: print the number of pending Barsukas string replacements."""

from strings.generate_barsukas_strings import compute_plan


def main() -> int:
    (
        template_plans,
        standard_catalog_state,
        cstr_catalog_state,
        _standard_stats,
        _cstr_stats,
    ) = compute_plan()
    pending = sum(len(items) for items in template_plans.values())
    print(pending)
    has_new_keys = any(standard_catalog_state.new_keys.values()) or any(
        cstr_catalog_state.new_keys.values()
    )
    return 1 if pending > 0 or has_new_keys else 0


if __name__ == "__main__":
    raise SystemExit(main())
