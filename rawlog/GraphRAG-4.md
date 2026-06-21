# GraphRAG 実行プロセスとソースコード対応関係レポート

* **対象コミットID**: `6d02c2355c3fed4c49007572fbe951d73258a37f`

このドキュメントでは、GraphRAG の各実行プロセス（`prompt-tune`、`index`、`query --method global`、`query --method local`）における実際のソースコードの対応箇所と、LLM に対するコンテキストの組み立て方を investigation し、解説します。

---

## 1. `1-prompt-tune` (自動プロンプトチューニング)

自動プロンプトチューニングは、ユーザーの指定したドメインやテキストデータに合わせて、インデックス作成やクエリ処理用のシステムプロンプトを動的に最適化するフェーズです。

### 1.1 00001.xml（ドメイン特定）

引数のテキスト（`docs`）を連結し、[domain.py](../packages/graphrag/graphrag/prompt_tune/prompt/domain.py) 内に定義されている `GENERATE_DOMAIN_PROMPT` の `{input_text}` に埋め込んで LLM を呼び出します。これにより、テキストがどの分野（例: 文学、医療科学、社会科学）に属するドメインかを特定させます。

```python:packages/graphrag/graphrag/prompt_tune/generator/domain.py:15-34
async def generate_domain(model: "LLMCompletion", docs: str | list[str]) -> str:
    """Generate an LLM persona to use for GraphRAG prompts.

    Parameters
    ----------
    - model (LLMCompletion): The LLM to use for generation
    - docs (str | list[str]): The domain to generate a persona for

    Returns
    -------
    - str: The generated domain prompt response.
    """
    docs_str = " ".join(docs) if isinstance(docs, list) else docs
    domain_prompt = GENERATE_DOMAIN_PROMPT.format(input_text=docs_str)

    response: LLMCompletionResponse = await model.completion_async(
        messages=domain_prompt
    )  # type: ignore

    return response.content
```

### 1.2 00002.xml（専門家ペルソナの定義）

前ステップで特定したドメインを埋め込んだタスク（デフォルトは `{domain}` 領域における関係マッピングタスク）を構築し、[persona.py](../packages/graphrag/graphrag/prompt_tune/prompt/persona.py) 内の `GENERATE_PERSONA_PROMPT` の `{sample_task}` に埋め込みます。これにより、そのドメインを専門的に分析するための AI の「ペルソナ（システムロール）」を生成させます。

```python:packages/graphrag/graphrag/prompt_tune/generator/persona.py:16-34
async def generate_persona(
    model: "LLMCompletion", domain: str, task: str = DEFAULT_TASK
) -> str:
    """Generate an LLM persona to use for GraphRAG prompts.

    Parameters
    ----------
    - model (LLMCompletion): The LLM to use for generation
    - domain (str): The domain to generate a persona for
    - task (str): The task to generate a persona for. Default is DEFAULT_TASK
    """
    formatted_task = task.format(domain=domain)
    persona_prompt = GENERATE_PERSONA_PROMPT.format(sample_task=formatted_task)

    response: LLMCompletionResponse = await model.completion_async(
        messages=persona_prompt
    )  # type: ignore

    return response.content
```

### 1.3 00003.xml（評価基準の定義）

`domain`、`persona`、および対象の `input_text` を [community_report_rating.py](../packages/graphrag/graphrag/prompt_tune/prompt/community_report_rating.py) の `GENERATE_REPORT_RATING_PROMPT` にフォーマットして LLM に送信します。このプロンプトには Few-Shot 例が含まれており、LLM に 0〜10 のスケールで重要度を評価するための具体的な「評価基準（Importance Criteria）」を生成させます。

```python:packages/graphrag/graphrag/prompt_tune/generator/community_report_rating.py:16-41
async def generate_community_report_rating(
    model: "LLMCompletion", domain: str, persona: str, docs: str | list[str]
) -> str:
    """Generate an LLM persona to use for GraphRAG prompts.

    Parameters
    ----------
    - model (LLMCompletion): The LLM to use for generation
    - domain (str): The domain to generate a rating for
    - persona (str): The persona to generate a rating for for
    - docs (str | list[str]): Documents used to contextualize the rating

    Returns
    -------
    - str: The generated rating description prompt response.
    """
    docs_str = " ".join(docs) if isinstance(docs, list) else docs
    domain_prompt = GENERATE_REPORT_RATING_PROMPT.format(
        domain=domain, persona=persona, input_text=docs_str
    )

    response: LLMCompletionResponse = await model.completion_async(
        messages=domain_prompt
    )  # type: ignore

    return response.content
```

