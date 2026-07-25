#!/usr/bin/env python3
"""
End-to-End Demo Pipeline for Arcus PR Review System.

Demonstrates the complete Front B pipeline:
1. Load sample PR envelope
2. Execute analysis agents in sequence
3. Display comprehensive report
4. Save enriched envelope
"""

import json
import logging
import sys
from pathlib import Path
from unittest.mock import patch

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Add src to path for imports
arcus_root = Path(__file__).parent.parent
sys.path.insert(0, str(arcus_root / "src"))

# Import contracts first
from arcus.contracts import PipelineEnvelope


def load_sample_envelope() -> PipelineEnvelope:
    """Load the sample envelope from fixtures."""
    fixture_path = arcus_root / "tests" / "fixtures" / "envelope_sample.json"
    logger.info(f"Loading sample envelope from {fixture_path}")

    with open(fixture_path) as f:
        envelope_data = json.load(f)

    envelope = PipelineEnvelope.model_validate(envelope_data)
    logger.info(f"Loaded envelope for PR {envelope.pr.repo_full_name}#{envelope.pr.pr_number}")

    return envelope


# Import agents AFTER path setup
from arcus.agents.context_builder import handle_context_builder
from arcus.agents.consistency_checker import handle_consistency_checker
from arcus.agents.bug_hunter import handle_bug_hunter
from arcus.agents.fix_suggester import handle_fix_suggester
from arcus.agents.reporter import handle_reporter


def run_pipeline(envelope: PipelineEnvelope) -> PipelineEnvelope:
    """
    Execute the complete Front B pipeline.

    Args:
        envelope: Initial PipelineEnvelope

    Returns:
        Enriched envelope after all agents
    """
    logger.info("=" * 80)
    logger.info("FRONT B PIPELINE EXECUTION")
    logger.info("=" * 80)

    # Mock the invoke_claude function with side_effect for sequential calls
    mock_responses = [
        "[]",  # context_builder - no consistency issues
        json.dumps([
            {
                "file": "src/main.py",
                "line_start": 42,
                "line_end": 45,
                "title": "Function naming inconsistency",
                "rationale": "Function uses camelCase but convention is snake_case",
                "severity": "medium",
                "type": "convention_violation",
            }
        ]),  # consistency_checker
        json.dumps([
            {
                "file": "src/main.py",
                "line_start": 10,
                "line_end": 15,
                "title": "Potential null pointer dereference",
                "rationale": "Variable may be None but is used without check",
                "severity": "high",
                "type": "logic_bug",
                "suggested_fix": "Add None check before accessing variable",
            }
        ]),  # bug_hunter
        json.dumps([
            {
                "finding_id": "bug-0",
                "description": "Add None check",
                "suggested_diff": "if var is not None: use_var()",
                "confidence": "high",
            }
        ]),  # fix_suggester
    ]

    with patch("arcus.bedrock.client.invoke_claude") as mock_invoke:
        mock_invoke.side_effect = mock_responses

        # Step 1: Context Builder
        logger.info("\n[1/5] Running Context Builder (B4)...")
        context_result = handle_context_builder(envelope)  # type: ignore
        if isinstance(context_result, dict):
            envelope = PipelineEnvelope.model_validate(context_result)
        else:
            envelope = context_result
        logger.info(f"✓ Context Builder completed - Status: {envelope.context.status}")
        logger.info(f"  - Detected Naming: {envelope.context.conventions.naming if envelope.context.conventions else 'N/A'}")

        # Step 2: Consistency Checker
        logger.info("\n[2/5] Running Consistency Checker (B5)...")
        consistency_result = handle_consistency_checker(envelope)  # type: ignore
        if isinstance(consistency_result, dict):
            envelope = PipelineEnvelope.model_validate(consistency_result)
        else:
            envelope = consistency_result
        logger.info(f"✓ Consistency Checker completed - Status: {envelope.consistency.status}")
        logger.info(f"  - Findings: {len(envelope.consistency.findings) if envelope.consistency.findings else 0}")

        # Step 3: Bug Hunter
        logger.info("\n[3/5] Running Bug Hunter (B6)...")
        bugs_result = handle_bug_hunter(envelope)  # type: ignore
        if isinstance(bugs_result, dict):
            envelope = PipelineEnvelope.model_validate(bugs_result)
        else:
            envelope = bugs_result
        logger.info(f"✓ Bug Hunter completed - Status: {envelope.bugs.status}")
        logger.info(f"  - Findings: {len(envelope.bugs.findings) if envelope.bugs.findings else 0}")

        # Step 4: Fix Suggester
        logger.info("\n[4/5] Running Fix Suggester (B7)...")
        fixes_result = handle_fix_suggester(envelope)  # type: ignore
        if isinstance(fixes_result, dict):
            envelope = PipelineEnvelope.model_validate(fixes_result)
        else:
            envelope = fixes_result
        logger.info(f"✓ Fix Suggester completed - Status: {envelope.fixes.status}")
        logger.info(f"  - Findings with fixes: {sum(1 for f in envelope.fixes.findings if f and f.fix) if envelope.fixes.findings else 0}")

        # Step 5: Reporter (no Claude call needed)
        logger.info("\n[5/5] Running Reporter (B8)...")
        report_result = handle_reporter(envelope)  # type: ignore
        if isinstance(report_result, dict):
            envelope = PipelineEnvelope.model_validate(report_result)
        else:
            envelope = report_result
        logger.info(f"✓ Reporter completed - Status: {envelope.report.status}")

    return envelope


