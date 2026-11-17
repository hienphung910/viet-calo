from django.contrib.auth.views import LogoutView
from django.urls import include, path

from app.controllers import accounts, diary, recognition

accounts_urls = ([
    path("register/", accounts.register, name="register"),
    path("login/", accounts.EmailLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
], "accounts")

recognition_urls = ([
    path("scan/", recognition.scan_upload, name="upload"),
    path("scan/<str:token>/", recognition.scan_confirm, name="confirm"),
    path("api/predict/", recognition.api_predict, name="api_predict"),
    path("recognition/reload/", recognition.reload_model, name="reload"),
], "recognition")

diary_urls = ([
    path("", diary.home, name="home"),
    path("week/", diary.week, name="week"),
    path("meals/add/", diary.meal_add, name="meal_add"),
    path("meals/<int:pk>/edit/", diary.meal_edit, name="meal_edit"),
    path("meals/<int:pk>/delete/", diary.meal_delete, name="meal_delete"),
], "diary")

urlpatterns = [
    path("accounts/", include(accounts_urls)),
    path("", include(recognition_urls)),
    path("", include(diary_urls)),
]
