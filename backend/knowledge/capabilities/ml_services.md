---
name: "ml_services_capabilities"
type: "capability"
agent: "ml-services-1"
updated_at: "2026-06-11T00:00:00+00:00"
---

# ml-services-1 Capabilities

Consolidates the former classify-1, forecaster-1, and llm-factory-1 agents
(feature 029). Historical per-service statistics below were recorded under the
predecessor agent ids; the five verbs the training services shared now carry
service prefixes (`classify_submit_dataset`, `forecaster_submit_dataset`, …).

## CLASSify (formerly classify-1)

Overall: 2 calls, 0.0% success rate

### Tools

- **get_ml_options**: 0.0% success (1 calls)
- **train_classifier**: 0.0% success (1 calls)

## Forecaster (formerly forecaster-1)

Overall: 1 calls, 0.0% success rate

### Tools

- **train_forecaster**: 0.0% success (1 calls)

## LLM-Factory (formerly llm-factory-1)

Overall: 3 calls, 66.7% success rate

### Tools

- **list_models**: 50.0% success (2 calls)
- **chat_with_model**: 100.0% success (1 calls)
