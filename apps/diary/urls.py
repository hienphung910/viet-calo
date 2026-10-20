from django.urls import path

from . import views

app_name = "diary"

urlpatterns = [
    path("", views.home, name="home"),                       # ?date=YYYY-MM-DD
    path("week/", views.week, name="week"),                  # ?start=YYYY-MM-DD
    path("meals/add/", views.meal_add, name="meal_add"),
    path("meals/<int:pk>/edit/", views.meal_edit, name="meal_edit"),
    path("meals/<int:pk>/delete/", views.meal_delete, name="meal_delete"),
]
