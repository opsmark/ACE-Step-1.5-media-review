# Generation resource boundary qualification — 2026-10-12

Status: SOURCE_TESTED / RED_TEAM_REQUALIFIED / ADMISSION_REQUALIFIED / STACKED_ON_PR_1 / DRAFT / UNMERGED / UNDEPLOYED

Base revision: 1bb0cf9d1356c9153459e4572210c6a6b2d8d963
First green qualification: GitHub Actions run 38218516390
Framing/cancellation red-team requalification: GitHub Actions run 38218899974
OpenRouter admission requalification: GitHub Actions run 38219548495
Python: 3.11.17

## Candidate boundary

The candidate bounds declared and chunked generation bodies before FastAPI/Pydantic route parsing; rejects conflicting Content-Length framing and trailing-slash bypasses; constrains text, base64 audio, custom timesteps, track classes, duration, batch size, inference steps and seed fan-out; and intersects absolute ceilings with the active hardware tier. The documented `-1` automatic-duration sentinel remains compatible while zero and every other explicit non-positive duration are rejected.

OpenRouter preprocessing is serialized per process before decode/file creation and cover-code conversion, then published atomically to the existing shared queue under the maintained pending/temp lock order. Full/racing queues, deadline setup errors, parser failures and cancellation before admission remove request-owned files, pending metadata and the exact unsubmitted job record. A started cover-conversion thread is shielded from request cancellation and awaited before cancellation propagates, preventing repeated disconnects from escaping the prequeue concurrency bound.

Streaming and non-streaming jobs share the same bounded deadline. Timeout/disconnect cancellation is terminal in the store, cannot be overwritten by later exception/progress paths, skips work cancelled before model initialization, and is rechecked after initialization and from progress callbacks. Core duration and batch-size checks remain defense in depth.

## Preserved negative evidence and corrections

- Run 38217731578: invalid workflow YAML; no source candidate promoted.
- Run 38217812125: incomplete parser-transform count.
- Run 38217948420: focused checks passed but parent worker tests exposed an assumption about minimal stores.
- Run 38218075738: faulty repair-script target.
- Run 38218439703: 56/57; a test harness accidentally protected its supposed unrelated path.
- Run 38218516390: 57/57 first green candidate.
- Post-green review found cancellation ordering/state and request-framing gaps; run 38218899974 requalified those repairs at 63/63.
- Post-PR review then found an explicit `-1` duration compatibility regression plus pre-admission temp-file/job leakage and unbounded concurrent cover conversion. This run qualifies those corrections rather than treating the earlier green state as final.

## Focused and parent test output

