"""A review of recorded quotes and unresolved terms, using the common report template."""

from .supervision import build_human_review


def document(artifact):
    case = artifact.get("procurement_case") or {}
    review = artifact.get("human_review") or build_human_review(artifact)
    evidence = artifact.get("evidence") or {}
    sections = [{"id": "assessment", "title": "Assessment", "blocks": [
        {"type": "paragraph", "text": artifact["executive_summary"]},
        {"type": "paragraph", "text": review["prompt"]},
        {"type": "paragraph", "text": review["why_now"]}]}]
    if case.get("mode") == "MOCK":
        sections[0]["blocks"].insert(0, {"type": "warning", "text": "Simulation with fictional suppliers and prices."})
    if case:
        quotes = case.get("quote_outcomes") or []
        rows = []
        for quote in quotes:
            cost = quote.get("cost") or {}
            subtotal = cost.get("known_cost_over_comparison_horizon")
            rows.append([quote.get("supplier_name") or quote["supplier_id"],
                         "Comparable" if quote.get("comparable") else str(quote.get("outcome") or "Unverified").replace("_", " ").lower(),
                         f"{cost.get('currency', '')} {subtotal}".strip() if subtotal is not None else "Not quoted",
                         ", ".join(quote.get("evidence_refs") or []) or "No source recorded"])
        evidence_blocks = [{"type": "table", "columns": ["Supplier", "Quote status", "Known horizon cost", "Source reference"],
                            "rows": rows, "caption": "Quote outcomes in approval-packet.json"}] if rows else [
                                {"type": "paragraph", "text": "The saved case contains no evaluated quotes."}]
    else:
        sources = evidence.get("public_sources") or []
        evidence_blocks = [{"type": "table", "columns": ["Source", "Recorded status"], "rows": [
            [str(s.get("source_ref") or s.get("url") or "Unspecified"), str(s.get("status") or "Not recorded")]
            for s in sources[:40]], "caption": f"Showing up to 40 of {len(sources)} records in research_sources.json."}] if sources else [
                {"type": "paragraph", "text": "No public sources were recorded. Review the local evidence in evidence.json."}]
        comparisons = artifact.get("candidate_comparisons") or []
        if comparisons:
            evidence_blocks.append({"type": "table", "columns": ["Option", "Vendor", "Observed", "Known three-year cost"],
                                    "rows": [[str(c.get("candidate_id") or "Unspecified"), c.get("vendor"),
                                              c.get("observed_at"), c.get("known_three_year_cost")] for c in comparisons[:40]]})
    sections.append({"id": "evidence", "title": "Evidence", "blocks": evidence_blocks})
    gaps = [x for x in (case.get("limitations") or artifact.get("evidence_gaps") or []) if isinstance(x, str)]
    sections.append({"id": "coverage", "title": "Coverage and next review", "blocks": [
        *({"type": "paragraph", "text": item} for item in gaps[:16]),
        {"type": "paragraph", "text": review["next_step"]},
        {"type": "paragraph", "text": "Check source dates and unquoted terms before committing funds. This saved assessment cannot authorize a purchase."}]})
    return {"title": "Purchase review", "identity": case.get("as_of") or "Saved purchase evidence", "sections": sections}

def publish(block, final):
    import json
    from mn_sdk.blueprint.hooks import fingerprint, report_activity
    from mn_sdk.blueprint.outputs import publish_artifact_bundle
    from mn_sdk_common.publication import ArtifactWrite

    try:
        from mn_web_report_skill import render_report_html
        from mn_sdk_web_ui import static_run_report_handle

        page = publish_artifact_bundle(block, [
            ArtifactWrite("web_report", "web/index.html", lambda: render_report_html(document(final)).encode(),
                          kind="html", required=False, revision=fingerprint(final), mode=0o644),
        ], receipt_path=block.root + "/purchase-preview.json")
        if page["warnings"] or page["delivery_warnings"]:
            raise OSError("Purchase review unavailable")
        handle = static_run_report_handle(block.store.run_dir, "web/index.html", title="Purchase review")
        receipt = publish_artifact_bundle(block, [
            ArtifactWrite("web_ui", "web_ui.json", json.dumps(handle).encode(), kind="json", required=False, mode=0o644),
        ], receipt_path=block.root + "/purchase-preview-handle.json")
        if receipt["warnings"] or receipt["delivery_warnings"]:
            raise OSError("Purchase review handle unavailable")
    except Exception:
        block.check()
        report_activity("The purchase packet was saved. The web report could not be published.",
                        kind="diagnostic", level="warning", step_id=block.step_id, run_dir=block.store.run_dir)
