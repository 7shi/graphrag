# GraphRAG 実行ログ（rawlogs）詳細分析レポート

このドキュメントは、GraphRAG の各実行プロセス（`prompt-tune`、`index`、`query --method global`、`query --method local`）で記録された XML ログファイル群を、補助スクリプト（`rawlog_log.py`、`rawlog_fields.py`）およびローカルLLM（`gemma4:26b`）を用いて解析・要約した結果をまとめたレポートです。

各フェーズで LLM がどのようなクエリを処理し、どのような形式（JSON / テキスト）でレスポンスを出力しているかを解説します。

---

## 1. `1-prompt-tune` (自動プロンプトチューニング)

日本語の解析・出力にシステムプロンプトを最適化するためのフェーズです。クエリとレスポンスの流れに沿って、時系列で以下のステップが実行されています。

### 1.1 00001.xml（ドメイン特定）
解析対象テキスト（『クリスマス・キャロル』）を分析し、最適なジャンル（ドメイン）を割り当てるタスクです。

入力された長い小説の抜粋テキストを分析し、それが学術論文などではなく「文学作品」であることを判断しています。
```text
Literature
```

### 1.2 00002.xml（専門家ペルソナの定義）
文学分野の分析を行うのに最適な専門家プロフィールを設定しています。

対象となるドメイン（Literature）に基づいて、タスクを解くための理想的なAIの役割（ペルソナ）を定義させています。
```text
You are an expert Bibliometric Analyst and Network Scientist. You are skilled at mapping citation networks, identifying co-authorship patterns, and extracting relational metadata from academic publications. You are adept at helping people with identifying the structural connections, influential nodes, and evolving clusters within specific research communities in the Literature domain.
```

### 1.3 00003.xml（評価基準の定義）
専門家の視点から、テキストデータの重要性を判断するためのルール・評価基準を設定しています。

ドメインや専門家ペルソナに基づき、ドキュメントの価値を判断するための 0〜10 のスコアの評価基準を定義しています。
```text
A float score between 0-10 that represents the relevance of the text to bibliometric analysis, citation networks, co-authorship patterns, and relational metadata within the literary domain, with 1 being trivial or irrelevant and 10 being highly significant for identifying structural connections, influential nodes, and evolving research clusters in academic literature.
```

### 1.4 00004.xml（エンティティ種別の抽出） ※JSON出力
物語内の実体のカテゴリ（`entity_types`）を自動定義し、アノテーションのための基盤スキーマを作成しています。

テキストの文脈において抽出するべき重要な情報の種類を決定し、JSONの配列として出力させています。
```json
{"entity_types": ["person", "spirit", "location", "food", "object", "family_member", "time", "feeling"]}
```

### 1.5 00005.xml 〜 00009.xml（エンティティ・関係性のFew-Shot抽出）
テキストの本文から、登場人物、アイテム、場所、およびそれらの結びつきの強さ（1〜10）を指定フォーマット（独自のデリミタ `<|>` や `##`）で抽出するための指示と抽出データです。

ログごとに、抽出のための Few-shot 例題や、実際に『クリスマス・キャロル』のテキストから抽出されたエンティティと関係性のデータが含まれます。日本語での詳細説明が出力されます。

00005.xml の一部:
```text
("entity"<|>SCROOGE<|>PERSON<|>スクルージ。精霊と共に街を歩き、人々の食事の様子を見守る)
##
("entity"<|>THE SPIRIT<|>SPIRIT<|>街の人々に香を振りかけるなど、寛大な性質を持つ精霊。スクルージに教えを与えるために同行している)
##
("relationship"<|THE SPIRIT<|>SCROOGE<|>精霊はスクルージと共に街を歩き、様々な場面を見せている>6)
##
("relationship"<|THE SPIRIT<|>BOB CRATCHIT'S DWELLING<|>精霊がボブ・クラチットの家を祝福するために立ち寄る>8)

<|COMPLETE|>
```

### 1.6 00010.xml（最終役割プロンプトの生成）
作品構造を解析するために「文学構造分析官（Literary Structural Analyst）」という高度な役割プロンプト（システム指示文）を最終生成しています。

チューニング結果を反映し、インデックス作成時にLLMのシステム指示として設定される最も重要なプロンプトテンプレートの一部となるテキストです。
```text
A literary structural analyst that is analyzing Charles Dickens' "A Christmas Carol," given a collection of narrative excerpts that include character dialogues, thematic descriptions, and episodic transitions. 

The report will be used to map the complex relational network between protagonist transformations, supernatural entities, and the socioeconomic settings that drive the story's emotional arc and moral resolution.
```

---

## 2. `2-index` (インデックス作成 / ナレッジグラフ構築)

