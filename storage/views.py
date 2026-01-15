from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .forms import UploadForm
from .models import StoredFile
from .utils import aes_encrypt, aes_decrypt, hide_data_in_image, extract_data_from_image
from django.core.files.base import ContentFile
from django.contrib import messages
from accounts.views import faces_match
import io

def landing_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html')

@login_required
def dashboard_view(request):
    files = StoredFile.objects.filter(user=request.user).order_by('-created_at')
    recent_files = list(files[:5])
    total_files = files.count()
    last_login = request.user.last_login
    ctx = {
        'recent_files': recent_files,
        'total_files': total_files,
        'last_login': last_login,
    }
    return render(request, 'storage/dashboard.html', ctx)

@login_required
def file_list_view(request):
    files = StoredFile.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'storage/file_list.html', {'files': files})

@login_required
def history_view(request):
    files = StoredFile.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'storage/history.html', {'files': files})

@login_required
def upload_view(request):
    if request.method == 'POST':
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            up_file = form.cleaned_data['file']
            cover = form.cleaned_data['cover_image']
            data = up_file.read()
            ct, nonce = aes_encrypt(request.user.id, data)
            # ensure cover content is available for both PIL and model save
            if hasattr(cover, 'temporary_file_path'):
                cover_path = cover.temporary_file_path()
            else:
                cover.seek(0)
                cover_buf = io.BytesIO(cover.read())
                cover_path = cover_buf
                cover.seek(0)
            stego_img = hide_data_in_image(cover_path, ct)
            output = io.BytesIO()
            stego_img.save(output, format='PNG')
            output.seek(0)
            stego_content = ContentFile(output.read(), name=f"{up_file.name}.png")
            obj = StoredFile.objects.create(
                user=request.user,
                original_name=up_file.name,
                cover_image=cover,
                stego_image=stego_content,
                nonce=nonce,
                data_length=len(ct),
            )
            messages.success(request, f'Your file "{up_file.name}" was uploaded successfully.')
            request.session['last_uploaded_filename'] = up_file.name
            return redirect('upload')
    else:
        form = UploadForm()
    last_uploaded = request.session.pop('last_uploaded_filename', None)
    return render(request, 'storage/upload.html', {'form': form, 'last_uploaded_filename': last_uploaded})

@login_required
def download_view(request, pk: int):
    obj = get_object_or_404(StoredFile, pk=pk, user=request.user)
    if request.method == 'POST':
        if not hasattr(request.user, 'profile') or not request.user.profile.face_image:
            messages.error(request, 'No registered face found for this account.')
            return redirect('file_list')
        face_data = request.POST.get('face_login_data') or ''
        if not face_data:
            messages.error(request, 'Face capture is required to download this file.')
            return redirect('file_list')
        if not faces_match(request.user.profile.face_image, face_data):
            messages.error(request, 'Face not recognized. Download blocked.')
            return redirect('file_list')
    obj.stego_image.open()
    buf = io.BytesIO(obj.stego_image.read())
    ct = extract_data_from_image(buf)
    data = aes_decrypt(request.user.id, bytes(obj.nonce), ct)
    resp = HttpResponse(data, content_type='application/octet-stream')
    resp['Content-Disposition'] = f'attachment; filename="{obj.original_name}"'
    return resp

# Create your views here.
