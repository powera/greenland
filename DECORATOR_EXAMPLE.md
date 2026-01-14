# Workqueue Handler Decorator Examples

This shows two approaches for using the new decorators in `agents.common.wq_tools`:

## Approach 1: `@lemma_handler` (Simple)

Use this when you still want to write handler logic, but want lemma lookup and commit automated.

**Before:**
```python
def handle_add_missing_translations(session, payload: Dict) -> str:
    lemma_id = payload["lemma_id"]
    lemma = get_lemma_or_raise(session, lemma_id)

    added_count, errors = generate_missing_translations_for_lemma(session, lemma)

    if errors and added_count == 0:
        raise RuntimeError("; ".join(errors))

    session.commit()

    if added_count == 0:
        return "No missing translations to generate"
    return f"Added {added_count} translation(s)"
```

**After:**
```python
from agents.common.wq_tools import lemma_handler

@lemma_handler
def handle_add_missing_translations(session, lemma, payload):
    added_count, errors = generate_missing_translations_for_lemma(session, lemma)

    if errors and added_count == 0:
        raise RuntimeError("; ".join(errors))

    if added_count == 0:
        return "No missing translations to generate"
    return f"Added {added_count} translation(s)"
```

**Eliminated:** 3 lines (lemma_id extraction, get_lemma_or_raise, session.commit)

---

## Approach 2: `@workqueue_handler` (Auto-generate)

Use this to auto-generate the entire handler from your business logic function.

**Current structure:**
```python
# Business logic (called by CLI and workqueue)
def generate_missing_translations_for_lemma(
    session,
    lemma: Lemma,
    config: Optional[DataSourceConfig] = None,
    source: Optional[str] = None,
) -> Tuple[int, List[str]]:
    if config is None:
        config = build_default_config()
    # ... business logic ...
    return added_count, errors

# Separate handler function
def handle_add_missing_translations(session, payload: Dict) -> str:
    lemma_id = payload["lemma_id"]
    lemma = get_lemma_or_raise(session, lemma_id)

    added_count, errors = generate_missing_translations_for_lemma(session, lemma)

    if errors and added_count == 0:
        raise RuntimeError("; ".join(errors))

    session.commit()

    if added_count == 0:
        return "No missing translations to generate"
    return f"Added {added_count} translation(s)"
```

**With decorator:**
```python
from agents.common.wq_tools import workqueue_handler

# Business logic - unchanged, still called by CLI agents
@workqueue_handler(
    "add_missing_translations",
    result_formatter=lambda result: (
        f"Added {result[0]} translation(s)"
        if result[0] > 0
        else "No missing translations to generate"
    ),
)
def generate_missing_translations_for_lemma(
    session,
    lemma: Lemma,
    config: Optional[DataSourceConfig] = None,
    source: Optional[str] = None,
) -> Tuple[int, List[str]]:
    if config is None:
        config = build_default_config()
    # ... business logic unchanged ...
    return added_count, errors

# Handler auto-generated! Access it via:
handle_add_missing_translations = generate_missing_translations_for_lemma._handler
```

**Eliminated:** Entire handler function (~15 lines) including error handling logic

---

## More Complex Example: Vilkas (with payload defaults)

```python
from agents.common.wq_tools import workqueue_handler

@workqueue_handler(
    "generate_forms",
    payload_defaults={"lang_code": "lt"},
    result_formatter=lambda result: (
        f"Generated {result[1]} forms" if result[0] else f"Error: {result[1]}"
    ),
)
def generate_forms_for_lemma(
    session,
    lemma: Lemma,
    lang_code: str = "lt",
    config: Optional[DataSourceConfig] = None,
    client: Optional[LinguisticClient] = None,
) -> Tuple[bool, Optional[str]]:
    # Business logic unchanged
    if config is None:
        config = build_default_config()
    # ...
    return success, error_message

# Auto-generates handle_generate_forms(session, payload)
handle_generate_forms = generate_forms_for_lemma._handler
```

---

## Registration in task_handlers.py

For the auto-generated handlers, register them like this:

```python
from barsukas.voras.wq_worker import generate_missing_translations_for_lemma
from barsukas.vilkas.wq_worker import generate_forms_for_lemma

TASK_HANDLERS = {
    "add_missing_translations": generate_missing_translations_for_lemma._handler,
    "generate_forms": generate_forms_for_lemma._handler,
    # ... or keep existing explicit handlers ...
}
```

---

## Limitations & When NOT to Use

The `@workqueue_handler` decorator works best when:
- ✅ Your business logic takes (session, lemma, **simple_kwargs)
- ✅ Return value can be formatted with a simple function
- ✅ No complex validation logic needed

Don't use it when:
- ❌ Handler needs to work with non-Lemma models (like Sentence in zvirblis)
- ❌ Complex pre-processing or validation logic
- ❌ Handler logic is significantly different from business logic
- ❌ Error handling is complex (multiple error paths)

For those cases, stick with explicit handlers or use `@lemma_handler`.

---

## Recommendation

Start with **`@lemma_handler`** for all handlers to eliminate boilerplate, then optionally migrate specific handlers to **`@workqueue_handler`** where the pattern fits cleanly.
