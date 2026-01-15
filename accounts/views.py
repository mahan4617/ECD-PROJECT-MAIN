from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from .forms import RegisterForm, LoginForm
import random
from django.core.mail import send_mail
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
from storage.models import StoredFile
import json
from django.core.files.base import ContentFile
import base64
import cv2
import numpy as np


def _decode_image_data_url(data_url):
    try:
        header, data = data_url.split(',', 1)
        raw = base64.b64decode(data)
        arr = np.frombuffer(raw, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None


def _extract_face(image):
    if image is None:
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(60, 60))
    if len(faces) == 0:
        face = gray
    else:
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        face = gray[y:y + h, x:x + w]
    face = cv2.resize(face, (100, 100))
    face = face.astype("float32") / 255.0
    return face


def faces_match(stored_file, data_url, threshold=0.02):
    try:
        stored_file.open()
        raw = stored_file.read()
    except Exception:
        return False
    finally:
        try:
            stored_file.close()
        except Exception:
            pass
    arr = np.frombuffer(raw, np.uint8)
    stored = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    captured = _decode_image_data_url(data_url)
    stored_face = _extract_face(stored)
    captured_face = _extract_face(captured)
    if stored_face is None or captured_face is None:
        return False
    diff = np.mean((stored_face - captured_face) ** 2)
    return diff < threshold


def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            face_data = request.POST.get('face_image_data') or ''
            if face_data.startswith('data:image'):
                try:
                    header, data = face_data.split(',', 1)
                    raw = base64.b64decode(data)
                    filename = f"user_{user.id}_face.png"
                    user.profile.face_image.save(filename, ContentFile(raw), save=True)
                except Exception:
                    pass
            return redirect('login')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})

def login_view(request):
    mode = 'password'
    if request.method == 'POST':
        mode = request.POST.get('login_mode', 'password')
        if mode == 'password':
            form = LoginForm(request.POST)
            if form.is_valid():
                user = form.cleaned_data['user']
                otp = str(random.randint(100000, 999999))
                user.profile.otp_code = otp
                user.profile.save()
                try:
                    print(f"DEBUG: EMAIL_HOST={settings.EMAIL_HOST}, PORT={settings.EMAIL_PORT}")
                    print(f"Sending OTP to {user.email}...")
                    email_message = f"""Hello {user.username},

Your One-Time Password (OTP) is: {otp}

This OTP is valid for 5 minutes.
Do not share this OTP with anyone.

Regards,
ECD Project Team."""
                    send_mail(
                        'Your OTP Code',
                        email_message,
                        settings.DEFAULT_FROM_EMAIL,
                        [user.email],
                        fail_silently=False,
                    )
                    print("Email sent successfully.")
                    messages.success(request, f'OTP sent to {user.email}')
                except Exception as e:
                    print(f"Error sending email: {e}")
                    messages.error(request, f"Error sending email: {e}")
                request.session['pre_mfa_user_id'] = user.id
                return redirect('otp_verify')
        else:
            form = LoginForm()
            username = request.POST.get('username') or ''
            email = request.POST.get('email') or ''
            face_login_data = request.POST.get('face_login_data') or ''
            if not username or not email or not face_login_data:
                messages.error(request, 'Username, email, and face capture are required for face login.')
                return render(request, 'accounts/login.html', {'form': form, 'login_mode': 'face'})
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                messages.error(request, 'No account found with that username.')
                return render(request, 'accounts/login.html', {'form': form, 'login_mode': 'face'})
            if user.email != email:
                messages.error(request, 'Email does not match this username.')
                return render(request, 'accounts/login.html', {'form': form, 'login_mode': 'face'})
            if not user.profile.face_image:
                messages.error(request, 'This account does not have a registered face. Use password login.')
                return render(request, 'accounts/login.html', {'form': form, 'login_mode': 'face'})
            if not faces_match(user.profile.face_image, face_login_data):
                messages.error(request, 'Face not recognized. Try again or use password login.')
                return render(request, 'accounts/login.html', {'form': form, 'login_mode': 'face'})
            otp = str(random.randint(100000, 999999))
            user.profile.otp_code = otp
            user.profile.save()
            try:
                print(f"DEBUG: EMAIL_HOST={settings.EMAIL_HOST}, PORT={settings.EMAIL_PORT}")
                print(f"Sending OTP to {user.email}...")
                email_message = f"""Hello {user.username},

Your One-Time Password (OTP) is: {otp}

This OTP is valid for 5 minutes.
Do not share this OTP with anyone.

Regards,
ECD Project Team."""
                send_mail(
                    'Your OTP Code',
                    email_message,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                )
                print("Email sent successfully.")
                messages.success(request, f'OTP sent to {user.email}')
            except Exception as e:
                print(f"Error sending email: {e}")
                messages.error(request, f"Error sending email: {e}")
            request.session['pre_mfa_user_id'] = user.id
            return redirect('otp_verify')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form, 'login_mode': mode})

