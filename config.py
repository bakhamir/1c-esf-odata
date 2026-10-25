"""Immutable business requirements for planning, not execution."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class BusinessRules:
    contract_label: str = "ALA-58/2025 SD"
    unit_label: str = "Усл"
    target_time: str = "10:00:00"
    tax_accounting: str = "НУ"
    cost_subconto_bu1: str = "Расходы по перелету"
    cost_subconto_bu3: str = "Основное подразделение"
    incoming_document_type: str = "Акт выполненных работ"

    def to_dict(self) -> dict:
        return asdict(self)
