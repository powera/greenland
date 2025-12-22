# Noun POS Subtype Review

## Current Issues

### 1. **Critical Mismatch: Schema vs AI Prompt**

There's a **significant discrepancy** between the enum definitions (`src/wordfreq/storage/models/enums.py`) and the AI classification prompt (`src/wordfreq/prompts/pos_subtype/noun.txt`).

**In Schema but NOT in AI Prompt:**
- `FOOD_DRINK`
- `BUILDING_STRUCTURE`
- `TOOL_MACHINE`
- `MATERIAL_SUBSTANCE`
- `DISEASE_CONDITION`
- `CLOTHING_ACCESSORY`
- `ARTWORK_ARTIFACT`
- `PATH_INFRASTRUCTURE`
- `CHEMICAL_COMPOUND`
- `MEDICATION_REMEDY`
- `CONCEPT_IDEA`
- `SYMBOLIC_ELEMENT`
- `QUALITY_ATTRIBUTE`
- `MENTAL_CONSTRUCT`
- `KNOWLEDGE_DOMAIN`
- `QUANTITATIVE_CONCEPT`
- `EMOTION_FEELING`

**In AI Prompt but NOT in Schema:**
- `demonym` (English, Texan, Muscovite)
- `abstract_concept`
- `emotion_thought`
- `event`
- `numbers_ordinals`
- `measurements`
- `gerunds`
- `nominalized_words`
- `abbreviation`

**⚠️ This mismatch means the AI may be classifying nouns into categories that don't exist in the database!**

---

## 2. Categories That Should Be Split

### A. **FOOD_DRINK** → Split into separate categories
**Current:** Single category for all consumables
**Problem:** Food and beverages are semantically distinct
**Proposed Split:**
- `FOOD` - solid consumables (bread, apple, rice, meat, cheese)
- `BEVERAGE` or `DRINK` - liquids (water, coffee, tea, juice, wine)

**Examples of ambiguity:**
- "milk" - beverage or food?
- "soup" - food or beverage?
- "ice cream" - food (but liquid-ish)

**Recommendation:** Keep them combined OR use `BEVERAGE` if split (more formal)

---

### B. **PLANT** → Split by plant type/part
**Current:** All plants and plant parts combined
**Problem:** "oak" (tree species) vs "leaf" (plant part) are very different
**Proposed Split:**
- `PLANT` - whole living plants (tree, flower, grass, bush, fern, cactus)
- `PLANT_PART` - parts of plants (leaf, root, petal, bark, seed, fruit)

**OR** more granular:
- `TREE` - woody plants (oak, pine, maple, birch)
- `FLOWER` - flowering plants (rose, tulip, daisy)
- `PLANT_OTHER` - other plants (grass, moss, fern, vine)
- `PLANT_PART` - parts (leaf, root, stem, seed)

**Recommendation:** Two-way split is sufficient (PLANT + PLANT_PART)

---

### C. **TOOL_MACHINE** → Split by type and power source
**Current:** All tools, machines, vehicles, electronics
**Problem:** "hammer" vs "car" vs "television" vs "computer" are vastly different
**Proposed Split:**
- `TOOL` - hand tools and implements (hammer, screwdriver, wrench, shovel, scissors)
- `MACHINE` - powered mechanical devices (engine, motor, generator, press)
- `APPLIANCE` - household powered devices (refrigerator, washing machine, oven, microwave)
- `VEHICLE` - transportation (car, truck, bicycle, motorcycle, boat, airplane)
- `ELECTRONICS` - electronic devices (television, computer, phone, radio, camera)

**Overlap Issues:**
- "computer" - machine or electronics?
- "electric drill" - tool or machine?
- "smartphone" - tool or electronics?

**Recommendation:** At minimum, split into:
- `TOOL` - hand-operated implements
- `MACHINE_APPLIANCE` - powered devices
- `VEHICLE` - transportation
- `ELECTRONICS` - computing/communication devices

