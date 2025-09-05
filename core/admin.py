from django.contrib import admin
from .models import Appointment

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        'first_name', 'last_name',
        'start_datetime',
        'therapy_type', 'session_format',
        'cancel_code', 'created_at'
    )
    search_fields = ('first_name', 'last_name', 'cancel_code')
    list_filter = ('start_datetime', 'therapy_type', 'session_format')
