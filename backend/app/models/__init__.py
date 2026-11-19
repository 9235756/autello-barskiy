"""Импорт всех моделей: Base.metadata должен знать каждую таблицу до create_all."""
from app.models.admin_settings import AdminSettings, AdminSettingsCRUD
from app.models.application import Application, ApplicationCRUD
from app.models.behavior_metrics import BehaviorMetrics, BehaviorMetricsCRUD

__all__ = [
    "AdminSettings",
    "AdminSettingsCRUD",
    "Application",
    "ApplicationCRUD",
    "BehaviorMetrics",
    "BehaviorMetricsCRUD",
]
