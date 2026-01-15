from django.db import models
from django.contrib.auth.models import User

class StoredFile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stored_files')
    original_name = models.CharField(max_length=255)
    cover_image = models.ImageField(upload_to='covers/')
    stego_image = models.ImageField(upload_to='stego/')
    nonce = models.BinaryField()
    data_length = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_name

# Create your models here.
