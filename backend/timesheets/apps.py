from django.apps import AppConfig


class TimesheetsConfig(AppConfig):
    name = "timesheets"
    verbose_name = "Consuntivi"

    def ready(self) -> None:
        from timesheets import signals  # noqa: F401
