"""Tool schemas: the descriptions and parameter contracts Hermes reads."""

SAFETY_NOTE = (
    "Read-only review only. This tool never places or cancels an order, never "
    "connects to a broker, and never returns financial advice. Its output is "
    "evidence for a human to review. Filesystem writes are limited to the "
    "configured run_root where explicitly stated. The plugin makes no network "
    "requests and opens no database; controlled core operations may use the "
    "human-configured state_dir PermissionStore, and host runtime caches may be "
    "written. The core capability protocol and PermissionStore remain authoritative "
    "for controlled operations. "
    "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"
)

DOCTOR = {
    "name": "smcub_doctor",
    "description": (
        "Report local SmartMoney-Cub harness health: package version, Python, and "
        "the read-only safety declaration. Use this to check whether the smcub CLI "
        "is installed and working before relying on the other SmartMoney-Cub tools. "
        + SAFETY_NOTE
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

VALIDATE_ENVELOPE = {
    "name": "smcub_validate_envelope",
    "description": (
        "Validate a SmartMoney-Cub run envelope JSON file against the published "
        "schema and contract. Use this after a run has been captured to confirm the "
        "artifact is well formed and its declared permission scope is intact. "
        + SAFETY_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "envelope_path": {
                "type": "string",
                "description": "Path to a run_envelope.json file to validate.",
            },
        },
        "required": ["envelope_path"],
    },
}

BUILD_EVIDENCE_PACK = {
    "name": "smcub_build_evidence_pack",
    "description": (
        "Build a frozen, hashed evidence pack from a run directory plus delayed "
        "outcome data. The pack is the artifact a human reviews. SmartMoney-Cub "
        "creates the evidence pack in output_dir. Use this when the user wants a "
        "reproducible record of a completed review run. "
        + SAFETY_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "run_dir": {
                "type": "string",
                "description": "Run directory produced by capture-run/loop.",
            },
            "output_dir": {
                "type": "string",
                "description": "Required directory below configured run_root where the pack will be created.",
            },
            "rule_candidate": {
                "type": "string",
                "description": "Required existing JSON rule candidate below configured run_root.",
            },
            "horizon": {
                "type": "string",
                "enum": ["d1", "d3"],
                "default": "d1",
                "description": "Outcome horizon to include in the pack.",
            },
        },
        "required": ["run_dir", "output_dir", "rule_candidate"],
    },
}

REPLAY_EVIDENCE_PACK = {
    "name": "smcub_replay_evidence_pack",
    "description": (
        "Verify an evidence pack: recompute validation, evaluation, and metrics "
        "and compare against the recorded hashes. Use this to check that a pack has "
        "not been altered and that its results reproduce. "
        + SAFETY_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "pack_dir": {
                "type": "string",
                "description": "Directory containing the evidence pack to replay.",
            },
        },
        "required": ["pack_dir"],
    },
}

EVALUATE_RUN = {
    "name": "smcub_evaluate_run",
    "description": (
        "Evaluate one run directory against its recorded outcome. SmartMoney-Cub "
        "writes eval.json in the run directory. Use this to grade a single "
        "decision record after outcome data exists. A grade is a review artifact, "
        "not a trading instruction. "
        + SAFETY_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "run_dir": {
                "type": "string",
                "description": "Run directory to evaluate.",
            },
            "horizon": {
                "type": "string",
                "enum": ["d1", "d3"],
                "default": "d1",
                "description": "Outcome horizon to read.",
            },
        },
        "required": ["run_dir"],
    },
}

INSPECT_ARTIFACTS = {
    "name": "smcub_inspect_artifacts",
    "description": (
        "Inspect a run directory and report its promotion readiness and sample "
        "count. Use this before presenting a run for human review, to avoid "
        "over-reading a small sample. "
        + SAFETY_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "run_dir": {
                "type": "string",
                "description": "Run directory to inspect.",
            },
        },
        "required": ["run_dir"],
    },
}

CAPABILITIES = {
    "name": "smcub_capabilities",
    "description": (
        "Ask the local SmartMoney-Cub CLI for its machine-readable operation "
        "catalog. The plugin accepts only cli.capabilities.v1 with protocol_version "
        "1, filters forbidden or networked operations, and never exposes secrets. "
        + SAFETY_NOTE
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

OPERATION = {
    "name": "smcub_operation",
    "description": (
        "Run one operation explicitly advertised by smcub capabilities. The JSON "
        "input must be an existing file below the human-configured run_root. The "
        "plugin supplies principal=hermes, state_dir, run_root, and --json; Hermes "
        "cannot select those roots or grant permissions. permissions.request is a "
        "proposal-only operation and approval remains with the human or core "
        "PermissionStore. "
        + SAFETY_NOTE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "Exact operation name returned by smcub_capabilities.",
            },
            "input_path": {
                "type": "string",
                "description": "Existing JSON request file below the configured run_root.",
            },
        },
        "required": ["operation", "input_path"],
    },
}

ALL_SCHEMAS = [
    DOCTOR,
    VALIDATE_ENVELOPE,
    BUILD_EVIDENCE_PACK,
    REPLAY_EVIDENCE_PACK,
    EVALUATE_RUN,
    INSPECT_ARTIFACTS,
    CAPABILITIES,
    OPERATION,
]
