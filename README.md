# awesome-skills

Reusable skills for agent workflows.

## Structure

Skills live under `skills/<skill-name>/`.

## Included Skills

### `writing-prd`

A skill for writing product requirement documents that:

- fills missing context with explicit assumptions
- separates product requirements from implementation details
- requires measurable metrics and acceptance criteria
- supports Chinese Word export with a bundled HTML template

Files:

- `skills/writing-prd/SKILL.md`
- `skills/writing-prd/prd-template-zh.html`
- `skills/writing-prd/example-prd-zh.md`

### `contract-to-interface`

A coding-stage workflow that:

- fetches an authoritative interface contract through a configured MCP tool
- persists and validates the contract locally
- invokes an existing CLI generator in the configured service directory
- compiles the owning service as the completion gate
- keeps environment-specific MCP, path, generator, and build details as documented placeholders

Files:

- `skills/contract-to-interface/SKILL.md`
- `skills/contract-to-interface/references/integration-config.md`
- `skills/contract-to-interface/references/integration-config.json`
- `skills/contract-to-interface/references/servicecomb-interface-patterns.md`
- `skills/contract-to-interface/references/servicecomb-contract-policy.json`
- `skills/contract-to-interface/references/commit-enforcement.md`
- `skills/contract-to-interface/scripts/check_integration_config.py`
- `skills/contract-to-interface/scripts/check_servicecomb_contract_code.py`
- `skills/contract-to-interface/scripts/test_check_servicecomb_contract_code.py`
