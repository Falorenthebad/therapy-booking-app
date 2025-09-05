from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.contrib import messages
from django.http import JsonResponse
from .models import Appointment
from .forms import BookingForm

TR_TZ = ZoneInfo('Europe/Istanbul')

SLOT_HOURS = [9, 10, 11, 14, 15, 16]
WEEKDAYS_WORK = {0, 1, 2, 3, 4, 5}

def ist_now():
    return timezone.now().astimezone(TR_TZ)

def is_sunday(d: date) -> bool:
    return d.weekday() == 6

def generate_candidate_slot_datetimes(d: date):
    if is_sunday(d):
        return []
    return [datetime(d.year, d.month, d.day, h, 0, tzinfo=TR_TZ) for h in SLOT_HOURS]

def filter_slots_for_availability(d: date):
    today = ist_now().date()
    if d < today:
        return []
    candidates = generate_candidate_slot_datetimes(d)
    if not candidates:
        return []
    now = ist_now()
    filtered = []
    for dt in candidates:
        if d == today and dt <= now:
            continue
        if Appointment.objects.filter(start_datetime=dt).exists():
            continue
        filtered.append(dt)
    return filtered

def slots_for_day(d: date):
    """Tüm slotları (boş/dolu) işaretli döndürür; Book sayfasında dolu/geçmiş saatleri sönük göstermek için."""
    today = ist_now().date()
    if d < today or is_sunday(d):
        return []

    candidates = generate_candidate_slot_datetimes(d)
    now = ist_now()

    slots = []
    for dt in candidates:
        is_past = (d == today and dt <= now)
        is_booked = Appointment.objects.filter(start_datetime=dt).exists()
        slots.append({
            'dt': dt,
            'available': not (is_past or is_booked),
        })
    return slots

def week_monday(today: date) -> date:
    return today - timedelta(days=today.weekday())

def days_for_this_and_next_week():
    today = ist_now().date()
    this_mon = week_monday(today)
    next_mon = this_mon + timedelta(days=7)

    def mon_to_sat(mon: date):
        days = [mon + timedelta(days=i) for i in range(6)]
        return [d for d in days if d.weekday() in WEEKDAYS_WORK]

    this_week_all = mon_to_sat(this_mon)
    this_week = [d for d in this_week_all if d >= today]
    next_week = mon_to_sat(next_mon)
    return {'this_week': this_week, 'next_week': next_week}

def home(request):
    return render(request, 'home.html')

def book(request):
    if request.method == 'POST':
        data = request.POST.copy()
        if 'therapy_type' not in data and 'ui_therapy_type' in data:
            data['therapy_type'] = data.get('ui_therapy_type')
        if 'session_format' not in data and 'ui_format' in data:
            data['session_format'] = data.get('ui_format')

        form = BookingForm(data)
        if form.is_valid():
            first_name = form.cleaned_data['first_name'].strip()
            last_name = form.cleaned_data['last_name'].strip()
            therapy_type = form.cleaned_data['therapy_type']
            session_format = form.cleaned_data['session_format']

            start_iso = form.cleaned_data['start'].strip()
            try:
                start_dt = datetime.fromisoformat(start_iso)
            except ValueError:
                messages.error(request, "Invalid time selection.")
                return redirect('book')

            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=TR_TZ)

            sel_date = start_dt.date()
            if is_sunday(sel_date):
                messages.error(request, "Selected date is not available (Sunday).")
                return redirect('book')

            valid_today_slots = generate_candidate_slot_datetimes(sel_date)
            if start_dt not in valid_today_slots:
                messages.error(request, "Selected time is not valid.")
                return redirect('book')

            now = ist_now()
            if start_dt <= now:
                messages.error(request, "This time is no longer available.")
                return redirect('book')

            try:
                with transaction.atomic():
                    appt = Appointment.objects.create(
                        first_name=first_name,
                        last_name=last_name,
                        start_datetime=start_dt,
                        therapy_type=therapy_type,
                        session_format=session_format,
                    )
            except IntegrityError:
                messages.error(request, "That time slot was just booked by someone else. Please pick another.")
                return redirect('book')

            request.session['code_to_show'] = appt.cancel_code

            resp = redirect('confirm', code=appt.cancel_code)
            max_age = 60 * 60 * 24 * 30
            resp.set_cookie('appointment_code', appt.cancel_code, max_age=max_age, samesite='Lax')
            return resp

        # HATALI FORM: tüm slotları (available/unavailable) hazırla ve form hatalarını şablonda göster
        weeks = days_for_this_and_next_week()
        slots_this = {d: slots_for_day(d) for d in weeks['this_week']}
        slots_next = {d: slots_for_day(d) for d in weeks['next_week']}
        return render(request, 'book.html', {
            'form': form,
            'weeks': weeks,
            'slots_this': slots_this,
            'slots_next': slots_next
        })

    form = BookingForm()
    weeks = days_for_this_and_next_week()
    # GET -> haftalık slotları (tümü: available/unavailable) hazırla
    slots_this = {d: slots_for_day(d) for d in weeks['this_week']}
    slots_next = {d: slots_for_day(d) for d in weeks['next_week']}
    return render(request, 'book.html', {
        'form': form,
        'weeks': weeks,
        'slots_this': slots_this,
        'slots_next': slots_next
    })

def confirm(request, code: str):
    appt = get_object_or_404(Appointment, cancel_code=code)
    end_dt = appt.start_datetime + timedelta(hours=1)
    show_code = request.session.get('code_to_show') == appt.cancel_code
    if show_code:
        try:
            del request.session['code_to_show']
        except KeyError:
            pass
    return render(request, 'confirm.html', {'appt': appt, 'end_dt': end_dt, 'show_code': show_code})

def appointments(request):
    """
    Bu sayfa artık genel herkese açık randevu listelemiyor.
    Kullanıcıdan code (serial key) bekliyor. Doğru code girilirse randevu gösteriliyor.
    Cookie ile otomatik bulma ve modal/JS kaldırıldı.
    """
    code = (request.GET.get('code') or '').strip()
    appt = Appointment.objects.filter(cancel_code=code).first() if code else None
    ctx = {'appt': appt, 'code': code}
    if appt:
        ctx['end_dt'] = appt.start_datetime + timedelta(hours=1)
    return render(request, 'appointments.html', ctx)

def cancel(request, code: str):
    appt = get_object_or_404(Appointment, cancel_code=code)
    end_dt = appt.start_datetime + timedelta(hours=1)

    if request.method == 'POST':
        confirm_code = (request.POST.get('confirm_code') or '').strip()
        if confirm_code != appt.cancel_code:
            messages.error(request, "Reference code does not match. Please try again.")
            return render(request, 'cancel.html', {'appt': appt, 'end_dt': end_dt})

        appt.delete()
        messages.success(request, "Your appointment has been cancelled.")
        resp = redirect('appointments')
        resp.delete_cookie('appointment_code')
        return resp

    return render(request, 'cancel.html', {'appt': appt, 'end_dt': end_dt})

def cancel_lookup(request):
    """(Opsiyonel) Formdan gelen code ile cancel sayfasına yönlendirir."""
    code = (request.GET.get('code') or '').strip()
    if not code:
        messages.error(request, "Please enter a reference code.")
        return redirect('appointments')
    return redirect('cancel', code=code)

def cancel_check(request):
    code = (request.GET.get('code') or '').strip()
    ok = Appointment.objects.filter(cancel_code=code).exists()
    return JsonResponse({'ok': bool(ok)})