def otp_verify_view(request):
    user_id = request.session.get('pre_mfa_user_id')
    if not user_id:
        return redirect('login')
    
    if request.method == 'POST':
        otp = request.POST.get('otp')
        try:
            user = User.objects.get(id=user_id)
            if user.profile.otp_code == otp:
                login(request, user)
                if 'pre_mfa_user_id' in request.session:
                    del request.session['pre_mfa_user_id']
                user.profile.otp_code = None 
                user.profile.save()
                return redirect('dashboard')
            else:
                messages.error(request, 'Invalid OTP')
        except User.DoesNotExist:
            return redirect('login')
            
    return render(request, 'accounts/otp_verify.html')

def resend_otp_view(request):
    user_id = request.session.get('pre_mfa_user_id')
    if not user_id:
        return redirect('login')
    
    try:
        user = User.objects.get(id=user_id)
        
        # Generate new OTP
        otp = str(random.randint(100000, 999999))
        user.profile.otp_code = otp
        user.profile.save()
        
        # Send Email
        try:
            print(f"DEBUG: EMAIL_HOST={settings.EMAIL_HOST}, PORT={settings.EMAIL_PORT}")
            email_message = f"""Hello {user.username},

Your One-Time Password (OTP) is: {otp}

This OTP is valid for 5 minutes.
Do not share this OTP with anyone.

Regards,
ECD Project Team."""

            send_mail(
                'Your OTP Code',
                email_message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
            messages.success(request, f'New OTP sent to {user.email}')
        except Exception as e:
            messages.error(request, f"Error sending email: {e}")
            
    except User.DoesNotExist:
        return redirect('login')
        
    return redirect('otp_verify')

@login_required
def profile_view(request):
    files = StoredFile.objects.filter(user=request.user)
    labels = ["PDF","ZIP","PPTX","DOCX","XLSX","TXT","PNG","JPG","Other"]
    counts_map = {k: 0 for k in labels}
    for f in files:
        name = (f.original_name or "").lower()
        if ".pdf" in name:
            counts_map["PDF"] += 1
        elif ".zip" in name:
            counts_map["ZIP"] += 1
        elif ".pptx" in name:
            counts_map["PPTX"] += 1
        elif ".docx" in name:
            counts_map["DOCX"] += 1
        elif ".xlsx" in name:
            counts_map["XLSX"] += 1
        elif ".txt" in name:
            counts_map["TXT"] += 1
        elif ".png" in name:
            counts_map["PNG"] += 1
        elif ".jpg" in name or ".jpeg" in name:
            counts_map["JPG"] += 1
        else:
            counts_map["Other"] += 1
    counts = [counts_map[l] for l in labels]
    return render(request, 'accounts/profile.html', {
        'chart_labels': labels,
        'chart_counts': counts,
        'labels_json': json.dumps(labels),
        'counts_json': json.dumps(counts),
    })

@login_required
def logout_view(request):
    logout(request)
    return redirect('/accounts/login/')