```text
/opt/hostedtoolcache/Python/3.11.17/x64/lib/python3.11/site-packages/pydantic/_internal/_config.py:408: UserWarning: Valid config keys have changed in V2:
* 'allow_population_by_field_name' has been renamed to 'validate_by_name'
  warnings.warn(message, UserWarning)
/opt/hostedtoolcache/Python/3.11.17/x64/lib/python3.11/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
  from starlette.testclient import TestClient as TestClient  # noqa
test_11_lifespan_installs_one_openrouter_prequeue_lock (acestep.api.openrouter_admission_test.AdmissionSourceIntegrationTests.test_11_lifespan_installs_one_openrouter_prequeue_lock) ... ok
test_12_prequeue_lock_precedes_audio_materialization_and_conversion (acestep.api.openrouter_admission_test.AdmissionSourceIntegrationTests.test_12_prequeue_lock_precedes_audio_materialization_and_conversion) ... ok
test_13_admission_uses_nonblocking_put_and_shared_lock_order (acestep.api.openrouter_admission_test.AdmissionSourceIntegrationTests.test_13_admission_uses_nonblocking_put_and_shared_lock_order) ... ok
test_08_documented_negative_one_auto_duration_is_preserved (acestep.api.openrouter_admission_test.DurationSentinelCompatibilityTests.test_08_documented_negative_one_auto_duration_is_preserved) ... ok
test_09_zero_and_other_negative_durations_are_rejected (acestep.api.openrouter_admission_test.DurationSentinelCompatibilityTests.test_09_zero_and_other_negative_durations_are_rejected) ... ok
test_10_positive_duration_ceiling_is_preserved (acestep.api.openrouter_admission_test.DurationSentinelCompatibilityTests.test_10_positive_duration_ceiling_is_preserved) ... ok
test_01_success_publishes_queue_and_metadata_together (acestep.api.openrouter_admission_test.OpenRouterAdmissionTests.test_01_success_publishes_queue_and_metadata_together) ... ok
test_02_nonstreaming_admission_sets_done_event (acestep.api.openrouter_admission_test.OpenRouterAdmissionTests.test_02_nonstreaming_admission_sets_done_event) ... ok
test_03_full_queue_rejects_before_record_and_cleans_file (acestep.api.openrouter_admission_test.OpenRouterAdmissionTests.test_03_full_queue_rejects_before_record_and_cleans_file) ... ok
test_04_put_nowait_race_rolls_back_every_side_effect (acestep.api.openrouter_admission_test.OpenRouterAdmissionTests.test_04_put_nowait_race_rolls_back_every_side_effect) ... ok
test_05_failure_after_record_creation_discards_record_and_file (acestep.api.openrouter_admission_test.OpenRouterAdmissionTests.test_05_failure_after_record_creation_discards_record_and_file) ... ok
test_06_cancelled_conversion_waits_for_started_thread (acestep.api.openrouter_admission_test.OpenRouterAdmissionTests.test_06_cancelled_conversion_waits_for_started_thread) ... ok
test_07_discard_unsubmitted_has_identity_and_state_guards (acestep.api.openrouter_admission_test.OpenRouterAdmissionTests.test_07_discard_unsubmitted_has_identity_and_state_guards) ... ok
test_16_cancelled_job_cannot_be_promoted_to_success (acestep.api.generation_resource_policy_test.CancellationAndSourceIntegrationTests.test_16_cancelled_job_cannot_be_promoted_to_success) ... ok
test_17_expired_deadline_is_observed_by_worker_thread (acestep.api.generation_resource_policy_test.CancellationAndSourceIntegrationTests.test_17_expired_deadline_is_observed_by_worker_thread) ... ok
test_18_queue_worker_skips_cancelled_queued_job (acestep.api.generation_resource_policy_test.CancellationAndSourceIntegrationTests.test_18_queue_worker_skips_cancelled_queued_job) ... ok
test_19_stream_timeout_requests_job_cancellation (acestep.api.generation_resource_policy_test.CancellationAndSourceIntegrationTests.test_19_stream_timeout_requests_job_cancellation) ... ok
test_20_pydantic_request_models_declare_hard_caps (acestep.api.generation_resource_policy_test.CancellationAndSourceIntegrationTests.test_20_pydantic_request_models_declare_hard_caps) ... ok
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
Ran 76 tests in 0.170s

OK
Using preferred download source: huggingface
[API Server] LLM initialization enabled via --init-llm
[API Server] Using LM model: acestep-5Hz-lm-0.6B
[API Server] --no-init: Models will NOT be loaded at startup (lazy load on first request)
[API Server] LLM initialization enabled via --init-llm
```

## Important limits

This remains an isolated source candidate. It does not merge or deploy this branch or PR 1, close the scanner finding, load a real model, exercise a GPU, prove Windows/ASGI/proxy behavior, impose per-principal rate quotas, or hard-stop a native kernel that never returns or invokes a progress callback. Cooperative cancellation prevents late success publication and stops at the next checked boundary; it is not an operating-system process kill.

The OpenRouter prequeue lock deliberately serializes cover-code conversion before admission. If that conversion itself hangs indefinitely, later OpenRouter preprocessing waits rather than creating unbounded conversion threads. Native/model-specific cancellation and timeout require target-runtime qualification. Audio decompression-bomb handling, media retention/session isolation, authentication-before-body-read and downstream proxy ceilings remain separately owned layers or findings.

The branch duplicates only the identity/state-guarded `discard_unsubmitted` primitive already proposed by PR 2 so OpenRouter can roll back its own unpublished jobs. Rebase after PR 2 should keep one identical primitive and its broader `/release_task` admission treatment.

## Receiving gate

1. Land/rebase after PR 1 authentication and reconcile the identical store primitive plus `/release_task` behavior from PR 2.
2. Run the full suite on the declared Windows/Python target, including actual ASGI server and proxy framing behavior.
3. Exercise JSON, urlencoded and multipart ingress immediately below/at/above limits, with conflicting lengths, chunked transfer and trailing slashes.
4. Generate normal short/long tracks, cover/repaint inputs, streaming output, client disconnects, a queue-full race, queued deadlines and a deadline during model initialization using trusted local weights.
5. Confirm every pre-admission failure leaves no request temp file, pending ID, temp registry entry or job record, and that admitted files survive until worker cleanup.
6. Confirm a cancelled cover conversion does not permit a second conversion to escape the one-at-a-time prequeue bound.
7. Inventory legitimate clients affected by the tightened contract, preserve installed-source rollback, and close the finding only after deployed runtime retest with actual receipts.