---

### D. **CLOTHING_ACCESSORY** → Optional split
**Current:** Combined category
**Potential Split:**
- `CLOTHING` - garments worn on body (shirt, pants, dress, coat)
- `ACCESSORY` - supplementary items (hat, belt, jewelry, watch, glasses)

**Recommendation:** Probably fine as-is unless you need granularity

---

## 3. Missing Categories

### A. **FURNITURE** ⭐ HIGH PRIORITY
**Current Issue:** No home for "table" (桌子), "chair", "desk", "sofa", "bed"
**Current Miscategorization:** These might go into `SMALL_MOVABLE_OBJECT` but that's for portable items (pen, book, phone)

**Proposed:** Add `FURNITURE` category
- Examples: table, chair, desk, sofa, bed, shelf, cabinet, dresser, bench, stool

**GUID Prefix Needed:** Assign unused prefix like `N38`

---

### B. **KITCHENWARE / COOKWARE**
**Current Issue:** No clear category for cooking vessels and utensils
**Might Currently Go To:** `SMALL_MOVABLE_OBJECT` or `TOOL`

**Proposed:** Add `KITCHENWARE` category
- Examples: pot, pan, plate, bowl, cup, fork, knife, spoon, spatula, whisk

**Alternative:** Keep in `SMALL_MOVABLE_OBJECT` if not needed

---

