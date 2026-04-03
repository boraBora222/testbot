from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_readme_mentions_documents_rollout_checklist() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "documents_and_compliance_rollout_checklist.md" in readme
    assert "audit matrix" in readme
    assert "profile and deal documents" in readme


def test_rollout_checklist_covers_spec_sections_5_11_12_13_and_14() -> None:
    checklist = (
        REPO_ROOT / "docs" / "specifications" / "documents_and_compliance_rollout_checklist.md"
    ).read_text(encoding="utf-8")

    assert "sections `5`, `11`, `12`, `13`, and `14`" in checklist
    assert "S3/MinIO" in checklist
    assert "15 minutes" in checklist
    assert "Telegram bot" in checklist
    assert "dashboard" in checklist
    assert "happy-path" in checklist
    assert "Release Sign-Off" in checklist


def test_rollout_checklist_keeps_mvp_exclusions_and_storage_assumptions_visible() -> None:
    checklist = (
        REPO_ROOT / "docs" / "specifications" / "documents_and_compliance_rollout_checklist.md"
    ).read_text(encoding="utf-8")

    assert "No moderation flow is added in this release." in checklist
    assert "No PDF generation or template generation is introduced." in checklist
    assert "No EDI integration is introduced." in checklist
    assert "No document versioning is introduced beyond same-type replacement." in checklist
    assert "No separate `company` entity is introduced" in checklist
    assert "DOCUMENT_STORAGE_ENDPOINT" in checklist
    assert "DOCUMENT_STORAGE_PUBLIC_ENDPOINT" in checklist
    assert "private" in checklist
    assert "900" in checklist


def test_deal_detail_page_loads_document_rows_from_live_api() -> None:
    deal_page = (
        REPO_ROOT / "front" / "src" / "pages" / "dashboard" / "deals" / "[id].tsx"
    ).read_text(encoding="utf-8")

    assert "await dealService.listDocuments(id);" in deal_page
    assert "deal.documents" not in deal_page
