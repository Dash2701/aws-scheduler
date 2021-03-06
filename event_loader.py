import json
import os
from datetime import timedelta, datetime

from lambda_client import invoke_lambda
from model import table
from util import make_chunks


def run():
    now = datetime.utcnow()
    until = (now + timedelta(minutes=5)).isoformat()

    last_evaluated_key = None

    count = 0
    # emulated do while loop
    while True:

        response = load_data(until, last_evaluated_key)

        if response['Count'] == 0:
            break
        else:
            count += response['Count']

        ids = []
        for item in response['Items']:
            ids.append(item['id'])

        for chunk in make_chunks(ids, 200):
            invoke_lambda(os.environ.get('SCHEDULE_FUNCTION'), json.dumps(chunk).encode('utf-8'))

        if 'LastEvaluatedKey' in response:
            print('Continuing at next page')
            last_evaluated_key = response['LastEvaluatedKey']
        else:
            print('Finished loading data')
            break

    print('Batched %d entries' % count)


def load_data(until, last_evaluated_key, limit=5000, status='NEW'):
    if last_evaluated_key is None:
        response = table.query(
            IndexName=os.environ.get('INDEX_NAME'),
            KeyConditionExpression='#status = :st and #date < :until',
            ExpressionAttributeNames={"#status": "status", "#date": "date"},
            ExpressionAttributeValues={":until": until, ':st': status},
            Limit=limit,
            ProjectionExpression='id'
        )
    else:
        response = table.query(
            IndexName=os.environ.get('INDEX_NAME'),
            KeyConditionExpression='#status = :st and #date < :until',
            ExpressionAttributeNames={"#status": "status", "#date": "date"},
            ExpressionAttributeValues={":until": until, ':st': status},
            Limit=limit,
            ProjectionExpression='id',
            ExclusiveStartKey=last_evaluated_key
        )
    return response
