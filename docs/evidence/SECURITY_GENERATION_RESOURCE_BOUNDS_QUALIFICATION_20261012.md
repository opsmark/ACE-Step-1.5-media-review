# Generation resource boundary qualification — 2026-10-12

Status: SOURCE_TESTED / RED_TEAM_REQUALIFIED / STACKED_ON_PR_1 / DRAFT / UNMERGED / UNDEPLOYED

Base revision: 1bb0cf9d1356c9153459e4572210c6a6b2d8d963
Initial green qualification: GitHub Actions run 38218516390
Red-team requalification: GitHub Actions run 38218899974
Python: 3.11.17

## Candidate boundary

The candidate bounds declared and chunked generation bodies before FastAPI/Pydantic route parsing, rejects conflicting Content-Length framing, normalizes a single trailing slash for protected generation routes, rejects over-budget text/base64 before temporary files or model work, intersects duration and batch size with the active GPU tier and absolute ceilings, caps inference steps, seed fan-out, custom timesteps and track-class collections, and constrains the custom Gradio generation payload.

Streaming and non-streaming OpenRouter jobs receive the same bounded deadline. Timeout and disconnect cancellation are terminal in the job store, cannot be overwritten by later exception/progress paths, skip work that has not reached model initialization, and are rechecked after initialization and from generation progress callbacks. Core duration and batch-size checks remain as defense in depth.

## Preserved negative evidence and corrections

- Run 38217731578 exposed invalid workflow YAML before any source candidate was promoted.
- Run 38217812125 exposed an incomplete parser-transform count.
- Run 38217948420 passed the new focused policy tests but failed two parent worker-loop tests because the first integration assumed every test store implemented cancellation.
- Run 38218075738 exposed a faulty repair-script target before source transformation.
- Run 38218439703 passed 56 of 57 checks; its sole failure was a test-harness error that accidentally configured the supposedly unrelated path as protected.
- Run 38218516390 passed 57 of 57 checks and sealed the first source candidate.
- Post-seal red-team review found that cancellation was checked after model initialization, a later failure could overwrite the cancellation reason, duplicate Content-Length values were collapsed, and a trailing slash could miss the exact-path body limit. This requalification repairs and tests those cases rather than relabeling the first candidate as final.

## Focused and parent test output