### 1.4 00004.xml（エンティティ種別の抽出） ※JSON出力

生成された専門家 `persona` をシステムプロンプトに設定し、`ENTITY_TYPE_GENERATION_JSON_PROMPT`（[entity_types.py](../packages/graphrag/graphrag/prompt_tune/prompt/entity_types.py) に定義）をユーザープロンプトとして設定します。Pydantic モデルの `EntityTypesResponse`（`entity_types: list[str]`）を `response_format` として指定し、構造化された JSON 形式で抽出対象のエンティティ種別（例: person, location など）を決定させます。

```python:packages/graphrag/graphrag/prompt_tune/generator/entity_types.py:30-74
async def generate_entity_types(
    model: "LLMCompletion",
    domain: str,
    persona: str,
    docs: str | list[str],
    task: str = DEFAULT_TASK,
    json_mode: bool = False,
) -> str | list[str]:
    """
    Generate entity type categories from a given set of (small) documents.
    ...
    """
    formatted_task = task.format(domain=domain)

    docs_str = "\n".join(docs) if isinstance(docs, list) else docs

    entity_types_prompt = (
        ENTITY_TYPE_GENERATION_JSON_PROMPT
        if json_mode
        else ENTITY_TYPE_GENERATION_PROMPT
    ).format(task=formatted_task, input_text=docs_str)

    messages = (
        CompletionMessagesBuilder()
        .add_system_message(persona)
        .add_user_message(entity_types_prompt)
        .build()
    )

    if json_mode:
        response: LLMCompletionResponse[
            EntityTypesResponse
        ] = await model.completion_async(
            messages=messages,
            response_format=EntityTypesResponse,
        )  # type: ignore
        parsed_model = response.formatted_response
        return parsed_model.entity_types if parsed_model else []
    ...
```

### 1.5 00005.xml 〜 00009.xml（エンティティ・関係性のFew-Shot抽出）

システムメッセージに `persona` を設定します。ドキュメントリストから最大5つのバッチに分割し、それぞれに対してエンティティ種別、ドキュメント、出力言語（例: "Japanese"）を埋め込んだ `ENTITY_RELATIONSHIPS_GENERATION_PROMPT`（[entity_relationship.py](../packages/graphrag/graphrag/prompt_tune/prompt/entity_relationship.py) に定義）をユーザーメッセージとして渡します。これらを `asyncio.gather` で並列に呼び出し、Few-Shot 用の抽出サンプルデータ（日本語）を複数生成します。

```python:packages/graphrag/graphrag/prompt_tune/generator/entity_relationship.py:26-78
async def generate_entity_relationship_examples(
    model: "LLMCompletion",
    persona: str,
    entity_types: str | list[str] | None,
    docs: str | list[str],
    language: str,
    json_mode: bool = False,
) -> list[str]:
    """Generate a list of entity/relationships examples for use in generating an entity configuration.
    ...
    """
    docs_list = [docs] if isinstance(docs, str) else docs

    msg_builder = CompletionMessagesBuilder().add_system_message(persona)

    if entity_types:
        entity_types_str = (
            entity_types
            if isinstance(entity_types, str)
            else ", ".join(map(str, entity_types))
        )

        messages = [
            (
                ENTITY_RELATIONSHIPS_GENERATION_JSON_PROMPT
                if json_mode
                else ENTITY_RELATIONSHIPS_GENERATION_PROMPT
            ).format(entity_types=entity_types_str, input_text=doc, language=language)
            for doc in docs_list
        ]
    ...
    tasks = [
        model.completion_async(
            messages=msg_builder.add_user_message(message).build(),
            response_format_json_object=json_mode,
        )
        for message in messages
    ]

    responses: list[LLMCompletionResponse] = await asyncio.gather(*tasks)  # type: ignore

    return [response.content for response in responses]
```

### 1.6 00010.xml（最終役割プロンプトの生成）

