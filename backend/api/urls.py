"""Routing dell'API v1.

In Fase 1 sono attivi autenticazione, impostazioni e le viste calcolate di dominio.
I ViewSet CRUD completi arrivano con le fasi successive e si agganciano a questo router.
"""

from __future__ import annotations

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from api import auth_views, domain_views

router = DefaultRouter()

urlpatterns = [
    path("auth/login", auth_views.LoginView.as_view(), name="login"),
    path("auth/logout", auth_views.LogoutView.as_view(), name="logout"),
    path("auth/session", auth_views.SessionView.as_view(), name="session"),
    path("settings", domain_views.SettingsView.as_view(), name="settings"),
    path("search", domain_views.CommandSearchView.as_view(), name="command-search"),
    path("checks/run", domain_views.ChecksRunView.as_view(), name="checks-run"),
    path("anomalies", domain_views.AnomalyListView.as_view(), name="anomaly-list"),
    path(
        "anomalies/<uuid:pk>/<str:action>",
        domain_views.AnomalyActionView.as_view(),
        name="anomaly-action",
    ),
    path("projects", domain_views.ProjectListCreateView.as_view(), name="project-list-create"),
    path("projects/balances", domain_views.ProjectBalancesView.as_view(), name="project-balances"),
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
    path("canoni", domain_views.CanoneListView.as_view(), name="canone-list"),
    path("canoni/<uuid:pk>/status", domain_views.CanoneStatusView.as_view(), name="canone-status"),
    path(
        "reconciliation/latest",
        domain_views.ReconciliationView.as_view(),
        name="reconciliation-latest",
    ),
    path("schema", SpectacularAPIView.as_view(), name="schema"),
    path("docs", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("", include(router.urls)),
]
