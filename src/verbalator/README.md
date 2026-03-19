# Verbalator

Verbalator is a multilingual text analysis tool that uses LLMs to perform
structured linguistic analysis. It provides two interfaces: **actions** that
return structured JSON via a pluggable action system, and **free-form queries**
that generate prose responses with configurable style controls.

It runs as part of the benchmarks web server (Flask) and is accessible at
`/verbalator/`.


## Architecture

```
src/verbalator/              Core action framework
  action_base.py             ActionBase ABC — defines the interface every action must implement
  action_registry.py         Global registry; actions self-register at import time
  actions/                   One module per action (each calls register() at the bottom)

src/benchmarks/server/routes/verbalator.py   Flask blueprint — /verbalator/* routes
src/benchmarks/verbalator/                   Free-form query support (prompts, style builder, samples)
src/benchmarks/server/templates/verbalator/  Jinja2 templates (index + result partials)
src/benchmarks/server/static/js/verbalator.js   Frontend form handling and result rendering
src/benchmarks/server/static/css/verbalator.css  Styles

prompts/verbalator/{action_name}/            Prompt files loaded by util.prompt_loader
  context.txt                                System/context prompt
  prompt.txt                                 User prompt template (with {placeholders})
```


## Actions

Each action is a Python class that extends `ActionBase` and implements three
methods:

| Method | Purpose |
|--------|---------|
| `build_prompt(text, context?, target_language?, session?)` | Returns `(system_context, user_prompt)` for the LLM call |
| `build_schema(**kwargs)` | Returns a JSON Schema dict describing the expected structured output |
| `get_template_name()` | Returns the Jinja2 template path for rendering results |

Actions also declare metadata used by the UI:

| Field | Example | Purpose |
|-------|---------|---------|
| `name` | `"metadata"` | Machine identifier, used in API calls |
| `display_name` | `"Text Metadata"` | Human-readable label |
| `description` | `"Analyze language, register, ..."` | Shown in the UI |
| `color_group` | `"blue"` or `"green"` | Groups actions visually in the UI |
| `needs_context` | `True` / `False` | Shows the "context" input field |
| `needs_target_language` | `True` / `False` | Shows the "target language" selector |


### Current actions

| Action | Color | Description | Special inputs |
|--------|-------|-------------|----------------|
| **Sentence Decomposition** (`decomposition`) | green | Word-by-word morphological breakdown with lemma matching from the DB | `target_language`, DB session |
| **Text Metadata** (`metadata`) | blue | Detect language, register, formality, genre, and key topics | none |
| **Time Analysis** (`time_analysis`) | blue | Estimate when text was written or when described events occurred | none |
| **Response-To** (`response_to`) | blue | Analyze whether text is responding to given context | `context` |


## Adding a new action

1. **Create the action module** at `src/verbalator/actions/your_action.py`:

```python
"""Short description of your action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "your_action"


class YourAction(ActionBase):
    name = "your_action"
    display_name = "Your Action"
    description = "One-line description for the UI"
    color_group = "blue"          # "blue" or "green"
    needs_context = False         # set True if you need the context input
    needs_target_language = False  # set True if you need a language selector

    def build_prompt(
        self,
        text: str,
        context: Optional[str] = None,
        target_language: Optional[str] = None,
        session: Optional[Any] = None,
    ) -> Tuple[str, str]:
        system_context = util.prompt_loader.get_context(_PROMPT_CATEGORY, _PROMPT_TYPE)
        prompt = util.prompt_loader.get_prompt(_PROMPT_CATEGORY, _PROMPT_TYPE).format(
            text=text,
        )
        return system_context, prompt

    def build_schema(self, **kwargs: Any) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                # Define your output fields here
                "example_field": {
                    "type": "string",
                    "description": "What this field contains",
                },
            },
            "required": ["example_field"],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/your_action.html"


register(YourAction())
```

2. **Create prompt files** in `prompts/verbalator/your_action/`:
   - `context.txt` — system prompt (role, constraints, output format guidance)
   - `prompt.txt` — user prompt template with `{placeholders}` matching the
     arguments passed to `.format()` in `build_prompt()`

3. **Register the import** in `src/verbalator/actions/__init__.py`:

```python
import verbalator.actions.your_action  # noqa: F401
```

4. **Add a frontend renderer** in `src/benchmarks/server/static/js/verbalator.js`.
   The JS file contains a `renderActionResult(actionName, result)` function with
   a switch on `actionName` — add a case for `"your_action"` that returns HTML
   for the structured result.

5. **Test it**: start the server and select your action in the Actions tab at
   `/verbalator/`.


## Free-form queries

The free-form query tab sends text plus a predefined prompt key (from
`benchmarks/verbalator/common.py`) to the LLM as unstructured prose. Style
controls (verbosity, reading level, topic preferences) are layered on via
`benchmarks/verbalator/prompt_builder.py`.

Available prompts: `style`, `audience`, `rephrase`, `register`, `difficulty`,
`history`, `science`, `culture`, `medical`, `legal`, `violence`, `drugs`,
`religion`, `pii`, `hijack`, `sex`, `nuclear`.


## API

### `POST /verbalator/action`

Run a structured action.

```json
{
  "action_name": "metadata",
  "text": "Text to analyze",
  "model": "gpt-5-mini",
  "context": "Optional surrounding context",
  "target_language": "es"
}
```

Response:
```json
{
  "action": "metadata",
  "result": { ... },
  "usage": { "prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168 },
  "template": "verbalator/results/metadata.html"
}
```

### `POST /verbalator/query`

Run a free-form query with style controls.

```json
{
  "prompt": "style",
  "entry": "Text to analyze",
  "model": "gpt-5-mini",
  "verbosity": 2,
  "reading_level": 2,
  "sports": 0,
  "politics": -1
}
```

Response:
```json
{
  "response": "The text uses a formal, ...",
  "usage": { ... },
  "reading_level": 8.2
}
```


## Local model queue

When a local model (Ollama, LMStudio, etc.) is selected, Verbalator checks
whether the model slot is available via the benchmark worker's
`touch_interactive_local_job()`. If a benchmark run is in progress, the request
returns HTTP 409.
