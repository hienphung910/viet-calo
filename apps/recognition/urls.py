from django.urls import path

from . import views

app_name = "recognition"

urlpatterns = [
    path("scan/", views.scan_upload, name="upload"),
    path("scan/<str:token>/", views.scan_confirm, name="confirm"),
    path("api/predict/", views.api_predict, name="api_predict"),
    path("recognition/reload/", views.reload_model, name="reload"),
    path("recognition/stats/", views.model_stats, name="stats"),
]
