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
    path("login_view/", views.login_view, name="login_view"),
    path("logout/", views.logout_view, name="logout"),
    path("upload/", views.UploadFileView.as_view(), name="uploadFile"),
    path("fetcher/", views.fetch_data_view, name="fetcher"),
    path("api/user/register/", views.user_register, name="userRegister"),
    path("api/user/detail/", views.user_profile_detail, name="user-detail"),
    path(
        "api/attendance/stats/",
        views.StaffAttendanceStatsView.as_view(),
        name="staff-attendance-stats",
    ),
    path(
        "api/department/<int:parent_department_id>/",
        views.department_summary,
        name="department-summary",
    ),
    path(
        "api/department/stats/<int:department_id>/",
        views.staff_detail_by_department_id,
        name="department-stats",
    ),
    path(
        "api/child_department/<int:child_department_id>/",
        views.child_department_detail,
        name="child-department-detail",
    ),
    path("api/staff/<str:staff_pin>/", views.staff_detail, name="staff-detail"),
    path("api/parent_department_id/", views.get_parent_id, name="get-parent-ids"),
    path("api/token/", TokenObtainPairView.as_view()),
    path("api/token/refresh/", TokenRefreshView.as_view()),
    path("api/token/verify/", TokenVerifyView.as_view()),
]

urlpatterns += doc_urls