`domain`、`persona`、および `docs` を [community_reporter_role.py](../packages/graphrag/graphrag/prompt_tune/prompt/community_reporter_role.py) の `GENERATE_COMMUNITY_REPORTER_ROLE_PROMPT` に埋め込み、インデックス作成時にコミュニティ要約レポートの作成（ステップ 2.4）を担当させる「コミュニティ・リポーター」の役割・ペルソナ（例: Literary Structural Analyst）を定義させます。

```python:packages/graphrag/graphrag/prompt_tune/generator/community_reporter_role.py:17-42
async def generate_community_reporter_role(
    model: "LLMCompletion", domain: str, persona: str, docs: str | list[str]
) -> str:
    """Generate an LLM persona to use for GraphRAG prompts.
    ...
    """
    docs_str = " ".join(docs) if isinstance(docs, list) else docs
    domain_prompt = GENERATE_COMMUNITY_REPORTER_ROLE_PROMPT.format(
        domain=domain, persona=persona, input_text=docs_str
    )

    response: LLMCompletionResponse = await model.completion_async(
        messages=domain_prompt
    )  # type: ignore

    return response.content
```

---

## 2. `2-index` (インデックス作成 / ナレッジグラフ構築)

インデックス作成では、小説テキスト全体からエンティティと関係性を抽出し、重複を統合した後にグラフ構造を検出して、コミュニティごとの要約レポートを作成します。

### 2.2 00002.xml 〜 00081.xml（エンティティ・関係性の抽出）

各テキストユニット（`text`）と事前に生成した `entity_types` を埋め込んだ `extraction_prompt`（Prompt Tune フェーズで生成されたプロンプト）を送信します。
1回目の抽出完了後、見落とされたエンティティがないかを回収するため `_max_gleanings` 回（Gleanループ）を上限に `CONTINUE_PROMPT` を追加して LLM を呼び出します。さらに `LOOP_PROMPT` で「まだエンティティが残っているか」を判定し、「Y」以外の返答があるまで抽出ループを回します。

```python:packages/graphrag/graphrag/index/operations/extract_graph/graph_extractor.py:85-122
    async def _process_document(self, text: str, entity_types: list[str]) -> str:
        messages_builder = CompletionMessagesBuilder().add_user_message(
            self._extraction_prompt.format(**{
                INPUT_TEXT_KEY: text,
                ENTITY_TYPES_KEY: ",".join(entity_types),
            })
        )

        response: LLMCompletionResponse = await self._model.completion_async(
            messages=messages_builder.build(),
        )  # type: ignore
        results = response.content
        messages_builder.add_assistant_message(results)

        # if gleanings are specified, enter a loop to extract more entities
        # there are two exit criteria: (a) we hit the configured max, (b) the model says there are no more entities
        if self._max_gleanings > 0:
            for i in range(self._max_gleanings):
                messages_builder.add_user_message(CONTINUE_PROMPT)
                response: LLMCompletionResponse = await self._model.completion_async(
                    messages=messages_builder.build(),
                )  # type: ignore
                response_text = response.content
                messages_builder.add_assistant_message(response_text)
                results += response_text

                # if this is the final glean, don't bother updating the continuation flag
                if i >= self._max_gleanings - 1:
                    break

                messages_builder.add_user_message(LOOP_PROMPT)
                response: LLMCompletionResponse = await self._model.completion_async(
                    messages=messages_builder.build(),
                )  # type: ignore
                if response.content != "Y":
                    break

        return results
```

### 2.3 00082.xml 〜 00223.xml（エンティティの要約・マージと矛盾解消）

異なるチャンクから抽出された同一エンティティの名前（`id`）と、それに対応する説明リスト（`descriptions`）を取得します。
バッファのトークン上限（`_max_input_tokens`）を測定しながら descriptions を収集し、上限に達するかリストを読み終えた段階で `_summarize_descriptions_with_llm` を呼び出します。`_summarization_prompt` 内の `entity_name`、`description_list` を埋めて LLM を呼び出し、名寄せして矛盾がない一貫性のある説明文を生成します。

