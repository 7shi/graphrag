# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""Graph extraction helpers that return tabular data."""

import logging
import traceback
from typing import TYPE_CHECKING, Any

import pandas as pd
from graphrag_llm.utils import (
    CompletionMessagesBuilder,
)
from pydantic import BaseModel, Field

from graphrag.index.typing.error_handler import ErrorHandlerFn
from graphrag.index.utils.string import clean_str
from graphrag.prompts.index.extract_graph import (
    CONTINUE_PROMPT,
    LOOP_PROMPT,
)

if TYPE_CHECKING:
    from graphrag_llm.completion import LLMCompletion
    from graphrag_llm.types import LLMCompletionResponse

INPUT_TEXT_KEY = "input_text"
ENTITY_TYPES_KEY = "entity_types"

logger = logging.getLogger(__name__)


class EntityModel(BaseModel):
    """A single extracted entity."""

    name: str = Field(description="Name of the entity, capitalized")
    type: str = Field(description="One of the provided entity types")
    description: str = Field(
        description="Comprehensive description of the entity's attributes and activities"
    )


class RelationshipModel(BaseModel):
    """A single extracted relationship between two entities."""

    source: str = Field(description="Name of the source entity")
    target: str = Field(description="Name of the target entity")
    description: str = Field(
        description="Explanation of why the source and target entities are related"
    )
    # Defaulted so a model that omits the score does not fail schema validation;
    # mirrors the previous parser's fallback weight of 1.0.
    strength: float = Field(
        default=1.0, description="Numeric score for the relationship strength"
    )


class GraphExtractionResult(BaseModel):
    """The structured response shape for a single extraction call."""

    entities: list[EntityModel] = Field(default_factory=list)
    relationships: list[RelationshipModel] = Field(default_factory=list)


class GraphExtractor:
    """Unipartite graph extractor class definition."""

    _model: "LLMCompletion"
    _extraction_prompt: str
    _max_gleanings: int
    _on_error: ErrorHandlerFn

    def __init__(
        self,
        model: "LLMCompletion",
        prompt: str,
        max_gleanings: int,
        on_error: ErrorHandlerFn | None = None,
    ):
        """Init method definition."""
        self._model = model
        self._extraction_prompt = prompt
        self._max_gleanings = max_gleanings
        self._on_error = on_error or (lambda _e, _s, _d: None)

    async def __call__(
        self, text: str, entity_types: list[str], source_id: str
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Extract entities and relationships from the supplied text."""
        try:
            # Invoke the entity extraction
            result = await self._process_document(text, entity_types)
        except Exception as e:  # pragma: no cover - defensive logging
            logger.exception("error extracting graph")
            self._on_error(
                e,
                traceback.format_exc(),
                {
                    "source_id": source_id,
                    "text": text,
                },
            )
            return _empty_entities_df(), _empty_relationships_df()

        return self._process_result(result, source_id)

    async def _process_document(
        self, text: str, entity_types: list[str]
    ) -> GraphExtractionResult:
        messages_builder = CompletionMessagesBuilder().add_user_message(
            self._extraction_prompt.format(**{
                INPUT_TEXT_KEY: text,
                ENTITY_TYPES_KEY: ",".join(entity_types),
            })
        )

        response: LLMCompletionResponse = await self._model.completion_async(
            messages=messages_builder.build(),
            response_format=GraphExtractionResult,
        )  # type: ignore
        result: GraphExtractionResult = response.formatted_response  # type: ignore
        messages_builder.add_assistant_message(response.content)

        # if gleanings are specified, enter a loop to extract more entities
        # there are two exit criteria: (a) we hit the configured max, (b) the model says there are no more entities
        if self._max_gleanings > 0:
            for i in range(self._max_gleanings):
                messages_builder.add_user_message(CONTINUE_PROMPT)
                response: LLMCompletionResponse = await self._model.completion_async(
                    messages=messages_builder.build(),
                    response_format=GraphExtractionResult,
                )  # type: ignore
                glean: GraphExtractionResult = response.formatted_response  # type: ignore
                result.entities.extend(glean.entities)
                result.relationships.extend(glean.relationships)
                messages_builder.add_assistant_message(response.content)

                # if this is the final glean, don't bother updating the continuation flag
                if i >= self._max_gleanings - 1:
                    break

                messages_builder.add_user_message(LOOP_PROMPT)
                response: LLMCompletionResponse = await self._model.completion_async(
                    messages=messages_builder.build(),
                )  # type: ignore
                if response.content != "Y":
                    break

        return result

    def _process_result(
        self,
        result: GraphExtractionResult,
        source_id: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Convert the structured result into entity and relationship data frames."""
        entities: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        seen_entities: set[tuple[str, str]] = set()
        seen_relationships: set[tuple[str, str]] = set()

        for entity in result.entities:
            entity_name = clean_str(entity.name.upper())
            entity_type = clean_str(entity.type.upper())
            if not entity_name:
                continue
            key = (entity_name, entity_type)
            if key in seen_entities:
                continue
            seen_entities.add(key)
            entities.append({
                "title": entity_name,
                "type": entity_type,
                "description": clean_str(entity.description),
                "source_id": source_id,
            })

        for relationship in result.relationships:
            source = clean_str(relationship.source.upper())
            target = clean_str(relationship.target.upper())
            if not source or not target:
                continue
            key = (source, target)
            if key in seen_relationships:
                continue
            seen_relationships.add(key)
            relationships.append({
                "source": source,
                "target": target,
                "description": clean_str(relationship.description),
                "source_id": source_id,
                "weight": float(relationship.strength),
            })

        entities_df = pd.DataFrame(entities) if entities else _empty_entities_df()
        relationships_df = (
            pd.DataFrame(relationships) if relationships else _empty_relationships_df()
        )

        return entities_df, relationships_df


def _empty_entities_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["title", "type", "description", "source_id"])


def _empty_relationships_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["source", "target", "weight", "description", "source_id"]
    )
