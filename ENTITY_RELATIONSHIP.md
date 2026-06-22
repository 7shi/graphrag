# Entity / Relationship Extraction: Migration to Structured Output

This note records why and how graph extraction was changed from a delimited
text format to LLM structured output (JSON).

## Background: the delimiter problem

The original extraction prompt asked the model to emit entities and
relationships as delimited tuples:

```
("entity"<|><name><|><type><|><description>)
##
("relationship"<|><source><|><target><|><description><|><strength>)
<|COMPLETE|>
```

The parser split each record on the tuple delimiter `<|>` and **silently
dropped** any record whose field count was too low (entities needing ≥4
fields, relationships ≥5). No error, no log, no `on_error` callback fired.

Local models (notably gemma) cannot reproduce `<|>` reliably. They collapse it
to `>` or `|`, most often on the relationship strength delimiter. Because the
collapse breaks the field count, the affected records were discarded. In the
non-prompt-tuned `tagore` experiment this meant only **10% of relationships
survived** (entities fared better at ~93%).

## Earlier workaround (now removed)

As an interim experiment on this branch (not part of upstream graphrag), the
tuple delimiter was made configurable through a `GRAPHRAG_TUPLE_DELIMITER`
environment variable. Setting it to a single
character the model could reproduce faithfully — e.g. the full-width `｜`
(U+FF5C) — eliminated the collapse. The `tagore4` experiment confirmed this:
relationship survival rose from 10% to ~75% and entities to 100%, with 0%
delimiter corruption.

That approach worked but was still a workaround: it depended on choosing a
delimiter the model happened to handle, and the residual ~24% relationship loss
was the model simply omitting the strength field. The delimiter concept itself
remained a source of fragility.

## Current solution: structured output

Extraction now uses litellm structured output (`response_format` = a Pydantic
model), the same mechanism already used by the community report extractor. The
delimiter concept is gone entirely, so neither `<|>` collapse nor strength-field
pasting can corrupt the output.

### Schema

A single response carries both lists (`response_format` applies to the whole
response, so entities and relationships share one JSON object):

```python
class EntityModel(BaseModel):
    name: str
    type: str
    description: str

class RelationshipModel(BaseModel):
    source: str
    target: str
    description: str
    strength: float = 1.0   # defaulted so an omitted score does not fail validation

class GraphExtractionResult(BaseModel):
    entities: list[EntityModel] = []
    relationships: list[RelationshipModel] = []
```

`strength` defaults to `1.0`, matching the old parser's fallback weight, so a
model that omits the score no longer drops the whole relationship.

### Flow

- `_process_document` calls `completion_async(..., response_format=GraphExtractionResult)`
  and reads `response.formatted_response`.
- **Gleaning is preserved.** Each gleaning round is also a structured call, and
  its `entities` / `relationships` lists are merged (extended) into the running
  result. The Y/N continuation check (`LOOP_PROMPT`) stays a plain,
  non-structured call.
- `_process_result` converts the structured result into the entity /
  relationship DataFrames: `clean_str` + uppercasing of names/types/endpoints,
  with simple per-round de-duplication on `(title, type)` and
  `(source, target)`. Downstream `_merge_entities` / `_merge_relationships`
  still aggregate descriptions and sum weights as before.

### Prompt

`GRAPH_EXTRACTION_PROMPT` was rewritten to instruct JSON output and the
few-shot examples were re-expressed as JSON. Literal `{` / `}` in the examples
are escaped as `{{` / `}}` because the prompt is rendered with `str.format`.
The `<|>` / `##` / `<|COMPLETE|>` instructions were removed.

## Files changed

- `packages/graphrag/graphrag/prompts/index/extract_graph.py` — prompt rewritten to JSON.
- `packages/graphrag/graphrag/index/operations/extract_graph/graph_extractor.py` —
  removed the env var and tuple parsing; added the Pydantic schema, structured
  calls, gleaning merge, and structured-to-DataFrame conversion.
- `tests/unit/.../graph_intelligence/test_gi_entity_extraction.py` — mock
  response converted to JSON.
- `packages/graphrag/graphrag/api/prompt_tune.py`,
  `prompt_tune/prompt/entity_relationship.py`,
  `prompt_tune/template/extract_graph.py`,
  `prompt_tune/generator/entity_relationship.py`,
  `prompt_tune/generator/extract_graph_prompt.py` — prompt tuning now emits the
  structured-output JSON schema (see "Prompt tuning" below).

The caller `extract_graph.py` is unchanged (the public API is the same).

## Prompt tuning

`graphrag prompt-tune` now generates an extraction prompt that matches the
structured-output schema, so a tuned `extract_graph.txt` is consistent with what
the index engine actually expects:

- `api/prompt_tune.py` calls `generate_entity_relationship_examples` and
  `create_extract_graph_prompt` with `json_mode=True` (previously `False`).
- The JSON prompt templates were rewritten to emit a single object
  `{"entities": [{name, type, description}], "relationships": [{source, target, description, strength}]}`
  — matching `GraphExtractionResult`. Relationship fields were renamed from the
  old `relationship` / `relationship_strength` to `description` / `strength`.
- Both the typed and untyped (`--no-discover-entity-types`) paths have JSON
  variants (`*_JSON_PROMPT` in `prompt_tune/prompt/entity_relationship.py` and
  `prompt_tune/template/extract_graph.py`).

The legacy `<|>` tuple templates remain in the prompt-tune modules but are no
longer used by the default flow.

## Out of scope

- Claim/covariate extraction (`extract_covariates`) still uses `<|>`
  (unrelated).
- Per-experiment `prompts/extract_graph.txt` files in the old tuple format. New
  experiments should use the JSON prompt; `response_format` constrains the
  output to JSON regardless, but a matching prompt avoids conflicting
  instructions.

## Verification

- `uv run pytest tests/unit/indexing/verbs/entities/extraction/strategies/graph_intelligence/test_gi_entity_extraction.py` → 3 passed.
- `uv run python -c "import graphrag.index.operations.extract_graph.graph_extractor"` and
  `GRAPH_EXTRACTION_PROMPT.format(...)` succeed (escaping correct).
- `grep -rn GRAPHRAG_TUPLE_DELIMITER packages/` → 0 matches (env var fully removed).
