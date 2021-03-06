import json
import math
import os
from datetime import datetime
from uuid import uuid4

from db_helper import save_with_retry
from util import make_chunks
from lambda_client import invoke_lambda
from sns_client import publish_sns


def publish_to_failure_topic(event, reason):
    # todo: prepare against failure of publish sns
    print('Event failed: %s' % event)
    if 'failure_topic' in event:
        payload = {
            'error': reason,
            'event': event
        }
        publish_sns(event['failure_topic'], json.dumps(payload))


def handle(events):
    received = datetime.utcnow()
    to_be_scheduled = []
    event_wrappers = []
    for event in events:
        if 'date' not in event:
            publish_to_failure_topic(event, 'date is required')
            print('error.date_required %s' % (json.dumps({'event': event})))
            continue
        if 'payload' not in event:
            publish_to_failure_topic(event, 'payload is required')
            print('error.payload_required %s' % (json.dumps({'event': event})))
            continue
        if 'target' not in event:
            publish_to_failure_topic(event, 'target is required')
            print('error.target_required %s' % (json.dumps({'event': event})))
            continue

        if not isinstance(event['payload'], str):
            publish_to_failure_topic(event, 'payload must be a string')
            print('error.payload_is_not_string %s' % (json.dumps({'event': event})))
            continue

        event_wrapper = {
            'id': str(uuid4()),
            'date': event['date'],
            'payload': event['payload'],
            'target': event['target'],
            'status': 'NEW'
        }

        if 'failure_topic' in event:
            event_wrapper['failure_topic'] = event['failure_topic']

        if 'user' not in event:
            if os.environ.get('ENFORCE_USER'):
                publish_to_failure_topic(event, 'user is required')
                print('error.event_has_no_user %s' % (json.dumps({'event': event})))
                continue
        else:
            event_wrapper['user'] = event['user']

        # if the event has less than 10 minutes until execution, then fast track it
        if has_less_then_ten_minutes(event_wrapper['date']):
            to_be_scheduled.append(event_wrapper['id'])

        print('event.consumed %s' % (json.dumps({'id': event_wrapper['id'], 'timestamp': str(received)})))
        event_wrappers.append(event_wrapper)

    # we must save before delegating, because the downstream function will access the DB entity
    save_with_retry(event_wrappers)

    print('Fast track scheduling for %d entries' % len(to_be_scheduled))
    for chunk in make_chunks(to_be_scheduled, 200):
        ids = json.dumps(chunk).encode('utf-8')
        invoke_lambda(os.environ.get('SCHEDULE_FUNCTION'), ids)

    print('Processed %d entries' % len(events))


def has_less_then_ten_minutes(date):
    minutes = int(get_seconds_remaining(date) / 60)
    return minutes < 10


def get_seconds_remaining(date):
    now = datetime.utcnow()
    target = datetime.fromisoformat(date)
    delta = target - now
    return math.ceil(delta.total_seconds())
