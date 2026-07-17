# Orchestrator ↔ Apps — Capability Catalogue & Gap Analysis

_Generated from each app's own live API list (`/openapi.json`) plus WebSocket routes read from source. This is the authoritative list of what each app can do — not a hand-written summary — cross-referenced against what the orchestrator currently knows how to call._

**Legend:** ✅ = the orchestrator already uses this &nbsp;|&nbsp; ❌ = the app offers it, the orchestrator can't reach it &nbsp;|&nbsp; ⚙️ = internal/support endpoint (health, docs — not a user capability).

## Coverage at a glance

| App | Covered | Missing capabilities | Internal | Total |
|---|---|---|---|---|
| Simulated Learning (`simulated-learning`) | 2 | **1** | 1 | 4 |
| ArXiv Paper Guide (`arxiv-papers`) | 7 | **17** | 1 | 25 |
| Coding Playground (`coding-playground`) | 6 | **62** | 2 | 70 |
| AI Intelligence Deck (`ai-intelligence-deck`) | 3 | **3** | 1 | 7 |
| Social Media AI (`social-media-ai`) | 4 | **3** | 1 | 8 |
| Stanford LLM Course (`stanford-llm`) | 1 | **0** | 1 | 2 |
| Statistics Teacher (`stats-teacher`) | 1 | **1** | 1 | 3 |
| Teach Me (`teach-me`) | 4 | **4** | 0 | 8 |
| Github Learnings (`github-learnings`) | 4 | **32** | 0 | 36 |
| Blogs Playground (`blogs-playground`) | 6 | **31** | 1 | 38 |
| Research Assistant (`research-assistant`) | 8 | **20** | 2 | 30 |
| **TOTAL** | **46** | **174** | **11** | **231** |

## Simulated Learning  
`simulated-learning` · port 8001 · Simulated Learning Backend

| ? | Endpoint | What it does | Inputs | Returns |
|---|---|---|---|---|
| ❌ | `GET /{full_path}` | Serve Spa | full_path | — |
| ✅ | `POST /api/ask` | Ask Endpoint | AskRequest | AskResponse |
| ✅ | `POST /api/execute` | Execute Code | CodeRequest | CodeResponse |
| ⚙️ | `GET /api/health` | Health Check | — | — |

## ArXiv Paper Guide  
`arxiv-papers` · port 8002 · ArXiv AI Paper Explorer

_Discover, search, and understand AI research papers from arXiv_


| ? | Endpoint | What it does | Inputs | Returns |
|---|---|---|---|---|
| ❌ | `GET /api/db/tables` | List Tables | — | — |
| ❌ | `GET /api/db/tables/{table_name}` | Get Table Data | table_name, limit, offset | — |
| ❌ | `GET /api/favorites/` | List Favorites | — | array |
| ❌ | `POST /api/favorites/` | Add Favorite | FavoriteCreateRequest | FavoriteOut |
| ❌ | `PUT /api/favorites/{favorite_id}` | Update Favorite | favorite_id, FavoriteUpdateRequest | FavoriteOut |
| ❌ | `DELETE /api/favorites/{favorite_id}` | Remove Favorite | favorite_id | — |
| ❌ | `POST /api/implement/chat` | Api Chat | routers__implement__ChatRequest | — |
| ❌ | `POST /api/implement/hint` | Api Get Hint | HintRequest | — |
| ❌ | `POST /api/implement/plan` | Api Generate Plan | PlanRequest | — |
| ❌ | `POST /api/implement/run` | Api Run Code | RunRequest | — |
| ❌ | `POST /api/implement/verify` | Api Verify | VerifyRequest | — |
| ❌ | `GET /api/luminaries/` | List Luminaries | — | array |
| ❌ | `GET /api/luminaries/{author_id}/papers` | Get Luminary Papers | author_id | array |
| ❌ | `POST /api/papers/by-title` | Search By Title | PaperSearchRequest | array |
| ❌ | `GET /api/papers/revolutionary` | Get Revolutionary Papers | — | array |
| ❌ | `POST /api/seed-revolutionary` | Trigger Seed | — | — |
| ❌ | `POST /api/url-paper/chat` | Chat Url Paper | URLPaperChatRequest | ChatResponse |
| ✅ | `POST /api/ai/analyze` | Analyze Paper | AIRequest | AIResponse |
| ✅ | `POST /api/ai/chat` | Chat | schemas__ChatRequest | ChatResponse |
| ✅ | `POST /api/papers/by-id` | Get Paper By Id | PaperIdRequest | PaperOut |
| ✅ | `POST /api/papers/search` | Search Papers | PaperSearchRequest | array |
| ✅ | `POST /api/topics/search` | Search By Topic | TopicSearchRequest | array |
| ✅ | `POST /api/url-paper/analyze` | Analyze Url Paper | URLPaperAnalyzeRequest | AIResponse |
| ✅ | `POST /api/url-paper/fetch` | Fetch Url Paper | URLPaperRequest | URLPaperResponse |
| ⚙️ | `GET /api/health` | Health Check | — | — |

