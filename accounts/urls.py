from django.urls import path
from .views import register_view, login_view, logout_view, otp_verify_view, resend_otp_view, profile_view

urlpatterns = [
    path('register/', register_view, name='register'),
    path('login/', login_view, name='login'),
    path('otp-verify/', otp_verify_view, name='otp_verify'),
    path('resend-otp/', resend_otp_view, name='resend_otp'),
    path('profile/', profile_view, name='profile'),
    path('logout/', logout_view, name='logout'),
]
