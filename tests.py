from __future__ import annotations
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import Appointment

TR_TZ = ZoneInfo("Europe/Istanbul")

def iso_in_tz(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TR_TZ)
    return dt.isoformat()

class TherapyAppointmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.FIXED_NOW = datetime(2025, 3, 3, 10, 0, tzinfo=TR_TZ)
        cls.client = Client()

    def _next_weekday(self, weekday: int, base: date | None = None) -> date:
        if base is None:
            base = self.FIXED_NOW.date()
        days_ahead = (weekday - base.weekday()) % 7
        return base + timedelta(days=days_ahead)

    def test_model_display_name(self):
        appt = Appointment.objects.create(
            first_name="Ada",
            last_name="Lovelace",
            start_datetime=self.FIXED_NOW + timedelta(days=1),
            therapy_type="cbt",
            session_format="online",
        )
        self.assertEqual(appt.display_name, "Ada L.")

        appt2 = Appointment.objects.create(
            first_name="Grace",
            last_name="",
            start_datetime=self.FIXED_NOW + timedelta(days=2),
            therapy_type="cbt",
            session_format="online",
        )
        self.assertEqual(appt2.display_name, "Grace")

    def test_unique_start_datetime_enforced(self):
        start_dt = self.FIXED_NOW + timedelta(days=1, hours=1)
        Appointment.objects.create(
            first_name="A",
            last_name="B",
            start_datetime=start_dt,
            therapy_type="cbt",
            session_format="online",
        )
        with self.assertRaises(Exception):
            Appointment.objects.create(
                first_name="X",
                last_name="Y",
                start_datetime=start_dt,
                therapy_type="cbt",
                session_format="online",
            )

    @patch("core.views.ist_now")
    def test_generate_candidate_slots_and_sunday(self, mock_now):
        from core.views import generate_candidate_slot_datetimes, is_sunday

        mock_now.return_value = self.FIXED_NOW
        sun = self._next_weekday(6)
        mon = self._next_weekday(0)
        self.assertTrue(is_sunday(sun))
        self.assertFalse(is_sunday(mon))

        slots_sun = generate_candidate_slot_datetimes(sun)
        self.assertEqual(slots_sun, [])

        slots_mon = generate_candidate_slot_datetimes(mon)
        self.assertEqual([dt.hour for dt in slots_mon], [9, 10, 11, 14, 15, 16])
        self.assertTrue(all(dt.tzinfo == TR_TZ for dt in slots_mon))

    @patch("core.views.ist_now")
    def test_filter_slots_past_and_booked(self, mock_now):
        from core.views import filter_slots_for_availability, generate_candidate_slot_datetimes

        mock_now.return_value = self.FIXED_NOW
        today = self.FIXED_NOW.date()
        slots_today = generate_candidate_slot_datetimes(today)

        avail_today = filter_slots_for_availability(today)
        self.assertTrue(all(dt.hour > 10 for dt in avail_today))

        tomorrow = today + timedelta(days=1)
        slots_tomorrow = generate_candidate_slot_datetimes(tomorrow)
        booked = slots_tomorrow[0]
        Appointment.objects.create(
            first_name="Book",
            last_name="Ed",
            start_datetime=booked,
            therapy_type="cbt",
            session_format="online",
        )
        avail_tomorrow = filter_slots_for_availability(tomorrow)
        self.assertNotIn(booked, avail_tomorrow)
        self.assertTrue(len(avail_tomorrow) < len(slots_tomorrow) and len(avail_tomorrow) >= 1)

    @patch("core.views.ist_now")
    def test_slots_for_day_marks_available_and_unavailable(self, mock_now):
        from core.views import slots_for_day, generate_candidate_slot_datetimes

        mock_now.return_value = self.FIXED_NOW
        today = self.FIXED_NOW.date()
        slots = slots_for_day(today)
        by_hour = {s["dt"].hour: s["available"] for s in slots}
        self.assertFalse(by_hour[9])
        self.assertFalse(by_hour[10])
        self.assertTrue(by_hour[11])

        future_dt = generate_candidate_slot_datetimes(today)[-1]
        Appointment.objects.create(
            first_name="Taken",
            last_name="Slot",
            start_datetime=future_dt,
            therapy_type="cbt",
            session_format="face_to_face",
        )
        slots2 = slots_for_day(today)
        by_hour2 = {s["dt"].hour: s["available"] for s in slots2}
        self.assertFalse(by_hour2[16])

    @patch("core.views.ist_now")
    def test_days_for_this_and_next_week(self, mock_now):
        from core.views import days_for_this_and_next_week

        mock_now.return_value = self.FIXED_NOW
        weeks = days_for_this_and_next_week()
        this_week = weeks["this_week"]
        next_week = weeks["next_week"]

        self.assertTrue(all(d.weekday() in {0, 1, 2, 3, 4, 5} for d in this_week))
        self.assertTrue(all(d.weekday() in {0, 1, 2, 3, 4, 5} for d in next_week))
        self.assertTrue(all(d >= self.FIXED_NOW.date() for d in this_week))
        self.assertTrue(all(d >= (self.FIXED_NOW.date() + timedelta(days=7)) for d in next_week))

    @patch("core.views.ist_now")
    def test_book_get_lists_slots(self, mock_now):
        mock_now.return_value = self.FIXED_NOW
        resp = self.client.get(reverse("book"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("weeks", resp.context)
        self.assertIn("slots_this", resp.context)
        self.assertIn("slots_next", resp.context)

    @patch("core.views.ist_now")
    def test_book_success_creates_appointment_and_redirects(self, mock_now):
        mock_now.return_value = self.FIXED_NOW
        tomorrow = self.FIXED_NOW.date() + timedelta(days=1)
        start_dt = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 11, tzinfo=TR_TZ)

        data = {
            "first_name": "John",
            "last_name": "Doe",
            "ui_therapy_type": "cbt",
            "ui_format": "online",
            "start": iso_in_tz(start_dt),
        }
        
        resp = self.client.post(reverse("book"), data, follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/confirm/", resp["Location"])
        self.assertIn("appointment_code", resp.cookies)
        self.assertTrue(Appointment.objects.filter(start_datetime=start_dt).exists())

    @patch("core.views.ist_now")
    def test_book_rejects_invalid_time(self, mock_now):
        mock_now.return_value = self.FIXED_NOW
        day = self.FIXED_NOW.date() + timedelta(days=2)
        invalid_dt = datetime(day.year, day.month, day.day, 13, tzinfo=TR_TZ)
        data = {
            "first_name": "A",
            "last_name": "B",
            "ui_therapy_type": "cbt",
            "ui_format": "face_to_face",
            "start": iso_in_tz(invalid_dt),
        }
        resp = self.client.post(reverse("book"), data, follow=True)
        self.assertEqual(resp.status_code, 200)
        msgs = list(resp.context["messages"])
        self.assertTrue(any("Selected time is not valid." in str(m) for m in msgs))

    @patch("core.views.ist_now")
    def test_book_rejects_past_or_now(self, mock_now):
        mock_now.return_value = self.FIXED_NOW
        today = self.FIXED_NOW.date()
        past_dt = datetime(today.year, today.month, today.day, 10, tzinfo=TR_TZ)
        data = {
            "first_name": "A",
            "last_name": "B",
            "ui_therapy_type": "cbt",
            "ui_format": "online",
            "start": iso_in_tz(past_dt),
        }
        resp = self.client.post(reverse("book"), data, follow=True)
        msgs = list(resp.context["messages"])
        self.assertTrue(any("no longer available" in str(m) for m in msgs))

    @patch("core.views.ist_now")
    def test_book_rejects_sunday(self, mock_now):
        mock_now.return_value = self.FIXED_NOW
        sunday = self._next_weekday(6)
        chosen = datetime(sunday.year, sunday.month, sunday.day, 11, tzinfo=TR_TZ)
        data = {
            "first_name": "A",
            "last_name": "B",
            "ui_therapy_type": "cbt",
            "ui_format": "online",
            "start": iso_in_tz(chosen),
        }
        resp = self.client.post(reverse("book"), data, follow=True)
        msgs = list(resp.context["messages"])
        self.assertTrue(any("Sunday" in str(m) for m in msgs))

    @patch("core.views.ist_now")
    def test_book_double_booking_atomic(self, mock_now):
        mock_now.return_value = self.FIXED_NOW
        day = self.FIXED_NOW.date() + timedelta(days=1)
        slot = datetime(day.year, day.month, day.day, 14, tzinfo=TR_TZ)
        Appointment.objects.create(
            first_name="First",
            last_name="User",
            start_datetime=slot,
            therapy_type="cbt",
            session_format="online",
        )
        data = {
            "first_name": "Second",
            "last_name": "User",
            "ui_therapy_type": "mindfulness",
            "ui_format": "face_to_face",
            "start": iso_in_tz(slot),
        }
        resp = self.client.post(reverse("book"), data, follow=True)
        msgs = list(resp.context["messages"])
        self.assertTrue(any("just booked by someone else" in str(m) for m in msgs))

    @patch("core.views.ist_now")
    def test_confirm_shows_code_once(self, mock_now):
        mock_now.return_value = self.FIXED_NOW
        start_dt = self.FIXED_NOW + timedelta(days=1, hours=1)
        appt = Appointment.objects.create(
            first_name="Jane",
            last_name="Doe",
            start_datetime=start_dt,
            therapy_type="cbt",
            session_format="online",
        )
        session = self.client.session
        session["code_to_show"] = appt.cancel_code
        session.save()

        url = reverse("confirm", kwargs={"code": appt.cancel_code})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["show_code"])

        resp2 = self.client.get(url)
        self.assertEqual(resp2.status_code, 200)
        self.assertFalse(resp2.context["show_code"])

    @patch("core.views.ist_now")
    def test_appointments_with_code(self, mock_now):
        mock_now.return_value = self.FIXED_NOW
        start_dt = self.FIXED_NOW + timedelta(days=3, hours=2)
        appt = Appointment.objects.create(
            first_name="Ali",
            last_name="Veli",
            start_datetime=start_dt,
            therapy_type="couples",
            session_format="face_to_face",
        )
        resp = self.client.get(reverse("appointments"), {"code": appt.cancel_code})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["appt"].id, appt.id)
        self.assertIn("end_dt", resp.context)

    def test_appointments_without_code(self):
        resp = self.client.get(reverse("appointments"))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.context["appt"])

    def test_cancel_lookup_redirects(self):
        resp = self.client.get(reverse("cancel_lookup"), follow=True)
        self.assertEqual(resp.resolver_match.view_name, "appointments")
        msgs = list(resp.context["messages"])
        self.assertTrue(any("Please enter a reference code." in str(m) for m in msgs))

    def test_cancel_check_api(self):
        start_dt = timezone.now() + timedelta(days=1)
        appt = Appointment.objects.create(
            first_name="X",
            last_name="Y",
            start_datetime=start_dt,
            therapy_type="cbt",
            session_format="online",
        )
        ok_resp = self.client.get(reverse("cancel_check"), {"code": appt.cancel_code})
        self.assertJSONEqual(ok_resp.content, {"ok": True})

        not_ok_resp = self.client.get(reverse("cancel_check"), {"code": "nope"})
        self.assertJSONEqual(not_ok_resp.content, {"ok": False})

    @patch("core.views.ist_now")
    def test_cancel_post_wrong_code(self, mock_now):
        mock_now.return_value = self.FIXED_NOW
        start_dt = self.FIXED_NOW + timedelta(days=2)
        appt = Appointment.objects.create(
            first_name="Will",
            last_name="Err",
            start_datetime=start_dt,
            therapy_type="mindfulness",
            session_format="face_to_face",
        )
        url = reverse("cancel", kwargs={"code": appt.cancel_code})
        resp = self.client.post(url, {"confirm_code": "WRONG"}, follow=True)
        self.assertEqual(resp.status_code, 200)
        msgs = list(resp.context["messages"])
        self.assertTrue(any("does not match" in str(m) for m in msgs))
        self.assertTrue(Appointment.objects.filter(id=appt.id).exists())

    @patch("core.views.ist_now")
    def test_cancel_post_ok_deletes_and_clears_cookie(self, mock_now):
        mock_now.return_value = self.FIXED_NOW
        start_dt = self.FIXED_NOW + timedelta(days=2)
        appt = Appointment.objects.create(
            first_name="Can",
            last_name="Sil",
            start_datetime=start_dt,
            therapy_type="cbt",
            session_format="online",
        )

        self.client.cookies["appointment_code"] = appt.cancel_code
        url = reverse("cancel", kwargs={"code": appt.cancel_code})
        resp = self.client.post(url, {"confirm_code": appt.cancel_code}, follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("appointments"), resp["Location"])
        self.assertFalse(Appointment.objects.filter(id=appt.id).exists())
        set_cookie_headers = [c for c in resp.cookies.values() if c.key == "appointment_code"]
        self.assertTrue(set_cookie_headers and set_cookie_headers[0]["max-age"] == 0)
