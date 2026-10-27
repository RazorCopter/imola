"""Routing dell'API v1.

In Fase 1 sono attivi autenticazione, impostazioni e le viste calcolate di dominio.
I ViewSet CRUD completi arrivano con le fasi successive e si agganciano a questo router.
"""

from __future__ import annotations

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from api import admin_views, auth_views, domain_views

router = DefaultRouter()

urlpatterns = [
    path("auth/login", auth_views.LoginView.as_view(), name="login"),
    path("auth/logout", auth_views.LogoutView.as_view(), name="logout"),
    path("auth/session", auth_views.SessionView.as_view(), name="session"),
    path("settings", domain_views.SettingsView.as_view(), name="settings"),
    path("cost-analysis", domain_views.CostAnalysisView.as_view(), name="cost-analysis"),
    path("admin/imports/seed", admin_views.SeedImportView.as_view(), name="admin-seed-import"),
    path("admin/imports/ppm", admin_views.PpmImportView.as_view(), name="admin-ppm-import"),
    path("admin/imports", admin_views.ImportHistoryView.as_view(), name="admin-import-history"),
    path(
        "admin/imports/<uuid:batch_id>/datasets",
        admin_views.WorkbookDatasetListView.as_view(),
        name="admin-workbook-datasets",
    ),
    path(
        "admin/imports/<uuid:batch_id>/datasets/<uuid:dataset_pk>",
        admin_views.WorkbookDatasetDetailView.as_view(),
        name="admin-workbook-dataset-detail",
    ),
    path("admin/users", admin_views.UserRolesView.as_view(), name="admin-users"),
    path(
        "admin/users/<int:pk>",
        admin_views.UserDetailView.as_view(),
        name="admin-user-detail",
    ),
    path(
        "admin/users/<int:pk>/password",
        admin_views.UserPasswordView.as_view(),
        name="admin-user-password",
    ),
    path(
        "admin/referents",
        admin_views.ReferentListCreateView.as_view(),
        name="admin-referents",
    ),
    path(
        "admin/referents/<uuid:pk>",
        admin_views.ReferentDetailView.as_view(),
        name="admin-referent-detail",
    ),
    path(
        "admin/roles/capabilities",
        admin_views.RoleCapabilitiesView.as_view(),
        name="admin-role-capabilities",
    ),
    path(
        "admin/reset-data",
        admin_views.AdminDataResetView.as_view(),
        name="admin-reset-data",
    ),
    path(
        "admin/reset-data/",
        admin_views.AdminDataResetView.as_view(),
        name="admin-reset-data-slash",
    ),
    path("dashboard", domain_views.DashboardView.as_view(), name="dashboard"),
    path("search", domain_views.CommandSearchView.as_view(), name="command-search"),
    path("checks/run", domain_views.ChecksRunView.as_view(), name="checks-run"),
    path("anomalies", domain_views.AnomalyListView.as_view(), name="anomaly-list"),
    path(
        "anomalies/<uuid:pk>/<str:action>",
        domain_views.AnomalyActionView.as_view(),
        name="anomaly-action",
    ),
    path("projects", domain_views.ProjectListCreateView.as_view(), name="project-list-create"),
    path(
        "projects/options",
        domain_views.ProjectFormOptionsView.as_view(),
        name="project-form-options",
    ),
    path("projects/balances", domain_views.ProjectBalancesView.as_view(), name="project-balances"),
    path(
        "projects/<uuid:pk>/ledger",
        domain_views.ProjectLedgerView.as_view(),
        name="project-ledger",
    ),
    path(
        "projects/<uuid:pk>/ledger/<uuid:entry_pk>",
        domain_views.ProjectTimesheetDetailView.as_view(),
        name="project-timesheet-detail",
    ),
    path(
        "projects/<uuid:pk>",
        domain_views.ProjectDetailUpdateView.as_view(),
        name="project-detail-update",
    ),
    path(
        "projects/<uuid:pk>/confirm-review",
        domain_views.ProjectConfirmReviewView.as_view(),
        name="project-confirm-review",
    ),
    path(
        "projects/<uuid:pk>/validate-closure",
        domain_views.ProjectValidateClosureView.as_view(),
        name="project-validate-closure",
    ),
    path(
        "wallet/allocations/<uuid:pk>",
        domain_views.WalletAllocationDetailUpdateView.as_view(),
        name="wallet-allocation-detail",
    ),
    path(
        "wallet/allocations/<uuid:pk>/",
        domain_views.WalletAllocationDetailUpdateView.as_view(),
        name="wallet-allocation-detail-slash",
    ),
    path(
        "allocations/<uuid:pk>",
        domain_views.WalletAllocationDetailUpdateView.as_view(),
        name="allocation-detail",
    ),
    path(
        "allocations/<uuid:pk>/",
        domain_views.WalletAllocationDetailUpdateView.as_view(),
        name="allocation-detail-slash",
    ),
    path(
        "allocations/<uuid:pk>/adjust",
        domain_views.WalletAllocationAdjustView.as_view(),
        name="allocation-adjust",
    ),
    path(
        "allocations",
        domain_views.WalletAllocationCreateView.as_view(),
        name="allocation-create",
    ),
    path(
        "allocations/",
        domain_views.WalletAllocationCreateView.as_view(),
        name="allocation-create-slash",
    ),
    path(
        "wallet/allocations",
        domain_views.WalletAllocationCreateView.as_view(),
        name="wallet-allocation-create",
    ),
    path(
        "wallet/allocations/",
        domain_views.WalletAllocationCreateView.as_view(),
        name="wallet-allocation-create-slash",
    ),
    path(
        "allocations/options",
        domain_views.WalletAllocationOptionsView.as_view(),
        name="allocation-options",
    ),
    path(
        "wallet/allocation-options",
        domain_views.WalletAllocationOptionsView.as_view(),
        name="wallet-allocation-options",
    ),
    path(
        "wallet/allocation-options/",
        domain_views.WalletAllocationOptionsView.as_view(),
        name="wallet-allocation-options-slash",
    ),
    path(
        "audit/<str:entity_type>/<uuid:pk>",
        domain_views.AuditHistoryView.as_view(),
        name="audit-history",
    ),
    path("imports/ppm", domain_views.PpmImportUploadView.as_view(), name="import-ppm-upload"),
    path(
        "review-queue",
        domain_views.ProjectReviewQueueView.as_view(),
        name="review-queue",
    ),
    path(
        "projects/<uuid:pk>/release-to-wallet",
        domain_views.ReleaseProjectToWalletView.as_view(),
        name="project-release-to-wallet",
    ),
    path(
        "wallet/<int:year>/balance",
        domain_views.WalletBalanceView.as_view(),
        name="wallet-balance",
    ),
    path("wallet/<int:year>/flow", domain_views.WalletFlowView.as_view(), name="wallet-flow"),
    path(
        "wallet/<int:year>/assignees",
        domain_views.WalletAssigneeSummaryView.as_view(),
        name="wallet-assignees",
    ),
    path("canoni", domain_views.CanoneListView.as_view(), name="canone-list"),
    path("canoni/", domain_views.CanoneListView.as_view(), name="canone-list-slash"),
    path("canoni/<uuid:pk>", domain_views.CanoneDetailView.as_view(), name="canone-detail"),
    path("canoni/<uuid:pk>/", domain_views.CanoneDetailView.as_view(), name="canone-detail-slash"),
    path(
        "canoni/<uuid:pk>/subactivities",
        domain_views.CanoneSubactivityListView.as_view(),
        name="canone-subactivity-list",
    ),
    path(
        "canoni/<uuid:pk>/subactivities/<uuid:subactivity_pk>",
        domain_views.CanoneSubactivityDetailView.as_view(),
        name="canone-subactivity-detail",
    ),
    path(
        "canoni/<uuid:pk>/subactivities/<uuid:subactivity_pk>/timesheets",
        domain_views.CanoneSubactivityTimesheetListView.as_view(),
        name="canone-subactivity-timesheet-list",
    ),
    path(
        "canoni/<uuid:pk>/subactivities/<uuid:subactivity_pk>/timesheets/<uuid:entry_pk>",
        domain_views.CanoneSubactivityTimesheetDetailView.as_view(),
        name="canone-subactivity-timesheet-detail",
    ),
    path("canoni/<uuid:pk>/status", domain_views.CanoneStatusView.as_view(), name="canone-status"),
    path(
        "reconciliation/latest",
        domain_views.ReconciliationView.as_view(),
        name="reconciliation-latest",
    ),
    path("export/json", domain_views.ExportJsonView.as_view(), name="export-json"),
    path("export/excel", domain_views.ExportExcelView.as_view(), name="export-excel"),
    path("export/csv/<str:entity>", domain_views.ExportCsvView.as_view(), name="export-csv"),
    path("schema", SpectacularAPIView.as_view(), name="schema"),
    path("docs", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("", include(router.urls)),
]