## Coding Playground  
`coding-playground` · port 8003 · ML Coding Playground API

| ? | Endpoint | What it does | Inputs | Returns |
|---|---|---|---|---|
| ❌ | `POST /api/chat/send` | Send Message | ChatRequest | — |
| ❌ | `POST /api/code-complete/` | Api Complete Code | CompleteRequest | — |
| ❌ | `POST /api/datasets/upload` | Upload Dataset | — | — |
| ❌ | `GET /api/datasets/{dataset_id}/load-code` | Get Dataset Load Code | dataset_id | — |
| ❌ | `POST /api/debug/analyze` | Post Analyze | DebugRequest | — |
| ❌ | `GET /api/debug/pitfalls` | List Pitfalls | — | — |
| ❌ | `GET /api/debug/pitfalls/{pitfall_id}` | Pitfall Detail | pitfall_id | — |
| ❌ | `POST /api/dl-rl/dl/generate-code` | Post Dl Generate Code | DLTrainRequest | — |
| ❌ | `GET /api/dl-rl/dl/models` | List Dl Models | — | — |
| ❌ | `GET /api/dl-rl/dl/models/{model_id}/params` | Dl Model Params | model_id | — |
| ❌ | `POST /api/dl-rl/dl/train` | Post Dl Train | DLTrainRequest | — |
| ❌ | `GET /api/dl-rl/rl/envs` | List Rl Envs | — | — |
| ❌ | `POST /api/dl-rl/rl/generate-code` | Post Rl Generate Code | RLTrainRequest | — |
| ❌ | `GET /api/dl-rl/rl/models` | List Rl Models | — | — |
| ❌ | `GET /api/dl-rl/rl/models/{model_id}/params` | Rl Model Params | model_id | — |
| ❌ | `POST /api/dl-rl/rl/train` | Post Rl Train | RLTrainRequest | — |
| ❌ | `GET /api/eda/{dataset_id}/correlation` | Get Correlation | dataset_id | — |
| ❌ | `GET /api/eda/{dataset_id}/distribution` | Get Distribution | dataset_id, column, plot_type | — |
| ❌ | `GET /api/eda/{dataset_id}/dtypes-missing` | Get Dtypes Missing | dataset_id | — |
| ❌ | `GET /api/eda/{dataset_id}/outliers` | Get Outliers | dataset_id, column, method | — |
| ❌ | `GET /api/eda/{dataset_id}/scatter` | Get Scatter | dataset_id, x, y, color | — |
| ❌ | `GET /api/eda/{dataset_id}/summary` | Get Summary | dataset_id | — |
| ❌ | `GET /api/eda/{dataset_id}/target-distribution` | Get Target Dist | dataset_id, target | — |
| ❌ | `GET /api/learn/paths` | List Paths | — | — |
| ❌ | `GET /api/learn/paths/{path_id}/topics` | List Topics | path_id | — |
| ❌ | `GET /api/learn/paths/{path_id}/topics/{topic_id}` | Topic Detail | path_id, topic_id | — |
| ❌ | `GET /api/learn/snippets` | List Snippets | q | — |
| ❌ | `POST /api/llm/generate-code` | Post Llm Generate Code | LLMRunRequest | — |
| ❌ | `GET /api/llm/models` | List Llm Models | — | — |
| ❌ | `GET /api/llm/models/{model_id}/params` | Llm Model Params | model_id | — |
| ❌ | `POST /api/llm/run` | Post Llm Run | LLMRunRequest | — |
| ❌ | `GET /api/mdp/gym-mapping/{env_id}` | Gym Mdp Map | env_id | — |
| ❌ | `GET /api/mdp/list` | List Mdps | — | — |
| ❌ | `POST /api/mdp/solve` | Solve Mdp | SolveRequest | — |
| ❌ | `GET /api/mdp/{mdp_id}` | Mdp Detail | mdp_id | — |
| ❌ | `POST /api/ml/generate-code` | Post Generate Code | TrainRequest | — |
| ❌ | `GET /api/ml/models` | List Models | — | — |
| ❌ | `GET /api/ml/models/{model_id}/params` | Model Params | model_id | — |
| ❌ | `POST /api/ml/train` | Post Train | TrainRequest | — |
| ❌ | `POST /api/ml/train-unsupervised` | Post Train Unsupervised | UnsupervisedRequest | — |
| ❌ | `GET /api/notebooks/list` | Api List Notebooks | — | — |
| ❌ | `POST /api/notebooks/save` | Api Save Notebook | SaveRequest | — |
| ❌ | `GET /api/notebooks/{notebook_id}` | Api Load Notebook | notebook_id | — |
| ❌ | `DELETE /api/notebooks/{notebook_id}` | Api Delete Notebook | notebook_id | — |
| ❌ | `PUT /api/notebooks/{notebook_id}/rename` | Api Rename Notebook | notebook_id, RenameRequest | — |
| ❌ | `POST /api/preprocessing/{dataset_id}/balance` | Post Balance | dataset_id, BalanceRequest | — |
| ❌ | `GET /api/preprocessing/{dataset_id}/columns` | Get Columns | dataset_id | — |
| ❌ | `POST /api/preprocessing/{dataset_id}/encode` | Post Encode | dataset_id, EncodeRequest | — |
| ❌ | `POST /api/preprocessing/{dataset_id}/impute` | Post Impute | dataset_id, ImputeRequest | — |
| ❌ | `POST /api/preprocessing/{dataset_id}/scale` | Post Scale | dataset_id, ScaleRequest | — |
| ❌ | `POST /api/preprocessing/{dataset_id}/split` | Post Split | dataset_id, SplitRequest | — |
| ❌ | `GET /api/tips` | List Tips | category | — |
| ❌ | `GET /api/tips/categories` | List Tip Categories | — | — |
| ❌ | `GET /api/tips/shortcuts` | List Shortcuts | — | — |
| ❌ | `POST /api/viz/classification-metrics` | Post Classification Metrics | VizRequest | — |
| ❌ | `POST /api/viz/compare` | Post Compare | CompareRequest | — |
| ❌ | `POST /api/viz/cross-validation` | Post Cross Val | CrossValRequest | — |
| ❌ | `POST /api/viz/decision-boundary` | Post Decision Boundary | DecisionBoundaryRequest | — |
| ❌ | `POST /api/viz/learning-curve` | Post Learning Curve | LearningCurveRequest | — |
| ❌ | `POST /api/viz/pr-curve` | Post Pr Curve | VizRequest | — |
| ❌ | `POST /api/viz/regression-plots` | Post Regression Plots | VizRequest | — |
| ❌ | `POST /api/viz/roc` | Post Roc | VizRequest | — |
| ✅ | `GET /api/datasets/` | Get Datasets | — | — |
| ✅ | `GET /api/datasets/{dataset_id}/preview` | Get Preview | dataset_id, n_rows | — |
| ✅ | `POST /api/kernel/interrupt` | Kernel Interrupt | — | — |
| ✅ | `POST /api/kernel/restart` | Kernel Restart | — | — |
| ✅ | `POST /api/kernel/start` | Kernel Start | — | — |
| ✅ | `GET /api/kernel/status` | Kernel Status | — | — |
| ⚙️ | `GET /` | Root | — | — |
| ⚙️ | `GET /health` | Health | — | — |