入力された長文テキストから知識グラフを構築し、マージとコミュニティ要約レポートを作成する中心プロセスです。246個のログが記録されており、以下のようにプロセス順にステップが進みます。

### 2.1 00001.xml（疎通確認）
LLM APIが正常に稼働しているかを確かめるためのテスト接続の出力です。
```text
Hello World
```

### 2.2 00002.xml 〜 00081.xml（エンティティ・関係性の抽出）
小説の本文やライセンス情報（テキストユニット）から、登場人物、場所、出来事、およびそれらの結びつきを検出し、日本語の説明付きで抽出する初期フェーズです（全80ファイル）。

00002.xml の出力例:
```text
("entity"<|>SCROOGE<|><person><|>スクルージ。マーレーの幽霊に警告を受け、恐怖と驚きを感じている人物。>
##
("entity"<|>MARLEY'S GHOST<|><spirit><|>かつてスクルージの友人であり、現在は鎖を体に巻き付けている姿で現れる精神的存在。スクルージに将来への警告を与えている。>
##
("entity"<|>THREE SPIRITS<|><spirit><|>スクルージにこれから訪れることになる、3人の精神的存在。>
##
...
##
("relationship"<|>MARLEY'S GHOST<|>SCROOGE<|>マーレーの幽霊はスクルージのかつての友人であり、現在は彼の前に現れて警告を与えている。>8
```

### 2.3 00082.xml 〜 00223.xml（エンティティの要約・マージと矛盾解消）
物語の異なる箇所から個別に抽出された同一エンティティの断片的な記述を集約・要約し、1つの整理された紹介文へと統合する中期フェーズです（全142ファイル）。

00100.xml の出力例（同一人物「DICK WILKINS」の情報マージ）:
```text
ディック・ウィルキンス（DICK WILKINS）は、スクルージの元徒弟であり、かつての同僚でもある人物である。以前からスクルージとは親しい関係にあり、過去に共に修行を積んだ間柄としての繋がりを持っている。
```

### 2.4 00224.xml（構造化コミュニティレポートの生成） ※JSON出力
密接に関わるエンティティのグループ（コミュニティ）ごとに、ネットワーク科学的手法に基づいて構造化コミュニティレポート（要約書）を生成する後期フェーズです。ハルシネーションを防ぐために、参照データID（`[Data: ...]`）が付与された厳格なJSON構造で出力されます。
```json
{
    "title": "エベネザー・スクルージの精神的変容と超自然的ネットワーク",
    "summary": "本コミュニティは、主人公エベネザー・スクルージを中心とした極めて動的な関係性によって構成されています。主要なノードであるスクルージは、亡きビジネスパートナーであるジェイコブ・マーレーの亡霊、および彼を導く3人の精神（THREE SPIRITS）との相互作用を通じて、自身の過去と向き合い、劇的な道徳的再生を遂げます...",
    "findings": [
        {
            "summary": "エベネザー・スクルージを中心とした高次ノードの構造",
            "explanation": "エベネザー・スクルージは、この物語ネットワークにおける中心的なハブ（Hub）として機能しており、他のほぼすべてのエンティティと直接的または間接的に接続されています [Data: Entities (0); Relationships (0, 12, 13, 15, 19, 21, 23, 31, 40, 41, 53, 57, 61, 68, 69, 74, 85, 112)]。彼の高い次数（Degree: 46）は、彼が単なる登場人物ではなく、物語の全イベントと感情的変化を繋ぐ構造的な結節点であることを示しています。..."
        },
        {
            "summary": "亡霊と精神による超自然的介入のメカニズム",
            "explanation": "ジェイコブ・マーレー（JACOB MARLEY）と3人の精神（THREE SPIRITS）は、スクルージの内的世界を強制的に変容させるための「媒介変数」として機能しています [Data: Entities (124, 148); Relationships (23, 31, 57)]。..."
        }
        // ...
    ],
    "rating": 9.5,
    "rating_explanation": "このテキストは、キャラクターの変容、象徴的オブジェクト、超自然的エンティティ間の複雑な関係性を詳細に記述しており..."
}
```

---

## 3. `3-global` (Global Searchによる全体質問)

「この物語の主要なテーマは何ですか？」のような、ドキュメント全体を跨ぐマクロな問いに対する質問応答プロセスです。

### 3.1 00001.xml（要点抽出その1） ※JSON出力
蓄積されたコミュニティレポート群（テーブル形式）の第1バッチから、質問に対する回答の根拠となる要点（points）と、その重要度スコア（score）、参照元データ（Reports id）を抽出したJSONデータです。
```json
{
    "points": [
        {
            "description": "主人公エベネザー・スクルージの精神前変容と道徳的な再生が中心的なテーマです。彼は、亡きビジネスパートナーや3人の精神との相互作用を通じて、恐怖から慈愛へと至る感情的な弧を描き、社会的孤立から社会への再統合へと劇的なシフトを遂げます [Data: Reports (14)]。",
            "score": 95
        },
        {
            "description": "物語は、経済的な執着や物質的な所有（現金箱、鍵、帳簿など）が、死後の罪業の象徴である「鎖」へと変容するプロセスを描いており、商業的執着が精神的な束縛となる構造を示しています [Data: Reports (3)]。",
            "score": 85
        }
        // ...
    ]
}
```

