from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator


class CoordinatesForm(forms.Form):
    latitude = forms.FloatField(
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
        widget=forms.NumberInput(attrs={'step': 'any', 'placeholder': 'ex: 48.8566'}),
    )
    longitude = forms.FloatField(
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
        widget=forms.NumberInput(attrs={'step': 'any', 'placeholder': 'ex: 2.3522'}),
    )
