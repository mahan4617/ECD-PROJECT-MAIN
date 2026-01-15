from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .models import StoredFile
from .serializers import StoredFileSerializer
from .utils import aes_encrypt, hide_data_in_image
from django.core.files.base import ContentFile
import io

class StoredFileList(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = StoredFile.objects.filter(user=request.user).order_by('-created_at')
        return Response(StoredFileSerializer(qs, many=True).data)

class StoredFileUpload(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        up_file = request.FILES.get('file')
        cover = request.FILES.get('cover_image')
        if not up_file or not cover:
            return Response({'detail': 'file and cover_image are required'}, status=status.HTTP_400_BAD_REQUEST)
        data = up_file.read()
        ct, nonce = aes_encrypt(request.user.id, data)
        cover.seek(0)
        buf = io.BytesIO(cover.read())
        stego_img = hide_data_in_image(buf, ct)
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
        return Response({'id': obj.id, 'original_name': obj.original_name}, status=status.HTTP_201_CREATED)
