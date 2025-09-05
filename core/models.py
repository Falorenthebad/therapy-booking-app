import secrets
from django.db import models
from django.utils import timezone

def generate_cancel_code() -> str:
    return secrets.token_urlsafe(6)

class Appointment(models.Model):
    THERAPY_TYPE_CHOICES = [
        ('cbt', 'Cognitive Behavioral Therapy'),
        ('couples', 'Couples Counseling'),
        ('mindfulness', 'Mindfulness Therapy'),
    ]

    SESSION_FORMAT_CHOICES = [
        ('face_to_face', 'Face to Face Session'),
        ('online', 'Online Session'),
    ]

    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    start_datetime = models.DateTimeField(unique=True, db_index=True)

    therapy_type = models.CharField(
        max_length=20,
        choices=THERAPY_TYPE_CHOICES,
        default='cbt',
    )
    session_format = models.CharField(
        max_length=20,
        choices=SESSION_FORMAT_CHOICES,
        default='face_to_face',
    )

    cancel_code = models.CharField(max_length=50, unique=True, db_index=True, default=generate_cancel_code)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ['start_datetime']

    def __str__(self):
        return f"{self.first_name} {self.last_name} @ {self.start_datetime}"

    @property
    def display_name(self):
        """Show first name + last initial (e.g., Steven J.)"""
        if self.last_name:
            return f"{self.first_name} {self.last_name[0]}."
        return self.first_name