### 3.2 00002.xml（要点抽出その2） ※JSON出力
蓄積されたコミュニティレポート群の第2バッチから、さらに別の切り口の要点（points）を同様に抽出・構造化したJSONデータです。
```json
{
    "points": [
        {
            "description": "主人公エベネザー・スクルージの精神的な変容：強欲で孤立していた状態から、慈愛に満ちた社会の一員へと再生するプロセスが物語の中核をなしています [Data: Reports (2, 5, 19, 22)]。",
            "score": 100
        },
        {
            "description": "超自然的な介入による道徳的教訓：精神（GHOST）と呼ばれる存在が、過去・現在・未来の視点からスクルージに介入し、自身の人生や他者の運命に向き合わせることで、彼の価値観を再構築させます [Data: Reports (2, 5, 17, 22)]。",
            "score": 95
        }
        // ...
    ]
}
```

### 3.3 00003.xml（回答集約・Markdown回答）
前ステップ（3.1 および 3.2）で抽出された複数の `points` 情報を読み込み、重複の排除や論理整合性の調整を行った上で、最終的なMarkdown形式のテーマ分析報告書を生成しています。出典元のエビデンス（`[Data: Reports (id)]`）が記載されています。
```markdown
# 物語の主要なテーマと精神的変容の分析

この物語における中心的なテーマは、主人公エベネザー・スクルージの精神的な変容と、それに伴う道徳的な再生のプロセスです。以下にその詳細な構造を解説します。

### 精神的な変容と道徳前再生
物語の中核をなすのは、強欲で孤立していた状態から、慈愛に満ちた社会の一員へとスクルージが再生していく過程です [Data: Reports (2, 5, 14, 19, 22)]。彼は亡きビジネスパートナーや3人の精神（GHOST）との相互作用を通じ、恐怖から慈愛へと至る感情的な弧を描きます。...
```

---

## 4. `4-local` (Local Searchによる個別質問)

特定の登場人物（「スクルージはどのような人物で、誰とどのような関係があるか」など）に焦点を当てたミクロな問いに対する質問応答プロセスです。

### 4.1 00001.xml（ローカルコンテキストからの直接回答）
質問に関連するエンティティとリレーション情報をコンテキストに詰め込み、直接回答を1回で作成しています。
スクルージの性格（強欲から慈愛への変容）、および周辺人物との関係性がカテゴリ別（ビジネス・家族・社会的関係）に整理され、根拠ID（`[Data: Reports (id); Entities (id)]`）付きの丁寧な解説テキストとして直接出力されています。
```markdown
エベネザー・スクルージの人物像とその周囲の人々との複雑な人間関係について、提供された資料に基づきまとめます。

### エベネザー・スクルージの人物像

エベネザー・スクルージは、物語の中心となる圧倒的な存在であり、極めて高い次数を持つハブとして機能しています [Data: Reports (0); Entities (0)]。彼の性格は以下のような特徴を持っています。

*   **強欲さと孤独:** 彼は「握りつぶすような、むしり取るような、掴み取ろうとする、執着心の強い強欲な罪人」として描かれ、非常に強欲で、硬い石のような冷酷な性質を持っています [Data: Sources (1)]。また、非常に孤独であり、「牡蠣のように自己完結し、世間から隔絶された」状態にありました [Data: Sources (1)]。
*   **社会的・精神的な変容:** 物語を通じて、彼は「孤独と強欲」から「慈愛と社会貢献」へと劇的に変化を遂げます [Data: Reports (23, 31, 41, 57, +more)]。...
```

---

## 5. まとめ

XMLログのパースと要約を俯瞰すると、GraphRAGの高度な動作ロジックが明確に浮き彫りになります。

1. **非構造化データの抽出と日本語化**（テキストを細切れにして、エンティティと関係性をリスト化する）
2. **情報の集約と要約**（散らばった記述を名寄せし、1つの矛盾のないプロフィールに統合する）
3. **ネットワーク構造の分析**（コミュニティごとに、データ根拠付きのJSON要約レポートを生成する）
4. **マクロ検索時の並列抽出と最終リライト**（JSONでの要点抽出を経て、1つの報告書へ編み直す）

このログを監視・分析することは、LLMを使ったナレッジグラフ構築の品質をデバッグし、プロンプトを洗練させる上で非常に強力な手段となります。
