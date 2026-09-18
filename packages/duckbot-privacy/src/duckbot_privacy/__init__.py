"""Duckbot privacy gateway — rule layer.

Workstream B of the engineering handover. Detection, redaction and local restoration for
Hong Kong business documents, with a measured recall figure rather than an assurance.
"""

from . import hkid
from .detectors import (
    ALL_DETECTORS,
    Detection,
    Detector,
    detect_all,
    detect_br_number,
    detect_email,
    detect_hkid,
    detect_money,
    detect_person_name,
    detect_phone,
    propagate_known_values,
    resolve_overlaps,
)
from .gateway import SENSITIVITY_BY_ENTITY, PrivacyGateway, RedactionResult

__all__ = [
    "ALL_DETECTORS",
    "SENSITIVITY_BY_ENTITY",
    "Detection",
    "Detector",
    "PrivacyGateway",
    "RedactionResult",
    "detect_all",
    "detect_br_number",
    "detect_email",
    "detect_hkid",
    "detect_money",
    "detect_person_name",
    "detect_phone",
    "hkid",
    "propagate_known_values",
    "resolve_overlaps",
]