## AI Intelligence Deck  
`ai-intelligence-deck` · port 8004 · AI Intelligence Deck API

| ? | Endpoint | What it does | Inputs | Returns |
|---|---|---|---|---|
| ❌ | `POST /api/dismiss` | Dismiss Item | DismissRequest | — |
| ❌ | `POST /api/refresh` | Trigger Refresh | RefreshRequest | RefreshResponse |
| ❌ | `GET /{full_path}` | Serve Spa | full_path | — |
| ✅ | `GET /api/data` | Get Data | — | — |
| ✅ | `POST /api/summary` | Get Summary | SummaryRequest | — |
| ✅ | `POST /api/trends` | Get Trends | TrendsRequest | — |
| ⚙️ | `GET /health` | Health Check | — | — |

## Social Media AI  
`social-media-ai` · port 8005 · Social Media AI Aggregator

| ? | Endpoint | What it does | Inputs | Returns |
|---|---|---|---|---|
| ❌ | `GET /api/feedback` | Get Feedback | — | — |
| ❌ | `POST /api/feedback` | Submit Feedback | FeedbackRequest | — |
| ❌ | `GET /{full_path}` | Serve Spa | full_path | — |
| ✅ | `GET /api/all` | Get All Feeds | — | — |
| ✅ | `GET /api/categories` | Get Categories | — | — |
| ✅ | `GET /api/medium` | Get Medium Feed | — | — |
| ✅ | `GET /api/twitter` | Get Twitter Feed | — | — |
| ⚙️ | `GET /api/health` | Health Check | — | — |

