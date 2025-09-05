from django import forms

class BookingForm(forms.Form):
    THERAPY_TYPE_CHOICES = [
        ('cbt', 'Cognitive Behavioral Therapy'),
        ('couples', 'Couples Counseling'),
        ('mindfulness', 'Mindfulness Therapy'),
    ]

    SESSION_FORMAT_CHOICES = [
        ('face_to_face', 'Face to Face Session'),
        ('online', 'Online Session'),
    ]

    first_name = forms.CharField(max_length=80)
    last_name = forms.CharField(max_length=80)
    start = forms.CharField()

    therapy_type = forms.ChoiceField(choices=THERAPY_TYPE_CHOICES)
    session_format = forms.ChoiceField(choices=SESSION_FORMAT_CHOICES)
