---
name: "ml_services_techniques"
type: "technique"
agent: "ml-services-1"
created_at: "2026-05-12T01:15:08+00:00"
updated_at: "2026-06-18T05:23:08+00:00"
synthesis_count: 5
interaction_count: 15
confidence: 0.575
---

### Effective Patterns
*   **Dataset Preparation & Configuration**: Tools related to data ingestion and setup (`classify_submit_dataset`, `set_column_types`, `propose_training_config`) show a **100% success rate** across 9 total calls.
*   **Post-Training Retrieval**: Monitoring and result extraction (`classify_get_job_status`, `classify_get_results`) are consistently successful (100%).

### Anti-Patterns
*   **Training Job Initiation**: The `classify_start_training_job` tool is a high-failure point.
    *   **Failure Rate**: 50%
    *   **Sample Size**: 4 calls
    *   **Pattern**: Attempting to pass a `list` type into a parameter expecting a hashable type (e.g., string or integer).

### Error Recovery
*   **Error**: `unhashable type: 'list'`
*   **Root Cause**: The agent is passing a list object to a tool argument that likely requires a unique identifier or a single value.
*   **Avoidance**: Implement a validation step before calling `classify_start_training_job` to ensure all arguments are flattened or converted from lists to the expected scalar types.

### Recommended Tool Sequences
Based on the toolset, the following logical pipeline is supported by the success data:
`classify_submit_dataset` $\rightarrow$ `set_column_types` $\rightarrow$ `propose_training_config` $\rightarrow$ `classify_start_training_job` $\rightarrow$ `classify_get_job_status` $\rightarrow$ `classify_get_results`.

### Statistics Summary

| Tool | Calls | Success Rate | Primary Error |
| :--- | :---: | :---: | :--- |
| `set_column_types` | 5 | 100% | N/A |
| `classify_start_training_job` | 4 | 50% | `unhashable type: 'list'` |
| `classify_submit_dataset` | 2 | 100% | N/A |
| `propose_training_config` | 2 | 100% | N/A |
| `classify_get_job_status` | 1 | 100% | N/A |
| `classify_get_results` | 1 | 100% | N/A |