### C. **ROOM / SPACE**
**Current Issue:** Interior spaces have no category
**Might Currently Go To:** `BUILDING_STRUCTURE` (but that's for whole buildings)

**Proposed:** Add `ROOM` or `INTERIOR_SPACE` category
- Examples: bedroom, kitchen, bathroom, living room, hallway, office, garage

**Alternative:** Extend `BUILDING_STRUCTURE` definition to include rooms

---

### D. **VEHICLE** (if splitting TOOL_MACHINE)
See section 2.C above - vehicles should be separate from general tools/machines

---

### E. **WEAPON** (Optional)
**Current Issue:** No category for weapons
**Might Currently Go To:** `TOOL`

**Examples:** sword, gun, rifle, bow, knife (when used as weapon)

**Recommendation:** Only add if relevant to your word lists

---

## 4. Categories That Are Too Broad or Unclear

### A. **SMALL_MOVABLE_OBJECT**
**Current Definition:** "Portable items (pen, book, phone)"
**Issues:**
- How small is "small"?
- Is a suitcase small? A bicycle?
- Overlaps with TOOL (hammer is small and movable)
- Overlaps with ELECTRONICS (phone)

**Recommendation:**
Rename to `EVERYDAY_OBJECT` or `PORTABLE_ITEM` and clarify:
- Objects that are easily carried/moved by one person
- Not clothing, tools, or furniture
- General household/office items
- Examples: pen, book, bag, wallet, key, bottle

---

### B. **NATURAL_FEATURE**
**Current:** "Natural elements (mountain, river, cloud)"
**Potential Issue:** Very broad - includes landforms, water bodies, weather phenomena

**Possible Refinement:**
- `LANDFORM` - mountain, hill, valley, cave
- `WATER_BODY` - river, lake, ocean, stream
- `WEATHER_PHENOMENON` - cloud, rain, snow, wind

**Recommendation:** Probably fine as-is unless granularity needed

---

### C. **CONCEPT_IDEA** vs AI Prompt's "abstract_concept"
These seem to overlap - need to align terminology

---

## 5. Potentially Useful Additional Categories

### **CONTAINER**
- Items whose primary function is to hold things
- Examples: box, jar, bottle, bucket, basket, bag
- Could be distinct from SMALL_MOVABLE_OBJECT

### **DOCUMENT**
- Written/printed materials
- Examples: letter, document, certificate, passport, ticket, receipt
- Currently might go to SMALL_MOVABLE_OBJECT

### **BOOK_PUBLICATION**
- Specifically for books, magazines, newspapers
- More specific than DOCUMENT

### **GAME_TOY**
- Recreational items
- Examples: ball, doll, puzzle, game, toy

### **MUSICAL_INSTRUMENT**
- Examples: piano, guitar, drum, flute
- Could be under TOOL currently

---

## 6. Recommended Action Plan

### Phase 1: Critical Fixes ⚠️
1. **Fix schema/AI prompt mismatch** - Align the two files
2. **Add FURNITURE category** - Solves the "table" problem
3. **Split TOOL_MACHINE** minimally into:
   - TOOL
   - VEHICLE
   - MACHINE_DEVICE (for computers, televisions, appliances)

### Phase 2: Important Improvements
4. **Split PLANT** into PLANT + PLANT_PART
5. **Consider splitting FOOD_DRINK** into FOOD + BEVERAGE
6. **Clarify SMALL_MOVABLE_OBJECT** definition

### Phase 3: Optional Enhancements
7. Add KITCHENWARE if needed
8. Add ROOM if needed
9. Add CONTAINER if needed
10. Add specialized categories (MUSICAL_INSTRUMENT, GAME_TOY, etc.)

---

## 7. Proposed New Taxonomy (Minimal Changes)

**Add These Categories:**
- `FURNITURE` (N38) - table, chair, desk, sofa, bed
- `VEHICLE` (N39) - car, truck, bicycle, boat, airplane
- `PLANT_PART` (N40) - leaf, root, seed, petal, fruit
- `ELECTRONICS` (N41) - television, computer, phone, radio

**Split These Categories:**
- `FOOD` (N42) - solid consumables
- `BEVERAGE` (N43) - liquid consumables
- [Remove old FOOD_DRINK]

**Rename These:**
- `TOOL_MACHINE` → `TOOL` (hand tools only)
- `PLANT` → `PLANT` (keep, but now excludes parts)
- `SMALL_MOVABLE_OBJECT` → `PORTABLE_OBJECT` (clearer name)

**Modify Definitions:**
- `BUILDING_STRUCTURE` - Include rooms and interior spaces

---

## 8. Migration Considerations

- Need to update GUID prefix mappings
- Need to update AI prompts
- May need to reclassify existing entries
- Update barsukas web interface dropdown
- Update any hardcoded references in pattern generation
- Update display name rendering functions

---

## Summary Table: Problem Examples

| Word | Current Category | Problem | Suggested Category |
|------|-----------------|---------|-------------------|
| table (桌子) | ❌ None/unclear | No furniture category | FURNITURE |
| chair | SMALL_MOVABLE_OBJECT? | Too large for "small" | FURNITURE |
| car | TOOL_MACHINE | Not a tool | VEHICLE |
| television | TOOL_MACHINE | Not a tool/machine | ELECTRONICS |
| oak | PLANT | Is a specific tree type | PLANT (keep) or TREE |
| leaf | PLANT | Is a plant part | PLANT_PART |
| coffee | FOOD_DRINK | Is a beverage | BEVERAGE |
| bread | FOOD_DRINK | Is food | FOOD |
| hammer | TOOL_MACHINE | Is a tool, not machine | TOOL |
| refrigerator | TOOL_MACHINE | Is an appliance | APPLIANCE or ELECTRONICS |

---

## Files That Need Updates

1. `/home/user/greenland/src/wordfreq/storage/models/enums.py` - Add new enum values
2. `/home/user/greenland/src/wordfreq/storage/models/guid_prefixes.py` - Add GUID mappings
3. `/home/user/greenland/src/wordfreq/prompts/pos_subtype/noun.txt` - Update AI prompt to match schema
4. `/home/user/greenland/src/wordfreq/trakaido/json_to_database.py` - Update category mappings
5. `/home/user/greenland/src/wordfreq/trakaido/utils/text_rendering.py` - Add display names
6. Database migration script - Reclassify existing entries if needed