## Stanford LLM Course  
`stanford-llm` · port 8006 · Stanford CME 295 Course Chatbot API

| ? | Endpoint | What it does | Inputs | Returns |
|---|---|---|---|---|
| ✅ | `POST /api/chat` | Chat With Assistant | ChatRequest | ChatResponse |
| ⚙️ | `GET /api/health` | Health Check | — | — |

## Statistics Teacher  
`stats-teacher` · port 8007 · Stats Teacher API

| ? | Endpoint | What it does | Inputs | Returns |
|---|---|---|---|---|
| ❌ | `GET /{full_path}` | Serve Spa | full_path | — |
| ✅ | `POST /api/qa` | Ask Question | QARequest | — |
| ⚙️ | `GET /api/health` | Health Check | — | — |

## Teach Me  
`teach-me` · port 8008 · Teach Me

| ? | Endpoint | What it does | Inputs | Returns |
|---|---|---|---|---|
| ❌ | `GET /preferences` | Get Preferences | — | array |
| ❌ | `POST /topics/{topic_id}/advance` | Advance Concept | topic_id | MessageOut |
| ❌ | `POST /topics/{topic_id}/feedback` | Submit Feedback | topic_id, FeedbackCreate | FeedbackOut |
| ❌ | `GET /{full_path}` | Serve Frontend | full_path | — |
| ✅ | `GET /topics` | List Topics | — | array |
| ✅ | `POST /topics` | Create Topic | TopicCreate | TopicDetail |
| ✅ | `GET /topics/{topic_id}` | Get Topic | topic_id | TopicDetail |
| ✅ | `POST /topics/{topic_id}/messages` | Send User Message | topic_id, MessageCreate | MessageOut |

## Github Learnings  
`github-learnings` · port 8009 · GitHub Learning Platform

| ? | Endpoint | What it does | Inputs | Returns |
|---|---|---|---|---|
| ❌ | `POST /api/build/suggest` | Get architecture suggestions (SSE streaming) | BuildSuggestRequest | — |
| ❌ | `POST /api/chat/code` | Chat about specific files in a repository (SSE streaming) | ChatRequest | — |
| ❌ | `POST /api/chat/cross-repo` | Chat across all ingested repositories (SSE streaming) | ChatRequest | — |
| ❌ | `POST /api/chat/repo` | Chat with a repository (SSE streaming) | ChatRequest | — |
| ❌ | `GET /api/chat/sessions` | List all chat sessions | — | — |
| ❌ | `POST /api/chat/sessions` | Create a new chat session | ChatSession | — |
| ❌ | `GET /api/chat/sessions/{session_id}` | Get a chat session with messages | session_id | — |
| ❌ | `DELETE /api/chat/sessions/{session_id}` | Delete a chat session | session_id | — |
| ❌ | `POST /api/compare/` | Compare repositories (SSE streaming) | CompareRequest | — |
| ❌ | `POST /api/help/chat` | Help Chat Endpoint | HelpChatRequest | — |
| ❌ | `GET /api/learning-paths/` | List all learning paths | — | array |
| ❌ | `POST /api/learning-paths/` | Create a learning path | LearningPathCreate | — |
| ❌ | `POST /api/learning-paths/generate` | Auto-generate a learning path | LearningPathGenerate | — |
| ❌ | `GET /api/learning-paths/{path_id}` | Get a learning path | path_id | object |
| ❌ | `DELETE /api/learning-paths/{path_id}` | Delete a learning path | path_id | object |
| ❌ | `POST /api/learnings/extract/{repo_id}` | Trigger learning extraction for a repository | repo_id | — |
| ❌ | `DELETE /api/learnings/{learning_id}` | Delete a learning | learning_id | object |
| ❌ | `GET /api/patterns/` | List all patterns | category | array |
| ❌ | `GET /api/patterns/categories` | List distinct pattern categories | — | array |
| ❌ | `POST /api/patterns/detect-cross` | Detect cross-repo patterns | — | — |
| ❌ | `POST /api/patterns/detect/{repo_id}` | Detect patterns in a repository | repo_id | — |
| ❌ | `GET /api/patterns/search` | Search patterns | q | array |
| ❌ | `GET /api/repos/{repo_id}` | Get repository details | repo_id | RepoResponse |
| ❌ | `DELETE /api/repos/{repo_id}` | Delete a repository | repo_id | StatusMessage |
| ❌ | `GET /api/repos/{repo_id}/file` | Get file content | repo_id, path | RepoFileContent |
| ❌ | `GET /api/repos/{repo_id}/files` | Get repository file tree | repo_id | array |
| ❌ | `POST /api/snippets/` | Create a new snippet | SnippetCreate | — |
| ❌ | `GET /api/snippets/` | List snippets | repo_id, language, tags | array |
| ❌ | `GET /api/snippets/search` | Search snippets | q | array |
| ❌ | `GET /api/snippets/{snippet_id}` | Get a snippet | snippet_id | object |
| ❌ | `PUT /api/snippets/{snippet_id}` | Update a snippet | snippet_id, body | object |
| ❌ | `DELETE /api/snippets/{snippet_id}` | Delete a snippet | snippet_id | object |
| ✅ | `GET /api/learnings/` | List all learnings | repo_id | array |
| ✅ | `GET /api/learnings/search` | Search learnings | q | array |
| ✅ | `GET /api/repos/` | List all ingested repositories | — | array |
| ✅ | `POST /api/repos/` | Ingest a new repository | RepoIngestRequest | — |

