import argparse
from collections import defaultdict
import datetime
import json
import logging
import os
from pathlib import Path
import time


import googleapiclient.discovery
from google.oauth2 import service_account
import requests


SPREADSHEET_ID = "1e_qMx2egdqsUFI_46u0JW1daivNzeVteudA5BwY-8oM"
DEVICE_SN = "z6-07496"


def query_zentra_one(token, start_date, end_date, page_num, per_page):
    url = "https://zentracloud.com/api/v3/get_readings/"
    headers = {"content-type": "application/json", "Authorization": f"Token {token}"}
    params = {
        "device_sn": DEVICE_SN,
        "start_date": start_date,
        "end_date": end_date,
        "page_num": page_num,
        "per_page": per_page,
    }
    return requests.get(url, params=params, headers=headers)


# Returns data of the form:
# [([port 0 timestamps], [port 0 values]), ([port 1 timestamps], [port 1 values]), ...]
def query_zentra_all(token, start_date, end_date):
    assert end_date >= start_date

    per_page = 500
    start_time = start_date.timestamp()
    end_time = end_date.timestamp()

    earliest_seen = end_time
    page_num = 1
    result = defaultdict(lambda: ([], []))

    while earliest_seen > start_time:
        response = query_zentra_one(token, start_date, end_date, page_num, per_page)

        if response.status_code == 200:
            data = json.loads(response.content)["data"]["Precipitation"]
            for port_data in data:
                name = port_data["metadata"]["sensor_name"]
                for reading in port_data["readings"]:
                    result[name][0].append(reading["timestamp_utc"])
                    result[name][1].append(reading["value"])

            earliest_seen = max([port_result[0][-1] for port_result in result.values()])
            page_num += 1

            progress = (end_time - earliest_seen) * 100 // (end_time - start_time)
            logging.info(f"ZENTRA data processed: {progress}%")
        elif response.status_code == 423:
            logging.info(f"ZENTRA lockout recieved, waiting to retry...")
        else:
            response.raise_for_status()

        # ZENTRA only allows one request per sensor per minute
        time.sleep(60)

    return result


def sheets_cell_number(v):
    return {"userEnteredValue": {"numberValue": v}}


def sheets_cell_string(s):
    return {"userEnteredValue": {"stringValue": s}}


def sheets_row(name, values):
    row = [sheets_cell_string(name)]
    for value in values:
        row.append(sheets_cell_number(value))
    return {"values": row}


def cell_update_from_data(data):
    updates = []
    for port_name, port_data in data:
        updates.append(f"{port_name} timestamps", port_data[0])
        updates.append(f"{port_name} values", port_data[1])
    return updates


def main():
    logging.basicConfig(level=os.environ.get("PYTHON_LOG", "INFO"))

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "service_account_file",
        help="A JSON credentials file for the service account to be used when accessing Google Sheets. See: https://stackoverflow.com/a/69941050.",
    )
    parser.add_argument(
        "zentra_token_file",
        help="A file containing the API token to be used when accessing ZENTRA. This token should NOT include the 'Token ' prefix.",
    )
    args = parser.parse_args()

    token = Path(args.zentra_token_file).read_text()

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = service_account.Credentials.from_service_account_file(
        args.service_account_file
    )
    creds = creds.with_scopes(scopes)
    service = googleapiclient.discovery.build("sheets", "v4", credentials=creds)

    # https://stackoverflow.com/questions/38245714/get-list-of-sheets-and-latest-sheet-in-google-spreadsheet-api-v4-in-python
    metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheets = metadata.get("sheets", "")
    sheet_id = sheets[0].get("properties", {}).get("sheetId", 0)

    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=30)
    try:
        data = query_zentra_all(token, start_date, end_date)
    except Exception as e:
        logging.error(f"Request to ZENTRA failed:\n{e}")
        return

    # https://googleapis.github.io/google-api-python-client/docs/dyn/sheets_v4.spreadsheets.html
    # https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/batchUpdate
    body = {
        "requests": [
            {
                "deleteRange": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "startColumnIndex": 0,
                    },
                    "shiftDimension": "ROWS",
                },
            },
            {
                "appendCells": {
                    "sheetId": sheet_id,
                    "rows": cell_update_from_data(data),
                    "fields": "userEnteredValue",
                }
            },
        ]
    }
    try:
        (
            service.spreadsheets()
            .batchUpdate(spreadsheetId=SPREADSHEET_ID, body=body)
            .execute()
        )
    except Exception as e:
        logging.error(f"Request to Google failed:\n{e}")
        return

    logging.info("Update complete 🎉")


if __name__ == "__main__":
    main()
