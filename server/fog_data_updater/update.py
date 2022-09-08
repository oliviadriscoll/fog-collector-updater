import argparse
from dataclasses import dataclass, field
import datetime
import json
import logging
import os
from pathlib import Path
import time
from typing import List


import googleapiclient.discovery
from google.oauth2 import service_account
import requests


SPREADSHEET_ID = "1e_qMx2egdqsUFI_46u0JW1daivNzeVteudA5BwY-8oM"
DEVICE_SN = "z6-07496"
REQUEST_INTERVAL = 7  # in days
ZENTRA_RATE_LIMIT = 60  # in seconds


S_OK = 200
S_LOCKED = 423
S_RATE_LIMITED = 429


def query_zentra_raw(token, start_date, end_date, page_num, per_page):
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


@dataclass
class PortData:
    sensor_name: str
    ts: List[int] = field(default_factory=list)  # timestamps
    vs: List[float] = field(default_factory=list)  # values


# Returns a mapping from port number to `PortData`
def query_zentra(token, start_date, end_date):
    assert end_date >= start_date

    per_page = 1000
    start_time = int(start_date.timestamp())
    end_time = int(end_date.timestamp())

    result = {}
    earliest_seen = end_time
    page_num = 1

    while earliest_seen > start_time:
        response = query_zentra_raw(token, start_date, end_date, page_num, per_page)
        response_time = time.time()

        if response.status_code == S_OK:
            content = json.loads(response.content)

            # This happens only when the distance between `earliest_seen` and `start_time` is
            # smaller than the interval between precipitation measurements
            if "data" not in content or "Precipitation" not in content["data"]:
                break

            data = content["data"]["Precipitation"]
            for port_data in data:
                port = port_data["metadata"]["port_number"]
                if port not in result:
                    sensor_name = port_data["metadata"]["sensor_name"]
                    result[port] = PortData(sensor_name=sensor_name)

                for reading in port_data["readings"]:
                    result[port].ts.append(reading["timestamp_utc"])
                    result[port].vs.append(reading["value"])

            earliest_seen = max([port_result.ts[-1] for port_result in result.values()])
            page_num += 1

            progress = (end_time - earliest_seen) * 100 // (end_time - start_time)
            logging.info(f"ZENTRA data processed: {progress}%")
        elif response.status_code == S_LOCKED or response.status_code == S_RATE_LIMITED:
            logging.info(f"ZENTRA lockout recieved, waiting to retry...")
        else:
            response.raise_for_status()

        # ZENTRA only allows one request per sensor per minute
        time.sleep(max(0, ZENTRA_RATE_LIMIT - (time.time() - response_time)))

    return result


# Iterate over data returned by `query_zentra` in "row-major" order
def zentra_row_iter(data):
    def inner(i):
        for port_data in data.values():
            if i < len(port_data.ts):
                yield port_data.ts[i]
                yield port_data.vs[i]
            else:
                yield None
                yield None

    l = max(len(port_data.ts) for port_data in data.values())
    for i in range(l):
        yield inner(i)


def sheets_cell_number(v):
    return {"userEnteredValue": {"numberValue": v}} if v is not None else {}


def sheets_cell_string(s):
    return {"userEnteredValue": {"stringValue": s}} if s is not None else {}


# The resulting update treats each set of precipitation values as a column, since the Google sheets
# API only allows 25 columns to be appended in each request
def cell_update_from_data(data):
    updates = []

    headers = []
    for port, port_data in data.items():
        header = f"Port {port}: {port_data.sensor_name}"
        headers.append(sheets_cell_string(header))  # timestamps column header
        headers.append(sheets_cell_string(header))  # values column header
    updates.append({"values": headers})

    for row in zentra_row_iter(data):
        updates.append({"values": [sheets_cell_number(val) for val in row]})
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
    start_date = end_date - datetime.timedelta(days=REQUEST_INTERVAL)
    try:
        data = query_zentra(token, start_date, end_date)
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
