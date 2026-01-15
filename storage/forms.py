from django import forms

class UploadForm(forms.Form):
    file = forms.FileField()
    cover_image = forms.ImageField()
