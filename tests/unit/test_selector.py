"""Unit tests for the operation selector — grounded operation + argument choice (no network)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pytest
from conftest import FakeLLM

from orchestrator.models import AppSelection, Subtask, SubtaskResult
from orchestrator.registry import AppEntry, AppOperation, RetrySpec, load_registry
from orchestrator.selector import (
    SelectionError,
    _enforce_arg_floors,
    build_select_message,
    load_system_prompt,
    select_operation,
)

REG = load_registry()
MakeLLM = Callable[[Sequence[str]], FakeLLM]


def _arxiv() -> AppEntry:
    app = REG.get("arxiv-papers")
    assert app is not None
    return app


def _subtask() -> Subtask:
    app = AppSelection("arxiv-papers", "ArXiv Paper Guide", "searches arxiv", 0.9, False)
    return Subtask("t1", "Find papers", "find recent MoE papers", (), app)


def test_prompt_requires_filling_primary_input_even_with_upstream() -> None:
    # Guards the fix for the empty-args-with-upstream bug (blog 422): the prompt must instruct the
    # model to fill the primary input from the subtask and treat upstream as id-only, not a reason
    # to leave the field blank.
    prompt = load_system_prompt()
    assert "primary input" in prompt
    assert "UPSTREAM RESULTS are ONLY" in prompt
    assert "Never return empty" in prompt


def test_prompt_requires_inline_chart_display() -> None:
    # Guards the fix for charts saved-to-disk-not-shown: code producing charts must display them
    # inline (plt.show) so the kernel captures them; saving to a file returns nothing to render.
    prompt = load_system_prompt()
    assert "plt.show()" in prompt
    assert "savefig" in prompt  # named as the thing NOT to do


def _blog_sub(title: str, desc: str) -> Subtask:
    app = AppSelection("blogs-playground", "Blogs Playground", "drafts blogs", 0.9, False)
    return Subtask("t2", title, desc, ("t1",), app)


def test_backfill_fills_missing_primary_field_from_subtask(fake_llm: MakeLLM) -> None:
    # The model returns EMPTY args (the upstream-distraction bug). 'topic' must be backfilled from
    # the subtask deterministically, so the blog app runs instead of failing to web.
    app = REG.get("blogs-playground")
    assert app is not None
    client = fake_llm(['{"operation": "generate_blog_async", "arguments": {}}'])
    op, args = select_operation(
        client, app, _blog_sub("Draft a blog", "write a blog on retro"), model="m"
    )
    assert op.name == "generate_blog_async"
    assert args["topic"] == "write a blog on retro"


def test_backfill_does_not_invent_id_fields(fake_llm: MakeLLM) -> None:
    # iterate needs blog_id (an id, not free text): it must NOT be fabricated from the subtask.
    app = REG.get("blogs-playground")
    assert app is not None
    client = fake_llm(['{"operation": "iterate_blog_async", "arguments": {}}'])
    op, args = select_operation(client, app, _blog_sub("Revise", "make it shorter"), model="m")
    assert op.name == "iterate_blog_async"
    assert not args.get("blog_id")  # id fields are never backfilled


def _upstream_result(output: object) -> SubtaskResult:
    return SubtaskResult(
        "t1",
        "arxiv-papers",
        "ArXiv Paper Guide",
        "ok",
        "search_papers_by_query",
        output,
        "http://arxiv/x",
        None,
        0.01,
    )


def test_select_success(fake_llm: MakeLLM) -> None:
    client = fake_llm(
        ['{"operation": "search_papers_by_query", "arguments": {"query": "moe", "max_results": 5}}']
    )
    op, args = select_operation(client, _arxiv(), _subtask(), model="m")
    assert op.name == "search_papers_by_query"
    assert args == {"query": "moe", "max_results": 5}


def test_select_requests_structured_tool_output(fake_llm: MakeLLM) -> None:
    # Regression for the code-heavy-argument truncation bug: the selection call must be made
    # as FORCED tool-use (so the response is always valid JSON, even when an argument embeds a
    # large multi-line code block) with a token budget big enough for that code.
    client = fake_llm(['{"operation": "search_papers_by_query", "arguments": {"query": "moe"}}'])
    select_operation(client, _arxiv(), _subtask(), model="m")
    req = client.requests[0]
    assert len(req.tools) == 1
    assert req.tools[0]["name"] == "select_operation"
    assert set(req.tools[0]["input_schema"]["properties"]) == {"operation", "arguments"}
    assert req.tool_choice == {"type": "tool", "name": "select_operation"}
    assert req.max_tokens >= 8000  # headroom for multi-section code args (was 2000 -> truncated)


def test_select_strips_code_fences(fake_llm: MakeLLM) -> None:
    client = fake_llm(
        ['```json\n{"operation": "get_paper_by_id", "arguments": {"arxiv_id": "2401.00001"}}\n```']
    )
    op, args = select_operation(client, _arxiv(), _subtask(), model="m")
    assert op.name == "get_paper_by_id"
    assert args == {"arxiv_id": "2401.00001"}


def test_select_open_fence_without_close(fake_llm: MakeLLM) -> None:
    client = fake_llm(['```\n{"operation": "get_paper_by_id", "arguments": {"arxiv_id": "1"}}'])
    op, args = select_operation(client, _arxiv(), _subtask(), model="m")
    assert op.name == "get_paper_by_id"
    assert args == {"arxiv_id": "1"}


def test_select_filters_unknown_arguments(fake_llm: MakeLLM) -> None:
    client = fake_llm(
        ['{"operation": "search_papers_by_query", "arguments": {"query": "x", "bogus": 1}}']
    )
    _, args = select_operation(client, _arxiv(), _subtask(), model="m")
    assert args == {"query": "x"}  # "bogus" is not a request_field -> dropped


def test_select_keeps_all_args_when_no_request_fields(fake_llm: MakeLLM) -> None:
    op = AppOperation(
        name="noargs",
        description="d",
        method="POST",
        path="/x",
        timeout_s=30,
        destructive=False,
        idempotency="none",
        retry=RetrySpec(0, 0.0),
    )
    app = AppEntry("custom", "Custom", "d", (), (), False, port=8099, health="/h", operations=(op,))
    client = fake_llm(['{"operation": "noargs", "arguments": {"anything": 1}}'])
    _, args = select_operation(client, app, _subtask(), model="m")
    assert args == {"anything": 1}


def test_select_unknown_operation_raises(fake_llm: MakeLLM) -> None:
    client = fake_llm(['{"operation": "does_not_exist", "arguments": {}}'])
    with pytest.raises(SelectionError, match="has no operation"):
        select_operation(client, _arxiv(), _subtask(), model="m", max_retries=0)


def test_select_bad_json_raises(fake_llm: MakeLLM) -> None:
    client = fake_llm(["not json at all"])
    with pytest.raises(SelectionError, match="not valid JSON"):
        select_operation(client, _arxiv(), _subtask(), model="m", max_retries=0)


def test_select_non_object_raises(fake_llm: MakeLLM) -> None:
    client = fake_llm(["[1, 2, 3]"])
    with pytest.raises(SelectionError, match="must be a JSON object"):
        select_operation(client, _arxiv(), _subtask(), model="m", max_retries=0)


def test_select_missing_operation_name_raises(fake_llm: MakeLLM) -> None:
    client = fake_llm(['{"arguments": {"query": "x"}}'])
    with pytest.raises(SelectionError, match="missing a valid 'operation'"):
        select_operation(client, _arxiv(), _subtask(), model="m", max_retries=0)


def test_select_bad_arguments_type_raises(fake_llm: MakeLLM) -> None:
    client = fake_llm(['{"operation": "search_papers_by_query", "arguments": "nope"}'])
    with pytest.raises(SelectionError, match="'arguments' must be an object"):
        select_operation(client, _arxiv(), _subtask(), model="m", max_retries=0)


# --- defaults: fill a missing request field so the chosen app is usable ------


def _op_with_defaults() -> tuple[AppEntry, str]:
    op = AppOperation(
        name="ask",
        description="d",
        method="POST",
        path="/ask",
        timeout_s=30,
        destructive=False,
        idempotency="none",
        request_fields=("question", "module_id"),
        defaults={"module_id": 1},
    )
    app = AppEntry("custom", "Custom", "d", (), (), False, port=8099, health="/h", operations=(op,))
    return app, "ask"


def test_select_applies_defaults(fake_llm: MakeLLM) -> None:
    app, _ = _op_with_defaults()
    client = fake_llm(['{"operation": "ask", "arguments": {"question": "q"}}'])  # module_id omitted
    _, args = select_operation(client, app, _subtask(), model="m")
    assert args == {"question": "q", "module_id": 1}  # default filled the missing field


def test_select_defaults_do_not_override_model(fake_llm: MakeLLM) -> None:
    app, _ = _op_with_defaults()
    client = fake_llm(['{"operation": "ask", "arguments": {"question": "q", "module_id": 7}}'])
    _, args = select_operation(client, app, _subtask(), model="m")
    assert args["module_id"] == 7  # model-supplied value wins over the default


# --- retry on malformed JSON (self-correction, mirrors the planner) ----------


def test_select_retries_then_succeeds(fake_llm: MakeLLM) -> None:
    # first reply is invalid JSON (a raw newline inside a string value); the retry recovers
    bad = '{"operation": "search_papers_by_query", "arguments": {"query": "line1\nline2"'
    good = '{"operation": "search_papers_by_query", "arguments": {"query": "moe"}}'
    client = fake_llm([bad, good])
    op, args = select_operation(client, _arxiv(), _subtask(), model="m", max_retries=1)
    assert op.name == "search_papers_by_query"
    assert args == {"query": "moe"}
    assert len(client.requests) == 2  # it took a second attempt
    assert "invalid" in client.requests[1].messages[-1]["content"]  # error fed back to the model


def test_select_exhausts_retries(fake_llm: MakeLLM) -> None:
    client = fake_llm(["nope", "still bad"])  # 2 responses = 2 attempts (max_retries=1)
    with pytest.raises(SelectionError, match="not valid JSON"):
        select_operation(client, _arxiv(), _subtask(), model="m", max_retries=1)
    assert len(client.requests) == 2  # both attempts consumed, original error re-raised


# --- data flow between steps (Task 1: upstream results reach the selector) ---


def test_message_has_no_upstream_section_when_none() -> None:
    # backward compatible: without dependencies, no UPSTREAM block is emitted
    message = build_select_message(_arxiv(), _subtask())
    assert "UPSTREAM" not in message


def test_message_includes_upstream_list_with_ids() -> None:
    # a downstream step must be able to see the arxiv_id an earlier step returned
    upstream = (_upstream_result([{"arxiv_id": "2401.12345", "title": "MoE paper"}]),)
    message = build_select_message(_arxiv(), _subtask(), upstream)
    assert "UPSTREAM RESULTS" in message
    assert "[t1]" in message  # provenance: which step produced it
    assert "2401.12345" in message  # the concrete id survives the summary


def test_upstream_output_is_truncated_when_long() -> None:
    upstream = (_upstream_result("x" * 5000),)
    message = build_select_message(_arxiv(), _subtask(), upstream)
    assert "…" in message  # long output is bounded, not dumped whole


def test_select_can_use_upstream_id_as_argument(fake_llm: MakeLLM) -> None:
    # end-to-end through select_operation: the model picks the id it saw upstream
    upstream = (_upstream_result([{"arxiv_id": "2401.12345"}]),)
    client = fake_llm(['{"operation": "get_paper_by_id", "arguments": {"arxiv_id": "2401.12345"}}'])
    op, args = select_operation(client, _arxiv(), _subtask(), model="m", upstream=upstream)
    assert op.name == "get_paper_by_id"
    assert args == {"arxiv_id": "2401.12345"}
    assert "2401.12345" in client.requests[0].messages[0]["content"]


# --- schema-safety: the selector sees field TYPES and never sends a wrongly-typed value ---
# Root cause of the "legit blog task -> 422 -> web fallback" bug (live proof 2026-07-13:
# word_count_target: "short" against an integer field). The registry only knows field names;
# types come from the committed OpenAPI snapshots.


def _blogs() -> AppEntry:
    app = REG.get("blogs-playground")
    assert app is not None
    return app


def test_operations_view_includes_field_types() -> None:
    # The model must SEE "limit: integer" to fill it correctly — names alone caused the 422s.
    message = build_select_message(_blogs(), _blog_sub("Suggest", "suggest blog topics"))
    assert "limit: integer" in message


def test_numeric_string_coerced(fake_llm: MakeLLM) -> None:
    # "5" for an integer field is safely convertible — coerce, don't punish.
    client = fake_llm(['{"operation": "suggest_topics", "arguments": {"limit": "5"}}'])
    op, args = select_operation(client, _blogs(), _blog_sub("Suggest", "suggest topics"), model="m")
    assert op.name == "suggest_topics"
    assert args == {"limit": 5}


def test_wrong_type_optional_dropped(fake_llm: MakeLLM) -> None:
    # An uncoercible value for an OPTIONAL typed field is dropped, so the app applies its own
    # default instead of 422-ing the whole call into web fallback.
    client = fake_llm(['{"operation": "suggest_topics", "arguments": {"limit": "many"}}'])
    op, args = select_operation(client, _blogs(), _blog_sub("Suggest", "suggest topics"), model="m")
    assert op.name == "suggest_topics"
    assert "limit" not in args


def test_wrong_type_required_dropped_causes_skip(fake_llm: MakeLLM) -> None:
    # An uncoercible REQUIRED field is dropped too: the executor's missing-required skip then
    # fires with an honest reason — an honest skip beats a garbage call every time.
    client = fake_llm(
        [
            '{"operation": "post_blog_restore", '
            '"arguments": {"blog_id": "b1", "version_num": "two"}}'
        ]
    )
    op, args = select_operation(
        client, _blogs(), _blog_sub("Restore", "restore version"), model="m"
    )
    assert op.name == "post_blog_restore"
    assert "version_num" not in args  # dropped -> executor skips instead of 422
    assert args["blog_id"] == "b1"


def _op_with_floor() -> AppEntry:
    op = AppOperation(
        name="search",
        description="d",
        method="POST",
        path="/search",
        timeout_s=30,
        destructive=False,
        idempotency="none",
        request_fields=("query", "max_results"),
        arg_min={"max_results": 5},
    )
    return AppEntry(
        "custom", "Custom", "d", (), (), False, port=8099, health="/h", operations=(op,)
    )


def test_enforce_arg_floors_raises_undersized_keeps_larger() -> None:
    op = _op_with_floor().operations[0]
    a = {"query": "x", "max_results": 1}
    _enforce_arg_floors(op, a)
    assert a["max_results"] == 5  # under-set 1 raised to the floor
    b = {"query": "x", "max_results": 20}
    _enforce_arg_floors(op, b)
    assert b["max_results"] == 20  # larger explicit value untouched


def test_enforce_arg_floors_ignores_bools_and_omitted() -> None:
    op = _op_with_floor().operations[0]
    a = {"query": "x"}  # max_results omitted -> left alone (app default applies)
    _enforce_arg_floors(op, a)
    assert "max_results" not in a
    b = {"query": "x", "max_results": True}  # bool is not a count
    _enforce_arg_floors(op, b)
    assert b["max_results"] is True


def test_select_clamps_undersized_count(fake_llm: MakeLLM) -> None:
    # The model reads "some papers" as max_results=1; the floor raises it so search isn't starved.
    app = _op_with_floor()
    client = fake_llm(['{"operation": "search", "arguments": {"query": "clt", "max_results": 1}}'])
    _, args = select_operation(client, app, _subtask(), model="m")
    assert args["max_results"] == 5