def print_report(envelope: PipelineEnvelope) -> None:
    """Print the generated report."""
    logger.info("\n" + "=" * 80)
    logger.info("GENERATED REPORT")
    logger.info("=" * 80)

    if envelope.report.summary:
        print("\n" + envelope.report.summary)
    else:
        logger.warning("No report summary generated")


def save_envelope(envelope: PipelineEnvelope) -> None:
    """Save the enriched envelope to fixtures."""
    output_path = arcus_root / "tests" / "fixtures" / "envelope_output_sample.json"
    logger.info(f"\nSaving enriched envelope to {output_path}")

    # Serialize envelope
    envelope_dict = envelope.model_dump(mode="json")

    with open(output_path, "w") as f:
        json.dump(envelope_dict, f, indent=2)

    logger.info(f"✓ Envelope saved successfully")
    logger.info(f"  - File size: {output_path.stat().st_size} bytes")


def print_summary(envelope: PipelineEnvelope) -> None:
    """Print execution summary."""
    logger.info("\n" + "=" * 80)
    logger.info("PIPELINE EXECUTION SUMMARY")
    logger.info("=" * 80)

    logger.info(f"\nPipeline Run: {envelope.pipeline_run_id}")
    logger.info(f"Repository: {envelope.pr.repo_full_name}")
    logger.info(f"PR #: {envelope.pr.pr_number}")
    logger.info(f"Commit: {envelope.pr.commit_sha}")

    logger.info(f"\nAgent Status:")
    logger.info(f"  Context Builder: {envelope.context.status}")
    logger.info(f"  Consistency Checker: {envelope.consistency.status}")
    logger.info(f"  Bug Hunter: {envelope.bugs.status}")
    logger.info(f"  Fix Suggester: {envelope.fixes.status}")
    logger.info(f"  Reporter: {envelope.report.status}")

    logger.info(f"\nFindings Summary:")
    consistency_count = len(envelope.consistency.findings) if envelope.consistency.findings else 0
    bug_count = len(envelope.bugs.findings) if envelope.bugs.findings else 0
    total_findings = consistency_count + bug_count

    logger.info(f"  Consistency Issues: {consistency_count}")
    logger.info(f"  Bugs/Security: {bug_count}")
    logger.info(f"  Total: {total_findings}")

    if envelope.fixes.findings:
        fixes_with_suggestions = sum(1 for f in envelope.fixes.findings if f and f.fix)
        logger.info(f"  Fixes Generated: {fixes_with_suggestions}/{len(envelope.fixes.findings)}")

    logger.info("\n✅ Pipeline execution completed successfully!")
    logger.info("=" * 80)


def main() -> None:
    """Main entry point."""
    try:
        # Load sample envelope
        envelope = load_sample_envelope()

        # Execute pipeline
        enriched_envelope = run_pipeline(envelope)

        # Print report
        print_report(enriched_envelope)

        # Save enriched envelope
        save_envelope(enriched_envelope)

        # Print summary
        print_summary(enriched_envelope)

        # Final validation
        logger.info("\nFinal Envelope Validation:")
        try:
            validated = PipelineEnvelope.model_validate(
                enriched_envelope.model_dump(mode="json")
            )
            logger.info("✓ Envelope passes Pydantic validation")
        except Exception as e:
            logger.error(f"✗ Envelope validation failed: {e}")
            return

        logger.info("\n🎉 Demo pipeline completed successfully!")

    except Exception as e:
        logger.error(f"Pipeline execution failed: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
