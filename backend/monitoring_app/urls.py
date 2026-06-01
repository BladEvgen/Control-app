from django.urls import path, re_path
from django.views.generic import RedirectView
from monitoring_app import custom_jwt, face_lab_tts, views
from monitoring_app.swagger import urlpatterns as doc_urls
from monitoring_app.swagger_views import swagger_session_login, swagger_session_logout

urlpatterns = [
    path("", RedirectView.as_view(url="/app/")),
    re_path(
        r"^(?P<asset_dir>mediapipe|mediapipe-models)/(?P<asset_path>.+)$",
        views.frontend_public_asset,
        name="frontend-public-asset",
    ),
    path("login_view/", views.login_view, name="login_view"),
    path("logout/", views.logout_view, name="logout"),
    path("upload/", views.UploadFileView.as_view(), name="uploadFile"),
    path("fetcher/", views.fetch_data_view, name="fetcher"),
    path("api/app-version/", views.app_version, name="app-version"),
    path(
        "api/attendance/stats/",
        views.StaffAttendanceStatsView.as_view(),
        name="staff-attendance-stats",
    ),
    path(
        "api/attendance/department-confirmation/",
        views.department_attendance_confirmation,
        name="department-attendance-confirmation",
    ),
    path(
        "api/attendance/suspicious-location-patterns/",
        views.suspicious_location_patterns,
        name="suspicious-location-patterns",
    ),
    path(
        "api/attendance/write/lesson/",
        views.create_signed_lesson_attendance,
        name="attendance-write-lesson",
    ),
    path(
        "api/attendance/write/staff/",
        views.upsert_signed_staff_attendance,
        name="attendance-write-staff",
    ),
    path("api/locations", views.map_location, name="locations"),
    path("api/lesson_locations/", views.lesson_locations, name="lesson_locations"),
    path(
        "api/classlocation/",
        views.class_location_list_create,
        name="class_location_list_create",
    ),
    path(
        "api/classlocation/bulk/",
        views.class_location_bulk_update,
        name="class_location_bulk_update",
    ),
    path(
        "api/classlocation/<int:pk>/",
        views.class_location_detail,
        name="class_location_detail",
    ),
    path(
        "api/lesson_attendance/",
        views.create_lesson_attendance,
        name="create_lesson_attendance",
    ),
    path(
        "api/lesson_attendance/json/",
        views.create_lesson_attendance_json,
        name="create_lesson_attendance_json",
    ),
    path(
        "api/lesson_attendance/<int:id>/",
        views.update_lesson_attendance,
        name="update_lesson_attendance",
    ),
    path(
        "api/lesson_attendance/photo_verdicts/",
        views.lesson_attendance_photo_verdicts,
        name="lesson_attendance_photo_verdicts",
    ),
    path(
        "api/lesson_attendance/<int:attendance_id>/photo_verdict/",
        views.lesson_attendance_photo_verdicts,
        name="lesson_attendance_photo_verdict_single",
    ),
    path(
        "api/lesson_attendance/task_status/<str:task_id>/",
        views.check_lesson_task_status,
        name="check_lesson_task_status",
    ),
    path(
        "api/child_department/<str:child_department_id>/",
        views.child_department_detail,
        name="child-department-detail",
    ),
    path(
        "api/department/stats/<str:department_id>/",
        views.staff_detail_by_department_id,
        name="department-stats",
    ),
    path(
        "api/department/<str:parent_department_id>/",
        views.department_summary,
        name="department-summary",
    ),
    path(
        "api/reports/building-attendance.xlsx",
        views.download_building_attendance_report,
        name="building-attendance-report",
    ),
    path("api/download/<str:department_id>/", views.sent_excel, name="sent_excel"),
    path("api/key_check/", views.APIKeyCheckView.as_view(), name="api_key_check"),
    path("api/parent_department_id/", views.get_parent_id, name="get-parent-ids"),
    path(
        "api/departments/root/",
        views.root_departments_batch,
        name="root-departments-batch",
    ),
    path(
        "api/staff/<str:staff_pin>/avatar/",
        views.staff_avatar_upload,
        name="staff-avatar-upload",
    ),
    path("api/staff/<str:staff_pin>/", views.staff_detail, name="staff-detail"),
    path(
        "api/token/",
        custom_jwt.CustomTokenObtainPairView.as_view(),
        name="token_obtain_pair",
    ),
    path(
        "api/token/refresh/",
        custom_jwt.CustomTokenRefreshView.as_view(),
        name="token_refresh",
    ),
    path(
        "api/token/verify/",
        custom_jwt.CustomTokenVerifyView.as_view(),
    ),
    path("api/user/register/", views.user_register, name="userRegister"),
    path(
        "password-reset/",
        views.password_reset_request_view,
        name="password_reset_request",
    ),
    path(
        "password-reset/<str:token>/",
        views.password_reset_confirm_view,
        name="password_reset_confirm",
    ),
    path(
        "api/face-lab/departments/",
        views.face_lab_departments,
        name="face-lab-departments",
    ),
    path(
        "api/face-lab/staff-options/",
        views.face_lab_staff_options,
        name="face-lab-staff-options",
    ),
    path(
        "api/face-lab/pad-test/",
        views.face_lab_pad_test,
        name="face-lab-pad-test",
    ),
    path(
        "api/face-lab/bootstrap-status/",
        views.face_lab_bootstrap_status,
        name="face-lab-bootstrap-status",
    ),
    path(
        "api/face-lab/save-face-sample/",
        views.face_lab_save_face_sample,
        name="face-lab-save-face-sample",
    ),
    path(
        "api/face-lab/apply-sample-avatar/",
        views.face_lab_apply_sample_avatar,
        name="face-lab-apply-sample-avatar",
    ),
    path(
        "api/face-lab/tts/",
        face_lab_tts.face_lab_tts_view,
        name="face-lab-tts",
    ),
    path("verify-face/", views.verify_face, name="verify-face"),
    path("recognize-faces/", views.recognize_faces, name="recognize-faces"),
    path(
        "download/examples/", views.download_examples_zip, name="download_examples_zip"
    ),
    path(
        "attendance_media/<path:path>",
        views.serve_attendance_media,
        name="attendance-media",
    ),
    path("api/absent_staff/", views.AbsentReasonView.as_view(), name="absent_staff"),
    path("api/swagger-login/", swagger_session_login, name="swagger_session_login"),
    path("api/swagger-logout/", swagger_session_logout, name="swagger_session_logout"),
]

urlpatterns += doc_urls

urlpatterns += [
    re_path(r"^app/.*$", views.react_app, name="react_app"),
]
