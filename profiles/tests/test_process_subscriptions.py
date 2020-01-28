import datetime
import pytz
import pytest
from django.contrib.auth.models import User
from graphapi.tests.utils import populate_db
from profiles.models import Subscription
from opencivicdata.legislative.models import Bill
from ..management.commands.process_subscriptions import (
    process_bill_sub,
    process_subs_for_user,
    send_subscription_email,
)


@pytest.mark.django_db
def setup():
    populate_db()


@pytest.fixture
def user():
    u = User.objects.create(username="testuser")
    u.profile.feature_subscriptions = True
    u.profile.subscription_last_checked = pytz.utc.localize(
        datetime.datetime(2020, 1, 1)
    )
    u.profile.save()
    u.emailaddress_set.create(email="valid@example.com", verified=True, primary=True)
    return u


@pytest.mark.django_db
def test_process_bill_sub(user):
    hb1 = Bill.objects.get(identifier="HB 1")
    sub = Subscription(user=user, bill=hb1)

    now = datetime.datetime.now()
    now = pytz.utc.localize(now)
    yesterday = now - datetime.timedelta(days=1)

    # no changes since now
    assert process_bill_sub(sub, now) is None

    # bill changed in last day
    assert process_bill_sub(sub, yesterday) == (sub, hb1)


@pytest.mark.django_db
def test_process_subs_for_user_simple(user):
    hb1 = Bill.objects.get(identifier="HB 1")
    sub = Subscription.objects.create(
        user=user, bill=hb1, subjects=[], status=[], query=""
    )

    # last check is more than a day ago
    query_updates, bill_updates = process_subs_for_user(user)
    assert query_updates == []
    assert bill_updates == [(sub, hb1)]

    # we're within a week now
    user.profile.subscription_last_checked = pytz.utc.localize(datetime.datetime.now())
    user.profile.save()
    query_updates, bill_updates = process_subs_for_user(user)
    assert query_updates is None
    assert bill_updates is None


@pytest.mark.django_db
def test_send_email_simple(user, mailoutbox):
    hb1 = Bill.objects.get(identifier="HB 1")
    sub = Subscription.objects.create(
        user=user, bill=hb1, subjects=[], status=[], query=""
    )

    query_updates = []
    bill_updates = [(sub, hb1)]
    send_subscription_email(user, query_updates, bill_updates)

    assert len(mailoutbox) == 1
    msg = mailoutbox[0]
    assert msg.subject.endswith("1 update")
    assert "This is your automated alert from OpenStates.org for this week." in msg.body
    assert "had activity this week" in msg.body
    assert (
        "HB 1 - Moose Freedom Act (Alaska 2018) - https://openstates.org/ak/bills/2018/HB1/"
        in msg.body
    )
    assert "https://openstates.org/accounts/unsubscribe/" in msg.body
