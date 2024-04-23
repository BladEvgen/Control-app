from django.urls import path
from rest_framework_simplejwt.views import (
    TokenVerifyView,
    TokenRefreshView,
    TokenObtainPairView,
)

from monitoring_app import views
from monitoring_app.swagger import urlpatterns as doc_urls

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("upload/", views.UploadFileView.as_view(), name="uploadFile"),
    path("user/register/", views.user_register, name="userRegister"),
    path(
        "attendance/stats/",
        views.StaffAttendanceStatsView.as_view(),
        name="staff-attendance-stats",
    ),
    path("api/token/", TokenObtainPairView.as_view()),
    path("api/token/refresh/", TokenRefreshView.as_view()),
    path("api/token/verify/", TokenVerifyView.as_view()),
]

urlpatterns += doc_urls
