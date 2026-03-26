"""CustomColumn + Case.extra_fields 模型測試。"""
from hcp_cms.data.models import Case, CustomColumn


class TestCustomColumnModel:
    def test_can_instantiate(self):
        col = CustomColumn(col_key="cx_1", col_label="測試欄", col_order=1)
        assert col.col_key == "cx_1"
        assert col.visible_in_list is True

class TestCaseExtraFields:
    def test_extra_fields_default_empty(self):
        case = Case(
            case_id="CS-2026-001", subject="主旨", status="處理中",
            priority="中", replied="否",
        )
        assert case.extra_fields == {}

    def test_extra_fields_independent_per_instance(self):
        c1 = Case(case_id="A", subject="s", status="s", priority="中", replied="否")
        c2 = Case(case_id="B", subject="s", status="s", priority="中", replied="否")
        c1.extra_fields["cx_1"] = "v1"
        assert "cx_1" not in c2.extra_fields
