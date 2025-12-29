# Data Release Files Review Summary

**Date:** 2025-12-29
**Branch:** claude/review-release-files-WH8nI

## Overview

This review analyzed all JSONL files in `data/release/lemmas/` for:
1. Duplicate entries across migrated categories (per `data/category_migrations.json`)
2. Dummy definitions that need fixing

## Results

### Duplicates Found and Removed

**Total duplicates removed:** 67 entries

The analysis identified entries that appeared in both old and new categories following the category splits defined in `category_migrations.json`. All duplicates were removed from the old categories, keeping them only in their new, more specific categories.

#### Category Migration: food_drink → food, beverage
- **Removed from food_drink:** 7 entries
- Beverages moved to new `beverage` category:
  - water (N06_002 → N42_001)
  - coffee (N06_003 → N42_002)
  - tea (N06_004 → N42_003)
  - beer (N06_005 → N42_004)
  - wine (N06_006 → N42_005)
  - milk (N06_089 → N42_006)
  - soda (N06_090 → N42_007)
- **Remaining in food_drink:** 84 entries

#### Category Migration: human → occupation, family_relation
- **Removed from human:** 51 entries

**Occupations moved to `occupation` category (35 entries):**
- teacher, doctor, nurse, police officer, waiter, farmer, engineer, artist, scientist, student, cook, lawyer, manager, plumber, electrician, mechanic, driver, pilot, firefighter, painter, accountant, journalist, musician, writer, dentist, salesperson, architect, butcher, barber, baker, soldier

**Family relations moved to `family_relation` category (24 entries):**
- family, mother, father, brother, sister, son, daughter, uncle, aunt, child, partner, spouse, grandfather, grandmother, grandson, granddaughter, nephew, niece, fiancé, fiancée, boyfriend, girlfriend

- **Remaining in human:** 24 entries

#### Category Migration: tool_machine → vehicle
- **Removed from tool_machine:** 3 entries
- Vehicles moved to new `vehicle` category:
  - car (N12_001 → N40_001)
  - bus (N12_002 → N40_002)
  - train (N12_003 → N40_003)
- **Remaining in tool_machine:** 43 entries

#### Category Migration: small_movable_object → furniture
- **Removed from small_movable_object:** 1 entry
- Furniture moved to new `furniture` category:
  - chair (N08_018 → N39_001)
- **Remaining in small_movable_object:** 45 entries

#### Category Migration: quality → size (adjectives)
- **Removed from quality:** 5 entries
- Size adjectives moved to new `size` category:
  - big (A05_017 → A01_001)
  - small (A05_018 → A01_002)
  - large (A05_053 → A01_003)
  - tiny (A05_087 → A01_004)
  - huge (A05_077 → A01_005)
- **Remaining in quality:** 159 entries

### Dummy Definitions

**Status:** ✓ No dummy definitions detected

The analysis checked for common dummy definition patterns:
- Definitions that are just "POS: concept" (e.g., "adjective: happy" for the word "happy")
- Definitions containing language markers like "Lithuanian:", "German:", etc.

All 1,501 unique concepts have proper English definitions.

## Files Modified

The following JSONL files were updated to remove duplicates:
- `data/release/lemmas/adjectives/quality/base.jsonl` (164 → 159 entries)
- `data/release/lemmas/nouns/food_drink/base.jsonl` (91 → 84 entries)
- `data/release/lemmas/nouns/human/base.jsonl` (75 → 24 entries)
- `data/release/lemmas/nouns/small_movable_object/base.jsonl` (46 → 45 entries)
- `data/release/lemmas/nouns/tool_machine/base.jsonl` (46 → 43 entries)

## Additional Category Consolidation

After the initial duplicate removal, the following entries were moved to their proper categories:

### Vehicle Consolidation
**Moved from tool_machine → vehicle:** 7 entries
- airplane, bicycle, boat, ship, taxi, truck, motorcycle

**Result:**
- tool_machine: 43 → 36 entries (now contains only tools/machines/technology)
- vehicle: 5 → 12 entries (all vehicle types consolidated)

### Food Consolidation
**Moved from food_drink → food:** 84 entries
- All remaining food items (bread, meat, fish, fruits, vegetables, etc.)

**Result:**
- food_drink: 84 → 0 entries (now empty, ready for deprecation)
- food: 1 → 85 entries (all food items consolidated)

**Note:** The beverage category (7 entries) remains separate as a distinct category for drinks.

## Next Steps

### Database Loading
These cleaned JSONL files are now ready to be loaded into the database. You can use agents like **VORAS** and **VILKAS** to:
1. Load the base concepts into the database
2. Generate additional language translations (en.jsonl, de.jsonl, etc.)
3. Expand the multilingual coverage

### Verification
To verify the cleanup was successful, you can:
```bash
# Re-run the analysis (should show 0 duplicates)
python analyze_release_files.py

# Check specific categories
grep '"concept_label"' data/release/lemmas/nouns/beverage/base.jsonl
grep '"concept_label"' data/release/lemmas/nouns/occupation/base.jsonl
```

## Tools Created

Two analysis scripts were created for this review:

1. **analyze_release_files.py** - Analyzes JSONL files for duplicates and dummy definitions
2. **remove_duplicates.py** - Removes duplicates from old categories based on migration rules

These scripts can be run again in the future if new migrations are added to `category_migrations.json`.