## Blogs Playground  
`blogs-playground` · port 8010 · Blogs Playground Backend

| ? | Endpoint | What it does | Inputs | Returns |
|---|---|---|---|---|
| ❌ | `POST /api/blog/generate` | Api Generate | GenerateReq | — |
| ❌ | `POST /api/blog/generate/streaming` | Api Generate Streaming | GenerateReq | — |
| ❌ | `POST /api/blog/import` | Api Import Blog | ImportReq | — |
| ❌ | `DELETE /api/blog/{blog_id}` | Api Delete Blog | blog_id | — |
| ❌ | `PATCH /api/blog/{blog_id}` | Api Patch Blog | blog_id, PatchBlogReq | — |
| ❌ | `POST /api/blog/{blog_id}/cover-image` | Api Cover Image | blog_id, CoverImageReq | — |
| ❌ | `POST /api/blog/{blog_id}/iterate` | Api Iterate | blog_id, IterateReq | — |
| ❌ | `POST /api/blog/{blog_id}/iterate/paragraph` | Api Iterate Paragraph | blog_id, ParagraphIterateReq | — |
| ❌ | `POST /api/blog/{blog_id}/manual_edit` | Api Manual Edit | blog_id, ManualEditReq | — |
| ❌ | `POST /api/blog/{blog_id}/publish/wordpress` | Api Wp Publish Blog | blog_id, WordpressPublishReq | — |
| ❌ | `POST /api/blog/{blog_id}/restore/{version_num}` | Api Restore Version | blog_id, version_num | — |
| ❌ | `POST /api/blog/{blog_id}/wordpress/unpublish` | Api Wp Unpublish Blog | blog_id | — |
| ❌ | `GET /api/blogs/search` | Api Blogs Search | q, status, tag, limit | — |
| ❌ | `GET /api/blogs/tags` | Api Blogs Tags | — | — |
| ❌ | `GET /api/blogs/{blog_id}/cost` | Api Blog Cost | blog_id | — |
| ❌ | `GET /api/models` | Models | — | — |
| ❌ | `GET /api/runs` | Api List Runs | — | — |
| ❌ | `POST /api/runs/{run_id}/cancel` | Api Cancel Run | run_id | — |
| ❌ | `GET /api/style` | Api Get Style | — | — |
| ❌ | `PUT /api/style` | Api Put Style | StyleProfileReq | — |
| ❌ | `POST /api/style/critique` | Api Style Critique | CritiqueReq | — |
| ❌ | `GET /api/style/drift` | Api Style Drift | — | — |
| ❌ | `POST /api/style/reset` | Api Reset Style | — | — |
| ❌ | `POST /api/style/sample` | Api Add Sample | StyleSampleReq | — |
| ❌ | `POST /api/style/samples/bulk` | Api Bulk Samples | BulkSampleReq | — |
| ❌ | `PATCH /api/style/trait/{trait_index}` | Api Patch Style Trait | trait_index, StyleTraitPatchReq | — |
| ❌ | `DELETE /api/style/trait/{trait_index}` | Api Delete Style Trait | trait_index | — |
| ❌ | `GET /api/topics/recent` | Api Topics Recent | limit | — |
| ❌ | `GET /api/wordpress/config` | Api Wp Get Config | — | — |
| ❌ | `POST /api/wordpress/config` | Api Wp Set Config | WordpressConfigReq | — |
| ❌ | `POST /api/wordpress/test` | Api Wp Test | — | — |
| ✅ | `POST /api/blog/generate/async` | Api Generate Async | GenerateReq | — |
| ✅ | `GET /api/blog/{blog_id}` | Api Get Blog | blog_id | — |
| ✅ | `POST /api/blog/{blog_id}/iterate/async` | Api Iterate Async | blog_id, IterateReq | — |
| ✅ | `GET /api/blogs` | Api List Blogs | — | — |
| ✅ | `GET /api/runs/{run_id}` | Api Get Run | run_id | — |
| ✅ | `GET /api/topics/suggestions` | Api Topic Suggestions | limit | — |
| ⚙️ | `GET /api/health` | Health | — | — |

