from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from .models import AstraControlSession

User = get_user_model()

class AstraControlTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_create_session(self):
        response = self.client.post("/api/astra-control/sessions/", {
            "goal": "Test goal",
            "model": "gpt-4o"
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(AstraControlSession.objects.count(), 1)
        session = AstraControlSession.objects.first()
        self.assertEqual(session.goal, "Test goal")
        self.assertEqual(session.user, self.user)
        self.assertEqual(session.status, AstraControlSession.Status.RUNNING)
        self.assertIsNotNone(session.sandbox_session)

    def test_list_sessions(self):
        AstraControlSession.objects.create(goal="Goal 1", user=self.user)
        AstraControlSession.objects.create(goal="Goal 2", user=self.user)
        
        response = self.client.get("/api/astra-control/sessions/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)