```text
/opt/hostedtoolcache/Python/3.11.17/x64/lib/python3.11/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
  from starlette.testclient import TestClient as TestClient  # noqa
test_16_cancelled_job_cannot_be_promoted_to_success (acestep.api.generation_resource_policy_test.CancellationAndSourceIntegrationTests.test_16_cancelled_job_cannot_be_promoted_to_success) ... ok
test_17_expired_deadline_is_observed_by_worker_thread (acestep.api.generation_resource_policy_test.CancellationAndSourceIntegrationTests.test_17_expired_deadline_is_observed_by_worker_thread) ... ok
test_18_queue_worker_skips_cancelled_queued_job (acestep.api.generation_resource_policy_test.CancellationAndSourceIntegrationTests.test_18_queue_worker_skips_cancelled_queued_job) ... ok
test_19_stream_timeout_requests_job_cancellation (acestep.api.generation_resource_policy_test.CancellationAndSourceIntegrationTests.test_19_stream_timeout_requests_job_cancellation) ... /home/runner/work/ACE-Step-1.5-media-review/ACE-Step-1.5-media-review/acestep/openrouter_models.py:71: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.14/migration/
  class ChatCompletionRequest(BaseModel):
ok
test_20_pydantic_request_models_declare_hard_caps (acestep.api.generation_resource_policy_test.CancellationAndSourceIntegrationTests.test_20_pydantic_request_models_declare_hard_caps) ... /home/runner/work/ACE-Step-1.5-media-review/ACE-Step-1.5-media-review/acestep/api/http/release_task_models.py:13: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.14/migration/
  class GenerateMusicRequest(BaseModel):
/opt/hostedtoolcache/Python/3.11.17/x64/lib/python3.11/site-packages/pydantic/_internal/_config.py:408: UserWarning: Valid config keys have changed in V2:
* 'allow_population_by_field_name' has been renamed to 'validate_by_name'
  warnings.warn(message, UserWarning)
ok
test_21_core_duration_allocator_has_defense_in_depth_cap (acestep.api.generation_resource_policy_test.CancellationAndSourceIntegrationTests.test_21_core_duration_allocator_has_defense_in_depth_cap) ... ok
test_22_openrouter_reads_bounded_body_before_model_parse (acestep.api.generation_resource_policy_test.CancellationAndSourceIntegrationTests.test_22_openrouter_reads_bounded_body_before_model_parse) ... ok
test_23_custom_api_uses_bounded_reader_and_validates_work (acestep.api.generation_resource_policy_test.CancellationAndSourceIntegrationTests.test_23_custom_api_uses_bounded_reader_and_validates_work) ... ok
test_24_worker_and_blocking_runtime_check_cancellation (acestep.api.generation_resource_policy_test.CancellationAndSourceIntegrationTests.test_24_worker_and_blocking_runtime_check_cancellation) ... ok
test_25_limit_environment_cannot_raise_hard_ceiling (acestep.api.generation_resource_policy_test.CancellationAndSourceIntegrationTests.test_25_limit_environment_cannot_raise_hard_ceiling) ... ok
test_01_declared_oversize_body_is_rejected_before_stream (acestep.api.generation_resource_policy_test.GenerationResourcePolicyTests.test_01_declared_oversize_body_is_rejected_before_stream) ... ok
test_02_chunked_oversize_body_is_rejected_during_read (acestep.api.generation_resource_policy_test.GenerationResourcePolicyTests.test_02_chunked_oversize_body_is_rejected_during_read) ... ok
test_03_bounded_json_object_is_parsed (acestep.api.generation_resource_policy_test.GenerationResourcePolicyTests.test_03_bounded_json_object_is_parsed) ... ok
test_04_json_array_is_not_accepted_as_request_object (acestep.api.generation_resource_policy_test.GenerationResourcePolicyTests.test_04_json_array_is_not_accepted_as_request_object) ... ok
test_05_invalid_base64_is_rejected (acestep.api.generation_resource_policy_test.GenerationResourcePolicyTests.test_05_invalid_base64_is_rejected) ... ok
test_06_audio_format_is_allowlisted (acestep.api.generation_resource_policy_test.GenerationResourcePolicyTests.test_06_audio_format_is_allowlisted) ... ok
test_07_decoded_audio_byte_limit_is_enforced (acestep.api.generation_resource_policy_test.GenerationResourcePolicyTests.test_07_decoded_audio_byte_limit_is_enforced) ... ok
test_08_hardware_and_absolute_work_limits_intersect (acestep.api.generation_resource_policy_test.GenerationResourcePolicyTests.test_08_hardware_and_absolute_work_limits_intersect) ... ok
test_09_duration_batch_and_steps_over_limits_are_rejected (acestep.api.generation_resource_policy_test.GenerationResourcePolicyTests.test_09_duration_batch_and_steps_over_limits_are_rejected) ... ok
test_10_nonfinite_and_fractional_work_values_are_rejected (acestep.api.generation_resource_policy_test.GenerationResourcePolicyTests.test_10_nonfinite_and_fractional_work_values_are_rejected) ... ok
test_11_seed_count_and_task_enum_are_bounded (acestep.api.generation_resource_policy_test.GenerationResourcePolicyTests.test_11_seed_count_and_task_enum_are_bounded) ... ok
test_12_text_and_audio_code_budgets_are_enforced (acestep.api.generation_resource_policy_test.GenerationResourcePolicyTests.test_12_text_and_audio_code_budgets_are_enforced) ... ok
test_13_task_query_and_param_object_counts_are_bounded (acestep.api.generation_resource_policy_test.GenerationResourcePolicyTests.test_13_task_query_and_param_object_counts_are_bounded) ... ok
test_14_openrouter_combined_audio_budget_is_enforced (acestep.api.generation_resource_policy_test.GenerationResourcePolicyTests.test_14_openrouter_combined_audio_budget_is_enforced) ... ok
test_15_openrouter_unknown_content_type_is_rejected (acestep.api.generation_resource_policy_test.GenerationResourcePolicyTests.test_15_openrouter_unknown_content_type_is_rejected) ... ok
test_deadline_during_initialization_skips_generation (acestep.api.generation_resource_policy_test.StickyCancellationRedTeamTests.test_deadline_during_initialization_skips_generation) ... ok
test_mark_failed_cannot_replace_cancellation_reason (acestep.api.generation_resource_policy_test.StickyCancellationRedTeamTests.test_mark_failed_cannot_replace_cancellation_reason) ... ok
test_pre_cancelled_job_does_not_initialize_models (acestep.api.generation_resource_policy_test.StickyCancellationRedTeamTests.test_pre_cancelled_job_does_not_initialize_models) ... ok
test_progress_cannot_reopen_or_relabel_cancelled_job (acestep.api.generation_resource_policy_test.StickyCancellationRedTeamTests.test_progress_cannot_reopen_or_relabel_cancelled_job) ... ok
test_08_normal_request_passes_hardware_intersection (acestep.api.generation_resource_middleware_test.ExtendedReleaseTaskTests.test_08_normal_request_passes_hardware_intersection) ... ok
test_09_timesteps_text_is_bounded (acestep.api.generation_resource_middleware_test.ExtendedReleaseTaskTests.test_09_timesteps_text_is_bounded) ... ok
test_10_track_class_count_is_bounded (acestep.api.generation_resource_middleware_test.ExtendedReleaseTaskTests.test_10_track_class_count_is_bounded) ... ok
test_11_each_track_class_is_bounded (acestep.api.generation_resource_middleware_test.ExtendedReleaseTaskTests.test_11_each_track_class_is_bounded) ... ok
test_12_release_task_work_is_intersected_with_hardware (acestep.api.generation_resource_middleware_test.ExtendedReleaseTaskTests.test_12_release_task_work_is_intersected_with_hardware) ... ok
test_13_route_setup_installs_body_limit_before_registration (acestep.api.generation_resource_middleware_test.ExtendedReleaseTaskTests.test_13_route_setup_installs_body_limit_before_registration) ... ok
test_14_release_task_validates_before_store_create (acestep.api.generation_resource_middleware_test.ExtendedReleaseTaskTests.test_14_release_task_validates_before_store_create) ... ok
test_15_path_caps_are_serializable_for_receipts (acestep.api.generation_resource_middleware_test.ExtendedReleaseTaskTests.test_15_path_caps_are_serializable_for_receipts) ... ok
test_01_declared_oversize_is_rejected_before_app (acestep.api.generation_resource_middleware_test.RequestBodyLimitTests.test_01_declared_oversize_is_rejected_before_app) ... ok
test_02_invalid_content_length_is_rejected (acestep.api.generation_resource_middleware_test.RequestBodyLimitTests.test_02_invalid_content_length_is_rejected) ... ok
test_03_negative_content_length_is_rejected (acestep.api.generation_resource_middleware_test.RequestBodyLimitTests.test_03_negative_content_length_is_rejected) ... ok
test_04_chunked_oversize_is_rejected_before_route_completion (acestep.api.generation_resource_middleware_test.RequestBodyLimitTests.test_04_chunked_oversize_is_rejected_before_route_completion) ... ok
test_05_body_at_limit_reaches_app_unchanged (acestep.api.generation_resource_middleware_test.RequestBodyLimitTests.test_05_body_at_limit_reaches_app_unchanged) ... ok
test_06_non_target_path_is_not_consumed_or_rejected (acestep.api.generation_resource_middleware_test.RequestBodyLimitTests.test_06_non_target_path_is_not_consumed_or_rejected) ... ok
test_07_all_network_generation_paths_have_explicit_caps (acestep.api.generation_resource_middleware_test.RequestBodyLimitTests.test_07_all_network_generation_paths_have_explicit_caps) ... ok
test_conflicting_duplicate_content_lengths_are_rejected (acestep.api.generation_resource_middleware_test.RequestFramingRedTeamTests.test_conflicting_duplicate_content_lengths_are_rejected) ... ok
test_trailing_slash_cannot_bypass_path_limit (acestep.api.generation_resource_middleware_test.RequestFramingRedTeamTests.test_trailing_slash_cannot_bypass_path_limit) ... ok
test_dependency_protects_router_without_protecting_unrelated_route (acestep.api.http.authenticated_router_test.TestAuthenticatedRouter.test_dependency_protects_router_without_protecting_unrelated_route) ... ok
test_api_key_is_visible_when_fresh_app_is_created (acestep.api.server_cli_test.ServerCliTests.test_api_key_is_visible_when_fresh_app_is_created) ... ok
test_loopback_detection (acestep.api.server_cli_test.ServerCliTests.test_loopback_detection) ... ok
test_loopback_without_key_remains_supported (acestep.api.server_cli_test.ServerCliTests.test_loopback_without_key_remains_supported) ... ok
test_remote_bind_without_key_is_rejected_before_app_creation (acestep.api.server_cli_test.ServerCliTests.test_remote_bind_without_key_is_rejected_before_app_creation) ... usage: python -m unittest [-h] [--host HOST] [--port PORT] [--api-key API_KEY]
                          [--download-source {huggingface,modelscope,auto}]
                          [--init-llm] [--lm-model-path LM_MODEL_PATH]
                          [--no-init]
python -m unittest: error: Refusing to bind an unauthenticated API beyond loopback. Set --api-key (or ACESTEP_API_KEY) or bind to 127.0.0.1/::1/localhost.
ok
test_run_api_server_main_invokes_uvicorn_with_parsed_host_port (acestep.api.server_cli_test.ServerCliTests.test_run_api_server_main_invokes_uvicorn_with_parsed_host_port)
CLI helper should pass parsed host/port and fixed worker settings to uvicorn. ... ok
test_run_api_server_main_sets_env_overrides_from_flags (acestep.api.server_cli_test.ServerCliTests.test_run_api_server_main_sets_env_overrides_from_flags)
CLI helper should apply legacy env side effects for supported flags. ... ok
test_run_api_server_main_uses_env_bool_for_flag_defaults (acestep.api.server_cli_test.ServerCliTests.test_run_api_server_main_uses_env_bool_for_flag_defaults)
CLI helper should respect env_bool-provided defaults when flags omitted. ... ok
test_append_jsonl_writes_one_json_line_per_record (acestep.api.jobs.store_test.JobStorePersistenceTests.test_append_jsonl_writes_one_json_line_per_record)
JSONL append should serialize each record with a newline terminator. ... ok
test_atomic_write_json_uses_atomic_replace_flow (acestep.api.jobs.store_test.JobStorePersistenceTests.test_atomic_write_json_uses_atomic_replace_flow)
Atomic write should write+flush+fsync and then replace target path. ... ok
test_cleanup_old_jobs_removes_only_completed_jobs (acestep.api.jobs.store_test.JobStoreTests.test_cleanup_old_jobs_removes_only_completed_jobs)
Cleanup should remove stale finished jobs while preserving queued jobs. ... ok
test_create_mark_running_mark_succeeded_updates_state (acestep.api.jobs.store_test.JobStoreTests.test_create_mark_running_mark_succeeded_updates_state)
Store should transition job state through queued->running->succeeded. ... ok
test_update_progress_clamps_values_and_ignores_missing_jobs (acestep.api.jobs.store_test.JobStoreTests.test_update_progress_clamps_values_and_ignores_missing_jobs)
Progress updates should clamp to [0,1] and no-op for unknown IDs. ... ok
test_process_queue_item_failure_marks_failed_and_notifies_error (acestep.api.jobs.worker_loops_test.WorkerLoopTests.test_process_queue_item_failure_marks_failed_and_notifies_error)
Failure path should mark failed, emit error+done, and perform cleanup. ... ok
test_process_queue_item_success_notifies_result_and_done (acestep.api.jobs.worker_loops_test.WorkerLoopTests.test_process_queue_item_success_notifies_result_and_done)
Success path should emit result+done and cleanup queue bookkeeping. ... ok
test_run_job_store_cleanup_loop_logs_cleanup_and_stops_on_cancel (acestep.api.jobs.worker_loops_test.WorkerLoopTests.test_run_job_store_cleanup_loop_logs_cleanup_and_stops_on_cancel)
Cleanup loop should log cleanup stats and exit on cancellation. ... ok
test_run_job_store_cleanup_loop_logs_errors_and_continues (acestep.api.jobs.worker_loops_test.WorkerLoopTests.test_run_job_store_cleanup_loop_logs_errors_and_continues)
Cleanup loop should log non-cancel exceptions and continue until cancelled. ... ok

----------------------------------------------------------------------
Ran 63 tests in 0.171s

OK
Using preferred download source: huggingface
[API Server] LLM initialization enabled via --init-llm
[API Server] Using LM model: acestep-5Hz-lm-0.6B
[API Server] --no-init: Models will NOT be loaded at startup (lazy load on first request)
[API Server] LLM initialization enabled via --init-llm
```