```python:packages/graphrag/graphrag/index/operations/summarize_descriptions/description_summary_extractor.py:75-134
    async def _summarize_descriptions(
        self, id: str | tuple[str, str], descriptions: list[str]
    ) -> str:
        """Summarize descriptions into a single description."""
        ...
        # Iterate over descriptions, adding all until the max input tokens is reached
        usable_tokens = self._max_input_tokens - self._tokenizer.num_tokens(
            self._summarization_prompt
        )
        descriptions_collected = []
        result = ""

        for i, description in enumerate(descriptions):
            usable_tokens -= self._tokenizer.num_tokens(description)
            descriptions_collected.append(description)

            # If buffer is full, or all descriptions have been added, summarize
            if (usable_tokens < 0 and len(descriptions_collected) > 1) or (
                i == len(descriptions) - 1
            ):
                # Calculate result (final or partial)
                result = await self._summarize_descriptions_with_llm(
                    sorted_id, descriptions_collected
                )
                ...
        return result

    async def _summarize_descriptions_with_llm(
        self, id: str | tuple[str, str] | list[str], descriptions: list[str]
    ):
        """Summarize descriptions using the LLM."""
        response: LLMCompletionResponse = await self._model.completion_async(
            messages=self._summarization_prompt.format(**{
                ENTITY_NAME_KEY: json.dumps(id, ensure_ascii=False),
                DESCRIPTION_LIST_KEY: json.dumps(
                    sorted(descriptions), ensure_ascii=False
                ),
                MAX_LENGTH_KEY: self._max_summary_length,
            }),
        )  # type: ignore
        return response.content
```

### 2.4 00224.xml（構造化コミュニティレポートの生成） ※JSON出力

ネットワーク分析によって決定された特定の「コミュニティ（実体のグループ）」内のエンティティとリレーション情報をテキスト化した `input_text` を取得し、`_extraction_prompt` の各プレースホルダーに埋め込みます。
Pydantic のモデル `CommunityReportResponse`（`title`, `summary`, `findings`, `rating`, `rating_explanation` を定義）を `response_format` として指定して LLM を呼び出すことで、厳密な JSON 構造で要約レポートを出力させます。

```python:packages/graphrag/graphrag/index/operations/summarize_communities/community_reports_extractor.py:74-96
    async def __call__(self, input_text: str):
        """Call method definition."""
        output = None
        try:
            prompt = self._extraction_prompt.format(**{
                INPUT_TEXT_KEY: input_text,
                MAX_LENGTH_KEY: str(self._max_report_length),
            })
            response = await self._model.completion_async(
                messages=prompt,
                response_format=CommunityReportResponse,  # A model is required when using json mode
            )

            output = response.formatted_response  # type: ignore
        except Exception as e:
            logger.exception("error generating community report")
            self._on_error(e, traceback.format_exc(), None)
        ...
```

---

## 3. `3-global` (Global Searchによる全体質問)

グローバル検索は、蓄積されたすべてのコミュニティレポート群を対象とし、Map-Reduce パターンで全体の要約を導き出します。

### 3.1 & 3.2 00001.xml & 00002.xml（要点抽出 Mapステップ） ※JSON出力

コミュニティレポートのサブセット（テーブルデータ `context_data`）を `map_system_prompt` に埋め込んでシステムメッセージに設定し、ユーザーの質問（`query`）をユーザーメッセージとして送信します。
LLM から返却される JSON データを `_parse_search_response` を通してパースし、キーポイントごとの説明（`description`）と重要度スコア（`score`）を抽出した辞書リストに変換して保持します。

```python:packages/graphrag/graphrag/query/structured_search/global_search/search.py:216-263
    async def _map_response_single_batch(
        self,
        context_data: str,
        query: str,
        max_length: int,
        **llm_kwargs,
    ) -> SearchResult:
        """Generate answer for a single chunk of community reports."""
        start_time = time.time()
        search_prompt = ""
        try:
            search_prompt = self.map_system_prompt.format(
                context_data=context_data, max_length=max_length
            )

            messages_builder = (
                CompletionMessagesBuilder()
                .add_system_message(search_prompt)
                .add_user_message(query)
            )

            async with self.semaphore:
                model_response = await self.model.completion_async(
                    messages=messages_builder.build(),
                    response_format_json_object=True,
                    **llm_kwargs,
                )
                search_response = await gather_completion_response_async(model_response)
                ...
```

### 3.3 00003.xml（回答集約 Reduceステップ）