## Research Assistant  
`research-assistant` · port 8011 · Research Assistant

| ? | Endpoint | What it does | Inputs | Returns |
|---|---|---|---|---|
| ❌ | `GET /api/bridges` | Bridges List | — | object |
| ❌ | `POST /api/bridges/regenerate` | Bridges Regenerate | — | object |
| ❌ | `DELETE /api/bridges/{bridge_id}` | Bridges Dismiss | bridge_id | object |
| ❌ | `POST /api/corpus/reindex` | Corpus Reindex | force | object |
| ❌ | `GET /api/corpus/{doc_id}/chunk/{idx}` | Corpus Chunk | doc_id, idx, neighbors | object |
| ❌ | `GET /api/disagreements` | Disagreements List | — | object |
| ❌ | `POST /api/disagreements` | Disagreement Create | DisagreementIn | object |
| ❌ | `DELETE /api/disagreements/{did}` | Disagreement Delete | did | object |
| ❌ | `GET /api/graph` | Graph | — | object |
| ❌ | `POST /api/notes` | Notes Create | NoteIn | object |
| ❌ | `DELETE /api/notes/{note_id}` | Notes Delete | note_id | object |
| ❌ | `POST /api/quiz/grade` | Quiz Grade | QuizGradeIn | object |
| ❌ | `POST /api/quiz/{run_id}/questions` | Quiz Questions | run_id | object |
| ❌ | `GET /api/review/queue` | Review Queue | — | object |
| ❌ | `POST /api/review/{concept_id}/done` | Review Done | concept_id | object |
| ❌ | `POST /api/review/{concept_id}/refresh` | Review Refresh | concept_id | object |
| ❌ | `GET /api/runs/{run_id}/events` | Get Run Events | run_id | object |
| ❌ | `GET /api/sources/trust` | List Trust | — | object |
| ❌ | `POST /api/sources/trust` | Set Trust | TrustIn | object |
| ❌ | `GET /api/stream/{run_id}` | Stream | run_id | — |
| ✅ | `GET /api/corpus` | Corpus List | — | object |
| ✅ | `POST /api/corpus/upload` | Corpus Upload | — | object |
| ✅ | `DELETE /api/corpus/{doc_id}` | Corpus Delete | doc_id | object |
| ✅ | `GET /api/notes` | Notes List | q | object |
| ✅ | `POST /api/research` | Start Research | ResearchRequest | object |
| ✅ | `GET /api/runs` | List Runs | — | object |
| ✅ | `GET /api/runs/{run_id}` | Get Run | run_id | object |
| ✅ | `POST /api/runs/{run_id}/cancel` | Cancel Run | run_id | object |
| ⚙️ | `GET /` | Root | — | object |
| ⚙️ | `GET /api/health` | Health | — | object |

## WebSocket capabilities (not in any app's /openapi.json)

| ? | App | Endpoint | What it does |
|---|---|---|---|
| ❌ | Coding Playground (`coding-playground`) | `WS /api/kernel/ws` | Run arbitrary Python in a live Jupyter kernel and stream back stdout, HTML, errors, and **rendered plot images (base64 PNG)**. This is the only source of free-form matplotlib graphs. |

_No other registered app exposes a WebSocket route._