## Important limits

This is an isolated source candidate. It does not merge or deploy either this branch or PR 1, close the scanner finding, load a real model, exercise a GPU, prove Windows/ASGI-server behavior, impose per-principal rate quotas, or hard-stop a native kernel that never returns or invokes a progress callback. Cooperative cancellation prevents late success publication and stops at the next checked boundary; it is not an operating-system process kill. Audio decompression-bomb handling, media retention/session isolation, authentication-before-body-read and downstream proxy limits remain separately owned findings or layers.

The 64 MiB request ceiling is a hard maximum; environment configuration may only tighten it. Compatibility should be reviewed for clients that require more than two input audio parts, unusually long lyrics/audio codes/custom timesteps, more than 64 track classes, batch size above 8, or more than 200 inference steps.

## Receiving gate

1. Land/rebase after PR 1 authentication and rerun the full suite on the declared Windows/Python environment.
2. Exercise JSON, urlencoded and multipart ingress with Content-Length, duplicate/conflicting headers, trailing slashes and chunked bodies immediately below/above each limit.
3. Generate a normal short track, a supported long track, cover/repaint inputs, streaming output, a disconnected stream, a queued deadline and a deadline during model initialization using real local weights.
4. Confirm over-limit requests fail before temp-file creation, audio decode, queue admission, model selection or GPU allocation.
5. Confirm timed-out running work stops at the next cooperative progress boundary and cannot overwrite the failed terminal state even when the executor later returns.
6. Inventory legitimate clients affected by the tightened factors before merge and document any reviewed migration; do not widen a hard cap merely to preserve an unknown caller.
7. Preserve the prior installed source and do not close the finding until both embedded OpenRouter and custom Gradio routes are deployed and retested on the target host.