Map ステップで得られた各バッチの要点リスト（`map_responses`）を重要度スコア（`score`）の降順にソートし、トークン制限（`max_data_tokens`）に収まるように重要度の高い要点を切り出して結合し `text_data` を作成します。
この `text_data` を `reduce_system_prompt`（システムプロンプト）の `{report_data}` に埋め込み、ユーザーの質問 `query` を投げて、重複を排しエビデンスを付与した最終回答（Markdown）を LLM に生成させます。

```python:packages/graphrag/graphrag/query/structured_search/global_search/search.py:306-421
    async def _reduce_response(
        self,
        map_responses: list[SearchResult],
        query: str,
        **llm_kwargs,
    ) -> SearchResult:
        """Combine all intermediate responses from single batches into a final answer to the user query."""
        ...
            # filter response with score = 0 and rank responses by descending order of score
            filtered_key_points = [
                point
                for point in key_points
                if point["score"] > 0  # type: ignore
            ]
            ...
            filtered_key_points = sorted(
                filtered_key_points,
                key=lambda x: x["score"],  # type: ignore
                reverse=True,  # type: ignore
            )

            data = []
            total_tokens = 0
            for point in filtered_key_points:
                formatted_response_data = []
                formatted_response_data.append(
                    f"----Analyst {point['analyst'] + 1}----"
                )
                formatted_response_data.append(
                    f"Importance Score: {point['score']}"  # type: ignore
                )
                formatted_response_data.append(point["answer"])  # type: ignore
                formatted_response_text = "\n".join(formatted_response_data)
                if (
                    total_tokens + len(self.tokenizer.encode(formatted_response_text))
                    > self.max_data_tokens
                ):
                    break
                data.append(formatted_response_text)
                total_tokens += len(self.tokenizer.encode(formatted_response_text))
            text_data = "\n\n".join(data)

            search_prompt = self.reduce_system_prompt.format(
                report_data=text_data,
                response_type=self.response_type,
                max_length=self.reduce_max_length,
            )
            ...
            messages_builder = (
                CompletionMessagesBuilder()
                .add_system_message(search_prompt)
                .add_user_message(query)
            )

            search_response = ""
            ...
            # LLM Completion stream
            return SearchResult(
                response=search_response,
                ...
            )
```

---

## 4. `4-local` (Local Searchによる個別質問)

ローカル検索は、特定のエンティティやそれらに直接関係する情報を抽出し、関連する生テキストとともに一度のプロンプトで回答します。

### 4.1 00001.xml（ローカルコンテキストからの直接回答）

`LocalContextBuilder` に `query` を渡し、そのクエリ内のキーワードに類似するエンティティ、関連するリレーションシップ、周辺のコベリエイト（covariates）、および該当する生のテキストチャンクをコンテキストウィンドウサイズ内に収まるよう収集し、`context_chunks` としてまとめます。
これを `self.system_prompt` の `{context_data}` に埋め込んでシステムメッセージに設定し、ユーザーの質問 `query` を送信することで、1回の LLM 呼び出しで詳細な回答（Markdown）を直接生成させます。

```python:packages/graphrag/graphrag/query/structured_search/local_search/search.py:56-132
    async def search(
        self,
        query: str,
        conversation_history: ConversationHistory | None = None,
        **kwargs,
    ) -> SearchResult:
        """Build local search context that fits a single context window and generate answer for the user query."""
        start_time = time.time()
        search_prompt = ""
        llm_calls, prompt_tokens, output_tokens = {}, {}, {}
        context_result = self.context_builder.build_context(
            query=query,
            conversation_history=conversation_history,
            ...
        )
        ...
        try:
            if "drift_query" in kwargs:
                ...
            else:
                search_prompt = self.system_prompt.format(
                    context_data=context_result.context_chunks,
                    response_type=self.response_type,
                )

            messages_builder = (
                CompletionMessagesBuilder()
                .add_system_message(search_prompt)
                .add_user_message(query)
            )

            full_response = ""

            response: AsyncIterator[
                LLMCompletionChunk
            ] = await self.model.completion_async(
                messages=messages_builder.build(),
                stream=True,
                **self.model_params,
            )  # type: ignore

            async for chunk in response:
                response_text = chunk.choices[0].delta.content or ""
                full_response += response_text
                ...

            return SearchResult(
                response=full_response,
                context_data=context_result.context_records,
                ...
            )
```
